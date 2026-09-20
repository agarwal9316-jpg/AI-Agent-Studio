#!/usr/bin/env python3
"""Materialize control plane backend + Control plane UI page."""
from __future__ import annotations
import base64, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "scripts" / "refactor_payload"
PREFIX = "cp_ui"

def _load_b64() -> str:
    texts = []
    for i in range(20):
        a = PAYLOAD / f"{PREFIX}.z{i:02d}a.b64"
        b = PAYLOAD / f"{PREFIX}.z{i:02d}b.b64"
        p = PAYLOAD / f"{PREFIX}.z{i:02d}.b64"
        if a.exists():
            t = a.read_text(encoding="utf-8").strip()
            if b.exists():
                t += b.read_text(encoding="utf-8").strip()
            if t and not t.startswith("PLACEHOLDER"):
                texts.append(t)
        elif p.exists():
            t = p.read_text(encoding="utf-8").strip()
            if t.startswith("PLACEHOLDER") or len(t) < 100:
                continue
            texts.append(t)
    return "".join(texts)

def main() -> None:
    b64 = _load_b64()
    if not b64:
        print("No cp_ui payload chunks found")
        return
    pad = (4 - len(b64) % 4) % 4
    b64 += "=" * pad
    raw = zlib.decompress(base64.b64decode(b64))
    header, body = raw.split(b"\n--\n", 1)
    offset = 0
    for line in header.decode().splitlines():
        if not line.strip() or "|" not in line:
            continue
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
