"""Fine-grained allow / ask / deny rules for agent tools (Grok-style)."""

from __future__ import annotations

import fnmatch
import re
from typing import Any

from app.core.services.data.storage import load_config, save_config


# rule format: "tool" or "tool:pattern"  e.g. "terminal:rm *", "write_file:**/.env"
DEFAULT_DENY: list[str] = [
    "terminal:format *",
    "terminal:rm -rf /",
    "terminal:Remove-Item -Recurse -Force C:\\",
]


def permission_mode() -> str:
    """ask | auto | always_approve | plan"""
    cfg = load_config()
    m = str(cfg.get("agent_permission_mode") or "auto").lower().strip()
    if m in ("always-approve", "yolo", "bypass"):
        return "always_approve"
    if m not in ("ask", "auto", "always_approve", "plan"):
        return "auto"
    return m


def _rule_lists() -> tuple[list[str], list[str], list[str]]:
    cfg = load_config()
    allow = list(cfg.get("agent_allow_rules") or [])
    ask = list(cfg.get("agent_ask_rules") or [])
    deny = list(cfg.get("agent_deny_rules") or DEFAULT_DENY)
    return (
        [str(x) for x in allow],
        [str(x) for x in ask],
        [str(x) for x in deny],
    )


def save_rules(
    *,
    allow: list[str] | None = None,
    ask: list[str] | None = None,
    deny: list[str] | None = None,
    mode: str | None = None,
) -> dict[str, Any]:
    cfg = load_config()
    if allow is not None:
        cfg["agent_allow_rules"] = allow
    if ask is not None:
        cfg["agent_ask_rules"] = ask
    if deny is not None:
        cfg["agent_deny_rules"] = deny
    if mode is not None:
        cfg["agent_permission_mode"] = mode
    save_config(cfg)
    return status()


def _match_rule(rule: str, tool: str, detail: str) -> bool:
    rule = (rule or "").strip()
    if not rule:
        return False
    tool = (tool or "").lower()
    detail = detail or ""
    if ":" in rule:
        rtool, pat = rule.split(":", 1)
        rtool = rtool.strip().lower()
        pat = pat.strip()
        if rtool != tool and rtool != "*":
            return False
        # glob then substring
        if fnmatch.fnmatch(detail, pat) or fnmatch.fnmatch(detail.lower(), pat.lower()):
            return True
        try:
            if re.search(pat, detail, re.I):
                return True
        except re.error:
            if pat.lower() in detail.lower():
                return True
        return False
    # tool-only rule
    return rule.lower() in (tool, "*")


def evaluate(tool: str, summary: str, detail: str = "") -> dict[str, Any]:
    """
    Returns {decision: allow|ask|deny, reason, mode}.
    """
    mode = permission_mode()
    allow, ask, deny = _rule_lists()
    blob = f"{summary}\n{detail}"

    for r in deny:
        if _match_rule(r, tool, blob):
            return {"decision": "deny", "reason": f"deny rule: {r}", "mode": mode, "rule": r}

    for r in allow:
        if _match_rule(r, tool, blob):
            return {"decision": "allow", "reason": f"allow rule: {r}", "mode": mode, "rule": r}

    for r in ask:
        if _match_rule(r, tool, blob):
            return {"decision": "ask", "reason": f"ask rule: {r}", "mode": mode, "rule": r}

    if mode == "always_approve":
        return {"decision": "allow", "reason": "always_approve", "mode": mode}
    if mode == "plan":
        # plan mode: only plan_write and read tools free
        if tool in (
            "read_file",
            "list_dir",
            "grep",
            "plan_write",
            "plan_read",
            "todo_write",
            "todo_read",
            "web_search",
            "project_rules",
        ):
            return {"decision": "allow", "reason": "plan-mode read/plan", "mode": mode}
        return {"decision": "deny", "reason": "plan mode: writes/exec blocked", "mode": mode}
    if mode == "ask":
        risky = tool in (
            "terminal",
            "write_file",
            "apply_patch",
            "search_replace",
            "delete_file",
            "gui",
            "pip",
            "self_improve",
            "git_write",
            "bg_shell",
        )
        if risky:
            return {"decision": "ask", "reason": "ask mode risky tool", "mode": mode}
        return {"decision": "allow", "reason": "ask mode safe tool", "mode": mode}

    # auto: allow most, ask on very risky
    very_risky = tool in ("self_improve", "delete_file", "gui")
    if very_risky:
        return {"decision": "ask", "reason": "auto mode elevated risk", "mode": mode}
    return {"decision": "allow", "reason": "auto mode", "mode": mode}


def status() -> dict[str, Any]:
    allow, ask, deny = _rule_lists()
    return {
        "mode": permission_mode(),
        "allow": allow,
        "ask": ask,
        "deny": deny,
        "risk_tier": get_risk_tier(),
        "risk_label": risk_tier_label(get_risk_tier()),
    }


