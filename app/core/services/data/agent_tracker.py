"""
Track multi-agent runs: which agent is active, inputs, outputs.
Persisted + live listeners for the UI.
"""

from __future__ import annotations

import threading
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable

from app.paths import data_dir
from app.core.services.data.storage import _read_json, _write_json

_lock = threading.Lock()
_listeners: list[Callable[[], None]] = []
_live: deque[dict[str, Any]] = deque(maxlen=200)
_active: dict[str, Any] | None = None
# Recent agent steps: which agent did what (tools, thinking, finish)
_steps: deque[dict[str, Any]] = deque(maxlen=400)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def tracker_path():
    return data_dir() / "agent_runs.json"


def _load() -> dict[str, Any]:
    data = _read_json(tracker_path(), None)
    if isinstance(data, dict) and "runs" in data:
        return data
    return {"runs": [], "updated_at": _now()}


def _save(data: dict[str, Any]) -> None:
    data["updated_at"] = _now()
    _write_json(tracker_path(), data)


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


def get_active() -> dict[str, Any] | None:
    with _lock:
        return dict(_active) if _active else None


def list_recent(limit: int = 50) -> list[dict[str, Any]]:
    with _lock:
        live = list(_live)[-limit:]
    data = _load()
    # merge persisted + live unique by id
    by_id = {r["id"]: r for r in (data.get("runs") or []) if r.get("id")}
    for r in live:
        by_id[r["id"]] = r
    runs = sorted(by_id.values(), key=lambda r: r.get("started_at") or "", reverse=True)
    return runs[:limit]


def start_run(
    *,
    agent_name: str,
    agent_role: str = "",
    agent_id: str = "",
    task_title: str = "",
    task_id: str = "",
    goal_id: str = "",
    model: str = "",
    input_text: str = "",
    source: str = "company",
) -> str:
    rid = str(uuid.uuid4())
    run = {
        "id": rid,
        "status": "running",
        "agent_name": agent_name,
        "agent_role": agent_role,
        "agent_id": agent_id,
        "task_title": task_title,
        "task_id": task_id,
        "goal_id": goal_id,
        "model": model,
        "input": input_text[:8000],
        "output": "",
        "source": source,
        "started_at": _now(),
        "finished_at": "",
        "error": "",
        "actions": [],
    }
    global _active
    with _lock:
        _active = run
        _live.append(run)
    data = _load()
    data.setdefault("runs", []).insert(0, run)
    data["runs"] = data["runs"][:300]
    _save(data)
    try:
        from app.core.services.data.activity_log import log as alog

        alog(
            f"ACTIVE AGENT: {agent_name} ({agent_role}) model={model} task={task_title}",
            source="agent",
        )
    except Exception:  # noqa: BLE001
        pass
    _notify()
    return rid


def finish_run(run_id: str, *, output: str = "", error: str = "", status: str = "done") -> None:
    global _active
    with _lock:
        if _active and _active.get("id") == run_id:
            _active["status"] = status
            _active["output"] = (output or "")[:12000]
            _active["error"] = error or ""
            _active["finished_at"] = _now()
            finished = dict(_active)
            _active = None
        else:
            finished = None
            for r in _live:
                if r.get("id") == run_id:
                    r["status"] = status
                    r["output"] = (output or "")[:12000]
                    r["error"] = error or ""
                    r["finished_at"] = _now()
                    finished = dict(r)
                    break

    data = _load()
    for r in data.get("runs") or []:
        if r.get("id") == run_id:
            r["status"] = status
            r["output"] = (output or "")[:12000]
            r["error"] = error or ""
            r["finished_at"] = _now()
            break
    _save(data)
    try:
        from app.core.services.data.activity_log import log as alog

        name = (finished or {}).get("agent_name") or "?"
        alog(f"AGENT FINISHED: {name} status={status}", source="agent")
    except Exception:  # noqa: BLE001
        pass
    _notify()


def abandon_stale_runs(*, max_age_sec: float = 600.0) -> int:
    """
    Mark zombie status=running runs as failed.
    max_age_sec=0 → abandon all running (used when user force-unlocks chat).
    Returns count abandoned.
    """
    from datetime import datetime, timezone

    global _active
    now = datetime.now(timezone.utc)
    n = 0
    with _lock:
        if _active and _active.get("status") == "running":
            _active["status"] = "failed"
            _active["error"] = _active.get("error") or "abandoned (stuck busy)"
            _active["finished_at"] = _now()
            _active = None
            n += 1
        for r in _live:
            if r.get("status") == "running":
                r["status"] = "failed"
                r["error"] = r.get("error") or "abandoned (stuck busy)"
                r["finished_at"] = _now()
                n += 1

    data = _load()
    changed = False
    for r in data.get("runs") or []:
        if r.get("status") != "running":
            continue
        age_ok = True
        if max_age_sec and max_age_sec > 0:
            try:
                started = str(r.get("started_at") or "")
                if started:
                    ts = datetime.fromisoformat(started.replace("Z", "+00:00"))
                    age = (now - ts).total_seconds()
                    age_ok = age >= float(max_age_sec)
            except Exception:  # noqa: BLE001
                age_ok = True
        if not age_ok:
            continue
        r["status"] = "failed"
        r["error"] = r.get("error") or "abandoned (stuck / app restart)"
        r["finished_at"] = _now()
        n += 1
        changed = True
    if changed:
        _save(data)
        _notify()
    return n


_last_step_notify = 0.0


def log_step(agent_name: str, action: str, *, detail: str = "") -> None:
    """Record a fine-grained step so UI can show which agent did what."""
    import time as _time

    global _last_step_notify
    step = {
        "at": _now(),
        "agent_name": agent_name or "?",
        "action": (action or "")[:500],
        "detail": (detail or "")[:1000],
    }
    with _lock:
        _steps.append(step)
        if _active:
            acts = list(_active.get("actions") or [])
            acts.append(step)
            _active["actions"] = acts[-80:]
            # also mirror on live copy
            for r in _live:
                if r.get("id") == _active.get("id"):
                    r["actions"] = list(_active["actions"])
                    break
    # Throttle UI listeners — every thinking line used to rebuild the side panel
    now = _time.monotonic()
    if now - _last_step_notify >= 0.35:
        _last_step_notify = now
        _notify()


def list_steps(limit: int = 60) -> list[dict[str, Any]]:
    with _lock:
        return list(_steps)[-limit:]


def format_who_did_what(limit: int = 40) -> str:
    lines = ["WHICH AGENT DID WHAT", ""]
    active = get_active()
    if active:
        lines.append(f"▶ NOW: {active.get('agent_name')} — {active.get('task_title')}")
        for a in (active.get("actions") or [])[-12:]:
            lines.append(f"   · {a.get('action')}")
        lines.append("")
    lines.append("=== Timeline ===")
    for s in list_steps(limit):
        lines.append(f"[{str(s.get('at') or '')[11:19]}] {s.get('agent_name')}: {s.get('action')}")
    if len(lines) <= 4:
        lines.append("(no agent activity yet)")
    return "\n".join(lines)


def search_runs(query: str, limit: int = 40) -> list[dict[str, Any]]:
    q = (query or "").lower().strip()
    if not q:
        return list_recent(limit)
    out = []
    for r in list_recent(200):
        blob = " ".join(
            [
                str(r.get("agent_name") or ""),
                str(r.get("task_title") or ""),
                str(r.get("input") or ""),
                str(r.get("output") or ""),
                str(r.get("model") or ""),
            ]
        ).lower()
        if q in blob:
            out.append(r)
        if len(out) >= limit:
            break
    return out
