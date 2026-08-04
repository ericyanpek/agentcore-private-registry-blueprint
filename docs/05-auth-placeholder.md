# Auth & permissions — index

This was the original placeholder for the entire auth story. Most of
its content has been promoted to dedicated docs:

| What you want to know | Where to read it |
|---|---|
| How four IAM personas (Reader / Publisher / Curator / Admin) get scoped policies for `bedrock-agentcore:*` and `codeartifact:*` | [docs/09-publishing-iam.md](./09-publishing-iam.md) |
| How non-IAM end users (analysts, support agents, most developers) consume skills via Cognito User Pool + Identity Pool, with no AWS credentials on their machines | [docs/10-end-user-access.md](./10-end-user-access.md) |
| The CDK that creates the Cognito identity layer | [`cdk/lib/identity-stack.ts`](../cdk/lib/identity-stack.ts) |
| The end-user client that bridges JWT to the AWS SDK `credential_process` | [`skills/skill-cli/`](../skills/skill-cli/) |

> **One thing to flag explicitly**: the four-tier IAM policies in
> `docs/09` are **documented JSON, not provisioned IAM resources**.
> `cdk deploy --all` does NOT create `Skills-Reader`, `Skills-Publisher`,
> etc. groups for you. You attach those policies to your own IAM Groups,
> Identity Center permission sets, or roles per your org's identity
> conventions. The CDK provisions only what's blueprint-specific
> (CodeArtifact, Registry, optional Cognito User/Identity Pools).

## What this doc still covers

The remaining items below are auth-related hardening that's neither
already shipped (in `docs/09` / `docs/10`) nor obviously belonging to a
different doc.

### Direct-JWT path on the Registry MCP endpoint

`docs/10` ships the **indirect** JWT path: Cognito User Pool → Identity
Pool → temporary IAM → Registry SigV4. This is the right shape when
you also need IAM credentials for CodeArtifact.

The Registry also supports a **direct** JWT inbound auth via
`customJWTAuthorizer`, where the Registry MCP endpoint validates JWTs
signed by any OIDC provider (not just Cognito) — Okta, Entra ID,
Auth0, IAM Identity Center, etc. This is appropriate when:

- Users only need to *search* the Registry, not pull artifacts
- You don't want any AWS service in the JWT validation path
- Your org's IdP is not Cognito and SAML-federating it through
  Cognito is unwanted overhead

> **Status correction (2026-08-04).** Earlier revisions of this doc and the
> README status table listed the direct-JWT path as "🔶 Phase 2 — non-Cognito
> IdPs still pending." That was ambiguous in a way that undersold the
> service: it read as if AWS hadn't shipped the capability. AWS had, and
> now documents it plainly — the registry integrates with Cognito, Okta,
> Microsoft Entra ID, or **any OAuth 2.0-compatible provider**, so
> developers and agents can search the registry and invoke the MCP
> endpoint with existing corporate credentials **without individual IAM
> access**.
>
> What is pending is only *our* CDK construct. The gap is blueprint
> ergonomics, not a missing AWS feature. Anyone who needs the direct-JWT
> path today can have it with one `update-registry` call — they just don't
> get it from `cdk deploy` in this repo.

One boundary worth keeping straight when choosing between the two paths:
the JWT authorizer setting governs **search / MCP data-plane access
only**. Control-plane operations — creating and updating registries and
records, mutating record status — **always use IAM**, regardless of the
registry's search authorization setting. So direct JWT covers Readers
cleanly, while Publishers, Curators, and Admins from `docs/09` still need
IAM identities. Direct JWT replaces the Cognito→Identity Pool bridge for
search-only consumers; it does not eliminate IAM from the publishing side.

The other reason a search-only reader may still want the indirect path:
direct JWT gets them into the Registry, but **not into CodeArtifact**.
Pulling the wheel is a `codeartifact:*` call needing SigV4. Direct JWT
therefore fits the "embed `SKILL.md` into context from search results"
consumption mode, while persistent `pip install` still wants the temporary
IAM credentials from `docs/10`.

```bash
# Sketch — productionize before using.
# Note the optionalValue wrapper, and that there is no --authorizer-type flag.
aws bedrock-agentcore-control update-registry \
  --registry-id <id> \
  --authorizer-configuration '{
    "optionalValue": {
      "customJWTAuthorizer": {
        "discoveryUrl": "https://your-idp/.well-known/openid-configuration",
        "allowedClients": ["<client-id>"],
        "allowedScopes": ["registry/search"],
        "allowedAudience": ["<audience>"]
      }
    }
  }'
```

Also note: the AWS console's registry search works for **IAM-authorized
registries only**. Flip a registry to JWT authorization and curators lose
console search — they need an HTTP client with a bearer token or an MCP
client instead. Worth knowing before switching a registry your curators
use daily.

