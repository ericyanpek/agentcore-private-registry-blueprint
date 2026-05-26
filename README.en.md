# agentcore-private-registry-blueprint

> 🌐 [中文版 README](./README.md) · **English (this page)**

> A working blueprint for running a **private, governed AI resource
> registry on AWS** — built on Amazon Bedrock AgentCore Registry +
> AWS CodeArtifact.
>
> **Day 1**: ships a verified end-to-end **Skills** demo (one-click
> CDK + a real skill that installs into Claude Code).
>
> **Day N**: the same registry — and most of the same patterns —
> hold MCP servers, A2A agents, knowledge bases, Lambda tools,
> guardrails, Cedar policies, eval datasets, and any custom resource
> your org wants to govern. See
> [docs/07-extending-to-other-resources.md](docs/07-extending-to-other-resources.md).

**Status**: Preview-stage reference (2026-05). AWS Agent Registry is in public preview; APIs may change.

---

## Why this exists

This blueprint exists at the intersection of two AWS shipments:

- **Bedrock AgentCore Registry** (preview, 2026-04) — a governed,
  searchable catalog for **agents, MCP servers/tools, skills, and
  any custom resource** an org wants to publish privately
- **CodeArtifact** — the obvious-but-rarely-paired private artifact
  backend for the things in that catalog

Together they solve a problem most enterprises haven't articulated yet
but will hit by mid-2026: **AI resources have become enterprise IP,
and they need the same governance you give code, infrastructure,
and data**.

The Day-1 demo focuses on **Skills** because that's where the privacy
case is sharpest:

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

## Architecture (1-minute version)

<p align="center">
  <img src="docs/images/architecture.svg" alt="Architecture overview" width="900">
</p>

Four actors: **Author / CI** pushes the skill to two backends in parallel — the artifact (PyPI package) goes to **CodeArtifact**, the metadata goes to the **Agent Registry**. The **consumer** (a developer, or Claude Code / AgentCore Runtime itself) searches the Registry, follows the `packages[]` pointer in the returned metadata to `pip install` from CodeArtifact, lands the files under `~/.claude/skills/<name>/`, and the agent picks the skill up on its next prompt.

[→ Full architecture: `docs/02-architecture.md`](docs/02-architecture.md)

## What's in this blueprint

The Day-1 scope (verified end-to-end):

| Concern | AWS service used | What this repo provides |
|---|---|---|
| **Discovery + governance** | Bedrock AgentCore Registry | CDK that creates the registry; Python scripts that publish/approve records; reference `skillDefinition` schema |
| **Artifact storage** | CodeArtifact (PyPI repo) | CDK that creates domain + repo; `pyproject.toml` template for text-only skills |
| **Skill format** | (the SKILL.md spec) | One real example: `aws-cost-anomaly-triage` with frontmatter + 6 resource files |
| **Activation** | (consumer-side) | `postinstall.py` console script + `04_consume_skill.py` showing search → install → activate end-to-end |
| **One-click deploy** | AWS CDK (TypeScript) | `cdk deploy` provisions everything in ~3 minutes |
| **Auth** | IAM today, JWT/OIDC documented | Working IAM auth in scripts; OAuth/JWT path documented as Phase 2 |

The Day-N scope (documented, ready to extend):

The same registry holds four `descriptorType`s. This blueprint demos
`AGENT_SKILLS`; the others are equally first-class:

| `descriptorType` | What it catalogs | Schema |
|---|---|---|
| `AGENT_SKILLS` | Reusable SOPs (this demo) | SKILL.md + skillDefinition v0.1.0 |
| `MCP` | MCP servers / tools | MCP server.json (open spec) |
| `A2A` | Agents | Google A2A Agent Card |
| `CUSTOM` | Anything else (KBs, Lambda tools, guardrails, Cedar policies, SFN state machines, eval sets, schemas, …) | You define the JSON shape |

A walked-through "customer care" example registering 18 resources
across all four types lives in
[`docs/07-extending-to-other-resources.md`](docs/07-extending-to-other-resources.md).

## What you can do with it in 10 minutes

