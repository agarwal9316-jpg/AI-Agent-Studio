"""
Organisation tree (like a real company org chart):

  CEO
  ├── Department (e.g. Engineering)
  │     ├── Agent (assigned AI employee)
  │     └── Agent
  └── Department (e.g. Product)
        └── Agent

Chat injects this tree so the LLM routes work through departments and agents.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.paths import company_dir
from app.core.services.data.storage import _read_json, _write_json, get_agent, list_agents, save_agent

# Primary types for org chart. "role"/"flow" kept for older saved graphs.
# "worker" is the unified AI-worker type (managers are workers with children).
NODE_TYPES = ("ceo", "department", "agent", "role", "flow", "worker")

# Sensible depth limit for hierarchy (CEO = 0).
MAX_ORG_DEPTH = 12

# Live execution status values for nodes (UI / Team roster).
WORKER_STATUSES = (
    "idle",
    "running",
    "thinking",
    "waiting",
    "delegating",
    "completed",
    "error",
    "disabled",
    "blocked",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _blank_worker_fields() -> dict[str, Any]:
    """Default fields for every AI worker / manager node."""
    return {
        "enabled": True,
        "status": "idle",
        "system_prompt": "",
        "worker_prompt": "",
        "llm_provider_id": "",  # empty = Default (global)
        "llm_model": "",  # empty = Default model
        "llm_base_url": "",  # empty = Default base URL
        "llm_api_key": "",  # empty = Default key (never export)
        "fallback_enabled": False,
        "fallback_provider_id": "",
        "fallback_model": "",
        "fallback_base_url": "",
        "fallback_api_key": "",
        "attachments": [],  # list of {path, name, type, size, status}
        "tool_permissions": {},  # optional per-worker tool allow map
        "temperature": None,  # None = default
        "top_p": None,
        "max_tokens": None,
        "timeout_s": None,
        "retry_count": None,
    }


def normalize_node(node: dict[str, Any]) -> dict[str, Any]:
    """Ensure legacy nodes have AI-organisation fields."""
    if not isinstance(node, dict):
        return node
    defaults = _blank_worker_fields()
    for k, v in defaults.items():
        node.setdefault(k, v if not isinstance(v, (dict, list)) else type(v)())
    # Map legacy type "role" → agent; keep department/ceo
    if node.get("type") == "role":
        node["type"] = "agent"
    node.setdefault("agent_id", "")
    node.setdefault("agent_role", "")
    node.setdefault("agent_goal", "")
    node.setdefault("instructions", "")
    node.setdefault("order", 0)
    if node.get("enabled") is False:
        node["status"] = "disabled"
    return node


def normalize_graph(graph: dict[str, Any]) -> dict[str, Any]:
    for n in graph.get("nodes") or []:
        normalize_node(n)
    return graph


def graphs_path():
    return company_dir() / "workflow_graphs.json"


def _empty_store() -> dict[str, Any]:
    gid = str(uuid.uuid4())
    ceo_id = "ceo-root"
    return {
        "active_id": gid,
        "graphs": [
            {
                "id": gid,
                "name": "Company organisation",
                "created_at": _now(),
                "updated_at": _now(),
                "nodes": [
                    {
                        "id": ceo_id,
                        "type": "ceo",
                        "title": "CEO",
                        "parent_id": None,
                        "order": 0,
                        "instructions": (
                            "Lead the organisation. Route objectives to departments, "
                            "coordinate agents, synthesize the final answer for the user."
                        ),
                        "agent_id": "",
                    },
                    {
                        "id": "dept-product",
                        "type": "department",
                        "title": "Product",
                        "parent_id": ceo_id,
                        "order": 0,
                        "instructions": "Own requirements and product clarity.",
                        "agent_id": "",
                    },
                    {
                        "id": "dept-engineering",
                        "type": "department",
                        "title": "Engineering",
                        "parent_id": ceo_id,
                        "order": 1,
                        "instructions": "Own implementation and technical delivery.",
                        "agent_id": "",
                    },
                    {
                        "id": "dept-quality",
                        "type": "department",
                        "title": "Quality",
                        "parent_id": ceo_id,
                        "order": 2,
                        "instructions": "Own verification and risk reporting.",
                        "agent_id": "",
                    },
                ],
            }
        ],
    }


def load_store() -> dict[str, Any]:
    data = _read_json(graphs_path(), None)
    if isinstance(data, dict) and data.get("graphs"):
        data.setdefault("active_id", data["graphs"][0]["id"])
        # normalize legacy nodes
        for g in data["graphs"]:
            normalize_graph(g)
        return data
    store = _empty_store()
    save_store(store)
    return store


def save_store(store: dict[str, Any]) -> None:
    _write_json(graphs_path(), store)


def list_graphs() -> list[dict[str, Any]]:
    return list(load_store().get("graphs") or [])


def get_active_graph() -> dict[str, Any]:
    store = load_store()
    aid = store.get("active_id")
    for g in store.get("graphs") or []:
        if g.get("id") == aid:
            return g
    graphs = store.get("graphs") or []
    if graphs:
        store["active_id"] = graphs[0]["id"]
        save_store(store)
        return graphs[0]
    store = _empty_store()
    save_store(store)
    return store["graphs"][0]


def set_active_graph(graph_id: str) -> None:
    store = load_store()
    store["active_id"] = graph_id
    save_store(store)


def get_graph(graph_id: str | None) -> dict[str, Any] | None:
    """Return a graph by id, or None if missing."""
    if not graph_id:
        return None
    gid = str(graph_id).strip()
    for g in list_graphs():
        if str(g.get("id") or "") == gid:
            return g
    return None


def resolve_graph(
    graph: dict[str, Any] | None = None,
    graph_id: str | None = None,
) -> dict[str, Any]:
    """Prefer explicit graph, then graph_id, then active."""
    if graph and isinstance(graph, dict) and graph.get("nodes") is not None:
        return graph
    if graph_id:
        found = get_graph(graph_id)
        if found:
            return found
    return get_active_graph()


def rename_graph(graph_id: str, name: str) -> dict[str, Any] | None:
    g = get_graph(graph_id)
    if not g:
        return None
    g["name"] = (name or "").strip() or g.get("name") or "Organisation"
    return save_graph(g)


def duplicate_graph(graph_id: str, name: str = "") -> dict[str, Any] | None:
    g = get_graph(graph_id)
    if not g:
        return None
    import copy

    new_g = copy.deepcopy(g)
    new_g["id"] = str(uuid.uuid4())
    new_g["name"] = (name or "").strip() or f"{g.get('name') or 'Organisation'} (copy)"
    new_g["created_at"] = _now()
    new_g["updated_at"] = _now()
    # Keep node ids stable within the copy (independent graph)
    return save_graph(new_g)


def delete_graph(graph_id: str) -> bool:
    """Delete a chart. Refuses if it is the only remaining graph."""
    store = load_store()
    graphs = list(store.get("graphs") or [])
    if len(graphs) <= 1:
        return False
    gid = str(graph_id).strip()
    new_graphs = [g for g in graphs if str(g.get("id") or "") != gid]
    if len(new_graphs) == len(graphs):
        return False
    store["graphs"] = new_graphs
    if str(store.get("active_id") or "") == gid:
        store["active_id"] = new_graphs[0]["id"]
    save_store(store)
    return True


def save_graph(graph: dict[str, Any]) -> dict[str, Any]:
    store = load_store()
    graph["updated_at"] = _now()
    if not graph.get("id"):
        graph["id"] = str(uuid.uuid4())
        graph["created_at"] = _now()
        store.setdefault("graphs", []).append(graph)
    else:
        found = False
        for i, g in enumerate(store.get("graphs") or []):
            if g.get("id") == graph["id"]:
                store["graphs"][i] = graph
                found = True
                break
        if not found:
            store.setdefault("graphs", []).append(graph)
    save_store(store)
    return graph


def new_graph(name: str = "New organisation") -> dict[str, Any]:
    ceo_id = str(uuid.uuid4())[:8]
    g = {
        "id": str(uuid.uuid4()),
        "name": name.strip() or "New organisation",
        "created_at": _now(),
        "updated_at": _now(),
        "nodes": [
            {
                "id": ceo_id,
                "type": "ceo",
                "title": "CEO",
                "parent_id": None,
                "order": 0,
                "instructions": "Lead the organisation and coordinate departments.",
                "agent_id": "",
            }
        ],
    }
    save_graph(g)
    set_active_graph(g["id"])
    return g


def get_node(graph: dict[str, Any], node_id: str) -> dict[str, Any] | None:
    for n in graph.get("nodes") or []:
        if n.get("id") == node_id:
            return n
    return None


def _norm_parent_id(pid: Any) -> str | None:
    """Treat missing / blank parent as root (None)."""
    if pid is None:
        return None
    s = str(pid).strip()
    return s if s else None


def children_of(graph: dict[str, Any], parent_id: str | None) -> list[dict[str, Any]]:
    want = _norm_parent_id(parent_id)
    kids = [
        n
        for n in (graph.get("nodes") or [])
        if _norm_parent_id(n.get("parent_id")) == want
    ]
    kids.sort(key=lambda n: (n.get("order") or 0, n.get("title") or ""))
    return kids


def departments(graph: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    g = graph or get_active_graph()
    return [n for n in (g.get("nodes") or []) if n.get("type") == "department"]


def agents_in_department(graph: dict[str, Any], dept_id: str) -> list[dict[str, Any]]:
    return [
        n
        for n in children_of(graph, dept_id)
        if n.get("type") in ("agent", "role")
    ]


def add_department(
    graph: dict[str, Any],
    title: str,
    *,
    parent_id: str | None = None,
    instructions: str = "",
) -> dict[str, Any]:
    """Create a department under CEO (or under another department if parent set)."""
    if parent_id is None:
        ceo = next((n for n in graph.get("nodes") or [] if n.get("type") == "ceo"), None)
        parent_id = ceo["id"] if ceo else None
    kids = children_of(graph, parent_id)
    node = {
        "id": str(uuid.uuid4())[:10],
        "type": "department",
        "title": title.strip() or "Department",
        "parent_id": parent_id,
        "order": len(kids),
        "instructions": instructions.strip()
        or f"Department: {title}. Coordinate assigned agents.",
        "agent_id": "",
    }
    graph.setdefault("nodes", []).append(node)
    save_graph(graph)
    return node


def assign_agent_to_department(
    graph: dict[str, Any],
    department_id: str,
    *,
    agent_id: str = "",
    title: str = "",
    role: str = "",
    goal: str = "",
    instructions: str = "",
    llm_model: str = "",
    llm_base_url: str = "",
    llm_api_key: str = "",
    create_if_missing: bool = True,
) -> dict[str, Any]:
    """
    Assign an AI agent under a department (legacy API).
    Prefer add_ai_worker() for unlimited-depth hierarchy.
    """
    return add_ai_worker(
        graph,
        parent_id=department_id,
        agent_id=agent_id,
        title=title,
        role=role,
        goal=goal,
        instructions=instructions,
        llm_model=llm_model,
        llm_base_url=llm_base_url,
        llm_api_key=llm_api_key,
        create_if_missing=create_if_missing,
        as_department_child=True,
    )


def node_depth(graph: dict[str, Any], node_id: str | None) -> int:
    """Depth from root (CEO = 0). Missing node → 0."""
    if not node_id:
        return 0
    depth = 0
    seen: set[str] = set()
    cur = get_node(graph, node_id)
    while cur and cur.get("parent_id"):
        pid = str(cur.get("parent_id") or "")
        if not pid or pid in seen:
            break
        seen.add(pid)
        depth += 1
        cur = get_node(graph, pid)
        if depth > MAX_ORG_DEPTH + 2:
            break
    return depth


def ancestors_of(graph: dict[str, Any], node_id: str) -> list[str]:
    """Parent chain from immediate parent up to root (ids)."""
    out: list[str] = []
    seen: set[str] = set()
    cur = get_node(graph, node_id)
    while cur and cur.get("parent_id"):
        pid = str(cur.get("parent_id") or "")
        if not pid or pid in seen:
            break
        seen.add(pid)
        out.append(pid)
        cur = get_node(graph, pid)
    return out


def descendants_of(graph: dict[str, Any], node_id: str) -> list[str]:
    """All descendant node ids (not including self)."""
    out: list[str] = []

    def collect(pid: str) -> None:
        for c in children_of(graph, pid):
            cid = str(c.get("id") or "")
            if cid:
                out.append(cid)
                collect(cid)

    collect(node_id)
    return out


def would_create_cycle(graph: dict[str, Any], node_id: str, new_parent_id: str | None) -> bool:
    """True if moving node under new_parent would create a circular hierarchy."""
    if not new_parent_id:
        return False
    if str(node_id) == str(new_parent_id):
        return True
    # new parent must not be a descendant of node
    return str(new_parent_id) in set(descendants_of(graph, node_id))


def is_manager(graph: dict[str, Any], node_id: str) -> bool:
    """Any node with subordinate workers acts as a manager."""
    return len(children_of(graph, node_id)) > 0


def add_ai_worker(
    graph: dict[str, Any],
    *,
    parent_id: str | None = None,
    agent_id: str = "",
    title: str = "",
    role: str = "",
    goal: str = "",
    instructions: str = "",
    system_prompt: str = "",
    worker_prompt: str = "",
    llm_model: str = "",
    llm_base_url: str = "",
    llm_api_key: str = "",
    llm_provider_id: str = "",
    create_if_missing: bool = True,
    as_department_child: bool = False,
    ntype: str = "agent",
) -> dict[str, Any]:
    """
    Create an AI Worker under any parent (CEO, department, manager, or worker).

    This is the primary hierarchy API for the AI Organisation upgrade.
    Parent defaults to CEO when omitted.
    """
    normalize_graph(graph)
    if parent_id is None:
        ceo = next((n for n in graph.get("nodes") or [] if n.get("type") == "ceo"), None)
        parent_id = ceo["id"] if ceo else None
    if parent_id is not None and not get_node(graph, parent_id):
        raise ValueError("parent_id not found in organisation")
    if parent_id is not None and node_depth(graph, parent_id) >= MAX_ORG_DEPTH:
        raise ValueError(f"Maximum organisation depth ({MAX_ORG_DEPTH}) reached")

    # Legacy path required department parent — still allow for assign_agent_to_department
    if as_department_child:
        parent = get_node(graph, parent_id) if parent_id else None
        if not parent or parent.get("type") not in ("department", "ceo", "agent", "worker", "role"):
            # Soft: allow any existing parent; only reject missing
            if parent is None:
                raise ValueError("parent_id must be an existing organisation node")

    profile: dict[str, Any] | None = None
    if agent_id:
        profile = get_agent(agent_id)
        if profile and (llm_model or llm_base_url or llm_api_key or system_prompt or worker_prompt):
            if llm_model:
                profile["llm_model"] = llm_model.strip()
            if llm_base_url:
                profile["llm_base_url"] = llm_base_url.strip()
            if llm_api_key:
                profile["llm_api_key"] = llm_api_key.strip()
            if system_prompt:
                profile["system_prompt"] = system_prompt.strip()
            if worker_prompt:
                profile["worker_prompt"] = worker_prompt.strip()
            if role:
                profile["role"] = role.strip()
            if goal:
                profile["goal"] = goal.strip()
            profile = save_agent(profile)
    if profile is None and create_if_missing:
        profile = save_agent(
            {
                "name": title.strip() or "AI Worker",
                "role": role.strip() or "Specialist",
                "goal": goal.strip() or instructions.strip() or "Complete assigned work",
                "backstory": instructions.strip() or worker_prompt.strip(),
                "system_prompt": system_prompt.strip(),
                "worker_prompt": worker_prompt.strip()
                or role.strip()
                or "You are an AI worker. Complete assignments carefully and report upward.",
                "llm_model": llm_model.strip(),
                "llm_base_url": llm_base_url.strip(),
                "llm_api_key": llm_api_key.strip(),
                "llm_provider_id": llm_provider_id.strip(),
            }
        )
        agent_id = profile["id"]
    elif profile is None:
        raise ValueError("agent_id not found and create_if_missing is False")

    kids = children_of(graph, parent_id)
    display = (
        (profile or {}).get("name")
        or (profile or {}).get("role")
        or title
        or "AI Worker"
    )
    node: dict[str, Any] = {
        "id": str(uuid.uuid4())[:10],
        "type": ntype if ntype in NODE_TYPES and ntype != "ceo" else "agent",
        "title": display,
        "parent_id": parent_id,
        "order": len(kids),
        "instructions": instructions.strip()
        or (
            f"Role: {(profile or {}).get('role')}. Goal: {(profile or {}).get('goal')}. "
            f"{(profile or {}).get('backstory') or ''}"
        ).strip(),
        "agent_id": agent_id,
        "agent_role": (profile or {}).get("role") or role or "",
        "agent_goal": (profile or {}).get("goal") or goal or "",
        "system_prompt": system_prompt
        or (profile or {}).get("system_prompt")
        or "",
        "worker_prompt": worker_prompt
        or (profile or {}).get("worker_prompt")
        or "",
        "llm_model": llm_model or (profile or {}).get("llm_model") or "",
        "llm_base_url": llm_base_url or (profile or {}).get("llm_base_url") or "",
        "llm_provider_id": llm_provider_id or (profile or {}).get("llm_provider_id") or "",
    }
    # Do not store raw API key on graph node (keep on agent profile only)
    node.update({k: v for k, v in _blank_worker_fields().items() if k not in node})
    if llm_api_key and profile:
        # already saved on profile above
        pass
    normalize_node(node)
    graph.setdefault("nodes", []).append(node)
    save_graph(graph)
    return node


def add_node(
    graph: dict[str, Any],
    *,
    parent_id: str | None,
    ntype: str,
    title: str,
    instructions: str = "",
    agent_id: str = "",
) -> dict[str, Any]:
    """Generic add. Prefer add_department / add_ai_worker."""
    if ntype == "department":
        return add_department(graph, title, parent_id=parent_id, instructions=instructions)
    if ntype in ("agent", "role", "worker"):
        if not parent_id:
            raise ValueError("AI Workers must be placed under a parent (CEO / manager / department)")
        return add_ai_worker(
            graph,
            parent_id=parent_id,
            agent_id=agent_id,
            title=title,
            instructions=instructions,
            ntype="agent" if ntype == "role" else ntype,
        )
    if ntype == "ceo":
        parent_id = None
        for n in graph.get("nodes") or []:
            if n.get("type") == "ceo":
                n["title"] = title or n.get("title")
                if instructions:
                    n["instructions"] = instructions
                save_graph(graph)
                return n
    kids = children_of(graph, parent_id)
    node = {
        "id": str(uuid.uuid4())[:10],
        "type": ntype if ntype in NODE_TYPES else "agent",
        "title": title.strip() or ntype.title(),
        "parent_id": parent_id,
        "order": len(kids),
        "instructions": instructions.strip(),
        "agent_id": agent_id,
    }
    node.update({k: v for k, v in _blank_worker_fields().items() if k not in node})
    normalize_node(node)
    graph.setdefault("nodes", []).append(node)
    save_graph(graph)
    return node


_UPDATABLE_NODE_FIELDS = frozenset(
    {
        "title",
        "instructions",
        "type",
        "order",
        "parent_id",
        "agent_id",
        "agent_role",
        "agent_goal",
        "enabled",
        "status",
        "system_prompt",
        "worker_prompt",
        "llm_provider_id",
        "llm_model",
        "llm_base_url",
        "fallback_enabled",
        "fallback_provider_id",
        "fallback_model",
        "fallback_base_url",
        "attachments",
        "tool_permissions",
        "temperature",
        "top_p",
        "max_tokens",
        "timeout_s",
        "retry_count",
    }
)


def update_node(graph: dict[str, Any], node_id: str, **fields: Any) -> dict[str, Any] | None:
    node = get_node(graph, node_id)
    if not node:
        return None
    # Circular hierarchy protection on reparent
    if "parent_id" in fields and fields["parent_id"] is not None:
        new_pid = fields["parent_id"]
        if would_create_cycle(graph, node_id, str(new_pid) if new_pid else None):
            raise ValueError("Cannot reparent: would create a circular hierarchy")
        if new_pid and node_depth(graph, str(new_pid)) >= MAX_ORG_DEPTH:
            raise ValueError(f"Cannot reparent: maximum depth ({MAX_ORG_DEPTH}) exceeded")
    for k, v in fields.items():
        if k in _UPDATABLE_NODE_FIELDS and v is not None:
            node[k] = v
        elif k == "llm_api_key" and v is not None:
            # Store on linked agent only — never plain on shared graph export paths
            pass
    # sync linked agent profile if present
    aid = node.get("agent_id")
    if aid and any(
        k in fields
        for k in (
            "title",
            "agent_role",
            "agent_goal",
            "instructions",
            "system_prompt",
            "worker_prompt",
            "llm_model",
            "llm_base_url",
            "llm_provider_id",
            "llm_api_key",
        )
    ):
        ag = get_agent(aid)
        if ag:
            if fields.get("title"):
                ag["name"] = fields["title"]
            if fields.get("agent_role") is not None:
                ag["role"] = fields["agent_role"]
            if fields.get("agent_goal") is not None:
                ag["goal"] = fields["agent_goal"]
            if fields.get("instructions") is not None:
                ag["backstory"] = fields["instructions"]
            if fields.get("system_prompt") is not None:
                ag["system_prompt"] = fields["system_prompt"]
            if fields.get("worker_prompt") is not None:
                ag["worker_prompt"] = fields["worker_prompt"]
            if fields.get("llm_model") is not None:
                ag["llm_model"] = fields["llm_model"]
            if fields.get("llm_base_url") is not None:
                ag["llm_base_url"] = fields["llm_base_url"]
            if fields.get("llm_provider_id") is not None:
                ag["llm_provider_id"] = fields["llm_provider_id"]
            if fields.get("llm_api_key"):
                ag["llm_api_key"] = fields["llm_api_key"]
            save_agent(ag)
    if fields.get("enabled") is False:
        node["status"] = "disabled"
    elif fields.get("enabled") is True and node.get("status") == "disabled":
        node["status"] = "idle"
    normalize_node(node)
    save_graph(graph)
    return node


def reparent_node(
    graph: dict[str, Any],
    node_id: str,
    new_parent_id: str | None,
) -> dict[str, Any]:
    """Move a worker under a new parent. Raises on cycle / CEO / missing."""
    node = get_node(graph, node_id)
    if not node:
        raise ValueError("Worker not found")
    if node.get("type") == "ceo":
        raise ValueError("CEO root cannot be reparented")
    if new_parent_id and not get_node(graph, new_parent_id):
        raise ValueError("New parent not found")
    if would_create_cycle(graph, node_id, new_parent_id):
        raise ValueError("Cannot move worker: would create a circular hierarchy")
    kids = children_of(graph, new_parent_id)
    node["parent_id"] = new_parent_id
    node["order"] = len(kids)
    save_graph(graph)
    return node


def duplicate_worker(graph: dict[str, Any], node_id: str) -> dict[str, Any]:
    """
    Duplicate a worker (and not its children). New unique IDs.
    Copies config/prompts; does NOT copy API keys or execution history.
    """
    import copy

    src = get_node(graph, node_id)
    if not src:
        raise ValueError("Worker not found")
    if src.get("type") == "ceo":
        raise ValueError("Cannot duplicate CEO root — use Copy organisation instead")
    node = copy.deepcopy(src)
    node["id"] = str(uuid.uuid4())[:10]
    node["title"] = f"{src.get('title') or 'Worker'} (copy)"
    node["status"] = "idle"
    # Place as sibling under same parent
    parent_id = src.get("parent_id")
    kids = children_of(graph, parent_id)
    node["order"] = len(kids)
    node["parent_id"] = parent_id
    # New agent profile without API key
    old_aid = str(src.get("agent_id") or "")
    old_ag = get_agent(old_aid) if old_aid else None
    new_ag = save_agent(
        {
            "name": node["title"],
            "role": (old_ag or {}).get("role") or src.get("agent_role") or "Specialist",
            "goal": (old_ag or {}).get("goal") or src.get("agent_goal") or "",
            "backstory": (old_ag or {}).get("backstory") or src.get("instructions") or "",
            "system_prompt": (old_ag or {}).get("system_prompt") or src.get("system_prompt") or "",
            "worker_prompt": (old_ag or {}).get("worker_prompt") or src.get("worker_prompt") or "",
            "llm_model": (old_ag or {}).get("llm_model") or src.get("llm_model") or "",
            "llm_base_url": (old_ag or {}).get("llm_base_url") or src.get("llm_base_url") or "",
            "llm_provider_id": (old_ag or {}).get("llm_provider_id")
            or src.get("llm_provider_id")
            or "",
            "llm_api_key": "",  # never copy secrets
            "tool_permissions": dict((old_ag or {}).get("tool_permissions") or {}),
        }
    )
    node["agent_id"] = new_ag["id"]
    node["llm_api_key"] = ""
    node["fallback_api_key"] = ""
    normalize_node(node)
    graph.setdefault("nodes", []).append(node)
    save_graph(graph)
    return node


def delete_node(
    graph: dict[str, Any],
    node_id: str,
    *,
    children_mode: str = "delete",
    reassign_to: str | None = None,
) -> dict[str, Any]:
    """
    Remove a worker from the hierarchy.

    children_mode:
      - delete: remove worker and all descendants
      - promote: reparent children to this node's parent
      - reassign: reparent children to reassign_to

    Never deletes CEO. Never deletes shared agent credentials/files.
    Returns {ok, removed_ids, error?}.
    """
    node = get_node(graph, node_id)
    if not node:
        return {"ok": False, "error": "Worker not found", "removed_ids": []}
    if node.get("type") == "ceo":
        return {"ok": False, "error": "CEO root cannot be deleted", "removed_ids": []}

    kids = children_of(graph, node_id)
    removed: list[str] = []

    if kids and children_mode == "promote":
        new_parent = node.get("parent_id")
        for c in kids:
            if would_create_cycle(graph, str(c["id"]), new_parent):
                return {
                    "ok": False,
                    "error": "Cannot promote children: cycle detected",
                    "removed_ids": [],
                }
            c["parent_id"] = new_parent
    elif kids and children_mode == "reassign":
        if not reassign_to or not get_node(graph, reassign_to):
            return {
                "ok": False,
                "error": "reassign_to must be a valid worker id",
                "removed_ids": [],
            }
        if str(reassign_to) == str(node_id) or would_create_cycle(graph, reassign_to, None):
            pass
        for c in kids:
            if would_create_cycle(graph, str(c["id"]), reassign_to) or str(c["id"]) == str(
                reassign_to
            ):
                return {
                    "ok": False,
                    "error": f"Cannot reassign child {c.get('title')} under target",
                    "removed_ids": [],
                }
            c["parent_id"] = reassign_to
    else:
        # delete subtree
        to_del = {node_id}
        for d in descendants_of(graph, node_id):
            to_del.add(d)
        removed = list(to_del)
        graph["nodes"] = [n for n in graph.get("nodes") or [] if n.get("id") not in to_del]
        save_graph(graph)
        return {"ok": True, "removed_ids": removed, "mode": "delete"}

    # promote / reassign: remove only this node
    graph["nodes"] = [n for n in graph.get("nodes") or [] if n.get("id") != node_id]
    removed = [node_id]
    save_graph(graph)
    return {"ok": True, "removed_ids": removed, "mode": children_mode}


def set_worker_status(graph: dict[str, Any], node_id: str, status: str) -> None:
    """Update live status for Team execution map."""
    node = get_node(graph, node_id)
    if not node:
        return
    st = (status or "idle").lower()
    if st not in WORKER_STATUSES:
        st = "idle"
    if node.get("enabled") is False:
        st = "disabled"
    node["status"] = st
    save_graph(graph)


def search_workers(
    graph: dict[str, Any],
    query: str,
) -> list[dict[str, Any]]:
    """Search workers by name, role, model, provider, status, goal."""
    q = (query or "").strip().lower()
    if not q:
        return walk_tree(graph)
    hits: list[dict[str, Any]] = []
    for n in walk_tree(graph):
        blob = " ".join(
            str(x or "")
            for x in (
                n.get("title"),
                n.get("type"),
                n.get("agent_role"),
                n.get("_agent_role"),
                n.get("agent_goal"),
                n.get("_agent_goal"),
                n.get("llm_model"),
                n.get("llm_provider_id"),
                n.get("status"),
                n.get("instructions"),
                n.get("worker_prompt"),
            )
        ).lower()
        if q in blob:
            hits.append(n)
    return hits


def export_graph_safe(graph: dict[str, Any]) -> dict[str, Any]:
    """Export hierarchy without API keys / secrets."""
    import copy

    g = copy.deepcopy(graph)
    for n in g.get("nodes") or []:
        n.pop("llm_api_key", None)
        n.pop("fallback_api_key", None)
        if isinstance(n.get("attachments"), list):
            for a in n["attachments"]:
                if isinstance(a, dict):
                    a.pop("content", None)
    return g


def import_graph_safe(
    payload: dict[str, Any],
    *,
    name: str = "",
    make_active: bool = True,
) -> dict[str, Any]:
    """Import a hierarchy export (no secrets expected)."""
    import copy

    nodes = payload.get("nodes") if isinstance(payload, dict) else None
    if not isinstance(nodes, list) or not nodes:
        raise ValueError("Import requires a graph with nodes")
    g = {
        "id": str(uuid.uuid4()),
        "name": (name or payload.get("name") or "Imported organisation").strip(),
        "created_at": _now(),
        "updated_at": _now(),
        "nodes": copy.deepcopy(nodes),
    }
    for n in g["nodes"]:
        n.pop("llm_api_key", None)
        n.pop("fallback_api_key", None)
        normalize_node(n)
    # Ensure at least one CEO
    if not any(n.get("type") == "ceo" for n in g["nodes"]):
        ceo_id = str(uuid.uuid4())[:8]
        g["nodes"].insert(
            0,
            normalize_node(
                {
                    "id": ceo_id,
                    "type": "ceo",
                    "title": "CEO",
                    "parent_id": None,
                    "order": 0,
                    "instructions": "Lead the organisation.",
                    "agent_id": "",
                }
            ),
        )
    save_graph(g)
    if make_active:
        set_active_graph(g["id"])
    return g


def walk_tree(graph: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Full organisation tree as a flat ordered list (depth-first).
    Includes every node: roots, children, and any orphaned nodes at the end.
    Each item has _depth, _is_manager, _status, optional _agent_* enrichments.
    """
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _enrich(n: dict[str, Any], depth: int) -> dict[str, Any]:
        item = dict(n)
        nid = str(item.get("id") or "")
        item["_depth"] = depth
        item["_is_manager"] = bool(nid and children_of(graph, nid))
        if item.get("agent_id"):
            ag = get_agent(item["agent_id"])
            if ag:
                item["_agent_name"] = ag.get("name")
                item["_agent_role"] = ag.get("role")
                item["_agent_goal"] = ag.get("goal")
                item["_llm_model"] = ag.get("llm_model") or item.get("llm_model") or ""
        status = item.get("status") or "idle"
        if item.get("enabled") is False:
            status = "disabled"
        item["_status"] = status
        return item

    def dfs(pid: str | None, depth: int) -> None:
        for n in children_of(graph, pid):
            nid = str(n.get("id") or "")
            if not nid or nid in seen:
                continue
            seen.add(nid)
            out.append(_enrich(n, depth))
            if depth < MAX_ORG_DEPTH + 1:
                dfs(nid, depth + 1)

    # Prefer CEO roots first, then any other root (parent None / blank)
    roots = children_of(graph, None)
    if not roots:
        # CEO with non-null parent_id edge case — still surface it
        for n in graph.get("nodes") or []:
            if n.get("type") == "ceo":
                roots = [n]
                break
    # CEO first among roots
    roots = sorted(
        roots,
        key=lambda n: (0 if n.get("type") == "ceo" else 1, n.get("order") or 0, n.get("title") or ""),
    )
    for r in roots:
        nid = str(r.get("id") or "")
        if not nid or nid in seen:
            continue
        seen.add(nid)
        out.append(_enrich(r, 0))
        dfs(nid, 1)

    # Orphans / broken parent links — list all remaining so nothing is missing
    for n in graph.get("nodes") or []:
        nid = str(n.get("id") or "")
        if not nid or nid in seen:
            continue
        seen.add(nid)
        item = _enrich(n, 0)
        item["_orphan"] = True
        out.append(item)
        dfs(nid, 1)
    return out