This is **not currently in the CDK** — `registry-stack.ts` uses the
default IAM auth.

**TODO (blueprint-side, not AWS-side)**: a CDK construct
`RegistryWithJwtAuth` taking discovery URL + allowed clients + scopes and
wiring them into the `update-registry` call. Since no CloudFormation
resource covers the authorizer configuration, expect this to be a custom
resource wrapping the SDK call.

### CodeArtifact KMS customer-managed key (CMK)

For compliance regimes that require CMK rather than AWS-managed keys.

```typescript
// Phase 2 sketch in cdk/lib/codeartifact-stack.ts
const cmk = new kms.Key(this, 'CodeArtifactCmk', {
  description: 'Customer-managed key for skills CodeArtifact domain',
  enableKeyRotation: true,
  alias: 'alias/skills-codeartifact',
});
new codeartifact.CfnDomain(this, 'Domain', {
  domainName: 'skills-demo',
  encryptionKey: cmk.keyArn,
});
```

**Phase 2 TODO**: add `--cmk` context flag wiring the CMK into
domain creation, plus rotation + access policies.

### Cross-account skill consumption

Today's blueprint assumes one AWS account. Real orgs typically have:

- A **central** account that owns the Registry + CodeArtifact
- **Workload** accounts where skills are consumed

CodeArtifact supports cross-account via repo resource policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "AWS": ["arn:aws:iam::<workload-account>:root"] },
      "Action": [
        "codeartifact:DescribePackage",
        "codeartifact:DescribePackageVersion",
        "codeartifact:GetPackageVersionAsset",
        "codeartifact:GetPackageVersionReadme",
        "codeartifact:ListPackageVersionAssets",
        "codeartifact:ListPackageVersions",
        "codeartifact:ReadFromRepository"
      ],
      "Resource": "*"
    }
  ]
}
```

The Registry side: the workload account principal needs
`bedrock-agentcore:SearchRegistryRecords` against the central
account's registry ARN. The control-plane stays in the central account.

**Phase 2 TODO**: a CDK construct `MultiAccountRegistry` taking a list
of consumer account IDs and emitting both resource policies.

### Approval gate hardening

Beyond the docs/09 baseline (`UpdateRegistryRecordStatus` permission +
MFA condition):

- Wire EventBridge on `Skill record submitted for approval` →
  Lambda → Slack interactive message → on approve, the Lambda calls
  `UpdateRegistryRecordStatus` with a service role
- Audit via CloudTrail Lake — query
  `eventName = 'UpdateRegistryRecordStatus' AND status = 'APPROVED'`

> **Status update (2026-08-04): the event source shipped.** The Registry
> now publishes to the **default EventBridge bus** in your account and
> Region when a record is submitted for approval, routable to Lambda, SNS,
> SQS, or Step Functions. AWS positions this as the seam for plugging the
> registry into an organization's existing review process rather than
> adopting a new one.
>
> So the remaining work is a *consumer*, not a pipeline. And if your org
> already runs security review / compliance checks / a ticketing flow,
> the recommendation inverts: point the EventBridge rule at what you have
> and let it call `UpdateRegistryRecordStatus`. The Slack bot below is the
> demo-friendly option, not the default one.

**TODO (blueprint-side)**: CDK rule + Lambda + Slack message template, as
a reference consumer of the managed event.

### Skill content scanning before approval

Optional but recommended. Pipeline:

```
PendingApproval → EventBridge → Lambda
                                 ├─ pip download from CodeArtifact
                                 ├─ unpack wheel
                                 ├─ POST SKILL.md to scanner sidecar
                                 └─ if clean: tag record with scan-passed metadata
                                    if dirty: tag + auto-reject with reason
```

Community standard scanner: `cisco-ai-skill-scanner` (the same one
iflytek/skillhub uses).

**Phase 2 TODO**: CDK module + Fargate task definition for the
scanner sidecar.

### VPC PrivateLink

When PrivateLink endpoints for AgentCore Registry GA, you'd want
skills to never traverse public internet inside a VPC-only customer.

**Phase 2 TODO**: VPC endpoint configuration in CDK once GA.

## Read-only audit policy reference

For security teams to inspect the registry without write:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "bedrock-agentcore:ListRegistries",
      "bedrock-agentcore:GetRegistry",
      "bedrock-agentcore:ListRegistryRecords",
      "bedrock-agentcore:GetRegistryRecord",
      "bedrock-agentcore:SearchRegistryRecords",
      "codeartifact:Describe*",
      "codeartifact:List*",
      "codeartifact:Read*"
    ],
    "Resource": "*"
  }]
}
```

→ Next: [extending to other resources](./07-extending-to-other-resources.md)
