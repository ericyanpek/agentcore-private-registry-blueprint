"""Build one skill wheel, publish it, and register its exact bytes with GA Registry."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

from packaging.utils import canonicalize_name

from registry_blueprint.artifacts import inspect_wheel
from registry_blueprint.registry import (
    client, find_registry, publish_record, skill_descriptors, verify_published_asset,
)


def parse_args() -> argparse.Namespace:
    config_path = Path.home() / ".skillpublish" / "config.toml"
    config = tomllib.loads(config_path.read_text()).get("default", {}) if config_path.exists() else {}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", default=config.get("region", "us-east-1"))
    parser.add_argument("--domain", default=config.get("codeartifact_domain", "skills-demo"))
    parser.add_argument("--repository", default=config.get("codeartifact_repository", "skills-prod"))
    parser.add_argument("--domain-owner")
    parser.add_argument("--registry", default=config.get("registry_name", "skills-demo-registry"))
    parser.add_argument("--registry-id", default=os.getenv("AGENT_REGISTRY_ARN"))
    parser.add_argument("--package-dir", type=Path, default=Path.cwd())
    parser.add_argument("--wheel", type=Path, help="Use an existing wheel instead of building")
    parser.add_argument("--skip-build", action="store_true", help="Require one matching wheel in dist/")
    parser.add_argument("--skip-upload", action="store_true", help="Verify an already uploaded wheel")
    parser.add_argument("--dry-run", action="store_true", help="Local metadata checks only; no AWS/build calls")
    parser.add_argument("--auto-submit", action="store_true")
    return parser.parse_args()


def upload(args: argparse.Namespace, wheel: Path, owner: str) -> None:
    codeartifact = client("codeartifact", args.region)
    endpoint = codeartifact.get_repository_endpoint(
        domain=args.domain, domainOwner=owner, repository=args.repository, format="pypi",
    )["repositoryEndpoint"]
    token = codeartifact.get_authorization_token(
        domain=args.domain, domainOwner=owner, durationSeconds=900,
    )["authorizationToken"]
    environment = {
        **os.environ, "TWINE_USERNAME": "aws", "TWINE_PASSWORD": token,
        "TWINE_REPOSITORY_URL": endpoint,
    }
    subprocess.run(
        [sys.executable, "-m", "twine", "upload", "--non-interactive", str(wheel)],
        check=True, env=environment,
    )


def main() -> None:
    args = parse_args()
    package_dir = args.package_dir.resolve()
    project = tomllib.loads((package_dir / "pyproject.toml").read_text())["project"]
    name, version = canonicalize_name(project["name"]), project["version"]
    skill_path = package_dir / "src" / name.replace("-", "_") / "skill_files" / "SKILL.md"
    if not skill_path.read_bytes().startswith(b"---\n"):
        raise ValueError("Source SKILL.md is missing YAML frontmatter")
    if args.dry_run:
        if args.wheel:
            inspect_wheel(args.wheel, name, version)
        print(f"Local preflight OK: {name}=={version}; no AWS or build calls made")
        return
    with tempfile.TemporaryDirectory(prefix="skill-build-") as temporary:
        if args.wheel:
            wheel = args.wheel.resolve()
        else:
            output = package_dir / "dist" if args.skip_build else Path(temporary)
            if not args.skip_build:
                subprocess.run(
                    [sys.executable, "-m", "build", "--wheel", "--outdir", str(output), str(package_dir)],
                    check=True,
                )
            wheels = list(output.glob("*.whl"))
            if len(wheels) != 1:
                raise ValueError("Select exactly one release wheel using --wheel")
            wheel = wheels[0]
        inspected = inspect_wheel(wheel, name, version)
        if inspected["skillMd"].encode("utf-8") != skill_path.read_bytes():
            raise ValueError("Source SKILL.md differs from the wheel; rebuild before publishing")
        control = client("agent-registry-control", args.region)
        registry_id = args.registry_id or find_registry(control, args.registry)
        owner = args.domain_owner or client("sts", args.region).get_caller_identity()["Account"]
        descriptors = skill_descriptors(
            wheel, name, version, args.domain, args.repository, owner, args.region,
        )
        if not args.skip_upload:
            upload(args, wheel, owner)
        verify_published_asset(client("codeartifact", args.region), descriptors, name, version)
        record = publish_record(
            control, registry_id, name, version, project.get("description", name), descriptors,
        )
        if args.auto_submit and record["status"] == "DRAFT":
            control.submit_registry_record_for_approval(
                registryId=registry_id, recordId=record["recordId"],
            )
            print(f"Submitted for approval: {record['recordArn']}")
        else:
            print(f"Record {record['recordArn']}: {record['status']}")


if __name__ == "__main__":
    main()
