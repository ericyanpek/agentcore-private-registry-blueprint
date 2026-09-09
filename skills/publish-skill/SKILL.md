---
name: publish-skill
description: |
  Use when the user wants to publish a new agent skill (a directory
  containing `pyproject.toml` + `src/<pkg>/skill_files/SKILL.md`) to
  the company's private AWS Agent Registry + CodeArtifact. Walks
  build → CodeArtifact upload → CreateRegistryRecord → optional
  submit-for-approval. Requires AWS credentials with
  codeartifact:PublishPackageVersion and agent-registry:CreateRegistryRecord
  on the target registry. AWS rejects unauthorized publication.
  Triggers on phrases like "publish this skill", "register
  this in our skill registry", "把这个 skill 发布出去", "推到 skills
  registry".
---

# Publishing a skill to the private registry

Requires Python 3.11+ and the shared blueprint library installed in the active interpreter:
`python -m pip install -e '.[publish]'` from the cloned repository. Copying this skill
directory alone does not install that dependency. The current runbook is authoritative.

This is the meta-skill that publishes other skills. It is intentionally
**limited in scope**: it assumes the project layout that this
blueprint's [skill-package/](../../skill-package) example uses,
and refuses to invent fields it doesn't have.

## When to invoke

- User says "publish this skill" / "把这个 skill 发布出去" /
  "register this skill in our registry" / "send this to skills hub"
- User has just finished editing a directory that contains
  `pyproject.toml` and `src/<pkg>/skill_files/SKILL.md`
- The user's intent is to make a skill discoverable across the
  organization, not just to test it locally

## When NOT to invoke

- The user is editing the skill content itself (use the regular
  edit flow; do not auto-publish drafts)
- The user is consuming a skill (search / install / use) — that's
  a different flow, see the consumer scripts
- There's no `pyproject.toml` in the current directory — this skill
  cannot publish raw markdown without a packaging step
- The user is on a machine without AWS credentials — refuse to
  proceed and explain how to set them up

## How this skill works

The work is delegated to a single Python script:
`scripts/publish.py`. The script is parameterized — it reads
defaults from `~/.skillpublish/config.toml` and accepts CLI flags
to override.

Always read [`resources/publish-skill-runbook.md`](resources/publish-skill-runbook.md)
**before** running anything. The runbook covers:

- The preflight checks the script performs (and what to do when
  one fails)
- How the four "knobs" (account / registry / CodeArtifact repo /
  namespace) decide where the skill lands
- The `DRAFT → PENDING_APPROVAL → APPROVED` lifecycle and who is
  expected to push each transition
- Common errors (record name collision, IAM AccessDenied, version
  immutability) and their resolutions

## Defaults and overrides

The script reads `~/.skillpublish/config.toml`:

```toml
[default]
region = "us-east-1"
codeartifact_domain = "skills-demo"
codeartifact_repository = "skills-prod"
registry_name = "skills-demo-registry"
```

If the file is absent, the script uses the demo defaults shown above.
Confirm that these are the intended destinations before publishing; pass explicit flags otherwise.

## Permissions

This skill cannot bypass IAM. Dry-run only checks local metadata and makes no AWS calls.
During real publication, AWS enforces authorization. Tokens are passed to Twine through its
environment, never persisted in pip configuration. The publisher role must not approve records.

For the full permission set required to run this skill end-to-end,
see [docs/09-publishing-iam.md](../../docs/09-publishing-iam.md).

## Default behavior is conservative

Two safeguards by default:

- **No auto-submit.** The script creates the record and stops at
  `DRAFT`. The author reviews via console / `get-registry-record`
  before running with `--auto-submit` to advance to `PENDING_APPROVAL`.
- **No update of existing content.** Identical name/version metadata is reused;
  different content at the same version is rejected. A new version may use the same name.
  Retry an already-uploaded wheel with `--wheel ... --skip-upload`; its digest is still checked.

If the user explicitly says "submit it for approval" / "go all the
way", pass `--auto-submit`. Otherwise leave the conservative default.

## What this skill does NOT do

- It does not approve records (separation of duty — only curators
  can; their IAM grants `UpdateRegistryRecordStatus`).
- It does not delete or yank records (also a curator's domain).
- It does not create the registry, the CodeArtifact domain, or
  any IAM resources — those are infrastructure provisioned by
  `cdk deploy` once per account.
- It does not validate skill quality (content review, scanning,
  policy compliance) — those belong on the curator's checklist
  or in an EventBridge-triggered scanner pipeline (see Phase 2).
