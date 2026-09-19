"""Bootstrap — auto-materializes module on first import/launch."""
from __future__ import annotations
from pathlib import Path
import sys
_FILE = Path(__file__).resolve()
if _FILE.stat().st_size < 5000:
    _root = _FILE.parents[3]
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))
    from app._ensure_refactor_modules import ensure_refactor_modules
    ensure_refactor_modules(quiet=True)
    exec(compile(_FILE.read_text(encoding="utf-8"), str(_FILE), "exec"), globals())
