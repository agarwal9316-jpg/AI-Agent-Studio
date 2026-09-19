#!/usr/bin/env python3
"""Restore full task_watch.py from payload chunks."""
from __future__ import annotations
import base64, zlib
from pathlib import Path
_ROOT = Path(__file__).resolve().parents[1]
_PAYLOAD = _ROOT / "scripts" / "refactor_payload"
_OUT = _ROOT / "app" / "core" / "services" / "chat" / "task_watch.py"
def main() -> None:
    parts = sorted(_PAYLOAD.glob("task_watch_restore.z*.b64"))
    if not parts:
        raise SystemExit("No task_watch_restore chunks")
    b64 = "".join(p.read_text(encoding="ascii").strip() for p in parts)
    raw = zlib.decompress(base64.b64decode(b64))
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_bytes(raw)
    print(f"Wrote {_OUT} ({len(raw)} bytes)")
if __name__ == "__main__":
    main()
