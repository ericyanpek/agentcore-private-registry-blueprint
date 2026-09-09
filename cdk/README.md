# CDK deployment

Requires Node.js 20+ and configured deployment credentials.

```bash
npm ci
npx tsc --noEmit
npx cdk synth --strict
npx cdk diff --all
npx cdk deploy --all
```

## Resources and outputs

- `CodeArtifactStack`: the existing private domain/repository, no public upstream.
- `AgentRegistryStack`: native `AWS::AgentRegistry::Registry`, IAM authorization, manual approval.
- Optional `IdentityStack`: temporary-credential access with explicit team registry/repository mappings.

The pinned CDK dependency does not contain an Agent Registry L1, so `RegistryStack` uses
`CfnResource` for the **native CloudFormation resource type**, not `AwsCustomResource`.
No Lambda/SDK custom resource is needed to create the Registry.
`AuthorizerType` is a top-level CloudFormation property; do not copy the SDK's nested shape into CFN.

Key outputs are `RegistryArn`, `RegistryId`, `McpEndpoint`, `DomainName`, and `RepositoryName`.
Use `RegistryArn` as `AGENT_REGISTRY_ARN` for scripts. For custom context values, pass matching
`--domain`, `--repository`, `--region`, and `--registry`/`--registry-id` to the scripts.

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

Validation performed for this revision is offline compilation/synthesis, not a live deployment.