```bash
# 1. Deploy infra (CodeArtifact domain + repo, Agent Registry)
cd cdk && npm install && npx cdk deploy --all

# 2. Build & publish the example skill to CodeArtifact
cd ../skill-package && python3 -m build
aws codeartifact login --tool twine --domain skills-demo --repository skills-prod --region us-east-1
python3 -m twine upload --repository codeartifact dist/*

# 3. Register, approve, and verify end-to-end discovery
cd ../scripts
python3 02_register_skill.py
python3 03_approve_skill.py
sleep 30   # the search index takes 15-30s to pick up a freshly approved record
python3 04_consume_skill.py
```

After step 3, `~/.claude/skills/aws-cost-anomaly-triage/` exists and
Claude Code automatically lists the skill alongside its built-ins.

## How authors publish — with `publish-skill` (the meta-skill)

The blueprint ships a special skill at **`skills/publish-skill/`**.
It is itself a skill, but its job is to **help authors publish other
skills to the Registry**. Once installed in `~/.claude/skills/`, an
author just says "publish this skill" in Claude Code and the entire
build → upload → register → submit-for-approval flow runs.

```bash
# one-time setup (per machine)
mkdir -p ~/.skillpublish && cat > ~/.skillpublish/config.toml <<'EOF'
[default]
region = "us-east-1"
codeartifact_domain = "skills-demo"
codeartifact_repository = "skills-prod"
registry_name = "skills-demo-registry"
EOF

# every time you publish a new skill
cd path/to/your-new-skill/      # has pyproject.toml + src/<pkg>/skill_files/SKILL.md
# In Claude Code, say: "publish this skill"
# Claude triggers the publish-skill skill, which runs publish.py:
#   build → twine upload → CreateRegistryRecord → stop at DRAFT for review
```

**Permission is enforced by IAM, not by the skill.** Even if
`publish-skill` is installed on a machine, **a user without
`codeartifact:PublishPackageVersion` and
`bedrock-agentcore:CreateRegistryRecord` is denied by IAM.** That's
the real guardrail; the skill is the convenience layer that lowers
the friction.

Four personas + the IAM policies that map to them are documented
in [docs/09-publishing-iam.md](docs/09-publishing-iam.md):
- **Reader**: everyone — search + install approved skills
- **Publisher**: scoped to a team — create + submit-for-approval
- **Curator**: a small list — approve / reject (**Publishers
  cannot approve their own records** by separation of duty)
- **Admin**: very few — manages the registry itself

Full author-facing doc: [docs/08-publishing-workflow.md](docs/08-publishing-workflow.md).

## Mental model — what Registry is and isn't

The single most common misconception about AWS Agent Registry is
that it's a "skill download service". It isn't. Get this right and
the rest of the design follows.

**Registry is a discovery + governance service for metadata. It does
not host artifacts and it does not install anything.**

The MCP endpoint a registry exposes contains exactly **one** tool:

```
search_registry_records(searchQuery, maxResults, filter)
```

No `install`, no `download`, no `activate`. Intentional. Compare to
how npm works:

