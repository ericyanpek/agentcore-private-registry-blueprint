# Example — registering a Bedrock Knowledge Base (CUSTOM)

Status: 📘 Documented (skeleton). Replace the placeholder ARN with
a real Knowledge Base in your account.

## What this does

Registers an existing Bedrock Knowledge Base into the registry as a
`descriptorType: CUSTOM` record with `kind: knowledge-base`. After
approval, agents and developers find it via search and use the
attached metadata to decide whether to query it.

## Why this matters

Without a registry record, KBs are invisible to anyone outside the
team that created them. Agents can be configured to use a KB ARN
directly, but **discovery** ("which KBs exist that I should
consider?") requires a catalog. That's what the registry adds.

## Files

- `example-record.json` — body for `CreateRegistryRecord`
- `register.py` — boto3 script

## TODO

- [ ] Verify end-to-end against a real Bedrock KB
- [ ] Add a discovery example: `search_registry_records` filtering on `kind: knowledge-base`
- [ ] Add an OpenSearch Serverless variant (different `target.service`)
