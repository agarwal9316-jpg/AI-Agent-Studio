"""Ensure refactor-split modules are materialized before the UI imports them.

Called automatically from app.main on every launch. Fast no-op when modules
are already present (size check). On first run after pull, decompresses
verified payloads via scripts/install_*_v2.py / fix_*_v2.py.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# app/_ensure_refactor_modules.py -> parents[1] = repo root
_ROOT = Path(__file__).resolve().parents[1]

_TARGETS: list[tuple[str, str]] = [
    # (relative path under repo, installer script name under scripts/)
    ("app/ui/components/chat_thinking.py", "install_chat_thinking_v2.py"),
    ("app/ui/components/chat_rail.py", "install_chat_rail_v2.py"),
    ("app/ui/components/chat_send.py", "install_chat_send_v2.py"),
    ("app/ui/components/chat_dialogs.py", "fix_chat_dialogs_v2.py"),
    ("app/ui/components/chat_render.py", "fix_chat_render_v2.py"),
    ("app/ui/components/chat_misc.py", "fix_chat_misc_v2.py"),
    ("app/ui/pages/chat_page.py", "fix_chat_page_v2.py"),
    ("app/ui/pages/settings_page.py", "fix_settings_page_v2.py"),
    ("app/ui/app_window.py", "fix_app_window_v2.py"),
    ("app/ui/pages/org_page_ai.py", "install_org_page_ai_v1.py"),
    ("app/ui/pages/org_page.py", "install_org_page_v1.py"),
    ("app/ui/pages/team_dialogs.py", "install_team_dialogs_v1.py"),
    ("app/ui/pages/team_page.py", "install_team_page_v1.py"),
]

_MIN_FULL_BYTES = 5000


def _is_stub(path: Path) -> bool:
    if not path.is_file():
        return True
    try:
        size = path.stat().st_size
    except OSError:
        return True
    if size < _MIN_FULL_BYTES:
        return True
    try:
        head = path.read_text(encoding="utf-8", errors="ignore")[:200]
    except OSError:
        return True
    if "Bootstrap" in head and ("auto-materializes" in head or "materializes" in head):
        return True
    return False


def needs_materialize() -> bool:
    return any(_is_stub(_ROOT / rel) for rel, _ in _TARGETS)


def ensure_refactor_modules(*, quiet: bool = True) -> None:
    """Materialize any missing/stub refactor modules. Safe to call every launch."""
    if not needs_materialize():
        return
    if not quiet:
        print("Materializing UI modules (first run after update)…", flush=True)
    for rel, script_name in _TARGETS:
        path = _ROOT / rel
        if not _is_stub(path):
            continue
        script = _ROOT / "scripts" / script_name
        if not script.exists():
            alt = script_name.replace("fix_", "install_")
            script = _ROOT / "scripts" / alt
        if not script.exists():
            raise RuntimeError(f"Missing installer for {rel}: {script_name}")
        if not quiet:
            print(f"  → {rel}", flush=True)
        r = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(_ROOT),
            capture_output=quiet,
            text=True,
        )
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip()
            raise RuntimeError(f"Failed to materialize {rel}: {err or r.returncode}")
        if _is_stub(path):
            raise RuntimeError(f"Installer ran but {rel} is still a stub")
    if not quiet:
        print("UI modules ready.", flush=True)


if __name__ == "__main__":
    ensure_refactor_modules(quiet=False)
