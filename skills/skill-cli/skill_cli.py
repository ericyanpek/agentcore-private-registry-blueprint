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
import http.server
import json
import os
import sys
import threading
import time
import urllib.parse
import webbrowser
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

KEYRING_SERVICE = "skill-cli"
TOKEN_KEY = "tokens_json"  # stores {access_token, id_token, refresh_token, expires_at}
CREDS_KEY = "aws_creds_json"  # stores {AccessKeyId, SecretAccessKey, SessionToken, Expiration}

CALLBACK_PORT = 8765
CALLBACK_PATH = "/callback"


def env_or(key: str, default: Optional[str] = None) -> str:
    """Read a value from env, fall back to default, error if neither."""
    val = os.environ.get(key, default)
    if val is None:
        sys.exit(
            f"missing required environment variable {key} — "
            "either export it or set it in ~/.skillpublish/skill-cli.env"
        )
    return val


def cognito_config() -> dict:
    """Resolve all Cognito endpoints/IDs from env. Required:
        SKILL_CLI_REGION
        SKILL_CLI_USER_POOL_ID
        SKILL_CLI_USER_POOL_CLIENT_ID
        SKILL_CLI_USER_POOL_DOMAIN     (e.g., my-pool.auth.us-east-1.amazoncognito.com)
        SKILL_CLI_IDENTITY_POOL_ID
    """
    return {
        "region": env_or("SKILL_CLI_REGION"),
        "user_pool_id": env_or("SKILL_CLI_USER_POOL_ID"),
        "client_id": env_or("SKILL_CLI_USER_POOL_CLIENT_ID"),
        "user_pool_domain": env_or("SKILL_CLI_USER_POOL_DOMAIN"),
        "identity_pool_id": env_or("SKILL_CLI_IDENTITY_POOL_ID"),
    }


# ── Browser OAuth flow ─────────────────────────────────────────────


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """Tiny localhost HTTP server to capture OAuth redirect."""
    captured_code: Optional[str] = None

    def do_GET(self) -> None:  # noqa: N802
        if not self.path.startswith(CALLBACK_PATH):
            self.send_response(404)
            self.end_headers()
            return
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        code = params.get("code", [None])[0]
        if code:
            _CallbackHandler.captured_code = code
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


def login(cfg: dict) -> dict:
    """Run OAuth code flow → return token bundle (id_token + refresh_token)."""
    redirect_uri = f"http://localhost:{CALLBACK_PORT}{CALLBACK_PATH}"
    auth_url = (
        f"https://{cfg['user_pool_domain']}/oauth2/authorize?"
        + urllib.parse.urlencode({
            "client_id": cfg["client_id"],
            "response_type": "code",
            "scope": "openid email profile",
            "redirect_uri": redirect_uri,
        })
    )

    server = http.server.HTTPServer(("localhost", CALLBACK_PORT),
                                     _CallbackHandler)
    server_thread = threading.Thread(target=server.handle_request, daemon=True)
    server_thread.start()

    print(f"opening browser for SSO login...")
    webbrowser.open(auth_url)
    server_thread.join(timeout=300)
    server.server_close()

    code = _CallbackHandler.captured_code
    if not code:
        sys.exit("did not receive auth code (timeout or denied)")

    # Exchange code for tokens
    token_url = f"https://{cfg['user_pool_domain']}/oauth2/token"
    resp = requests.post(token_url, data={
        "grant_type": "authorization_code",
        "client_id": cfg["client_id"],
        "code": code,
        "redirect_uri": redirect_uri,
    }, headers={"Content-Type": "application/x-www-form-urlencoded"})
    resp.raise_for_status()
    tokens = resp.json()
    tokens["expires_at"] = int(time.time()) + int(tokens.get("expires_in", 3600))
    return tokens


def refresh_tokens(cfg: dict, refresh_token: str) -> dict:
    """Use refresh_token to get new id_token without browser."""
    token_url = f"https://{cfg['user_pool_domain']}/oauth2/token"
    resp = requests.post(token_url, data={
        "grant_type": "refresh_token",
        "client_id": cfg["client_id"],
        "refresh_token": refresh_token,
    }, headers={"Content-Type": "application/x-www-form-urlencoded"})
    if resp.status_code != 200:
        return {}
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
    tokens = login(cfg)
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

    new_tokens = refresh_tokens(cfg, tokens["refresh_token"])
    if not new_tokens.get("id_token"):
        sys.exit("refresh failed (refresh token may be expired). "
                 "Run: skill-cli login")
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
    import base64
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    claims = json.loads(base64.urlsafe_b64decode(payload))
    print(f"email: {claims.get('email')}")
    print(f"sub:   {claims.get('sub')}")
    print(f"groups: {claims.get('cognito:groups', [])}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="skill-cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("login", help="Browser SSO login + cache credentials")
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
