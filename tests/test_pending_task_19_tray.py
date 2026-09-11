"""Tests for PENDING_TASKS.md #19 system tray + run in background."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    fails: list[str] = []

    def check(ok: bool, msg: str) -> None:
        print(("OK  " if ok else "FAIL") + " " + msg)
        if not ok:
            fails.append(msg)

    from app.version import __version__
    from app.core.services.system import system_tray as tray
    from app.core.services.data.storage import load_config, save_config

    check(__version__ == "1.27.81", f"version is 1.27.81 (got {__version__})")
    check(tray.is_supported() is True, "pystray+Pillow supported in this env")
    st = tray.status()
    check(isinstance(st, dict), "status dict")
    check(st.get("supported") is True, "status.supported")
    check("enabled" in st and "start_minimized" in st, "status keys")

    cfg0 = load_config()
    prev = {
        "system_tray_enabled": cfg0.get("system_tray_enabled", True),
        "start_minimized": cfg0.get("start_minimized", False),
        "close_to_tray": cfg0.get("close_to_tray", True),
        "minimize_to_tray": cfg0.get("minimize_to_tray", True),
    }
    try:
        tray.set_tray_enabled(True)
        check(tray.tray_enabled() is True, "tray_enabled True")
        tray.set_start_minimized(True)
        check(tray.start_minimized() is True, "start_minimized True")
        tray.set_start_minimized(False)
        check(tray.start_minimized() is False, "start_minimized False")
        tray.set_close_to_tray(False)
        check(tray.close_to_tray() is False, "close_to_tray False")
        tray.set_close_to_tray(True)
        check(tray.close_to_tray() is True, "close_to_tray True")
        tray.set_minimize_to_tray(False)
        check(tray.minimize_to_tray() is False, "minimize_to_tray False")
        tray.set_minimize_to_tray(True)
        check(tray.minimize_to_tray() is True, "minimize_to_tray True")
        check(tray.should_use_tray() is True, "should_use_tray when enabled+supported")
        tray.set_tray_enabled(False)
        check(tray.should_use_tray() is False, "should_use_tray False when disabled")
        tray.set_tray_enabled(True)
    finally:
        cfg = load_config()
        cfg.update(prev)
        save_config(cfg)

    icon = tray.ensure_tray_icon_asset()
    check(icon.is_file(), f"tray icon asset exists ({icon})")
    check(icon.stat().st_size > 50, "tray icon non-trivial size")

    # Callbacks wire without starting GUI
    called: dict[str, int] = {"show": 0, "hide": 0, "quit": 0}
    tray.set_callbacks(
        show=lambda: called.__setitem__("show", called["show"] + 1),
        hide=lambda: called.__setitem__("hide", called["hide"] + 1),
        quit_app=lambda: called.__setitem__("quit", called["quit"] + 1),
    )
    tray._emit("show")
    tray._emit("hide")
    tray._emit("quit")
    check(called == {"show": 1, "hide": 1, "quit": 1}, f"callbacks fired {called}")

    aw = (ROOT / "app" / "ui" / "app_window.py").read_text(encoding="utf-8")
    check("_setup_system_tray" in aw, "app_window has _setup_system_tray")
    check("_hide_to_tray" in aw and "_show_from_tray" in aw, "hide/show helpers")
    check("_quit_from_tray" in aw, "quit from tray")
    check("Start minimized" in aw, "Settings Start minimized")
    check("Show / Hide / Quit" in aw or "Show · Hide · Quit" in aw, "menu documented in Settings")

    req = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    check("pystray" in req, "pystray in requirements.txt")

    bat = (ROOT / "Launch.bat").read_text(encoding="utf-8", errors="replace")
    check("Starting GUI" in bat, "Launch.bat still starts GUI")
    check("-m app" in bat, "Launch.bat still runs python -m app")
    check("requirements.txt" in bat, "Launch.bat still installs requirements")
    # Ensure we did not rewrite Launch.bat
    import subprocess

    diff = subprocess.check_output(
        ["git", "diff", "--", "Launch.bat"], cwd=str(ROOT), text=True
    )
    check(diff.strip() == "", "Launch.bat unmodified")

    pending = (ROOT / "docs" / "PENDING_TASKS.md").read_text(encoding="utf-8")
    row19 = [ln for ln in pending.splitlines() if ln.startswith("| 19 |")]
    check(bool(row19) and "**done**" in row19[0], f"PENDING #19 marked done ({row19[:1]})")

    cl = (ROOT / "docs" / "CHANGELOG.md").read_text(encoding="utf-8")
    check("1.27.81" in cl and "tray" in cl.lower(), "CHANGELOG mentions 1.27.81 tray")

    # services export
    from app.services import system_tray as tray2

    check(tray2 is not None and hasattr(tray2, "start"), "app.services.system_tray export")

    if fails:
        print("FAILED:", fails)
        return 1
    print("All pending-task #19 tray checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
