"""Register an already-uploaded wheel, verifying its CodeArtifact digest first."""

import argparse
import os
from pathlib import Path

from registry_blueprint.artifacts import safe_name
from registry_blueprint.registry import (
    client, find_registry, publish_record, skill_descriptors, verify_published_asset, wait_record,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--name", default="aws-cost-anomaly-triage")
    parser.add_argument("--version", default="0.1.0")
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "us-east-1"))
    parser.add_argument("--registry", default="skills-demo-registry")
    parser.add_argument("--registry-id", default=os.getenv("AGENT_REGISTRY_ARN"))
    parser.add_argument("--domain", default="skills-demo")
    parser.add_argument("--repository", default="skills-prod")
    parser.add_argument("--domain-owner")
    args = parser.parse_args()
    args.name = safe_name(args.name)
    control = client("agent-registry-control", args.region)
    registry_id = args.registry_id or find_registry(control, args.registry)
    owner = args.domain_owner or client("sts", args.region).get_caller_identity()["Account"]
    descriptors = skill_descriptors(
        args.wheel, args.name, args.version, args.domain, args.repository, owner, args.region,
    )
    verify_published_asset(client("codeartifact", args.region), descriptors, args.name, args.version)
    record = publish_record(
        control, registry_id, args.name, args.version, "Private FinOps skill", descriptors,
    )
    if record["status"] == "DRAFT":
        control.submit_registry_record_for_approval(
            registryId=registry_id, recordId=record["recordId"],
        )
        record = wait_record(control, registry_id, record["recordId"], "PENDING_APPROVAL")
    print(f"registry={registry_id} record={record['recordId']} status={record['status']}")


if __name__ == "__main__":
    main()
