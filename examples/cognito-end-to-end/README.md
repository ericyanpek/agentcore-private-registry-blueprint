# Cognito + Identity Pool + CodeArtifact — end-to-end live demo

Status: ✅ Verified end-to-end on 2026-05-26 against a real AWS account.

## What it does

A self-contained Python script that **provisions, exercises, and tears
down** the entire Cognito identity layer described in
[`docs/10-end-user-access.md`](../../docs/10-end-user-access.md). In
~30 seconds it proves that the design works as documented:

```
Cognito User Pool group
    → JWT cognito:groups claim
       → Identity Pool rule match
          → IAM role with scoped CodeArtifact ARN
             → CodeArtifact returns wheel bytes
```

Both a **positive** test (user in group → success) and a **negative**
test (user NOT in group → Identity Pool rejects) run, so you can see
the isolation actually enforced rather than merely described.

## What gets created (and destroyed)

The script provisions, then unconditionally cleans up in `finally`:

- `SkillsDemo-Cognito-Live-UserPool` — Cognito User Pool
- `skills-readers-demo` — Cognito Group inside the pool
- `SkillsDemo-Cognito-Live-Client` — App Client (admin auth flow)
- `alice@demo.local` — user in `skills-readers-demo` (positive test)
- `bob@demo.local` — user NOT in any group (negative test)
- `SkillsDemo_Cognito_Live_IdPool` — Cognito Identity Pool
- `SkillsDemoCognitoLiveReader` — IAM role assumed via web identity,
  scoped to `skills-prod` CodeArtifact repository

After the run, none of these exist. The CodeArtifact repo from the
Day-1 demo is **read but not modified**.

## Prerequisites

You need IAM permissions on whichever principal runs this:

- `cognito-idp:*` (broad — User Pool admin)
- `cognito-identity:*` (Identity Pool admin)
- `iam:CreateRole / GetRole / DeleteRole / PutRolePolicy / DeleteRolePolicy`
  scoped to `SkillsDemo*` role names is sufficient
- `codeartifact:*` already granted in the Day-1 demo

The blueprint expects the Day-1 CodeArtifact resources to already
exist (`skills-demo` domain, `skills-prod` repository, with the
`aws-cost-anomaly-triage` package version `0.1.0` published). Run
the regular `cdk deploy` + publish flow first if not.

## Run it

```bash
cd examples/cognito-end-to-end
python3 run_demo.py
```

Expected runtime: 25–35 seconds. Most of that is the IAM role
propagation wait (8s) — Cognito itself is fast.

## What you'll see (real run output)

The script prints 12 numbered steps. Highlights:

```
Step 9: Alice — admin_initiate_auth → JWT
  ✅ id_token received (len=1135)
     claims preview: sub=049834c8-c0d1-7040-...
                     email=alice@demo.local
                     groups=['skills-readers-demo']

Step 10: Alice's IAM creds → real CodeArtifact pull
  who am I? arn:aws:sts::<acct>:assumed-role/SkillsDemoCognitoLiveReader/CognitoIdentityCredentials
  ✅ ListPackageVersions succeeded — 1 version(s):
       0.1.0  (Published)
  ✅ GetPackageVersionAsset succeeded — 11555 bytes pulled

Step 11: Bob (no group) — should be REJECTED
  bob authenticated; claims.cognito:groups = None
  ✅ as expected — Identity Pool denied bob:
     error code: NotAuthorizedException
     message: The ambiguous role mapping rules for: ... denied this request.
```

## Why this matters

Before running this script, the documentation merely *asserts* that
group→role isolation works. After running, you have **direct API
evidence** for every link in the chain:

| Documented claim | Demonstrated by |
|---|---|
| Cognito User Pool authenticates a user | `admin_initiate_auth` returns id_token |
| Group membership ends up as JWT claim | Decoded claims show `cognito:groups` for Alice, `None` for Bob |
| Identity Pool exchanges JWT for IAM creds | `get_credentials_for_identity` returns `AccessKeyId`, `SessionToken` |
| Scoped IAM role only allows configured repo | Alice's session can call `codeartifact:GetPackageVersionAsset` |
| Without group, no role is issued | Bob's `get_credentials_for_identity` raises `NotAuthorizedException` |
| CloudTrail-traceable identity in CodeArtifact | Caller arn is `assumed-role/.../CognitoIdentityCredentials` — that session name encodes the Cognito identity id |

## Edge cases the script does NOT cover

- Browser-based OAuth code flow with PKCE (uses `admin_initiate_auth`
  for headless reproducibility)
- Refresh token expiry behavior
- IAM Identity Center as an alternative path
- SAML / OIDC federation upstream of Cognito
- Cognito Advanced Security adaptive auth

These are documented in `docs/10-end-user-access.md` but require
either a browser session or upstream IdP setup that this self-contained
script can't fake.

## Reading the source

`run_demo.py` is ~280 LOC, structured as 12 numbered steps each
preceded by a `banner()` call. Read it top-to-bottom; the order
matches the architecture: identity → groups → client → users → pool
→ role → mapping → JWT → exchange → use → reject test → cleanup.

The `cleanup()` function runs in `finally`, so even on failure you
won't leak resources.
