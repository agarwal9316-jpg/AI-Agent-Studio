#!/usr/bin/env python3
"""Fix settings_page_v2 payload transcription errors and install."""
from __future__ import annotations
from pathlib import Path
import re, zlib, base64

ROOT = Path(__file__).resolve().parents[1]
PD = ROOT / "scripts" / "refactor_payload"
OUT = ROOT / "app/ui/pages/settings_page.py"

def main() -> None:
    # z01: missing char + wrong sequence around pos 1194
    z01 = PD / "settings_page_v2.z01.b64"
    t = re.sub(r"\s+", "", z01.read_text(encoding="ascii"))
    bad = "AdeR19hQf38TS195"
    good = "AcegV19hQf38TS195"
    if bad in t:
        t = t.replace(bad, good, 1)
        print(f"z01: replaced {bad!r} -> {good!r}")
    elif good in t:
        print("z01: substring already correct")
    else:
        print(f"z01: unexpected around 1194: {t[1185:1220]!r}")

    # z01 single-char at 3097 (after length restored)
    if len(t) >= 3098 and t[3097] != "1":
        print(f"z01[3097] {t[3097]!r} -> '1'")
        t = t[:3097] + "1" + t[3098:]
    elif len(t) >= 3098:
        print("z01[3097] already correct")

    lines = [t[i:i+80] for i in range(0, len(t), 80)]
    z01.write_text("\n".join(lines) + "\n", encoding="ascii")

    parts = sorted(p for p in PD.glob("settings_page_v2.z*.b64") if re.search(r"\.z\d{2}\.b64$", p.name))
    b64 = "".join(re.sub(r"\s+", "", p.read_text(encoding="ascii")) for p in parts)
    data = zlib.decompress(base64.b64decode(b64))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(data)
    print(f"OK wrote {OUT} ({len(data)} bytes)")

if __name__ == "__main__":
    main()
