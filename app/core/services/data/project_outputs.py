"""Save agent / chat results into project output folders."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.paths import data_dir


def _get_project_store():
    """Lazy import to break circular dependency."""
    from app.services import project_store
    return project_store


def _now_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _safe_name(s: str) -> str:
    s = re.sub(r"[^\w\-. ]+", "", (s or "output").strip())[:60]
    return s.replace(" ", "_") or "output"


def project_outputs_dir(project_id: str = "") -> Path:
    pid = project_id or _get_project_store().get_active_project_id() or "ungrouped"
    d = data_dir() / "project_outputs" / pid
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_result(
    content: str,
    *,
    title: str = "result",
    agent_name: str = "",
    project_id: str = "",
    source: str = "agent",
    ext: str = ".md",
) -> dict[str, Any]:
    """Write content into project outputs folder; return path meta."""
    text = content or ""
    if not text.strip():
        return {"ok": False, "error": "Empty content"}
    folder = project_outputs_dir(project_id)
    name = f"{_now_slug()}_{_safe_name(agent_name or source)}_{_safe_name(title)}{ext}"
    path = folder / name
    header = (
        f"# {title}\n\n"
        f"- Agent: {agent_name or '—'}\n"
        f"- Source: {source}\n"
        f"- Saved: {datetime.now(timezone.utc).isoformat()}\n\n"
        f"---\n\n"
    )
    if ext.lower() in (".md", ".txt", ".json", ".py", ".csv"):
        path.write_text(header + text if ext.lower() == ".md" else text, encoding="utf-8")
    else:
        path.write_text(text, encoding="utf-8")
    # index on project
    pid = project_id or _get_project_store().get_active_project_id()
    if pid:
        proj = _get_project_store().load_project(pid)
        if proj:
            outs = list(proj.get("outputs") or [])
            outs.insert(
                0,
                {
                    "path": str(path),
                    "title": title,
                    "agent": agent_name,
                    "source": source,
                    "at": datetime.now(timezone.utc).isoformat(),
                },
            )
            proj["outputs"] = outs[:100]
            _get_project_store().save_project(proj)
    return {"ok": True, "path": str(path.resolve()), "name": name}


def list_outputs(project_id: str = "", limit: int = 50) -> list[dict[str, Any]]:
    folder = project_outputs_dir(project_id)
    files = sorted(folder.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    out = []
    for p in files[:limit]:
        if p.is_file():
            out.append(
                {
                    "path": str(p.resolve()),
                    "name": p.name,
                    "size": p.stat().st_size,
                    "mtime": datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat(),
                }
            )
    return out


def save_chat_exchange_to_project(
    messages: list[dict[str, Any]],
    *,
    title: str = "chat_export",
    project_id: str = "",
    agent_name: str = "",
) -> dict[str, Any]:
    lines = []
    for m in messages:
        role = m.get("role") or "?"
        content = m.get("content") or ""
        who = m.get("agent_name") or role
        lines.append(f"## {who}\n\n{content}\n")
    return save_result(
        "\n".join(lines),
        title=title,
        agent_name=agent_name,
        project_id=project_id,
        source="chat",
        ext=".md",
    )
