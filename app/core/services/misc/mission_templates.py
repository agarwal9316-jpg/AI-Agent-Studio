"""One-click mission templates for Cockpit."""

from __future__ import annotations

from typing import Any

# Each template configures navigation + optional chat flags / team mode
TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "chat_action",
        "title": "Chat · Action",
        "subtitle": "Single agent with full tools",
        "page": "Chat",
        "icon": "💬",
        "flags": {
            "mode": "action",
            "terminal_enabled": True,
            "laptop_enabled": True,
            "skills_enabled": True,
            "mcp_enabled": True,
            "use_workflow_graph": False,
        },
    },
    {
        "id": "team_pipeline",
        "title": "Team · Pipeline",
        "subtitle": "Multi-AI sequential coordination",
        "page": "Team",
        "icon": "⧉",
        "flags": {},
    },
    {
        "id": "team_coordinate",
        "title": "Team · Coordinate",
        "subtitle": "Agents talk to each other",
        "page": "Team",
        "icon": "⧉",
        "flags": {},
        "hint": "New goal → mode=coordinate",
    },
    {
        "id": "research",
        "title": "Deep research",
        "subtitle": "Web search + page fetch",
        "page": "Chat",
        "icon": "🔍",
        "flags": {
            "mode": "action",
            "terminal_enabled": False,
            "use_workflow_graph": False,
        },
        "starter": "Search the web and deep-research: ",
    },
    {
        "id": "pc_control",
        "title": "Control this PC",
        "subtitle": "Terminal + GUI + screenshot",
        "page": "Chat",
        "icon": "🖥",
        "flags": {
            "mode": "action",
            "terminal_enabled": True,
            "laptop_enabled": True,
            "safety_mode": False,
        },
        "starter": "On this Windows PC, ",
    },
    {
        "id": "knowledge",
        "title": "Ask my files",
        "subtitle": "Local Knowledge RAG",
        "page": "Knowledge",
        "icon": "📚",
        "flags": {},
    },
    {
        "id": "models",
        "title": "Models & train",
        "subtitle": "Create / pull / fine-tune LLMs",
        "page": "Models",
        "icon": "🧠",
        "flags": {},
    },
    {
        "id": "monitor",
        "title": "Mission Control",
        "subtitle": "Live monitoring & ops log",
        "page": "Monitor",
        "icon": "📊",
        "flags": {},
    },
    {
        "id": "org",
        "title": "Org charts",
        "subtitle": "Build or AI-create company tree",
        "page": "Org chart",
        "icon": "⎇",
        "flags": {},
    },
    {
        "id": "train_from_chats",
        "title": "Train on my chats",
        "subtitle": "Export dataset + open train lab",
        "page": "Models",
        "icon": "🧪",
        "flags": {},
        "action": "export_chat_dataset",
    },
]


def list_templates() -> list[dict[str, Any]]:
    return list(TEMPLATES)


def get_template(tid: str) -> dict[str, Any] | None:
    for t in TEMPLATES:
        if t.get("id") == tid:
            return t
    return None
