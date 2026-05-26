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

Search filters compose neatly:

```python
# All knowledge bases the agent might use
data.search_registry_records(
    registryIds=arns,
    searchQuery="product knowledge",
    filter={"descriptorType": {"$eq": "CUSTOM"}},
)

# Only AGENT_SKILLS
data.search_registry_records(
    registryIds=arns, searchQuery="...",
    filter={"descriptorType": {"$eq": "AGENT_SKILLS"}},
)

# Skills OR MCP — exclude CUSTOM noise
data.search_registry_records(
    registryIds=arns, searchQuery="...",
    filter={"descriptorType": {"$in": ["AGENT_SKILLS", "MCP"]}},
)
```

The `filter` only operates on top-level fields (`name`,
`descriptorType`, `version`). To filter by `kind` (your custom
field), add it as a search-time keyword in the query and rely on
hybrid scoring.

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
