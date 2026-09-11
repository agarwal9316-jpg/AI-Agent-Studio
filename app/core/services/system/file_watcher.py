"""Watch folders and auto-index new/changed files into Local Knowledge RAG."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Callable

from app.services import rag_knowledge as rag
from app.core.services.data.storage import _read_json, _write_json
from app.paths import data_dir

_lock = threading.Lock()
_thread: threading.Thread | None = None
_running = False
_listeners: list[Callable[[str], None]] = []

TEXT_EXTS = rag.TEXT_EXTS | {".pdf"}
MAX_FILES_PER_SCAN = 80


def config_path() -> Path:
    return data_dir() / "watch_folders.json"


def load_watches() -> list[dict[str, Any]]:
    data = _read_json(config_path(), {"folders": []})
    if isinstance(data, dict):
        return list(data.get("folders") or [])
    return []


def save_watches(folders: list[dict[str, Any]]) -> None:
    _write_json(config_path(), {"folders": folders})


def add_watch(folder: str, *, recursive: bool = True) -> dict[str, Any]:
    p = Path(folder).expanduser()
    try:
        p = p.resolve(strict=False)
    except Exception:  # noqa: BLE001
        return {"ok": False, "error": f"Invalid path: {folder}"}
    if not p.is_dir():
        return {"ok": False, "error": f"Not a directory: {p}"}
    items = load_watches()
    for it in items:
        try:
            if Path(it.get("path") or "").resolve() == p:
                start()
                return {"ok": True, "path": str(p), "already": True}
        except Exception:  # noqa: BLE001
            continue
    items.append(
        {
            "path": str(p),
            "recursive": bool(recursive),
            "last_scan": "",
            "indexed": 0,
            "seen": [],
        }
    )
    save_watches(items)
    start()
    return {"ok": True, "path": str(p)}


def remove_watch(folder: str) -> bool:
    try:
        p = str(Path(folder).expanduser().resolve())
    except Exception:  # noqa: BLE001
        p = str(folder)
    items = []
    for i in load_watches():
        try:
            if str(Path(i.get("path") or "").resolve()) != p:
                items.append(i)
        except Exception:  # noqa: BLE001
            items.append(i)
    save_watches(items)
    return True


def add_listener(fn: Callable[[str], None]) -> None:
    with _lock:
        _listeners.append(fn)


def _emit(msg: str) -> None:
    with _lock:
        ls = list(_listeners)
    for fn in ls:
        try:
            fn(msg)
        except Exception:  # noqa: BLE001
            pass
    try:
        from app.core.services.data.activity_log import log as alog

        alog(msg, source="watch")
    except Exception:  # noqa: BLE001
        pass


def scan_once() -> dict[str, Any]:
    """Scan all watched folders; index a limited number of new/changed files."""
    items = load_watches()
    total = 0
    errors = 0
    updated = []
    for it in items:
        folder = Path(it.get("path") or "")
        if not folder.is_dir():
            continue
        recursive = bool(it.get("recursive", True))
        pattern = "**/*" if recursive else "*"
        count = 0
        seen = set(it.get("seen") or [])
        checked = 0
        try:
            iterator = folder.glob(pattern)
        except Exception:  # noqa: BLE001
            continue
        for fp in iterator:
            if checked >= MAX_FILES_PER_SCAN * 5:
                break
            checked += 1
            if not fp.is_file():
                continue
            if fp.suffix.lower() not in TEXT_EXTS:
                continue
            if any(x in fp.parts for x in (".venv", "node_modules", "__pycache__", ".git", "browsers")):
                continue
            try:
                mtime = int(fp.stat().st_mtime)
                key = f"{fp}|{mtime}"
                if key in seen:
                    continue
                r = rag.index_file(fp)
                if r.get("ok"):
                    count += 1
                    total += 1
                    seen.add(key)
                    if count >= MAX_FILES_PER_SCAN:
                        break
                else:
                    errors += 1
            except Exception:  # noqa: BLE001
                errors += 1
        it["seen"] = list(seen)[-2000:]
        it["indexed"] = int(it.get("indexed") or 0) + count
        it["last_scan"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if count:
            updated.append({"path": str(folder), "new": count})
            _emit(f"Auto-index {count} file(s) in {folder}")
    save_watches(items)
    return {"ok": True, "indexed": total, "errors": errors, "updated": updated}


def _loop(interval: float = 60.0) -> None:
    global _running
    # delay first scan so UI stays responsive after start()
    time.sleep(3.0)
    while _running:
        try:
            if load_watches():
                scan_once()
        except Exception as e:  # noqa: BLE001
            _emit(f"watch error: {e}")
        # interruptible sleep
        for _ in range(int(interval)):
            if not _running:
                break
            time.sleep(1.0)


def start() -> None:
    global _running, _thread
    with _lock:
        if _running:
            return
        _running = True
        _thread = threading.Thread(target=_loop, daemon=True, name="file-watcher")
        _thread.start()
    # emit outside lock
    _emit("File watcher started")


def stop() -> None:
    global _running
    _running = False


def is_running() -> bool:
    return _running


def tool_instructions() -> str:
    return """
## Auto-index folders (file watcher)

User can add watch folders in Knowledge. You may also:
<<<KNOWLEDGE>>>
action: index_folder
path: C:\\path\\to\\notes
recursive: true
<<<END_KNOWLEDGE>>>
""".strip()
