# Demo walkthrough — publish, approve, discover, install

> Verified end-to-end in a sandbox account, us-east-1, on 2026-05-25.
> Expected wall-clock time: 5-10 minutes.

This page is the operations manual. Run from the repo root unless noted.

## 0. Prerequisites

| Tool | Version | Why |
|---|---|---|
| `boto3` | ≥ 1.42.88 | Earlier versions have the client but not the Registry operations |
| `awscli` | ≥ 2.30 | For `codeartifact login --tool pip/twine` |
| `python` | ≥ 3.9 | The example skill targets 3.9+ |
| `twine`, `build` | latest | Standard PyPI tooling |
| AWS region | `us-east-1` | Agent Registry preview regions: us-west-2, us-east-1, eu-west-1, ap-northeast-1, ap-southeast-2 |

IAM permissions (attach to the publishing principal):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {"Effect": "Allow", "Action": ["codeartifact:*", "sts:GetServiceBearerToken"], "Resource": "*"},
    {"Effect": "Allow", "Action": "bedrock-agentcore:*", "Resource": "*"}
  ]
}
```

This is broad for demo. See [docs/05-auth-placeholder.md](./05-auth-placeholder.md)
for least-privilege scoping by persona (admin / publisher / consumer / curator).

## 1. Provision infrastructure (one-click CDK)

```bash
cd cdk
npm install
npx cdk bootstrap          # only once per account/region
npx cdk deploy --all
```

What this creates:

- CodeArtifact **domain** `skills-demo` (KMS aws-managed)
- CodeArtifact **repo** `skills-prod` (PyPI format)
- Bedrock AgentCore **Registry** `skills-demo-registry` (IAM auth, manual approval)

Wall time: ~2-3 minutes (the registry takes ~30s to leave `CREATING`).

CDK outputs the registry ARN; export it for downstream scripts:

```bash
export REGISTRY_ARN=$(aws cloudformation describe-stacks \
  --stack-name AgentCoreRegistryStack --region us-east-1 \
  --query 'Stacks[0].Outputs[?OutputKey==`RegistryArn`].OutputValue' \
  --output text)
```

## 2. Build and publish the example skill

```bash
cd skill-package
python3 -m build
```

Output:
- `dist/aws_cost_anomaly_triage-0.1.0.tar.gz` (sdist)
- `dist/aws_cost_anomaly_triage-0.1.0-py3-none-any.whl` (wheel, ~14.6KB)

The wheel bundles `SKILL.md` + 6 resource markdown files via
`[tool.setuptools.package-data]` in `pyproject.toml`.

Login + upload:

```bash
aws codeartifact login --tool twine \
  --domain skills-demo --repository skills-prod --region us-east-1

