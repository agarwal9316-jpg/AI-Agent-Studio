#!/usr/bin/env python3
"""Materialize control plane backend + Control plane UI page."""
from __future__ import annotations
import base64, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "scripts" / "refactor_payload"
PREFIX = "cp_ui"

def main() -> None:
    parts = sorted(PAYLOAD.glob(f"{PREFIX}.z*.b64"))
    if not parts:
        print("No cp_ui payload chunks found")
        return
    b64 = "".join(p.read_text(encoding="utf-8").strip() for p in parts)
    raw = zlib.decompress(base64.b64decode(b64))
    header, body = raw.split(b"\n--\n", 1)
    offset = 0
    for line in header.decode().splitlines():
        path_s, size_s = line.split("|", 1)
        size = int(size_s)
        data = body[offset : offset + size]
        offset += size
        dest = ROOT / path_s
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        print("wrote", dest, len(data), "bytes")
    print("Control plane UI + modules installed.")

if __name__ == "__main__":
    main()