def tree_ascii(graph: dict[str, Any]) -> str:
    lines = [
        f"Organisation: {graph.get('name')}",
        "(CEO → Managers / Departments → AI Workers — unlimited depth)",
    ]
    for n in walk_tree(graph):
        d = int(n.get("_depth") or 0)
        pad = "│  " * d
        t = n.get("type")
        if t == "ceo":
            icon = "👑 CEO"
        elif t == "department":
            icon = "🏢 DEPT"
        elif n.get("_is_manager") and t in ("agent", "role", "worker"):
            icon = "📋 MGR"
        elif t in ("agent", "role", "worker"):
            icon = "👤 WORKER"
        else:
            icon = f"• {t}"
        extra = ""
        if n.get("_agent_role"):
            extra = f" | role={n.get('_agent_role')}"
        elif n.get("agent_role"):
            extra = f" | role={n.get('agent_role')}"
        st = n.get("_status") or n.get("status")
        if st and st != "idle":
            extra += f" | status={st}"
        if n.get("enabled") is False:
            extra += " | DISABLED"
        if n.get("agent_id"):
            extra += f" | agent_id={str(n.get('agent_id'))[:8]}"
            ag = get_agent(n["agent_id"])
            if ag and (ag.get("llm_model") or ag.get("llm_base_url")):
                extra += f" | llm={ag.get('llm_model') or 'Default'}"
            elif n.get("llm_model"):
                extra += f" | llm={n.get('llm_model')}"
            else:
                extra += " | llm=Default"
        lines.append(f"{pad}├─ {icon}: {n.get('title')}{extra}")
        prompt = n.get("worker_prompt") or n.get("instructions") or ""
        if prompt:
            lines.append(f"{pad}│     role_prompt: {str(prompt)[:100]}")
    return "\n".join(lines)


