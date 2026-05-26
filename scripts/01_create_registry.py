"""Create an Agent Registry in us-east-1 with IAM auth + manual approval.

Usage:
    python3 01_create_registry.py
"""

from __future__ import annotations

import json

import boto3

REGION = "us-east-1"
REGISTRY_NAME = "skills-demo-registry"


def main() -> None:
    client = boto3.client("bedrock-agentcore-control", region_name=REGION)

    # Idempotent: reuse existing registry if name matches
    existing = client.list_registries().get("registries", [])
    for reg in existing:
        if reg.get("name") == REGISTRY_NAME:
            print("registry already exists:")
            print(json.dumps(reg, default=str, indent=2))
            return

    resp = client.create_registry(
        name=REGISTRY_NAME,
        description=(
            "Demo registry for the AWS Agent Registry + CodeArtifact "
            "skill-distribution pattern (text-only Python-package skills)."
        ),
        # Default authorizer is IAM. JWT/OAuth (Cognito/Okta/etc.) would
        # be configured by setting authorizerType=CUSTOM_JWT and
        # authorizerConfiguration.customJWTAuthorizer.
        # Manual approval — admin must explicitly approve every record
        # before it becomes discoverable.
        approvalConfiguration={"autoApproval": False},
    )

    print("created registry:")
    print(json.dumps(resp.get("registry", resp), default=str, indent=2))


if __name__ == "__main__":
    main()
