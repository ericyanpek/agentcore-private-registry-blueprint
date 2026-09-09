"""Consume only discoverable records and download a pinned CodeArtifact wheel."""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import boto3

from .artifacts import (
    INTEGRITY_KEY, MAX_ARTIFACT_BYTES, SOURCE_KEY, activate, safe_name, verify_wheel,
)


def registry_owner(registry_arn: str, region: str) -> str:
    match = re.fullmatch(
        r"arn:aws(?:-[a-z]+)*:agent-registry:([a-z0-9-]+):([0-9]{12}):registry/([a-zA-Z0-9]{12,16})",
        registry_arn,
    )
    if not match or match.group(1) != region:
        raise ValueError("Pass a GA Registry ARN in the selected region")
    return match.group(2)


def get_approved(data, registry_arn: str, record_id: str) -> dict:
    response = data.batch_get_discoverable_registry_record(
        entries=[{"registryId": registry_arn, "recordIds": [record_id]}],
    )
    found = response.get("registryRecords", [])
    if response.get("errors") or len(found) != 1:
        raise ValueError("Record is not available on the approved discovery plane")
    record = found[0]
    if (
        record["status"] != "APPROVED"
        or record["registryArn"] != registry_arn
        or record["recordId"] != record_id
        or record["recordType"] != "SKILL"
    ):
        raise ValueError("Discovery returned an unexpected or unapproved record")
    return record


def find_approved(data, registry_arn: str, name: str, version: str, query: str) -> dict:
    response = data.search_discoverable_registry_records(
        registryIds=[registry_arn], searchQuery=query, maxResults=20,
        filters={"$and": [
            {"recordType": {"$eq": "SKILL"}},
            {"name": {"$eq": name}},
            {"recordVersion": {"$eq": version}},
        ]},
    )
    matches = [
        record for record in response.get("registryRecords", [])
        if record.get("name") == name and record.get("recordVersion") == version
    ]
    if len(matches) != 1:
        raise ValueError("Expected one approved release; check name/version or retry after indexing")
    record = get_approved(data, registry_arn, matches[0]["recordId"])
    if record["name"] != name or record["recordVersion"] != version:
        raise ValueError("The selected release changed during discovery")
    return record


def definition_from_record(record: dict, expected_source: dict) -> tuple[dict, str]:
    descriptor = record["descriptors"]["agentSkillsDefinition"]
    if descriptor.get("dataSchemaVersion") != "0.1.0":
        raise ValueError("Unsupported skill definition schema")
    definition = json.loads(descriptor["data"])
    if definition.get("_meta", {}).get(SOURCE_KEY) != expected_source:
        raise ValueError("Record points outside the explicitly trusted CodeArtifact repository")
    packages = definition.get("packages", [])
    if (
        len(packages) != 1
        or packages[0].get("registryType") != "pypi"
        or packages[0].get("identifier") != record["name"]
        or packages[0].get("version") != record["recordVersion"]
    ):
        raise ValueError("Record identity and package identity disagree")
    safe_name(packages[0]["identifier"])
    return definition, descriptor["additionalData"]["skillMd"]["data"]


def download(codeartifact, definition: dict, directory: Path) -> Path:
    source = definition["_meta"][SOURCE_KEY]
    asset = definition["_meta"][INTEGRITY_KEY]["asset"]
    if not isinstance(asset, str) or Path(asset).name != asset or not asset.endswith(".whl"):
        raise ValueError("Invalid wheel asset name")
    package = definition["packages"][0]
    response = codeartifact.get_package_version_asset(
        domain=source["domain"], domainOwner=source["domainOwner"],
        repository=source["repository"], format="pypi",
        package=package["identifier"], packageVersion=package["version"], asset=asset,
    )
    body = response["asset"]
    wheel = directory / asset
    try:
        size = 0
        with wheel.open("xb") as output:
            for chunk in body.iter_chunks(chunk_size=65536):
                size += len(chunk)
                if size > MAX_ARTIFACT_BYTES:
                    raise ValueError("Downloaded wheel exceeds the 20 MiB blueprint limit")
                output.write(chunk)
    finally:
        body.close()
    return wheel


def consume(
    registry_arn: str, region: str, name: str, version: str, query: str,
    domain: str, repository: str, domain_owner: str | None, target: Path,
) -> Path:
    name = safe_name(name)
    owner = registry_owner(registry_arn, region)
    expected_source = {
        "domain": domain, "repository": repository,
        "domainOwner": domain_owner or owner, "region": region,
    }
    data = boto3.client("agent-registry", region_name=region)
    codeartifact = boto3.client("codeartifact", region_name=region)
    record = find_approved(data, registry_arn, name, version, query)
    definition, skill_md = definition_from_record(record, expected_source)
    with tempfile.TemporaryDirectory(prefix="verified-skill-") as temporary:
        wheel = download(codeartifact, definition, Path(temporary))
        inspected = verify_wheel(wheel, definition, skill_md)
        current = get_approved(data, registry_arn, record["recordId"])
        current_definition, current_md = definition_from_record(current, expected_source)
        if (
            current["recordVersion"] != record["recordVersion"]
            or current["name"] != record["name"]
            or current_definition != definition
            or current_md != skill_md
        ):
            raise ValueError("Approved release changed during download; retry discovery")
        return activate(inspected, target, name, {
            "registryArn": registry_arn, "recordId": record["recordId"],
            "recordArn": record["recordArn"], "recordVersion": version,
            "recordUpdatedAt": current["updatedAt"].isoformat(),
            "package": definition["packages"][0], "source": expected_source,
        })
