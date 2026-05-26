# Publishing workflow — for skill authors

> Audience: an engineer in your organization who wrote a skill and
> wants to publish it. Assumes the platform team has already
> deployed the registry and CodeArtifact (if not, see
> [docs/03-demo-walkthrough.md](./03-demo-walkthrough.md)).

The blueprint ships a **meta-skill** named `publish-skill`. Once it's
installed in your `~/.claude/skills/` (instructions below), publishing
any new skill becomes a single Claude Code prompt away.

## TL;DR

```bash
# one-time setup (per-machine)
pip install <publish-skill-package> && install-publish-skill
mkdir -p ~/.skillpublish && cat > ~/.skillpublish/config.toml <<'EOF'
[default]
region = "us-east-1"
codeartifact_domain = "skills-demo"
codeartifact_repository = "skills-prod"
registry_name = "skills-demo-registry"
EOF

# every time you want to publish a new skill
cd path/to/your-new-skill/      # has pyproject.toml + src/<pkg>/skill_files/SKILL.md
# Then in Claude Code, just say:
#   "publish this skill"
# Claude triggers the publish-skill skill and runs the publisher.
```

If you don't want to involve Claude Code at all, the same script
runs from the CLI:

```bash
python3 ~/.claude/skills/publish-skill/scripts/publish.py
```

## What "publishing" actually does

Five distinct steps, all wrapped by `publish.py`:

1. **Build** the skill into a Python wheel (`python -m build`)
2. **Upload** the wheel to CodeArtifact (`twine upload`)
3. **Register** the metadata in Agent Registry as an
   `AGENT_SKILLS` record (`CreateRegistryRecord`)
4. **Wait** for `DRAFT` (~1-2 seconds)
5. **Stop**, leaving the record in `DRAFT`

The author then inspects the record and either submits it for
approval (`--auto-submit` or a separate API call), or deletes
and tries again. **The author cannot approve their own record —
that's the curator's job.**

## The skill-package layout convention

`publish.py` is opinionated. Your skill must look like this:

```
your-new-skill/
├── pyproject.toml                                  # name, version, description
├── README.md                                       # optional
└── src/
    └── your_new_skill/                             # underscore version of name
        ├── __init__.py
        ├── postinstall.py                          # the activation entry point
        └── skill_files/
            ├── SKILL.md                            # frontmatter + body — required
            └── resources/                          # optional supporting files
```

Two things that must match:

- `[project].name` in pyproject.toml ↔ the package directory
  (`your-new-skill` ↔ `your_new_skill`, hyphens to underscores)
- `[tool.setuptools.package-data]` includes
  `"your_new_skill" = ["skill_files/**/*"]` so SKILL.md ends up
  inside the wheel

Copy `skill-package/` from this repo as your starting template.

## What "where does it land" means

Three independent decisions you make at publish time:

| Knob | Where you set it | What it controls |
|---|---|---|
| **AWS account** | The active AWS profile when you run `publish.py` | Which organization sees the skill |
| **Registry** | `--registry` (or `registry_name` in config.toml) | Which catalog inside the account (e.g., `prod-registry`, `dev-registry`, `customer-care-registry`) |
| **CodeArtifact repo** | `--domain` + `--repository` (or in config.toml) | Which PyPI repo holds the artifact |

A typical organization might have:

| Use case | Registry | CodeArtifact repo | Approver |
|---|---|---|---|
| Team-private skills | `team-finops-registry` | `team-finops-skills` | FinOps lead |
| Org-wide skills | `global-shared-registry` | `shared-skills-prod` | Platform team |
| Dev / experiment | `dev-registry` (auto-approve) | `skills-dev` | (none) |

**The Publisher IAM Group** (see [docs/09-publishing-iam.md](./09-publishing-iam.md))
is what gates which authors can publish to each `(registry, codeartifact-repo)`
combination.

## The DRAFT-first policy

By default `publish.py` stops at `DRAFT`. This is on purpose:

- Lets the author re-read the metadata before it goes to a curator
- Catches embarrassing typos in the description (which is what the
  org-wide search will rank on)
- Catches `_meta` mistakes (wrong region, wrong CodeArtifact URL)

To skip the stop and submit immediately, pass `--auto-submit`. Most
teams should leave the default in place.

## When publishing fails

The runbook bundled with the skill itself has a comprehensive
error table. The most common failures:

- **Version collision** (`package version already exists`) — CodeArtifact
  PyPI versions are immutable, bump `pyproject.toml [project].version`
- **Record collision** (`record 'foo' already exists`) — same name was
  already registered, even at a different version. Same fix: bump
  the version
- **`AccessDeniedException`** — your IAM principal isn't in the
  Publishers group. See [docs/09-publishing-iam.md](./09-publishing-iam.md)

## Versioning convention

Use **semantic versioning** in `pyproject.toml`:

| Change | Version bump |
|---|---|
| Typo fix in SKILL.md, no behavior change | patch (0.1.0 → 0.1.1) |
| New resources/ file, new section, no breaking change | minor (0.1.1 → 0.2.0) |
| Description / trigger conditions changed (consumers may need to update prompts) | major (0.x.y → 1.0.0) |
| Skill renamed | new package, old version deprecated |

The skill is published as a new version every time pyproject.toml
ticks; the registry record's `recordVersion` follows the package
version. **Older versions remain installable** — consumers
explicitly pin a version when they need to.

## The full lifecycle, end to end

```
[Author]                              [Curator]                 [Consumer]

write SKILL.md
edit pyproject.toml
"publish this skill"  ─────────▶
   │
   ▼ publish.py
   build wheel
   twine upload  ─────────────▶ CodeArtifact (artifact stored)
   CreateRegistryRecord  ─────▶ Registry (DRAFT)
   ─ stop ─

inspect DRAFT
submit for approval  ─────────▶                        Registry (PENDING)
                                              [console / API]
                                                   ▲
                                          UpdateRegistryRecordStatus APPROVED ─▶ Registry (APPROVED, indexed in 15-30s)
                                                                                              │
                                                                                              ▼
                                                                                      search_registry_records
                                                                                      finds the new skill
                                                                                              │
                                                                                              ▼
                                                                                       pip install + activate
                                                                                              │
                                                                                              ▼
                                                                                       ~/.claude/skills/<name>/
                                                                                          available next prompt
```

## See also

- [docs/09-publishing-iam.md](./09-publishing-iam.md) — IAM groups
  for Publishers, Curators, Readers, day-to-day developers
- [skills/publish-skill/SKILL.md](../skills/publish-skill/SKILL.md) — the
  meta-skill itself
- [skills/publish-skill/scripts/publish.py](../skills/publish-skill/scripts/publish.py) —
  the underlying tool, runnable directly without going through Claude
