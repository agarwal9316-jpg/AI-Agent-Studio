"""Chat thinking UI — extracted from AppWindow.\n\nOn first import, if this file is still a stub, materializes full source from\nverified zlib+base64 payloads via scripts/install_chat_thinking_v2.py.\n"""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys

_FILE = Path(__file__).resolve()
_ROOT = _FILE.parents[3]
_MARKER = "def thinking_add_card"


def _materialize() -> None:
    script = _ROOT / "scripts" / "install_chat_thinking_v2.py"
    if not script.exists():
        raise ImportError(f"Missing installer: {script}")
    subprocess.check_call([sys.executable, str(script)], cwd=str(_ROOT))


# Auto-install when only stub is present
_src = _FILE.read_text(encoding="utf-8")
if _MARKER not in _src:
    _materialize()
    # Reload this module from the freshly written file
    _src = _FILE.read_text(encoding="utf-8")
    exec(compile(_src, str(_FILE), "exec"), globals())
else:
    # Full module already present (developer replaced stub)
    pass
