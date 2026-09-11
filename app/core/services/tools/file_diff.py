"""Unified diffs for agent file edits (Task #8) — pure helpers + session log."""

from __future__ import annotations

import difflib
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.paths import data_dir
from app.core.services.data.storage import _read_json, _write_json

_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_path() -> Path:
    return data_dir() / "file_edit_log.json"


def unified_diff(
    old: str,
    new: str,
    *,
    path: str = "file",
    context: int = 3,
    max_lines: int = 800,
) -> str:
    """Build a unified diff string (empty if no change)."""
    a = (old or "").splitlines(keepends=True)
    b = (new or "").splitlines(keepends=True)
    name = Path(path).name if path else "file"
    # Ensure trailing newline handling for empty files
    if a and not a[-1].endswith("\n"):
        a[-1] = a[-1] + "\n"
    if b and not b[-1].endswith("\n"):
        b[-1] = b[-1] + "\n"
    lines = list(
        difflib.unified_diff(
            a,
            b,
            fromfile=f"a/{name}",
            tofile=f"b/{name}",
            n=max(0, int(context)),
            lineterm="\n",
        )
    )
    if not lines:
        return ""
    if len(lines) > max_lines:
        head = lines[: max_lines - 2]
        head.append(f"... ({len(lines) - len(head)} more diff lines truncated)\n")
        return "".join(head)
    return "".join(lines)


def diff_stats(diff_text: str) -> dict[str, int]:
    """Count +/- lines (excluding headers)."""
    added = removed = 0
    for ln in (diff_text or "").splitlines():
        if ln.startswith("+++") or ln.startswith("---") or ln.startswith("@@"):
            continue
        if ln.startswith("+"):
            added += 1
        elif ln.startswith("-"):
            removed += 1
    return {"added": added, "removed": removed, "total": added + removed}


def summarize_edit(
    *,
    path: str,
    old: str,
    new: str,
    action: str = "edit",
) -> dict[str, Any]:
    """
    Full package for tool results / UI.
    {diff, stats, summary, is_new, path, action}
    """
    path_s = str(path or "")
    is_new = not (old or "").strip() and bool((new or "").strip())
    if is_new and action == "edit":
        action = "create"
    diff = unified_diff(old or "", new or "", path=path_s)
    stats = diff_stats(diff)
    name = Path(path_s).name if path_s else "file"
    if not diff and (old or "") == (new or ""):
        summary = f"No change · {name}"
    elif is_new:
        summary = f"Created {name} · +{stats['added']} lines"
    elif action == "delete":
        summary = f"Deleted {name} · -{stats['removed']} lines"
    else:
        summary = f"Edited {name} · +{stats['added']} / -{stats['removed']}"
    return {
        "path": path_s,
        "action": action,
        "is_new": is_new,
        "diff": diff,
        "stats": stats,
        "summary": summary,
        "old_chars": len(old or ""),
        "new_chars": len(new or ""),
    }


def format_diff_display(diff_text: str, *, summary: str = "", path: str = "") -> str:
    """Human-readable block for chat tool messages."""
    head = summary or "File change"
    if path:
        head = f"{head}\nPath: {path}"
    body = (diff_text or "").rstrip()
    if not body:
        return head + "\n(no textual diff)"
    return f"{head}\n\n```diff\n{body}\n```"


def record_edit(edit: dict[str, Any], *, chat_id: str = "") -> dict[str, Any]:
    """Append to session file-edit log (for later Artifacts / audit)."""
    entry = {
        "id": str(uuid.uuid4())[:12],
        "at": _now(),
        "chat_id": chat_id or "",
        "path": edit.get("path") or "",
        "action": edit.get("action") or "edit",
        "summary": edit.get("summary") or "",
        "stats": edit.get("stats") or {},
        "diff": (edit.get("diff") or "")[:50000],
    }
    with _lock:
        data = _read_json(log_path(), None)
        if not isinstance(data, dict):
            data = {"events": []}
        events = list(data.get("events") or [])
        events.insert(0, entry)
        data["events"] = events[:300]
        data["updated_at"] = _now()
        _write_json(log_path(), data)
    return entry


def list_recent_edits(limit: int = 30, *, chat_id: str = "") -> list[dict[str, Any]]:
    data = _read_json(log_path(), {"events": []})
    events = list((data or {}).get("events") or [])
    if chat_id:
        events = [e for e in events if str(e.get("chat_id") or "") == chat_id]
    return events[: max(1, int(limit))]


def extract_diff_from_text(text: str) -> str:
    """Pull ```diff ... ``` or unified diff hunks from tool message content."""
    t = text or ""
    m = re_search_diff_fence(t)
    if m:
        return m
    # bare unified diff
    lines = t.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if ln.startswith("--- ") or ln.startswith("diff --git"):
            start = i
            break
        if ln.startswith("@@ "):
            start = i
            break
    if start is None:
        return ""
    return "\n".join(lines[start:]).strip()


def re_search_diff_fence(text: str) -> str:
    import re

    m = re.search(r"```diff\s*\n([\s\S]*?)```", text or "", re.I)
    if m:
        return (m.group(1) or "").strip()
    m2 = re.search(r"```\s*\n(--- [\s\S]*?)```", text or "")
    if m2 and ("@@" in m2.group(1) or m2.group(1).startswith("---")):
        return (m2.group(1) or "").strip()
    return ""
