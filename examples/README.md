# Day-N extension examples

Each subdirectory is a self-contained example for registering a
non-Skill resource type into the same Agent Registry that the Day-1
demo creates. Status notation:

- 📘 **Documented** — example.json + register.py skeleton present, run yourself
- ✅ **Verified end-to-end** — confirmed in a real AWS account (will list account/region)
- 🔶 **Stubbed** — directory exists, schema TBD

| Example | Type | Status |
|---|---|---|
| [`cognito-end-to-end/`](./cognito-end-to-end/) | End-user identity layer (Cognito → Identity Pool → IAM → CodeArtifact) | ✅ Verified |
| [`mcp-server/`](./mcp-server/) | `descriptorType: MCP` | 📘 |
| [`knowledge-base/`](./knowledge-base/) | `descriptorType: CUSTOM` (`kind: knowledge-base`) | 📘 |
| [`lambda-tool/`](./lambda-tool/) | `descriptorType: CUSTOM` (`kind: lambda-tool`) | 📘 |
| [`guardrail/`](./guardrail/) | `descriptorType: CUSTOM` (`kind: guardrail`) | 📘 |

To extend: see the schema convention in
[`../docs/07-extending-to-other-resources.md`](../docs/07-extending-to-other-resources.md)
and copy one of the `register.py` files as a starting point.

PRs adding more examples (Cedar policy bundle, Step Functions
workflow, eval dataset, OpenAPI schema, etc.) are welcome.
