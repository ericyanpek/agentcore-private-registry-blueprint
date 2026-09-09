# CDK deployment

Requires Node.js 20+ and configured deployment credentials.

```bash
npm ci
npx tsc --noEmit
npx cdk synth --strict
npx cdk diff
npx cdk deploy --all
```

## Resources and outputs

- `CodeArtifactStack`: the existing private domain/repository, no public upstream.
- `AgentRegistryStack`: native `AWS::AgentRegistry::Registry`, IAM authorization, manual approval.
- Optional `IdentityStack`: temporary-credential access with explicit team registry/repository mappings.

`RegistryStack` uses the typed `aws-agentregistry.CfnRegistry` L1 from CDK 2.268.0
for the **native CloudFormation resource type**, not `AwsCustomResource`.
No Lambda/SDK custom resource is needed to create the Registry.
`AuthorizerType` is a top-level CloudFormation property; do not copy the SDK's nested shape into CFN.

Key outputs are `RegistryArn`, `RegistryId`, `McpEndpoint`, `DomainName`, and `RepositoryName`.
Use `RegistryArn` as `AGENT_REGISTRY_ARN` for scripts. For custom context values, pass matching
`--domain`, `--repository`, `--region`, and `--registry`/`--registry-id` to the scripts.

## Isolated deployment

Use a unique stack prefix **and** resource names to avoid touching existing demo stacks:

```bash
RUN="registry-test-$(date -u +%Y%m%d-%H%M%S)"
ASSEMBLY="$(mktemp -d)"
npx cdk synth -c stackPrefix="$RUN" -c domainName="$RUN" \
  -c repositoryName=skills-test -c registryName="$RUN" --output "$ASSEMBLY"
npx cdk diff --app "$ASSEMBLY"
npx cdk deploy --all --app "$ASSEMBLY" --outputs-file "$ASSEMBLY/outputs.json"
```

`stackPrefix` is optional; omitting it preserves existing stack names. Do not add or change
it when updating an existing deployment: that selects different stacks, not a rename.
The prefix must start with a letter and contain at most 50 letters, digits or hyphens.
The cloud assembly keeps deployment and cleanup pointed at the same names:
`npx cdk destroy --all --app "$ASSEMBLY"` after explicitly cleaning retained registries.
The optional Cognito stack is not enabled by this isolated core-path example.

## Preview upgrades require a separate migration

The old stack name was `AgentCoreRegistryStack`. The new `AgentRegistryStack` is deliberately
separate: creating a GA resource does not update or migrate the Preview registry.
This avoids treating a namespace/data migration as an ordinary resource replacement.

1. Export/back up Preview data and follow [the AWS migration guide](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/registry-faq.html)
   before the 2026-09-17 cutoff.
2. Choose whether the migration tool or CDK creates the destination registry.
   Do not run both with the same destination name without an explicit import/reconciliation plan.
3. Review `cdk diff` and all retained data before deploying.
4. Switch scripts, identity policies and clients to the new ARN.
5. Do not delete the old stack/data until migration and consumer validation succeed.

This blueprint does not execute data migration or import an existing registry into CloudFormation.

## Retention and cleanup

The GA Registry has `DeletionPolicy: Retain` and `UpdateReplacePolicy: Retain`.
`cdk destroy` therefore **does not delete it or its records**.
To clean up an isolated demo: explicitly delete the records and registry using the GA APIs after
reviewing the data, then remove the stacks. Retained resources must be tracked separately.

CodeArtifact and Cognito keep their pre-existing lifecycle settings. Review their data and users
before destroying stacks; this change does not add a new automatic data-deletion workflow.

## Optional identity

```bash
npx cdk synth -c enableIdentity=true -c enableDefaultReader=true
```

`enableDefaultReader=true` grants only the demo registry/repository. Without it, the default role
has no catalog or artifact access. For team mappings, supply both `groupRepoMap` and
`groupRegistryMap`; see [end-user access](../docs/10-end-user-access.md).

Core stacks were deployed and the scoped-role publish/approve/consume flow was live-tested
in `us-east-1` on 2026-09-09. The optional Cognito stack has only compilation/synthesis coverage
in this run. See [validation details](../docs/13-live-validation.md).
