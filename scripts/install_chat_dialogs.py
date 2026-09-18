#!/usr/bin/env python3
"""Install chat_dialogs.py from zlib+base64 payload chunks."""
from __future__ import annotations
import base64
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = Path(__file__).resolve().parent / "refactor_payload"
OUT = ROOT / "app" / "ui" / "components" / "chat_dialogs.py"

def main() -> None:
    parts = sorted(PAYLOAD.glob("chat_dialogs.z*.b64"))
    if not parts:
        raise SystemExit(f"No payload chunks in {PAYLOAD}")
    b64 = "".join(p.read_text(encoding="ascii").strip() for p in parts)
    data = zlib.decompress(base64.b64decode(b64))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(data)
    print(f"wrote {OUT} ({len(data)} bytes)")

if __name__ == "__main__":
    main()
