# End-user access and team isolation

The existing `skill-cli` authenticates users and exposes short-lived AWS credentials through
`credential_process`. It remains useful: native Registry JWT discovery does not authorize CodeArtifact.
The GA trusted consumer uses IAM-signed `GetPackageVersionAsset`, not `pip install`.

## Two independent boundaries

1. **Catalog visibility:** each team receives explicit Registry ARNs and discovery-only permissions.
2. **Artifact access:** each team receives `GetPackageVersionAsset` on the PyPI package ARNs in its repository.

Metadata search filters are not access control. Separate sensitive teams into separate registries.
The default authenticated role has **no registry or artifact access** unless explicitly enabled.
No role receives governance reads, wildcard registry discovery or CodeArtifact delete/publish permissions.

## Single-team identity demo

```bash
cd cdk
npx cdk synth -c enableIdentity=true -c enableDefaultReader=true
npx cdk diff --all -c enableIdentity=true -c enableDefaultReader=true
npx cdk deploy --all -c enableIdentity=true -c enableDefaultReader=true
```

This explicitly grants the default reader access to the one demo registry and one demo repository.
It does not grant access to all repositories in the domain. The old
`defaultGroupAccessAllRepos` context option is removed.

IdentityStack configures the User Pool, Identity Pool, group mapping and scoped roles.
Hosted UI domain setup, federation and user onboarding remain prerequisites as described in
[`skill-cli`](../skills/skill-cli/README.md); this stack does not provision a Hosted UI domain.

## Team-specific mappings

Supply both maps with exactly the same group keys. The repositories and team registries must already exist;
IdentityStack configures access, not their creation:

```bash
cd cdk
npx cdk synth -c enableIdentity=true \
  -c 'groupRepoMap={"finops-readers":"finops-skills-prod","care-readers":"care-skills-prod"}' \
  -c 'groupRegistryMap={"finops-readers":["arn:aws:agent-registry:us-east-1:111122223333:registry/finops123456"],"care-readers":["arn:aws:agent-registry:us-east-1:111122223333:registry/care12345678"]}'
```

These ARNs are examples; replace them before deployment. Empty/wildcard/missing registry mappings
are rejected at synthesis rather than silently granting broader discovery.
Artifact repositories in this construct belong to the deployment account and configured domain.
Configure one team group per demo user; Cognito rule matching is not a union of all group permissions.

Outputs include `DefaultReaderRoleArn` and the per-group role ARNs.
When group rules exist, unmatched identities are denied role selection (`AmbiguousRoleResolution: Deny`).

## Consumer usage

After configuring `skill-cli login` and the `skills` AWS profile:

```bash
AWS_PROFILE=skills python scripts/04_consume_skill.py \
  --registry-arn YOUR_TEAM_REGISTRY_ARN \
  --domain skills-demo --repository YOUR_TEAM_REPOSITORY \
  --name aws-cost-anomaly-triage --version 0.1.0 --target-dir ./demo-skills
```

Keep publisher/curator credentials out of the end-user profile. The role cannot approve or publish.
Manual pip-based installations from older docs are not the verified path and require different permissions.

## OAuth is separate extension work

An OAuth-authorized Registry can be accessed natively by a compatible MCP client without the
Registry SigV4 proxy. That does not remove the artifact credential path above.
This revision provisions IAM-authorized registries only; it does not implement new OAuth deployment constructs.
