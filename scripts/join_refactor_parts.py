#!/usr/bin/env python3
"""Join scripts/refactor_parts/*.pNNN into final app/ui paths."""
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
PARTS = Path(__file__).resolve().parent / "refactor_parts"

groups = defaultdict(list)
for p in sorted(PARTS.glob("*.p*")):
    name = p.name
    if ".p" not in name:
        continue
    base, _, idx = name.rpartition(".p")
    try:
        groups[base].append((int(idx), p))
    except ValueError:
        continue
for base, items in groups.items():
    items.sort()
    rel = base.replace("__", "/")
    dest = ROOT / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = b"".join(p.read_bytes() for _, p in items)
    dest.write_bytes(data)
    print(f"joined {dest} ({len(data)} bytes from {len(items)} parts)")
print("Done.")
