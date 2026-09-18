#!/usr/bin/env python3
"""Fix chat_render_v2 payload transcription errors and install."""
from __future__ import annotations
from pathlib import Path
import re, zlib, base64

ROOT = Path(__file__).resolve().parents[1]
PD = ROOT / "scripts" / "refactor_payload"
OUT = ROOT / "app/ui/components/chat_render.py"

# Single-char fixes: (filename, pos, correct_char)
FIXES = [
    ("chat_render_v2.z00.b64", 621, "I"),
    ("chat_render_v2.z01.b64", 3090, "P"),
    ("chat_render_v2.z02.b64", 664, "9"),
    ("chat_render_v2.z02.b64", 1458, "p"),
    ("chat_render_v2.z03.b64", 3165, "Q"),
    ("chat_render_v2.z03.b64", 3393, "J"),
    ("chat_render_v2.z05.b64", 2350, "D"),
]

# z04 has an extra character insertion; replace bad substring with correct one
Z04_BAD = "ZCest5ntOn7MtXi9yqm7Mg4l1sxDMlTAFiVTRoZ3It9L"
Z04_GOOD = "ZAct5ntOn7MtXi9yqm7Mg4l1sxDMlTAFiVTRoZ3It9L"

def main() -> None:
    # Fix z04 first (length issue)
    z04 = PD / "chat_render_v2.z04.b64"
    t = re.sub(r"\s+", "", z04.read_text(encoding="ascii"))
    if Z04_BAD in t:
        t = t.replace(Z04_BAD, Z04_GOOD, 1)
        print(f"z04: replaced bad substring ({len(Z04_BAD)} -> {len(Z04_GOOD)})")
    elif Z04_GOOD in t:
        print("z04: already correct")
    else:
        if len(t) == 3501:
            print(f"z04: length {len(t)}, attempting pos-based fix around 3318")
            if t[3318:3325] == "Cest5nt":
                t = t[:3318] + "Act5nt" + t[3325:]
                print("z04: removed extra e and fixed ZA")
            else:
                print(f"z04: unexpected pattern {t[3315:3330]!r}")
        else:
            print(f"z04: unexpected state len={len(t)}")
    lines = [t[i:i+80] for i in range(0, len(t), 80)]
    z04.write_text("\n".join(lines) + "\n", encoding="ascii")

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

    parts = sorted(p for p in PD.glob("chat_render_v2.z*.b64") if re.search(r"\.z\d{2}\.b64$", p.name))
    b64 = "".join(re.sub(r"\s+", "", p.read_text(encoding="ascii")) for p in parts)
    data = zlib.decompress(base64.b64decode(b64))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(data)
    print(f"OK wrote {OUT} ({len(data)} bytes)")

if __name__ == "__main__":
    main()
