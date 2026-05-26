# End-user access — Cognito Identity Pool + zero-config clients

> Audience: a platform engineer who needs hundreds or thousands of
> non-IAM users (analysts, support agents, business users, and yes,
> developers) to consume private skills without ever touching an
> AWS access key.

## The honest constraint

There are two physically distinct user populations:

| User type | Where their agent runs | Can be 100% server-side |
|---|---|---|
| Business user via claude.ai web, Claude.ai for Slack, Bedrock AgentCore Runtime, Claude Cowork, or any company-hosted agent UI | **In AWS / Anthropic infra** | ✅ **Yes — no client work needed** |
| Developer using Claude Code desktop / Cursor / local CLI agents | **On their laptop** | ❌ No — local processes need local credentials |

For the first group the Registry is consumed by the runtime itself,
which has its own IAM service role. **There is no end-user access
problem to solve there**; the rest of this doc focuses on the
second group.

For the second group, "zero local config" is achievable but
"zero local state" is not — `pip install` runs locally, so AWS
credentials must reach the local process somehow. The bar this
blueprint sets:

- **Zero configuration files containing secrets** ✅
- **Zero AWS-specific terminology in the user's daily flow** ✅
- **One browser login per ~30 days; transparent the rest of the time** ✅
- **Zero AWS credentials traversing the user's filesystem** ❌ Impossible
- **Credentials stored in OS keyring, not files** ✅ Best achievable

## The architecture

```
┌──────────────────────────────────────────────────────────────┐
│  [User Pool] — identity                                       │
│   - Authenticates users (federation-friendly: Okta/Entra/...) │
│   - Manages groups: finops-readers, customer-care-readers, …  │
│   - Issues JWT (id_token contains cognito:groups claim)        │
└───────────────────────────────┬──────────────────────────────┘
                                │ id_token (JWT)
                                ▼
┌──────────────────────────────────────────────────────────────┐
│  [Identity Pool] — credentials                                │
│   - Verifies JWT signature against User Pool JWKS              │
│   - Reads cognito:groups claim                                 │
│   - Maps group → IAM role, assumes via STS:AssumeRoleWithWebIdentity │
│   - Returns 1-hour temp IAM credentials                        │
└───────────────────────────────┬──────────────────────────────┘
                                │ AccessKey + SecretKey + SessionToken
                                ▼
┌──────────────────────────────────────────────────────────────┐
│  [CodeArtifact / Agent Registry / S3 / anything IAM]           │
│   - Standard SigV4 auth                                        │
│   - Sees the assumed role's identity                           │
│   - Resource policy decides what each role can do              │
└──────────────────────────────────────────────────────────────┘
```

The whole stack is **zero self-hosted code**. No Lambda. No proxy.
The only thing you ship is a small client (`skill-cli`, ~500 LOC of
Python including PKCE, retry/refresh, and keyring storage) that runs
the OAuth flow.

## Why Identity Pool, not a custom JWT-to-IAM bridge

The blueprint earlier discussed a "SkillProxy" Lambda that verifies
JWT and pulls from CodeArtifact on the user's behalf. That works
but introduces a service to run, scale, and maintain. **Cognito
Identity Pool is the AWS-native version of exactly the same
translation step**, configured with CDK and zero code.

| | Custom Lambda (SkillProxy) | Identity Pool (this doc) |
|---|---|---|
| Self-managed code | ~200 LOC + tests | 0 |
| Tools available | Just CodeArtifact (or whatever you wire) | Any AWS service the role can talk to |
| Identity in CloudTrail | Lambda execution role (proxy logs map to user) | The assumed role with `cognito-identity:userId` in session context — direct CloudTrail attribution |
| User experience | `pip install` works once tokens injected | Same |
| Cost | Lambda invocations + ALB | Free (Identity Pool + STS calls) |

The SkillProxy approach is documented as an alternative in
[docs/05-auth-placeholder.md](./05-auth-placeholder.md) for cases
where you need access-decision logic richer than what IAM policies
can express. For the standard "different teams pull different
repos" case, Identity Pool wins.

## Group → IAM role mapping (the heart of the system)

This is what enforces "the FinOps team's skills are not visible to
the customer care team." Two layers:

### Layer 1 — search visibility

The Agent Registry's search results are filtered by what the
calling principal has `bedrock-agentcore:SearchRegistryRecords`
permission for. If you create a separate registry per team and
limit each team's role to its own registry ARN, **users from one
team cannot see records from another team's registry**.

### Layer 2 — artifact pull permission

Even if a user got hold of a CodeArtifact package name, they can
only pull from repositories their assumed IAM role permits. The
`IdentityStack` constructs one IAM role per Cognito group, with
`Resource` scoped to a specific repository.

A user in `customer-care-readers` cannot `pip install` a package
from `finops-skills-prod` because the role they get from Identity
Pool has no `codeartifact:ReadFromRepository` on that ARN.

## Provisioning the identity layer (CDK)

