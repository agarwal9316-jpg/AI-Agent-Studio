"""Home one-click work modes (Task #5): Research / Control PC / Code / Team."""

from __future__ import annotations

from typing import Any

PRESET_IDS = ("research", "control_pc", "code", "team")

# Pure flag maps applied to chat_state / UI vars. risk_tier uses permissions API.
PRESETS: dict[str, dict[str, Any]] = {
    "research": {
        "id": "research",
        "label": "Research",
        "icon": "🔍",
        "title": "Research the web",
        "body": "Search and read pages. Safe tools on; PC control off.",
        "page": "Chat",
        "mode": "action",
        "terminal_enabled": False,
        "laptop_enabled": False,
        "skills_enabled": True,
        "mcp_enabled": True,
        "safety_mode": False,
        "use_workflow_graph": False,
        "risk_tier": "ask",
        "starter": "Research this topic and summarize with sources:\n",
        "status": "Research mode — web search + read; terminal/PC off",
    },
    "control_pc": {
        "id": "control_pc",
        "label": "Control PC",
        "icon": "🖥",
        "title": "Control this PC",
        "body": "Terminal + mouse/keyboard. Asks before risky actions.",
        "page": "Chat",
        "mode": "action",
        "terminal_enabled": True,
        "laptop_enabled": True,
        "skills_enabled": True,
        "mcp_enabled": True,
        "safety_mode": True,
        "use_workflow_graph": False,
        "risk_tier": "ask",
        "starter": "On this PC, please help me with:\n",
        "status": "Control PC mode — terminal + laptop GUI; Ask first",
    },
    "code": {
        "id": "code",
        "label": "Code",
        "icon": "💻",
        "title": "Write & run code",
        "body": "Terminal + files for coding. Browser GUI off by default.",
        "page": "Chat",
        "mode": "action",
        "terminal_enabled": True,
        "laptop_enabled": False,
        "skills_enabled": True,
        "mcp_enabled": True,
        "safety_mode": False,
        "use_workflow_graph": False,
        "risk_tier": "ask",
        "starter": "Help me code this (explain + edit files as needed):\n",
        "status": "Code mode — terminal + tools; laptop GUI off",
    },
    "team": {
        "id": "team",
        "label": "Team",
        "icon": "👥",
        "title": "Multi-AI team",
        "body": "Several agents work one goal and deliver a final answer.",
        "page": "Team",
        "mode": "action",
        "terminal_enabled": True,
        "laptop_enabled": False,
        "skills_enabled": True,
        "mcp_enabled": True,
        "safety_mode": False,
        "use_workflow_graph": True,
        "risk_tier": "ask",
        "starter": "",
        "status": "Team mode — open AI Team workspace",
    },
}


def list_presets() -> list[dict[str, Any]]:
    return [dict(PRESETS[i]) for i in PRESET_IDS]


def get_preset(preset_id: str) -> dict[str, Any] | None:
    pid = (preset_id or "").lower().strip().replace("-", "_").replace(" ", "_")
    if pid in ("pc", "control", "desktop"):
        pid = "control_pc"
    if pid in ("coding", "dev"):
        pid = "code"
    if pid in ("search", "web"):
        pid = "research"
    return dict(PRESETS[pid]) if pid in PRESETS else None


def apply_preset_to_chat_state(state: dict[str, Any], preset_id: str) -> dict[str, Any]:
    """
    Mutate and return chat state dict with preset flags.
    Does not touch UI vars or risk_tier config (caller applies those).
    """
    p = get_preset(preset_id)
    if not p:
        return state
    state["mode"] = p.get("mode") or "action"
    state["terminal_enabled"] = bool(p.get("terminal_enabled"))
    state["laptop_enabled"] = bool(p.get("laptop_enabled"))
    state["skills_enabled"] = bool(p.get("skills_enabled", True))
    state["mcp_enabled"] = bool(p.get("mcp_enabled", True))
    state["safety_mode"] = bool(p.get("safety_mode"))
    state["use_workflow_graph"] = bool(p.get("use_workflow_graph"))
    state["home_preset"] = p.get("id")
    return state
