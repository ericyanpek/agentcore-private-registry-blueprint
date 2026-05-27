# Future optimizations — roadmap and placeholders

This is the "what we'd build next if this PoC graduates" page.
Items are loosely ordered by ROI for a typical enterprise rollout.

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

Trigger: `Skill record submitted for approval` event.
Action: post interactive Slack message with Approve/Reject buttons.
On click: Lambda calls `UpdateRegistryRecordStatus`.

Removes the need for curators to log into the AWS console for
approvals.

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

### Cross-registry federation

> "search across multiple registries as one"
> — *AWS Launch blog (2026-04-09)*

Today, a `SearchRegistryRecords` call accepts exactly one
`registryId`. The blueprint's "central registry, multi-account
consumers" pattern (above) handles cross-account *consumption* but
not cross-registry *search*. AWS-shipped federation would replace
the client-side fan-out workaround.

Implication for this blueprint: the multi-account fan-out section
above is a transitional pattern. Build it minimally; don't invest
heavily in client-side aggregation logic that a managed federation
will obsolete.

### Auto-indexing on deploy

> "automatic indexing of agents the moment they deploy"

For agents and MCP servers running on AgentCore Runtime / Gateway,
AWS plans to surface them in the registry without an explicit
`CreateRegistryRecord` call. URL-based discovery (already shipped
for `MCP` / `A2A`) is the precursor to this — it's the same
mechanism, just initiated by the Registry team's catalog rather than
by the publisher.

Implication: `AGENT_SKILLS` records — being PyPI-backed and not tied
to a runtime — will likely **continue to require explicit
publishing**. So the `publish-skill` meta-skill and the IAM model
behind it stay relevant; the auto-indexing future doesn't
invalidate them, just narrows them to the skill case.

### Observability data flowing into records

> "operational data from AgentCore Observability — invocation
> counts, latency, uptime, usage patterns — directly into registry
> records"

When this lands, `search_registry_records` results will carry
freshness/popularity signals. Search ranking can use them; deprecation
decisions can use them ("this record has zero invocations in 90
days"); curators can stop relying on out-of-band dashboards.

Implication: the "Telemetry feedback loop" item further down is no
longer something we'd build — wait for AWS to ship it natively.
Custom OTEL plumbing for the same purpose becomes redundant work.

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
