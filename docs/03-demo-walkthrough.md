# GA walkthrough: publish, approve, verify, activate

Run from the repository root. Use Python 3.11+ and install the shared blueprint package:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[publish]'
```

For a copied `publish-skill` meta-skill, install this same package in the interpreter that runs
its script. Copying `publish.py` alone does not include the shared validation library.

## 1. Provision as an administrator

Review [CDK lifecycle and migration](../cdk/README.md), then:

```bash
cd cdk
npm ci
npx cdk synth
npx cdk diff
npx cdk deploy --all
cd ..
export AGENT_REGISTRY_ARN='arn:aws:agent-registry:us-east-1:YOUR_ACCOUNT_ID:registry/YOUR_REGISTRY_ID'
```

Use the actual `AgentRegistryStack.RegistryArn` output. The built-in configuration creates
`skills-demo/skills-prod` and `skills-demo-registry` in `us-east-1`.
Existing CodeArtifact data is not copied or replaced by the Registry namespace migration.
`scripts/01_create_registry.py` is an SDK-only alternative to provisioning the registry with CDK;
do not run both to create the same named resource.

## 2. Configure three identities

Create/configure `publisher`, `curator`, and `consumer` profiles using your organization's normal
federation/role-assumption process. Apply [the role-specific permissions](09-publishing-iam.md).
Do not use an administrator profile as proof that consumer isolation works.

## 3. Publish a wheel and its exact metadata

```bash
python skills/publish-skill/scripts/publish.py --package-dir skill-package --dry-run
AWS_PROFILE=publisher python skills/publish-skill/scripts/publish.py \
  --package-dir skill-package --auto-submit
```

The dry run performs only local metadata checks. It does not prove AWS authorization or that a
future build will succeed. Real publication:

1. Builds one wheel in a fresh temporary output directory.
2. Rejects wheels with Python dependencies, unsafe paths or unexpected package identities.
3. Extracts `SKILL.md` from the wheel and compares it byte-for-byte with the source.
4. Uploads only that wheel; the short-lived Twine token is passed in the subprocess environment,
   not command-line arguments, pip config or `.pypirc`.
5. Confirms the CodeArtifact asset's SHA-256 matches the built wheel.
6. Creates a GA `SKILL` record with digest, source and package identity.
7. Submits the draft when `--auto-submit` is present. Without it, stops at `DRAFT`.

To publish an already built wheel, use `--wheel path/to/release.whl`.
To retry after the upload succeeded but registration failed, add `--skip-upload` with the **same**
wheel. Its digest is still compared with CodeArtifact before registration.
Same name/version plus identical metadata reuses a record; different bytes require a new version.
The publisher does not overwrite existing record content or approve records.

`scripts/02_register_skill.py --wheel path/to/release.whl` is the register-only alternative.
It verifies an already uploaded asset and submits a draft; it does not build or upload.

## 4. Verify the pre-approval boundary

Before approval:

```bash
AWS_PROFILE=consumer python scripts/04_consume_skill.py --target-dir ./demo-skills
```

Expected: no approved match and no new installed skill.
Also attempt a governance read using the consumer identity:

```bash
AWS_PROFILE=consumer aws agent-registry-control get-registry-record \
  --registry-id "$AGENT_REGISTRY_ARN" --record-id RECORD_ID --region us-east-1
```

Expected: access denied. The consumer policy grants no governance reads.
If it succeeds, inspect other policies/resource policies attached to that identity.

## 5. Approve as the curator

Inspect the full record, skill SOP and supporting files before approving:

```bash
AWS_PROFILE=curator python scripts/03_approve_skill.py \
  --name aws-cost-anomaly-triage --version 0.1.0 \
  --reason 'Reviewed SOP, supporting resources, publisher and wheel digest'
```

The curator script only approves `PENDING_APPROVAL`; it does not submit drafts.
This separation is enforced with separate IAM policies, not merely profile names.

## 6. Consume as the reader

```bash
AWS_PROFILE=consumer python scripts/04_consume_skill.py \
  --name aws-cost-anomaly-triage --version 0.1.0 --target-dir ./demo-skills
python scripts/05_verify_installed_skill.py ./demo-skills/aws-cost-anomaly-triage
```

The consumer uses one explicit registry, server-side type/name/version filtering, and
`BatchGetDiscoverableRegistryRecord` for full approved details. It never switches to
`GetRegistryRecord`. After approval, allow for discovery indexing and retry a miss.

`--domain`, `--repository`, `--region` and optional `--domain-owner` define the trusted
artifact location independently of the record. By default the domain owner is the registry
owner. Cross-account artifact repositories need an explicit owner and appropriate IAM/resource policies.

Only verified `skill_files/` content is copied. Package code and `postinstall.py` never run.
To activate in Claude Code, choose `--target-dir ~/.claude/skills` after reviewing the demo.

## 7. Negative checks and upgrades

- Change a copied `SKILL.md`, add a file or delete a resource: the local verifier must fail.
- Reinstall the same unchanged release: succeeds without replacing the tree or changing provenance.
- Try to overwrite a modified or different release: fails; review and remove the old tree explicitly first.
- A replaced wheel at the same name/version must fail the digest check before extraction.
  Do not delete/re-publish production package versions to perform this experiment; use an isolated demo.
- An unapproved, deprecated, inaccessible or changed record must fail discovery/recheck.
- A record pointing at a different repository must fail even when the caller has broader AWS permissions.
- For two-team isolation, test both registry discovery and artifact download using the other team's identity.

Version upgrades require a new package/record version, independent approval, and an explicit local
replacement decision. This blueprint does not silently choose the first semantic match or latest package.

## Validation status

On 2026-09-09, native CloudFormation deployment and the core positive/negative flow passed
live checks in `us-east-1`, using separate publisher, curator and consumer IAM roles.
This includes pre-approval rejection, cross-team denial, approved consumption, local drift,
remote same-version wheel substitution and deprecation. Boto3/Botocore 1.43.90 contract checks,
17 offline scenarios, TypeScript compilation and CDK synthesis also passed.
See [the validation record](13-live-validation.md) for dependency fixes, cleanup and untested areas.
Repeat these acceptance checks in your own deployment; they are not a production-security certification.