def workflow_prompt_for_llm(graph: dict[str, Any] | None = None) -> str:
    g = graph or get_active_graph()
    lines = [
        "## Organisation structure (USER-DEFINED ORG CHART — FOLLOW THIS)",
        f"Company graph: {g.get('name')}",
        "This is a teams organisational structure: CEO leads Departments; Agents work inside Departments.",
        "When the user gives a task in chat:",
        "1. CEO understands and routes work to the right department(s).",
        "2. Each department's assigned agents execute their part (in tree order).",
        "3. CEO synthesizes a final answer for the user.",
        "Do not invent departments or agents that are not in the chart.",
        "",
        "```",
        tree_ascii(g),
        "```",
        "",
        "### People / agents detail",
    ]
    for n in walk_tree(g):
        if n.get("type") not in ("agent", "role", "ceo"):
            if n.get("type") == "department":
                lines.append(
                    f"- **Department {n.get('title')}**: {n.get('instructions') or ''}"
                )
            continue
        ag = get_agent(n.get("agent_id") or "") if n.get("agent_id") else None
        role = (ag or {}).get("role") or n.get("agent_role") or n.get("type")
        goal = (ag or {}).get("goal") or n.get("agent_goal") or ""
        from app.core.services.data.storage import resolve_agent_llm

        llm = resolve_agent_llm(ag)
        sp = ((ag or {}).get("system_prompt") or "")[:120]
        lines.append(
            f"- **{n.get('title')}** ({n.get('type')}) dept_parent={n.get('parent_id')} "
            f"role={role} goal={goal} "
            f"LLM model=`{llm['model']}` base=`{llm['base_url']}` "
            f"system_prompt_set={'yes' if sp else 'no'} "
            f"— {n.get('instructions') or ''}"
        )
        if sp:
            lines.append(f"  system_prompt preview: {sp}…")
    lines.append(
        "\nMulti-agent rule: when executing via org workflow, each agent runs with "
        "**its own** LLM model/base_url/key (if set); otherwise global Settings defaults."
    )
    return "\n".join(lines)


