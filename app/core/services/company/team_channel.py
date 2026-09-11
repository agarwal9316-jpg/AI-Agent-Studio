"""Teams-style goal channels for multi-AI coordination.

One goal = one channel with a message feed, roster presence, and final answer.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from app.paths import team_channels_dir
from app.core.services.data.storage import _read_json, _write_json


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _index_path():
    return team_channels_dir() / "index.json"


def _channel_path(channel_id: str):
    return team_channels_dir() / f"{channel_id}.json"


def _load_index() -> dict[str, Any]:
    data = _read_json(_index_path(), None)
    if isinstance(data, dict) and isinstance(data.get("channels"), list):
        return data
    return {"channels": [], "active_id": ""}


def _save_index(idx: dict[str, Any]) -> None:
    _write_json(_index_path(), idx)


def list_channels(*, limit: int = 50) -> list[dict[str, Any]]:
    """Recent channel summaries (newest first)."""
    idx = _load_index()
    items = list(idx.get("channels") or [])
    items.sort(key=lambda c: str(c.get("updated_at") or c.get("created_at") or ""), reverse=True)
    return items[: max(1, limit)]


def get_active_channel_id() -> str:
    return str(_load_index().get("active_id") or "")


def set_active_channel_id(channel_id: str) -> None:
    idx = _load_index()
    idx["active_id"] = channel_id or ""
    _save_index(idx)


def load_channel(channel_id: str) -> dict[str, Any] | None:
    if not channel_id:
        return None
    data = _read_json(_channel_path(channel_id), None)
    return data if isinstance(data, dict) else None


def save_channel(ch: dict[str, Any]) -> dict[str, Any]:
    if not ch.get("id"):
        ch["id"] = str(uuid.uuid4())
    ch["updated_at"] = _now()
    if not ch.get("created_at"):
        ch["created_at"] = ch["updated_at"]
    _write_json(_channel_path(str(ch["id"])), ch)
    # update index summary
    idx = _load_index()
    summary = {
        "id": ch["id"],
        "title": ch.get("title") or "Goal",
        "status": ch.get("status") or "open",
        "org_graph_id": ch.get("org_graph_id") or "",
        "org_name": ch.get("org_name") or "",
        "mode": ch.get("mode") or "pipeline",
        "created_at": ch.get("created_at"),
        "updated_at": ch["updated_at"],
        "message_count": len(ch.get("messages") or []),
        "final_preview": (ch.get("final_text") or "")[:120],
    }
    channels = [c for c in (idx.get("channels") or []) if c.get("id") != ch["id"]]
    channels.insert(0, summary)
    idx["channels"] = channels[:100]
    idx["active_id"] = ch["id"]
    _save_index(idx)
    return ch


def delete_channel(channel_id: str) -> bool:
    ch = load_channel(channel_id)
    if not ch:
        return False
    path = _channel_path(channel_id)
    try:
        path.unlink(missing_ok=True)  # type: ignore[arg-type]
    except TypeError:
        if path.exists():
            path.unlink()
    except Exception:  # noqa: BLE001
        pass
    idx = _load_index()
    idx["channels"] = [c for c in (idx.get("channels") or []) if c.get("id") != channel_id]
    if idx.get("active_id") == channel_id:
        idx["active_id"] = (idx["channels"][0]["id"] if idx["channels"] else "")
    _save_index(idx)
    return True


def update_channel(
    channel_id: str,
    *,
    title: str | None = None,
    goal: str | None = None,
    max_rounds: int | None = None,
) -> dict[str, Any] | None:
    """Rename title and/or rewrite goal text (does not re-run the team)."""
    ch = load_channel(channel_id)
    if not ch:
        return None
    if title is not None:
        t = (title or "").strip()
        if t:
            ch["title"] = t[:120]
    if goal is not None:
        g = (goal or "").strip()
        if g:
            ch["goal"] = g
    if max_rounds is not None:
        ch.setdefault("settings", {})
        ch["settings"]["max_rounds"] = max(2, min(40, int(max_rounds)))
    return save_channel(ch)


def repair_stuck_channel(channel_id: str) -> dict[str, Any] | None:
    """
    If a channel has a finished answer but status is still 'running'
    (e.g. re-run interrupted), mark it done so the UI is honest.
    """
    ch = load_channel(channel_id)
    if not ch:
        return None
    final = str(ch.get("final_text") or "").strip()
    st = str(ch.get("status") or "")
    if final and st in ("running", "open", ""):
        ch["status"] = "done"
        return save_channel(ch)
    if st == "running" and not final:
        # Abandoned run with no answer — leave as running or mark failed?
        # Mark cancelled so user can re-start cleanly
        ch["status"] = "cancelled"
        append_message(
            ch,
            role="system",
            agent_name="System",
            content="Marked incomplete (run was interrupted). Press Start team to try again.",
            save=False,
        )
        return save_channel(ch)
    return ch


def prepare_rerun(channel_id: str) -> dict[str, Any] | None:
    """Reset roster/final for a clean re-run."""
    ch = load_channel(channel_id)
    if not ch:
        return None
    append_message(
        ch,
        role="system",
        agent_name="System",
        content="——— Re-run started (previous finished answer cleared) ———",
        save=False,
    )
    for r in ch.get("roster") or []:
        r["status"] = "waiting"
    ch["final_text"] = ""
    ch["round"] = 0
    ch["status"] = "running"
    return save_channel(ch)


def clear_channel_messages(
    channel_id: str,
    *,
    keep_goal: bool = True,
    clear_final: bool = True,
) -> dict[str, Any] | None:
    """
    Clear the chat feed for a goal (like “new chat” for this channel).
    Keeps title/goal/org/mode by default. Optionally clears finished answer.
    """
    ch = load_channel(channel_id)
    if not ch:
        return None
    goal = str(ch.get("goal") or "")
    ch["messages"] = []
    ch["round"] = 0
    if clear_final:
        ch["final_text"] = ""
    # Reset presence so the next run looks fresh
    for r in ch.get("roster") or []:
        r["status"] = "waiting"
    if ch.get("status") in ("done", "failed", "cancelled", "running"):
        ch["status"] = "open"
    append_message(
        ch,
        role="system",
        agent_name="System",
        content=(
            "Chat cleared."
            + (f"\n\nGoal is still:\n{goal}" if keep_goal and goal else "")
            + "\n\nPress Start team when you want a new run."
        ),
        save=False,
    )
    return save_channel(ch)


def roster_from_graph(graph: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Build roster seats from org chart agents + CEO."""
    from app.services import workflow_graph as wfg
    from app.core.services.data.storage import get_agent

    g = graph or {}
    roster: list[dict[str, Any]] = []
    # CEO first
    for n in g.get("nodes") or []:
        if n.get("type") == "ceo":
            roster.append(
                {
                    "org_node_id": str(n.get("id") or ""),
                    "name": str(n.get("title") or "CEO"),
                    "role": "ceo",
                    "department": "Leadership",
                    "status": "waiting",
                    "kind": "ceo",
                    "agent_id": str(n.get("agent_id") or ""),
                    "last_post_at": None,
                }
            )
    for n in wfg.walk_tree(g):
        if n.get("type") not in ("agent", "role"):
            continue
        ag = get_agent(n.get("agent_id") or "") if n.get("agent_id") else None
        parent = wfg.get_node(g, str(n.get("parent_id") or ""))
        dept = (parent or {}).get("title") if (parent or {}).get("type") == "department" else "Team"
        roster.append(
            {
                "org_node_id": str(n.get("id") or ""),
                "name": str((ag or {}).get("name") or n.get("title") or "Agent"),
                "role": str((ag or {}).get("role") or n.get("agent_role") or "specialist"),
                "department": str(dept or "Team"),
                "status": "waiting",
                "kind": "agent",
                "agent_id": str(n.get("agent_id") or ""),
                "last_post_at": None,
            }
        )
    return roster


