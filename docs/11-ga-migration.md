# GA migration — `bedrock-agentcore` → `agent-registry`

AWS Agent Registry reaches GA on **2026-08-06**. It leaves the
`bedrock-agentcore` namespace for a dedicated `agent-registry` namespace,
and the registry/record data model changes in ways that **break backward
compatibility**. The old namespace shuts down **2026-09-17**.

Everything in this repo currently targets the preview namespace. This doc
is the migration plan for it: what changes, what it maps to here, and why
the code has not been flipped yet.

## Status of this repo

| | |
|---|---|
| Code targets | preview (`bedrock-agentcore`) |
| Verified against GA SDK | ❌ not yet — see below |
| Docs updated for GA | ✅ this doc + warnings in affected pages |

**Why the code is still on preview.** The GA service clients do not exist
in the current SDK. Checked 2026-08-04 with boto3/botocore 1.42.97:

```
bedrock-agentcore              YES
bedrock-agentcore-control      YES
agent-registry                 no
agent-registry-control         no
```

Rewriting `boto3.client("bedrock-agentcore-control")` to
`boto3.client("agent-registry-control")` today would turn a working demo
into `UnknownServiceError` for everyone, including us. The sequence is:
GA lands → SDK ships the clients → flip the code → re-run the end-to-end
verification → then update the status table above. Not before.

