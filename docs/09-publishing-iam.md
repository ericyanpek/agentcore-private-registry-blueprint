# IAM: keep publication, approval and consumption separate

Use separate federated IAM roles/profiles. Profile names alone are not a security boundary.
This page describes the GA namespace; AgentCore Runtime/Gateway/Identity actions retain their
own `bedrock-agentcore` prefix.

## Consumer

[`iam/consumer-policy.json`](../iam/consumer-policy.json) is the SDK consumer baseline, generated
from `registry_blueprint/consumer.py` using IAM Policy Autopilot and narrowed to explicit resource
placeholders. Substitute `REGION`, `ACCOUNT_ID`, `REGISTRY_ID`, `DOMAIN`, and `REPOSITORY`
before attaching it to a role. Use the respective owner account for cross-account resources.

| Permission | Resource scope |
|---|---|
| `agent-registry:SearchDiscoverableRegistryRecords` | One registry ARN |
| `agent-registry:GetDiscoverableRegistryRecord` | Records under that registry (`/record/*`) |
| `codeartifact:GetPackageVersionAsset` | PyPI packages in one repository |

`BatchGetDiscoverableRegistryRecord` is authorized using `GetDiscoverableRegistryRecord`;
there is no separate batch IAM action. No `ListRegistries`, `ListRegistryRecords`,
`GetRegistryRecord`, publish or approval permissions belong in this role.

For browsing/MCP, additionally grant `agent-registry:ListDiscoverableRegistryRecords` and
`agent-registry:InvokeRegistryMcp` on the same registry ARN. IdentityStack includes these.
The SDK download path requires no CodeArtifact bearer token, STS token exchange for CodeArtifact,
or `ReadFromRepository`; those are needed for a separate pip/Twine path, not this consumer.

The IAM baseline can be regenerated locally (no policy upload):

```bash
DISABLE_IAM_POLICY_AUTOPILOT_TELEMETRY=true uvx iam-policy-autopilot@latest generate-policies \
  "$PWD/registry_blueprint/consumer.py" \
  --region us-east-1 --service-hints agent-registry codeartifact --pretty
```

Do not apply wildcard output blindly. Bind account, registry and repository to deployment outputs.
Also review existing role policies, permission boundaries, SCPs and resource policies.

## Publisher

The publisher needs the following operations, not approval:

- Registry: `CreateRegistryRecord`, `GetRegistryRecord`, `ListRegistryRecords`,
  `SubmitRegistryRecordForApproval` under the selected registry.
- CodeArtifact: `GetAuthorizationToken` on the domain; `GetRepositoryEndpoint` and
  `ReadFromRepository` on the repository; `PublishPackageVersion` and
  `ListPackageVersionAssets` on its PyPI package ARNs.
- STS: `GetServiceBearerToken`, conditioned on `sts:AWSServiceName = codeartifact.amazonaws.com`,
  for Twine authentication; `GetCallerIdentity` if resolving the artifact domain owner.
- Optional `agent-registry:ListRegistries` on `*` only if resolving a registry **name**.
  Pass `--registry-id`/`AGENT_REGISTRY_ARN` to avoid this discovery requirement.

Use the `agent-registry:` prefix for the listed Registry actions.
Scope record actions to the resource types specified in the service authorization reference,
including the selected registry and its `/record/*` children as required.
Do not grant `UpdateRegistryRecordStatus`, metadata mutation of approved releases, or
`codeartifact:DeletePackageVersions` merely to make publication work.

Static analyzers may not resolve shared-client wrapper functions or Twine's HTTP requests;
publisher output from Autopilot alone is not a complete publishing policy.

## Curator

Use `agent-registry:ListRegistryRecords`, `GetRegistryRecord`, and
`UpdateRegistryRecordStatus` for the selected registry and its records.
Provide the registry ARN so no `ListRegistries` grant is needed.
The curator script will not submit drafts or publish wheels.

Approval is a human/content-review decision. Automated status changes do not establish that
the SOP or bundled scripts are safe. Give a curator narrowly scoped artifact-read access if
they need to inspect the wheel as part of that review.

## Verify the boundary

Run the positive and negative steps in [the walkthrough](03-demo-walkthrough.md):

1. A publisher can submit but cannot approve.
2. A curator can approve but cannot publish a wheel.
3. A consumer can fetch the approved record but cannot read drafts through governance APIs.
4. A team A consumer cannot discover team B's registry or download team B's repository assets.

CodeArtifact itself is not approval-aware. Anyone with download permission can bypass this client
and request an unapproved artifact directly. Server-enforced approval-gated download requires
a separate staging/release repository promotion design; it is outside this revision.

References: [Registry authorization](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/registry.html),
[BatchGet API](https://docs.aws.amazon.com/agent-registry/latest/APIReference/API_BatchGetDiscoverableRegistryRecord.html).
