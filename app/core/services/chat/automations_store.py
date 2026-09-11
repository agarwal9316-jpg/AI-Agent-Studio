"""Workspace Automations — schedule prompts, fire into linked chats (P1.3).

Ideas from Open WebUI automations (named prompt + recurrence + run→chat)
reimplemented cleanly for Studio CustomTkinter — no GPL blobs.

Separate from company ``scheduler_service`` / ``data/schedules.json`` (org agent
tasks). This module owns user Workspace automations under ``data/automations.json``.
"""

from __future__ import annotations

import re
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from app.paths import automations_path
from app.core.services.data.storage import _read_json, _write_json

SCHEDULE_KINDS = ("hourly", "daily", "weekday", "interval")
POLL_SECONDS = 15

# Injectable clock for tests (epoch seconds). None → time.time().
_clock: Callable[[], float] | None = None

_lock = threading.RLock()
_thread: threading.Thread | None = None
_running = False
_listeners: list[Callable[[str], None]] = []


def set_clock(fn: Callable[[], float] | None) -> None:
    """Override wall clock (tests). Pass None to restore real time."""
    global _clock
    _clock = fn


def _now_ts() -> float:
    if _clock is not None:
        return float(_clock())
    return time.time()


def _now_iso(ts: float | None = None) -> str:
    t = _now_ts() if ts is None else float(ts)
    return datetime.fromtimestamp(t, tz=timezone.utc).isoformat()


