"""GA control-plane helpers for publishers and curators."""

from __future__ import annotations

import json
import time
from pathlib import Path

import boto3

from .artifacts import INTEGRITY_KEY, SOURCE_KEY, inspect_wheel, safe_name


def client(service: str, region: str):
    session = boto3.Session(region_name=region)
    if service not in session.get_available_services():
        raise RuntimeError("Install the blueprint dependencies; the GA Registry SDK is required")
    return session.client(service)


def find_registry(control, name: str) -> str:
    for page in control.get_paginator("list_registries").paginate():
        for registry in page.get("registries", []):
            if registry["name"] == name:
                if registry["status"] != "READY":
                    raise ValueError(f"Registry {name} is not READY")
                return registry["registryArn"]
    raise ValueError(f"Registry {name!r} not found")


def records(control, registry_id: str):
    for page in control.get_paginator("list_registry_records").paginate(registryId=registry_id):
        yield from page.get("registryRecords", [])


def wait_record(control, registry_id: str, record_id: str, target: str, timeout: int = 120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        record = control.get_registry_record(registryId=registry_id, recordId=record_id)
        status = record["status"]
        if status == target:
            return record
        if status.endswith("_FAILED") or status in ("REJECTED", "DEPRECATED"):
            raise ValueError(f"Record entered {status}: {record.get('statusReason', '')}")
        time.sleep(2)
    raise TimeoutError(f"Record {record_id} did not reach {target}")


def skill_descriptors(
    wheel: Path, name: str, version: str, domain: str, repository: str,
    domain_owner: str, region: str,
) -> dict:
    name = safe_name(name)
    inspected = inspect_wheel(wheel, name, version)
    definition = {
        "packages": [{"registryType": "pypi", "identifier": name, "version": version}],
        "_meta": {
            SOURCE_KEY: {
                "domain": domain,
                "repository": repository,
                "domainOwner": domain_owner,
                "region": region,
            },
            INTEGRITY_KEY: {
                field: inspected[field]
                for field in ("asset", "sha256", "skillMdSha256", "skillPath")
            },
        },
    }
    return {
        "agentSkillsDefinition": {
            "data": json.dumps(definition, sort_keys=True),
            "dataSchemaVersion": "0.1.0",
            "additionalData": {"skillMd": {"data": inspected["skillMd"]}},
        }
    }


def verify_published_asset(codeartifact, descriptors: dict, name: str, version: str) -> None:
    definition = json.loads(descriptors["agentSkillsDefinition"]["data"])
    source = definition["_meta"][SOURCE_KEY]
    integrity = definition["_meta"][INTEGRITY_KEY]
    for page in codeartifact.get_paginator("list_package_version_assets").paginate(
        domain=source["domain"], domainOwner=source["domainOwner"],
        repository=source["repository"], format="pypi", package=name,
        packageVersion=version,
    ):
        for asset in page.get("assets", []):
            if asset["name"] == integrity["asset"]:
                if asset.get("hashes", {}).get("SHA-256") != integrity["sha256"]:
                    raise ValueError("Uploaded CodeArtifact asset differs from the built wheel")
                return
    raise ValueError("The selected wheel is not present in CodeArtifact")


def publish_record(control, registry_id: str, name: str, version: str, description: str, descriptors: dict):
    for summary in records(control, registry_id):
        if summary["name"] == name and summary.get("recordVersion") == version:
            record = control.get_registry_record(
                registryId=registry_id, recordId=summary["recordId"],
            )
            current = record.get("descriptors", {}).get("agentSkillsDefinition", {})
            requested = descriptors["agentSkillsDefinition"]
            if (
                record.get("recordType") != "SKILL"
                or current.get("dataSchemaVersion") != requested["dataSchemaVersion"]
                or json.loads(current.get("data", "{}")) != json.loads(requested["data"])
                or current.get("additionalData", {}).get("skillMd", {}).get("data")
                != requested["additionalData"]["skillMd"]["data"]
            ):
                raise ValueError("This name/version already describes different content; bump the version")
            if record["status"] not in ("DRAFT", "PENDING_APPROVAL", "APPROVED"):
                raise ValueError(f"Existing release is {record['status']}; publish a new version")
            return record
    response = control.create_registry_record(
        registryId=registry_id, name=name, displayName=name,
        recordType="SKILL", recordVersion=version,
        description=description[:4096] or name, descriptors=descriptors,
    )
    return wait_record(control, registry_id, response["recordArn"].rsplit("/", 1)[-1], "DRAFT")
