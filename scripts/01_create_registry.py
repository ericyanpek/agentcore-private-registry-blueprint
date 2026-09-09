"""Create an IAM-authorized GA registry with manual approval (alternative to CDK)."""

import argparse
import json
import os

from registry_blueprint.registry import client


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "us-east-1"))
    parser.add_argument("--name", default="skills-demo-registry")
    args = parser.parse_args()
    control = client("agent-registry-control", args.region)
    for page in control.get_paginator("list_registries").paginate():
        for registry in page.get("registries", []):
            if registry["name"] == args.name:
                print(json.dumps(registry, default=str, indent=2))
                return
    response = control.create_registry(
        name=args.name, description="Private skill distribution blueprint",
        discoveryConfiguration={"authorizerType": "AWS_IAM"},
        approvalConfiguration={"autoApprovalRules": []},
    )
    control.get_waiter("registry_ready").wait(registryId=response["registryArn"])
    print(json.dumps(response, default=str, indent=2))


if __name__ == "__main__":
    main()
