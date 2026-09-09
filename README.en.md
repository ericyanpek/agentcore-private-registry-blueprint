# agentcore-private-registry-blueprint

[中文](README.md)

Private skill distribution and verified consumption using **AWS Agent Registry GA + CodeArtifact**.
Registry owns catalog discovery and approval; CodeArtifact stores wheels; this blueprint binds approved
metadata to the bytes activated on a consumer's machine.

**Status — 2026-09-09:** native CloudFormation deployment and the GA publisher → curator → consumer
flow passed live checks in `us-east-1`, using separate, scoped IAM roles. Cross-team access denial,
artifact substitution rejection and deprecation were also checked. The three high-severity npm
findings are fixed; `npm audit` reports zero. Cognito login was not live-tested in this run.
See [validation coverage](docs/13-live-validation.md).

## Flow

1. Build one wheel; derive the record's `SKILL.md` and SHA-256 from that wheel.
2. Upload to CodeArtifact and verify the server-reported asset hash.
3. Publish a `SKILL` record, submit it, and have a separate curator approve it.
4. Consumers search an explicit registry for an exact name/version and fetch approved details through the discovery plane.
5. Download from the explicitly trusted repository; verify bytes and embedded `SKILL.md`.
6. Recheck the approved discovery record, extract only `skill_files/`, and write provenance.

Consumers do not enumerate registries, read governance records, execute package installation hooks,
install Python dependencies, or write CodeArtifact tokens into pip configuration.

## Quick start

Requires Python 3.11+, Node.js 20+, a current AWS CLI v2 with the GA Registry commands, and
separate preconfigured publisher, curator and consumer AWS profiles.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[publish]'
cd cdk
npm ci
npx cdk synth
npx cdk diff
npx cdk deploy --all
cd ..
export AGENT_REGISTRY_ARN='arn:aws:agent-registry:us-east-1:YOUR_ACCOUNT_ID:registry/YOUR_REGISTRY_ID'
AWS_PROFILE=publisher python skills/publish-skill/scripts/publish.py --package-dir skill-package --auto-submit
AWS_PROFILE=curator python scripts/03_approve_skill.py --reason 'Reviewed content and digest'
AWS_PROFILE=consumer python scripts/04_consume_skill.py --target-dir ./demo-skills
python scripts/05_verify_installed_skill.py ./demo-skills/aws-cost-anomaly-triage
```

Deploying creates billable resources. Use `AgentRegistryStack.RegistryArn` as the ARN above.
Discovery indexing is eventually consistent; retry a search miss rather than bypassing approval.
The scripts do not create AWS profiles or grant their permissions.

See [the complete walkthrough](docs/03-demo-walkthrough.md), [IAM separation](docs/09-publishing-iam.md),
[team isolation](docs/10-end-user-access.md), [MCP setup](docs/04-dynamic-discovery.md),
[integrity model](docs/12-record-artifact-integrity.md) and [CDK lifecycle](cdk/README.md).

## Boundaries

- Supports a single platform-independent, dependency-free wheel with at most 20 MiB compressed/expanded content.
- Matching hashes prove consistency with approval, not that the skill is harmless.
- Provenance manifests are not signatures; an attacker modifying both files and the manifest can defeat local checks.
- Deprecating a registry record does not revoke local copies. Approval rechecks and activation are not an atomic transaction.
- Repository download permission is separate from approval. A caller can bypass this client and fetch an unapproved artifact
  directly; server-side approval-gated artifact access would require a separate quarantine/promotion workflow.
- Use separate registries and IAM boundaries for sensitive teams. Search filters are not authorization.
- OAuth discovery, EventBridge approval workflows, RAM sharing and organization auto-detection remain extension work.

The native CloudFormation registry is retained on deletion. The GA stack is deliberately named
`AgentRegistryStack`, separate from the old Preview stack. Existing data needs an explicit migration.
The Preview namespace closes on 2026-09-17; see [migration](docs/11-ga-migration.md).

Research pages `docs/02`, `05`, `06`, `07` and `08` retain historical design context.
Their Preview snippets are not current deployment instructions.
