# Dynamic discovery — Claude Code via the Registry MCP endpoint

The `04_consume_skill.py` script uses boto3 directly. That's the
right answer for CI/CD pipelines and automation.

For the **interactive IDE case** — a developer in Claude Code asking
"how do I triage this cost spike" — there's a more direct path: each
registry exposes a standards-compliant **MCP endpoint** the IDE can
configure as just another MCP server.

## The endpoint

```
https://bedrock-agentcore.{region}.amazonaws.com/registries/{registryId}/mcp
```

The CDK stack outputs the full URL as `McpEndpoint`. Substitute your
own values for `{region}` and `{registryId}`:

```
https://bedrock-agentcore.us-east-1.amazonaws.com/registries/<registryId>/mcp
```

This endpoint speaks **MCP spec 2025-11-25**. It exposes exactly one
tool:

```
Tool name: search_registry_records
Description: Searches for registry records using natural language queries.
             Returns metadata for matching records.
Parameters:
  searchQuery (required): string  — natural language query
  maxResults  (1-20, default 10) : integer
  filter      : object — $eq/$ne/$in + $and/$or on (name, descriptorType, version)
```

**Just one tool**, `search_registry_records`. Approval, deletion, and
record management deliberately don't have MCP tools — those are
governance operations and stay on the SDK / Console path.

## Two auth modes

Different MCP clients support different auth styles. Both are
supported by this same endpoint.

### Mode A — IAM auth via stdio proxy

MCP spec doesn't natively understand AWS SigV4, so AWS ships a small
stdio adapter, `mcp-proxy-for-aws`, that the client launches as a
subprocess. The proxy translates between MCP-over-stdio (what Claude
Code speaks to it) and HTTPS-with-SigV4 (what the registry expects).

`~/.claude/mcp.json` (or project-level `.claude/mcp.json`):

```json
{
  "mcpServers": {
    "private-skills-registry": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "mcp-proxy-for-aws@latest",
        "https://bedrock-agentcore.us-east-1.amazonaws.com/registries/<registryId>/mcp",
        "--service", "bedrock-agentcore",
        "--region", "us-east-1",
        "--profile", "my-profile"
      ]
    }
  }
}
```

Best for: developers with corporate SSO + AWS profile already
configured (e.g., IAM Identity Center).

### Mode B — JWT/OIDC auth, native HTTP

If the registry was created with a JWT authorizer, MCP clients
connect over HTTP directly with OAuth2 tokens — no proxy needed:

```bash
aws bedrock-agentcore-control update-registry \
  --registry-id <registryId> \
  --authorizer-configuration '{
    "customJWTAuthorizer": {
      "discoveryUrl": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_xxx/.well-known/openid-configuration",
      "allowedClients": ["abcdef123456"]
    }
  }'
```

`mcp.json`:

```json
{
  "mcpServers": {
    "private-skills-registry": {
      "type": "http",
      "url": "https://bedrock-agentcore.us-east-1.amazonaws.com/registries/<registryId>/mcp",
      "oauth": {
        "clientId": "abcdef123456",
        "callbackPort": 8765
      }
    }
  }
}
```

Best for: external contractors, multi-account orgs, scenarios where
giving everyone an IAM principal is not how identity is administered.

See [docs/05-auth-placeholder.md](./05-auth-placeholder.md) for the
full Cognito setup walk-through (Phase 2).

## End-to-end interaction

```
T=0   Claude Code starts
      ├─ reads mcp.json
      └─ spawns `uvx mcp-proxy-for-aws ...` (stdio)

T+50ms  MCP initialize handshake
        Claude Code → proxy → registry
        Registry returns serverInfo + capabilities

T+100ms  tools/list
         Registry returns: [search_registry_records]
         Claude Code adds the tool to its tool registry

T+...   User: "help me triage this AWS cost spike"
        Claude reasons → decides search_registry_records is relevant
        tools/call:
          name = search_registry_records
          arguments.searchQuery = "AWS cost spike triage"
        Registry returns 1 hit, full skillMd inline

T+...   Claude reads the SKILL.md → has 3 options:

         (a) inline:    pull skillMd into conversation context, follow it
         (b) install:   bash → pip install + activate (persists)
         (c) inspect:   ask user which option they want
```

## Why the registry returns the full SKILL.md

The MCP search response includes the **entire** `skillMd.inlineContent`
of each hit. Up to ~100KB, this is an intentional design: the agent
can decide whether to use the skill **without making a follow-up
download call**.

For a 3.5KB SKILL.md (our demo), this is roughly 700 tokens of
context — well below the threshold where you'd want to defer the
read.

For larger skills with substantial resource files, the agent typically
takes the install path (b) so the resource files end up on local
disk and can be referenced lazily.

## Permissions

Two extra IAM actions are needed for MCP-endpoint access (vs. SDK):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock-agentcore:InvokeRegistryMcp",
        "bedrock-agentcore:SearchRegistryRecords"
      ],
      "Resource": "arn:aws:bedrock-agentcore:us-east-1:*:registry/*"
    }
  ]
}
```

Verify the proxy can reach the endpoint:

```bash
curl -sS -X POST \
  "https://bedrock-agentcore.us-east-1.amazonaws.com/registries/<registryId>/mcp" \
  -H "Content-Type: application/json" \
  -H "X-Amz-Security-Token: ${AWS_SESSION_TOKEN}" \
  --aws-sigv4 "aws:amz:us-east-1:bedrock-agentcore" \
  --user "${AWS_ACCESS_KEY_ID}:${AWS_SECRET_ACCESS_KEY}" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"search_registry_records","arguments":{"searchQuery":"weather"}}}'
```

(`weather` returns 0 hits but exercises the auth + protocol path.)

## Comparison to the SDK path

| | SDK (boto3) | MCP endpoint |
|---|---|---|
| Auth | Native AWS credentials | IAM via proxy *or* JWT native |
| Caller | Programs (CI/CD, custom scripts) | Agents (Claude Code, Cursor, Kiro) |
| Tool surface | Full CRUD on records | `search_registry_records` only |
| Audit | CloudTrail | CloudTrail (same) |
| Latency | Direct HTTPS, ~100ms | Direct HTTPS or stdio→HTTPS, ~150ms |
| Versions seen | Same data | Same data (only `APPROVED` for non-admins) |

Use SDK for governance/automation. Use MCP for IDE-driven discovery.

→ Next: [auth & permissions placeholder](./05-auth-placeholder.md)
