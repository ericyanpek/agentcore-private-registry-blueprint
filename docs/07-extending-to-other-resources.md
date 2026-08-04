# Beyond skills — the registry as a unified AI resource catalog

> The Day-1 demo registers a skill. This page is what to do on Day 2,
> Day 30, Day 365 — when your org's catalog grows past skills.

## Why one registry for everything

Most enterprises hit this realization in roughly this order:

1. We need a place to share **skills** (this blueprint's Day-1 demo)
2. The platform team has a half-dozen useful **MCP servers** we want to publish; do those go in the same place? **(Yes)**
3. Marketing wants to register the **knowledge bases** their RAG agents use; should we put those somewhere different? **(No — same registry, `descriptorType: CUSTOM`)**
4. Security wants to audit which **Bedrock Guardrails** are referenced by which agents; can we attach guardrails to the registry? **(Yes — CUSTOM again)**
5. SRE wants to register their **incident response Step Functions** so on-call agents can invoke them; same place? **(Yes — CUSTOM)**

The principle: **if it's a governable AI resource that humans or
agents need to discover, publish it to the registry**. The registry
already gives you search, approval workflow, version pinning,
CloudTrail audit, MCP-endpoint discovery — there's no good reason to
build separate catalogs.

## Native types vs. CUSTOM

Two categories.

**Native** types get server-side schema validation:

| `descriptorType` | Schema | When to use |
|---|---|---|
| `AGENT_SKILLS` | SKILL.md + skillDefinition v0.1.0 | A reusable SOP / methodology |
| `MCP` | MCP server.json open spec | An MCP server you've stood up (in AgentCore Runtime, Lambda, ECS, or third-party host) |
| `A2A` | Google A2A Agent Card | An agent that speaks A2A protocol |

### MCP and A2A records get URL-based discovery for free

For `MCP` and `A2A` records there is a second registration path
that the Day-1 demo doesn't use but is the right answer for most
in-house MCP servers and A2A agents: instead of submitting a JSON
body, you submit a **URL**. The Registry fetches the server.json /
agent card itself, validates it, and produces a record from it. When
the source endpoint's metadata changes, the Registry re-syncs and
emits a new revision — no manual update.

```python
client.create_registry_record(
    registryId=rid,
    name="example-mcp",
    descriptorType="MCP",
    recordVersion="1.0.0",
    synchronizationType="URL",
    synchronizationConfiguration={
        "fromUrl": {
            "url": "https://mcp.example.internal/v1/.well-known/mcp/server-card.json",
            # Optional — for sources behind OAuth2:
            # "credentialProviderConfigurations": [{
            #     "credentialProviderType": "OAUTH",
            #     "credentialProvider": {"oauthCredentialProvider": {
            #         "providerArn": "<AgentCore Identity provider ARN>",
            #         "grantType": "CLIENT_CREDENTIALS"
            #     }}
            # }]
        }
    },
)
```

**Why this matters for org rollout**: under URL discovery, the team
that operates an MCP server **does not need to write any publish
pipeline**. They expose a well-known endpoint with appropriate ACLs;
the Registry keeps itself fresh. Compare to AGENT_SKILLS records,
which always require an explicit publish step (`twine upload` +
`CreateRegistryRecord`) because the artifact backend (CodeArtifact)
is separate from the metadata source.

| | Path A — inline JSON | Path B — URL sync |
|---|---|---|
| Source of truth | The JSON you submitted | Live MCP/A2A endpoint |
| Drift handling | Manual `update-registry-record` | Automatic re-sync, new revision |
| Auth on fetch | N/A | Public, IAM-signed, or OAuth2 (via AgentCore Identity credential provider) |
| Best for | Third-party MCP, fixed snapshots, air-gapped publishing | In-house MCP/A2A, anything iterating frequently |
| Server team writes publish code? | Yes (one-time inline JSON) | No |

A working URL-sync example lives at
[`examples/mcp-server/register-url-sync.py`](../examples/mcp-server/register-url-sync.py).
URL discovery does **not** apply to `AGENT_SKILLS` or `CUSTOM`
records — the Registry has nothing to fetch in those cases.

**CUSTOM** is the escape hatch:

| Resource | Why register it | Owner persona |
|---|---|---|
| Bedrock Knowledge Base | Discoverable RAG sources | Data / ML team |
| Lambda function as tool | Single-function tool, simpler than building an MCP server | Backend team |
| Bedrock Guardrails | Reusable safety/PII configs | Security |
| Cedar policy bundle (AgentCore Policy) | Reusable agent permission bundles | Security / Platform |
| Step Functions state machine | Workflow that's complex enough not to inline | SRE / Ops |
| API (REST/GraphQL) | Internal API exposed for agents | API owner team |
| Database / data product | "Things agents are allowed to query" | Data team |
| Eval / golden dataset | Pre-launch regression sets | ML / QA |
| SageMaker endpoint | Private model as agent tool | ML platform |
| Prompt template / prompt card | Sub-skill granularity prompt assets | Any team |
| Schema (OpenAPI / JSON Schema / Avro) | Data contracts agents need to comply with | Data / Platform |
| Code Interpreter sandbox profile | Reusable sandbox configs | Platform |
| Embedding model endpoint | Which embedding model to use for which task | ML platform |

## CUSTOM record schema convention (recommended)

The registry validates `CUSTOM` records as "any valid JSON". Without
discipline this becomes mush. Use this convention for every CUSTOM
record:

```jsonc
{
  // top-level: short, human-relevant identification
  "kind": "knowledge-base",
  "kindVersion": "1.0.0",
  "displayName": "Product FAQ KB v3",

  // pointer: where the actual resource lives
  "target": {
    "service": "bedrock",
    "resourceType": "KnowledgeBase",
    "arn": "arn:aws:bedrock:us-east-1:111122223333:knowledge-base/ABC123",
    "region": "us-east-1"
  },

  // governance metadata
  "owner": {
    "team": "Marketing-RAG",
    "contact": "marketing-rag@example.internal",
    "slack": "#marketing-rag"
  },

  // resource-specific properties
  "spec": {
    "embeddingModel": "amazon.titan-embed-text-v2",
    "vectorStore": "OpenSearch Serverless",
    "documentCount": 4218,
    "lastIngested": "2026-05-01"
  },

  // extension fields for activation/usage hints
  "_meta": {
    "com.example.invocation": {
      "guidance": "Use for product/pricing questions only; not for engineering specs",
      "exampleQuery": "What's the upgrade path for tier-2 customers?"
    }
  }
}
```

Replace `com.example` with your reversed corporate domain. Keep `kind`
values stable — clients filter on them (`filter: {kind: {$eq:
"knowledge-base"}}` returns all KBs).

## Worked example — "customer-care" registry

This is what a real registry looks like 6-12 months after a
medium-sized company adopts the pattern. **18 records, 4 descriptor
types, 8 owning teams, single registry.**

```
Registry: customer-care-prod                       (1 registry)
│
├─ AGENT_SKILLS  (3)                              ← these are SOPs
│  ├─ customer-tone-polish
│  ├─ refund-eligibility-triage
│  └─ case-summary-handoff
│
├─ A2A           (2)                              ← agents
│  ├─ customer-onboarding-agent
│  └─ escalation-router-agent
│
├─ MCP           (2)                              ← MCP servers / tools
│  ├─ salesforce-mcp                              (hosted on AgentCore Runtime)
│  └─ zendesk-mcp                                 (third-party HTTPS endpoint, URL-synced)
│
└─ CUSTOM        (11)                             ← everything else
   ├─ kind: knowledge-base
   │  ├─ product-faq-kb-v3                        (Bedrock KB)
   │  └─ 2026-policy-changes-kb                   (OpenSearch Serverless)
   │
   ├─ kind: lambda-tool
   │  ├─ credit-limit-lookup                      (Lambda)
   │  └─ loyalty-tier-recompute                   (Lambda)
   │
   ├─ kind: guardrail
   │  ├─ pii-strict-guardrail                     (Bedrock Guardrails)
   │  └─ refund-cap-guardrail
   │
   ├─ kind: cedar-policy
   │  ├─ tier-1-agent-permissions                 (Cedar bundle in S3)
   │  └─ after-hours-restrictions
   │
   ├─ kind: workflow
   │  └─ escalation-runbook-sm                    (Step Functions)
   │
   ├─ kind: eval-dataset
   │  └─ 1000-historical-tickets-golden           (S3 manifest)
   │
   └─ kind: schema
      └─ ticket-event-v3-schema                   (Avro / EventBridge Schema Registry)
```

A few useful observations from this layout:

- **Skills are 3 of 18 records.** The blueprint title `private-registry`
  matters more than `private-skills`.
- **The same approval workflow applies to all.** A new guardrail goes
  through the same DRAFT → PENDING_APPROVAL → APPROVED states as a
  new skill. The curator (probably security in this case) is
  different per `kind`, enforced by IAM Conditions on
  `bedrock-agentcore:UpdateRegistryRecordStatus`.
- **Search works across types.** "PII handling" surfaces both the
  `pii-strict-guardrail` and the `customer-tone-polish` skill. That
  cross-resource discovery is the registry's killer feature.

## Concrete CUSTOM record examples

Below are the actual JSON bodies for the most useful CUSTOM kinds.
Copy + adapt these when extending the blueprint to your environment.

### Knowledge Base (Bedrock KB or OpenSearch)

```json
{
  "kind": "knowledge-base",
  "kindVersion": "1.0.0",
  "displayName": "Product FAQ KB v3",
  "target": {
    "service": "bedrock",
    "resourceType": "KnowledgeBase",
    "arn": "arn:aws:bedrock:us-east-1:111122223333:knowledge-base/ABC123XYZ",
    "region": "us-east-1"
  },
  "owner": {
    "team": "Marketing-RAG",
    "contact": "marketing-rag@example.internal"
  },
  "spec": {
    "embeddingModel": "amazon.titan-embed-text-v2",
    "vectorStore": "OpenSearch Serverless",
    "documentCount": 4218,
    "lastIngested": "2026-05-01",
    "freshnessSlaHours": 24
  },
  "_meta": {
    "com.example.invocation": {
      "useFor": "Product/pricing questions only",
      "doNotUseFor": "Engineering specs, internal roadmap"
    }
  }
}
```

Two caveats on that example, since it is the one most likely to be
copy-pasted:

**`documentCount` and `lastIngested` will go stale immediately.** CUSTOM
records have no synchronization, so nothing refreshes them. Shown here to
illustrate a full `spec`, but for a real record either drop them or wire the
scheduled refresh described below. A stale number inside an *approved*
record is worse than an absent one — approval implies review.

**For AWS-managed Knowledge Bases, drop `embeddingModel` and
`vectorStore`.** Those are implementation details the service owns; hand-
copying them into a record creates a second source of truth that can
silently disagree with reality. Keep `spec` to facts you actually own —
data sources, refresh cadence, language, scope — and let `target.arn` be
the handle for anything live.

The `useFor` / `doNotUseFor` pair is the highest-value part of this record,
above everything in `spec`. A KB is *retrieved from*, not invoked, so the
only governance question that matters is which questions belong here — and
`_meta` plus `description` are the sole places to answer it.

### Lambda function as agent tool

```json
{
  "kind": "lambda-tool",
  "kindVersion": "1.0.0",
  "displayName": "credit-limit-lookup",
  "target": {
    "service": "lambda",
    "resourceType": "Function",
    "arn": "arn:aws:lambda:us-east-1:111122223333:function:credit-limit-lookup-prod",
    "region": "us-east-1",
    "alias": "PROD"
  },
  "owner": {
    "team": "Billing",
    "contact": "billing@example.internal"
  },
  "spec": {
    "inputSchema": {
      "type": "object",
      "properties": {"customerId": {"type": "string"}},
      "required": ["customerId"]
    },
    "outputSchema": {
      "type": "object",
      "properties": {
        "limit": {"type": "number"},
        "currency": {"type": "string"}
      }
    },
    "timeoutSeconds": 5,
    "rateLimitPerSecond": 100
  },
  "_meta": {
    "com.example.invocation": {
      "iamPrincipalRequired": "agent must assume CallerRole-CreditLookup"
    }
  }
}
```

### Bedrock Guardrails record

```json
{
  "kind": "guardrail",
  "kindVersion": "1.0.0",
  "displayName": "pii-strict-guardrail",
  "target": {
    "service": "bedrock",
    "resourceType": "Guardrail",
    "id": "abc123guardrailid",
    "version": "DRAFT",
    "region": "us-east-1"
  },
  "owner": {
    "team": "Security-AppSec",
    "contact": "appsec@example.internal"
  },
  "spec": {
    "blockedTopics": ["financial-advice", "legal-advice"],
    "piiEntities": ["SSN", "CREDIT_CARD", "EMAIL", "PHONE"],
    "applicableTo": ["customer-facing", "external-comm"],
    "regulatoryBasis": ["GDPR Art.5", "CCPA 1798.100"]
  }
}
```

### Cedar policy bundle (AgentCore Policy)

```json
{
  "kind": "cedar-policy",
  "kindVersion": "1.0.0",
  "displayName": "tier-1-agent-permissions",
  "target": {
    "service": "s3",
    "resourceType": "Object",
    "uri": "s3://example-policies/cedar/tier-1-v3.cedar",
    "sha256": "9af1...c0",
    "region": "us-east-1"
  },
  "owner": {
    "team": "Platform-Security",
    "contact": "platform-security@example.internal"
  },
  "spec": {
    "policyEngine": "AgentCore Policy",
    "appliesTo": "Tier-1 customer-facing agents",
    "principalRoleConditions": ["customer-tier == 'standard'"],
    "summary": "No refund > $500, no escalation past 2 hops"
  }
}
```

### Step Functions state machine

```json
{
  "kind": "workflow",
  "kindVersion": "1.0.0",
  "displayName": "escalation-runbook-sm",
  "target": {
    "service": "states",
    "resourceType": "StateMachine",
    "arn": "arn:aws:states:us-east-1:111122223333:stateMachine:escalation-runbook-prod",
    "region": "us-east-1"
  },
  "owner": {
    "team": "SRE",
    "contact": "sre-oncall@example.internal"
  },
  "spec": {
    "expressOrStandard": "EXPRESS",
    "averageDurationSeconds": 8,
    "retryStrategy": "exponential-backoff",
    "humanInTheLoop": false
  },
  "_meta": {
    "com.example.invocation": {
      "triggerCondition": "Severity 1 or sustained > 15min",
      "doNotInvokeFor": "Tier-3 customers (manual ack required)"
    }
  }
}
```

### Eval / golden dataset

```json
{
  "kind": "eval-dataset",
  "kindVersion": "1.0.0",
  "displayName": "1000-historical-tickets-golden",
  "target": {
    "service": "s3",
    "resourceType": "Manifest",
    "uri": "s3://example-eval-sets/customer-care/2026-Q2/manifest.jsonl",
    "sha256": "12af...88",
    "region": "us-east-1"
  },
  "owner": {
    "team": "QA-AI",
    "contact": "qa-ai@example.internal"
  },
  "spec": {
    "exampleCount": 1000,
    "labelType": "human-graded-3way",
    "harness": "AgentCore Evaluator",
    "regenCadence": "quarterly",
    "passingThreshold": 0.85
  }
}
```

### Schema (OpenAPI / JSON Schema / Avro)

```json
{
  "kind": "schema",
  "kindVersion": "1.0.0",
  "displayName": "ticket-event-v3-schema",
  "target": {
    "service": "events",
    "resourceType": "SchemaRegistry-Schema",
    "registryName": "customer-care",
    "schemaName": "ticket-event",
    "version": "3",
    "region": "us-east-1"
  },
  "owner": {
    "team": "Data-Platform",
    "contact": "data-platform@example.internal"
  },
  "spec": {
    "format": "Avro",
    "compatibility": "BACKWARD",
    "producedBy": ["zendesk-connector", "manual-entry-app"],
    "consumedBy": ["customer-care-prod agents"]
  }
}
```

## Registering a CUSTOM record (boto3)

The pattern is the same as the skill demo, just different
`descriptorType` and `descriptors`:

```python
import json
import boto3

client = boto3.client("bedrock-agentcore-control", region_name="us-east-1")

custom_body = {
    "kind": "knowledge-base",
    "kindVersion": "1.0.0",
    "displayName": "Product FAQ KB v3",
    # ... (see schema above)
}

resp = client.create_registry_record(
    registryId="<registryId>",
    name="product-faq-kb-v3",
    description="RAG knowledge base for product FAQ — 4200+ docs, daily refresh.",
    descriptorType="CUSTOM",
    descriptors={"custom": {"inlineContent": json.dumps(custom_body)}},
    recordVersion="3.0.0",
)
```

The rest of the lifecycle (DRAFT → submit → approve → discoverable
via search) is **identical** to skills. Curators filter the approval
queue by `kind` to route reviews to the right team.

## Discovery patterns by `kind`

Search filters compose neatly. Note the parameter is **`filters`**, plural
— verified against the SDK's own service model, where
`SearchRegistryRecords` takes `searchQuery`, `registryIds`, `maxResults`,
`filters`. Passing `filter=` raises `ParamValidationError`:

```python
# All knowledge bases the agent might use
data.search_registry_records(
    registryIds=arns,
    searchQuery="product knowledge",
    filters={"descriptorType": {"$eq": "CUSTOM"}},
)

# Only AGENT_SKILLS
data.search_registry_records(
    registryIds=arns, searchQuery="...",
    filters={"descriptorType": {"$eq": "AGENT_SKILLS"}},
)

# Skills OR MCP — exclude CUSTOM noise
data.search_registry_records(
    registryIds=arns, searchQuery="...",
    filters={"descriptorType": {"$in": ["AGENT_SKILLS", "MCP"]}},
)
```

`filters` only operates on top-level fields (`name`, `descriptorType`,
`version`) with the operators `$eq` / `$ne` / `$in`, plus `$and` / `$or` to
combine them. To filter by `kind` (your custom field), add it as a
search-time keyword in the query and rely on hybrid scoring.

> **GA rename**: `descriptorType` becomes `recordType` and the values
> change (`AGENT_SKILLS` → `SKILL`), so these become
> `filters={"recordType": {"$eq": "CUSTOM"}}`. `version` becomes
> `recordVersion`. See [docs/11](./11-ga-migration.md).

## Many KBs — registering and discovering across projects and domains

The single-KB case is easy and the record is mostly documentation. It gets
interesting at **multiple projects or knowledge domains**, which is the
common shape well before "multiple agents" is. Three constraints drive the
whole design, and the first one is a decision you cannot walk back easily.

### Do not shard registries by knowledge domain

The tempting move is one registry per project or domain. Resist it.

`SearchRegistryRecords` accepts **exactly one** registry identifier (the
parameter is list-shaped, but the API reference states you may specify only
one; `SearchDiscoverableRegistryRecords` keeps this at GA). Cross-registry
federated search is **not shipped** — see the federation discussion in
[docs/06](./06-future-optimizations.md).

So sharding by domain permanently forfeits unified retrieval — and
"which KB should answer this question?" is the *only* question that really
matters once you have many KBs. You would be optimizing the filing cabinet
at the cost of the thing you actually need.

**One registry; encode the domain inside the record.** Legitimate reasons
to split a registry are prod/dev isolation and hard compliance boundaries.
Knowledge domains are not among them.

### Routing rides on `description`, not on your custom fields

Server-side filterable fields are only `name`, `descriptorType` /
`recordType`, and `version` / `recordVersion`. Your `kind: knowledge-base`
is **not** filterable, and there is **no prefix or wildcard operator** —
`$eq` / `$ne` / `$in` only. So `kb-finops-*` is not expressible; you would
have to enumerate names with `$in`.

The consequence is blunt: **multi-KB routing is semantic search, and the
`description` field is the routing surface.** Not `spec.embeddingModel`,
not `kind` — the natural-language description. The registry runs semantic
and lexical search in parallel and merges results, and that text is what an
agent uses to decide where to look.

That inverts where the effort goes when you have many KBs:

| Field | Role once there are many KBs |
|---|---|
| `description` | **Highest leverage.** State what it covers, what it does *not*, and which questions belong here |
| `name` | Dedup key and the only precise filter handle — worth a naming convention, e.g. `kb-<domain>-<topic>` |
| `_meta.…invocation.useFor` / `doNotUseFor` | Disambiguation between neighbouring domains |
| `spec` | Governance, not routing. Keep volatile numbers out (see below) |

`doNotUseFor` shifts from nice-to-have to necessary here: a finance KB and
a legal KB **will** overlap in vector space, and negative scope is often
the only thing that separates them. Write it as the boundary between
specific sibling KBs, not as generic caution.

A worked pair, where the descriptions are doing the routing:

```jsonc
// kb-finops-cost-allocation
"description": "Cost allocation methodology, showback/chargeback rules, and
  tag policy for AWS spend. Answers 'who pays for this account' and 'how is
  shared infra split'. Does NOT cover vendor contract terms or procurement
  approval thresholds — see kb-legal-vendor-contracts.",

// kb-legal-vendor-contracts
"description": "Executed vendor agreements, renewal dates, liability caps,
  and procurement approval thresholds. Answers 'what did we sign' and 'who
  can approve this spend'. Does NOT cover internal cost attribution — see
  kb-finops-cost-allocation."
```

Both mention cost and spend, so lexical overlap is unavoidable. The
explicit hand-offs are what make the pair routable.

### Enumerating vs. routing are different APIs

Two distinct questions arise with many KBs, and they should not be served
by the same call:

| Question | API | Why |
|---|---|---|
| "Which KB can answer *this*?" | `SearchRegistryRecords` → GA: `SearchDiscoverableRegistryRecords` | Relevance-ranked; `maxResults` caps at **20** |
| "What KBs do we have?" | GA: `ListDiscoverableRegistryRecords` | Paginated browse of approved records, `maxResults` up to **100**, filterable by `recordType` |

The 20-result search ceiling is verified against the SDK service model, and
it bites sooner than you would expect in a mixed registry: skills, MCP
servers, and KBs all compete for the same 20 slots unless you filter by
type. This is the concrete reason to push the type predicate server-side
rather than filtering in Python after the fact — the same bug called out for
`04_consume_skill.py` in [docs/06](./06-future-optimizations.md).

At GA, `BatchGetDiscoverableRegistryRecord` also lets you pull full details
for 1–100 records in one call — the natural follow-up to a List when you
want an agent to choose among candidate KBs with their full descriptors in
hand.

### Keep volatile numbers out of `spec`

CUSTOM records get **no URL synchronization**. GA is explicit: auto-sync
fires only for the `mcpServer` and `a2aAgentCard` descriptors, and *"CUSTOM
records must be created manually by providing `data` directly."* The
`custom` descriptor carries no `source` field at all — this is structural,
not a not-yet-implemented gap.

So every volatile field you write **will** drift, with nothing to correct
it. In `examples/knowledge-base/example-record.json` that means
`documentCount: 4218` and `lastIngested` are stale the day after they are
written, and a stale number in an approved record is worse than no number,
because readers trust it.

Multiply that by many KBs and hand-maintenance stops being realistic. Two
honest options:

1. **Omit volatile fields.** Keep `spec` to facts you own and that rarely
   change: data sources, refresh cadence, language coverage, scope
   boundaries. Let `target.arn` be the handle for anyone who needs live
   numbers.
2. **Refresh them from a scheduled job** — EventBridge → Lambda that reads
   the real resource and calls `UpdateRegistryRecord`. This is the
   skill-shaped analogue of synchronization applied to CUSTOM, and note
   each update creates a new revision, so a chatty refresh job inflates
   revision history.

Start with option 1. Take on option 2 only when someone actually depends on
a number being current — the cost is a job you now have to operate, per
domain, forever. See
[docs/12](./12-record-artifact-integrity.md) for why this is the same
discovered-vs-actual problem in a different costume: CUSTOM's version of
the gap is wider than the skill one, since skills at least have an immutable
artifact to hash.

### Discovery is not authorization

A record containing a KB ARN does not grant anyone the ability to query it
— `bedrock:Retrieve` is separate IAM. That separation is a feature: the
catalog can legitimately be broader than any one consumer's access.

But it raises a question worth deciding deliberately with many domains:
**is the KB ARN itself, plus its description, sensitive?** Anyone who can
search the registry sees every approved KB's ARN, owning team, and scope
description. For a finance or legal KB, "this KB exists and covers
litigation exposure" may itself be information you would not broadcast
company-wide. If so, that — not knowledge domain — is a real reason to
split registries, since authorization is per-registry.

## Migration story — what to do today vs. later

If you've cloned this blueprint and got the skill demo working, the
incremental path to "full registry" is:

| Step | Effort | Value |
|---|---|---|
| Add a single `kind: knowledge-base` CUSTOM record for an existing Bedrock KB | 30 min | Search across "skills + KBs" works |
| Add `kind: lambda-tool` records for top-3 internal Lambda tools | 1 hour | Backend team's tools become discoverable without an MCP server build-out |
| Add `kind: guardrail` records for shared guardrails | 30 min | Security team gains audit visibility |
| Migrate one MCP server from "URL in a Confluence page" to a `descriptorType: MCP` record | 1 hour | The IDE MCP endpoint flow now picks up that server too |
| Wire EventBridge → Slack for `kind`-routed approvals | half day | Approval queue scales to multi-team curation |

The point: **each step adds one more `descriptorType` or `kind`
without rebuilding anything.** The infrastructure (CDK), the
governance (approval workflow), the discovery (MCP endpoint) is
already in place from Day 1.

→ Concrete starter records for the most common CUSTOM kinds live
under `examples/` — those are the jump-off points for your team's
extensions.
