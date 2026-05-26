# agentcore-private-skills-blueprint

> A working blueprint for running a **private, governed Agent Skills
> registry on AWS** — built on Amazon Bedrock AgentCore Registry +
> AWS CodeArtifact. Includes one-click CDK, an end-to-end Python demo,
> and a real text-only skill that gets installed into Claude Code.

**Status**: Preview-stage reference (2026-05). AWS Agent Registry is in public preview; APIs may change.

---

## Why this exists

In 2025-2026, **Agent Skills became how teams encode their SOPs**:
financial analysis playbooks, incident triage runbooks, data discovery
methodologies, compliance review checklists. A skill is no longer a
prompt — it's a piece of operational IP that an AI agent will execute
without further human translation.

That makes "where do skills live and who can publish them" a real
governance question:

- **Privacy** — a financial-analysis skill embeds internal margin
  conventions, customer tiers, pricing rules. **It cannot live on a
  public marketplace or in a public GitHub.**
- **Compliance** — MAS/HKMA/PBOC, HIPAA, EU AI Act all treat
  agent-executable instructions as auditable artifacts. You need
  versioning, approval trails, immutable history.
- **Discoverability at scale** — once an org has 50+ skills, search
  and trust signals matter more than git URLs in a Confluence page.

Public skill marketplaces (Anthropic's, npm-style hubs like
`skills.sh`) and self-hosted hobbyist projects (e.g., iflytek's
SkillHub) **don't fit the enterprise constraint**. AWS shipped
Bedrock AgentCore Registry in 2026-04 specifically for this gap.

This repo is the missing piece: **how to actually wire AWS Agent
Registry + CodeArtifact into a working private skill distribution
pipeline**, with one-click infrastructure and a demo skill you can
verify against your own Claude Code install.

[→ Full rationale: `docs/01-why-private-skills.md`](docs/01-why-private-skills.md)

## What's in this blueprint

| Concern | AWS service used | What this repo provides |
|---|---|---|
| **Discovery + governance** | Bedrock AgentCore Registry | CDK that creates the registry; Python scripts that publish/approve records; reference `skillDefinition` schema |
| **Artifact storage** | CodeArtifact (PyPI repo) | CDK that creates domain + repo; `pyproject.toml` template for text-only skills |
| **Skill format** | (the SKILL.md spec) | One real example: `aws-cost-anomaly-triage` with frontmatter + 6 resource files |
| **Activation** | (consumer-side) | `postinstall.py` console script + `04_consume_skill.py` showing search → install → activate end-to-end |
| **One-click deploy** | AWS CDK (TypeScript) | `cdk deploy` provisions everything in ~3 minutes |
| **Auth** | IAM today, JWT/OIDC documented | Working IAM auth in scripts; OAuth/JWT path documented as Phase 2 |

## What you can do with it in 10 minutes

```bash
# 1. Deploy infra (CodeArtifact domain + repo, Agent Registry)
cd cdk && npm install && npx cdk deploy

# 2. Build & publish the example skill to CodeArtifact
cd ../skill-package && python3 -m build
aws codeartifact login --tool twine --domain skills-demo --repository skills-prod --region us-east-1
python3 -m twine upload --repository codeartifact dist/*

# 3. Register, approve, and verify end-to-end discovery
cd ../scripts
python3 02_register_skill.py
python3 03_approve_skill.py
python3 04_consume_skill.py
```

After step 3, `~/.claude/skills/aws-cost-anomaly-triage/` exists and
Claude Code automatically lists the skill alongside its built-ins.

## Architecture (1-minute version)

```
┌──────────────────────────────────────────────────────────┐
│  Author / CI                                              │
│  pyproject.toml + SKILL.md + resources                    │
└─────────┬─────────────────────────────────────┬───────────┘
          │ twine upload                        │ create_registry_record
          ▼                                     ▼
┌────────────────────────┐         ┌────────────────────────┐
│ CodeArtifact (PyPI)    │         │ Bedrock AgentCore      │
│ Private artifact store │◀────────│ Registry               │
│ KMS at-rest, IAM auth  │ packages│ Metadata + governance  │
└────────────────────────┘         └────────────────────────┘
          ▲                                     ▲
          │ pip install                         │ search_registry_records
          │                                     │   (boto3 OR MCP endpoint)
          └────────────┬────────────────────────┘
                       ▼
            Consumer: developer / agent
            ─→ install-aws-cost-anomaly-triage
            ─→ ~/.claude/skills/<name>/  (immediately discoverable)
```

