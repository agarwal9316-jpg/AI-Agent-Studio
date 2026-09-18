#!/usr/bin/env python3
"""Install all extracted refactor modules (v2). Prefers fix_* scripts when present."""
from __future__ import annotations
import subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
ORDER = [
    "chat_thinking", "chat_rail", "chat_send", "chat_dialogs",
    "chat_render", "chat_misc", "chat_page", "settings_page", "app_window",
]
def main() -> int:
    for name in ORDER:
        fix = ROOT / "scripts" / f"fix_{name}_v2.py"
        install = ROOT / "scripts" / f"install_{name}_v2.py"
        script = fix if fix.exists() else install
        if not script.exists():
            print(f"MISSING {script}", file=sys.stderr)
            return 1
        print(f"=== {name} ({script.name}) ===")
        r = subprocess.run([sys.executable, str(script)], cwd=str(ROOT))
        if r.returncode != 0:
            return r.returncode
    print("ALL MODULES MATERIALIZED")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
