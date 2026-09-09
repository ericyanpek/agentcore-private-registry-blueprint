"""Approve one explicitly selected release as the curator, not as the consumer."""

import argparse
import os

from registry_blueprint.registry import client, find_registry, records, wait_record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry-id", default=os.getenv("AGENT_REGISTRY_ARN"))
    parser.add_argument("--registry", default="skills-demo-registry")
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "us-east-1"))
    parser.add_argument("--name", default="aws-cost-anomaly-triage")
    parser.add_argument("--version", default="0.1.0")
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    control = client("agent-registry-control", args.region)
    registry_id = args.registry_id or find_registry(control, args.registry)
    matches = [
        record for record in records(control, registry_id)
        if record["name"] == args.name and record.get("recordVersion") == args.version
    ]
    if len(matches) != 1:
        raise ValueError("Expected exactly one record with the requested name/version")
    record = control.get_registry_record(registryId=registry_id, recordId=matches[0]["recordId"])
    if record["status"] == "APPROVED":
        print(f"Already approved: {record['recordArn']}")
        return
    if record["status"] != "PENDING_APPROVAL":
        raise ValueError("Publisher must submit the release for approval first")
    control.update_registry_record_status(
        registryId=registry_id, recordId=record["recordId"],
        status="APPROVED", statusReason=args.reason,
    )
    approved = wait_record(control, registry_id, record["recordId"], "APPROVED")
    print(f"Approved: {approved['recordArn']}; allow time for discovery indexing")


if __name__ == "__main__":
    main()