[→ Full architecture: `docs/02-architecture.md`](docs/02-architecture.md)

## Repository layout

```
.
├── README.md                          # this file
├── docs/
│   ├── 01-why-private-skills.md       # the enterprise case
│   ├── 02-architecture.md             # service mapping + diagrams
│   ├── 03-demo-walkthrough.md         # the 4-script flow with timings
│   ├── 04-dynamic-discovery.md        # MCP endpoint: how Claude Code finds skills
│   ├── 05-auth-placeholder.md         # IAM today, JWT/OIDC TODO
│   └── 06-future-optimizations.md     # cross-account, KMS CMK, EventBridge, OCI
├── cdk/                               # one-click TypeScript CDK
│   ├── bin/blueprint.ts
│   ├── lib/codeartifact-stack.ts
│   ├── lib/registry-stack.ts
│   └── package.json
├── skill-package/                     # the example skill, ready to publish
│   ├── pyproject.toml
│   └── src/aws_cost_anomaly_triage/
│       ├── postinstall.py
│       └── skill_files/
│           ├── SKILL.md
│           └── resources/*.md
└── scripts/                           # boto3 publish/approve/consume
    ├── 01_create_registry.py
    ├── 02_register_skill.py
    ├── 03_approve_skill.py
    └── 04_consume_skill.py
```

## Status of each section

| Section | Status |
|---|---|
| CodeArtifact + Agent Registry CDK | ✅ Working |
| `aws-cost-anomaly-triage` example skill | ✅ Working |
| Publish + approve + consume scripts | ✅ Tested end-to-end |
| MCP endpoint dynamic discovery | ✅ Documented; client config example |
| IAM auth | ✅ Working |
| JWT/OIDC auth (Cognito/Okta) | 🔶 Phase 2 — see `docs/05-auth-placeholder.md` |
| Cross-account skill consumption | 🔶 Phase 2 |
| KMS CMK on CodeArtifact | 🔶 Phase 2 |
| EventBridge → Slack approval pipeline | 🔶 Phase 2 |
| OCI artifact distribution | ⏸ Future — pending agentskills/agentskills spec |
| GitHub Actions CI for publish-on-merge | ⏸ Future |

[→ Roadmap: `docs/06-future-optimizations.md`](docs/06-future-optimizations.md)

## Why now (the SA take)

Two timing facts make this blueprint valuable in 2026-Q2:

1. **AWS Agent Registry just shipped (2026-04 preview)**. There is
   currently **no AWS official blog or sample repo that connects it
   to CodeArtifact for skill distribution**. This repo fills that gap
   with verified end-to-end code.
2. **Skills as enterprise IP is a real concern but most teams haven't
   hit it yet**. The first wave of customers asking "where do my
   private skills live" is happening now. Having a working blueprint
   means an SA conversation goes from "let me get back to you" to
   "here's the repo, let's adapt it to your IdP."

This repo is intentionally opinionated where AWS docs aren't:
PyPI-via-CodeArtifact is the recommended artifact backend, IAM auth
is the day-1 path, JWT/OIDC is the day-2 path. Disagreements welcome
— file an issue.

## Inspiration / prior art

- AWS Agent Registry public docs and the 2026-04 preview launch blog
- Pinterest's "central registry + paved path" MCP architecture (ByteByteGo deep dive)
- ToolHive / Stacklok Enterprise (the production-ready MCP equivalent for tools)
- iflytek/skillhub (the cautionary tale: protocol mismatch with where the industry went)
- Anthropic's `anthropics/skills` repo (the format definition)

## License

Apache 2.0. See [LICENSE](LICENSE).

## Disclaimer

The author is an AWS Solutions Architect; this is a personal
blueprint, not an AWS-published reference. Validate against your
account-specific compliance requirements before production use.
