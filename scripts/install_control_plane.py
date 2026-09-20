#!/usr/bin/env python3
"""Install control_plane store/service/adapters from payload."""
from __future__ import annotations
import base64, json, zlib
from pathlib import Path
_ROOT = Path(__file__).resolve().parents[1]
_P = _ROOT / "scripts" / "refactor_payload"
def main() -> None:
    parts = sorted(_P.glob("control_plane.z*.b64"))
    b64 = "".join(p.read_text().strip() for p in parts)
    blob = json.loads(zlib.decompress(base64.b64decode(b64)).decode())
    for rel, enc in blob.items():
        raw = zlib.decompress(base64.b64decode(enc))
        out = _ROOT / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(raw)
        print(f"Wrote {out} ({len(raw)} bytes)")
if __name__ == "__main__":
    main()