def _parse_iso(s: str) -> float | None:
    raw = (s or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except Exception:  # noqa: BLE001
        return None


def _normalize(item: dict[str, Any]) -> dict[str, Any]:
    kind = str(item.get("schedule_kind") or "daily").strip().lower()
    if kind not in SCHEDULE_KINDS:
        kind = "daily"
    try:
        interval = max(1, int(item.get("interval_minutes") or 60))
    except (TypeError, ValueError):
        interval = 60
    try:
        hour = int(item.get("hour") if item.get("hour") is not None else 9)
    except (TypeError, ValueError):
        hour = 9
    try:
        minute = int(item.get("minute") if item.get("minute") is not None else 0)
    except (TypeError, ValueError):
        minute = 0
    hour = max(0, min(23, hour))
    minute = max(0, min(59, minute))
    return {
        "id": str(item.get("id") or ""),
        "name": str(item.get("name") or "Untitled").strip() or "Untitled",
        "prompt": str(item.get("prompt") or ""),
        "schedule_kind": kind,
        "interval_minutes": interval,
        "hour": hour,
        "minute": minute,
        "enabled": bool(item.get("enabled", True)),
        "last_run": str(item.get("last_run") or ""),
        "next_run": str(item.get("next_run") or ""),
        "last_status": str(item.get("last_status") or ""),  # success | failed | ""
        "last_error": str(item.get("last_error") or ""),
        "last_chat_id": str(item.get("last_chat_id") or ""),
        "run_count": int(item.get("run_count") or 0),
        "created_at": str(item.get("created_at") or ""),
        "updated_at": str(item.get("updated_at") or ""),
    }


def load_automations() -> list[dict[str, Any]]:
    data = _read_json(automations_path(), {"items": []})
    if isinstance(data, dict):
        items = list(data.get("items") or [])
    elif isinstance(data, list):
        items = list(data)
    else:
        items = []
    out = [_normalize(i) for i in items if isinstance(i, dict) and i.get("id")]
    out.sort(key=lambda a: a.get("updated_at") or a.get("created_at") or "", reverse=True)
    return out


def save_automations(items: list[dict[str, Any]]) -> None:
    normed = [_normalize(i) for i in items if isinstance(i, dict) and i.get("id")]
    _write_json(
        automations_path(),
        {"items": normed, "updated_at": _now_iso()},
    )


def list_automations(*, query: str = "") -> list[dict[str, Any]]:
    items = load_automations()
    q = (query or "").strip().lower()
    if not q:
        return items
    words = [w for w in re.split(r"\s+", q) if w]
    out: list[dict[str, Any]] = []
    for a in items:
        hay = f"{a.get('name', '')}\n{a.get('prompt', '')}".lower()
        if all(w in hay for w in words):
            out.append(a)
    return out


def get_automation(aid: str) -> dict[str, Any] | None:
    aid = str(aid or "").strip()
    if not aid:
        return None
    for a in load_automations():
        if a.get("id") == aid:
            return a
    return None


def compute_next_run(
    *,
    schedule_kind: str,
    interval_minutes: int = 60,
    hour: int = 9,
    minute: int = 0,
    after_ts: float | None = None,
) -> str:
    """Next run ISO after ``after_ts`` (default now)."""
    kind = (schedule_kind or "daily").strip().lower()
    if kind not in SCHEDULE_KINDS:
        kind = "daily"
    base = float(after_ts) if after_ts is not None else _now_ts()
    # Work in UTC naive for arithmetic
    dt = datetime.fromtimestamp(base, tz=timezone.utc)

    if kind == "interval":
        mins = max(1, int(interval_minutes or 60))
        nxt = dt + timedelta(minutes=mins)
        return nxt.isoformat()

    if kind == "hourly":
        # Next clock hour boundary (or +1h if exactly on the hour and we just fired)
        nxt = dt.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        return nxt.isoformat()

    # daily / weekday — fire at hour:minute local-as-UTC (Studio uses UTC stamps)
    h = max(0, min(23, int(hour)))
    m = max(0, min(59, int(minute)))
    candidate = dt.replace(hour=h, minute=m, second=0, microsecond=0)
    if candidate <= dt:
        candidate = candidate + timedelta(days=1)

    if kind == "weekday":
        # Skip Sat(5)/Sun(6) — Python weekday(): Mon=0 … Sun=6
        while candidate.weekday() >= 5:
            candidate = candidate + timedelta(days=1)
    return candidate.isoformat()


def create_automation(
    *,
    name: str = "New automation",
    prompt: str = "",
    schedule_kind: str = "daily",
    interval_minutes: int = 60,
    hour: int = 9,
    minute: int = 0,
    enabled: bool = True,
) -> dict[str, Any]:
    now = _now_iso()
    kind = (schedule_kind or "daily").strip().lower()
    if kind not in SCHEDULE_KINDS:
        kind = "daily"
    item = _normalize(
        {
            "id": str(uuid.uuid4()),
            "name": (name or "New automation").strip() or "New automation",
            "prompt": prompt or "",
            "schedule_kind": kind,
            "interval_minutes": interval_minutes,
            "hour": hour,
            "minute": minute,
            "enabled": bool(enabled),
            "last_run": "",
            "next_run": compute_next_run(
                schedule_kind=kind,
                interval_minutes=interval_minutes,
                hour=hour,
                minute=minute,
            ),
            "last_status": "",
            "last_error": "",
            "last_chat_id": "",
            "run_count": 0,
            "created_at": now,
            "updated_at": now,
        }
    )
    with _lock:
        items = load_automations()
        items.insert(0, item)
        save_automations(items)
    if item["enabled"]:
        start()
    return item


def update_automation(aid: str, **fields: Any) -> dict[str, Any] | None:
    aid = str(aid or "").strip()
    with _lock:
        items = load_automations()
        target = None
        for i, a in enumerate(items):
            if a.get("id") == aid:
                target = a
                idx = i
                break
        if target is None:
            return None
        allowed = {
            "name",
            "prompt",
            "schedule_kind",
            "interval_minutes",
            "hour",
            "minute",
            "enabled",
        }
        changed_sched = False
        for k, v in fields.items():
            if k not in allowed:
                continue
            if k == "schedule_kind":
                v = str(v or "daily").strip().lower()
                if v not in SCHEDULE_KINDS:
                    v = "daily"
                if v != target.get("schedule_kind"):
                    changed_sched = True
            if k in ("interval_minutes", "hour", "minute") and v != target.get(k):
                changed_sched = True
            target[k] = v
        target["updated_at"] = _now_iso()
        if changed_sched or "enabled" in fields:
            target["next_run"] = compute_next_run(
                schedule_kind=str(target.get("schedule_kind") or "daily"),
                interval_minutes=int(target.get("interval_minutes") or 60),
                hour=int(target.get("hour") if target.get("hour") is not None else 9),
                minute=int(target.get("minute") or 0),
            )
        items[idx] = _normalize(target)
        save_automations(items)
        out = items[idx]
    if out.get("enabled"):
        start()
    return out


def set_enabled(aid: str, enabled: bool) -> dict[str, Any] | None:
    return update_automation(aid, enabled=bool(enabled))


def delete_automation(aid: str) -> bool:
    aid = str(aid or "").strip()
    with _lock:
        items = load_automations()
        nxt = [a for a in items if a.get("id") != aid]
        if len(nxt) == len(items):
            return False
        save_automations(nxt)
    return True


def is_due(item: dict[str, Any], now_ts: float | None = None) -> bool:
    if not item.get("enabled"):
        return False
    ts = _now_ts() if now_ts is None else float(now_ts)
    nxt = _parse_iso(str(item.get("next_run") or ""))
    if nxt is None:
        # Never scheduled → due immediately when enabled
        return True
    return ts >= nxt


def _create_result_chat(title: str) -> dict[str, Any]:
    """Create a chat for the run without stealing the user's active session."""
    from app.core.services.chat import chat_store

    prev = ""
    try:
        prev = chat_store.get_active_chat_id() or ""
    except Exception:  # noqa: BLE001
        prev = ""
    c = chat_store.new_chat(title)
    if prev and prev != c.get("id"):
        try:
            chat_store.set_active_chat_id(prev)
        except Exception:  # noqa: BLE001
            pass
    return c


def _resolve_llm() -> dict[str, Any]:
    try:
        from app.core.services.llm.providers import resolve_active_llm
        from app.core.services.data.storage import load_config

        active = resolve_active_llm()
        cfg = load_config()
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "note": f"LLM unavailable: {e}",
            "api_key": "",
            "model": "gpt-4o-mini",
            "base_url": "https://api.openai.com/v1",
        }
    return {
        "ok": True,
        "api_key": (active.get("api_key") or cfg.get("api_key") or "").strip(),
        "model": (active.get("model") or cfg.get("model") or "gpt-4o-mini").strip(),
        "base_url": (
            active.get("base_url") or cfg.get("api_base_url") or "https://api.openai.com/v1"
        ).strip(),
    }


