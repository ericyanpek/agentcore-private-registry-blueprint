"""skill-cli — minimal client for end-user JWT → AWS credentials flow.

Goal: an end-user runs `skill-cli login` once, then standard tools
like `pip install <skill>` or `aws codeartifact login` Just Work,
with NO ~/.aws/credentials file containing secrets.

How:
  1. `skill-cli login`
       Opens a browser to Cognito Hosted UI, completes OAuth code flow,
       exchanges id_token for temporary IAM credentials via Cognito
       Identity Pool, stores credentials + refresh_token in OS keyring.

  2. `skill-cli get-credentials`
       Prints credentials in the JSON shape AWS SDKs expect from a
       `credential_process`. Auto-refreshes if expired.

  3. ~/.aws/config (the only on-disk file, contains NO secrets):

       [profile skills]
       credential_process = skill-cli get-credentials

  4. End-user runs `pip install <skill>` (or anything else AWS) with
     AWS_PROFILE=skills — the SDK invokes step 2 transparently.

This is a minimal viable implementation (~150 LOC). Production
hardening:
  - device_code flow as fallback when no browser available
  - encrypted refresh_token at rest (keyring already encrypts on macOS/Win;
    Linux Secret Service requires unlock)
  - friendlier error messages when corp SSO returns IdP-specific failures
  - telemetry / opt-in usage analytics
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.server
import json
import os
import secrets
import sys
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Any, Optional

try:
    import boto3
    import keyring
    import requests
except ImportError as e:
    sys.exit(
        f"missing dependency ({e.name}). Install with:\n"
        "  pip install boto3 keyring requests"
    )

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:
    try:
        import tomli as tomllib  # type: ignore
    except ModuleNotFoundError:
        tomllib = None  # graceful: env vars still work without TOML support

KEYRING_SERVICE = "skill-cli"
TOKEN_KEY = "tokens_json"  # stores {access_token, id_token, refresh_token, expires_at}
CREDS_KEY = "aws_creds_json"  # stores {AccessKeyId, SecretAccessKey, SessionToken, Expiration}

CONFIG_PATH = Path.home() / ".skillpublish" / "skill-cli.toml"
CALLBACK_PATH = "/callback"

# Cognito requires the redirect_uri sent to /oauth2/authorize to *exactly*
# match a registered callbackUrl on the app client (no port wildcarding,
# unlike RFC 8252 §7.3 loopback equivalence). So this port has to be a
# fixed value that matches what IdentityStack registers in CDK. If the
# port is in use locally, --callback-port lets the user override it,
# but the matching value must also be added to the Cognito app client's
# callback URL list (otherwise OAuth fails with redirect_mismatch).
DEFAULT_CALLBACK_PORT = 8765

# Required keys; map TOML key → env var name
_REQUIRED_KEYS = {
    "region": "SKILL_CLI_REGION",
    "user_pool_id": "SKILL_CLI_USER_POOL_ID",
    "client_id": "SKILL_CLI_USER_POOL_CLIENT_ID",
    "user_pool_domain": "SKILL_CLI_USER_POOL_DOMAIN",
    "identity_pool_id": "SKILL_CLI_IDENTITY_POOL_ID",
}


def _load_toml_config(path: Path = CONFIG_PATH) -> dict:
    """Read [default] section from ~/.skillpublish/skill-cli.toml if present."""
    if not path.exists() or tomllib is None:
        return {}
    with path.open("rb") as f:
        data = tomllib.load(f)
    return data.get("default", {}) or {}


def cognito_config() -> dict:
    """Resolve Cognito endpoints/IDs from (in order of precedence):
        1. Environment variables (SKILL_CLI_*)
        2. ~/.skillpublish/skill-cli.toml [default] section
       And error out clearly listing whichever keys are still missing.

    Example skill-cli.toml:
        [default]
        region = "us-east-1"
        user_pool_id = "us-east-1_AbCdEfG"
        client_id = "abc123"
        user_pool_domain = "my-pool.auth.us-east-1.amazoncognito.com"
        identity_pool_id = "us-east-1:identity-pool-uuid"
    """
    toml_cfg = _load_toml_config()
    resolved: dict = {}
    missing: list[str] = []
    for toml_key, env_key in _REQUIRED_KEYS.items():
        val = os.environ.get(env_key) or toml_cfg.get(toml_key)
        if val is None:
            missing.append(f"{env_key} (or [default].{toml_key} in {CONFIG_PATH})")
        else:
            resolved[toml_key] = val
    if missing:
        sys.exit(
            "missing required configuration:\n  - "
            + "\n  - ".join(missing)
            + "\n\nSet them as environment variables OR create "
            f"{CONFIG_PATH} with a [default] section."
        )
    return resolved


def _make_pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) per RFC 7636 S256."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).decode("ascii").rstrip("=")
    return verifier, challenge


# ── Browser OAuth flow ─────────────────────────────────────────────


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """Tiny localhost HTTP server to capture OAuth redirect.

    The expected flow:
      browser → Cognito Hosted UI → 302 → http://localhost:<port>/callback?code=...&state=...

    We capture both `code` and `state`. `login()` validates state matches
    the CSRF token it generated, before touching the code.
    """
    captured_code: Optional[str] = None
    captured_state: Optional[str] = None
    captured_error: Optional[str] = None

    def do_GET(self) -> None:  # noqa: N802
        if not self.path.startswith(CALLBACK_PATH):
            self.send_response(404)
            self.end_headers()
            return
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        if "error" in params:
            _CallbackHandler.captured_error = params["error"][0]
            self.send_response(400)
            self.end_headers()
            self.wfile.write(
                b"<html><body><h2>Login failed.</h2>"
                b"<p>Check the terminal for details.</p></body></html>"
            )
            return
        _CallbackHandler.captured_code = params.get("code", [None])[0]
        _CallbackHandler.captured_state = params.get("state", [None])[0]
        if _CallbackHandler.captured_code:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h2>Login complete.</h2>"
                b"<p>You can close this tab.</p></body></html>"
            )
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"missing code parameter")

    def log_message(self, *_args: Any) -> None:
        pass  # silence default logging


def login(cfg: dict, callback_port: int = DEFAULT_CALLBACK_PORT) -> dict:
    """Run OAuth code flow with PKCE + state → return token bundle.

    Implements RFC 8252 (OAuth 2.0 for Native Apps) recommendations:
      - PKCE S256 (code_verifier + code_challenge)
      - CSRF state parameter, validated on callback

    Note on the loopback port: Cognito does NOT honor RFC 8252 §7.3
    loopback port equivalence — the redirect_uri must literally match
    a registered callbackUrl on the app client. So the port is a fixed
    constant matching what `cdk/lib/identity-stack.ts` registers
    (8765). If port 8765 is in use, override via `--callback-port`,
    BUT you must also register that port's callback URL on the Cognito
    app client (via `aws cognito-idp update-user-pool-client`).
    """
    redirect_uri = f"http://localhost:{callback_port}{CALLBACK_PATH}"
    try:
        server = http.server.HTTPServer(
            ("localhost", callback_port), _CallbackHandler,
        )
    except OSError as e:
        sys.exit(
            f"could not bind localhost:{callback_port} ({e}). "
            f"Is another OAuth tool running? Pass --callback-port <other> "
            f"AND register that callback URL on your Cognito app client."
        )

    code_verifier, code_challenge = _make_pkce_pair()
    state = secrets.token_urlsafe(32)

    auth_url = (
        f"https://{cfg['user_pool_domain']}/oauth2/authorize?"
        + urllib.parse.urlencode({
            "client_id": cfg["client_id"],
            "response_type": "code",
            "scope": "openid email profile",
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": state,
        })
    )

    server_thread = threading.Thread(target=server.handle_request, daemon=True)
    server_thread.start()

    print(f"opening browser for SSO login (callback on port {callback_port})...")
    print(f"if no browser opens (e.g. on a headless server), open this URL manually:\n  {auth_url}\n")
    opened = webbrowser.open(auth_url)
    if not opened:
        print("(webbrowser.open returned False — paste the URL above into a browser)")
    server_thread.join(timeout=300)
    server.server_close()

    if _CallbackHandler.captured_error:
        sys.exit(f"OAuth provider returned error: {_CallbackHandler.captured_error}")

    code = _CallbackHandler.captured_code
    received_state = _CallbackHandler.captured_state
    if not code:
        sys.exit(
            "did not receive auth code within 5 minutes (browser closed, "
            "denied, or timed out). Re-run `skill-cli login`."
        )
    if received_state != state:
        sys.exit(
            "OAuth state mismatch — possible CSRF attempt. "
            "Aborting login. Try `skill-cli login` again."
        )

    # Exchange code for tokens — include code_verifier per PKCE spec
    token_url = f"https://{cfg['user_pool_domain']}/oauth2/token"
    resp = requests.post(token_url, data={
        "grant_type": "authorization_code",
        "client_id": cfg["client_id"],
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
    }, headers={"Content-Type": "application/x-www-form-urlencoded"})
    resp.raise_for_status()
    tokens = resp.json()
    tokens["expires_at"] = int(time.time()) + int(tokens.get("expires_in", 3600))
    return tokens


class TokenRefreshError(Exception):
    """Raised when refresh_tokens() can't recover.

    `recoverable=True` means transient (5xx, network) — caller should
    retry. False means the refresh_token is dead — caller should
    redirect the user to `skill-cli login`.
    """
    def __init__(self, message: str, recoverable: bool = False) -> None:
        super().__init__(message)
        self.recoverable = recoverable


def refresh_tokens(cfg: dict, refresh_token: str) -> dict:
    """Use refresh_token to get new id_token without browser."""
    token_url = f"https://{cfg['user_pool_domain']}/oauth2/token"
    try:
        resp = requests.post(token_url, data={
            "grant_type": "refresh_token",
            "client_id": cfg["client_id"],
            "refresh_token": refresh_token,
        }, headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30)
    except requests.RequestException as e:
        raise TokenRefreshError(f"network error: {e}", recoverable=True) from e
    if resp.status_code >= 500:
        raise TokenRefreshError(
            f"Cognito returned {resp.status_code} (transient). Try again.",
            recoverable=True,
        )
    if resp.status_code >= 400:
        # 4xx — refresh_token rejected. User must re-login.
        raise TokenRefreshError(
            f"refresh_token rejected ({resp.status_code}). "
            "Run: skill-cli login",
            recoverable=False,
        )
    tokens = resp.json()
    tokens["expires_at"] = int(time.time()) + int(tokens.get("expires_in", 3600))
    # Cognito does not always return a new refresh_token; keep the old one.
    if "refresh_token" not in tokens:
        tokens["refresh_token"] = refresh_token
    return tokens


# ── Identity Pool exchange ─────────────────────────────────────────


def jwt_to_aws_creds(cfg: dict, id_token: str) -> dict:
    """Trade JWT for temp IAM creds via Cognito Identity Pool."""
    cog = boto3.client("cognito-identity", region_name=cfg["region"])
    provider = (
        f"cognito-idp.{cfg['region']}.amazonaws.com/{cfg['user_pool_id']}"
    )
    logins = {provider: id_token}

    id_resp = cog.get_id(
        IdentityPoolId=cfg["identity_pool_id"], Logins=logins,
    )
    creds_resp = cog.get_credentials_for_identity(
        IdentityId=id_resp["IdentityId"], Logins=logins,
    )
    c = creds_resp["Credentials"]
    return {
        "Version": 1,
        "AccessKeyId": c["AccessKeyId"],
        "SecretAccessKey": c["SecretKey"],
        "SessionToken": c["SessionToken"],
        # AWS SDK credential_process expects ISO-8601 expiration
        "Expiration": c["Expiration"].isoformat(),
    }


# ── Keyring storage ────────────────────────────────────────────────


def save_tokens(tokens: dict) -> None:
    keyring.set_password(KEYRING_SERVICE, TOKEN_KEY, json.dumps(tokens))


def load_tokens() -> Optional[dict]:
    raw = keyring.get_password(KEYRING_SERVICE, TOKEN_KEY)
    return json.loads(raw) if raw else None


def save_creds(creds: dict) -> None:
    keyring.set_password(KEYRING_SERVICE, CREDS_KEY, json.dumps(creds))


def load_creds() -> Optional[dict]:
    raw = keyring.get_password(KEYRING_SERVICE, CREDS_KEY)
    return json.loads(raw) if raw else None


def creds_expired(creds: dict, leeway_s: int = 60) -> bool:
    if not creds.get("Expiration"):
        return True
    from datetime import datetime, timezone
    try:
        exp = datetime.fromisoformat(creds["Expiration"].replace("Z", "+00:00"))
    except Exception:
        return True
    return (exp - datetime.now(timezone.utc)).total_seconds() < leeway_s


# ── Subcommands ────────────────────────────────────────────────────


def cmd_login(args: argparse.Namespace) -> int:
    cfg = cognito_config()
    tokens = login(cfg, callback_port=args.callback_port)
    save_tokens(tokens)
    creds = jwt_to_aws_creds(cfg, tokens["id_token"])
    save_creds(creds)
    print("login successful. credentials cached in OS keyring.")
    print(f"  expires: {creds['Expiration']}")
    return 0


def cmd_get_credentials(args: argparse.Namespace) -> int:
    """Called transparently by AWS SDKs via credential_process."""
    cfg = cognito_config()
    creds = load_creds()
    if creds and not creds_expired(creds):
        print(json.dumps(creds))
        return 0

    # Need to refresh. Use cached refresh_token to get a new id_token
    # without bothering the user.
    tokens = load_tokens()
    if not tokens or not tokens.get("refresh_token"):
        sys.exit("no cached login. Run: skill-cli login")

    try:
        new_tokens = refresh_tokens(cfg, tokens["refresh_token"])
    except TokenRefreshError as e:
        # Recoverable (5xx, network) → AWS SDK will retry credential_process
        # itself. Non-recoverable (4xx) → user must re-login.
        sys.exit(str(e))
    if not new_tokens.get("id_token"):
        sys.exit("refresh response missing id_token. Run: skill-cli login")
    save_tokens(new_tokens)
    creds = jwt_to_aws_creds(cfg, new_tokens["id_token"])
    save_creds(creds)
    print(json.dumps(creds))
    return 0


def cmd_logout(args: argparse.Namespace) -> int:
    for k in (TOKEN_KEY, CREDS_KEY):
        try:
            keyring.delete_password(KEYRING_SERVICE, k)
        except keyring.errors.PasswordDeleteError:
            pass
    print("logged out (keyring cleared).")
    return 0


def cmd_whoami(args: argparse.Namespace) -> int:
    """Show the current cached identity (for debugging)."""
    tokens = load_tokens()
    if not tokens:
        print("not logged in")
        return 1
    # Decode id_token claims (no verification — just for display).
    id_token = tokens.get("id_token", "")
    parts = id_token.split(".")
    if len(parts) != 3:
        print("invalid id_token in keyring")
        return 1
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    claims = json.loads(base64.urlsafe_b64decode(payload))
    print(f"email: {claims.get('email')}")
    print(f"sub:   {claims.get('sub')}")
    print(f"groups: {claims.get('cognito:groups', [])}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="skill-cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    p_login = sub.add_parser("login",
                              help="Browser SSO login + cache credentials")
    p_login.add_argument(
        "--callback-port", type=int, default=DEFAULT_CALLBACK_PORT,
        help=(
            f"Local OAuth callback port (default: {DEFAULT_CALLBACK_PORT}). "
            "Must match a callbackUrl registered on your Cognito app client."
        ),
    )
    sub.add_parser("get-credentials",
                    help="Print AWS credentials JSON (for credential_process)")
    sub.add_parser("logout", help="Clear keyring")
    sub.add_parser("whoami", help="Show cached identity")
    args = p.parse_args()
    return {
        "login": cmd_login,
        "get-credentials": cmd_get_credentials,
        "logout": cmd_logout,
        "whoami": cmd_whoami,
    }[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
