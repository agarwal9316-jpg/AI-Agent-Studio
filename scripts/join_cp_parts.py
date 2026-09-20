#!/usr/bin/env python3
"""Join scripts/cp_parts/*.pNN.txt into control plane source files."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
PARTS = ROOT / "scripts" / "cp_parts"
TARGETS = {
    "store": ROOT / "app/core/services/control_plane/store.py",
    "service": ROOT / "app/core/services/control_plane/service.py",
    "page": ROOT / "app/ui/pages/control_plane_page.py",
}
def main():
    for key, dest in TARGETS.items():
        chunks = sorted(PARTS.glob(f"{key}.p*.txt"))
        if not chunks:
            print("skip", key)
            continue
        text = "".join(p.read_text(encoding="utf-8") for p in chunks)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        print("wrote", dest, len(text))
if __name__ == "__main__":
    main()
