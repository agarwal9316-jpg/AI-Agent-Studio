"""Simple portable application log (JSON lines under data/logs/).

Used by org AI create and other long operations so timeouts are diagnosable
without a console.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.paths import data_dir

_lock = threading.Lock()
_MAX_BYTES = 2_000_000  # ~2 MB rotate


def logs_dir() -> Path:
    d = data_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def app_log_path() -> Path:
    return logs_dir() / "app.log"


def org_ai_log_path() -> Path:
    return logs_dir() / "org_ai.log"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rotate_if_needed(path: Path) -> None:
    try:
        if path.exists() and path.stat().st_size > _MAX_BYTES:
            bak = path.with_suffix(".log.1")
            if bak.exists():
                bak.unlink()
            path.rename(bak)
    except OSError:
        pass


def log_event(
    event: str,
    *,
    level: str = "info",
    channel: str = "app",
    **fields: Any,
) -> None:
    """Append one JSON line. Never raises to callers."""
    try:
        path = org_ai_log_path() if channel == "org_ai" else app_log_path()
        _rotate_if_needed(path)
        row = {
            "ts": _now(),
            "level": level,
            "event": str(event),
            **{k: v for k, v in fields.items() if v is not None},
        }
        # Never write raw secrets
        for secret_key in ("api_key", "key", "llm_api_key", "Authorization"):
            if secret_key in row:
                val = str(row[secret_key] or "")
                row[secret_key] = (val[:4] + "…" + val[-2:]) if len(val) > 8 else "(set)" if val else ""
        line = json.dumps(row, ensure_ascii=False, default=str) + "\n"
        with _lock:
            with path.open("a", encoding="utf-8") as f:
                f.write(line)
    except Exception:  # noqa: BLE001
        pass


def read_tail(channel: str = "app", *, max_lines: int = 80) -> str:
    """Return last N lines of a log file (for Troubleshooting / About)."""
    try:
        path = org_ai_log_path() if channel == "org_ai" else app_log_path()
        if not path.exists():
            return f"(no log yet: {path})"
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-max_lines:])
    except Exception as e:  # noqa: BLE001
        return f"(log read failed: {e})"
