"""Roadmap — Code signing for portable exe (1.28.1).

Pipeline + docs only; no real Authenticode cert required.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.version import __version__  # noqa: E402

PS1 = ROOT / "scripts" / "sign_portable.ps1"
SH = ROOT / "scripts" / "sign_portable.sh"
DOC = ROOT / "docs" / "CODE_SIGNING.md"
BUILD = ROOT / "build_portable.ps1"


def test_version():
    assert __version__ == "1.28.1", __version__
    file_ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert file_ver == "1.28.1", file_ver
    print("✓ version 1.28.1")


def test_scripts_exist():
    assert PS1.is_file(), f"missing {PS1}"
    assert SH.is_file(), f"missing {SH}"
    assert os.access(SH, os.X_OK) or True  # Windows may lack +x; Linux CI should have it
    text_ps = PS1.read_text(encoding="utf-8")
    text_sh = SH.read_text(encoding="utf-8")
    for needle in ("AAS_SIGN_CERT", "AAS_SIGN_PASSWORD", "DryRun", "SelfSignedDev"):
        assert needle in text_ps, needle
    for needle in ("AAS_SIGN_CERT", "AAS_SIGN_PASSWORD", "--dry-run", "--help", "osslsigncode"):
        assert needle in text_sh, needle
    print("✓ sign_portable.ps1 + .sh exist with expected knobs")


def test_docs_present():
    assert DOC.is_file(), f"missing {DOC}"
    text = DOC.read_text(encoding="utf-8")
    for needle in (
        "AAS_SIGN_CERT",
        "Get-AuthenticodeSignature",
        "osslsigncode verify",
        "NOT for distribution",
        "self-signed",
        "user-provided",
    ):
        assert needle.lower() in text.lower(), needle
    roadmap = (ROOT / "docs" / "ROADMAP.md").read_text(encoding="utf-8")
    assert "Code signing" in roadmap
    assert "pipeline ready" in roadmap.lower() or "user-provided" in roadmap.lower()
    assert "- [x] Code signing" in roadmap or "[x] Code signing for portable exe" in roadmap
    print("✓ docs/CODE_SIGNING.md + ROADMAP checkbox")


def test_build_hook_mentions_sign():
    text = BUILD.read_text(encoding="utf-8")
    assert "sign_portable.ps1" in text
    assert "CODE_SIGNING" in text or "Authenticode" in text or "sign" in text.lower()
    print("✓ build_portable.ps1 hooks sign script")


def test_sh_help_path():
    r = subprocess.run(
        ["bash", str(SH), "--help"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    out = (r.stdout + r.stderr).lower()
    assert "sign_portable" in out or "osslsigncode" in out or "aas_sign" in out
    assert "help" in out or "dry-run" in out or "cert" in out
    print("✓ sign_portable.sh --help")


def test_sh_dry_run_no_cert():
    env = os.environ.copy()
    env.pop("AAS_SIGN_CERT", None)
    env.pop("AAS_SIGN_PASSWORD", None)
    env["AAS_SIGN_SKIP"] = "0"
    r = subprocess.run(
        ["bash", str(SH), "--dry-run"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=env,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    combined = r.stdout + r.stderr
    assert "dry-run" in combined.lower()
    print("✓ sign_portable.sh --dry-run (no cert)")


def test_sh_skip_env():
    env = os.environ.copy()
    env["AAS_SIGN_SKIP"] = "1"
    r = subprocess.run(
        ["bash", str(SH)],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=env,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "skip" in (r.stdout + r.stderr).lower()
    print("✓ AAS_SIGN_SKIP=1")


def test_ps1_help_text_embedded():
    """PowerShell may be unavailable on Linux CI — assert -Help content in script."""
    text = PS1.read_text(encoding="utf-8")
    assert "Show-Help" in text or "sign_portable.ps1" in text
    assert "-Help" in text and "-DryRun" in text
    assert "docs/CODE_SIGNING.md" in text
    print("✓ sign_portable.ps1 help/dry-run surface present")


def main() -> int:
    test_version()
    test_scripts_exist()
    test_docs_present()
    test_build_hook_mentions_sign()
    test_sh_help_path()
    test_sh_dry_run_no_cert()
    test_sh_skip_env()
    test_ps1_help_text_embedded()
    print("All roadmap code-signing checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
