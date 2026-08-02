"""Build and scan the reviewed public-boundary staging output.

The private core owns this tooling. It deliberately uses an explicit
allowlist, while the sensitive-data scan is only a secondary safety gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


class BoundaryError(ValueError):
    """Raised when a publication boundary rule is violated."""


_DENIED_NAME_PARTS = {
    ".env",
    ".git",
    ".venv",
    "asr",
    "debug",
    "fixture",
    "models",
    "output",
    "private",
    "prompt",
    "prompts",
    "provider",
    "providers",
    "src",
    "tests",
    "worker",
}
_DENIED_SUFFIXES = {".map", ".zip", ".7z", ".rar", ".tar", ".gz"}
_TEXT_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("credential_pattern", re.compile(r"(?i)(?:api[_ -]?key|secret[_ -]?key|client[_ -]?secret)\s*[:=]")),
    ("authorization_header", re.compile(r"(?i)\b(?:authorization|cookie)\s*:")),
    ("bearer_token", re.compile(r"(?i)\bbearer\s+[a-z0-9._-]{12,}")),
    ("provider_or_prompt_reference", re.compile(r"(?i)\b(?:provider|prompt|model[_ -]?route|worker)\b")),
    ("private_module_reference", re.compile(r"(?i)(?:^|[\s\"'`])(?:src[\\/.]|viewledge-cloud|video-summary-skill)(?:$|[\s\"'`])")),
    ("absolute_machine_path", re.compile(r"(?i)(?:^|[\s\"'(])(?:[a-z]:[\\/]|/users/|/home/|\\\\[a-z0-9_.-]+\\)")),
    ("known_key_shape", re.compile(r"\b(?:sk|gsk|AIza|xai)-[A-Za-z0-9_-]{16,}\b")),
)


def _canonical_relative(path: str, *, field: str) -> Path:
    value = Path(path)
    if value.is_absolute() or ".." in value.parts or value == Path("."):
        raise BoundaryError(f"{field} must be a relative path without '..': {path!r}")
    return value


def load_allowlist(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BoundaryError(f"invalid allowlist: {path}") from exc
    if not isinstance(payload, dict) or payload.get("manifest_version") != "1":
        raise BoundaryError("allowlist manifest_version must be '1'")
    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        raise BoundaryError("allowlist must contain at least one entry")
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("source"), str) or not isinstance(entry.get("destination"), str):
            raise BoundaryError("each allowlist entry needs source and destination")
        _canonical_relative(entry["source"], field="source")
        _canonical_relative(entry["destination"], field="destination")
    if payload.get("fresh_history_required") is not True or payload.get("private_history_reuse_forbidden") is not True:
        raise BoundaryError("allowlist must require fresh history and forbid private-history reuse")
    return payload


def _git_revision(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"
    return result.stdout.strip() or "unavailable"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_staging(root: Path, allowlist_path: Path, output: Path) -> dict[str, Any]:
    root = root.resolve()
    allowlist_path = allowlist_path.resolve()
    output = output.resolve()
    if output == root or root in output.parents:
        raise BoundaryError("staging output must be outside the private repository")
    if output.exists():
        if not output.is_dir() or any(output.iterdir()):
            raise BoundaryError("staging output must be absent or an empty directory")
    else:
        output.mkdir(parents=True)
    manifest = load_allowlist(allowlist_path)
    copied: list[dict[str, str]] = []
    for entry in manifest["entries"]:
        source = (root / _canonical_relative(entry["source"], field="source")).resolve()
        destination_rel = _canonical_relative(entry["destination"], field="destination")
        destination = output / destination_rel
        if not source.is_file() or root not in source.parents:
            raise BoundaryError(f"allowlisted source is missing or outside root: {entry['source']}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied.append({"path": destination_rel.as_posix(), "sha256": _sha256(destination)})
    publication = {
        "manifest_version": manifest["manifest_version"],
        "public_repository": manifest["public_repository"],
        "schema_versions": manifest.get("schema_versions", {}),
        "source_revision": _git_revision(root),
        "fresh_history_required": True,
        "private_history_reuse_forbidden": True,
        "files": sorted(copied, key=lambda item: item["path"]),
    }
    (output / "publication-manifest.json").write_text(
        json.dumps(publication, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    findings = scan_tree(output)
    if findings:
        raise BoundaryError(f"sensitive-data scan failed with {len(findings)} finding(s)")
    verify_staging(output)
    return publication


def verify_staging(staging: Path) -> dict[str, Any]:
    """Verify a generated staging directory without consulting private code."""

    staging = staging.resolve()
    manifest_path = staging / "publication-manifest.json"
    if not manifest_path.is_file():
        raise BoundaryError("staging directory is missing publication-manifest.json")
    try:
        publication = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BoundaryError("publication-manifest.json is not valid UTF-8 JSON") from exc
    if not isinstance(publication, dict) or publication.get("manifest_version") != "1":
        raise BoundaryError("publication manifest_version must be '1'")
    if publication.get("fresh_history_required") is not True or publication.get("private_history_reuse_forbidden") is not True:
        raise BoundaryError("publication manifest must require fresh history")
    files = publication.get("files")
    if not isinstance(files, list) or not files:
        raise BoundaryError("publication manifest must contain files")
    expected: dict[str, str] = {}
    for item in files:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not isinstance(item.get("sha256"), str):
            raise BoundaryError("publication file entries need path and sha256")
        relative = _canonical_relative(item["path"], field="publication path")
        if relative.as_posix() == "publication-manifest.json" or relative.as_posix() in expected:
            raise BoundaryError("publication manifest contains an invalid or duplicate path")
        if not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]):
            raise BoundaryError(f"invalid SHA-256 for {relative.as_posix()}")
        expected[relative.as_posix()] = item["sha256"]
    actual = {
        path.relative_to(staging).as_posix()
        for path in staging.rglob("*")
        if path.is_file() and path.name != "publication-manifest.json"
    }
    if actual != set(expected):
        raise BoundaryError("staging files do not exactly match publication manifest")
    for relative, expected_hash in expected.items():
        actual_hash = _sha256(staging / Path(relative))
        if actual_hash != expected_hash:
            raise BoundaryError(f"SHA-256 mismatch for {relative}")
    findings = scan_tree(staging)
    if findings:
        raise BoundaryError(f"sensitive-data scan failed with {len(findings)} finding(s)")
    return publication


def scan_tree(root: Path) -> list[dict[str, str]]:
    root = root.resolve()
    if not root.is_dir():
        raise BoundaryError(f"scan root is not a directory: {root}")
    findings: list[dict[str, str]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        parts = {part.casefold() for part in relative.parts}
        if path.is_dir():
            if parts & _DENIED_NAME_PARTS:
                findings.append({"path": relative.as_posix(), "rule": "denied_path_component"})
            continue
        if (
            path.name.casefold() in _DENIED_NAME_PARTS
            or path.stem.casefold() in _DENIED_NAME_PARTS
            or path.suffix.casefold() in _DENIED_SUFFIXES
        ):
            findings.append({"path": relative.as_posix(), "rule": "denied_filename"})
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for rule, pattern in _TEXT_RULES:
            if pattern.search(text):
                findings.append({"path": relative.as_posix(), "rule": rule})
    return findings


def _command_build(args: argparse.Namespace) -> int:
    publication = build_staging(Path(args.root), Path(args.manifest), Path(args.output))
    print(json.dumps(publication, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _command_scan(args: argparse.Namespace) -> int:
    findings = scan_tree(Path(args.root))
    payload = {"ok": not findings, "findings": findings}
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not findings else 1


def _command_verify(args: argparse.Namespace) -> int:
    publication = verify_staging(Path(args.root))
    print(json.dumps(publication, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build or scan Viewledge public-boundary staging output")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="copy only allowlisted files into clean staging")
    build.add_argument("--root", required=True, help="private repository root")
    build.add_argument("--manifest", required=True, help="allowlist JSON path")
    build.add_argument("--output", required=True, help="empty staging directory outside the repository")
    build.set_defaults(handler=_command_build)
    scan = subparsers.add_parser("scan", help="scan a staging directory")
    scan.add_argument("--root", required=True, help="staging directory")
    scan.set_defaults(handler=_command_scan)
    verify = subparsers.add_parser("verify", help="verify hashes, file set, and scan for generated staging")
    verify.add_argument("--root", required=True, help="generated staging directory")
    verify.set_defaults(handler=_command_verify)
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except BoundaryError as exc:
        print(f"boundary error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