def new_channel(
    goal: str,
    *,
    title: str = "",
    org_graph_id: str = "",
    org_name: str = "",
    mode: str = "pipeline",
    graph: dict[str, Any] | None = None,
    max_rounds: int = 12,
) -> dict[str, Any]:
    goal = (goal or "").strip()
    title = (title or goal[:60] or "Team goal").strip()
    ch: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "title": title,
        "goal": goal,
        "org_graph_id": org_graph_id,
        "org_name": org_name,
        "status": "open",
        "mode": mode if mode in ("pipeline", "coordinate") else "pipeline",
        "created_at": _now(),
        "updated_at": _now(),
        "messages": [],
        "roster": roster_from_graph(graph),
        "final_text": "",
        "living_plan": {"summary": "Waiting to start…", "steps": [], "updated_at": _now()},
        "settings": {"max_rounds": max(2, min(40, int(max_rounds or 12)))},
        "round": 0,
    }
    # System welcome
    append_message(
        ch,
        role="system",
        content=(
            f"Team channel opened for goal:\n{goal}\n\n"
            f"Org: {org_name or org_graph_id or 'default'} · Mode: {ch['mode']}"
        ),
        agent_name="System",
        save=False,
    )
    return save_channel(ch)


def append_message(
    ch: dict[str, Any],
    *,
    role: str,
    content: str,
    agent_name: str = "",
    agent_role: str = "",
    org_node_id: str = "",
    reply_to: str | None = None,
    mentions: list[str] | None = None,
    tools: list[Any] | None = None,
    round_n: int | None = None,
    save: bool = True,
) -> dict[str, Any]:
    msg = {
        "id": str(uuid.uuid4())[:12],
        "role": role,
        "agent_name": agent_name or role.title(),
        "agent_role": agent_role,
        "org_node_id": org_node_id or "",
        "content": content or "",
        "at": _now(),
        "reply_to": reply_to,
        "mentions": list(mentions or []),
        "tools": list(tools or []),
        "round": int(round_n if round_n is not None else ch.get("round") or 0),
    }
    ch.setdefault("messages", []).append(msg)
    # Update roster presence timestamp
    if org_node_id:
        for r in ch.get("roster") or []:
            if str(r.get("org_node_id") or "") == str(org_node_id):
                r["last_post_at"] = msg["at"]
                if r.get("status") == "working":
                    r["status"] = "done"
                break
    if save:
        save_channel(ch)
    return msg


