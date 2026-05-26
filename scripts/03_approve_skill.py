"""Submit and approve the demo skill record.

In a real org, the publisher submits and a different IAM principal
(admin) approves. For demo we do both with the same identity. The
status machine is:

  DRAFT ──submit──> PENDING_APPROVAL ──update_status──> APPROVED
                                    └──update_status──> REJECTED

Only APPROVED records are visible to consumers via search.
"""

from __future__ import annotations

import json
import sys
import time

import boto3
from botocore.exceptions import ClientError

REGION = "us-east-1"
REGISTRY_NAME = "skills-demo-registry"
RECORD_NAME = "aws-cost-anomaly-triage"


def find_ids(client) -> tuple[str, str, str]:
    registry_id = None
    for r in client.list_registries().get("registries", []):
        if r.get("name") == REGISTRY_NAME:
            registry_id = r["registryArn"].rsplit("/", 1)[-1]
            break
    if not registry_id:
        sys.exit(f"registry {REGISTRY_NAME!r} not found")
    for rec in client.list_registry_records(registryId=registry_id).get(
        "registryRecords", []
    ):
        if rec.get("name") == RECORD_NAME:
            return registry_id, rec["recordId"], rec["status"]
    sys.exit(f"record {RECORD_NAME!r} not found in {registry_id}")


def wait_state(client, registry_id, record_id, target, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        rec = client.get_registry_record(
            registryId=registry_id, recordId=record_id
        )
        if rec.get("status") == target:
            return rec
        time.sleep(2)
    sys.exit(f"timeout waiting for {target}")


def main() -> None:
    client = boto3.client("bedrock-agentcore-control", region_name=REGION)
    registry_id, record_id, status = find_ids(client)
    print(f"registry={registry_id} record={record_id} status={status}")

    if status == "DRAFT":
        print("submitting for approval...")
        client.submit_registry_record_for_approval(
            registryId=registry_id, recordId=record_id
        )
        rec = wait_state(client, registry_id, record_id, "PENDING_APPROVAL")
        status = rec["status"]
        print(f"now {status}")

    if status == "PENDING_APPROVAL":
        print("approving...")
        try:
            client.update_registry_record_status(
                registryId=registry_id,
                recordId=record_id,
                status="APPROVED",
                statusReason="demo: approved by SA after content review",
            )
        except ClientError as e:
            sys.exit(f"approval failed: {e}")
        rec = wait_state(client, registry_id, record_id, "APPROVED")
        status = rec["status"]
        print(f"now {status}")

    if status == "APPROVED":
        print("\nrecord is APPROVED — visible to consumers via search.")
        rec = client.get_registry_record(
            registryId=registry_id, recordId=record_id
        )
        print(json.dumps({
            "name": rec["name"],
            "recordArn": rec["recordArn"],
            "status": rec["status"],
            "version": rec.get("recordVersion"),
        }, default=str, indent=2))


if __name__ == "__main__":
    main()
