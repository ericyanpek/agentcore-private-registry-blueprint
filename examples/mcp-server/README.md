# Example — registering an MCP server

Status: 📘 Documented (skeleton). Adapt the placeholder values to a
real MCP server you control before running.

## What this does

Registers an MCP server you've already deployed (in AgentCore
Runtime / Lambda / ECS / on-prem / a third-party host) into the
registry as a `descriptorType: MCP` record. After approval,
consumers (Claude Code, Cursor, Kiro) can discover and connect
to it through the registry.

## Prerequisites

- An existing registry from `cdk deploy` (Day-1)
- An MCP server reachable via HTTPS (the example below uses
  `https://mcp.example.internal/v1`)
- Optional: server.json published at the server's well-known path
  for URL synchronization

## Files

- `example-record.json` — the record body sent to `CreateRegistryRecord`
- `register.py` — boto3 script (mirrors `scripts/02_register_skill.py`)

## Two registration paths

### Path A — manual, with explicit `inlineContent`

You provide the MCP server.json as JSON inline. Best when the server
isn't yet exposing its server.json at a well-known endpoint.

```bash
python3 register.py
```

### Path B — URL synchronization

Set `synchronizationType=FROM_URL`. The registry fetches the latest
server metadata from the URL and updates the record on a schedule
or on-demand.

```python
client.create_registry_record(
    registryId="<id>",
    name="example-mcp",
    descriptorType="MCP",
    descriptors={
        "mcp": {
            "server": {
                "schemaVersion": "2025-12-11",
                "inlineContent": "{}",
            }
        }
    },
    synchronizationType="FROM_URL",
    synchronizationConfiguration={
        "fromUrl": {
            "url": "https://mcp.example.internal/v1/.well-known/mcp/server-card.json",
            # If the URL needs auth, attach an OAuth2 or IAM credentialProvider here
        }
    },
    recordVersion="1.0.0",
)
```

## TODO

- [ ] Verify end-to-end against a real MCP server
- [ ] Add an example using AgentCore Runtime as the host
- [ ] Add an example with OAuth2 credentialProvider for synced URLs