python3 -m twine upload --repository codeartifact dist/*
```

Verify:

```bash
aws codeartifact list-package-versions \
  --domain skills-demo --repository skills-prod \
  --format pypi --package aws-cost-anomaly-triage --region us-east-1
```

You should see version `0.1.0`, status `Published`, origin `INTERNAL`.

## 3. Register the skill in Agent Registry

```bash
cd ../scripts
python3 02_register_skill.py
```

What happens:
1. Loads `SKILL.md` raw text (frontmatter included — required by registry validation)
2. Builds `skillDefinition` JSON pointing at the CodeArtifact PyPI package
3. `CreateRegistryRecord` → record state `CREATING`
4. Polls until state = `DRAFT` (~1 second)

Output ends with the record ARN. Note the recordId from the ARN tail.

## 4. Submit + approve

```bash
python3 03_approve_skill.py
```

Transitions: `DRAFT` → `PENDING_APPROVAL` → `APPROVED`.

In a real org, the publisher submits and a separate IAM principal
(curator) approves. The script does both for demo. Use IAM Conditions
on `bedrock-agentcore:UpdateRegistryRecordStatus` to enforce the
separation of duty.

## 5. Wait for the search index

After APPROVED, the semantic index takes **15–30 seconds** to pick up
the record. This is timing data the AWS docs don't mention but it
matters for UX in any consumer flow. Poll with:

```bash
python3 -c "
import boto3, time
ctrl = boto3.client('bedrock-agentcore-control', region_name='us-east-1')
data = boto3.client('bedrock-agentcore', region_name='us-east-1')
arns = [r['registryArn'] for r in ctrl.list_registries()['registries']]
for _ in range(10):
    hits = data.search_registry_records(registryIds=arns, searchQuery='cost anomaly').get('registryRecords', [])
    print(len(hits), 'hits')
    if hits: break
    time.sleep(10)
"
```

## 6. Run the consumer

```bash
python3 04_consume_skill.py
```

This script demonstrates the full end-to-end consumer path:

1. `search_registry_records(query="cost anomaly triage")` — finds 1 hit
2. `get_registry_record` — pulls the full skillDefinition
3. Parses `packages[0]` to learn the PyPI package + version
4. Reads `_meta.com.example.codeartifact.indexUrl`
5. `aws codeartifact login --tool pip` — refreshes the 12h pip token
6. Creates a fresh venv, `pip install aws-cost-anomaly-triage==0.1.0`
7. Runs the `install-aws-cost-anomaly-triage` console script
8. Final tree: `~/.claude/skills/aws-cost-anomaly-triage/SKILL.md` + `resources/*`

After this completes, **Claude Code's plugin loader picks up the new
directory automatically.** Open Claude Code (or send a fresh prompt
in an existing session) and the skill appears in the Skill list with
the description from frontmatter.

## Verification — the proof point

The most concrete evidence the demo works: the system reminder Claude
Code emits on every prompt includes available skills. After running
step 6, that list includes `aws-cost-anomaly-triage` alongside built-in
skills, exactly the same listing format. **The agent doesn't know
the skill came from a private AWS-hosted registry — it just sees a
local skill with a triggering description.**

## Timing summary (real numbers from a fresh run)

| Step | Time |
|---|---|
| `cdk deploy --all` | ~2-3 min |
| `python3 -m build` | < 5 s |
| `twine upload` | < 5 s (14.6KB wheel) |
| `create_registry_record` → DRAFT | < 2 s |
| Submit → PENDING_APPROVAL | < 2 s |
| Approve → APPROVED | < 2 s |
| **APPROVED → search-discoverable** | **15–30 s** |
| `pip install` from CodeArtifact | < 3 s |
| Postinstall copy | < 1 s |
| **Total fresh-deploy wall time** | **~5 min** |

## Cleanup

```bash
# remove the local skill (optional)
rm -rf ~/.claude/skills/aws-cost-anomaly-triage

# tear down the AWS infra
cd cdk
npx cdk destroy --all
```

`cdk destroy` will fail if the registry has un-deleted records or
the CodeArtifact repo has un-deleted packages — the CDK stacks
include cleanup helpers, but you can also do it manually:

```bash
# delete record + registry first
python3 -c "
import boto3
c = boto3.client('bedrock-agentcore-control', region_name='us-east-1')
for r in c.list_registries()['registries']:
    if r['name'] == 'skills-demo-registry':
        rid = r['registryArn'].rsplit('/', 1)[-1]
        for rec in c.list_registry_records(registryId=rid).get('registryRecords', []):
            c.delete_registry_record(registryId=rid, recordId=rec['recordId'])
        c.delete_registry(registryId=rid)
"

# then CodeArtifact
aws codeartifact delete-repository --domain skills-demo --repository skills-prod --region us-east-1
aws codeartifact delete-domain --domain skills-demo --region us-east-1
```

## Common errors

| Error | Cause | Fix |
|---|---|---|
| `ConflictException: Registry is not in READY state: CREATING` | Calling `ListRegistryRecords` too soon after `CreateRegistry` | Wait until the registry's status is `READY` (~30s) |
| `Unknown parameter "approvalConfig"` | API parameter is `approvalConfiguration.autoApproval`, not `approvalConfig.approvalType` | Use the correct schema; introspect with `client.meta.service_model.operation_model('CreateRegistry').input_shape.members` |
| `KeyError: 'registryRecordArn'` | Wrong key name | The output is `recordArn`, not `registryRecordArn` |
| Empty search hits right after APPROVED | Index not refreshed | Wait 15-30s, poll |
| `botocore.exceptions.NoCredentialsError` | EC2 role missing | See `docs/05-auth-placeholder.md` |

→ Next: [dynamic discovery via the MCP endpoint](./04-dynamic-discovery.md)