def run_automation(
    aid: str,
    *,
    force: bool = False,
    chat_completion_fn: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Execute one automation: open/create a result chat, send prompt, link chat id.

    Soft-degrades when no API key — marks run failed with a clear error, does not raise.
    """
    with _lock:
        item = get_automation(aid)
        if item is None:
            return {"ok": False, "error": "Automation not found", "automation": None}
        if not force and not item.get("enabled"):
            return {
                "ok": False,
                "error": "Automation is disabled",
                "automation": item,
            }

    name = item.get("name") or "Automation"
    prompt = (item.get("prompt") or "").strip()
    chat_id = ""
    status = "failed"
    error = ""
    reply_text = ""

    try:
        chat = _create_result_chat(f"[auto] {name}")
        chat_id = str(chat.get("id") or "")
    except Exception as e:  # noqa: BLE001
        error = f"Could not create result chat: {e}"
        chat = None

    now_iso = _now_iso()
    if chat is not None and chat_id:
        # Seed user message
        msgs = list(chat.get("messages") or [])
        msgs.append(
            {
                "role": "user",
                "content": prompt or f"(empty prompt for automation '{name}')",
                "at": now_iso,
            }
        )

        resolved = _resolve_llm()
        api_key = str(resolved.get("api_key") or "")
        model = str(resolved.get("model") or "gpt-4o-mini")
        base_url = str(resolved.get("base_url") or "https://api.openai.com/v1")

        if not prompt:
            error = "Empty prompt — nothing to send"
            msgs.append(
                {
                    "role": "assistant",
                    "content": f"[Automation failed] {error}",
                    "at": _now_iso(),
                }
            )
        elif not api_key:
            error = (
                "No API key — automation run soft-degraded "
                "(add a key in Settings → Providers)"
            )
            msgs.append(
                {
                    "role": "assistant",
                    "content": f"[Automation failed] {error}",
                    "at": _now_iso(),
                }
            )
        else:
            fn = chat_completion_fn
            if fn is None:
                from app.core.services.llm.llm import chat_completion as fn  # type: ignore

            try:
                out = fn(
                    api_key=api_key,
                    messages=[{"role": "user", "content": prompt}],
                    model=model,
                    base_url=base_url,
                    timeout=120.0,
                    temperature=0.6,
                    max_tokens=4096,
                )
                if isinstance(out, tuple):
                    reply_text = str(out[0] or "").strip()
                else:
                    reply_text = str(out or "").strip()
                if not reply_text:
                    error = "Empty model reply (soft-degrade)"
                    msgs.append(
                        {
                            "role": "assistant",
                            "content": f"[Automation failed] {error}",
                            "at": _now_iso(),
                        }
                    )
                else:
                    status = "success"
                    error = ""
                    msgs.append(
                        {
                            "role": "assistant",
                            "content": reply_text,
                            "at": _now_iso(),
                        }
                    )
            except Exception as e:  # noqa: BLE001
                error = f"Model reply failed (soft-degrade): {e}"
                msgs.append(
                    {
                        "role": "assistant",
                        "content": f"[Automation failed] {error}",
                        "at": _now_iso(),
                    }
                )

        chat["messages"] = msgs
        try:
            from app.core.services.chat import chat_store

            chat_store.save_chat(chat)
        except Exception as e:  # noqa: BLE001
            if not error:
                error = f"Could not save result chat: {e}"
            status = "failed"

    # Persist automation bookkeeping
    with _lock:
        items = load_automations()
        updated = None
        for i, a in enumerate(items):
            if a.get("id") == aid:
                a["last_run"] = now_iso
                a["last_status"] = status
                a["last_error"] = error
                a["last_chat_id"] = chat_id
                a["run_count"] = int(a.get("run_count") or 0) + 1
                a["updated_at"] = _now_iso()
                a["next_run"] = compute_next_run(
                    schedule_kind=str(a.get("schedule_kind") or "daily"),
                    interval_minutes=int(a.get("interval_minutes") or 60),
                    hour=int(a.get("hour") if a.get("hour") is not None else 9),
                    minute=int(a.get("minute") or 0),
                    after_ts=_now_ts(),
                )
                items[i] = _normalize(a)
                updated = items[i]
                break
        if updated is not None:
            save_automations(items)

    _emit(
        f"Automation '{name}' → {status}"
        + (f" chat={chat_id[:8]}" if chat_id else "")
        + (f" err={error[:80]}" if error else "")
    )
    return {
        "ok": status == "success",
        "status": status,
        "error": error,
        "chat_id": chat_id,
        "reply": reply_text,
        "automation": updated or get_automation(aid),
    }


def tick(*, force_all_due: bool = False) -> int:
    """Fire due automations once. Returns number attempted."""
    now = _now_ts()
    with _lock:
        items = load_automations()
        due_ids = [
            str(a["id"])
            for a in items
            if a.get("enabled") and (force_all_due or is_due(a, now))
        ]
    n = 0
    for aid in due_ids:
        try:
            run_automation(aid, force=True)
            n += 1
        except Exception as e:  # noqa: BLE001
            _emit(f"Automation tick error {aid[:8]}: {e}")
    return n


def _loop() -> None:
    global _running
    while _running:
        try:
            tick()
        except Exception as e:  # noqa: BLE001
            _emit(f"automations ticker error: {e}")
        # Sleep in small slices so stop() is responsive
        for _ in range(POLL_SECONDS):
            if not _running:
                break
            time.sleep(1)


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

        alog(msg, source="automations")
    except Exception:  # noqa: BLE001
        pass


def start() -> None:
    global _running, _thread
    with _lock:
        if _running:
            return
        _running = True
        _thread = threading.Thread(target=_loop, daemon=True, name="studio-automations")
        _thread.start()


def stop() -> None:
    global _running
    _running = False


def is_running() -> bool:
    return _running


def schedule_label(item: dict[str, Any]) -> str:
    """Human-readable schedule summary for UI lists."""
    kind = str(item.get("schedule_kind") or "daily")
    h = int(item.get("hour") if item.get("hour") is not None else 9)
    m = int(item.get("minute") or 0)
    hm = f"{h:02d}:{m:02d}"
    if kind == "hourly":
        return "Every hour"
    if kind == "daily":
        return f"Daily at {hm} UTC"
    if kind == "weekday":
        return f"Weekdays at {hm} UTC"
    if kind == "interval":
        mins = int(item.get("interval_minutes") or 60)
        if mins == 60:
            return "Every 60 minutes"
        if mins < 60:
            return f"Every {mins} min"
        hours = mins // 60
        rem = mins % 60
        if rem:
            return f"Every {hours}h {rem}m"
        return f"Every {hours}h"
    return kind
