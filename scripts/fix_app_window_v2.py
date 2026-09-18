#!/usr/bin/env python3
"""Fix app_window_v2 payload transcription errors and install."""
from __future__ import annotations
from pathlib import Path
import re, zlib, base64

ROOT = Path(__file__).resolve().parents[1]
PD = ROOT / "scripts" / "refactor_payload"
OUT = ROOT / "app/ui/app_window.py"

FIXES = [
    ("app_window_v2.z01.b64", 1478, "L"),
    ("app_window_v2.z03.b64", 3358, "F"),
    ("app_window_v2.z05.b64", 1042, "7"),
    ("app_window_v2.z09.b64", 245, "B"),
    ("app_window_v2.z10.b64", 2146, "8"),
    ("app_window_v2.z11.b64", 857, "3"),
    ("app_window_v2.z11.b64", 2721, "n"),
    ("app_window_v2.z12.b64", 1037, "j"),
    ("app_window_v2.z12.b64", 2312, "9"),
    ("app_window_v2.z13.b64", 321, "d"),
]

def main() -> None:
    for name, pos, ch in FIXES:
        fp = PD / name
        stripped = re.sub(r"\s+", "", fp.read_text(encoding="ascii"))
        if stripped[pos] == ch:
            print(f"{name}[{pos}] already correct")
            continue
        print(f"{name}[{pos}] {stripped[pos]!r} -> {ch!r}")
        stripped = stripped[:pos] + ch + stripped[pos+1:]
        lines = [stripped[i:i+80] for i in range(0, len(stripped), 80)]
        fp.write_text("\n".join(lines) + "\n", encoding="ascii")

    parts = sorted(p for p in PD.glob("app_window_v2.z*.b64") if re.search(r"\.z\d{2}\.b64$", p.name))
    b64 = "".join(re.sub(r"\s+", "", p.read_text(encoding="ascii")) for p in parts)
    data = zlib.decompress(base64.b64decode(b64))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(data)
    print(f"OK wrote {OUT} ({len(data)} bytes)")

if __name__ == "__main__":
    main()