def set_roster_status(
    ch: dict[str, Any],
    org_node_id: str,
    status: str,
    *,
    save: bool = True,
) -> None:
    status = (status or "waiting").lower()
    if status not in ("waiting", "working", "done", "failed", "blocked"):
        status = "waiting"
    for r in ch.get("roster") or []:
        if str(r.get("org_node_id") or "") == str(org_node_id):
            r["status"] = status
            break
    if save:
        save_channel(ch)


def set_channel_status(ch: dict[str, Any], status: str, *, save: bool = True) -> None:
    ch["status"] = status
    if save:
        save_channel(ch)


def clean_team_final_text(text: str) -> str:
    """
    One clean user-facing answer (Task #6).
    Strips FINAL: prefix, tool-log appendices, raw tool markup, status headers.
    """
    t = (text or "").strip()
    if not t:
        return ""
    # Drop leading markers
    t = re.sub(r"^\s*\*?\*?FINAL\s*(ANSWER)?\*?\*?\s*:?\s*", "", t, flags=re.I)
    t = re.sub(r"^\s*\*?\*?FINISHED\s+ANSWER\*?\*?\s*:?\s*", "", t, flags=re.I)
    # Drop "Tools used this turn" appendix (agent internal)
    t = re.split(r"\n###\s*Tools used this turn\b", t, maxsplit=1, flags=re.I)[0]
    t = re.split(r"\n##\s*Tools used\b", t, maxsplit=1, flags=re.I)[0]
    # Strip raw tool block markers
    t = re.sub(r"<<<\s*(TERMINAL|WEB_SEARCH|WEB_FETCH|GUI|TOOL)[^>]*>>>[\s\S]*?<<<\s*/\s*\1\s*>>>", "", t, flags=re.I)
    t = re.sub(r"<<<\s*(TERMINAL|WEB_SEARCH|WEB_FETCH|GUI|TOOL)[^>]*>>>", "", t, flags=re.I)
    # Collapse excess blank lines
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return t


def set_final(ch: dict[str, Any], text: str, *, save: bool = True) -> None:
    cleaned = clean_team_final_text(text)
    ch["final_text"] = cleaned
    ch["status"] = "done"
    # Mark living plan complete when we have a final
    lp = ch.get("living_plan")
    if isinstance(lp, dict) and cleaned:
        for step in lp.get("steps") or []:
            if isinstance(step, dict) and step.get("status") not in ("done", "failed", "skipped"):
                step["status"] = "done"
        lp["summary"] = "Complete — finished answer ready"
        lp["updated_at"] = _now()
        ch["living_plan"] = lp
    if save:
        save_channel(ch)


