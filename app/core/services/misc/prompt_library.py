"""Prompt library + system presets (Task #11), optional per-project override."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.paths import data_dir
from app.core.services.misc.default_prompts import get_default_system_prompt
from app.core.services.data.storage import _read_json, _write_json, load_config, save_config

BUILTIN: list[dict[str, Any]] = [
    {
        "id": "default",
        "name": "Default operator",
        "category": "system",
        "builtin": True,
        "body": "",  # empty → app default
        "hint": "Full AI Agent Studio operator prompt",
    },
    {
        "id": "research",
        "name": "Research analyst",
        "category": "work",
        "builtin": True,
        "hint": "Web research with citations",
        "body": (
            "You are a careful research analyst.\n"
            "Use WEB_SEARCH / WEB_FETCH for claims. Cite sources with titles and URLs.\n"
            "Structure answers: summary → key findings → sources. Prefer primary sources.\n"
            "Do not invent links or statistics."
        ),
    },
    {
        "id": "coding",
        "name": "Coding pair",
        "category": "work",
        "builtin": True,
        "hint": "Write and edit code with tools",
        "body": (
            "You are an expert software engineer pair-programmer.\n"
            "Prefer reading files before editing. Use search_replace for surgical edits.\n"
            "Explain changes briefly. Run tests/commands via TERMINAL when useful.\n"
            "Match existing style. Never invent file contents — verify with tools."
        ),
    },
    {
        "id": "pc_helper",
        "name": "PC helper",
        "category": "work",
        "builtin": True,
        "hint": "Windows desktop tasks",
        "body": (
            "You help the user operate this Windows PC safely and clearly.\n"
            "Use TERMINAL and GUI tools when asked. Confirm destructive actions.\n"
            "Explain what you did in plain English for a non-technical user."
        ),
    },
    {
        "id": "writer",
        "name": "Writer / editor",
        "category": "work",
        "builtin": True,
        "hint": "Clear writing and editing",
        "body": (
            "You are a sharp editor and writer.\n"
            "Improve clarity, structure, and tone. Offer a polished draft and a short "
            "list of changes. Match the user's requested style (formal, casual, etc.)."
        ),
    },
    {
        "id": "concise",
        "name": "Concise answers",
        "category": "style",
        "builtin": True,
        "hint": "Short replies by default",
        "body": (
            "Be concise. Prefer short paragraphs and bullet lists.\n"
            "Skip filler. Expand only when the user asks for detail."
        ),
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def library_path():
    return data_dir() / "prompt_library.json"


def _load_user() -> list[dict[str, Any]]:
    data = _read_json(library_path(), None)
    if isinstance(data, dict):
        return list(data.get("items") or [])
    if isinstance(data, list):
        return data
    return []


def _save_user(items: list[dict[str, Any]]) -> None:
    _write_json(library_path(), {"items": items, "updated_at": _now()})


def list_presets(*, include_builtin: bool = True) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if include_builtin:
        for b in BUILTIN:
            out.append(dict(b))
    for u in _load_user():
        if isinstance(u, dict) and u.get("id"):
            item = dict(u)
            item["builtin"] = False
            out.append(item)
    return out


def get_preset(preset_id: str) -> dict[str, Any] | None:
    pid = (preset_id or "").strip()
    if not pid:
        return None
    for p in list_presets():
        if str(p.get("id")) == pid:
            return p
    return None


def resolve_prompt_body(preset_id: str = "", *, fallback_default: bool = True) -> str:
    """Return system prompt text for a preset id."""
    p = get_preset(preset_id) if preset_id else None
    if not p:
        return get_default_system_prompt() if fallback_default else ""
    body = (p.get("body") or "").strip()
    if not body or str(p.get("id")) == "default":
        return get_default_system_prompt() if fallback_default else ""
    return body + "\n"


def save_user_preset(
    *,
    name: str,
    body: str,
    category: str = "custom",
    hint: str = "",
    preset_id: str = "",
) -> dict[str, Any]:
    items = _load_user()
    pid = (preset_id or "").strip() or str(uuid.uuid4())[:12]
    # no overwrite of builtin ids
    if pid in {b["id"] for b in BUILTIN}:
        pid = str(uuid.uuid4())[:12]
    entry = {
        "id": pid,
        "name": (name or "Custom preset").strip() or "Custom preset",
        "category": (category or "custom").strip(),
        "hint": (hint or "").strip(),
        "body": (body or "").strip(),
        "builtin": False,
        "updated_at": _now(),
    }
    found = False
    for i, it in enumerate(items):
        if str(it.get("id")) == pid:
            items[i] = entry
            found = True
            break
    if not found:
        items.insert(0, entry)
    _save_user(items[:100])
    return entry


def delete_user_preset(preset_id: str) -> bool:
    pid = (preset_id or "").strip()
    if not pid or pid in {b["id"] for b in BUILTIN}:
        return False
    items = [i for i in _load_user() if str(i.get("id")) != pid]
    _save_user(items)
    return True


def get_active_preset_id() -> str:
    return str(load_config().get("active_prompt_preset_id") or "default")


def set_active_preset_id(preset_id: str) -> None:
    cfg = load_config()
    cfg["active_prompt_preset_id"] = (preset_id or "default").strip() or "default"
    save_config(cfg)


def resolve_effective_system_prompt(
    *,
    config_prompt: str = "",
    project: dict[str, Any] | None = None,
    chat: dict[str, Any] | None = None,
) -> str:
    """
    Priority (Task #11):
      1. Chat-level system_prompt / prompt_preset_id
      2. Project system_prompt / prompt_preset_id
      3. Config active_prompt_preset_id (if not default and no custom config text)
      4. Config system_prompt or built-in default
    """
    # Chat override
    if chat:
        cp = str(chat.get("system_prompt") or "").strip()
        if cp:
            return cp
        cpid = str(chat.get("prompt_preset_id") or "").strip()
        if cpid:
            return resolve_prompt_body(cpid)

    # Project override
    if project:
        pp = str(project.get("system_prompt") or "").strip()
        if pp:
            return pp
        ppid = str(project.get("prompt_preset_id") or "").strip()
        if ppid:
            return resolve_prompt_body(ppid)

    cfg_text = (config_prompt or "").strip()
    # If user set a full custom config prompt, keep it (unless only preset selected)
    active_pid = get_active_preset_id()
    if active_pid and active_pid != "default" and not cfg_text:
        return resolve_prompt_body(active_pid)
    if cfg_text:
        return cfg_text
    if active_pid and active_pid != "default":
        return resolve_prompt_body(active_pid)
    return get_default_system_prompt()
