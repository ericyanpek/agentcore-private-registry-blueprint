# Publish-skill runbook

This is the step-by-step Claude follows when the user invokes the
`publish-skill` skill. The agent should read this runbook end-to-end
before executing any command.

## Preconditions Claude verifies

1. The user is in (or just `cd`'d into) a directory containing
   `pyproject.toml`. If not, ask them to navigate to one.
2. That directory has `src/<pkg>/skill_files/SKILL.md`. If not,
   tell the user to follow the layout convention shown in
   `skill-package/` and stop.
3. AWS credentials are set in the environment / profile. If
   `aws sts get-caller-identity` fails, point the user to
   `aws configure sso` (or whatever their org uses) and stop.

If all three pass, proceed.

## Decide on parameters

Default values come from `~/.skillpublish/config.toml`. If the user
has it set up, use it. Otherwise ask:

> Where should I publish this skill?
> - Region (default us-east-1):
> - CodeArtifact domain:
> - CodeArtifact repository:
> - Agent Registry name:

Suggest writing to `~/.skillpublish/config.toml` for next time:

```toml
[default]
region = "us-east-1"
codeartifact_domain = "skills-demo"
codeartifact_repository = "skills-prod"
registry_name = "skills-demo-registry"
```

## Step 1 — Dry-run preflight

Always run dry-run first:

```bash
python3 <path-to-publish.py> --dry-run
```

(If `<path-to-publish.py>` is `~/.claude/skills/publish-skill/scripts/publish.py`,
that's where it lands when this skill itself was installed via the
standard postinstall flow.)

Expected output ends with `preflight OK\n--dry-run set; stopping`.

If preflight fails, the error message tells the user exactly what
to fix (missing pyproject.toml, missing SKILL.md frontmatter, etc.).
**Don't continue past a failed preflight.**

## Step 2 — Run the real publish

If dry-run was clean:

```bash
python3 <path-to-publish.py>
```

This runs:

1. `python -m build` — produces wheel + sdist in `./dist/`
2. `aws codeartifact login --tool twine ...` — refreshes the 12h pip token
3. `python -m twine upload --repository codeartifact dist/*` — uploads the wheel
4. `CreateRegistryRecord` — registers metadata, descriptorType=AGENT_SKILLS
5. Polls until status=DRAFT (~1-2 seconds)

**Important: stops at DRAFT by default.** The author should inspect
the record before submitting it for approval.

## Step 3 — Inspect the DRAFT record

Show the user the record's metadata:

```bash
aws bedrock-agentcore-control get-registry-record \
  --registry-id <id> --record-id <id> --region us-east-1
```

Verify:

- `descriptorType` is `AGENT_SKILLS`
- `descriptors.agentSkills.skillMd.inlineContent` contains the full
  SKILL.md text (frontmatter included)
- `descriptors.agentSkills.skillDefinition.inlineContent` parses
  to JSON with `packages[0].registryType == "pypi"` and the right
  package identifier

If anything looks wrong (wrong region in `_meta.codeartifact`, etc.),
delete the record and re-run with corrected parameters:

```bash
aws bedrock-agentcore-control delete-registry-record \
  --registry-id <id> --record-id <id>
```

## Step 4 — Submit for approval

Once the DRAFT looks right:

```bash
aws bedrock-agentcore-control submit-registry-record-for-approval \
  --registry-id <id> --record-id <id> --region us-east-1
```

Or re-run the publisher with `--auto-submit` (it will skip steps
1-3 if the version was already uploaded — actually it won't,
because CodeArtifact rejects duplicate versions; bump the version
in pyproject.toml first if you need a fresh attempt).

Status moves to `PENDING_APPROVAL`. A curator now needs to act.

## Step 5 — Curator approval (separate person)

This is **not part of the publish-skill skill's scope**. The
curator is a different IAM principal with
`bedrock-agentcore:UpdateRegistryRecordStatus`. They use the
AgentCore console or:

```bash
aws bedrock-agentcore-control update-registry-record-status \
  --registry-id <id> --record-id <id> \
  --status APPROVED --status-reason "<reason>"
```

15-30 seconds after APPROVED, the record is searchable across the
org — by humans via the console, by agents via the Registry MCP
endpoint or `search_registry_records`.

## Common errors

| Error | Cause | Fix |
|---|---|---|
| `botocore.errorfactory.ConflictException: package version already exists` | `pyproject.toml` version was already uploaded — CodeArtifact PyPI versions are immutable | Bump version in `pyproject.toml`, re-run |
| `record 'foo' already exists` | A registry record with this name exists at any version | Bump `pyproject.toml` version, re-run (record name + version compose the unique key) |
| `AccessDeniedException` on `CreateRegistryRecord` | Caller lacks `bedrock-agentcore:CreateRegistryRecord` | Get added to the Publishers IAM group; see [docs/09-publishing-iam.md](../../docs/09-publishing-iam.md) |
| `AccessDenied` on twine upload | Caller lacks `codeartifact:PublishPackageVersion` | Same Publishers group |
| `registry not found` | The registry-name doesn't exist in this account/region, or you're in the wrong region | Run `aws bedrock-agentcore-control list-registries`, fix `--region` or `--registry` |
| `no SKILL.md at expected path` | Skill files are not in the conventional location | Move them to `src/<pkg_module>/skill_files/SKILL.md`. The wheel must contain the SKILL.md as package data |
| `SKILL.md is missing the YAML frontmatter` | The file doesn't start with `---` | Add the frontmatter; see `skill-package/` for a working example |

## What "successful publish" looks like

End state, in this order:

1. CodeArtifact has a new package version (`aws codeartifact list-package-versions ...` shows it)
2. Agent Registry has a new record in `APPROVED` status
3. Other developers / agents can `search_registry_records` and
   find the new skill
4. The record's `_meta.com.example.activate.postInstallCommand`
   tells consumers how to install it locally — typically
   `install-<skill-name>` after `pip install <skill-name>`

If you got to step 2 but step 3 takes more than 30 seconds, that's
the search-index lag we documented in the demo walkthrough; wait
and try again.
