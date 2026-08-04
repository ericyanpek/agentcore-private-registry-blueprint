# Future optimizations — roadmap and placeholders

This is the "what we'd build next if this PoC graduates" page.
Items are loosely ordered by ROI for a typical enterprise rollout.

## Scoreboard — what AWS shipped since this roadmap was written

*Reviewed 2026-08-04 against the current service documentation.*

This page was written during the 2026-04 preview. Several items have since
been **shipped natively by AWS**, which is the good outcome: this repo's
job is to be a thin layer over the managed service, so every row that
moves to "AWS ships it" is custom plumbing the blueprint no longer has to
carry.

| Roadmap item | Judgment then | Official status now | What changes here |
|---|---|---|---|
| EventBridge → approval pipeline | 🔶 Phase 2 — build the event source + Lambda ourselves | ✅ **Shipped.** Registry emits an EventBridge event to the default bus when a record is submitted for approval; route to Lambda / SNS / SQS / Step Functions, then call `UpdateRegistryRecordStatus` | Stop planning an event *source*. Only the Slack-formatting Lambda remains ours |
| Direct JWT on the Registry MCP endpoint | 🔶 Phase 2 — non-Cognito IdPs "still pending" | ✅ **Shipped.** Cognito, Okta, Microsoft Entra ID, or any OAuth 2.0 provider; developers and agents search + invoke MCP with corporate credentials, no individual IAM | Demote from "missing capability" to "CDK ergonomics" — the capability exists, only our construct is missing |
| Auto-indexing on deploy | 🔶 Predicted — "URL discovery is the precursor" | 🟡 **Partially shipped as record synchronization.** A URL-configured record re-fetches server + tool metadata from the live endpoint and creates a **new revision**; supports OAuth *and* IAM credential providers | Prediction held. Still publisher-initiated, not runtime-initiated |
| Cross-registry federation | 🔶 Predicted — would obsolete client-side fan-out | ❌ **Not shipped.** `registryIds` is list-shaped, but the API reference states you may specify exactly one identifier | Judgment unchanged, now doc-confirmed. Keep multi-account fan-out minimal |
| Observability data in records | 🔶 Predicted — "wait for AWS, don't build OTEL plumbing" | ❌ **Not shipped.** No record-level invocation / latency fields in the current API | Judgment unchanged. Continue to not build it |
| Metadata search filters | ⬜ Wasn't on the roadmap | ✅ **Shipped.** `filters` on `SearchRegistryRecords` with `$eq` / `$ne` / `$in` / `$and` / `$or` over `name`, `descriptorType`, `version` | A capability we didn't anticipate and should adopt — see below |

**One item now outranks everything else on this page**: AWS Agent Registry
reaches GA on **2026-08-06** and moves from the `bedrock-agentcore`
namespace to `agent-registry`, with a restructured API schema. The old
namespace shuts down **2026-09-17**. Every script and IAM policy in this
repo targets the preview namespace.

Two adjacent launches reframe this blueprint's *positioning* without
touching its architecture: **AgentCore harness** went GA 2026-06-17
(config-defined agents with access to an AWS-curated skill catalog), and
**Agent Toolkit for AWS** launched 2026-05-06 as the successor to the AWS
Labs MCP servers / skills / plugins. Both are the official answer for
*public, AWS-authored* skill distribution — which sharpens rather than
undercuts the case here: **private** skill distribution still has no
official AWS sample.

## GA migration — the blocking item

Not an optimization; a hard deadline. Tracked on this page because it
gates everything else on it.

| | Preview (this repo today) | GA |
|---|---|---|
| IAM action prefix | `bedrock-agentcore:*` | `agent-registry:*` |
| Service principal | `bedrock-agentcore.amazonaws.com` | `agent-registry.amazonaws.com` |
| API schema | preview shape | restructured registry + record data model |
| Data | in the old namespace | must be moved with the AWS-provided migration script |