The blueprint ships `cdk/lib/identity-stack.ts`. It is **off by
default** — to deploy it:

```bash
cd cdk
npx cdk deploy --all \
  -c enableIdentity=true \
  -c 'groupRepoMap={"finops-readers":"finops-skills-prod","customer-care-readers":"customer-care-skills-prod"}'
```

What gets created:

- A User Pool with email sign-in, MFA optional, password policy,
  one app client for `skill-cli`'s OAuth flow
- A `skills-readers` group (default) plus one group per key in
  `groupRepoMap`
- An Identity Pool wired to the User Pool
- One IAM role per group, scoped to the named CodeArtifact
  repository
- A role-attachment with `ambiguousRoleResolution: Deny` (a user
  belonging to no listed group is rejected, not silently mapped to
  the default)

Outputs include `UserPoolId`, `UserPoolClientId`, `IdentityPoolId`,
and `OidcDiscoveryUrl` — paste these into `skill-cli` env vars
(see below).

## skill-cli — the end-user side

`skills/skill-cli/skill_cli.py` is ~500 lines of Python (PKCE flow,
keyring, refresh, error handling). Authors
package and ship it via the regular skill publishing flow (it could
itself be a skill if you want recursive composition, but it doesn't
have to be).

### Subcommands

```
skill-cli login            # browser OAuth, cache tokens + creds in OS keyring
skill-cli get-credentials  # print AWS creds JSON (for credential_process)
skill-cli logout           # clear keyring
skill-cli whoami           # show cached identity
```

### Where do the secrets live?

| Item | Storage |
|---|---|
| Cognito `id_token`, `refresh_token` | OS keyring (KEYRING_SERVICE = "skill-cli") |
| Temp IAM `AccessKeyId/SecretAccessKey/SessionToken` | OS keyring |
| AWS profile pointer | `~/.aws/config` — plain text but contains no secrets |

OS keyring is encrypted at rest by the OS (Keychain on macOS, DPAPI
on Windows, libsecret on Linux). An attacker with offline access to
the user's home directory cannot recover anything.

### How users use it

```bash
# One-time: write Cognito endpoint config (NO secrets)
mkdir -p ~/.skillpublish && cat > ~/.skillpublish/skill-cli.toml <<'EOF'
[default]
region = "us-east-1"
user_pool_id = "us-east-1_AbCdEfG"
client_id = "<client-id>"
user_pool_domain = "<your-pool>.auth.us-east-1.amazoncognito.com"
identity_pool_id = "us-east-1:<identity-pool-uuid>"
EOF

# One-time: write AWS profile pointer (NO secrets)
mkdir -p ~/.aws && cat >> ~/.aws/config <<'EOF'
[profile skills]
credential_process = skill-cli get-credentials
EOF

# One-time: pip install + login
pip install boto3 keyring requests
pip install <skill-cli-package>   # or run from source
skill-cli login

# Daily use: nothing — pip / aws / boto3 with AWS_PROFILE=skills just work
AWS_PROFILE=skills pip install aws-cost-anomaly-triage
```

After `skill-cli login` exits, the user's machine has:

- `~/.skillpublish/skill-cli.toml` — endpoint identifiers, no secrets
- `~/.aws/config` — a 2-line plain text pointer
- OS keyring — the actual credentials, OS-encrypted

That's all. No `~/.aws/credentials` file, no plaintext token anywhere.

**Configuration precedence**: env vars (`SKILL_CLI_*`) override TOML
when both are set; TOML is recommended for daily use, env vars for CI.

### OAuth security details

The login flow implements the RFC 8252 ("OAuth 2.0 for Native Apps")
recommendations:

- **PKCE S256** — every login generates a fresh `code_verifier`; the
  derived `code_challenge` goes into the authorize URL; the verifier
  goes into the token exchange. Without it, an attacker with the
  authorization code (e.g., a malicious browser extension) could
  exchange it for tokens.
- **CSRF state** — a random `state` parameter ties the callback to the
  request that started the login. Mismatch → abort.
- **Loopback redirect with OS-assigned port** — `skill-cli` binds port 0
  and reads back what the OS assigned, so multiple OAuth tools on the
  same machine don't collide on a fixed port.

## Sequence — Alice installs a skill

```
T+0     Claude Code (or Alice in terminal): pip install aws-cost-anomaly-triage
        (with AWS_PROFILE=skills)

T+0.1s  AWS SDK sees credential_process; runs `skill-cli get-credentials`

T+0.1s  skill-cli reads keyring:
        - cached IAM creds present?
          - yes, not expired → print them, exit
          - yes, expired → fall through
          - no → fall through
        - cached refresh_token present?
          - yes → POST /oauth2/token with grant_type=refresh_token
                  → fresh id_token (no browser)
                  → exchange for IAM creds via Identity Pool
                  → cache and print
          - no → exit("Run: skill-cli login")

T+0.5s  pip receives credentials, configures itself

T+0.6s  pip → CodeArtifact endpoint (signed with Alice's assumed-role creds)

T+0.6s  CodeArtifact verifies SigV4, sees role
        SkillsReader-FinOps assumed by cognito-uuid-alice; checks resource
        policy; serves the wheel

T+1s    pip install completes; install-aws-cost-anomaly-triage runs;
        ~/.claude/skills/aws-cost-anomaly-triage/ is populated
```

