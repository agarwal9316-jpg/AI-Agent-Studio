#!/usr/bin/env python3
"""One-shot fix for chat_dialogs_v2 payload transcription errors."""
from __future__ import annotations
from pathlib import Path
import re, zlib, base64

ROOT = Path(__file__).resolve().parents[1]
PD = ROOT / "scripts" / "refactor_payload"

# (filename, position_in_stripped_b64, correct_char)
FIXES = [
    ("chat_dialogs_v2.z00.b64", 3202, "c"),
    ("chat_dialogs_v2.z02.b64", 394, "K"),
    ("chat_dialogs_v2.z04.b64", 2562, "3"),
    ("chat_dialogs_v2.z05.b64", 242, "q"),
    ("chat_dialogs_v2.z05.b64", 254, "k"),
    ("chat_dialogs_v2.z05.b64", 1050, "f"),
]

def main() -> None:
    for name, pos, ch in FIXES:
        fp = PD / name
        raw_text = fp.read_text(encoding="ascii")
        # work on stripped version, then re-wrap
        stripped = re.sub(r"\s+", "", raw_text)
        if stripped[pos] == ch:
            print(f"{name}[{pos}] already correct ({ch!r})")
            continue
        print(f"{name}[{pos}] {stripped[pos]!r} -> {ch!r}")
        stripped = stripped[:pos] + ch + stripped[pos+1:]
        lines = [stripped[i:i+80] for i in range(0, len(stripped), 80)]
        fp.write_text("\n".join(lines) + "\n", encoding="ascii")
    # verify full decompress
    parts = sorted(p for p in PD.glob("chat_dialogs_v2.z*.b64") if re.search(r"\.z\d{2}\.b64$", p.name))
    b64 = "".join(re.sub(r"\s+", "", p.read_text(encoding="ascii")) for p in parts)
    data = zlib.decompress(base64.b64decode(b64))
    out = ROOT / "app" / "ui" / "components" / "chat_dialogs.py"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    print(f"OK wrote {out} ({len(data)} bytes)")

if __name__ == "__main__":
    main()