def expand_to_company_tasks(
    user_objective: str,
    *,
    graph: dict[str, Any] | None = None,
    project_id: str = "",
    goal_id: str = "",
    force_auto_approve: bool = False,
) -> list[dict[str, Any]]:
    """
    Queue one work task per org agent (tree order) + CEO synthesis last.

    CEO task starts as status=blocked with depends_on = all agent task ids
    so it cannot run until every agent has finished.
    """
    from app.services import company_store as company

    g = graph or get_active_graph()
    created: list[dict[str, Any]] = []
    agent_task_ids: list[str] = []
    dept_name = {}
    for n in g.get("nodes") or []:
        if n.get("type") == "department":
            dept_name[n["id"]] = n.get("title") or "Department"

    auto = force_auto_approve or company.get_approval_mode() == "auto"

    def _make_agent_task(
        *,
        title: str,
        desc: str,
        role_id: str,
        agent_id: str = "",
        org_node_id: str = "",
        ag: dict[str, Any] | None = None,
        agent_name: str = "",
        agent_role: str = "",
        agent_goal: str = "",
    ) -> dict[str, Any]:
        task = company.new_work_task(
            title,
            goal_id=goal_id,
            role_id=role_id,
            description=desc,
            project_id=project_id,
        )
        task["agent_id"] = agent_id
        task["org_node_id"] = org_node_id
        task["depends_on"] = []
        if ag:
            task["llm_model"] = ag.get("llm_model") or ""
            task["llm_base_url"] = ag.get("llm_base_url") or ""
            task["llm_api_key"] = ag.get("llm_api_key") or ""
            task["agent_name"] = ag.get("name") or agent_name or title
            task["agent_role"] = ag.get("role") or agent_role
            task["agent_goal"] = ag.get("goal") or agent_goal
        else:
            task["agent_name"] = agent_name or title
            task["agent_role"] = agent_role
            task["agent_goal"] = agent_goal
        if auto:
            task["auto_approved"] = True
            task["status"] = "queued"
        # Exclusive pipeline holds these until run_task_now
        task["pipeline"] = "org"
        company.save_work_task(task)
        return task

    for n in walk_tree(g):
        # Any executable AI worker seat (agent / role / worker). Departments are
        # structural unless they have a linked agent_id.
        t = n.get("type")
        if t not in ("agent", "role", "worker"):
            continue
        if n.get("enabled") is False:
            continue
        parent = n.get("parent_id") or ""
        dname = dept_name.get(parent, "")
        if not dname:
            # walk up for nearest department title, else manager title
            p = get_node(g, parent) if parent else None
            while p and p.get("type") != "department":
                pid = p.get("parent_id")
                p = get_node(g, pid) if pid else None
            dname = (p.get("title") if p else None) or "Organisation"
        ag = get_agent(n.get("agent_id") or "") if n.get("agent_id") else None
        title = f"[{dname}] {n.get('title')}"
        worker_prompt = (
            (ag or {}).get("worker_prompt")
            or n.get("worker_prompt")
            or n.get("instructions")
            or ""
        )
        system_prompt = (ag or {}).get("system_prompt") or n.get("system_prompt") or ""
        desc = (
            f"Objective: {user_objective}\n"
            f"Department: {dname}\n"
            f"Worker: {n.get('title')}\n"
            f"Role: {(ag or {}).get('role') or n.get('agent_role') or ''}\n"
            f"Goal: {(ag or {}).get('goal') or n.get('agent_goal') or ''}\n"
            f"System Prompt: {system_prompt}\n"
            f"Worker Prompt: {worker_prompt}\n"
            f"Instructions: {n.get('instructions') or ''}\n"
            f"Is Manager: {bool(n.get('_is_manager'))}\n"
        )
        role_id = "engineer"
        blob = f"{n.get('title')} {(ag or {}).get('role') or ''}".lower()
        if "pm" in blob or "product" in blob:
            role_id = "pm"
        elif "qa" in blob or "test" in blob or "quality" in blob:
            role_id = "qa"
        elif "research" in blob:
            role_id = "researcher"
        task = _make_agent_task(
            title=title,
            desc=desc,
            role_id=role_id,
            agent_id=n.get("agent_id") or "",
            org_node_id=n.get("id") or "",
            ag=ag,
        )
        agent_task_ids.append(task["id"])
        created.append(task)

    # Fallback when org has departments but no agent seats
    if not agent_task_ids:
        fallback = [
            ("pm", "Product", "Clarify requirements and acceptance criteria"),
            ("engineer", "Engineering", "Technical plan and implementation notes"),
            ("qa", "Quality", "Risks, tests, and verification checklist"),
        ]
        for role_id, dname, instructions in fallback:
            title = f"[{dname}] {role_id.upper()} specialist"
            desc = (
                f"Objective: {user_objective}\n"
                f"Department: {dname}\n"
                f"Role: {role_id}\n"
                f"Instructions: {instructions}\n"
            )
            task = _make_agent_task(
                title=title,
                desc=desc,
                role_id=role_id,
                agent_name=f"{dname} {role_id}",
                agent_role=role_id,
            )
            agent_task_ids.append(task["id"])
            created.append(task)

    ceo = next((n for n in g.get("nodes") or [] if n.get("type") == "ceo"), None)
    ceo_title = (ceo or {}).get("title") or "CEO"
    ceo_instr = (ceo or {}).get("instructions") or ""
    task = company.new_work_task(
        f"[CEO] Synthesize for user",
        goal_id=goal_id,
        role_id="ceo",
        description=(
            f"Objective: {user_objective}\n"
            f"CEO ({ceo_title}) instructions: {ceo_instr}\n"
            "Synthesize ALL department/agent outputs into one final answer for the user.\n"
            "You must not invent missing agent work — use the handoff pack provided at run time.\n"
        ),
        project_id=project_id,
    )
    # Hard block until every agent task is done
    task["depends_on"] = list(agent_task_ids)
    task["status"] = "blocked"
    task["pipeline"] = "org"
    task["agent_name"] = "CEO"
    task["agent_role"] = "ceo"
    if auto:
        task["auto_approved"] = True
    company.save_work_task(task)
    created.append(task)
    return created
