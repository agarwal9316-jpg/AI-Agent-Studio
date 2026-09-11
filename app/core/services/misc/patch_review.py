"""
Pending self-improve patches for user review (diff UI) before apply.
Safer than auto-writing source.
"""

from __future__ import annotations

import difflib
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.paths import data_dir
from app.core.services.data.storage import _read_json, _write_json


def _get_self_improve():
    """Lazy import to break circular dependency."""
    from app.services import self_improve
    return self_improve


_lock = threading.Lock()
_listeners: list[Callable[[], None]] = []


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def queue_path():
    return data_dir() / "pending_patches.json"


def _load() -> list[dict[str, Any]]:
    data = _read_json(queue_path(), {"items": []})
    if isinstance(data, dict):
        return list(data.get("items") or [])
    return []


def _save(items: list[dict[str, Any]]) -> None:
    _write_json(queue_path(), {"items": items, "updated_at": _now()})


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


def list_pending() -> list[dict[str, Any]]:
    return [i for i in _load() if i.get("status") == "pending"]


def list_all(limit: int = 50) -> list[dict[str, Any]]:
    return _load()[:limit]


def queue_patch(
    *,
    path: str,
    content: str,
    mode: str = "write",
    note: str = "",
) -> dict[str, Any]:
    abs_p, rel_or_err = _get_self_improve().resolve_target(path)
    if abs_p is None:
        return {"ok": False, "error": rel_or_err}
    old = ""
    if abs_p.is_file():
        try:
            old = abs_p.read_text(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            old = ""
    new = content or ""
    if mode == "append" and old:
        new = old + content
    diff = "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"a/{rel_or_err}",
            tofile=f"b/{rel_or_err}",
            n=3,
        )
    )
    item = {
        "id": str(uuid.uuid4()),
        "status": "pending",
        "path": rel_or_err,
        "mode": mode,
        "note": note,
        "old": old,
        "new": new,
        "diff": diff or "(new file or no textual diff)",
        "created_at": _now(),
        "resolved_at": "",
    }
    items = _load()
    items.insert(0, item)
    _save(items[:200])
    _notify()
    try:
        from app.core.services.data.activity_log import log as alog

        alog(f"PATCH PENDING: {rel_or_err} — {note[:60]}", source="patch")
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "id": item["id"], "path": rel_or_err, "diff_lines": diff.count("\n")}


def apply_patch(pid: str) -> dict[str, Any]:
    items = _load()
    for i in items:
        if i.get("id") == pid and i.get("status") == "pending":
            res = _get_self_improve().apply_patch(
                path=i["path"],
                content=i.get("new") or "",
                mode="write",
                note=i.get("note") or "approved patch",
                create_backup_first=True,
            )
            i["status"] = "applied" if res.get("ok") else "failed"
            i["result"] = res
            i["resolved_at"] = _now()
            _save(items)
            _notify()
            return res
    return {"ok": False, "error": "Patch not found or not pending"}


def reject_patch(pid: str) -> bool:
    items = _load()
    for i in items:
        if i.get("id") == pid and i.get("status") == "pending":
            i["status"] = "rejected"
            i["resolved_at"] = _now()
            _save(items)
            _notify()
            return True
    return False


def tool_instructions() -> str:
    return """
## Safe code changes (patch review)

Prefer proposing patches for user approval instead of silent edits:

<<<PATCH_REVIEW>>>
path: app/services/example.py
note: what changed
---
full new file content
<<<END_PATCH_REVIEW>>>

User reviews diff in the **Patches** page, then Apply or Reject.
For emergency direct edit (still backed up): use SELF_IMPROVE.
""".strip()


PATCH_RE = __import__("re").compile(
    r"<<<PATCH_REVIEW>>>\s*(.*?)\s*<<<END_PATCH_REVIEW>>>",
    __import__("re").DOTALL | __import__("re").IGNORECASE,
)


def extract_patch_blocks(text: str) -> list[dict[str, str]]:
    out = []
    for m in PATCH_RE.finditer(text or ""):
        body = (m.group(1) or "").strip()
        if "---" in body:
            header, content = body.split("---", 1)
        else:
            lines = body.splitlines()
            header, content = "\n".join(lines[:4]), "\n".join(lines[4:])
        meta = {"path": "", "note": "", "mode": "write", "content": content.lstrip("\n")}
        for line in header.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                k, v = k.strip().lower(), v.strip()
                if k in ("path", "file"):
                    meta["path"] = v
                elif k == "note":
                    meta["note"] = v
                elif k == "mode":
                    meta["mode"] = v
        if meta["path"]:
            out.append(meta)
    return out
