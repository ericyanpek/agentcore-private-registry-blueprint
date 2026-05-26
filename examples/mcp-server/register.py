"""Register an MCP server record (descriptorType=MCP).

Reads example-record.json, calls CreateRegistryRecord, polls for
DRAFT, submits for approval. Mirrors the structure of
scripts/02_register_skill.py — only the descriptor body changes.

Usage:
    python3 register.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import boto3

REGION = "us-east-1"
REGISTRY_NAME = "skills-demo-registry"  # reuse the Day-1 registry
HERE = Path(__file__).parent


def find_registry_id(client) -> str:
    for r in client.list_registries().get("registries", []):
        if r.get("name") == REGISTRY_NAME:
            return r["registryArn"].rsplit("/", 1)[-1]
    sys.exit(f"registry {REGISTRY_NAME!r} not found")


def main() -> None:
    body = json.loads((HERE / "example-record.json").read_text())
    if "example.internal" in json.dumps(body):
        sys.exit(
            "example-record.json points at example.internal — "
            "swap in a real MCP server endpoint before running."
        )
    client = boto3.client("bedrock-agentcore-control", region_name=REGION)
    rid = find_registry_id(client)

    descriptors = body["descriptors"]
    # Inline JSON content must be a string, not a dict
    descriptors["mcp"]["server"]["inlineContent"] = json.dumps(
        descriptors["mcp"]["server"]["inlineContent"]
    )
    if "tools" in descriptors["mcp"]:
        descriptors["mcp"]["tools"]["inlineContent"] = json.dumps(
            descriptors["mcp"]["tools"]["inlineContent"]
        )

    resp = client.create_registry_record(
        registryId=rid,
        name=body["name"],
        description=body["description"],
        descriptorType=body["descriptorType"],
        descriptors=descriptors,
        recordVersion=body["recordVersion"],
    )
    record_id = resp["recordArn"].rsplit("/", 1)[-1]
    print(f"created record {record_id} in {rid}")

    deadline = time.time() + 60
    while time.time() < deadline:
        rec = client.get_registry_record(registryId=rid, recordId=record_id)
        if rec["status"] == "DRAFT":
            break
        time.sleep(2)
    else:
        sys.exit("timed out waiting for DRAFT")

    client.submit_registry_record_for_approval(
        registryId=rid, recordId=record_id
    )
    print(f"submitted for approval (record id: {record_id})")
    print("approve via the AgentCore console, or:")
    print(
        "  aws bedrock-agentcore-control update-registry-record-status \\\n"
        f"    --registry-id {rid} --record-id {record_id} \\\n"
        "    --status APPROVED --status-reason 'reviewed'"
    )


if __name__ == "__main__":
    main()
