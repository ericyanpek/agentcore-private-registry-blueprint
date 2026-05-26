# Example — registering a Bedrock Guardrail (CUSTOM)

Status: 📘 Documented (skeleton). Swap the placeholder Guardrail id
with a real one before running.

## What this does

Registers an existing Bedrock Guardrail as a
`descriptorType: CUSTOM` record with `kind: guardrail`. Agents and
developers can search for "PII redaction" or "financial-advice block"
and find the guardrail, then attach it to their model invocation
configuration.

## Why this matters

Bedrock Guardrails today are **per-account resources** that any agent
can attach to a model invocation, but there's no built-in
catalog of "which guardrails exist and what they're for". Without a
registry record, security teams can't audit which agents reuse the
canonical safety configs vs. roll their own.

## Files

- `example-record.json` — body for `CreateRegistryRecord`
- `register.py` — boto3 script

## TODO

- [ ] Verify end-to-end against a real Bedrock Guardrail
- [ ] Show consumer pattern: agent reads the record's `target.id`
      and `target.version`, attaches to `bedrock-runtime:Converse`
- [ ] Add a Cedar-policy-bundle CUSTOM example (`kind: cedar-policy`)
- [ ] Add a Step Functions CUSTOM example (`kind: workflow`)
