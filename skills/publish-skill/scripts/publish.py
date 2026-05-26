#!/usr/bin/env python3
"""Parameterized skill publisher.

Reads the current directory's pyproject.toml + SKILL.md, builds the
PyPI package, uploads to a CodeArtifact PyPI repo, registers the
metadata as an AGENT_SKILLS record in an Agent Registry, and
submits the record for approval.

Authoring assumption (the convention this script enforces):

    your-skill/
    ├── pyproject.toml                    # name, version, description
    ├── README.md                          # optional
    └── src/<package_name>/
        ├── __init__.py
        ├── postinstall.py                 # the activation entry point
        └── skill_files/
            ├── SKILL.md                   # frontmatter + body
            └── resources/                 # optional supporting files

The script is **stateless and idempotent** in the sense that
re-running it for the same (name, version) will fail loudly at
twine upload (CodeArtifact PyPI versions are immutable); to
re-publish, bump the version in pyproject.toml first.

Usage:
    publish-skill                              # uses ~/.skillpublish/config.toml
    publish-skill --domain my-domain --repository my-repo --registry my-registry
    publish-skill --dry-run                    # preflight only, no API calls
    publish-skill --skip-build                 # if you've already python -m build'd

IAM permissions required on the calling principal:
    - codeartifact:GetAuthorizationToken
    - codeartifact:GetRepositoryEndpoint
    - codeartifact:ReadFromRepository
    - codeartifact:PublishPackageVersion
    - sts:GetServiceBearerToken
    - sts:GetCallerIdentity
    - bedrock-agentcore:ListRegistries
    - bedrock-agentcore:ListRegistryRecords
    - bedrock-agentcore:CreateRegistryRecord
    - bedrock-agentcore:GetRegistryRecord
    - bedrock-agentcore:SubmitRegistryRecordForApproval

(See ../docs/09-publishing-iam.md for an Apache-2.0-licensed policy
template you can attach to a Publishers IAM Group.)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    try:
        import tomli as tomllib  # Python 3.9-3.10 fallback
    except ModuleNotFoundError:
        sys.exit(
            "Python <3.11 detected and 'tomli' is not installed. "
            "Install it with: pip install tomli"
        )

import boto3
from botocore.exceptions import ClientError

CONFIG_PATH = Path.home() / ".skillpublish" / "config.toml"


def load_config(path: Path = CONFIG_PATH) -> dict[str, str]:
    """Read default domain/repo/registry/region from a per-user config file.

    Format:
        [default]
        region = "us-east-1"
        codeartifact_domain = "skills-demo"
        codeartifact_repository = "skills-prod"
        registry_name = "skills-demo-registry"
    """
    if not path.exists():
        return {}
    with path.open("rb") as f:
        data = tomllib.load(f)
    return data.get("default", {})


def parse_args() -> argparse.Namespace:
    cfg = load_config()
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument(
        "--region", default=cfg.get("region", "us-east-1"),
        help="AWS region (default: us-east-1)",
    )
    p.add_argument(
        "--domain", default=cfg.get("codeartifact_domain"),
        help="CodeArtifact domain name",
    )
    p.add_argument(
        "--repository", default=cfg.get("codeartifact_repository"),
        help="CodeArtifact repository name",
    )
    p.add_argument(
        "--registry", default=cfg.get("registry_name"),
        help="Agent Registry name (not ARN — the script resolves it)",
    )
    p.add_argument(
        "--package-dir", default=".",
        help="Directory containing pyproject.toml (default: cwd)",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Run preflight checks only; do not call any external API",
    )
    p.add_argument(
        "--skip-build", action="store_true",
        help="Skip 'python -m build' (assume dist/ already populated)",
    )
    p.add_argument(
        "--auto-submit", action="store_true",
        help=(
            "Automatically submit for approval after CreateRegistryRecord. "
            "Default is to leave the record in DRAFT so the author can "
            "manually inspect via console first."
        ),
    )
    args = p.parse_args()
    missing = [
        k for k in ("domain", "repository", "registry")
        if getattr(args, k.replace("-", "_"), None) is None
    ]
    if missing:
        sys.exit(
            f"missing required: {', '.join('--' + m for m in missing)}\n"
            f"either pass on the command line or write defaults to {CONFIG_PATH}"
        )
    return args


def find_package_root(package_dir: Path) -> dict[str, Any]:
    """Resolve pyproject.toml + the on-disk SKILL.md path."""
    pyproject = package_dir / "pyproject.toml"
    if not pyproject.exists():
        sys.exit(f"no pyproject.toml in {package_dir.resolve()}")
    with pyproject.open("rb") as f:
        data = tomllib.load(f)
    project = data.get("project", {})
    name = project.get("name")
    version = project.get("version")
    description = project.get("description", "")
    if not name or not version:
        sys.exit("pyproject.toml must define [project].name and [project].version")

    # Find SKILL.md — convention: src/<pkg>/skill_files/SKILL.md.
    pkg_module = name.replace("-", "_")
    skill_md = (
        package_dir / "src" / pkg_module / "skill_files" / "SKILL.md"
    )
    if not skill_md.exists():
        sys.exit(
            f"no SKILL.md at expected path {skill_md.relative_to(package_dir)} — "
            f"the publisher convention requires src/<pkg_name>/skill_files/SKILL.md "
            f"so it ships inside the wheel."
        )
    skill_md_text = skill_md.read_text(encoding="utf-8")
    if not skill_md_text.lstrip().startswith("---"):
        sys.exit("SKILL.md is missing the YAML frontmatter (--- ... ---)")

    return {
        "name": name,
        "version": version,
        "description": description,
        "skill_md": skill_md_text,
        "package_dir": package_dir,
    }


def preflight(args: argparse.Namespace, project: dict[str, Any]) -> None:
    print("=== preflight ===")
    print(f"  project: {project['name']}=={project['version']}")
    print(f"  description: {project['description'][:80]}")
    print(f"  skill md size: {len(project['skill_md'])} chars")
    print(f"  region: {args.region}")
    print(f"  CodeArtifact: {args.domain}/{args.repository}")
    print(f"  Registry: {args.registry}")

    # AWS identity sanity
    try:
        sts = boto3.client("sts", region_name=args.region)
        ident = sts.get_caller_identity()
        print(f"  IAM principal: {ident['Arn']}")
    except ClientError as e:
        sys.exit(f"AWS credentials check failed: {e}")

    # Required CLIs
    for tool in ("aws", "twine"):
        if not shutil.which(tool):
            sys.exit(
                f"required CLI not on PATH: {tool}. Install with "
                f"'pip install twine' (twine) or follow AWS CLI install docs (aws)."
            )
    if not shutil.which("python3") and not shutil.which("python"):
        sys.exit("python interpreter not found")

    print("preflight OK\n")


def build_wheel(args: argparse.Namespace, project: dict[str, Any]) -> None:
    print("=== build ===")
    if args.skip_build:
        print("skipped (--skip-build)")
        return
    cmd = [sys.executable, "-m", "build", str(project["package_dir"])]
    print(f"  $ {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    print()


def codeartifact_login(args: argparse.Namespace) -> None:
    print("=== codeartifact login ===")
    cmd = [
        "aws", "codeartifact", "login",
        "--tool", "twine",
        "--domain", args.domain,
        "--repository", args.repository,
        "--region", args.region,
    ]
    print(f"  $ {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    print()


def twine_upload(args: argparse.Namespace, project: dict[str, Any]) -> None:
    print("=== twine upload ===")
    dist = project["package_dir"] / "dist"
    artifacts = sorted(p for p in dist.iterdir() if p.is_file())
    if not artifacts:
        sys.exit(f"no artifacts in {dist} — did the build step succeed?")
    cmd = [
        sys.executable, "-m", "twine", "upload",
        "--repository", "codeartifact",
        *(str(p) for p in artifacts),
    ]
    print(f"  $ {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    print()


def find_registry_id(client, registry_name: str) -> str:
    for r in client.list_registries().get("registries", []):
        if r.get("name") == registry_name:
            return r["registryArn"].rsplit("/", 1)[-1]
    sys.exit(
        f"registry {registry_name!r} not found in this account/region. "
        f"Did you run 'cdk deploy --all' yet?"
    )


def build_skill_definition(
    args: argparse.Namespace, project: dict[str, Any], account_id: str,
) -> str:
    """Construct the skillDefinition JSON inline content."""
    code_artifact_index = (
        f"https://{args.domain}-{account_id}.d.codeartifact."
        f"{args.region}.amazonaws.com/pypi/{args.repository}/simple/"
    )
    definition = {
        "packages": [
            {
                "registryType": "pypi",
                "identifier": project["name"],
                "version": project["version"],
            }
        ],
        "_meta": {
            "com.example.codeartifact": {
                "domain": args.domain,
                "repository": args.repository,
                "region": args.region,
                "indexUrl": code_artifact_index,
            },
            "com.example.activate": {
                "postInstallCommand": (
                    "install-" + project["name"]
                ),
                "skillTargetDir": (
                    f"~/.claude/skills/{project['name']}/"
                ),
            },
        },
    }
    return json.dumps(definition, indent=2)


def create_record(
    args: argparse.Namespace, project: dict[str, Any],
) -> tuple[str, str]:
    print("=== register ===")
    ctrl = boto3.client("bedrock-agentcore-control", region_name=args.region)
    registry_id = find_registry_id(ctrl, args.registry)
    account_id = boto3.client("sts").get_caller_identity()["Account"]
    skill_def = build_skill_definition(args, project, account_id)

    # If a record with this (name) already exists, fail clearly.
    for r in ctrl.list_registry_records(registryId=registry_id).get(
        "registryRecords", []
    ):
        if r.get("name") == project["name"]:
            print(
                f"  record {project['name']!r} already exists "
                f"(status={r['status']}, version={r.get('recordVersion')})."
            )
            print(
                f"  This script does not auto-update existing records. "
                f"To publish a new version, bump pyproject.toml [project].version "
                f"and re-run. To replace metadata at the same version, use "
                f"the AWS console or boto3 update_registry_record directly."
            )
            sys.exit(1)

    resp = ctrl.create_registry_record(
        registryId=registry_id,
        name=project["name"],
        description=project["description"][:4000] or project["name"],
        descriptorType="AGENT_SKILLS",
        descriptors={
            "agentSkills": {
                "skillMd": {"inlineContent": project["skill_md"]},
                "skillDefinition": {
                    "schemaVersion": "0.1.0",
                    "inlineContent": skill_def,
                },
            }
        },
        recordVersion=project["version"],
    )
    record_arn = resp["recordArn"]
    record_id = record_arn.rsplit("/", 1)[-1]
    print(f"  record arn: {record_arn}")

    # Wait for DRAFT
    deadline = time.time() + 60
    while time.time() < deadline:
        rec = ctrl.get_registry_record(
            registryId=registry_id, recordId=record_id
        )
        if rec.get("status") == "DRAFT":
            break
        time.sleep(2)
    else:
        sys.exit(f"timed out waiting for DRAFT (record {record_id})")
    print(f"  status: DRAFT")

    return registry_id, record_id


def submit_for_approval(
    args: argparse.Namespace, registry_id: str, record_id: str,
) -> None:
    if not args.auto_submit:
        print(
            "\nrecord is in DRAFT. To submit for approval, run:\n"
            "  aws bedrock-agentcore-control submit-registry-record-for-approval "
            f"\\\n    --registry-id {registry_id} --record-id {record_id} "
            f"--region {args.region}\n"
            "or pass --auto-submit on the next run.\n"
        )
        return
    print("=== submit for approval ===")
    ctrl = boto3.client("bedrock-agentcore-control", region_name=args.region)
    ctrl.submit_registry_record_for_approval(
        registryId=registry_id, recordId=record_id
    )
    print("  submitted (status: PENDING_APPROVAL).")
    print(
        "  A curator must call update-registry-record-status to move "
        "it to APPROVED before it appears in search."
    )


def main() -> int:
    args = parse_args()
    project = find_package_root(Path(args.package_dir).resolve())
    preflight(args, project)
    if args.dry_run:
        print("--dry-run set; stopping before any external calls.")
        return 0
    build_wheel(args, project)
    codeartifact_login(args)
    twine_upload(args, project)
    registry_id, record_id = create_record(args, project)
    submit_for_approval(args, registry_id, record_id)
    print("\ndone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
