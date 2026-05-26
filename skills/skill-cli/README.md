# skill-cli

A minimal client tool that bridges Cognito JWT login → temporary AWS
IAM credentials, with **zero AWS config files containing secrets**.

## What it does

```
$ skill-cli login        # one time per ~30 days
opening browser for SSO login...
login successful. credentials cached in OS keyring.

$ pip install <some-skill>   # works transparently
```

The bridge is the standard AWS SDK `credential_process` mechanism:

```ini
# ~/.aws/config (the only on-disk file, NO secrets)
[profile skills]
credential_process = skill-cli get-credentials
```

When `pip` (or `aws`, or `boto3`) runs with `AWS_PROFILE=skills`, the
SDK invokes `skill-cli get-credentials`, which:

1. Reads cached temp IAM credentials from OS keyring
2. If expired, silently refreshes using the cached refresh_token
3. If refresh_token is dead, prints "Run: skill-cli login"
4. Otherwise prints credentials JSON to stdout

User never sees the credentials. Never edits a file.

## Setup

Set environment variables (once, in shell rc):

```bash
export SKILL_CLI_REGION="us-east-1"
export SKILL_CLI_USER_POOL_ID="<from CDK output: UserPoolId>"
export SKILL_CLI_USER_POOL_CLIENT_ID="<from CDK output: UserPoolClientId>"
export SKILL_CLI_USER_POOL_DOMAIN="<your-pool>.auth.us-east-1.amazoncognito.com"
export SKILL_CLI_IDENTITY_POOL_ID="<from CDK output: IdentityPoolId>"
```

Install dependencies:

```bash
pip install boto3 keyring requests
```

Configure AWS profile (one line, no secrets):

```bash
mkdir -p ~/.aws
cat >> ~/.aws/config <<'EOF'
[profile skills]
credential_process = skill-cli get-credentials
EOF
```

First login:

```bash
skill-cli login
```

## Daily use

```bash
# Once a month or so:
skill-cli login

# Every day, transparently:
AWS_PROFILE=skills aws codeartifact login --tool pip --domain ... --repository ...
AWS_PROFILE=skills pip install <some-skill>
```

If you're using Claude Code, set `AWS_PROFILE=skills` once in your
shell environment and any tool Claude invokes will pick it up.

## Subcommands

| Command | What it does |
|---|---|
| `skill-cli login` | Browser OAuth → keyring |
| `skill-cli get-credentials` | Print creds JSON (called automatically by AWS SDKs) |
| `skill-cli logout` | Clear keyring |
| `skill-cli whoami` | Show cached identity (email, groups) |

## Where the secrets live

| Item | Location |
|---|---|
| `id_token`, `refresh_token` | OS keyring (`KEYRING_SERVICE = "skill-cli"`) |
| Temp `AccessKeyId` / `SecretAccessKey` / `SessionToken` | OS keyring |
| AWS profile pointer | `~/.aws/config` (plain text, but no secrets) |
| **Anywhere else** | Nothing |

OS keyring is encrypted at rest by:

- macOS: Keychain (login session encrypted)
- Windows: Credential Manager (DPAPI)
- Linux: GNOME Secret Service or KWallet (Secret Service API)

This means an attacker with read access to your home directory but
not your unlocked OS user session **cannot recover credentials**.

## Security notes

- `skill-cli` does NOT validate JWT signatures locally — it trusts
  Cognito's responses over HTTPS. Identity Pool validates JWTs
  server-side; that's the actual enforcement point.
- Refresh tokens last 30 days by default (Cognito User Pool client
  config). Shorter = more re-logins, but better post-compromise
  recovery.
- The localhost callback listener (port 8765) only runs during
  active login. It captures only the OAuth `code` parameter.

## What this is NOT

- Not a replacement for SSO. The actual identity check happens at
  Cognito Hosted UI, federated to your corporate IdP if configured.
- Not a credential broker / proxy. It runs on the user's machine,
  uses standard OAuth + Cognito Identity Pool APIs.
- Not pinned to this blueprint. The same pattern works for any
  Cognito User Pool + Identity Pool deployment.

For the architecture rationale see
[`../../docs/10-end-user-access.md`](../../docs/10-end-user-access.md).
