# GA live validation and npm security fixes

Date: **2026-09-09**. Region: **`us-east-1`**.

This run validates the core blueprint against real AWS services, not just SDK stubs.
It does not certify the entire repository or every optional integration.

## Deployment and identities

- Deployed isolated CodeArtifact and Agent Registry stacks with a unique `stackPrefix`,
  domain name and registry name. The Registry used native `AWS::AgentRegistry::Registry`,
  IAM discovery, manual approval and retention.
- Created a second registry and repository for negative team-boundary tests.
- Used three temporary IAM roles: publisher, curator and consumer, each trusted only to
  the test operator and scoped to the primary test resources. No administrator credentials
  were used for positive consumer operations.
- The consumer used the exact substituted [`consumer-policy.json`](../iam/consumer-policy.json):
  `SearchDiscoverableRegistryRecords`, `GetDiscoverableRegistryRecord` and
  `GetPackageVersionAsset`, with explicit registry/repository resources.
- STS credentials and Twine bearer tokens stayed in process memory/subprocess environments;
  no secrets were written to pip configuration, source files or the result record.

Use the [isolated deployment commands](../cdk/README.md#isolated-deployment) and
[walkthrough](03-demo-walkthrough.md) to reproduce the flow with your own identities.
The destructive artifact-substitution check must only target disposable test repositories.

## Live results

| Check | Observed result |
|---|---|
| Native CloudFormation deployment | Both core stacks reached `CREATE_COMPLETE` |
| Publisher uploads the sample wheel | Twine upload and CodeArtifact SHA-256 verification succeeded |
| Publisher creates/submits the record | `DRAFT` → `PENDING_APPROVAL` succeeded |
| Consumer before approval | Draft and pending releases did not activate; search returned no approved match |
| Publisher attempts approval | `AccessDeniedException` |
| Consumer calls governance Get/List | Both returned `AccessDeniedException` |
| Curator requests a publishing token | `AccessDeniedException`; no CodeArtifact publishing permission was granted |
| Curator approves | Record reached `APPROVED` |
| Approved discovery | Exact type/name/version filters and batch detail retrieval succeeded after indexing |
| Minimum-permission consumer | Real SDK download, digest/metadata checks and skill-only activation succeeded |
| Repeat consumption | Succeeded without replacing the unchanged local installation |
| Modified local `SKILL.md` | Reinstallation failed rather than overwriting the changed tree |
| Team A searches/gets Team B's record | Both Search and BatchGet returned `AccessDeniedException` |
| Team A downloads Team B's existing wheel | `AccessDeniedException` |
| Same-version remote wheel substitution | Replaced the wheel in the disposable repository; consumer rejected the digest before activation |
| Deprecated record | Consumer refused new activation after the discovery state updated |

The first post-approval search needed approximately 13 seconds of polling in this run.
This is an observation, not an indexing latency guarantee. Cross-registry BatchGet denial
was a top-level `AccessDeniedException`, not a successful response containing per-record errors.

## npm findings: fix, not suppress

The original lockfile resolved `aws-cdk-lib` **2.257.0** and produced **three high-severity
findings**, attributed to `aws-cdk-lib` and its bundled/transitive `brace-expansion` and
`fast-uri` dependencies.

The direct CDK advisory concerns OS command injection in `NodejsFunction` Docker bundling
([GHSA-vcrf-j523-4mrf](https://github.com/advisories/GHSA-vcrf-j523-4mrf)).
This blueprint does not use `NodejsFunction`, so that specific path was not exercised here.
These findings affect the IaC toolchain, not the Python consumer's dependency tree;
limited current exposure is not a reason to retain vulnerable dependencies when a compatible fix exists.

Changes:

- Raised `aws-cdk-lib` to **2.268.0** and the CDK CLI to **2.1140.0**, updating the lockfile together.
- The resolved tree contains `brace-expansion` **5.0.9** and no `fast-uri` package.
- Clean `npm ci --ignore-scripts` followed by `npm audit --json` reported **0 vulnerabilities**
  across all severities. No advisory suppression, forced audit fix or hand-edited transitive override was used.
- Adopted the newly available typed `aws-agentregistry.CfnRegistry` L1. Against the live stack,
  this preserved Registry properties, logical ID, ARN and retention; only CDK metadata changed on deployment.
- The upgraded CloudFormation validator also caught an existing em dash in the optional
  IdentityStack IAM role description, outside IAM's allowed character range. Replaced it
  with a constant ASCII description and validated synthesis with default-rule errors enabled.
  This correction has synthesis coverage, not live Cognito login coverage.

Recheck over time; the zero finding count reflects the advisory database on the test date:

```bash
cd cdk
npm ci --ignore-scripts
npm audit
npx tsc --noEmit
npx cdk synth
```

## Additional validation

The local validation harness passed **17 offline scenarios**, including SDK request shapes,
full Stubber-backed consumption, changed/unapproved records, untrusted sources, digest and
metadata mismatches, unsafe archive paths, symlinks, idempotence and local drift.
The harness was external to the repository; these are executed checks, not a newly shipped CI suite.
Python dependency consistency and compilation also passed.

CDK compilation and synthesis covered default and two-team identity configurations.
These checks do **not** constitute a live Cognito authentication test.

## Cleanup and boundaries

The test registries and their records were explicitly deleted because CloudFormation retention
does not remove them. Temporary role policies/roles and the extra team repository were removed,
then both test stacks were destroyed. Resource-read APIs were used to confirm cleanup.
The pre-existing shared CDK bootstrap stack, its deployment artifacts and AWS audit history were
preserved; no existing application stack or Preview data was migrated or deleted.

Not live-tested here: Cognito login/Identity Pool credential exchange, MCP client sessions,
OAuth, cross-account sharing, Preview data migration, organization discovery, extension-resource
examples, scale/concurrency and failure recovery.

Approval is still a content-review decision. These tests do not prove a skill is harmless,
make approval/activation atomic, revoke existing local copies or prevent callers with repository
read permission from bypassing the consumer and directly downloading an unapproved wheel.
