# CDK — one-click infra for the blueprint

Provisions:

1. **CodeArtifact** domain + PyPI repository (`skills-demo` / `skills-prod`)
2. **Bedrock AgentCore Registry** (`skills-demo-registry`, IAM auth, manual approval)

Both stacks deploy to `us-east-1` by default; override via context:

```bash
npx cdk deploy --all -c blueprintRegion=us-west-2 \
                     -c domainName=acme-skills \
                     -c repositoryName=acme-skills-prod \
                     -c registryName=acme-skills-registry
```

## Why a custom resource for the registry?

Agent Registry is in **public preview** (2026-04). It does not yet
have an `AWS::BedrockAgentCore::Registry` CloudFormation resource.
We use `AwsCustomResource` to call the SDK directly.

When the L1 resource ships, swap `lib/registry-stack.ts` for the
declarative form. The rest of the blueprint (skill package, scripts,
docs) is unchanged.

## First-time setup

```bash
npm install
npx cdk bootstrap                       # once per account/region
npx cdk deploy --all
```

Outputs include `RegistryArn`, `RegistryId`, and `McpEndpoint` —
copy these into your `mcp.json` or downstream scripts.

## Tear down

```bash
npx cdk destroy --all
```

If destroy fails because the registry has un-deleted records (CFN
won't cascade by default), delete records first:

```bash
python3 -c "
import boto3
c = boto3.client('bedrock-agentcore-control', region_name='us-east-1')
for r in c.list_registries()['registries']:
    rid = r['registryArn'].rsplit('/', 1)[-1]
    for rec in c.list_registry_records(registryId=rid).get('registryRecords', []):
        c.delete_registry_record(registryId=rid, recordId=rec['recordId'])
"
```

Then `cdk destroy --all` again.

## Status

| Stack | Status |
|---|---|
| `CodeArtifactStack` | ✅ Production-ready (declarative L1) |
| `AgentCoreRegistryStack` | 🔶 Uses AwsCustomResource (preview API). Replace with L1 when available. |

Phase 2 additions (auth modules, KMS CMK, multi-account) tracked in
`../docs/05-auth-placeholder.md` and `../docs/06-future-optimizations.md`.
