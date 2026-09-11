"""Live activity log so the user can see what the LLM / tools are doing."""

from __future__ import annotations

import re
import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.paths import data_dir

_lock = threading.Lock()
_lines: deque[str] = deque(maxlen=2000)
_listeners: list[Callable[[str], None]] = []

# Do not spam idle heartbeats into the terminal panel
_IDLE_PATTERNS = [
    re.compile(r"idle\s*[—\-–].*no queued", re.I),
    re.compile(r"idle\s*-\s*no queued", re.I),
    re.compile(r"^idle$", re.I),
    re.compile(r"no queued company tasks", re.I),
    re.compile(r"waiting for tool/llm activity", re.I),
]


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _is_idle_noise(message: str) -> bool:
    msg = (message or "").strip()
    if not msg:
        return True
    for pat in _IDLE_PATTERNS:
        if pat.search(msg):
            return True
    return False


def log(message: str, *, source: str = "app") -> None:
    if _is_idle_noise(message):
        return
    line = f"[{_now()}][{source}] {message}"
    with _lock:
        _lines.append(line)
        listeners = list(_listeners)
    for fn in listeners:
        try:
            fn(line)
        except Exception:  # noqa: BLE001
            pass


def get_text(limit: int = 500) -> str:
    with _lock:
        items = list(_lines)[-limit:]
    return "\n".join(items)


def clear() -> None:
    with _lock:
        _lines.clear()
    # intentional system note (not idle)
    line = f"[{_now()}][system] activity cleared"
    with _lock:
        _lines.append(line)
        listeners = list(_listeners)
    for fn in listeners:
        try:
            fn(line)
        except Exception:  # noqa: BLE001
            pass


def add_listener(fn: Callable[[str], None]) -> None:
    with _lock:
        _listeners.append(fn)


def remove_listener(fn: Callable[[str], None]) -> None:
    with _lock:
        if fn in _listeners:
            _listeners.remove(fn)


def export_log(path: Path | None = None) -> Path:
    exports = data_dir() / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    if path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = exports / f"terminal_activity_{ts}.log"
    path = Path(path)
    try:
        from app.core.services.misc.redact import redact_text

        text = redact_text(get_text(2000) or "(empty)\n")
    except Exception:  # noqa: BLE001
        text = get_text(2000) or "(empty)\n"
    path.write_text(text, encoding="utf-8")
    return path
