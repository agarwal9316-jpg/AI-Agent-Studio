"""Ensure refactor-split modules are materialized before the UI imports them.

Called automatically from app.main on every launch. Fast no-op when modules
are already present (size check). On first run after clone/pull, decompresses
verified payloads via scripts/install_* / fix_* .

Also writes data/last_materialize.txt for diagnostics (health check).
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# app/_ensure_refactor_modules.py -> parents[1] = repo root
_ROOT = Path(__file__).resolve().parents[1]

_TARGETS: list[tuple[str, str]] = [
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
    ("app/ui/pages/org_chart_widgets.py", "install_org_chart_widgets_v1.py"),
    ("app/ui/pages/org_chart_view.py", "install_org_chart_view_v1.py"),
    ("app/ui/pages/mgmt_pages.py", "install_mgmt_pages_v1.py"),
    ("app/ui/pages/models_page.py", "install_models_page_v1.py"),
    ("app/ui/pages/models_advanced.py", "install_models_advanced_v1.py"),
    ("app/ui/pages/chats_page.py", "install_chats_page_v1.py"),
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


def _ensure_task_watch() -> None:
    """Restore task_watch.py if truncated/placeholder."""
    path = _ROOT / "app/core/services/chat/task_watch.py"
    try:
        text = path.read_text(encoding="utf-8", errors="ignore") if path.is_file() else ""
    except OSError:
        text = ""
    if path.is_file() and len(text) > 8000 and "PLACEHOLDER" not in text[:80]:
        return
    script = _ROOT / "scripts" / "install_task_watch_restore.py"
    if not script.is_file():
        return
    subprocess.run([sys.executable, str(script)], cwd=str(_ROOT), check=False)


def _ensure_control_plane_ui() -> None:
    """Install control plane service + Control plane page if missing."""
    service = _ROOT / "app/core/services/control_plane/service.py"
    page = _ROOT / "app/ui/pages/control_plane_page.py"
    need = (not service.is_file() or service.stat().st_size < 5000) or (
        not page.is_file() or page.stat().st_size < 5000
    )
    if not need:
        return
    script = _ROOT / "scripts" / "install_cp_ui.py"
    if not script.is_file():
        return
    subprocess.run([sys.executable, str(script)], cwd=str(_ROOT), check=False)


def _write_health(status: str, details: str = "") -> None:
    """Write data/last_materialize.txt for About/Diagnostics and support."""
    try:
        data = _ROOT / "data"
        data.mkdir(parents=True, exist_ok=True)
        lines = [
            f"time={datetime.now(timezone.utc).isoformat()}",
            f"status={status}",
            f"python={sys.version.split()[0]}",
            f"root={_ROOT}",
        ]
        if details:
            lines.append(f"details={details}")
        for rel, _ in _TARGETS:
            path = _ROOT / rel
            if not path.is_file():
                state = "missing"
            elif _is_stub(path):
                state = f"stub({path.stat().st_size})"
            else:
                state = f"ok({path.stat().st_size})"
            lines.append(f"module={rel}:{state}")
        cp = _ROOT / "app/core/services/control_plane/service.py"
        page = _ROOT / "app/ui/pages/control_plane_page.py"
        lines.append(
            f"module=control_plane/service.py:{'ok' if cp.is_file() and cp.stat().st_size > 5000 else 'missing'}"
        )
        lines.append(
            f"module=control_plane_page.py:{'ok' if page.is_file() and page.stat().st_size > 5000 else 'missing'}"
        )
        (data / "last_materialize.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError:
        pass


def ensure_refactor_modules(*, quiet: bool = True) -> None:
    """Materialize any missing/stub refactor modules. Safe to call every launch."""
    _ensure_task_watch()
    _ensure_control_plane_ui()
    if not needs_materialize():
        _write_health("ok", "no_materialize_needed")
        return
    if not quiet:
        print("Materializing UI modules (first run after update)…", flush=True)
    errors: list[str] = []
    for rel, script_name in _TARGETS:
        path = _ROOT / rel
        if not _is_stub(path):
            continue
        script = _ROOT / "scripts" / script_name
        if not script.exists():
            alt = script_name.replace("fix_", "install_")
            script = _ROOT / "scripts" / alt
        if not script.exists():
            msg = f"Missing installer for {rel}: expected scripts/{script_name}"
            errors.append(msg)
            if not quiet:
                print(f"  ✗ {msg}", flush=True)
            continue
        if not quiet:
            print(f"  → {rel}", flush=True)
        try:
            r = subprocess.run(
                [sys.executable, str(script)],
                cwd=str(_ROOT),
                capture_output=True,
                text=True,
            )
        except OSError as exc:
            errors.append(f"{rel}: could not run installer ({exc})")
            continue
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip()
            hint = ""
            low = err.lower()
            if "incorrect header check" in low or "zlib" in low or "decompress" in low:
                hint = " (payload may be corrupt — re-clone or pull latest main)"
            elif "binascii" in low or "padding" in low or "base64" in low:
                hint = " (base64 payload padding error — re-clone or pull latest main)"
            errors.append(f"{rel}: {err or r.returncode}{hint}")
            continue
        if _is_stub(path):
            errors.append(f"Installer ran but {rel} is still a stub (size check failed)")
            continue
        if not quiet:
            print(f"  ✓ {rel} ({path.stat().st_size} bytes)", flush=True)

    if errors:
        _write_health("error", "; ".join(errors[:5]))
        raise RuntimeError(
            "Failed to materialize UI modules:\n  - "
            + "\n  - ".join(errors)
            + "\n\nFix: clone/pull latest main and run Launch.bat again."
            "\nSee data/last_materialize.txt for details."
        )
    if not quiet:
        print("UI modules ready.", flush=True)
    _write_health("ok", "materialized")


def materialize_status() -> dict[str, str]:
    """Return relative path → state string for diagnostics UI."""
    out: dict[str, str] = {}
    for rel, _ in _TARGETS:
        path = _ROOT / rel
        if not path.is_file():
            out[rel] = "missing"
        elif _is_stub(path):
            out[rel] = f"stub ({path.stat().st_size} bytes)"
        else:
            out[rel] = f"ok ({path.stat().st_size} bytes)"
    return out


if __name__ == "__main__":
    ensure_refactor_modules(quiet=False)
