"""Detect local drift against the provenance manifest (not a signature verification)."""

import argparse
import json
from pathlib import Path

from registry_blueprint.artifacts import verify_installed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    manifest = verify_installed(args.directory.expanduser())
    print(json.dumps({
        "result": "unchanged",
        "recordArn": manifest["recordArn"],
        "recordVersion": manifest["recordVersion"],
        "artifactSha256": manifest["artifactSha256"],
    }, indent=2))


if __name__ == "__main__":
    main()