Timeline: **2026-08-06** GA, both namespaces accessible simultaneously,
migration tooling lands in the `agentcore-samples` GitHub repo →
**2026-09-17** the old namespace loses read *and* write access.

The trap specific to a public blueprint: accounts with **no** existing
registries as of 2026-08-06 cannot access the `bedrock-agentcore`
namespace at all. A reader cloning this repo after that date will have
`boto3.client("bedrock-agentcore-control")` fail outright — the demo does
not degrade gracefully, it simply doesn't run.

Work required: client construction in `scripts/*.py` plus every
`create_registry` / `create_registry_record` /
`update_registry_record_status` call re-verified against the new schema;
IAM policies in `cdk/lib/*.ts` re-prefixed; the four-tier policy JSON in
`docs/09` and the read-only audit policy in `docs/05` re-prefixed.

## Near-term (next 1-3 sprints)

### CI/CD — publish-on-merge via GitHub Actions

Current state: skills are published manually with `twine` and
registered with `02_register_skill.py` from a developer laptop.

Target state:

```yaml
# .github/workflows/publish-skill.yml (sketch)
name: Publish skill
on:
  push:
    branches: [main]
    paths: ['skills/**']
permissions:
  id-token: write   # OIDC to AWS
  contents: read
jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::<central>:role/GHA-SkillPublisher
          aws-region: us-east-1
      - run: python -m build
      - run: aws codeartifact login --tool twine --domain skills-demo --repository skills-prod
      - run: twine upload --repository codeartifact dist/*
      - run: python scripts/register-skill-from-pyproject.py
```

The `register-skill-from-pyproject.py` would parse `pyproject.toml`
to derive the record name + version, lift the SKILL.md into
`skillMd.inlineContent`, and call `CreateRegistryRecord`.

### Skill scaffolding CLI (`skill init`)

A small `skill` CLI that:

```
skill init my-new-skill          # creates pyproject.toml + SKILL.md skeleton
skill validate                    # lints SKILL.md frontmatter against the spec
skill publish                     # build + twine + register-record + submit-for-approval
skill deprecate <name> <version>  # marks a record DEPRECATED
```

This removes the per-skill boilerplate that's currently copy-pasted
from the example.

### S3-backed sibling track for non-Python skills

Some skills don't fit the Python wheel format — large binary
resources, mixed-language assets, OCI-style layered content. The
sibling pattern:

| | Python skills (this blueprint) | S3 skills (Phase 2) |
|---|---|---|
| Backend | CodeArtifact PyPI | S3 with Object Lock |
| Schema reference | `skillDefinition.packages[pypi]` | `_meta.com.example.s3Uri` |
| Consumer | `pip install` | SDK GetObject + presigned URL |
| Versioning | PyPI immutable | S3 Versioning + Object Lock Compliance |

The Agent Registry record format is identical; only the artifact
backend differs.

### EventBridge → Slack approval bot

> **Status update (2026-08-04): the hard half of this shipped.** When
> this section was written, "trigger on submitted-for-approval" was an
> assumption about a service that might emit such an event. It now does:
> AWS Agent Registry publishes to the **default EventBridge bus** in your
> account and Region when a record is submitted for approval, and the
> event can be routed to any EventBridge target (Lambda, SNS, SQS, Step
> Functions). AWS documents this explicitly as the integration point for
> plugging the registry into an organization's existing review process —
> security reviews, compliance checks, ticketing — with the pipeline
> calling `UpdateRegistryRecordStatus` when its checks pass.

What this changes: the original framing was "build an approval event
pipeline." The correct framing is now "**consume** the approval event."
The event source, delivery, and the status-mutation API are all managed;
the only custom code left is the Slack interactive-message formatting and
the callback handler.

Remaining scope for this repo:

- A rule on the default bus filtering registry approval-submission events
- Lambda: format an interactive Slack message with Approve / Reject
- Lambda: on button click, call `UpdateRegistryRecordStatus` under a
  service role (keeping separation of duties — the bot's role is the
  Curator, and per `docs/09` the Publisher still cannot approve its own
  record)

