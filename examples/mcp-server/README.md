# Example — registering an MCP server

Status: 📘 Documented (skeleton). Adapt the placeholder values to a
real MCP server you control before running.

## What this does

Registers an MCP server you've already deployed (in AgentCore
Runtime / Lambda / ECS / on-prem / a third-party host) into the
registry as a `recordType: MCP` record. After approval,
consumers (Claude Code, Cursor, Kiro) can discover and connect
to it through the registry.

## Prerequisites

- An existing registry from `cdk deploy` (Day-1)
- An MCP server reachable via HTTPS (the example below uses
  `https://mcp.example.internal/v1`)
- Install the shared blueprint package: `python -m pip install -e .` from the repository root
- For URL-sync (Path B): a live MCP endpoint reachable by Registry with the configured source credentials

## Files

- `example-record.json` + `register.py` — Path A (manual inline)
- `example-record-url-sync.json` + `register-url-sync.py` — Path B (URL sync)

## Two registration paths

### Path A — manual, with explicit descriptor `data`

You provide the MCP server.json + tool list as JSON inline. Best when
the server isn't yet exposing its server.json at a well-known
endpoint, or when you want to pin a specific snapshot regardless of
what's live.

```bash
python3 register.py
```

### Path B — URL synchronization (recommended for in-house MCP servers)

Configure `descriptors.mcpServer.source.fromUrl` with the live endpoint.
Registry fetches metadata using the source's authorization configuration.
Synchronization updates create record revisions; verify synchronization and approval behavior
against your endpoint rather than treating this as a runtime integrity guarantee.

```bash
# anonymous fetch
python3 register-url-sync.py

# OAuth2-protected source (bearer token from AgentCore Identity)
python3 register-url-sync.py --credential-provider YOUR_AGENTCORE_OAUTH_PROVIDER_ARN
```

This is the path that scales: your platform team operates the
registry while each MCP server team owns its own endpoint without
having to integrate a publish pipeline.

## When to use which

| | Path A — inline | Path B — URL sync |
|---|---|---|
| Source of truth | Whatever JSON you submitted | The live MCP server endpoint |
| Drift handling | Manual: run `update-registry-record` on changes | Automatic: new revision when source changes |
| Auth on fetch | N/A (no fetch) | This script supports anonymous/OAuth2; IAM requires an explicit source credential configuration |
| Best for | External / third-party MCP, fixed snapshots, air-gapped publishing | In-house MCP servers, anything iterating frequently |
| Server team writes publish code? | Yes (one-time inline JSON) | No |

## TODO

- [ ] Verify Path A end-to-end against a real MCP server
- [ ] Verify Path B end-to-end against an MCP server in AgentCore Runtime
- [ ] Add an example using AgentCore Identity OAuth2 credential provider for synced URLs
