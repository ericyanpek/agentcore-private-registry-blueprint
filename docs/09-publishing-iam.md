# Publishing IAM — four-tier policy reference

> Audience: a platform / security engineer who decides who can
> publish, approve, and consume skills. This doc gives you the IAM
> policies to attach to four IAM Groups (or IAM Identity Center
> permission sets) that map to the four real personas in skill
> governance.

The lever you pull to control "who publishes" is **IAM**, not
something inside the Registry. The Registry trusts whoever
`bedrock-agentcore:CreateRegistryRecord` says it trusts. Get IAM
right and everything else follows.

## The four personas

| Persona | What they do | What they need IAM-wise |
|---|---|---|
| **Reader** (everyone in the org) | Search the registry, install approved skills | search + read on registry; pull on CodeArtifact |
| **Publisher** | Author and publish new skill versions | Reader + create-record + submit-for-approval + push on CodeArtifact |
| **Curator** | Approve / reject / deprecate records; respond to incidents | Reader + update-record-status |
| **Admin** | Create/delete the registry itself, manage IAM | Full bedrock-agentcore + codeartifact admin |

Most engineers are Readers. Some teams have a few Publishers. Curators
are typically a small named list — security, FinOps lead, platform
TPM, etc.

**A single person is usually in multiple groups** (e.g., a FinOps lead
is both a Publisher of finops skills and a Curator of finops skills).
That's fine; the policies are additive.

## Policy 1 — Reader (broad)

For every engineer in the org. Probably attached to a baseline
"Developer" managed permission set in IAM Identity Center.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "RegistryReadOnly",
      "Effect": "Allow",
      "Action": [
        "bedrock-agentcore:ListRegistries",
        "bedrock-agentcore:GetRegistry",
        "bedrock-agentcore:ListRegistryRecords",
        "bedrock-agentcore:GetRegistryRecord",
        "bedrock-agentcore:SearchRegistryRecords",
        "bedrock-agentcore:InvokeRegistryMcp"
      ],
      "Resource": "arn:aws:bedrock-agentcore:*:*:registry/*"
    },
    {
      "Sid": "CodeArtifactPullOnly",
      "Effect": "Allow",
      "Action": [
        "codeartifact:GetAuthorizationToken",
        "codeartifact:GetRepositoryEndpoint",
        "codeartifact:ReadFromRepository",
        "codeartifact:GetPackageVersionAsset",
        "codeartifact:GetPackageVersionReadme",
        "codeartifact:DescribePackage",
        "codeartifact:DescribePackageVersion",
        "codeartifact:ListPackageVersionAssets",
        "codeartifact:ListPackageVersions",
        "codeartifact:ListRepositories",
        "codeartifact:ListPackages"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CodeArtifactBearerToken",
      "Effect": "Allow",
      "Action": "sts:GetServiceBearerToken",
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "sts:AWSServiceName": "codeartifact.amazonaws.com"
        }
      }
    }
  ]
}
```

This is the full set needed to run `04_consume_skill.py` (which is
what consumers do). No write capability anywhere.

## Policy 2 — Publisher (scoped to a registry / repo)

Attach to authors of a specific team. Scope `Resource` to the registry
ARN they own — that's how you say "FinOps engineers can publish to
the FinOps registry only".

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "RegistryRecordCreateAndSubmit",
      "Effect": "Allow",
      "Action": [
        "bedrock-agentcore:CreateRegistryRecord",
        "bedrock-agentcore:UpdateRegistryRecord",
        "bedrock-agentcore:DeleteRegistryRecord",
        "bedrock-agentcore:SubmitRegistryRecordForApproval"
      ],
      "Resource": "arn:aws:bedrock-agentcore:us-east-1:111122223333:registry/<registryId>/*"
    },
    {
      "Sid": "CodeArtifactPublishToOwnRepo",
      "Effect": "Allow",
      "Action": [
        "codeartifact:PublishPackageVersion",
        "codeartifact:PutPackageMetadata"
      ],
      "Resource": "arn:aws:codeartifact:us-east-1:111122223333:package/<domain>/<repo>/pypi/*/*"
    }
  ]
}
```

**Two important things this policy does NOT grant:**

- `bedrock-agentcore:UpdateRegistryRecordStatus` — Publishers cannot
  approve their own records. That's the curator's job, by IAM
  separation of duty.
- Any cross-team registry — scoping `Resource` to a single registry
  ARN means a FinOps Publisher cannot publish to the Customer Care
  registry. Repeat the policy with a different ARN for cross-team
  publishers.

This is usually attached to an IAM Group like `Skills-Publishers-FinOps`,
populated via SSO group membership.

## Policy 3 — Curator (separation-of-duty)

