"""Scheduled / recurring company agent tasks (native cron-like)."""

from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from app.paths import data_dir
from app.core.services.data.storage import _read_json, _write_json

_lock = threading.Lock()
_thread: threading.Thread | None = None
_running = False
_listeners: list[Callable[[str], None]] = []


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def schedules_path():
    return data_dir() / "schedules.json"


def load_schedules() -> list[dict[str, Any]]:
    data = _read_json(schedules_path(), {"items": []})
    if isinstance(data, dict):
        return list(data.get("items") or [])
    return []


def save_schedules(items: list[dict[str, Any]]) -> None:
    _write_json(schedules_path(), {"items": items, "updated_at": _now()})


def add_schedule(
    *,
    title: str,
    prompt: str,
    interval_minutes: int = 60,
    role_id: str = "engineer",
    enabled: bool = True,
) -> dict[str, Any]:
    items = load_schedules()
    item = {
        "id": str(uuid.uuid4()),
        "title": (title or "Scheduled task").strip(),
        "prompt": (prompt or "").strip(),
        "interval_minutes": max(1, int(interval_minutes)),
        "role_id": role_id or "engineer",
        "enabled": bool(enabled),
        "last_run": "",
        "next_run": _now(),
        "created_at": _now(),
        "run_count": 0,
    }
    items.insert(0, item)
    save_schedules(items)
    start()
    return item


def delete_schedule(sid: str) -> bool:
    items = [i for i in load_schedules() if i.get("id") != sid]
    save_schedules(items)
    return True


def set_enabled(sid: str, enabled: bool) -> None:
    items = load_schedules()
    for i in items:
        if i.get("id") == sid:
            i["enabled"] = bool(enabled)
    save_schedules(items)


def _due(item: dict[str, Any], now_ts: float) -> bool:
    if not item.get("enabled"):
        return False
    last = item.get("last_run") or ""
    interval = max(1, int(item.get("interval_minutes") or 60)) * 60
    if not last:
        return True
    try:
        # parse ISO
        from datetime import datetime

        t = datetime.fromisoformat(last.replace("Z", "+00:00")).timestamp()
        return (now_ts - t) >= interval
    except Exception:  # noqa: BLE001
        return True


def _fire(item: dict[str, Any]) -> None:
    """Queue a company work task for background orchestrator."""
    try:
        from app.services import company_store as company
        from app.core.services.chat.orchestrator import get_orchestrator

        title = item.get("title") or "Scheduled"
        desc = item.get("prompt") or title
        t = company.new_work_task(
            title=f"[sched] {title}",
            role_id=item.get("role_id") or "engineer",
            description=desc,
        )
        if company.get_approval_mode() == "auto":
            t["auto_approved"] = True
            company.save_work_task(t)
        get_orchestrator().kick()
        _emit(f"Scheduled fire: {title} → task {t.get('id', '')[:8]}")
    except Exception as e:  # noqa: BLE001
        _emit(f"Schedule fire failed: {e}")


def tick() -> int:
    """Run due schedules once. Returns number fired."""
    now_ts = time.time()
    items = load_schedules()
    n = 0
    for item in items:
        if _due(item, now_ts):
            _fire(item)
            item["last_run"] = _now()
            item["run_count"] = int(item.get("run_count") or 0) + 1
            n += 1
    if n:
        save_schedules(items)
    return n


def _loop() -> None:
    global _running
    while _running:
        try:
            tick()
        except Exception as e:  # noqa: BLE001
            _emit(f"scheduler error: {e}")
        time.sleep(30)


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

        alog(msg, source="sched")
    except Exception:  # noqa: BLE001
        pass


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
