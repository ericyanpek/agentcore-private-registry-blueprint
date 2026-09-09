"""Register an MCP server via GA descriptor source synchronization.

The Registry fetches server.json + tools/list from the URL itself and
populates the descriptor. The MCP server team writes zero publish code
beyond exposing a well-known endpoint with appropriate ACLs.

Two auth modes for the URL fetch:
  - public, unauthenticated endpoint (default in this script)
  - OAuth2 — pass --credential-provider <arn> when the URL needs a
    bearer token; the credential provider is created via
    AgentCore Identity (out of scope here).

Usage:
    python3 register-url-sync.py
    python3 register-url-sync.py --credential-provider <arn>
"""

from __future__ import annotations

import argparse
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
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--credential-provider",
        help="ARN of an OAuth2 credential provider (AgentCore Identity) "
        "for fetching a URL that requires a bearer token.",
    )
    args = parser.parse_args()

    body = json.loads((HERE / "example-record-url-sync.json").read_text())
    if "example.internal" in json.dumps(body):
        sys.exit(
            "example-record-url-sync.json points at example.internal — "
            "swap in a real MCP server URL before running."
        )

    sync_config = body["descriptors"]["mcpServer"]["source"]
    if args.credential_provider:
        sync_config["fromUrl"]["credentialProviderConfigurations"] = [
            {
                "credentialProviderType": "OAUTH",
                "credentialProvider": {
                    "oauthCredentialProvider": {
                        "providerArn": args.credential_provider,
                        "grantType": "CLIENT_CREDENTIALS",
                    }
                },
            }
        ]

    client = boto3.client("agent-registry-control", region_name=REGION)
    rid = find_registry_id(client)

    resp = client.create_registry_record(
        registryId=rid,
        name=body["name"],
        displayName=body["name"],
        description=body["description"],
        recordType=body["recordType"],
        recordVersion=body["recordVersion"],
        descriptors=body["descriptors"],
    )
    record_id = resp["recordArn"].rsplit("/", 1)[-1]
    print(f"created record {record_id} in {rid}")
    print("Registry is fetching the URL and populating the descriptor.")
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