| | npm ecosystem | Agent Registry ecosystem |
|---|---|---|
| Search service | `registry.npmjs.org` | Agent Registry MCP endpoint |
| Search command | `npm search` | `search_registry_records` |
| Install command | `npm install` (CLI, client-side) | `pip install` (run by Claude Code's Bash tool) |
| Local install dir | `~/.node_modules/` | `~/.claude/skills/` |
| Auto-load installed | Node `require()` resolution | Claude Code scans `~/.claude/skills/` on every prompt |

So when Claude Code uses a private skill, three independent things
happen — and they are **decoupled by design**:

```
1. DISCOVER (remote, metadata-only, KB-sized)
   Claude Code → Registry MCP → search_registry_records
   Returns: SKILL.md + packages[] pointers
   No artifact transferred.

2. DECIDE (Claude reasoning, no API call)
   Claude reads the skillMd, decides whether to:
     (a) inline the SKILL.md into context for one-shot use, OR
     (b) install persistently via Bash, OR
     (c) skip — already installed locally

3. INSTALL (only if 2b, runs Claude Code's built-in Bash tool)
   pip install <pkg> from CodeArtifact + post-install copy
   Idempotent: re-running pip on a same-version package is a no-op.
```

The Registry never *pushes* a skill to your machine. The Registry
never knows whether you have a skill installed locally. Those two
concerns belong to the agent runtime (Claude Code) and to your
consumer scripts.

### Two layers of "discovery", running in parallel

```
┌──────────────────────────────────────┐
│ Remote layer                         │
│ Registry MCP / SDK                   │
│ → returns metadata for the org's     │
│   approved catalog                   │
│ → unaware of your local filesystem   │
└──────────────────────────────────────┘
                 ┊  no communication
                 ┊
┌──────────────────────────────────────┐
│ Local layer                          │
│ Claude Code / Bedrock Runtime        │
│ → scans ~/.claude/skills/ on every   │
│   prompt, lists what it finds        │
│ → unaware of the Registry            │
└──────────────────────────────────────┘
```

The two layers don't talk to each other. A skill installed yesterday
is found by the local layer instantly, with **zero remote calls**. A
skill the team just published is found by the remote layer, with
**zero local effect** until someone (or some agent) decides to
install it.

### Cost of each interaction

| Scenario | What runs | Bytes over the wire |
|---|---|---|
| Skill already in `~/.claude/skills/` | Local scan | 0 |
| Search returns a skill, Claude inlines into context | `search_registry_records` | ~5KB metadata |
| Search → decide to install | search + `pip install` from CodeArtifact | ~5KB metadata + ~15KB wheel |
| Re-run install of same version | `pip install` no-ops via local cache | 0 |
| Registry has v0.2.0, local has v0.1.0 | search + `pip install --upgrade` | metadata + delta |

This is why "every Claude Code session calls the Registry" is fine.
The calls are KB-sized metadata lookups, not artifact transfers.

## Repository layout

```
.
├── README.md                          # this file
├── docs/
│   ├── 01-why-private-skills.md            # the enterprise case (Day-1 framing)
│   ├── 02-architecture.md                  # service mapping + diagrams
│   ├── 03-demo-walkthrough.md              # the 4-script flow with timings
│   ├── 04-dynamic-discovery.md             # MCP endpoint: how Claude Code finds skills
│   ├── 05-auth-placeholder.md              # IAM today, JWT/OIDC TODO
│   ├── 06-future-optimizations.md          # cross-account, KMS CMK, EventBridge, OCI
│   ├── 07-extending-to-other-resources.md  # MCP, KBs, Lambda tools, guardrails, etc.
│   ├── 08-publishing-workflow.md           # author-facing: how to publish your own skill
│   └── 09-publishing-iam.md                # platform-team-facing: 4-tier IAM policies
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
├── skills/                            # blueprint-bundled meta-skill
│   └── publish-skill/                 # the skill that publishes other skills
│       ├── SKILL.md
│       ├── resources/publish-skill-runbook.md
│       └── scripts/publish.py
├── scripts/                           # boto3 publish/approve/consume (Day-1)
│   ├── 01_create_registry.py
│   ├── 02_register_skill.py
│   ├── 03_approve_skill.py
│   └── 04_consume_skill.py
└── examples/                          # Day-N extension placeholders
    ├── mcp-server/
    ├── knowledge-base/
    ├── lambda-tool/
    └── guardrail/
```

## Status of each section

Day-1 (Skills, end-to-end):

| Section | Status |
|---|---|
| CodeArtifact + Agent Registry CDK | ✅ Working |
| `aws-cost-anomaly-triage` example skill | ✅ Working |
| Publish + approve + consume scripts | ✅ Tested end-to-end |
| MCP endpoint dynamic discovery | ✅ Documented; client config example |
| IAM auth | ✅ Working |
| `publish-skill` meta-skill (parameterized publisher + 4-tier IAM) | ✅ Script preflight verified; docs/08+09 written |

Day-N extensions:

| Section | Status |
|---|---|
| MCP server records (`descriptorType: MCP`) | 📘 Documented in `07-extending` + `examples/mcp-server/` placeholder |
| Knowledge Base records (CUSTOM) | 📘 Documented in `07-extending` + `examples/knowledge-base/` placeholder |
| Lambda tool records (CUSTOM) | 📘 Documented in `07-extending` + `examples/lambda-tool/` placeholder |
| Bedrock Guardrails records (CUSTOM) | 📘 Documented in `07-extending` + `examples/guardrail/` placeholder |
| JWT/OIDC auth (Cognito/Okta) | 🔶 Phase 2 — see `docs/05-auth-placeholder.md` |
| Cross-account consumption | 🔶 Phase 2 |
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
PyPI-via-CodeArtifact is the recommended artifact backend for
text-and-script skills, IAM auth is the day-1 path, JWT/OIDC is the
day-2 path, and the registry is the right home for every governable
AI resource type — not just skills. Disagreements welcome — file an
issue.

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
