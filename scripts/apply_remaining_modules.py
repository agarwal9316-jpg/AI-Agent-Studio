#!/usr/bin/env python3
"""Apply remaining refactor modules from scripts/refactor_payload/*.b64

Usage (from repo root):
  python scripts/apply_remaining_modules.py

This writes the extracted page/component files + thinned app_window.py
into app/ui/ without needing GitHub upload limits.
"""
from __future__ import annotations
import base64
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = Path(__file__).resolve().parent / "refactor_payload"

def main() -> None:
    if not PAYLOAD.is_dir():
        raise SystemExit(f"Missing payload dir: {PAYLOAD}")
    count = 0
    for b64_path in sorted(PAYLOAD.glob("*.b64")):
        rel = b64_path.name[:-4].replace("__", "/")  # strip .b64
        dest = ROOT / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        data = base64.b64decode(b64_path.read_text(encoding="ascii"))
        dest.write_bytes(data)
        print(f"wrote {dest} ({len(data)} bytes)")
        count += 1
    print(f"Done. {count} files written.")
    print("Next: run Start.bat / Launch.bat and smoke-test Chat, Settings, sidebar.")

if __name__ == "__main__":
    main()
