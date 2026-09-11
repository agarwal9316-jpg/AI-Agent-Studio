"""Plan mode with plan.md file (Grok-style gated planning)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.paths import data_dir
from app.core.services.data.storage import load_config, save_config


def plans_dir() -> Path:
    d = data_dir() / "plans"
    d.mkdir(parents=True, exist_ok=True)
    return d


def plan_path(chat_id: str | None = None) -> Path:
    cid = (chat_id or "default").replace("/", "_").replace("\\", "_")[:64]
    return plans_dir() / f"{cid}_plan.md"


def is_plan_mode() -> bool:
    cfg = load_config()
    return bool(cfg.get("agent_plan_mode", False)) or str(
        cfg.get("agent_permission_mode") or ""
    ).lower() == "plan"


def enter_plan_mode(chat_id: str | None = None) -> dict[str, Any]:
    cfg = load_config()
    cfg["agent_plan_mode"] = True
    cfg["agent_permission_mode"] = "plan"
    cfg["agent_plan_chat_id"] = chat_id or cfg.get("active_chat_id") or "default"
    save_config(cfg)
    p = plan_path(str(cfg["agent_plan_chat_id"]))
    if not p.exists():
        p.write_text(
            f"# Plan\n\n_Started {datetime.now(timezone.utc).isoformat()}_\n\n"
            "## Context\n\n## Approach\n\n## Files to change\n\n## Verification\n",
            encoding="utf-8",
        )
    return {"ok": True, "plan_mode": True, "path": str(p)}


def exit_plan_mode(*, approve: bool = False) -> dict[str, Any]:
    cfg = load_config()
    cfg["agent_plan_mode"] = False
    if cfg.get("agent_permission_mode") == "plan":
        cfg["agent_permission_mode"] = "auto"
    cfg["agent_plan_approved"] = bool(approve)
    save_config(cfg)
    return {
        "ok": True,
        "plan_mode": False,
        "approved": bool(approve),
        "hint": "Plan approved — execute in Action mode" if approve else "Plan mode off",
    }


def write_plan(content: str, chat_id: str | None = None) -> dict[str, Any]:
    cfg = load_config()
    cid = chat_id or cfg.get("agent_plan_chat_id") or cfg.get("active_chat_id") or "default"
    p = plan_path(str(cid))
    p.write_text(content or "", encoding="utf-8")
    return {"ok": True, "path": str(p), "chars": len(content or "")}


def read_plan(chat_id: str | None = None) -> dict[str, Any]:
    cfg = load_config()
    cid = chat_id or cfg.get("agent_plan_chat_id") or cfg.get("active_chat_id") or "default"
    p = plan_path(str(cid))
    if not p.exists():
        return {"ok": False, "error": "No plan file yet", "path": str(p)}
    text = p.read_text(encoding="utf-8", errors="replace")
    return {"ok": True, "path": str(p), "content": text, "chars": len(text)}


def status(chat_id: str | None = None) -> dict[str, Any]:
    p = plan_path(chat_id)
    cfg = load_config()
    return {
        "plan_mode": is_plan_mode(),
        "approved": bool(cfg.get("agent_plan_approved")),
        "path": str(p),
        "exists": p.exists(),
    }
