"""Register a Bedrock Guardrail as a CUSTOM (kind=guardrail) record.

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
REGISTRY_NAME = "skills-demo-registry"
HERE = Path(__file__).parent


def find_registry_id(client) -> str:
    for r in client.list_registries().get("registries", []):
        if r.get("name") == REGISTRY_NAME:
            return r["registryArn"].rsplit("/", 1)[-1]
    sys.exit(f"registry {REGISTRY_NAME!r} not found")


def main() -> None:
    body = json.loads((HERE / "example-record.json").read_text())
    if "REPLACE_ME" in json.dumps(body):
        sys.exit(
            "example-record.json contains REPLACE_ME placeholders — "
            "swap in a real Guardrail id before running."
        )

    client = boto3.client("bedrock-agentcore-control", region_name=REGION)
    rid = find_registry_id(client)

    resp = client.create_registry_record(
        registryId=rid,
        name=body["name"],
        description=body["description"],
        descriptorType="CUSTOM",
        descriptors={
            "custom": {"inlineContent": json.dumps(body["customBody"])},
        },
        recordVersion=body["recordVersion"],
    )
    record_id = resp["recordArn"].rsplit("/", 1)[-1]
    print(f"created CUSTOM record {record_id} (kind=guardrail)")

    deadline = time.time() + 60
    while time.time() < deadline:
        rec = client.get_registry_record(registryId=rid, recordId=record_id)
        if rec["status"] == "DRAFT":
            break
        time.sleep(2)

    client.submit_registry_record_for_approval(
        registryId=rid, recordId=record_id
    )
    print("submitted for approval")


if __name__ == "__main__":
    main()
