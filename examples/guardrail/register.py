"""Register a Bedrock Guardrail as a CUSTOM (kind=guardrail) record.

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
REGISTRY_NAME = "skills-demo-registry"
HERE = Path(__file__).parent


def find_registry_id(client) -> str:
    return find_registry(client, REGISTRY_NAME)


def main() -> None:
    body = json.loads((HERE / "example-record.json").read_text())
    if "REPLACE_ME" in json.dumps(body):
        sys.exit(
            "example-record.json contains REPLACE_ME placeholders — "
            "swap in a real Guardrail id before running."
        )

    client = boto3.client("agent-registry-control", region_name=REGION)
    rid = find_registry_id(client)

    resp = client.create_registry_record(
        registryId=rid,
        name=body["name"],
        displayName=body["name"],
        description=body["description"],
        recordType="CUSTOM",
        descriptors={
            "custom": {"data": json.dumps(body["customBody"])},
        },
        recordVersion=body["recordVersion"],
    )
    record_id = resp["recordArn"].rsplit("/", 1)[-1]
    print(f"created CUSTOM record {record_id} (kind=guardrail)")

    wait_record(client, rid, record_id, "DRAFT")

    client.submit_registry_record_for_approval(
        registryId=rid, recordId=record_id
    )
    print("submitted for approval")


if __name__ == "__main__":
    main()
