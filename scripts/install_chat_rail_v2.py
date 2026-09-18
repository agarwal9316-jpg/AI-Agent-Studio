#!/usr/bin/env python3
"""Install chat_rail from verified zlib+base64 payload chunks (v2)."""
from __future__ import annotations
import base64, zlib, re
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = Path(__file__).resolve().parent / "refactor_payload"
OUT = ROOT / 'app/ui/components/chat_rail.py'
def main() -> None:
    parts = sorted(p for p in PAYLOAD.glob("chat_rail_v2.z*.b64") if re.search(r"\.z\d{2}\.b64$", p.name))
    if not parts:
        raise SystemExit(f"No payload chunks in {PAYLOAD}")
    b64 = "".join(re.sub(r"\s+", "", p.read_text(encoding="ascii")) for p in parts)
    data = zlib.decompress(base64.b64decode(b64))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(data)
    print(f"wrote {OUT} ({len(data)} bytes)")
if __name__ == "__main__":
    main()
