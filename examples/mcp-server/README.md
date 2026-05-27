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
- For URL-sync (Path B): the server exposes a well-known
  `server-card.json` endpoint (or any URL returning the MCP
  server.json + tool list)

## Files

- `example-record.json` + `register.py` — Path A (manual inline)
- `example-record-url-sync.json` + `register-url-sync.py` — Path B (URL sync)

## Two registration paths

### Path A — manual, with explicit `inlineContent`

You provide the MCP server.json + tool list as JSON inline. Best when
the server isn't yet exposing its server.json at a well-known
endpoint, or when you want to pin a specific snapshot regardless of
what's live.

```bash
python3 register.py
```

### Path B — URL synchronization (recommended for in-house MCP servers)

The MCP server team writes **no publish code at all** — they just
expose a well-known endpoint. The Registry sets `synchronizationType=URL`
on the record, fetches `server.json` and `tools/list` itself,
validates against the MCP schema, and generates a new revision every
time the source changes.

```bash
# anonymous / IAM-signed fetch
python3 register-url-sync.py

# OAuth2-protected source (bearer token from AgentCore Identity)
python3 register-url-sync.py --credential-provider arn:aws:bedrock-agentcore:us-east-1:<acct>:credential-provider/<id>
```

This is the path that scales: your platform team operates the
registry while each MCP server team owns its own endpoint without
having to integrate a publish pipeline.

## When to use which

| | Path A — inline | Path B — URL sync |
|---|---|---|
| Source of truth | Whatever JSON you submitted | The live MCP server endpoint |
| Drift handling | Manual: run `update-registry-record` on changes | Automatic: new revision when source changes |
| Auth on fetch | N/A (no fetch) | Public, IAM-signed, or OAuth2 via credential provider |
| Best for | External / third-party MCP, fixed snapshots, air-gapped publishing | In-house MCP servers, anything iterating frequently |
| Server team writes publish code? | Yes (one-time inline JSON) | No |

## TODO

- [ ] Verify Path A end-to-end against a real MCP server
- [ ] Verify Path B end-to-end against an MCP server in AgentCore Runtime
- [ ] Add an example using AgentCore Identity OAuth2 credential provider for synced URLs