# ---------------------------------------------------------------------------
# User-facing risk tiers (Task #4): Read-only / Ask / Full
# Maps onto permission_mode + sandbox + tool_approval_required.
# ---------------------------------------------------------------------------

RISK_TIERS = ("read_only", "ask", "full")

_RISK_LABELS = {
    "read_only": "Read-only",
    "ask": "Ask first",
    "full": "Full access",
}

_RISK_BADGES = {
    "read_only": "🔒 Read",
    "ask": "✋ Ask",
    "full": "⚡ Full",
}

_RISK_HINTS = {
    "read_only": "Reads + search only — no terminal, file writes, or PC control",
    "ask": "Risky tools pause for your OK (Approvals page)",
    "full": "Agent may run tools without stopping (still blocks hard deny rules)",
}


def get_risk_tier() -> str:
    """Return read_only | ask | full (default ask for safety)."""
    cfg = load_config()
    t = str(cfg.get("agent_risk_tier") or "").lower().strip().replace("-", "_").replace(" ", "_")
    if t in ("readonly", "read"):
        t = "read_only"
    if t in ("yolo", "auto", "always_approve", "unrestricted"):
        t = "full"
    if t in RISK_TIERS:
        return t
    # Infer from existing settings if never set
    mode = str(cfg.get("agent_permission_mode") or "auto").lower()
    if mode in ("plan",):
        return "read_only"
    if mode in ("ask",):
        return "ask"
    if mode in ("always_approve", "always-approve", "yolo", "bypass"):
        return "full"
    if bool(cfg.get("tool_approval_required")):
        return "ask"
    return "ask"  # safe default for lay users


def risk_tier_label(tier: str | None = None) -> str:
    t = (tier or get_risk_tier()).lower()
    return _RISK_LABELS.get(t, _RISK_LABELS["ask"])


def risk_tier_badge(tier: str | None = None) -> str:
    t = (tier or get_risk_tier()).lower()
    return _RISK_BADGES.get(t, _RISK_BADGES["ask"])


def risk_tier_hint(tier: str | None = None) -> str:
    t = (tier or get_risk_tier()).lower()
    return _RISK_HINTS.get(t, _RISK_HINTS["ask"])


def set_risk_tier(tier: str) -> dict[str, Any]:
    """
    Apply a risk tier and sync underlying permission/sandbox/approval flags.
    Returns status() after apply.
    """
    t = (tier or "ask").lower().strip().replace("-", "_").replace(" ", "_")
    if t in ("readonly", "read"):
        t = "read_only"
    if t in ("yolo", "unrestricted", "always_approve"):
        t = "full"
    if t not in RISK_TIERS:
        t = "ask"

    cfg = load_config()
    cfg["agent_risk_tier"] = t

    if t == "read_only":
        cfg["agent_permission_mode"] = "plan"
        cfg["agent_sandbox_enabled"] = True
        cfg["agent_sandbox_profile"] = "read_only_workspace"
        cfg["tool_approval_required"] = True
    elif t == "ask":
        cfg["agent_permission_mode"] = "ask"
        cfg["agent_sandbox_enabled"] = True
        cur_prof = str(cfg.get("agent_sandbox_profile") or "").lower()
        if cur_prof in ("read_only", "read_only_workspace", "off", ""):
            cfg["agent_sandbox_profile"] = "project_only"
        cfg["tool_approval_required"] = True
    else:  # full
        cfg["agent_permission_mode"] = "auto"
        # Map to Full disk with ask profile unless user already chose workspace/off
        if "agent_sandbox_enabled" not in cfg:
            cfg["agent_sandbox_enabled"] = True
        cur_prof = str(cfg.get("agent_sandbox_profile") or "").lower()
        if cur_prof in ("read_only", "read_only_workspace", ""):
            cfg["agent_sandbox_profile"] = "full_ask"
        cfg["tool_approval_required"] = False

    save_config(cfg)
    return {
        "ok": True,
        "tier": t,
        "label": risk_tier_label(t),
        "badge": risk_tier_badge(t),
        "hint": risk_tier_hint(t),
        "mode": permission_mode(),
        "tool_approval_required": bool(cfg.get("tool_approval_required")),
        "sandbox_enabled": bool(cfg.get("agent_sandbox_enabled")),
        "sandbox_profile": str(cfg.get("agent_sandbox_profile") or ""),
    }


def cycle_risk_tier() -> dict[str, Any]:
    """Cycle read_only → ask → full → read_only."""
    order = list(RISK_TIERS)
    cur = get_risk_tier()
    try:
        i = order.index(cur)
    except ValueError:
        i = 1
    nxt = order[(i + 1) % len(order)]
    return set_risk_tier(nxt)
