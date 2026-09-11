"""Long-term memory for the studio (facts the LLM / CEO can use)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.paths import memory_path
from app.core.services.data.storage import _read_json, _write_json


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_memory() -> dict[str, Any]:
    data = _read_json(memory_path(), None)
    if isinstance(data, dict) and "items" in data:
        return data
    return {"items": [], "updated_at": _now()}


def save_memory(mem: dict[str, Any]) -> None:
    mem["updated_at"] = _now()
    _write_json(memory_path(), mem)


def list_items(project_id: str = "") -> list[dict[str, Any]]:
    items = load_memory().get("items") or []
    if project_id:
        return [i for i in items if (i.get("project_id") or "") in ("", project_id)]
    return list(items)


def add_item(
    content: str,
    *,
    tags: list[str] | None = None,
    project_id: str = "",
    source: str = "user",
) -> dict[str, Any]:
    mem = load_memory()
    item = {
        "id": str(uuid.uuid4()),
        "content": content.strip(),
        "tags": tags or [],
        "project_id": project_id,
        "source": source,
        "created_at": _now(),
    }
    mem.setdefault("items", []).insert(0, item)
    save_memory(mem)
    return item


def delete_item(item_id: str) -> None:
    mem = load_memory()
    mem["items"] = [i for i in (mem.get("items") or []) if i.get("id") != item_id]
    save_memory(mem)


def memory_prompt_block(limit: int = 40, project_id: str = "") -> str:
    items = list_items(project_id=project_id)[:limit]
    if not items:
        return "## Memory\n(no stored memories yet)"
    lines = ["## Memory (use when relevant; do not invent facts not listed)"]
    for i in items:
        tags = ",".join(i.get("tags") or [])
        lines.append(f"- [{i.get('id','')[:8]}] {i.get('content')} (tags:{tags})")
    return "\n".join(lines)
