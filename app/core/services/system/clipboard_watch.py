"""Smart clipboard watch: detect file paths / images for auto-attach."""

from __future__ import annotations

import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable

_lock = threading.Lock()
_running = False
_thread: threading.Thread | None = None
_last_text = ""
_listeners: list[Callable[[dict[str, Any]], None]] = []

_PATH_RE = re.compile(
    r'(?:[A-Za-z]:\\[^\s\|<>"]+|\\\\[^\s\|<>"]+|/(?:Users|home|tmp|var)[^\s\|<>"]+)',
)


def add_listener(fn: Callable[[dict[str, Any]], None]) -> None:
    with _lock:
        _listeners.append(fn)


def remove_listener(fn: Callable[[dict[str, Any]], None]) -> None:
    with _lock:
        if fn in _listeners:
            _listeners.remove(fn)


def _notify(ev: dict[str, Any]) -> None:
    with _lock:
        ls = list(_listeners)
    for fn in ls:
        try:
            fn(ev)
        except Exception:  # noqa: BLE001
            pass


def _read_clipboard_text() -> str:
    """PowerShell only — never create a second Tk root (hangs with CustomTkinter)."""
    try:
        p = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "try { Get-Clipboard -Raw -ErrorAction Stop } catch { '' }",
            ],
            capture_output=True,
            text=True,
            timeout=4,
        )
        return (p.stdout or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def analyze_clipboard(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        return {"ok": False, "kind": "empty"}
    paths = []
    path_chars = 0
    for m in _PATH_RE.finditer(text):
        raw = m.group(0).strip().strip('"')
        path_chars += len(raw)
        p = Path(raw)
        if p.exists():
            paths.append(str(p.resolve()))
    # A sentence that *mentions* a path is text (composer paste), not an attach.
    leftover = max(0, len(text) - path_chars)
    if leftover > 24 and len(text) > 40:
        return {
            "ok": True,
            "kind": "text",
            "text": text[:2000],
            "paths": [],
            "images": [],
            "files": [],
        }
    if not paths:
        p = Path(text.strip().strip('"'))
        if len(text) < 400 and p.exists() and p.is_file():
            paths.append(str(p.resolve()))
    # Never auto-attach folders (clipboard leftover Desktop\AI dumped the tree)
    files_only: list[str] = []
    for raw_p in paths:
        try:
            pp = Path(raw_p)
            if not pp.exists() or pp.is_dir():
                continue
            if pp.name.lower() in {"ai", "ai working"}:
                continue
            files_only.append(str(pp.resolve()))
        except Exception:  # noqa: BLE001
            continue
    paths = files_only
    images = [
        p
        for p in paths
        if Path(p).suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
    ]
    files = [p for p in paths if p not in images]
    kind = "text"
    if images:
        kind = "image_paths"
    elif files:
        kind = "file_paths"
    elif text.startswith("http://") or text.startswith("https://"):
        kind = "url"
    return {
        "ok": True,
        "kind": kind,
        "text": text[:2000],
        "paths": paths,
        "images": images,
        "files": files,
    }


def _loop(interval: float = 1.5) -> None:
    global _running, _last_text
    while _running:
        try:
            text = _read_clipboard_text()
            if text and text != _last_text:
                _last_text = text
                info = analyze_clipboard(text)
                if info.get("ok") and info.get("kind") in ("file_paths", "image_paths", "url"):
                    _notify({"type": "clipboard", **info})
        except Exception:  # noqa: BLE001
            pass
        time.sleep(interval)


def start() -> None:
    global _running, _thread
    with _lock:
        if _running:
            return
        _running = True
        _thread = threading.Thread(target=_loop, daemon=True)
        _thread.start()


def stop() -> None:
    global _running
    _running = False


def is_running() -> bool:
    return _running
