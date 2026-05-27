"""Register an MCP server via URL-based discovery (synchronizationType=FROM_URL).

The Registry fetches server.json + tools/list from the URL itself and
populates the descriptor. The MCP server team writes zero publish code
beyond exposing a well-known endpoint with appropriate ACLs.

Two auth modes for the URL fetch:
  - public / IAM-signed (default in this script)
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

    sync_config = body["synchronizationConfiguration"]
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

    client = boto3.client("bedrock-agentcore-control", region_name=REGION)
    rid = find_registry_id(client)

    resp = client.create_registry_record(
        registryId=rid,
        name=body["name"],
        description=body["description"],
        descriptorType=body["descriptorType"],
        recordVersion=body["recordVersion"],
        synchronizationType=body["synchronizationType"],
        synchronizationConfiguration=sync_config,
    )
    record_id = resp["recordArn"].rsplit("/", 1)[-1]
    print(f"created record {record_id} in {rid}")
    print("Registry is fetching the URL and populating the descriptor.")
    print(
        "Subsequent revisions are produced automatically when the source "
        "MCP server's metadata changes."
    )

    deadline = time.time() + 120
    while time.time() < deadline:
        rec = client.get_registry_record(registryId=rid, recordId=record_id)
        if rec["status"] == "DRAFT":
            break
        if rec["status"] == "CREATE_FAILED":
            sys.exit(
                f"sync failed: {rec.get('statusReason') or '(no reason)'}"
            )
        time.sleep(3)
    else:
        sys.exit("timed out waiting for sync to finish")

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
