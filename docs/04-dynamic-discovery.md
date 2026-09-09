# GA Registry discovery through MCP

Registry discovers metadata; it does not install skills or automatically invoke discovered MCP servers.
Treat discovery and verified installation as separate steps.

## IAM registry

The CDK output `McpEndpoint` uses:

```text
https://agent-registry.REGION.api.aws/registries/REGISTRY_ID/mcp
```

An MCP client that cannot sign SigV4 requests can use the AWS MCP proxy:

```json
{
  "mcpServers": {
    "private-skills-registry": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "mcp-proxy-for-aws",
        "https://agent-registry.us-east-1.api.aws/registries/REGISTRY_ID/mcp",
        "--service", "agent-registry",
        "--region", "us-east-1",
        "--profile", "consumer"
      ]
    }
  }
}
```

For repeatable enterprise distribution, pin the proxy to the version verified with your client.
Use the client's supported MCP configuration location rather than assuming all IDEs share one file.
Verify the endpoint with MCP `tools/list`; the GA search tool is
`search_discoverable_registry_records`, not the Preview `search_registry_records`.

The IAM identity needs `agent-registry:InvokeRegistryMcp` and the relevant discovery actions on
the configured registry/records. The minimal SDK-only policy in `iam/consumer-policy.json` intentionally
omits MCP invoke; add it for this route. IdentityStack's reader roles already include it.

After selecting an approved release, use `scripts/04_consume_skill.py` with its explicit version
to download and verify it. Do not ask the IDE to run arbitrary installation commands from metadata.
Reading inline `SKILL.md` for one-off use does not verify or load the wheel's supporting resources.

## OAuth/JWT registry

GA supports native OAuth/JWT discovery through an enterprise IdP. Configure discovery authorization
when provisioning an appropriate registry; the IAM blueprint does not provision this mode.
One registry uses its configured authorization type; do not assume a single endpoint accepts IAM and
JWT simultaneously. All governance APIs still require IAM.

OAuth discovery does not grant CodeArtifact access. For artifact download, retain the separate temporary
IAM credential path (for example, Cognito Identity Pool and `skill-cli`).

References: [discovery authorization](https://docs.aws.amazon.com/help-panel/bedrock-agentcore/latest/console/hp-registry-search-api-auth.html),
[GA migration](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/registry-faq.html).
