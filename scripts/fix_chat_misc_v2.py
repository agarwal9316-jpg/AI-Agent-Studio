#!/usr/bin/env python3
"""Fix chat_misc_v2 payload transcription errors and install."""
from __future__ import annotations
from pathlib import Path
import re, zlib, base64

ROOT = Path(__file__).resolve().parents[1]
PD = ROOT / "scripts" / "refactor_payload"
OUT = ROOT / "app/ui/components/chat_misc.py"

FIXES = [
    ("chat_misc_v2.z00.b64", 2829, "2"),
    ("chat_misc_v2.z00.b64", 2889, "3"),
    ("chat_misc_v2.z00.b64", 2890, "8"),
    ("chat_misc_v2.z01.b64", 553, "S"),
    ("chat_misc_v2.z01.b64", 1829, "K"),
    ("chat_misc_v2.z02.b64", 2893, "7"),
    ("chat_misc_v2.z02.b64", 2894, "5"),
    ("chat_misc_v2.z03.b64", 1957, "J"),
    ("chat_misc_v2.z03.b64", 2832, "h"),
    ("chat_misc_v2.z04.b64", 2878, "g"),
    ("chat_misc_v2.z04.b64", 3278, "K"),
    ("chat_misc_v2.z05.b64", 878, "k"),
    ("chat_misc_v2.z05.b64", 2569, "8"),
    ("chat_misc_v2.z07.b64", 750, "K"),
]

def main() -> None:
    # z04 missing character insertion (must run before single-char fixes on z04)
    z04 = PD / "chat_misc_v2.z04.b64"
    t = re.sub(r"\s+", "", z04.read_text(encoding="ascii"))
    if len(t) == 3499 and t[2000:2004] == "uFLj":
        t = t[:2000] + "z" + t[2000:]
        print("z04: inserted 'z' at 2000")
        lines = [t[i:i+80] for i in range(0, len(t), 80)]
        z04.write_text("\n".join(lines) + "\n", encoding="ascii")
    elif len(t) == 3500 and t[2000:2005] == "zuFLj":
        print("z04: insert already applied")
    else:
        print(f"z04: state len={len(t)} ctx={t[1995:2010]!r}")

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

    parts = sorted(p for p in PD.glob("chat_misc_v2.z*.b64") if re.search(r"\.z\d{2}\.b64$", p.name))
    b64 = "".join(re.sub(r"\s+", "", p.read_text(encoding="ascii")) for p in parts)
    data = zlib.decompress(base64.b64decode(b64))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(data)
    print(f"OK wrote {OUT} ({len(data)} bytes)")

if __name__ == "__main__":
    main()
