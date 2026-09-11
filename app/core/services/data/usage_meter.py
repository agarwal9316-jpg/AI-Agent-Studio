"""Token / cost usage meter per provider, model, and agent."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

from app.paths import data_dir
from app.core.services.data.storage import _read_json, _write_json

_lock = threading.Lock()
# Per-process totals so the status bar is not a scary lifetime dump
_session_totals: dict[str, float] = {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
    "est_cost_usd": 0.0,
}

# Rough USD per 1M tokens (prompt, completion) — estimates only
_MODEL_RATES: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
    "gpt-4.1": (2.0, 8.0),
    "gpt-4.1-mini": (0.4, 1.6),
    "o1": (15.0, 60.0),
    "o3": (10.0, 40.0),
    "claude-3.5": (3.0, 15.0),
    "claude-sonnet": (3.0, 15.0),
    "claude-opus": (15.0, 75.0),
    "gemini": (0.5, 1.5),
    "llama": (0.2, 0.2),
    "deepseek": (0.14, 0.28),
    "grok-3": (3.0, 15.0),
    "grok-4": (3.0, 15.0),
    "grok": (3.0, 15.0),
    "default": (1.0, 3.0),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def usage_path():
    return data_dir() / "usage.json"


def _load() -> dict[str, Any]:
    data = _read_json(usage_path(), None)
    if isinstance(data, dict) and "events" in data:
        return data
    return {
        "events": [],
        "totals": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "est_cost_usd": 0.0,
        },
        "by_model": {},
        "by_agent": {},
        "by_provider": {},
        "updated_at": _now(),
    }


def _save(data: dict[str, Any]) -> None:
    data["updated_at"] = _now()
    _write_json(usage_path(), data)


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    m = (model or "").lower()
    rate = _MODEL_RATES["default"]
    for key, r in _MODEL_RATES.items():
        if key != "default" and key in m:
            rate = r
            break
    return (prompt_tokens / 1_000_000.0) * rate[0] + (completion_tokens / 1_000_000.0) * rate[1]


def estimate_tokens_from_text(text: str) -> int:
    """Rough token estimate (~4 chars/token)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def record_usage(
    *,
    model: str = "",
    provider: str = "",
    agent: str = "",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int | None = None,
    source: str = "chat",
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if prompt_tokens < 0:
        prompt_tokens = 0
    if completion_tokens < 0:
        completion_tokens = 0
    if total_tokens is None:
        total_tokens = prompt_tokens + completion_tokens
    cost = estimate_cost(model, prompt_tokens, completion_tokens)
    event = {
        "at": _now(),
        "model": model or "?",
        "provider": provider or "?",
        "agent": agent or "Chat",
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "est_cost_usd": round(cost, 6),
        "source": source,
        "meta": meta or {},
    }
    with _lock:
        data = _load()
        data.setdefault("events", []).insert(0, event)
        data["events"] = data["events"][:2000]
        t = data.setdefault(
            "totals",
            {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "est_cost_usd": 0.0,
            },
        )
        t["prompt_tokens"] = int(t.get("prompt_tokens") or 0) + prompt_tokens
        t["completion_tokens"] = int(t.get("completion_tokens") or 0) + completion_tokens
        t["total_tokens"] = int(t.get("total_tokens") or 0) + total_tokens
        t["est_cost_usd"] = round(float(t.get("est_cost_usd") or 0) + cost, 6)
        _session_totals["prompt_tokens"] += prompt_tokens
        _session_totals["completion_tokens"] += completion_tokens
        _session_totals["total_tokens"] += total_tokens
        _session_totals["est_cost_usd"] = round(
            float(_session_totals.get("est_cost_usd") or 0) + cost, 6
        )

        for bucket_name, key in (
            ("by_model", model or "?"),
            ("by_agent", agent or "Chat"),
            ("by_provider", provider or "?"),
        ):
            bucket = data.setdefault(bucket_name, {})
            b = bucket.setdefault(
                key,
                {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "est_cost_usd": 0.0},
            )
            b["prompt_tokens"] = int(b.get("prompt_tokens") or 0) + prompt_tokens
            b["completion_tokens"] = int(b.get("completion_tokens") or 0) + completion_tokens
            b["total_tokens"] = int(b.get("total_tokens") or 0) + total_tokens
            b["est_cost_usd"] = round(float(b.get("est_cost_usd") or 0) + cost, 6)

        _save(data)
    return event


def get_summary() -> dict[str, Any]:
    with _lock:
        return _load()


def format_status_line() -> str:
    sess = int(_session_totals.get("total_tokens") or 0)
    scost = float(_session_totals.get("est_cost_usd") or 0)
    s = get_summary().get("totals") or {}
    life = int(s.get("total_tokens") or 0)
    if sess:
        return f"This session {sess:,} tok · ${scost:.2f}  ·  all-time {life:,}"
    return f"This session 0 tok  ·  all-time {life:,}"


def reset_usage() -> None:
    with _lock:
        _save(
            {
                "events": [],
                "totals": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "est_cost_usd": 0.0,
                },
                "by_model": {},
                "by_agent": {},
                "by_provider": {},
            }
        )