The broader point for anyone adapting this blueprint: if your org already
has an approval mechanism, **do not** rebuild it as a Slack bot. Point the
EventBridge rule at the pipeline you already have and let it call
`UpdateRegistryRecordStatus`. Slack is the demo-friendly choice, not the
recommended one.

One operational caveat when wiring this up: search indexing is eventually
consistent. After `UpdateRegistryRecordStatus` returns APPROVED, the
record typically takes seconds — occasionally minutes — to appear in
`SearchRegistryRecords` or `InvokeRegistryMcp`. Downstream steps that
verify by searching need a delay or a `GetRegistryRecord` check instead.

### Adopt metadata search filters

Not on the original roadmap — this capability wasn't anticipated. The
`SearchRegistryRecords` API takes a `filters` document supporting
`$eq` / `$ne` / `$in` and `$and` / `$or` over the filterable fields
`name`, `descriptorType`, and `version`:

```python
resp = data.search_registry_records(
    registryIds=[arn],
    searchQuery="cost anomaly",
    filters={"descriptorType": {"$eq": "AGENT_SKILLS"}},
    maxResults=5,
)
```

Direct payoff for `04_consume_skill.py`, which currently searches, then
filters `descriptorType == "AGENT_SKILLS"` in Python after the fact. That
client-side filter competes with `maxResults` — non-skill records consume
result slots before the client ever sees them. Pushing the predicate into
the API removes the bug class entirely.

This matters more as a registry fills up with the four coexisting
descriptor types that `docs/07` advocates: once one registry holds MCP
servers, agents, skills, and custom resources, a skill consumer that
can't filter server-side is reading a mostly-irrelevant result set.

## Mid-term (next quarter)

### Multi-account fan-out

Common org shape:

```
                 ┌─── workload-acct-a ──── consumers (Claude Code, Bedrock agents)
central-acct ────┤
(registry +      └─── workload-acct-b ──── consumers
 CodeArtifact)   └─── workload-acct-c ──── consumers
```

Required pieces:
- CodeArtifact resource policy granting consumer accounts read access
- Cross-account `bedrock-agentcore:SearchRegistryRecords` permission
- Optional: replicate the registry to each region with an
  EventBridge-driven sync

### Customer-managed KMS + key rotation

For compliance regimes that mandate it. Includes:
- CMK with annual rotation
- Per-domain key (not per-bucket)
- Key access audit via CloudTrail Lake query templates

### Read replicas in additional regions

Agent Registry preview is in 5 regions. For latency-sensitive
consumers (or data residency), provisioning a registry per region
and synchronizing records via EventBridge is a known pattern.

### Skill content scanning

Pipeline to run `cisco-ai-skill-scanner` (LLM-driven) +
`agnix` (SKILL.md linter) before approval. Wire as an EventBridge
target on `PENDING_APPROVAL`.

## Longer-term (when standards stabilize)

### OCI artifact distribution