**If you are cloning this repo on or after 2026-08-06**: read the
[hard cutoff](#the-hard-cutoff-for-new-accounts) section first. The
scripts will very likely not run for you as-is.

## The hard cutoff for new accounts

This is the sharpest edge in the whole migration, and it is specific to
public blueprints like this one.

Accounts that have **no** registries or records as of 2026-08-06 **cannot
access AWS Agent Registry through the `bedrock-agentcore` namespace at
all**. Only accounts with pre-existing preview data keep dual-namespace
access, and only until 2026-09-17.

So there are two very different reader experiences:

| Your account | What happens when you run `scripts/01_create_registry.py` |
|---|---|
| Has preview registries from before 2026-08-06 | Works until 2026-09-17 |
| Fresh account, first run after 2026-08-06 | **Fails** — no access to the preview namespace |

The failure is not graceful. There is no deprecation warning and no
fallback — the demo simply does not run. If that's you, wait for the
GA-flipped version of this repo, or apply the mapping below yourself.

## Namespace and configuration changes

| Surface | Preview | GA |
|---|---|---|
| IAM action prefix | `bedrock-agentcore:*` | `agent-registry:*` |
| Service principal | `bedrock-agentcore.amazonaws.com` | `agent-registry.amazonaws.com` |
| Data plane endpoint | `bedrock-agentcore.{region}.amazonaws.com` | `agent-registry.{region}.api.aws` |
| Control plane endpoint | `bedrock-agentcore-control.{region}.amazonaws.com` | `agent-registry-control.{region}.api.aws` |
| Registry ARN | `arn:aws:bedrock-agentcore:{region}:{acct}:registry/{id}` | `arn:aws:agent-registry:{region}:{acct}:registry/{id}` |
| Record ARN | `…:registry/{id}/record/{rid}` under `bedrock-agentcore` | same shape under `agent-registry` |
| boto3 data plane client | `bedrock-agentcore` | `agent-registry` |
| boto3 control plane client | `bedrock-agentcore-control` | `agent-registry-control` |
| CLI | `aws bedrock-agentcore-control …` | `aws agent-registry-control …` |
| CloudTrail event source | `bedrock-agentcore.amazonaws.com` | `agent-registry.amazonaws.com` |
| EventBridge source | `aws.bedrock-agentcore` | `aws.agent-registry` |
| CloudWatch namespace | `AWS/BedrockAgentCore` | `AWS/AgentRegistry` |
| Service Quotas code | `bedrock-agentcore` | `agent-registry` |

Note the endpoint domain change: `.amazonaws.com` → **`.api.aws`**. A
find-and-replace on the service name alone will produce hostnames that
don't resolve.

### Two traps in the IAM rewrite

**Trap 1 — do not blanket-replace every `bedrock-agentcore` action.**
The namespace move applies *only* to Agent Registry. The rest of
AgentCore — Identity, Gateway, Runtime, Policy — stays put. Concretely,
workload identity and OAuth credential provider resources **intentionally
retain the old namespace**. If a registry uses URL sync with OAuth or IAM
credentials, these must survive the rewrite unchanged:

```
"bedrock-agentcore:CreateWorkloadIdentity",
"bedrock-agentcore:GetWorkloadIdentity",
"bedrock-agentcore:DeleteWorkloadIdentity"
```

This repo happens not to grant any workload-identity actions today
(verified: no `WorkloadIdentity` / `WorkloadAccessToken` references
anywhere outside this doc), so nothing here is currently exposed to the
trap. It becomes live the moment someone adds URL-sync with OAuth — which
`examples/mcp-server/register-url-sync.py` is the natural place for. Flagged
because a repo-wide `sed 's/bedrock-agentcore/agent-registry/g'` is the
obvious way to do this migration and is wrong: it would break those
permissions in any downstream fork that has added them.

**Trap 2 — the managed policy does not carry over.**
`BedrockAgentCoreFullAccess` will **not** be updated with
`agent-registry:*` permissions. Anyone relying on it must switch to the
new **AgentRegistryFullAccess** managed policy, available at GA.

Also worth flagging for anyone who filed quota increases: custom quotas
requested under the `bedrock-agentcore` service code must be
**re-requested** under `agent-registry`. The `docs/06` advice about
raising `SearchRegistryRecords` / `InvokeRegistryMcp` from the 5 TPS
default applies to the new service code now.

## API schema changes

Six areas change. Renaming clients is the easy part; this is the part that
actually requires reading code.

### 1. Registry entity

`authorizerType` and `authorizerConfiguration` move inside a new
`discoveryConfiguration` wrapper. `approvalConfiguration.autoApproval`
(boolean) becomes `approvalConfiguration.autoApprovalRules` (array of
enum). `["APPROVE_ALL"]` means what `autoApproval: true` meant; `[]` or
absent means manual approval.

Affects `scripts/01_create_registry.py`, which passes
`approvalConfiguration={"autoApproval": False}`:

```python
# preview
approvalConfiguration={"autoApproval": False},

# GA — manual approval, which is what this blueprint wants
approvalConfiguration={"autoApprovalRules": []},
```

The JWT sketch in `docs/05` also needs the extra nesting level, since
`authorizerConfiguration` now sits under `discoveryConfiguration`.

### 2. New required record fields

Records gain two required top-level fields:

- **`name`** — a dedup key, unique within the registry. Where
  `recordVersion` is also set, `name` + `recordVersion` must be unique.
- **`recordType`** — semantic type, one of `AGENT`, `MCP`, `SKILL`,
  `CUSTOM`. Determines which primary descriptor key is legal.

### 3. Record restructuring — the breaking one

`descriptorType` **is removed entirely**. `recordType` replaces it for
categorization, and the `descriptors` union is flattened into a flat
keyed structure.

| Preview | GA |
|---|---|
| `name` | `displayName` (and a *new* `name` as dedup key) |
| `descriptorType` | **removed** — replaced by top-level `recordType` |
| `inlineContent` | `data` |
| `schemaVersion` / `protocolVersion` | `dataSchemaVersion` |
| `synchronizationConfiguration` (top level) | `source`, moved *inside* each descriptor |
| `descriptors.agentSkills.skillDefinition` | `descriptors.agentSkillsDefinition` |
| `descriptors.agentSkills.skillMd` | `descriptors.agentSkillsDefinition.additionalData.skillMd` |
| `descriptors.mcp.server` | `descriptors.mcpServer` |
| `descriptors.mcp.tools` | `descriptors.mcpServer.additionalData.tools` |
| `descriptors.agent.a2aAgentCard` | `descriptors.a2aAgentCard` |
| `descriptors.custom` | `descriptors.custom` (unchanged key, `inlineContent` → `data`) |

Exactly one primary descriptor per record. Valid pairings:

| `recordType` | Allowed primary descriptor |
|---|---|
| `AGENT` | `a2aAgentCard`, `mcpServer`, `custom` |
| `MCP` | `mcpServer`, `custom` |
| `SKILL` | `agentSkillsDefinition`, `custom` |
| `CUSTOM` | `custom` |

**Note the rename that matters most to this repo**: the skill descriptor
type is `AGENT_SKILLS` in preview but the record type is **`SKILL`** at
GA. Every `descriptorType="AGENT_SKILLS"` in this repo becomes
`recordType="SKILL"`.

Concretely, for `scripts/02_register_skill.py`:

```python
# preview
descriptorType="AGENT_SKILLS",
descriptors={
    "agentSkills": {
        "skillMd": {"inlineContent": skill_md},
        "skillDefinition": {
            "schemaVersion": "0.1.0",
            "inlineContent": skill_def,
        },
    }
},

# GA
recordType="SKILL",
descriptors={
    "agentSkillsDefinition": {
        "data": skill_def,
        "dataSchemaVersion": "0.1.0",
        "additionalData": {
            "skillMd": {"data": skill_md},
        },
    }
},
```

Two things to notice in that diff, because they are easy to get wrong:

1. **The nesting inverts.** In preview, `skillMd` and `skillDefinition`
   are siblings. At GA, `agentSkillsDefinition` is the primary descriptor
   and `skillMd` is demoted to a child under `additionalData`. The
   skill definition is now structurally the record's identity; the
   human-readable `SKILL.md` is supplementary metadata hanging off it.
2. **`name` changes meaning.** The old `name` becomes `displayName`, and a
   new `name` is the dedup key. A migration that maps old `name` → new
   `name` and stops has silently dropped the display name — and since both
   fields accept the same string, nothing will error. Set both
   deliberately.

### 4. Data plane / search changes

`SearchRegistryRecords` is **renamed** to
`SearchDiscoverableRegistryRecords` (`POST /discoverable-records-search`).
Filters change with it: `recordType` replaces `descriptorType`,
`recordVersion` replaces `version`. Responses come back in the new
descriptor format and omit `credentialProviderConfigurations`.

The MCP tool is renamed too: **`search_registry_records` →
`search_discoverable_registry_records`**. This one reaches beyond code
into prose — the "Registry exposes exactly one tool" mental model in the
README and `docs/04` names the old tool, and so does any MCP client
config a reader may have copied.

The IAM actions change more than a prefix swap here:

| Preview action | GA action |
|---|---|
| `bedrock-agentcore:SearchRegistryRecords` | `agent-registry:SearchDiscoverableRegistryRecords` |
| — | `agent-registry:ListDiscoverableRegistryRecords` (new) |
| — | `agent-registry:GetDiscoverableRegistryRecord` (new) |

So the Reader policy in `docs/09` needs new action *names*, not just a new
prefix.

### 5. New browsing APIs

Two additions, no migration required:

- **`ListDiscoverableRegistryRecords`** — paginated list of approved
  records, for browsing/catalog UIs rather than query-driven search.
- **`BatchGetDiscoverableRegistryRecord`** — full details for 1–100
  records in one call. Accepts exactly one registry entry at launch; the
  grouped request shape is forward-compatible with cross-registry
  batching later.

`BatchGetDiscoverableRegistryRecord` has **no IAM action of its own** — it
authorizes each requested record against
`agent-registry:GetDiscoverableRegistryRecord`. A policy without that
action cannot use BatchGet.

These are genuinely useful here. `ListDiscoverable…` is the API this
blueprint wanted for "show me the approved catalog" without inventing a
search query, and the grouped shape of BatchGet is the same
forward-looking-plural signal as `registryIds` — see the federation
discussion in `docs/06`.

### 6. List APIs adopt structured filters

Per-field query parameters are replaced by a single `filters` list of
`{"name": "<dotted.path>", "values": [...]}`, and **List operations move
from `GET` to `POST`**. Pagination is unchanged.

```
# preview
GET /registries?status=READY&authorizerType=AWS_IAM

# GA — POST /registries-list
{"filters": [
   {"name": "status", "values": ["READY"]},
   {"name": "discoveryConfiguration.authorizerType", "values": ["AWS_IAM"]}
]}
```

Note the dotted path tracking change 1's nesting:
`discoveryConfiguration.authorizerType`, not `authorizerType`.

## Per-file work list for this repo

Ordered by blast radius. 25 files reference the old namespace; these are
the ones where the change is more than a string swap.

| File | What has to change |
|---|---|
| `scripts/01_create_registry.py` | client name + endpoint; `autoApproval` → `autoApprovalRules`; `list_registries` filter shape |
| `scripts/02_register_skill.py` | client + endpoint; drop `descriptorType`, add `recordType="SKILL"`; restructure `descriptors`; set `name` **and** `displayName` |
| `scripts/03_approve_skill.py` | client + endpoint; record-listing filter shape |
| `scripts/04_consume_skill.py` | both clients + endpoints; `search_registry_records` → `search_discoverable_registry_records`; client-side `descriptorType` check → server-side `recordType` filter (see `docs/06`) |
| `skills/publish-skill/scripts/publish.py` | same record-shape changes as `02` |
| `cdk/lib/registry-stack.ts` | IAM actions and ARNs; registry props if authorizer config is set |
| `cdk/lib/identity-stack.ts` | IAM actions and ARNs in the Identity Pool role policies |
| `docs/09-publishing-iam.md` | all four persona policies; `SearchRegistryRecords` → `SearchDiscoverableRegistryRecords` plus the two new Discoverable actions — new action *names*, not just a new prefix |
| `docs/04-dynamic-discovery.md` | MCP tool rename; endpoint host; SigV4 signing service name |
| `docs/05-auth-placeholder.md` | `discoveryConfiguration` nesting in the JWT sketch; audit policy actions |
| `docs/03-demo-walkthrough.md` | command output and API names in the walkthrough |
| `examples/*/register*.py` | record-shape changes; `source` moves inside descriptors for the URL-sync example |
| `README.md` / `README.en.md` | MCP tool name in the mental-model section; status tables |

`examples/mcp-server/register-url-sync.py` deserves individual attention:
it uses top-level `synchronizationConfiguration`, which at GA becomes a
per-descriptor `source` under `mcpServer`. That's a structural move, not a
rename.

## Recommended sequence

1. **Now** — docs carry the warnings (done); code stays on preview so the
   demo keeps working.
2. **On/after 2026-08-06** — confirm `agent-registry-control` exists in
   boto3, then flip clients + endpoints + schemas together. They are one
   atomic change; a half-migrated script fails in confusing ways.
3. **Verify** by re-running the full end-to-end path
   (`01` → `02` → `03` → `04`) in a scratch account, plus
   `examples/cognito-end-to-end/`, which is the one example with a live
   verification script.
4. **Then** update the status table at the top of this doc and the README
   status tables.

For anyone with real preview data, AWS provides migration tooling in
[agentcore-samples](https://github.com/awslabs/agentcore-samples) that
extracts, transforms, and loads into the new namespace, deduplicating on
`name`. Under ~5 registries / ~100 records, run it locally; larger or
without terminal access, deploy it as Lambda or Glue; actively-written
production platforms should dual-write first, then migrate, then cut over
reads. This blueprint's own demo data is disposable — recreating it from
`01`–`04` is faster than migrating it.

→ Back to: [roadmap](./06-future-optimizations.md)
