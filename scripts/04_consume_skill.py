"""Discover an approved release, verify the wheel, and activate only its skill files."""

import argparse
import os
from pathlib import Path

from registry_blueprint.consumer import consume


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry-arn", default=os.getenv("AGENT_REGISTRY_ARN"))
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "us-east-1"))
    parser.add_argument("--name", default="aws-cost-anomaly-triage")
    parser.add_argument("--version", default="0.1.0")
    parser.add_argument("--query", default="cost anomaly triage")
    parser.add_argument("--domain", default="skills-demo")
    parser.add_argument("--repository", default="skills-prod")
    parser.add_argument("--domain-owner")
    parser.add_argument("--target-dir", type=Path, default=Path.home() / ".claude" / "skills")
    args = parser.parse_args()
    if not args.registry_arn:
        parser.error("--registry-arn or AGENT_REGISTRY_ARN is required; consumers never enumerate registries")
    destination = consume(
        args.registry_arn, args.region, args.name, args.version, args.query,
        args.domain, args.repository, args.domain_owner, args.target_dir,
    )
    print(f"Verified and activated: {destination}")


if __name__ == "__main__":
    main()
