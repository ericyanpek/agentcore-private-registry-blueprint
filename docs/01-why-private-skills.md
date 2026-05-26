# Why private, governed Agent Skills are an enterprise problem

> If you can already articulate why this matters to your team,
> [skip to the architecture](./02-architecture.md). This page is
> for the conversation with stakeholders who haven't connected the
> dots yet.

## Skills are not prompts

A skill is a directory with a `SKILL.md` (frontmatter + body) and
optional resources, **executed by an AI agent without further human
translation**. The agent reads the description, decides "this applies",
and follows the steps in the body — invoking tools, calling APIs, and
producing decisions.

That last sentence is the whole story. Skills sit at the boundary
where natural-language SOPs become **executable instructions an agent
will run on production data**.

## What that makes them, in business terms

| If you have a skill for... | The skill encodes... |
|---|---|
| Financial analysis / pitchbook generation | Internal margin conventions, customer tiering, modeling methodology |
| Cost anomaly triage (this repo's example) | Internal thresholds, escalation paths, "do not touch" guardrails |
| Compliance review | Regulator-specific checklists, judgment calls, sign-off rules |
| Strategic planning | OKR conventions, competitive intel sources, scenario weights |
| Data discovery | Schema paths, metric definitions, dashboard URLs, "trusted vs raw" tags |
| Risk / fraud scoring | Decision rules, threshold tunings, exception conditions |
| HR review | Comp band logic, performance calibration rubrics |
| Incident response | Severity matrices, paging escalations, customer-comms templates |

These are **trade secrets, regulated artifacts, or organizational
muscle memory** — none of them are appropriate for public marketplaces
or public GitHub.

## Three concrete failure modes if you don't govern

### 1. Leakage equals competitive damage

A leaked SKILL.md isn't like a leaked design doc — it's a direct,
runnable instruction set. A competitor's Claude Code instance,
fed your skill, executes the same way your team does the next
afternoon. **The cost of catching up to your methodology drops by
an order of magnitude.**

### 2. Compliance failure is provable

Regulators in financial services (MAS, HKMA, PBOC), healthcare
(HIPAA), and increasingly under the EU AI Act treat
agent-executable instructions as auditable artifacts. You will be
asked:

- Who authored this skill?
- When was it modified, and by whom?
- What review approved this version for production?
- Where is the immutable record of that approval?

If your skills live in a personal `~/.claude/skills/` or a Slack
DM'd zip file, **you cannot answer any of these.** A registered
record with a `recordVersion`, an `approvedBy`, a CloudTrail event,
and an immutable `assets[].sha256` lets you answer all of them.

### 3. Sprawl breaks reuse

The non-compliance reason: in any org with 50+ skills, finding
"is there a skill for X" becomes its own job. Every team
re-implementing PII redaction differently, or three slightly
different cost-triage skills competing for the same trigger
description, creates exactly the kind of friction skills are
supposed to remove. **A registry with semantic search and an
approval workflow is what stops this.**

## Why GitHub Enterprise is *almost* enough but not quite

A common pushback: "we already have private GitHub with CODEOWNERS
and branch protection, isn't that the registry?"

It's most of it. Where it falls short:

| Need | GitHub Enterprise | Agent Registry |
|---|---|---|
| Versioned artifact storage | ✅ git tags | ✅ recordVersion + immutable PyPI versions |
| Code review / approval gates | ✅ PR review | ✅ submit-for-approval + curator workflow |
| RBAC | ✅ team permissions | ✅ IAM / JWT |
| Audit trail | ✅ git log + audit log | ✅ CloudTrail (richer than git log for non-content actions) |
| **Semantic search across skills** | ❌ exact-string only | ✅ hybrid keyword + semantic |
| **Agents themselves can query** | ❌ no MCP endpoint | ✅ Registry exposes MCP endpoint, Claude Code/Cursor can directly search |
| **Cross-resource discovery** (skills + MCP tools + agents in one search) | ❌ separate repos | ✅ unified index |
| **Schema validation at publish time** | 🔶 only via custom CI | ✅ enforced server-side |

For a 5-skill, single-team scenario, GitHub is fine. For the
50-skill, multi-team, "agent itself searches the catalog" scenario,
the registry's MCP endpoint and unified search become the
deciding capability.

## What public marketplaces give you that you don't want

Anthropic's claude.ai skills marketplace, plus community sites like
`skills.sh`, `awesomeskill.ai`, `awesomeclaude.ai`, work great for
public skills. They are **not built for**:

- Skills that should never leave a VPC
- Skills tied to internal endpoints or schemas
- Skills with org-specific compliance requirements
- Skills that need approval by an internal curator before anyone in the org can use them

The architectural choice in this blueprint is: **public skills can
still be installed by reference; private skills live entirely in
your AWS account, never on a public registry.**

## The "but it's just markdown" objection

> "It's just text. Why all the infrastructure for text files?"

Two answers:

1. **It's text that an AI agent will execute, on production data,
   without re-asking the human.** The category of artifact is
   closer to a Lambda deployment than to a Confluence page. We
   already have governance for Lambda code. Same logic applies.

2. **Resource files matter as much as the SKILL.md.** Most real
   skills ship a `resources/` directory: query templates, decision
   trees, threshold lookups, post-mortem templates. Those are
   versioned alongside the skill. `pip install
   aws-cost-anomaly-triage==0.1.0` gives you exactly the
   `confounders.md` that was approved for that version. Drift is
   prevented by version pinning, not by hope.

## The conversation this enables

When a stakeholder says "we need to start using AI agents for
[serious thing]", the right SA response is no longer:

> "Sure, here are some MCP server examples."

It's:

> "Before any of that — where will your operational SOPs live, who
> can publish them, who approves them, and how does the agent find
> them? Let's set up the registry first."

That conversation is what this repo enables you to have.

→ Next: [the architecture](./02-architecture.md)
