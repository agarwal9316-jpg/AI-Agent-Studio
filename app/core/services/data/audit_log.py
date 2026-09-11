"""Persistent audit log of tool calls — exportable as JSON/CSV (PENDING #16).

Soft-degrades: every public API swallows I/O / serialization errors so chat
never breaks if the audit write fails. Secrets are redacted / truncated.
"""

from __future__ import annotations

import csv
import io
import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.paths import data_dir
from app.core.services.data.storage import _read_json, _write_json

_lock = threading.Lock()
_MAX_ENTRIES = 5000
_ARGS_MAX = 800
_RESULT_MAX = 1200
_SECRET_KEYS = {
    "api_key",
    "apikey",
    "token",
    "password",
    "secret",
    "authorization",
    "auth",
    "bearer",
    "access_token",
    "refresh_token",
    "private_key",
    "key",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def audit_path() -> Path:
    return data_dir() / "tool_audit.json"


def exports_dir() -> Path:
    d = data_dir() / "exports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _empty() -> dict[str, Any]:
    return {"entries": [], "updated_at": _now(), "version": 1}


def _load() -> dict[str, Any]:
    try:
        data = _read_json(audit_path(), None)
        if isinstance(data, dict) and isinstance(data.get("entries"), list):
            return data
    except Exception:  # noqa: BLE001
        pass
    return _empty()


def _save(data: dict[str, Any]) -> None:
    data["updated_at"] = _now()
    _write_json(audit_path(), data)


def _truncate(text: str, limit: int) -> str:
    s = str(text or "")
    if len(s) <= limit:
        return s
    return s[: max(0, limit - 1)] + "\u2026"


def _redact_text(text: str) -> str:
    try:
        from app.core.services.misc.redact import redact_text

        return redact_text(text)
    except Exception:  # noqa: BLE001
        return text


def summarize_args(args: Any, *, limit: int = _ARGS_MAX) -> str:
    """Truncate + redact tool args for safe persistence."""
    try:
        if args is None:
            return ""
        if isinstance(args, str):
            return _truncate(_redact_text(args), limit)
        if isinstance(args, dict):
            safe: dict[str, Any] = {}
            for k, v in args.items():
                key = str(k)
                low = key.lower()
                if low in _SECRET_KEYS or any(
                    s in low for s in ("password", "secret", "token", "api_key", "apikey")
                ):
                    safe[key] = "***REDACTED***"
                elif isinstance(v, (dict, list)):
                    try:
                        safe[key] = json.loads(
                            _truncate(_redact_text(json.dumps(v, ensure_ascii=False, default=str)), 200)
                        )
                    except Exception:  # noqa: BLE001
                        safe[key] = _truncate(_redact_text(str(v)), 200)
                else:
                    safe[key] = _truncate(_redact_text(str(v)), 400)
            blob = json.dumps(safe, ensure_ascii=False, default=str)
            return _truncate(blob, limit)
        if isinstance(args, (list, tuple)):
            blob = json.dumps(list(args)[:20], ensure_ascii=False, default=str)
            return _truncate(_redact_text(blob), limit)
        return _truncate(_redact_text(str(args)), limit)
    except Exception:  # noqa: BLE001
        try:
            return _truncate(str(args), limit)
        except Exception:  # noqa: BLE001
            return ""


def summarize_result(result: Any, *, limit: int = _RESULT_MAX) -> str:
    try:
        if result is None:
            return ""
        if isinstance(result, dict):
            slim: dict[str, Any] = {}
            for k in ("ok", "error", "denied", "exit_code", "status", "path", "count", "tool"):
                if k in result:
                    slim[k] = result[k]
            for k in ("stdout", "stderr", "output", "content", "text", "message"):
                if k in result and result[k] is not None:
                    slim[k] = _truncate(_redact_text(str(result[k])), 240)
                    break
            if len(slim) < 2:
                blob = json.dumps(result, ensure_ascii=False, default=str)
                return _truncate(_redact_text(blob), limit)
            return _truncate(_redact_text(json.dumps(slim, ensure_ascii=False, default=str)), limit)
        return _truncate(_redact_text(str(result)), limit)
    except Exception:  # noqa: BLE001
        try:
            return _truncate(str(result), min(limit, 200))
        except Exception:  # noqa: BLE001
            return ""


def _status_from_result(result: Any, status: str | None) -> str:
    if status:
        return str(status)
    if isinstance(result, dict):
        if result.get("denied"):
            return "denied"
        if result.get("ok") is False:
            return "error"
        if result.get("ok") is True:
            return "ok"
        if result.get("error"):
            return "error"
    return "ok" if result is not None else "unknown"


def record(
    tool: str,
    *,
    args: Any = None,
    args_summary: str | None = None,
    result: Any = None,
    result_summary: str | None = None,
    status: str | None = None,
    error: str | None = None,
    chat_id: str | None = None,
    session_id: str | None = None,
    source: str = "chat",
    duration_ms: int | float | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Append one tool-call audit entry. Never raises."""
    try:
        name = (tool or "").strip() or "?"
        entry: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "at": _now(),
            "tool": name,
            "args_summary": args_summary
            if args_summary is not None
            else summarize_args(args),
            "result_summary": result_summary
            if result_summary is not None
            else summarize_result(result),
            "status": _status_from_result(result, status),
            "error": _truncate(_redact_text(error or ""), 500),
            "chat_id": str(chat_id or "")[:120],
            "session_id": str(session_id or "")[:120],
            "source": str(source or "chat")[:64],
            "duration_ms": int(duration_ms) if duration_ms is not None else None,
            "meta": meta or {},
        }
        if not entry["error"] and isinstance(result, dict) and result.get("error"):
            entry["error"] = _truncate(_redact_text(str(result.get("error"))), 500)

        with _lock:
            data = _load()
            entries = list(data.get("entries") or [])
            entries.append(entry)
            if len(entries) > _MAX_ENTRIES:
                entries = entries[-_MAX_ENTRIES:]
            data["entries"] = entries
            _save(data)
        return entry
    except Exception:  # noqa: BLE001
        return None


def list_entries(
    *,
    limit: int = 500,
    chat_id: str | None = None,
    tool: str | None = None,
) -> list[dict[str, Any]]:
    try:
        with _lock:
            entries = list((_load().get("entries") or []))
        if chat_id:
            cid = str(chat_id)
            entries = [e for e in entries if str(e.get("chat_id") or "") == cid]
        if tool:
            t = tool.lower().strip()
            entries = [e for e in entries if str(e.get("tool") or "").lower() == t]
        if limit and limit > 0:
            entries = entries[-limit:]
        return entries
    except Exception:  # noqa: BLE001
        return []


def count() -> int:
    try:
        with _lock:
            return len((_load().get("entries") or []))
    except Exception:  # noqa: BLE001
        return 0


def clear() -> int:
    """Clear all audit entries. Returns previous count (0 on failure)."""
    try:
        with _lock:
            data = _load()
            n = len(data.get("entries") or [])
            data["entries"] = []
            _save(data)
        return n
    except Exception:  # noqa: BLE001
        return 0


def rotate(*, keep: int = 1000) -> int:
    """Keep only the newest `keep` entries. Returns number removed."""
    try:
        keep = max(0, int(keep))
        with _lock:
            data = _load()
            entries = list(data.get("entries") or [])
            if len(entries) <= keep:
                return 0
            removed = len(entries) - keep
            data["entries"] = entries[-keep:] if keep else []
            _save(data)
        return removed
    except Exception:  # noqa: BLE001
        return 0


def export_json(path: Path | None = None) -> Path:
    exports = exports_dir()
    if path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = exports / f"tool_audit_{ts}.json"
    path = Path(path)
    with _lock:
        data = _load()
    payload = {
        "exported_at": _now(),
        "count": len(data.get("entries") or []),
        "entries": data.get("entries") or [],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


_CSV_FIELDS = [
    "id",
    "at",
    "tool",
    "status",
    "args_summary",
    "result_summary",
    "error",
    "chat_id",
    "session_id",
    "source",
    "duration_ms",
]


def export_csv(path: Path | None = None) -> Path:
    exports = exports_dir()
    if path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = exports / f"tool_audit_{ts}.csv"
    path = Path(path)
    with _lock:
        entries = list((_load().get("entries") or []))
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for e in entries:
        row = {k: e.get(k, "") if e.get(k) is not None else "" for k in _CSV_FIELDS}
        writer.writerow(row)
    path.write_text(buf.getvalue(), encoding="utf-8", newline="")
    return path


def status_summary() -> dict[str, Any]:
    try:
        with _lock:
            data = _load()
            entries = data.get("entries") or []
            n = len(entries)
            last = entries[-1] if entries else None
        return {
            "count": n,
            "path": str(audit_path()),
            "updated_at": data.get("updated_at") if isinstance(data, dict) else "",
            "last_tool": (last or {}).get("tool") if last else "",
            "last_at": (last or {}).get("at") if last else "",
        }
    except Exception:  # noqa: BLE001
        return {
            "count": 0,
            "path": str(audit_path()),
            "updated_at": "",
            "last_tool": "",
            "last_at": "",
        }
