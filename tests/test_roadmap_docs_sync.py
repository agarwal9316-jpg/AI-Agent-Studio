"""Roadmap — Keep docs/ in sync on every release (1.27.98).

Runs scripts/check_docs_sync.py against the current tree (must pass).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.version import __version__  # noqa: E402
from scripts.check_docs_sync import check_docs_sync  # noqa: E402


def test_version():
    assert __version__ == "1.27.98", __version__
    print("✓ version 1.27.98")


def test_checker_module_passes_on_tree():
    fails = check_docs_sync(ROOT)
    assert fails == [], fails
    print("✓ check_docs_sync(ROOT) empty fails")


def test_checker_cli_exit_zero():
    script = ROOT / "scripts" / "check_docs_sync.py"
    r = subprocess.run(
        [sys.executable, str(script), "--root", str(ROOT)],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "OK docs sync" in r.stdout
    print("✓ CLI exit 0:", r.stdout.strip())


def test_checker_detects_trio_mismatch():
    """Synthetic tree: VERSION out of sync → must fail."""
    import json
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "app").mkdir()
        (root / "docs").mkdir()
        (root / "VERSION").write_text("9.9.9\n", encoding="utf-8")
        (root / "app" / "version.py").write_text(
            '__version__ = "9.9.8"\nAPP_NAME = "X"\n', encoding="utf-8"
        )
        (root / "version_manifest.json").write_text(
            json.dumps({"version": "9.9.9"}), encoding="utf-8"
        )
        (root / "docs" / "CHANGELOG.md").write_text(
            "| **9.9.9** | note |\n", encoding="utf-8"
        )
        (root / "docs" / "CONTINUITY.md").write_text(
            "**Head:** 9.9.9 — test\n", encoding="utf-8"
        )
        fails = check_docs_sync(root)
        assert any("trio mismatch" in f for f in fails), fails
        print("✓ detects VERSION trio mismatch")


def test_checker_detects_missing_changelog_row():
    import json
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "app").mkdir()
        (root / "docs").mkdir()
        (root / "VERSION").write_text("1.2.3\n", encoding="utf-8")
        (root / "app" / "version.py").write_text(
            '__version__ = "1.2.3"\n', encoding="utf-8"
        )
        (root / "version_manifest.json").write_text(
            json.dumps({"version": "1.2.3"}), encoding="utf-8"
        )
        (root / "docs" / "CHANGELOG.md").write_text(
            "| **1.2.2** | old |\n", encoding="utf-8"
        )
        (root / "docs" / "CONTINUITY.md").write_text(
            "**Head:** 1.2.3 — test\n", encoding="utf-8"
        )
        fails = check_docs_sync(root)
        assert any("CHANGELOG" in f for f in fails), fails
        print("✓ detects missing CHANGELOG row")


def main() -> int:
    test_version()
    test_checker_module_passes_on_tree()
    test_checker_cli_exit_zero()
    test_checker_detects_trio_mismatch()
    test_checker_detects_missing_changelog_row()
    print("All roadmap docs-sync checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
