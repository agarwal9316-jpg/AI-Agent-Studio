"""
Unified approval queue for dangerous tool actions + company tasks.
Surfaces in the Approvals page / chat Live panel.
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from app.paths import data_dir
from app.core.services.data.storage import _read_json, _write_json, load_config

_lock = threading.Lock()
_listeners: list[Callable[[], None]] = []
# Pending tool approvals waiting for UI decision (blocking via Event)
_pending_events: dict[str, threading.Event] = {}
_pending_decisions: dict[str, str] = {}  # id -> approve|reject


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def approvals_path():
    return data_dir() / "tool_approvals.json"


def _load() -> dict[str, Any]:
    data = _read_json(approvals_path(), None)
    if isinstance(data, dict) and "items" in data:
        return data
    return {"items": [], "updated_at": _now()}


def _save(data: dict[str, Any]) -> None:
    data["updated_at"] = _now()
    _write_json(approvals_path(), data)


def add_listener(fn: Callable[[], None]) -> None:
    with _lock:
        _listeners.append(fn)


def _notify() -> None:
    with _lock:
        ls = list(_listeners)
    for fn in ls:
        try:
            fn()
        except Exception:  # noqa: BLE001
            pass


def tool_approval_required() -> bool:
    """When True, risky tools wait for user approval before running."""
    cfg = load_config()
    return bool(cfg.get("tool_approval_required") or cfg.get("safety_mode"))


def list_pending() -> list[dict[str, Any]]:
    with _lock:
        data = _load()
    return [i for i in (data.get("items") or []) if i.get("status") == "pending"]


def list_all(limit: int = 80) -> list[dict[str, Any]]:
    with _lock:
        data = _load()
    items = list(data.get("items") or [])
    return items[:limit]


def request_tool_approval(
    *,
    tool: str,
    summary: str,
    detail: str = "",
    agent: str = "Chat",
    chat_id: str = "",
    wait: bool = True,
    timeout: float = 300.0,
) -> dict[str, Any]:
    """
    Create a pending approval. If wait=True, block until approve/reject/timeout.
    Returns dict with status: approved|rejected|timeout|auto
    """
    cfg = load_config()
    if not tool_approval_required() and not cfg.get("always_approve_tools"):
        # auto-allow unless safety / tool_approval_required
        if not cfg.get("tool_approval_required"):
            return {"status": "auto", "id": "", "summary": summary}

    aid = str(uuid.uuid4())
    item = {
        "id": aid,
        "kind": "tool",
        "tool": tool,
        "summary": summary[:500],
        "detail": (detail or "")[:4000],
        "agent": agent,
        "chat_id": chat_id,
        "status": "pending",
        "created_at": _now(),
        "resolved_at": "",
    }
    with _lock:
        data = _load()
        data.setdefault("items", []).insert(0, item)
        data["items"] = data["items"][:500]
        _save(data)
        if wait:
            ev = threading.Event()
            _pending_events[aid] = ev
    _notify()
    try:
        from app.core.services.data.activity_log import log as alog

        alog(f"APPROVAL needed: {tool} — {summary[:80]}", source="approve")
    except Exception:  # noqa: BLE001
        pass

    if not wait:
        return item

    ev = _pending_events.get(aid)
    if not ev:
        return {**item, "status": "timeout"}
    ok = ev.wait(timeout=timeout)
    with _lock:
        decision = _pending_decisions.pop(aid, "timeout" if not ok else "reject")
        _pending_events.pop(aid, None)
        data = _load()
        for i in data.get("items") or []:
            if i.get("id") == aid and i.get("status") == "pending":
                i["status"] = "approved" if decision == "approve" else (
                    "timeout" if decision == "timeout" else "rejected"
                )
                i["resolved_at"] = _now()
                item = dict(i)
                break
        _save(data)
    _notify()
    return item


def resolve(approval_id: str, decision: str) -> bool:
    decision = "approve" if decision in ("approve", "approved", "yes") else "reject"
    with _lock:
        data = _load()
        found = False
        for i in data.get("items") or []:
            if i.get("id") == approval_id and i.get("status") == "pending":
                i["status"] = "approved" if decision == "approve" else "rejected"
                i["resolved_at"] = _now()
                found = True
                break
        if found:
            _save(data)
        ev = _pending_events.get(approval_id)
        if ev:
            _pending_decisions[approval_id] = decision
            ev.set()
    if found:
        _notify()
    return found


def approve(approval_id: str) -> bool:
    return resolve(approval_id, "approve")


def reject(approval_id: str) -> bool:
    return resolve(approval_id, "reject")


def approve_all_pending() -> int:
    n = 0
    for item in list_pending():
        if approve(item["id"]):
            n += 1
    return n
