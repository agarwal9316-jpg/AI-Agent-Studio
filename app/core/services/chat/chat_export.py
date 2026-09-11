"""Export chats to Markdown / JSON / plain text."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.paths import app_root


def exports_dir() -> Path:
    d = app_root() / "data" / "exports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def export_chat(
    chat: dict[str, Any],
    *,
    fmt: str = "md",
    path: Path | None = None,
) -> Path:
    fmt = (fmt or "md").lower()
    title = (chat.get("title") or "chat").replace("/", "-").replace("\\", "-")
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    if path is None:
        ext = "json" if fmt == "json" else ("txt" if fmt == "txt" else "md")
        path = exports_dir() / f"{title[:40]}_{ts}.{ext}"

    from app.core.services.misc.redact import redact_obj, redact_text

    messages = chat.get("messages") or []
    if fmt == "json":
        safe = redact_obj(dict(chat))
        path.write_text(json.dumps(safe, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    lines: list[str] = []
    if fmt == "md":
        lines.append(f"# {chat.get('title') or 'Chat'}")
        lines.append("")
        lines.append(f"- id: `{chat.get('id')}`")
        lines.append(f"- project_id: `{chat.get('project_id') or ''}`")
        lines.append(f"- exported: {ts}")
        lines.append("")
        for m in messages:
            role = m.get("role") or "unknown"
            content = redact_text(str(m.get("content") or ""))
            lines.append(f"## {role}")
            lines.append("")
            lines.append(content)
            lines.append("")
            # media refs
            for key in ("images", "videos", "attachments"):
                for p in m.get(key) or []:
                    lines.append(f"![]({p})" if key == "images" else f"- media: `{p}`")
            lines.append("")
    else:
        lines.append(f"{chat.get('title')}\n")
        for m in messages:
            lines.append(f"[{m.get('role')}]\n{redact_text(str(m.get('content') or ''))}\n")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path
