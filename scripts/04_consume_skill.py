"""Consumer flow.

A developer (or an AI agent) wants to find and install a skill.

  1. SearchRegistryRecords(query="cost anomaly") via boto3 data plane
  2. From the matched record, GetRegistryRecord to read the full
     skillDefinition, parse packages[] to find the pypi identifier
  3. Read _meta.com.example.codeartifact for the index URL,
     run `aws codeartifact login --tool pip` to get a fresh token
  4. pip install the package into a venv
  5. Run the postinstall console script to materialize the skill
     under ~/.claude/skills/

This script demonstrates the entire path end-to-end from a fresh venv.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import boto3

REGION = "us-east-1"
SEARCH_QUERY = "cost anomaly triage"


def search_registry(query: str) -> dict:
    """Use the data-plane SearchRegistryRecords API.

    The data-plane client is `bedrock-agentcore` (no -control suffix).
    Search requires the registry's full ARN(s).
    """
    ctrl = boto3.client("bedrock-agentcore-control", region_name=REGION)
    arns = [
        r["registryArn"]
        for r in ctrl.list_registries().get("registries", [])
        if r.get("status") == "READY"
    ]
    if not arns:
        sys.exit("no READY registries found")

    data = boto3.client("bedrock-agentcore", region_name=REGION)
    resp = data.search_registry_records(
        registryIds=arns,
        searchQuery=query,
        maxResults=5,
    )
    hits = resp.get("registryRecords", [])
    if not hits:
        sys.exit(f"no hits for query {query!r}")
    print(f"search hits ({len(hits)}):")
    for h in hits:
        print(
            f"  {h.get('name')} "
            f"({h.get('descriptorType')}, status={h.get('status')}, "
            f"v={h.get('recordVersion')})"
        )
    # Take the first AGENT_SKILLS hit
    for h in hits:
        if h.get("descriptorType") == "AGENT_SKILLS":
            return h
    sys.exit("no AGENT_SKILLS record in hits")


def fetch_skill_definition(record: dict) -> dict:
    ctrl = boto3.client("bedrock-agentcore-control", region_name=REGION)
    full = ctrl.get_registry_record(
        registryId=record["registryArn"].rsplit("/", 1)[-1],
        recordId=record["recordId"],
    )
    raw = (
        full["descriptors"]["agentSkills"]["skillDefinition"]["inlineContent"]
    )
    return json.loads(raw)


def codeartifact_index_url(definition: dict) -> tuple[str, str, str, str]:
    meta = definition.get("_meta", {}).get("com.example.codeartifact", {})
    return (
        meta["domain"],
        meta["repository"],
        meta["region"],
        meta["indexUrl"],
    )


def install_into_venv(
    pkg_name: str, pkg_version: str, index_url: str, ca_domain: str,
    ca_repo: str, ca_region: str, venv_dir: Path,
) -> Path:
    print(f"\ncreating fresh venv at {venv_dir}")
    subprocess.run(
        [sys.executable, "-m", "venv", str(venv_dir)], check=True,
    )
    pip = venv_dir / "bin" / "pip"

    # Refresh CodeArtifact token via aws cli; this writes ~/.pip/pip.conf
    # and ~/.config/pip/pip.conf with the fresh token.
    print("refreshing CodeArtifact pip token...")
    subprocess.run(
        [
            "aws", "codeartifact", "login",
            "--tool", "pip",
            "--domain", ca_domain,
            "--repository", ca_repo,
            "--region", ca_region,
        ],
        check=True,
    )

    print(f"pip install {pkg_name}=={pkg_version} (from CodeArtifact)")
    subprocess.run(
        [str(pip), "install", "--quiet", f"{pkg_name}=={pkg_version}"],
        check=True,
    )
    return venv_dir


def activate_skill(venv_dir: Path, postinstall_cmd: str,
                   target_dir: Path) -> None:
    bin_path = venv_dir / "bin" / postinstall_cmd
    if not bin_path.exists():
        sys.exit(f"postinstall command not found: {bin_path}")
    print(f"\nrunning {bin_path} --target-dir {target_dir}")
    subprocess.run(
        [str(bin_path), "--target-dir", str(target_dir)], check=True,
    )


def main() -> None:
    print(f"searching registry for: {SEARCH_QUERY!r}")
    hit = search_registry(SEARCH_QUERY)
    print(f"\npicked: {hit['name']} ({hit['recordId']})")

    definition = fetch_skill_definition(hit)
    print("\nskill definition:")
    print(json.dumps(definition, indent=2))

    pkg = definition["packages"][0]
    if pkg["registryType"] != "pypi":
        sys.exit(f"unexpected registryType: {pkg['registryType']}")
    pkg_name, pkg_version = pkg["identifier"], pkg["version"]
    ca_domain, ca_repo, ca_region, index_url = codeartifact_index_url(
        definition
    )
    activate = definition["_meta"]["com.example.activate"]

    target_dir = Path(
        os.path.expanduser(activate["skillTargetDir"])
    ).parent  # ~/.claude/skills/

    with tempfile.TemporaryDirectory(prefix="skill-consume-") as tmp:
        venv = Path(tmp) / "venv"
        install_into_venv(
            pkg_name, pkg_version, index_url, ca_domain, ca_repo, ca_region,
            venv,
        )
        activate_skill(venv, activate["postInstallCommand"], target_dir)

    installed = target_dir / pkg_name
    print(f"\nfinal artifact tree at {installed}:")
    for p in sorted(installed.rglob("*")):
        print(f"  {p.relative_to(installed)}")


if __name__ == "__main__":
    main()