def init_living_plan(
    ch: dict[str, Any],
    steps: list[dict[str, Any]] | None = None,
    *,
    summary: str = "",
    save: bool = True,
) -> dict[str, Any]:
    """
    Living plan shown while team runs (Task #6).
    steps: [{id, title, owner?, status: pending|working|done|failed|skipped}]
    """
    out_steps: list[dict[str, Any]] = []
    for i, s in enumerate(steps or []):
        if not isinstance(s, dict):
            continue
        out_steps.append(
            {
                "id": str(s.get("id") or f"s{i+1}"),
                "title": str(s.get("title") or s.get("name") or f"Step {i+1}"),
                "owner": str(s.get("owner") or s.get("agent_name") or ""),
                "status": str(s.get("status") or "pending"),
            }
        )
    plan = {
        "summary": summary or "Team plan",
        "steps": out_steps,
        "updated_at": _now(),
    }
    ch["living_plan"] = plan
    if save:
        save_channel(ch)
    return plan


def update_living_plan_step(
    ch: dict[str, Any],
    *,
    step_id: str = "",
    owner: str = "",
    title: str = "",
    status: str = "working",
    summary: str = "",
    save: bool = True,
) -> dict[str, Any] | None:
    """Update a step by id, owner name, or title substring. Creates plan if missing."""
    status = (status or "pending").lower()
    if status not in ("pending", "working", "done", "failed", "skipped"):
        status = "working"
    lp = ch.get("living_plan")
    if not isinstance(lp, dict):
        lp = {"summary": "Team plan", "steps": [], "updated_at": _now()}
        ch["living_plan"] = lp
    steps = list(lp.get("steps") or [])
    hit = None
    sid = (step_id or "").strip()
    own = (owner or "").strip().lower()
    tit = (title or "").strip().lower()
    for s in steps:
        if not isinstance(s, dict):
            continue
        if sid and str(s.get("id") or "") == sid:
            hit = s
            break
        if own and own in str(s.get("owner") or "").lower():
            hit = s
            break
        if tit and tit in str(s.get("title") or "").lower():
            hit = s
            break
    if hit is None and (owner or title):
        hit = {
            "id": sid or f"s{len(steps)+1}",
            "title": title or owner or "Step",
            "owner": owner or "",
            "status": status,
        }
        steps.append(hit)
    if hit is not None:
        hit["status"] = status
        if owner:
            hit["owner"] = owner
        if title and not hit.get("title"):
            hit["title"] = title
    lp["steps"] = steps
    if summary:
        lp["summary"] = summary
    lp["updated_at"] = _now()
    ch["living_plan"] = lp
    if save:
        save_channel(ch)
    return lp


def format_living_plan(ch: dict[str, Any] | None) -> str:
    """Human-readable living plan for UI banner."""
    if not ch:
        return ""
    lp = ch.get("living_plan")
    if not isinstance(lp, dict):
        return ""
    marks = {
        "pending": "○",
        "working": "●",
        "done": "✓",
        "failed": "✗",
        "skipped": "–",
    }
    lines = [str(lp.get("summary") or "Team plan")]
    for s in lp.get("steps") or []:
        if not isinstance(s, dict):
            continue
        st = str(s.get("status") or "pending")
        m = marks.get(st, "○")
        own = str(s.get("owner") or "").strip()
        title = str(s.get("title") or "Step")
        tail = f" — {own}" if own else ""
        lines.append(f"{m} {title}{tail}")
    return "\n".join(lines)


def avatar_color(name: str) -> tuple[str, str]:
    """Stable light/dark pair for avatar from name hash."""
    palette = [
        ("#3b82f6", "#60a5fa"),
        ("#8b5cf6", "#a78bfa"),
        ("#ec4899", "#f472b6"),
        ("#14b8a6", "#2dd4bf"),
        ("#f59e0b", "#fbbf24"),
        ("#ef4444", "#f87171"),
        ("#22c55e", "#4ade80"),
        ("#6366f1", "#818cf8"),
    ]
    h = sum(ord(c) for c in (name or "?")) % len(palette)
    return palette[h]


def format_channel_transcript(ch: dict[str, Any], *, max_msgs: int = 40) -> str:
    """Text transcript for LLM coordination context."""
    lines = [
        f"## Team channel: {ch.get('title')}",
        f"Goal: {ch.get('goal')}",
        f"Status: {ch.get('status')} · Mode: {ch.get('mode')}",
        "",
        "### Messages",
    ]
    msgs = list(ch.get("messages") or [])[-max_msgs:]
    for m in msgs:
        who = m.get("agent_name") or m.get("role")
        role = m.get("agent_role") or m.get("role")
        body = (m.get("content") or "").strip()
        lines.append(f"**{who}** ({role}):\n{body}\n")
    return "\n".join(lines)
