"""Register an MCP server record (recordType=MCP).

Reads example-record.json, calls CreateRegistryRecord, polls for
DRAFT, submits for approval. Mirrors the structure of
scripts/02_register_skill.py — only the descriptor body changes.

Usage:
    python3 register.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import boto3
from registry_blueprint.registry import find_registry, wait_record

REGION = "us-east-1"
REGISTRY_NAME = "skills-demo-registry"  # reuse the Day-1 registry
HERE = Path(__file__).parent


def find_registry_id(client) -> str:
    return find_registry(client, REGISTRY_NAME)


def main() -> None:
    body = json.loads((HERE / "example-record.json").read_text())
    if "example.internal" in json.dumps(body):
        sys.exit(
            "example-record.json points at example.internal — "
            "swap in a real MCP server endpoint before running."
        )
    client = boto3.client("agent-registry-control", region_name=REGION)
    rid = find_registry_id(client)

    descriptors = body["descriptors"]
    descriptors["mcpServer"]["data"] = json.dumps(
        descriptors["mcpServer"]["data"]
    )
    if "tools" in descriptors["mcpServer"].get("additionalData", {}):
        descriptors["mcpServer"]["additionalData"]["tools"]["data"] = json.dumps(
            descriptors["mcpServer"]["additionalData"]["tools"]["data"]
        )

    resp = client.create_registry_record(
        registryId=rid,
        name=body["name"],
        displayName=body["name"],
        description=body["description"],
        recordType=body["recordType"],
        descriptors=descriptors,
        recordVersion=body["recordVersion"],
    )
    record_id = resp["recordArn"].rsplit("/", 1)[-1]
    print(f"created record {record_id} in {rid}")

    wait_record(client, rid, record_id, "DRAFT")

    client.submit_registry_record_for_approval(
        registryId=rid, recordId=record_id
    )
    print(f"submitted for approval (record id: {record_id})")
    print("approve via the AgentCore console, or:")
    print(
        "  aws agent-registry-control update-registry-record-status \\\n"
        f"    --registry-id {rid} --record-id {record_id} \\\n"
        "    --status APPROVED --status-reason 'reviewed'"
    )


if __name__ == "__main__":
    main()
