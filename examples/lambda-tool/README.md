# Example — registering a Lambda function as an agent tool (CUSTOM)

Status: 📘 Documented (skeleton). Replace the placeholder ARN with a
real Lambda function before running.

## What this does

Registers a single Lambda function as a discoverable tool, using
`descriptorType: CUSTOM` with `kind: lambda-tool`. Agents looking
for tools find it via search, then invoke it directly via
AgentCore Gateway, Bedrock function-calling, or a Step Functions
wrapper.

## When to use this vs. an MCP server

| Use lambda-tool record | Use MCP server record |
|---|---|
| Single function, simple input/output | Multiple tools that share state or auth |
| Don't want to maintain an MCP server process | Tools form a coherent surface (e.g., a CRM API) |
| Already have a Lambda you want to expose | Building from scratch |

## Files

- `example-record.json` — body for `CreateRegistryRecord`
- `register.py` — boto3 script

## TODO

- [ ] Verify end-to-end against a real Lambda
- [ ] Show AgentCore Gateway → Lambda integration as the consumer
- [ ] Add an example with VPC-only Lambda (PrivateLink endpoint)
