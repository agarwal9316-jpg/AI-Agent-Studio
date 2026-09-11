#!/usr/bin/env python3
"""Enforce docs/ version sync for every release.

Checks (exit 0 = ok, 1 = failures printed to stderr):
  1. VERSION file == app/version.py __version__ == version_manifest.json version
  2. docs/CHANGELOG.md has a table row for the current VERSION
  3. docs/CONTINUITY.md Head / resume mentions the current VERSION
  4. docs/FEATURES.md **Version:** line (if present) matches current VERSION

Usage:
  python scripts/check_docs_sync.py
  python scripts/check_docs_sync.py --root /path/to/AI-Agent-Studio
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _version_from_py(text: str) -> str | None:
    m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.M)
    return m.group(1) if m else None


def check_docs_sync(root: Path) -> list[str]:
    """Return a list of failure messages (empty = pass)."""
    fails: list[str] = []
    root = root.resolve()

    version_path = root / "VERSION"
    py_path = root / "app" / "version.py"
    manifest_path = root / "version_manifest.json"
    changelog = root / "docs" / "CHANGELOG.md"
    continuity = root / "docs" / "CONTINUITY.md"
    features = root / "docs" / "FEATURES.md"

    for p in (version_path, py_path, manifest_path, changelog, continuity):
        if not p.is_file():
            fails.append(f"missing required file: {p.relative_to(root)}")
    if fails:
        return fails

    file_ver = _read_text(version_path).strip()
    py_ver = _version_from_py(_read_text(py_path))
    try:
        man = json.loads(_read_text(manifest_path))
        man_ver = str(man.get("version") or "").strip()
    except json.JSONDecodeError as e:
        fails.append(f"version_manifest.json invalid JSON: {e}")
        man_ver = ""

    if not file_ver:
        fails.append("VERSION file is empty")
    if not py_ver:
        fails.append("app/version.py: could not parse __version__")
    if not man_ver:
        fails.append("version_manifest.json: missing version")

    trio = {v for v in (file_ver, py_ver, man_ver) if v}
    if len(trio) > 1:
        fails.append(
            f"VERSION trio mismatch: VERSION={file_ver!r} "
            f"app/version.py={py_ver!r} version_manifest.json={man_ver!r}"
        )

    version = file_ver or py_ver or man_ver
    if not version:
        return fails

    # CHANGELOG row: | **1.27.98** | ...
    cl_text = _read_text(changelog)
    row_pat = re.compile(
        rf"^\|\s*\*\*{re.escape(version)}\*\*\s*\|",
        re.M,
    )
    if not row_pat.search(cl_text):
        # also accept unbolded | 1.27.98 |
        alt = re.compile(rf"^\|\s*{re.escape(version)}\s*\|", re.M)
        if not alt.search(cl_text):
            fails.append(
                f"docs/CHANGELOG.md: no table row for version {version}"
            )

    # CONTINUITY must mention head version (Head: line or Last version)
    cont = _read_text(continuity)
    head_ok = bool(
        re.search(
            rf"\*\*Head:\*\*\s*{re.escape(version)}\b",
            cont,
        )
        or re.search(
            rf"\*\*Last version:\*\*\s*\*\*{re.escape(version)}\*\*",
            cont,
        )
        or re.search(rf"\b{re.escape(version)}\b", cont)
    )
    if not head_ok:
        fails.append(
            f"docs/CONTINUITY.md: does not mention version {version}"
        )
    else:
        # Prefer Head line when present — warn-as-fail if Head exists but stale
        head_m = re.search(r"\*\*Head:\*\*\s*([0-9]+(?:\.[0-9]+)*)", cont)
        if head_m and head_m.group(1) != version:
            fails.append(
                f"docs/CONTINUITY.md Head is {head_m.group(1)!r}, "
                f"expected {version!r}"
            )

    # FEATURES version line if present
    if features.is_file():
        feat = _read_text(features)
        feat_m = re.search(
            r"^\*\*Version:\*\*\s*([0-9]+(?:\.[0-9]+)*)",
            feat,
            re.M,
        )
        if feat_m and feat_m.group(1) != version:
            fails.append(
                f"docs/FEATURES.md Version line is {feat_m.group(1)!r}, "
                f"expected {version!r}"
            )

    return fails


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Project root (default: parent of scripts/)",
    )
    args = parser.parse_args(argv)
    root = args.root
    if root is None:
        root = Path(__file__).resolve().parent.parent

    fails = check_docs_sync(root)
    if fails:
        print("docs sync check FAILED:", file=sys.stderr)
        for f in fails:
            print(f"  - {f}", file=sys.stderr)
        return 1
    # Resolve version for friendly OK line
    ver = (root / "VERSION").read_text(encoding="utf-8").strip()
    print(f"OK docs sync for {ver}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
