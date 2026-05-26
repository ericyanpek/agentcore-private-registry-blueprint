# Architecture — service mapping and design choices

## At a glance

```
                Author / CI                       AWS Account
       ┌─────────────────────────┐         ┌────────────────────────────┐
       │ skill-package/           │         │ CodeArtifact (us-east-1)   │
       │   pyproject.toml         │         │   domain  : skills-demo    │
       │   src/<name>/            │   pkg   │   repo    : skills-prod    │
       │     SKILL.md             │ ──────▶ │   format  : pypi           │
       │     resources/*.md       │  twine  │   KMS     : aws-managed    │
       │     postinstall.py       │         │   storage : service-S3     │
       └────────┬─────────────────┘         └──────────────┬─────────────┘
                │                                          │
                │ create_registry_record                   │
                │ (skillMd + skillDefinition.packages[pypi])
                ▼                                          │
       ┌──────────────────────────────────┐                │
       │ Bedrock AgentCore Registry        │                │
       │   - record metadata + governance │                │
       │   - hybrid search (semantic+kw)  │                │
       │   - status: APPROVED only        │                │
       │   - exposes MCP endpoint         │                │
       └─────────────────┬────────────────┘                │
                         │                                 │
        SDK path         │            MCP path             │
   boto3.search_registry │   tools/call search_registry    │
                         │                                 │
       ┌─────────────────┴───────┐                         │
       │ Consumer (developer or  │                         │
       │ Claude Code itself)     │                         │
       └─────────────┬───────────┘                         │
                     │           pip install               │
                     └─────────────────────────────────────┘
                                         │
                                         ▼
                          ~/.claude/skills/<name>/
                              SKILL.md + resources/
                          Auto-discovered by Claude Code
```

## Service-by-service mapping

### CodeArtifact — the artifact backend

| Property | Value | Why this matters |
|---|---|---|
| Format | PyPI (npm/Maven/Generic also supported) | Agent Registry's `skillDefinition.packages[].registryType` schema enumerates `pypi` and `npm` as first-class. PyPI wins because Python tooling is already present in every Bedrock/AgentCore runtime |
| Domain encryption | AWS-managed KMS by default; CMK swappable | At-rest encryption is on without configuration; CMK upgrade is a parameter when you need it |
| Version immutability | Once published, cannot overwrite | This is **the** compliance property. `aws-cost-anomaly-triage==0.1.0` is the same forever |
| Authentication | IAM-issued 12h bearer token | `aws codeartifact login --tool pip` writes the token to pip config; CI runners use IAM roles |
| Public-package proxy | External Connection (optional) | Lets you mirror upstream PyPI through the same repo, with caching and license scanning |

**Design choice — why not S3 directly?**
S3 is cheaper and has Object Lock for compliance, but:
- The Registry schema doesn't enumerate `s3` as a `registryType`; you'd
  have to use the `_meta` extension field, losing first-class search.
- Consumers would need to write custom download logic; with PyPI,
  `pip install` is the consumer protocol.
- No native version-immutability semantics — you'd build it with
  Object Lock and pray.

S3 still makes sense for **non-Python skills with arbitrary file
trees**; see [docs/06-future-optimizations.md](./06-future-optimizations.md)
for the hybrid pattern.

### Agent Registry — the metadata + governance layer

| Property | Value | Why this matters |
|---|---|---|
| Resource types | MCP servers, A2A agents, **AGENT_SKILLS**, custom | Skills are first-class, not custom |
| Skill record | `skillMd` (full SKILL.md text) + `skillDefinition` (JSON pointing at PyPI package) | Search can match against the full SKILL.md content; consumers parse `packages[]` to find the artifact |
| Approval workflow | DRAFT → PENDING_APPROVAL → APPROVED / REJECTED / DEPRECATED | Only APPROVED records are visible to consumers via search. This is the audit gate. |
| Search | Hybrid semantic + keyword on description, name, descriptors | "AWS cost spike triage" finds `aws-cost-anomaly-triage` even though the words don't match exactly |
| Auth | IAM (control + data plane) or JWT (data plane only, via Cognito/Okta/etc.) | Control plane is always IAM (admins are AWS principals); search and MCP can be JWT (broader user base via SSO) |
| MCP endpoint | One per registry, exposes `search_registry_records` tool | This is the dynamic-discovery surface — see [docs/04-dynamic-discovery.md](./04-dynamic-discovery.md) |
| Audit | CloudTrail integration | Every API call is logged for compliance |
| Notification | EventBridge events on state changes | Wire approval-pending events to Slack / email / ServiceNow |

### Skill record — anatomy of an `AGENT_SKILLS` descriptor

A real published record from this repo:

