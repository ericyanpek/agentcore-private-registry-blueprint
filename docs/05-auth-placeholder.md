# Auth & permissions — placeholder + cross-references

> **Status:** Hardening still in progress, but the major item — end-user
> JWT-based access via Cognito — is now spec'd and built. See:
>   - [docs/10-end-user-access.md](./10-end-user-access.md) for the
>     end-user (Reader) path with Cognito User Pool + Identity Pool
>   - [docs/09-publishing-iam.md](./09-publishing-iam.md) for the
>     Publisher / Curator / Admin IAM roles
>
> The current Day-1 demo still uses broad `bedrock-agentcore:*` and
> `codeartifact:*` so an SA can run it end-to-end without hand-crafting
> policies. Items below are remaining hardening for production.

## What's working today (Phase 1)

- IAM-based inbound auth on the registry (control + data plane)
- IAM-issued 12h bearer token for CodeArtifact via `aws codeartifact login`
- `mcp-proxy-for-aws` for SigV4-signed MCP requests from Claude Code
- Broad IAM grant on the EC2/dev role for end-to-end testing

This is fine for: a single team's PoC, an internal SA demo, an early
customer evaluation.

## What needs hardening (Phase 2 — TODO)

### 2.1 Per-persona least privilege

The four personas need different IAM policies; the demo collapses
them. The right shape:

| Persona | What they do | Allowed actions |
|---|---|---|
| **Admin** | Create/delete registries, manage namespaces | `CreateRegistry`, `DeleteRegistry`, `UpdateRegistry`, `*RegistryRecordStatus`, full CodeArtifact admin |
| **Publisher** | Publish skills | `CreateRegistryRecord`, `SubmitRegistryRecordForApproval`, `Get*` on own records, CodeArtifact `PublishPackageVersion` on the team's repo |
| **Curator** | Approve/reject submissions | `UpdateRegistryRecordStatus`, `Get*`, `List*` |
| **Consumer** | Search + install | `SearchRegistryRecords`, `InvokeRegistryMcp`, `Get*` on `APPROVED` records, CodeArtifact `Read*Package*` |

**TODO**: ship `cdk/lib/iam-personas.ts` with four IAM groups +
managed policies + role-trust patterns for IAM Identity Center.

### 2.2 JWT/OIDC inbound auth (Cognito flavor)

Currently the registry is created with default IAM auth. To switch
to Cognito JWT for the search/MCP plane:

```bash
# rough shape — to be productized in CDK
aws bedrock-agentcore-control update-registry \
  --registry-id <id> \
  --authorizer-configuration '{
    "customJWTAuthorizer": {
      "discoveryUrl": "https://cognito-idp.<region>.amazonaws.com/<userPoolId>/.well-known/openid-configuration",
      "allowedClients": ["<appClientId>"],
      "allowedScopes": ["registry/search"],
      "allowedAudience": ["<audience>"]
    }
  }'
```

**TODO**:
- CDK module that provisions Cognito user pool + app client + scopes
- Worked example: same flow with **Okta** (`discoveryUrl` + `allowedClients`
  swapped, no Cognito)
- Worked example: same flow with **AWS IAM Identity Center** as OIDC IdP

### 2.3 CodeArtifact resource policies for cross-account consumption

Today the demo assumes one AWS account. Real orgs have:

- A **central** account that owns the registry + CodeArtifact
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

The Agent Registry side: the workload account's principal needs
`bedrock-agentcore:SearchRegistryRecords` against the central
account's registry ARN. The control-plane stays in the central account.

**TODO**:
- CDK construct `MultiAccountRegistry` that takes a list of consumer
  account IDs and emits both resource policies
- Worked AWS Organizations OU example

### 2.4 KMS customer-managed key for CodeArtifact

The demo uses AWS-managed KMS. For compliance regimes (financial,
healthcare), a customer-managed key is usually required.

```typescript
// rough sketch for cdk/lib/codeartifact-stack.ts Phase 2
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

**TODO**: wire CMK into the CDK with rotation + access policies.

### 2.5 Approval gate hardening

Today: any principal with `bedrock-agentcore:UpdateRegistryRecordStatus`
can approve. For separation of duty:

- Use IAM **Conditions** to require MFA on the approve action
- Wire **EventBridge** rule on `Skill record submitted for approval` →
  Lambda → Slack interactive message → on approve, the Lambda calls
  `UpdateRegistryRecordStatus` with a service role
- Audit via **CloudTrail Lake** — query
  `eventName = 'UpdateRegistryRecordStatus' AND status = 'APPROVED'`

**TODO**: CDK + Lambda + Slack message template.

### 2.6 Skill content scanning before approval

Optional but useful. The community-standard scanner is
`cisco-ai-skill-scanner` (the same one iflytek/skillhub uses).
It runs as an HTTP service and consumes a SKILL.md path.

Pipeline:

```
PendingApproval → EventBridge → Lambda
                                 ├─ pip download from CodeArtifact
                                 ├─ unpack wheel
                                 ├─ POST SKILL.md to scanner sidecar
                                 └─ if clean: tag record with scan-passed metadata
                                    if dirty: tag + auto-reject with reason
```

**TODO**: CDK module + Fargate task definition for the scanner sidecar.

### 2.7 VPC PrivateLink

Both Bedrock AgentCore and CodeArtifact will support PrivateLink
endpoints. In a private-deployment scenario this is the difference
between "this skill never leaves the VPC" and "this skill traverses
the public internet on the way to itself."

**TODO**: VPC endpoint configuration in CDK once GA.

## Read-only audit policy reference

Useful for security teams to inspect the registry without write:

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

→ Next: [future optimizations](./06-future-optimizations.md)
