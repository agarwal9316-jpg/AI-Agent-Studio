"""Bootstrap for app_window — materializes full thin host from payload if needed."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys

_FILE = Path(__file__).resolve()
_ROOT = _FILE.parents[2]

if _FILE.stat().st_size < 5000:
    script = _ROOT / "scripts" / "fix_app_window_v2.py"
    subprocess.check_call([sys.executable, str(script)], cwd=str(_ROOT))
    exec(compile(_FILE.read_text(encoding="utf-8"), str(_FILE), "exec"), globals())
