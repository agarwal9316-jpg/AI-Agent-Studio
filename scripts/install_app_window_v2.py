#!/usr/bin/env python3
"""Install app_window from verified zlib+base64 payload chunks (v2)."""
from __future__ import annotations
import base64, zlib
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = Path(__file__).resolve().parent / "refactor_payload"
OUT = ROOT / 'app/ui/app_window.py'
def main() -> None:
    parts = sorted(PAYLOAD.glob("app_window_v2.z*.b64"))
    if not parts:
        raise SystemExit(f"No payload chunks in {PAYLOAD}")
    b64 = "".join(p.read_text(encoding="ascii").strip() for p in parts)
    data = zlib.decompress(base64.b64decode(b64))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(data)
    print(f"wrote {OUT} ({len(data)} bytes)")
if __name__ == "__main__":
    main()