CloudTrail end-to-end:

```
{
  "eventName": "GetPackageVersionAsset",
  "userIdentity": {
    "type": "AssumedRole",
    "principalId": "AROAXXX:cognito-uuid-alice",
    "arn": "arn:aws:sts::111122223333:assumed-role/SkillsReader-FinOps/cognito-uuid-alice",
    "sessionContext": {
      "webIdFederationData": {
        "federatedProvider": "cognito-identity.amazonaws.com",
        "attributes": { "cognito-identity.amazonaws.com:sub": "us-east-1:..." }
      }
    }
  }
}
```

The audit chain is:
- CloudTrail entry references the assumed role
- AssumeRoleWithWebIdentity event references the Cognito Identity ID
- Cognito Identity → User Pool sub → email — full traceback to
  `alice@company.com`

## Edge cases

### Alice on a server (no browser available)

`skill-cli login` opens a browser. On a server, two options:

- **OAuth Device Flow** — the standard fallback. User sees a code
  on the server terminal, opens https://device.example/ on their
  phone, types the code. Cognito User Pool supports this if you
  configure the app client appropriately. (Not in MVP; documented
  as Phase 2 in skills/skill-cli/README.md)
- **Pre-authenticated profile** — for CI/CD where there's no
  human, prefer GitHub Actions OIDC or IAM Identity Center direct
  IAM assume-role rather than skill-cli.

### Alice in a country where Cognito Hosted UI is slow

Cognito User Pool Hosted UI can be backed by your own domain via
custom domain mapping. The latency hit is one-time on login, not
per-pip-install — usually acceptable.

### Refresh token expires (after 30 days of inactivity)

`skill-cli get-credentials` prints a clear error pointing the user
to `skill-cli login`. The browser opens, user re-authenticates via
SSO, done.

### Bob steals Alice's laptop

Within the OS-locked period (Alice's user session locked), keyring
is sealed. After Alice's password is cracked, Bob has up to
30 days of refresh-token life. **Mitigations:**

- Set User Pool client `RefreshTokenValidity` to a shorter window
  (7 days instead of 30) — more re-logins, faster revocation
- Configure Cognito Advanced Security to detect anomalous IPs and
  force re-MFA on next refresh
- IT initiates User Pool admin force sign-out (`AdminUserGlobalSignOut`)
  on offboarding — kills all refresh tokens immediately

## Decision tree — picking the right access pattern

```
Are end-users humans typing into Claude Code on their own laptops?
│
├─ No (they use claude.ai, Bedrock Runtime, web UI, etc.)
│  → Don't build any client tooling. Runtime uses its own IAM service
│     role. Just configure Cognito JWT inbound auth on the Registry
│     for human-facing surfaces if needed.
│
└─ Yes
   │
   ├─ Are users a small dev team that's already on AWS IAM Identity
   │  Center?
   │  → Use IAM Identity Center directly. `aws sso login` →
   │     `aws codeartifact login`. Zero new infrastructure.
   │
   ├─ Hundreds+ users with team-based isolation needs, no Identity Center?
   │  → THIS DOC. Cognito User Pool + Identity Pool + skill-cli.
   │     Group-to-role mapping enforces team isolation.
   │
   └─ Need access decisions richer than IAM resource policies can
      express (e.g., per-skill-record allow-lists, time-of-day
      restrictions, custom approval flows)?
      → Add a SkillProxy Lambda after Identity Pool. JWT/IAM does
        the broad sweep, Lambda does the fine-grained logic.
        Documented in docs/05.
```

## What's still TODO (Phase 2)

- Device Flow path in `skill-cli` for headless servers
- Sample SAML federation config (Okta, Entra ID, Google Workspace)
  — currently only native Cognito users work end-to-end
- Custom domain on Cognito Hosted UI (so the URL is
  `auth.skills.company.com`, not `xxx.amazoncognito.com`)
- Migration playbook for orgs already using IAM Identity Center —
  when to consolidate, when to keep both
- Per-skill access lists (skill record `_meta` declares allowed
  groups; consumed by a SkillProxy Lambda; out of scope for the
  pure Identity Pool path)

## See also

- [docs/05-auth-placeholder.md](./05-auth-placeholder.md) — broader
  auth context including JWT-to-Registry direct (no Identity Pool)
- [docs/09-publishing-iam.md](./09-publishing-iam.md) — Publisher
  and Curator IAM roles (still IAM-based, complementary to this doc)
- [skills/skill-cli/](../skills/skill-cli/) — the client tool
- `cdk/lib/identity-stack.ts` — the CDK that creates everything
