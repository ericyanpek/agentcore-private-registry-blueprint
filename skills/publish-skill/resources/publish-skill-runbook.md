# Publish-skill runbook — GA

The interpreter must have the shared blueprint package installed with publishing extras:
`python -m pip install -e '.[publish]'` from the cloned repository.
Copying this skill's directory does not copy that library.

## Preconditions

- Python 3.11+; a directory with `pyproject.toml` and `src/<normalized_package>/skill_files/SKILL.md`.
- A GA Registry and CodeArtifact repository, plus explicit publishing authorization.
- The publisher role must not have Registry approval permissions.

## 1. Local preflight

```bash
python <path-to-publish.py> --package-dir <skill-project> --dry-run
```

This performs no AWS calls and no build. It is not an IAM permission audit.
Defaults are `skills-demo`, `skills-prod`, `skills-demo-registry`, `us-east-1`;
override them with flags or `~/.skillpublish/config.toml`.
`AGENT_REGISTRY_ARN`/`--registry-id` avoids listing registries by name.

## 2. Publish

After the user approves publication:

```bash
python <path-to-publish.py> --package-dir <skill-project>
```

Builds one wheel, derives its Markdown/digests, uploads it, verifies the CodeArtifact hash,
and creates a `SKILL` record in `DRAFT`. No package installation hook executes.
Twine receives a short-lived token through environment variables, not a persistent config file.

For an existing wheel use `--wheel path/to/release.whl`.
If upload already succeeded, retry with `--wheel ... --skip-upload` so the same bytes are reused.
The remote digest is still checked. Bump the version for different content.

## 3. Inspect and submit

```bash
aws agent-registry-control get-registry-record \
  --registry-id REGISTRY_ARN --record-id RECORD_ID --region us-east-1
aws agent-registry-control submit-registry-record-for-approval \
  --registry-id REGISTRY_ARN --record-id RECORD_ID --region us-east-1
```

Check `recordType=SKILL`, `recordVersion`, `agentSkillsDefinition.data`,
the `com.example.integrity`/`com.example.codeartifact` conventions, and
`agentSkillsDefinition.additionalData.skillMd.data`.
Alternatively, `--auto-submit` submits immediately after creation/reuse of a draft.

## 4. Separate curator

Approval is outside this publishing skill's scope.
The curator reviews content and provenance and uses `scripts/03_approve_skill.py --reason ...`.
Allow discovery indexing to catch up after approval.

## 5. Verified consumer

Use `scripts/04_consume_skill.py` for the approved exact version.
Do not translate record metadata into arbitrary shell commands, run the legacy postinstall command,
or recommend unverified `pip install` as the trusted consumption flow.

For permissions, limitations and live acceptance steps, see `docs/09-publishing-iam.md`,
`docs/12-record-artifact-integrity.md`, and `docs/03-demo-walkthrough.md` in the repository.
