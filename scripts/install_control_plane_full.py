#!/usr/bin/env python3
"""Materialize control_plane store/adapters/service from payload chunks."""
from __future__ import annotations
import base64, json, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "scripts" / "refactor_payload"
DEST = ROOT / "app" / "core" / "services" / "control_plane"

def main() -> None:
    parts = sorted(PAYLOAD.glob("control_plane_full.z*.b64"))
    if not parts:
        print("No control_plane_full chunks found")
        return
    b64 = "".join(p.read_text().strip() for p in parts)
    data = json.loads(zlib.decompress(base64.b64decode(b64)).decode("utf-8"))
    DEST.mkdir(parents=True, exist_ok=True)
    for name, content in data.items():
        path = DEST / name
        path.write_text(content, encoding="utf-8")
        print("wrote", path, len(content), "bytes")
    print("control_plane materialize OK")

if __name__ == "__main__":
    main()
