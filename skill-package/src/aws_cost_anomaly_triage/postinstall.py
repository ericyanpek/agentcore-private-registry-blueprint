"""Post-install script: copy bundled skill_files into ~/.claude/skills/<name>/.

This is the bridge between PyPI distribution (which ships the
SKILL.md inside a Python wheel) and the Claude Code / agent runtime
convention of looking for skills under ~/.claude/skills/.

Idempotent: re-running the script overwrites existing files. Safe
to wire into automation.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from importlib import resources
from pathlib import Path

SKILL_NAME = "aws-cost-anomaly-triage"
PACKAGE_NAME = "aws_cost_anomaly_triage"


def _resolve_skill_files_root() -> Path:
    """Locate the on-disk path of the bundled skill_files directory."""
    pkg_files = resources.files(PACKAGE_NAME)
    skill_files = pkg_files / "skill_files"
    if not skill_files.is_dir():
        raise SystemExit(
            f"skill_files not found in installed package {PACKAGE_NAME}"
        )
    return Path(str(skill_files))


def main() -> int:
    parser = argparse.ArgumentParser(
        description=f"Install {SKILL_NAME} into ~/.claude/skills/"
    )
    parser.add_argument(
        "--target-dir",
        default=os.environ.get(
            "CLAUDE_SKILLS_DIR",
            str(Path.home() / ".claude" / "skills"),
        ),
        help="Skills directory (default: ~/.claude/skills, override with "
        "$CLAUDE_SKILLS_DIR or --target-dir).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be copied without touching disk.",
    )
    args = parser.parse_args()

    src = _resolve_skill_files_root()
    dst = Path(args.target_dir).expanduser() / SKILL_NAME

    print(f"source: {src}")
    print(f"target: {dst}")

    if args.dry_run:
        for item in src.rglob("*"):
            rel = item.relative_to(src)
            print(f"  would copy: {rel}")
        return 0

    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)

    print(f"installed skill {SKILL_NAME!r} into {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