Attach to the small list of people who can approve / reject /
deprecate records. Typically scoped to a specific registry.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "RegistryRecordApprovalActions",
      "Effect": "Allow",
      "Action": [
        "bedrock-agentcore:UpdateRegistryRecordStatus",
        "bedrock-agentcore:GetRegistryRecord",
        "bedrock-agentcore:ListRegistryRecords"
      ],
      "Resource": "arn:aws:bedrock-agentcore:us-east-1:111122223333:registry/<registryId>/*"
    }
  ],
  "Condition": {
    "Bool": {
      "aws:MultiFactorAuthPresent": "true"
    }
  }
}
```

**Two recommended hardenings on top of the basic grant:**

1. **MFA condition** — `aws:MultiFactorAuthPresent: true` so an
   approval action requires the curator to have signed in with MFA.
   Approving a skill is a privileged action; treat it like a prod
   deployment.
2. **CloudTrail alerting** — Wire a CloudTrail event rule that
   alerts on every `UpdateRegistryRecordStatus` call. You want
   visibility into who approved what, when, with what reason.

## Policy 4 — Admin (small, audited, infrequent)

For the platform engineer who created the registry and might need
to delete it. **Should not be attached to any human's daily-driver
role** — assume-role only.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "RegistryFullControl",
      "Effect": "Allow",
      "Action": "bedrock-agentcore:*Registry*",
      "Resource": "*"
    },
    {
      "Sid": "CodeArtifactFullControl",
      "Effect": "Allow",
      "Action": "codeartifact:*",
      "Resource": "*"
    }
  ]
}
```

## Putting it together — IAM Identity Center recipe

If you're using IAM Identity Center (recommended), four permission
sets:

| Permission set | Inline policy | Default users |
|---|---|---|
| `Skills-Reader` | Policy 1 | All engineers (by AD/Okta group sync) |
| `Skills-Publisher-<team>` | Policy 1 + Policy 2 (scoped to team registry) | Team's authors |
| `Skills-Curator-<team>` | Policy 1 + Policy 3 (scoped to team registry) | 1-3 named people |
| `Skills-Admin` | Policy 4 | 1-2 platform engineers, assume-role only |

Provision with CDK / CloudFormation from the central account so
the layout is auditable.

## Three IAM patterns that come up

### Pattern: Publishers must run from CI, not laptop

Restrict the Publisher group to only allow the action when the
caller is the GitHub Actions OIDC role:

```json
{
  "Sid": "PublisherOnlyFromCi",
  "Effect": "Deny",
  "Action": [
    "bedrock-agentcore:CreateRegistryRecord",
    "codeartifact:PublishPackageVersion"
  ],
  "Resource": "*",
  "Condition": {
    "StringNotLike": {
      "aws:PrincipalArn": "arn:aws:iam::*:role/GitHubActions-Publisher-*"
    }
  }
}
```

This eliminates "I published from my laptop and the version isn't
reproducible" failures.

### Pattern: Publishers cannot publish to global namespace

If you have a `global-shared-registry`, scope the team Publisher
policies to their team registry only — a separate Curator-level
review is required to "promote" a skill from a team registry to
global. Implement promotion as a CI job that runs under a
purpose-built IAM role, not as a Publisher action.

### Pattern: Self-approve audit detection

Even with separation of duty, an admin in both the Publisher and
Curator groups can self-approve. Detect this with CloudTrail:

```sql
-- CloudTrail Lake query
SELECT eventTime, userIdentity.arn, recordId
FROM cloudtrail
WHERE eventName = 'UpdateRegistryRecordStatus'
  AND status = 'APPROVED'
  AND userIdentity.arn IN (
    SELECT userIdentity.arn FROM cloudtrail
    WHERE eventName = 'CreateRegistryRecord'
      AND recordId = <same record>
      AND eventTime > <recent window>
  )
```

Alert on hits. This is a compensating control, not a hard block —
some teams legitimately have a single trusted person doing both.

## When to ignore this whole doc

If you're a single-team PoC and security oversight isn't a
near-term concern: just attach Policy 4 to your developer role,
ship the demo, and revisit when you're ready to onboard the second
team. **The blueprint's Day-1 demo deliberately uses broad
`bedrock-agentcore:*` and `codeartifact:*`** because security
hardening is Phase-2 work. This doc is what Phase 2 looks like
when it gets here.

## See also

- [docs/05-auth-placeholder.md](./05-auth-placeholder.md) — the
  per-persona policies (this doc) plus JWT/OIDC inbound auth
  (Phase 2)
- [docs/08-publishing-workflow.md](./08-publishing-workflow.md) —
  what authors do, assuming the IAM groups in this doc are set up
- [skills/publish-skill/](../skills/publish-skill/) — the meta-skill
  that publishes other skills
