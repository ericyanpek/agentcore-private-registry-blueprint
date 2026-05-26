"""Register the aws-cost-anomaly-triage skill into the demo registry.

Flow:
  1. Read the SKILL.md from the source tree (frontmatter included — the
     SDK strips frontmatter when loading a skill, but the Registry
     wants the raw file).
  2. Build a skillDefinition JSON pointing at the CodeArtifact PyPI
     package (registryType=pypi).
  3. CreateRegistryRecord (status=CREATING).
  4. Poll until status=DRAFT.
  5. SubmitRegistryRecordForApproval (status=PENDING_APPROVAL).

Usage:
    python3 02_register_skill.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

REGION = "us-east-1"
REGISTRY_NAME = "skills-demo-registry"
RECORD_NAME = "aws-cost-anomaly-triage"
RECORD_VERSION = "0.1.0"

CODE_ARTIFACT_DOMAIN = "skills-demo"
CODE_ARTIFACT_REPO = "skills-prod"
PYPI_PACKAGE_NAME = "aws-cost-anomaly-triage"

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_MD_PATH = (
    REPO_ROOT
    / "skill-package"
    / "src"
    / "aws_cost_anomaly_triage"
    / "skill_files"
    / "SKILL.md"
)


def find_registry_id(client) -> str:
    for reg in client.list_registries().get("registries", []):
        if reg.get("name") == REGISTRY_NAME:
            arn = reg["registryArn"]
            return arn.rsplit("/", 1)[-1]
    raise SystemExit(f"registry {REGISTRY_NAME!r} not found — run 01 first")


def load_skill_md() -> str:
    raw = SKILL_MD_PATH.read_text(encoding="utf-8")
    if not raw.startswith("---"):
        raise SystemExit("SKILL.md missing YAML frontmatter")
    return raw


def build_skill_definition() -> str:
    """Skill definition pointing at the CodeArtifact PyPI package.

    The schema (v0.1.0) lets us advertise:
      - the source repository (for human browsing)
      - one or more package distributions (registryType + identifier)
      - vendor-specific extensions in _meta (reverse-DNS namespaced)
    """
    account_id = boto3.client("sts").get_caller_identity()["Account"]
    code_artifact_index = (
        f"https://{CODE_ARTIFACT_DOMAIN}-{account_id}.d.codeartifact."
        f"{REGION}.amazonaws.com/pypi/{CODE_ARTIFACT_REPO}/simple/"
    )
    definition = {
        "websiteUrl": "https://example.internal/finops/cost-anomaly-triage",
        "repository": {
            "url": "https://example.internal/git/finops/skills",
            "source": "github",
        },
        "packages": [
            {
                "registryType": "pypi",
                "identifier": PYPI_PACKAGE_NAME,
                "version": RECORD_VERSION,
            }
        ],
        "_meta": {
            "com.example.codeartifact": {
                "domain": CODE_ARTIFACT_DOMAIN,
                "repository": CODE_ARTIFACT_REPO,
                "region": REGION,
                "indexUrl": code_artifact_index,
            },
            "com.example.activate": {
                "postInstallCommand": "install-aws-cost-anomaly-triage",
                "skillTargetDir": "~/.claude/skills/aws-cost-anomaly-triage/",
            },
            "com.example.owner": {
                "team": "FinOps",
                "contact": "finops@example.internal",
            },
        },
    }
    return json.dumps(definition, indent=2)


def wait_for_state(client, registry_id: str, record_id: str, target: str,
                   timeout_s: int = 60) -> dict:
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        rec = client.get_registry_record(
            registryId=registry_id, recordId=record_id
        )
        last = rec
        if rec.get("status") == target:
            return rec
        time.sleep(2)
    raise SystemExit(
        f"timeout waiting for record {record_id} to reach {target}; "
        f"last state: {last}"
    )


def main() -> None:
    client = boto3.client("bedrock-agentcore-control", region_name=REGION)
    registry_id = find_registry_id(client)
    print(f"registry id: {registry_id}")

    skill_md = load_skill_md()
    skill_def = build_skill_definition()
    print(f"SKILL.md: {len(skill_md)} chars")
    print(f"skill definition: {len(skill_def)} chars")

    # Reuse if exists
    for r in client.list_registry_records(registryId=registry_id).get(
        "registryRecords", []
    ):
        if r.get("name") == RECORD_NAME:
            print("record already exists:")
            print(json.dumps(r, default=str, indent=2))
            return

    try:
        resp = client.create_registry_record(
            registryId=registry_id,
            name=RECORD_NAME,
            description=(
                "FinOps SOP for triaging AWS cost anomalies — text-only "
                "skill distributed via CodeArtifact PyPI."
            ),
            descriptorType="AGENT_SKILLS",
            descriptors={
                "agentSkills": {
                    "skillMd": {"inlineContent": skill_md},
                    "skillDefinition": {
                        "schemaVersion": "0.1.0",
                        "inlineContent": skill_def,
                    },
                }
            },
            recordVersion=RECORD_VERSION,
        )
    except ClientError as e:
        sys.exit(f"create_registry_record failed: {e}")

    record_arn = resp["recordArn"]
    record_id = record_arn.rsplit("/", 1)[-1]
    print(f"record ARN: {record_arn}")
    print(f"record id: {record_id}")

    print("waiting for record to reach DRAFT...")
    rec = wait_for_state(client, registry_id, record_id, "DRAFT")
    print(f"reached state: {rec.get('status')}")

    print("submitting record for approval...")
    client.submit_registry_record_for_approval(
        registryId=registry_id, recordId=record_id
    )
    rec = wait_for_state(client, registry_id, record_id, "PENDING_APPROVAL")
    print(f"reached state: {rec.get('status')}")
    print()
    print("Next step: run 03_approve_skill.py to approve as admin.")


if __name__ == "__main__":
    main()
