#!/usr/bin/env python3
"""Headless smoke: materialize + compile critical modules (no GUI).

Usage (Windows or any OS):
  python scripts/smoke_launch.py
  .venv\\Scripts\\python.exe scripts\\smoke_launch.py

Exit 0 = ready to Launch.bat; non-zero = print failures.
"""
from __future__ import annotations

import py_compile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CRITICAL = [
    "app/main.py",
    "app/_ensure_refactor_modules.py",
    "app/ui/app_window.py",
    "app/ui/page_router.py",
    "app/ui/components/chat_thinking.py",
    "app/ui/components/chat_rail.py",
    "app/ui/components/chat_send.py",
    "app/ui/components/chat_dialogs.py",
    "app/ui/components/chat_render.py",
    "app/ui/components/chat_misc.py",
    "app/ui/pages/chat_page.py",
    "app/ui/pages/settings_page.py",
    "app/ui/pages/team_page.py",
    "app/ui/pages/team_dialogs.py",
    "app/ui/pages/org_chart_view.py",
    "app/ui/pages/org_chart_widgets.py",
    "app/ui/pages/mgmt_pages.py",
    "app/ui/pages/models_page.py",
    "app/ui/pages/models_advanced.py",
    "app/ui/pages/chats_page.py",
    "app/ui/pages/org_page.py",
    "app/ui/pages/org_page_ai.py",
]


def main() -> int:
    print(f"ROOT={ROOT}")
    print("1) Materialize refactor modules…")
    from app._ensure_refactor_modules import ensure_refactor_modules, materialize_status

    try:
        ensure_refactor_modules(quiet=False)
    except RuntimeError as exc:
        print(f"MATERIALIZE FAILED:\n{exc}")
        return 1

    print("2) Module status:")
    for rel, state in materialize_status().items():
        print(f"  {rel}: {state}")

    print("3) py_compile critical paths…")
    failed = []
    for rel in CRITICAL:
        path = ROOT / rel
        if not path.is_file():
            failed.append(f"{rel}: missing")
            continue
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            failed.append(f"{rel}: {exc}")

    if failed:
        print("COMPILE FAILED:")
        for f in failed:
            print(f"  - {f}")
        return 2

    print("OK — ready for Launch.bat")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
