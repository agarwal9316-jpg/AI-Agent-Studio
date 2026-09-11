"""
LLM-callable tools to create/edit the organisation tree when a task needs it.
"""

from __future__ import annotations

import json
import re
from typing import Any


def _get_wfg():
    """Lazy import to break circular dependency."""
    from app.services import workflow_graph as wfg
    return wfg

ORG_BLOCK_RE = re.compile(
    r"<<<ORG>>>\s*(.*?)\s*<<<END_ORG>>>",
    re.DOTALL | re.IGNORECASE,
)


def extract_org_commands(text: str) -> list[str]:
    return [m.group(1).strip() for m in ORG_BLOCK_RE.finditer(text or "") if m.group(1).strip()]


def org_tool_instructions() -> str:
    return """
## Organisation structure tools (you CAN create/edit the org when the task needs it)

Active org chart is used for multi-agent work. If the structure is wrong or incomplete for the user task, update it.

Emit one JSON action per block:

<<<ORG>>>
{"action": "list"}
<<<END_ORG>>>

<<<ORG>>>
{"action": "add_department", "title": "Marketing", "instructions": "Own campaigns"}
<<<END_ORG>>>

<<<ORG>>>
{"action": "assign_agent", "department": "Engineering", "name": "Coder", "role": "Engineer", "goal": "Implement", "llm_model": "openai/gpt-4o-mini", "llm_base_url": "", "llm_api_key": ""}
<<<END_ORG>>>

<<<ORG>>>
{"action": "assign_existing", "department": "Engineering", "agent_id": "paste-agent-uuid"}
<<<END_ORG>>>

<<<ORG>>>
{"action": "update_node", "node_id": "abc", "title": "New title", "instructions": "..."}
<<<END_ORG>>>

<<<ORG>>>
{"action": "delete_node", "node_id": "abc"}
<<<END_ORG>>>

<<<ORG>>>
{"action": "new_graph", "name": "Project Phoenix Org"}
<<<END_ORG>>>

Rules:
- Prefer editing the active graph over inventing shadow departments in prose only.
- After ORG changes, continue the user task using the updated structure.
- department can be title match (case-insensitive) or node id.
""".strip()


def run_org_command(body: str) -> dict[str, Any]:
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return {"ok": False, "error": "ORG body must be JSON"}

    if not isinstance(data, dict):
        return {"ok": False, "error": "ORG JSON must be an object"}

    action = (data.get("action") or "").strip().lower()
    g = _get_wfg().get_active_graph()

    try:
        if action == "list":
            return {
                "ok": True,
                "graph": g.get("name"),
                "tree": _get_wfg().tree_ascii(g),
                "nodes": [
                    {
                        "id": n.get("id"),
                        "type": n.get("type"),
                        "title": n.get("title"),
                        "parent_id": n.get("parent_id"),
                        "agent_id": n.get("agent_id"),
                    }
                    for n in _get_wfg().walk_tree(g)
                ],
            }

        if action == "add_department":
            title = data.get("title") or "Department"
            parent = data.get("parent_id") or data.get("parent")
            # resolve parent department by title
            parent_id = parent
            if parent and not wfg.get_node(g, str(parent)):
                for n in g.get("nodes") or []:
                    if n.get("type") == "department" and (n.get("title") or "").lower() == str(parent).lower():
                        parent_id = n["id"]
                        break
                else:
                    parent_id = None
            node = _get_wfg().add_department(
                g,
                title,
                parent_id=parent_id if parent_id else None,
                instructions=data.get("instructions") or "",
            )
            return {"ok": True, "node": node, "tree": _get_wfg().tree_ascii(_get_wfg().get_active_graph())}

        if action == "assign_agent":
            dept = data.get("department") or data.get("department_id") or ""
            dept_id = _resolve_dept(g, str(dept))
            if not dept_id:
                return {"ok": False, "error": f"Department not found: {dept}"}
            node = _get_wfg().assign_agent_to_department(
                g,
                dept_id,
                title=data.get("name") or data.get("title") or "Agent",
                role=data.get("role") or "Specialist",
                goal=data.get("goal") or "Complete assigned work",
                instructions=data.get("instructions") or "",
                llm_model=data.get("llm_model") or "",
                llm_base_url=data.get("llm_base_url") or "",
                llm_api_key=data.get("llm_api_key") or "",
                create_if_missing=True,
            )
            return {"ok": True, "node": node, "tree": _get_wfg().tree_ascii(_get_wfg().get_active_graph())}

        if action == "assign_existing":
            dept = data.get("department") or data.get("department_id") or ""
            dept_id = _resolve_dept(g, str(dept))
            aid = data.get("agent_id") or ""
            if not dept_id or not aid:
                return {"ok": False, "error": "Need department and agent_id"}
            node = _get_wfg().assign_agent_to_department(
                g, dept_id, agent_id=str(aid), create_if_missing=False
            )
            return {"ok": True, "node": node}

        if action == "update_node":
            nid = data.get("node_id") or data.get("id")
            if not nid:
                return {"ok": False, "error": "node_id required"}
            fields = {}
            for k in ("title", "instructions", "agent_role", "agent_goal", "agent_id"):
                if k in data and data[k] is not None:
                    fields[k] = data[k]
            node = _get_wfg().update_node(g, str(nid), **fields)
            return {"ok": True, "node": node, "tree": _get_wfg().tree_ascii(_get_wfg().get_active_graph())}

        if action == "delete_node":
            nid = data.get("node_id") or data.get("id")
            if not nid:
                return {"ok": False, "error": "node_id required"}
            _get_wfg().delete_node(g, str(nid))
            return {"ok": True, "tree": _get_wfg().tree_ascii(_get_wfg().get_active_graph())}

        if action == "new_graph":
            ng = _get_wfg().new_graph(data.get("name") or "Task org")
            return {"ok": True, "graph": ng, "tree": _get_wfg().tree_ascii(ng)}

        return {"ok": False, "error": f"Unknown action: {action}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def _resolve_dept(graph: dict[str, Any], dept: str) -> str | None:
    if not dept:
        return None
    wfg = _get_wfg()
    if wfg.get_node(graph, dept) and wfg.get_node(graph, dept).get("type") == "department":
        return dept
    for n in graph.get("nodes") or []:
        if n.get("type") == "department" and (n.get("title") or "").lower() == dept.lower():
            return n["id"]
    return None