The agentskills community is actively designing **OCI as the
canonical skill packaging format** (see agentskills/agentskills
Discussion #292). Benefits over PyPI:
- Native digest pinning, signing (cosign), SBOM attachments
- Layered content (skill bundle + resources + scripts as separate layers)
- Fits any private container registry (ECR, Harbor, etc.)
- Inspectable without execution

When AWS Agent Registry adds `registryType: oci` to the
`skillDefinition.packages[]` enum, this blueprint should grow an
OCI variant alongside the PyPI variant.

### Skill execution sandbox tie-in

Right now, "activation" = "copy file to `~/.claude/skills/`". The
agent runtime decides whether to execute scripts inside the skill.

Bedrock AgentCore Runtime offers a sandbox profile for skill
execution. Future state: a registry record can reference the
required sandbox configuration (network access, allowed file system
paths) via `_meta.com.example.runtime`. The runtime then enforces
that profile on activation.

### Telemetry feedback loop

Every consumer install + invocation could emit an OpenTelemetry
span. Aggregated:
- "this skill is invoked 1000x/week" — promote to default
- "this skill is never invoked" — review for deprecation
- "this skill triggers wrong" — feedback to the author for description tuning

OTEL hookpoint exists already (Bedrock AgentCore emits OTEL).
The wiring + dashboard is the missing piece.

> Note: AWS has publicly announced that observability data
> (invocation counts, latency, usage patterns) will flow directly
> into registry records — see the *AWS-announced roadmap items*
> section above. If you're considering this, wait for AWS to ship
> it natively rather than building a custom OTEL aggregator that
> duplicates the future managed feature.

### Inter-skill dependency model

Today, a skill can declare PyPI dependencies via `pyproject.toml`,
but it cannot declare "I depend on the `aws-base-context` skill
being installed first." A real dependency graph between skills is
a known unsolved problem in the agent skills community.

## Operational guardrails worth pre-planning

### Service quotas — `SearchRegistryRecords` defaults to 5 TPS

The blueprint advocates a discovery model where every Claude Code
prompt may call `search_registry_records`. That works at small
scale, but the **preview default for `SearchRegistryRecords` and
`InvokeRegistryMcp` is 5 TPS per account, region-wide** ([service
quotas reference](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html)).
For a 100-developer IDE rollout where each session opens with a
search, that's the first thing you'll hit.

Both quotas are adjustable via Service Quotas console. Two things to
do before going wide:

1. Submit a quota increase request **per region** for each of:
   `SearchRegistryRecords`, `InvokeRegistryMcp`,
   `CreateRegistryRecord`, `UpdateRegistryRecordStatus`.
2. Add client-side caching on the consumer side. Search results are
   metadata (a few KB per record) and APPROVED records are
   eventually consistent anyway; a 60-90s TTL on the search response
   eliminates the pathological "every prompt re-searches identically"
   pattern without compromising freshness.

Backfill jobs (importing existing assets into a new registry) bump
into the **CreateRegistryRecord 5 TPS** ceiling fast. Throttle from
the client (e.g., a token bucket at 4 TPS) — it's cheaper than
asking for a quota that you'll only need for one afternoon.

## AWS-announced roadmap items (track these)

These were called out in the AWS launch announcements and the
service team's public talks. They aren't in the service today, but
they're real enough to plan around — when they ship, they may
deprecate or simplify pieces of the Phase 2 list above.

> **Re-checked 2026-08-04.** Of the three items in this section, one
> partially shipped (auto-indexing, as record synchronization) and two
> remain unshipped. The two that remain are the two where the roadmap's
> advice was "don't build it yourself" — so that advice still stands, and
> is now backed by a second reading of the API surface rather than a
> single-point-in-time guess.

### Cross-registry federation

> "search across multiple registries as one"
> — *AWS Launch blog (2026-04-09)*

**Status: not shipped as of 2026-08-04 — and the API now says so
explicitly.**

The original claim here was that `SearchRegistryRecords` accepts exactly
one `registryId`. This is worth restating precisely, because the API's
shape invites the opposite conclusion: the parameter is named
`registryIds` and is typed as a **list**, but the API reference and every
SDK binding carry the same constraint — *"Currently, you can specify
exactly one registry identifier."* The plural signature is forward
capacity for federation, not present capability.

Practical consequence: `scripts/04_consume_skill.py` passes a list built
from all READY registries. With one registry that works; with two it will
fail validation rather than silently searching one. Anyone extending this
blueprint to multiple registries needs a client-side loop, not a longer
list.

Judgment unchanged, and the reasoning is now firmer rather than merely
still-true: the multi-account fan-out section above remains a transitional
pattern. Build it minimally. Don't invest in client-side aggregation logic
that a managed federation will obsolete — the list-shaped parameter is a
fairly direct signal about where the service team intends to go.

### Auto-indexing on deploy

> "automatic indexing of agents the moment they deploy"

**Status: partially shipped as record synchronization (2026-08-04).**

The prediction in this section was that URL-based discovery was the
precursor to auto-indexing — the same mechanism, differing only in who
initiates it. That held up. What shipped is **record synchronization**:
configure a record with a URL pointing at an external MCP server and the
Registry fetches current server metadata (name, description) and tool
metadata (tool names, tool descriptions) from that URL. Synchronization
works both for creating a record initially and for refreshing an existing
one, and a refresh **creates a new revision** rather than mutating in
place. Authorization supports both OAuth and IAM credential providers.

So the staleness problem the original prediction cared about is solved for
URL-addressable resources: an `MCP` record no longer drifts from the
server it describes. What has *not* shipped is the runtime-initiated half
— deploying to AgentCore Runtime still does not create a record for you.
Synchronization keeps a record fresh; it does not bring a record into
existence unprompted.

The judgment about skills was correct and is now firmer: `AGENT_SKILLS`
records are PyPI-backed and have no live endpoint to synchronize against,
so **there is nothing for synchronization to poll**. Skills require
explicit publishing, which means the `publish-skill` meta-skill and the
four-tier IAM model behind it stay load-bearing indefinitely rather than
transitionally.

This produces a genuine architectural split worth stating plainly, since
it cuts against the "all four descriptor types are equal" framing in
`docs/07`:

| | `MCP` / `A2A` records | `AGENT_SKILLS` records |
|---|---|---|
| Metadata source | live endpoint, synchronized by AWS | wheel + `SKILL.md`, pushed by publisher |
| Freshness | managed, revision per sync | publisher's responsibility |
| Drift risk | low | real — record and wheel can disagree |
| Governance leverage | approval workflow | approval workflow **+** artifact immutability |

The four types are equal as *catalog entries* and unequal in *lifecycle*.
A future blueprint iteration should close the skill-side gap — a CI check
that the registered `skillMd.inlineContent` still matches the published
wheel's `SKILL.md` is the skill-shaped analogue of synchronization, and
this repo doesn't have one.

### Observability data flowing into records

> "operational data from AgentCore Observability — invocation
> counts, latency, uptime, usage patterns — directly into registry
> records"

**Status: not shipped as of 2026-08-04.** The `SearchRegistryRecords`
response carries `name`, `description`, `descriptorType`, `descriptors`,
`version`, `status`, `createdAt`, `updatedAt` — no invocation counts, no
latency, no usage signals. Filterable fields are limited to `name`,
`descriptorType`, and `version`.

When this lands, `search_registry_records` results will carry
freshness/popularity signals. Search ranking can use them; deprecation
decisions can use them ("this record has zero invocations in 90
days"); curators can stop relying on out-of-band dashboards.

Implication: the "Telemetry feedback loop" item further down is no
longer something we'd build — wait for AWS to ship it natively.
Custom OTEL plumbing for the same purpose becomes redundant work.

This is the roadmap's most consequential *non*-recommendation, so it's
worth noting it has now survived four months without being invalidated.
The advice was to not build an OTEL aggregator; had we built one in
2026-04, it would still be unreplaced today — which is the honest way to
frame it. "Wait for AWS" was the right call, but it has cost four months
of not having the capability at all. A team that genuinely needs
usage-based deprecation decisions *now* should weigh that tradeoff
explicitly rather than reading this section as "the feature is coming
soon."

## Items explicitly NOT in scope

- A self-hosted alternative to Agent Registry. iflytek's SkillHub
  is the cautionary tale; the AWS managed service is the right
  abstraction layer for this concern.
- A new SKILL.md format. The existing spec is sufficient.
- A consumer-side runtime that's not Claude Code / Bedrock
  AgentCore Runtime. The blueprint's activation step is generic
  enough that any agent that reads `~/.claude/skills/` works.

## How to contribute

If you've built one of the items above and want it merged into
this blueprint, open a PR with:
- A working CDK module under `cdk/lib/`
- A doc page under `docs/` cross-referenced from the README status
  table
- Either an automated test or a manual verification log

→ Next: [extending to other resources](./07-extending-to-other-resources.md)
