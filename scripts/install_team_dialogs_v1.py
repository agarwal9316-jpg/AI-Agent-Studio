"""Materialize app/ui/pages/team_dialogs.py from zlib+base64 payload chunks."""
from __future__ import annotations

import base64
import zlib
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_TARGET = _ROOT / "app" / "ui" / "pages" / "team_dialogs.py"
_PAYLOAD = _ROOT / "scripts" / "refactor_payload"
_PREFIX = "team_dialogs.z"


def main() -> None:
    parts = sorted(_PAYLOAD.glob(f"{_PREFIX}*.b64"))
    if not parts:
        raise SystemExit(f"No payload chunks for {_PREFIX}")
    b64 = "".join(p.read_text(encoding="ascii").strip() for p in parts)
    raw = zlib.decompress(base64.b64decode(b64))
    _TARGET.parent.mkdir(parents=True, exist_ok=True)
    _TARGET.write_bytes(raw)
    print(f"Wrote {_TARGET} ({len(raw)} bytes) from {len(parts)} chunks")


if __name__ == "__main__":
    main()
