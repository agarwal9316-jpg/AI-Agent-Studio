"""Projects: group chats, goals, memory scope."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.paths import projects_dir
from app.core.services.data.storage import _read_json, _write_json, load_config, save_config


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_projects() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in sorted(projects_dir().glob("*.json"), reverse=True):
        data = _read_json(p, None)
        if isinstance(data, dict) and data.get("id"):
            out.append(data)
    return out


def load_project(project_id: str) -> dict[str, Any] | None:
    path = projects_dir() / f"{project_id}.json"
    data = _read_json(path, None)
    return data if isinstance(data, dict) else None


def save_project(proj: dict[str, Any]) -> dict[str, Any]:
    if not proj.get("id"):
        proj["id"] = str(uuid.uuid4())
        proj["created_at"] = _now()
    proj["updated_at"] = _now()
    _write_json(projects_dir() / f"{proj['id']}.json", proj)
    return proj


def new_project(name: str, description: str = "") -> dict[str, Any]:
    return save_project(
        {
            "id": str(uuid.uuid4()),
            "name": name.strip() or "Untitled project",
            "description": description.strip(),
            "status": "active",
            "system_prompt": "",
            "prompt_preset_id": "",
            "created_at": _now(),
        }
    )


def set_project_prompt(
    project_id: str,
    *,
    system_prompt: str | None = None,
    prompt_preset_id: str | None = None,
) -> dict[str, Any] | None:
    """Task #11: attach a system prompt or library preset to a project."""
    proj = load_project(project_id)
    if not proj:
        return None
    if system_prompt is not None:
        proj["system_prompt"] = system_prompt
    if prompt_preset_id is not None:
        proj["prompt_preset_id"] = prompt_preset_id
    return save_project(proj)


def delete_project(project_id: str) -> None:
    path = projects_dir() / f"{project_id}.json"
    if path.exists():
        path.unlink()


def get_active_project_id() -> str:
    return str(load_config().get("active_project_id") or "")


def set_active_project_id(project_id: str) -> None:
    cfg = load_config()
    cfg["active_project_id"] = project_id
    save_config(cfg)