```json
{
  "name": "aws-cost-anomaly-triage",
  "description": "FinOps SOP for triaging AWS cost anomalies — text-only skill distributed via CodeArtifact PyPI.",
  "descriptorType": "AGENT_SKILLS",
  "recordVersion": "0.1.0",
  "status": "APPROVED",
  "descriptors": {
    "agentSkills": {
      "skillMd": {
        "inlineContent": "---\nname: aws-cost-anomaly-triage\ndescription: ...\n---\n# AWS Cost Anomaly Triage\n..."
      },
      "skillDefinition": {
        "schemaVersion": "0.1.0",
        "inlineContent": "{
          \"websiteUrl\": \"https://example.internal/finops/cost-anomaly-triage\",
          \"repository\": {\"url\": \"...\", \"source\": \"github\"},
          \"packages\": [
            {
              \"registryType\": \"pypi\",
              \"identifier\": \"aws-cost-anomaly-triage\",
              \"version\": \"0.1.0\"
            }
          ],
          \"_meta\": {
            \"com.example.codeartifact\": {
              \"domain\": \"skills-demo\",
              \"repository\": \"skills-prod\",
              \"region\": \"us-east-1\",
              \"indexUrl\": \"https://skills-demo-984072314535.d.codeartifact.us-east-1.amazonaws.com/pypi/skills-prod/simple/\"
            },
            \"com.example.activate\": {
              \"postInstallCommand\": \"install-aws-cost-anomaly-triage\",
              \"skillTargetDir\": \"~/.claude/skills/aws-cost-anomaly-triage/\"
            },
            \"com.example.owner\": {
              \"team\": \"FinOps\",
              \"contact\": \"finops@example.internal\"
            }
          }
        }"
      }
    }
  }
}
```

**Why two parts (`skillMd` + `skillDefinition`)?**
- `skillMd` is human/agent-readable, used for semantic search and to
  show in the registry console. Lifted directly from the repo SKILL.md.
- `skillDefinition` is machine-readable, validated against an Amazon
  schema (v0.1.0 currently). This is what a consumer parses to know
  where to actually `pip install` from.

The split matches the MCP Registry community design: **metadata vs.
pointers, both first-class**.

### `_meta` extension fields

The schema requires reverse-DNS namespaced keys. This blueprint defines:

| Key | Purpose |
|---|---|
| `com.example.codeartifact` | Index URL + domain + repo + region for the PyPI source |
| `com.example.activate` | Post-install console script + target directory for activation |
| `com.example.owner` | Team + contact for governance / support |

Replace `com.example` with your actual reversed corporate domain
(e.g., `com.acme.codeartifact`) when you fork.

## Sequence: publish a skill

```
Author → CodeArtifact:    aws codeartifact login + twine upload
                          ───────────────────────────────────▶ pkg v0.1.0 stored

Author → AgentRegistry:   create_registry_record (DRAFT)
                          submit_for_approval (PENDING_APPROVAL)

Curator → AgentRegistry:  update_registry_record_status APPROVED

[15-30s]                  semantic index update

Consumer search ↓
```

## Sequence: consume a skill

```
Consumer → AgentRegistry:  search_registry_records "cost anomaly"
                            (via boto3 SDK or MCP endpoint)

Registry → Consumer:        record metadata (incl. skillMd + packages[])

Consumer parses _meta.codeartifact.indexUrl
Consumer → CodeArtifact:    aws codeartifact login --tool pip
Consumer:                   pip install aws-cost-anomaly-triage==0.1.0
Consumer:                   install-aws-cost-anomaly-triage
                            (postinstall script copies skill_files/ to
                             ~/.claude/skills/aws-cost-anomaly-triage/)

Claude Code:                detects new skill on next prompt
```

## Beyond skills — the same registry holds more

Everything above describes the Skill flow, because that's what the
Day-1 demo verifies end-to-end. The registry's design is broader:

| `descriptorType` | Validation | Backend pattern |
|---|---|---|
| `AGENT_SKILLS` (this demo) | SKILL.md + skillDefinition v0.1.0 | CodeArtifact PyPI artifact + `pip install` activation |
| `MCP` | MCP server.json schema | AgentCore Runtime / Lambda / ECS-hosted, **or** external HTTPS endpoint (URL-synced) |
| `A2A` | Google A2A Agent Card | Any A2A-speaking agent runtime |
| `CUSTOM` | Whatever JSON you define (`_meta` reverse-DNS recommended) | Any AWS resource: Bedrock KB, Lambda function, Step Functions state machine, Bedrock Guardrail, Cedar policy bundle, eval dataset in S3, schema in Schema Registry, … |

The publish/approve/consume flow is identical for every type — only
the descriptor body and the activation step differ. This is what
makes the registry the right home for **all** of an org's governed
AI resources, not just skills.

For worked examples (an 18-record customer-care registry that uses
all four `descriptorType`s), see
[docs/07-extending-to-other-resources.md](./07-extending-to-other-resources.md).

## Boundary decisions

A few things this blueprint deliberately leaves out — see
[docs/06-future-optimizations.md](./06-future-optimizations.md) for context:

- **No artifact rehosting in the registry**. The registry has 100KB
  inline limits per descriptor. The artifact lives in CodeArtifact.
  This matches the MCP Registry industry pattern.
- **No skill execution sandbox**. Activation = "copy file to
  `~/.claude/skills/`". Sandboxing is the agent runtime's job
  (Claude Code, Bedrock AgentCore Runtime sandbox profile, etc.).
- **No skill scanning gate at this layer**. You can wire EventBridge
  → Lambda → `cisco-ai-skill-scanner` to add automated security
  scanning before approval; it's a Phase 2 add-on, not in the core blueprint.

→ Next: [demo walkthrough](./03-demo-walkthrough.md)
