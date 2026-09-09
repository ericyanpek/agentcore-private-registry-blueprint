"""Inspect wheels without executing package code and track installed provenance."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
import unicodedata
import zipfile
from datetime import datetime, timezone
from email.parser import BytesParser
from pathlib import Path, PurePosixPath

from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import Version

MAX_ARTIFACT_BYTES = 20 * 1024 * 1024
MANIFEST_NAME = ".registry-provenance.json"
INTEGRITY_KEY = "com.example.integrity"
SOURCE_KEY = "com.example.codeartifact"


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def safe_name(name: str) -> str:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]*", name):
        raise ValueError(f"Unsafe package or skill name: {name!r}")
    return canonicalize_name(name)


def inspect_wheel(wheel: Path, name: str, version: str) -> dict:
    expected_name = safe_name(name)
    wheel_name, wheel_version, _, tags = parse_wheel_filename(wheel.name)
    if wheel_name != expected_name or wheel_version != Version(version):
        raise ValueError("Wheel filename does not match the selected package version")
    if any(tag.abi != "none" or tag.platform != "any" for tag in tags):
        raise ValueError("This blueprint only activates platform-independent skill wheels")
    if wheel.stat().st_size > MAX_ARTIFACT_BYTES:
        raise ValueError("Wheel exceeds the 20 MiB blueprint limit")
    with zipfile.ZipFile(wheel) as archive:
        entries = archive.infolist()
        if len(entries) > 1000:
            raise ValueError("Wheel exceeds the 1000-member blueprint limit")
        names = [entry.filename for entry in entries]
        if len(names) != len(set(names)):
            raise ValueError("Wheel contains duplicate paths")
        if sum(entry.file_size for entry in entries) > MAX_ARTIFACT_BYTES:
            raise ValueError("Expanded wheel exceeds the 20 MiB blueprint limit")
        for entry in entries:
            path = PurePosixPath(entry.filename)
            mode = entry.external_attr >> 16
            if (
                path.is_absolute()
                or ".." in path.parts
                or entry.filename.rstrip("/") != path.as_posix()
                or "\\" in entry.filename
                or ":" in entry.filename
                or stat.S_ISLNK(mode)
                or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR))
            ):
                raise ValueError(f"Unsafe wheel member: {entry.filename!r}")
        metadata_paths = [
            name for name in names if name.endswith(".dist-info/METADATA")
        ]
        if len(metadata_paths) != 1:
            raise ValueError("Wheel must contain exactly one METADATA file")
        metadata = BytesParser().parsebytes(archive.read(metadata_paths[0]))
        if (
            canonicalize_name(metadata.get("Name", "")) != expected_name
            or Version(metadata.get("Version", "0")) != Version(version)
        ):
            raise ValueError("Wheel METADATA does not match the selected package version")
        if metadata.get_all("Requires-Dist"):
            raise ValueError("Skill wheels with Python dependencies are not supported")
        skill_root = f"{expected_name.replace('-', '_')}/skill_files/"
        files = {
            entry.filename[len(skill_root):]: archive.read(entry)
            for entry in entries
            if entry.filename.startswith(skill_root) and not entry.is_dir()
        }
    if MANIFEST_NAME in files or "SKILL.md" not in files:
        raise ValueError("Wheel must contain SKILL.md and must not supply a provenance manifest")
    if len(files["SKILL.md"]) > 102400:
        raise ValueError("SKILL.md exceeds the 100 KiB blueprint limit")
    folded_paths = [unicodedata.normalize("NFC", path).casefold() for path in files]
    if len(set(folded_paths)) != len(folded_paths):
        raise ValueError("Skill paths collide on case-insensitive filesystems")
    skill_md = files["SKILL.md"].decode("utf-8")
    if not skill_md.startswith("---\n"):
        raise ValueError("Wheel SKILL.md must start with YAML frontmatter")
    return {
        "asset": wheel.name,
        "sha256": sha256(wheel.read_bytes()),
        "skillMdSha256": sha256(files["SKILL.md"]),
        "skillPath": skill_root,
        "skillMd": skill_md,
        "files": files,
    }


def verify_wheel(wheel: Path, definition: dict, skill_md: str) -> dict:
    if wheel.stat().st_size > MAX_ARTIFACT_BYTES:
        raise ValueError("Wheel exceeds the 20 MiB blueprint limit")
    packages = definition.get("packages", [])
    if len(packages) != 1 or packages[0].get("registryType") != "pypi":
        raise ValueError("Exactly one pinned PyPI package is required")
    package = packages[0]
    integrity = definition.get("_meta", {}).get(INTEGRITY_KEY, {})
    if not re.fullmatch(r"[0-9a-f]{64}", integrity.get("sha256", "")):
        raise ValueError("Approved record has no valid SHA-256 digest")
    if wheel.name != integrity.get("asset") or sha256(wheel.read_bytes()) != integrity["sha256"]:
        raise ValueError("Artifact digest mismatch; refusing to activate")
    inspected = inspect_wheel(wheel, package["identifier"], package["version"])
    for field in ("asset", "sha256", "skillMdSha256", "skillPath"):
        if inspected[field] != integrity.get(field):
            raise ValueError(f"Approved record disagrees with wheel: {field}")
    if skill_md != inspected["skillMd"]:
        raise ValueError("Approved SKILL.md differs from the wheel")
    return inspected


def activate(inspected: dict, target: Path, name: str, provenance: dict) -> Path:
    skill_name = safe_name(name)
    target = target.expanduser().absolute()
    if target.is_symlink():
        raise ValueError("The target directory must not be a symlink")
    target.mkdir(parents=True, exist_ok=True)
    destination = target / skill_name
    manifest = {
        "schemaVersion": 1,
        **provenance,
        "artifactSha256": inspected["sha256"],
        "installedAt": datetime.now(timezone.utc).isoformat(),
        "files": {path: sha256(content) for path, content in inspected["files"].items()},
    }
    if destination.exists() or destination.is_symlink():
        verify_installed(destination)
        previous = json.loads((destination / MANIFEST_NAME).read_text())
        identity_fields = ("registryArn", "recordId", "recordVersion", "artifactSha256")
        if all(previous.get(field) == manifest.get(field) for field in identity_fields):
            return destination
        raise ValueError(
            f"{destination} already contains a different release; review and remove it explicitly"
        )
    with tempfile.TemporaryDirectory(prefix=".skill-stage-", dir=target) as temporary:
        staging = Path(temporary) / skill_name
        staging.mkdir(mode=0o700)
        for relative, content in inspected["files"].items():
            output = staging / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(content)
        (staging / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2) + "\n")
        verify_installed(staging)
        os.rename(staging, destination)
    return destination


def verify_installed(directory: Path) -> dict:
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("Installed skill must be a real directory")
    manifest_path = directory / MANIFEST_NAME
    if manifest_path.is_symlink():
        raise ValueError("Provenance manifest must not be a symlink")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schemaVersion") != 1 or not isinstance(manifest.get("files"), dict):
        raise ValueError("Unsupported provenance manifest")
    actual = {}
    for path in directory.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"Unexpected symlink in installed skill: {path}")
        if path.is_file() and path != manifest_path:
            actual[path.relative_to(directory).as_posix()] = sha256(path.read_bytes())
    if not actual or actual != manifest["files"]:
        raise ValueError("Installed skill has changed, missing, or extra files")
    return manifest
