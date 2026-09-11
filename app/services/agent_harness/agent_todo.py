"""Agent-visible todo list (Grok-style progress)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from app.paths import data_dir


def _path(chat_id: str | None = None) -> Path:
    d = data_dir() / "agent_todos"
    d.mkdir(parents=True, exist_ok=True)
    cid = (chat_id or "default").replace("/", "_")[:64]
    return d / f"{cid}.json"


def load_todos(chat_id: str | None = None) -> list[dict[str, Any]]:
    p = _path(chat_id)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return list(data.get("todos") or [])
    except Exception:  # noqa: BLE001
        return []


def save_todos(todos: list[dict[str, Any]], chat_id: str | None = None) -> dict[str, Any]:
    p = _path(chat_id)
    p.write_text(json.dumps({"todos": todos}, indent=2), encoding="utf-8")
    return {"ok": True, "count": len(todos), "todos": todos, "path": str(p)}


def write_todos(
    items: list[dict[str, Any]],
    *,
    chat_id: str | None = None,
    merge: bool = True,
) -> dict[str, Any]:
    """
    items: [{id?, content, status: pending|in_progress|completed|cancelled}]
    """
    current = {t.get("id"): t for t in load_todos(chat_id) if t.get("id")}
    out: list[dict[str, Any]] = list(load_todos(chat_id)) if merge else []
    by_id = {t.get("id"): i for i, t in enumerate(out) if t.get("id")}

    for it in items or []:
        tid = it.get("id") or uuid.uuid4().hex[:8]
        status = str(it.get("status") or "pending")
        if status not in ("pending", "in_progress", "completed", "cancelled"):
            status = "pending"
        row = {
            "id": tid,
            "content": it.get("content") or current.get(tid, {}).get("content") or "",
            "status": status,
        }
        if not row["content"] and tid in current:
            row["content"] = current[tid].get("content") or ""
        if tid in by_id:
            out[by_id[tid]] = {**out[by_id[tid]], **row}
        else:
            out.append(row)
            by_id[tid] = len(out) - 1
    return save_todos(out, chat_id)


def format_for_prompt(chat_id: str | None = None) -> str:
    todos = load_todos(chat_id)
    if not todos:
        return ""
    lines = ["## Agent todos"]
    for t in todos:
        mark = {
            "pending": "[ ]",
            "in_progress": "[~]",
            "completed": "[x]",
            "cancelled": "[-]",
        }.get(t.get("status") or "", "[ ]")
        lines.append(f"- {mark} {t.get('id')}: {t.get('content')}")
    return "\n".join(lines)
