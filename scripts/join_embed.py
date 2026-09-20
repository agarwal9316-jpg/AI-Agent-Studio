#!/usr/bin/env python3
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
parts = sorted((ROOT / "scripts" / "cp_embed_parts").glob("embed.p*.txt"))
text = "".join(p.read_text(encoding="utf-8") for p in parts)
dest = ROOT / "scripts" / "install_cp_embedded.py"
dest.write_text(text, encoding="utf-8")
print("wrote", dest, len(text))
