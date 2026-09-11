"""Richer flow canvas model (nodes + edges) on top of workflow_graph.

Persists layout/extra edges on each organisation graph under ``flow_canvas``.
Uses only stdlib + existing workflow store — no Electron / Langflow deps.
Soft-degrades: missing canvas key → auto-layout from parent_id tree.
"""

from __future__ import annotations

import copy
import uuid
from typing import Any

FLOW_CANVAS_KEY = "flow_canvas"
FLOW_CANVAS_VERSION = 1

# Default card size used by layout + UI (logical units, pre-zoom)
NODE_W = 160
NODE_H = 72
H_GAP = 48
V_GAP = 56
ORIGIN_X = 80
ORIGIN_Y = 60


def empty_canvas_state() -> dict[str, Any]:
    return {
        "version": FLOW_CANVAS_VERSION,
        "zoom": 1.0,
        "pan_x": 0.0,
        "pan_y": 0.0,
        "positions": {},  # node_id -> {"x": float, "y": float}
        "edges": [],  # [{id, source, target, kind}]
    }


def normalize_canvas_state(raw: Any) -> dict[str, Any]:
    """Coerce arbitrary JSON into a valid canvas state (never raises)."""
    base = empty_canvas_state()
    if not isinstance(raw, dict):
        return base
    try:
        zoom = float(raw.get("zoom", 1.0))
    except (TypeError, ValueError):
        zoom = 1.0
    if zoom < 0.25:
        zoom = 0.25
    if zoom > 3.0:
        zoom = 3.0
    try:
        pan_x = float(raw.get("pan_x", 0.0))
    except (TypeError, ValueError):
        pan_x = 0.0
    try:
        pan_y = float(raw.get("pan_y", 0.0))
    except (TypeError, ValueError):
        pan_y = 0.0

    positions: dict[str, dict[str, float]] = {}
    pos_in = raw.get("positions")
    if isinstance(pos_in, dict):
        for nid, xy in pos_in.items():
            if not isinstance(xy, dict):
                continue
            try:
                positions[str(nid)] = {
                    "x": float(xy.get("x", 0.0)),
                    "y": float(xy.get("y", 0.0)),
                }
            except (TypeError, ValueError):
                continue

    edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for e in raw.get("edges") or []:
        if not isinstance(e, dict):
            continue
        src = str(e.get("source") or "").strip()
        tgt = str(e.get("target") or "").strip()
        if not src or not tgt or src == tgt:
            continue
        key = (src, tgt)
        if key in seen:
            continue
        seen.add(key)
        edges.append(
            {
                "id": str(e.get("id") or f"e-{uuid.uuid4().hex[:8]}"),
                "source": src,
                "target": tgt,
                "kind": str(e.get("kind") or "link"),
            }
        )

    return {
        "version": int(raw.get("version") or FLOW_CANVAS_VERSION),
        "zoom": zoom,
        "pan_x": pan_x,
        "pan_y": pan_y,
        "positions": positions,
        "edges": edges,
    }


def get_canvas_state(graph: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(graph, dict):
        return empty_canvas_state()
    return normalize_canvas_state(graph.get(FLOW_CANVAS_KEY))


def tree_edges(graph: dict[str, Any]) -> list[dict[str, Any]]:
    """Hierarchy edges derived from parent_id (source=parent → target=child)."""
    out: list[dict[str, Any]] = []
    for n in graph.get("nodes") or []:
        if not isinstance(n, dict):
            continue
        nid = str(n.get("id") or "").strip()
        pid = n.get("parent_id")
        if not nid or pid is None:
            continue
        pid_s = str(pid).strip()
        if not pid_s:
            continue
        out.append(
            {
                "id": f"tree-{pid_s}-{nid}",
                "source": pid_s,
                "target": nid,
                "kind": "hierarchy",
            }
        )
    return out


def merged_edges(graph: dict[str, Any], canvas: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Tree hierarchy edges + extra canvas links (deduped by source/target)."""
    canvas = canvas or get_canvas_state(graph)
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for e in tree_edges(graph) + list(canvas.get("edges") or []):
        src = str(e.get("source") or "")
        tgt = str(e.get("target") or "")
        if not src or not tgt or (src, tgt) in seen:
            continue
        seen.add((src, tgt))
        out.append(dict(e))
    return out


def auto_layout_positions(graph: dict[str, Any]) -> dict[str, dict[str, float]]:
    """Simple top-down hierarchical layout from parent_id tree."""
    nodes = [n for n in (graph.get("nodes") or []) if isinstance(n, dict) and n.get("id")]
    by_id = {str(n["id"]): n for n in nodes}
    children: dict[str | None, list[str]] = {}
    for n in nodes:
        nid = str(n["id"])
        pid = n.get("parent_id")
        key: str | None
        if pid is None or str(pid).strip() == "":
            key = None
        else:
            key = str(pid).strip()
        children.setdefault(key, []).append(nid)

    for kids in children.values():
        kids.sort(
            key=lambda i: (
                by_id[i].get("order") or 0,
                str(by_id[i].get("title") or ""),
            )
        )

    # Prefer CEO roots first
    roots = list(children.get(None) or [])
    roots.sort(
        key=lambda i: (
            0 if by_id[i].get("type") == "ceo" else 1,
            by_id[i].get("order") or 0,
            str(by_id[i].get("title") or ""),
        )
    )

    positions: dict[str, dict[str, float]] = {}
    # Assign each subtree a width (leaf count)
    leaf_count: dict[str, int] = {}

    def count_leaves(nid: str) -> int:
        kids = children.get(nid) or []
        if not kids:
            leaf_count[nid] = 1
            return 1
        total = sum(count_leaves(c) for c in kids)
        leaf_count[nid] = max(1, total)
        return leaf_count[nid]

    for r in roots:
        count_leaves(r)
    # orphans
    for nid in by_id:
        if nid not in leaf_count:
            count_leaves(nid)

    cursor_x = ORIGIN_X

    def place(nid: str, depth: int, left_x: float) -> float:
        """Place node; return right edge x of subtree."""
        width = leaf_count.get(nid, 1) * (NODE_W + H_GAP)
        kids = children.get(nid) or []
        if not kids:
            cx = left_x + (NODE_W + H_GAP) / 2
            positions[nid] = {"x": cx - NODE_W / 2, "y": ORIGIN_Y + depth * (NODE_H + V_GAP)}
            return left_x + (NODE_W + H_GAP)
        # place children first
        child_left = left_x
        for c in kids:
            child_left = place(c, depth + 1, child_left)
        # center parent over children
        first = positions[kids[0]]
        last = positions[kids[-1]]
        mid = (first["x"] + last["x"] + NODE_W) / 2
        positions[nid] = {"x": mid - NODE_W / 2, "y": ORIGIN_Y + depth * (NODE_H + V_GAP)}
        return left_x + width

    for r in roots:
        cursor_x = place(r, 0, cursor_x) + H_GAP

    # Any remaining (cycles / orphans not reached)
    for nid in by_id:
        if nid not in positions:
            positions[nid] = {"x": cursor_x, "y": ORIGIN_Y}
            cursor_x += NODE_W + H_GAP

    return positions


def ensure_positions(graph: dict[str, Any], canvas: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fill missing positions via auto-layout; return updated canvas state (not saved)."""
    canvas = normalize_canvas_state(canvas if canvas is not None else get_canvas_state(graph))
    positions = dict(canvas.get("positions") or {})
    node_ids = [str(n.get("id")) for n in (graph.get("nodes") or []) if n.get("id")]
    missing = [i for i in node_ids if i not in positions]
    if missing or not positions:
        auto = auto_layout_positions(graph)
        for i in node_ids:
            if i not in positions:
                positions[i] = auto.get(i) or {"x": ORIGIN_X, "y": ORIGIN_Y}
    # Drop stale positions
    live = set(node_ids)
    positions = {k: v for k, v in positions.items() if k in live}
    canvas["positions"] = positions
    return canvas


def set_node_position(
    canvas: dict[str, Any],
    node_id: str,
    x: float,
    y: float,
) -> dict[str, Any]:
    canvas = normalize_canvas_state(canvas)
    canvas.setdefault("positions", {})[str(node_id)] = {"x": float(x), "y": float(y)}
    return canvas


def add_edge(
    canvas: dict[str, Any],
    source: str,
    target: str,
    *,
    kind: str = "link",
) -> dict[str, Any]:
    """Add an extra (non-hierarchy) edge. Idempotent."""
    canvas = normalize_canvas_state(canvas)
    src, tgt = str(source).strip(), str(target).strip()
    if not src or not tgt or src == tgt:
        raise ValueError("edge requires distinct source and target")
    for e in canvas.get("edges") or []:
        if e.get("source") == src and e.get("target") == tgt:
            return canvas
    canvas.setdefault("edges", []).append(
        {
            "id": f"e-{uuid.uuid4().hex[:8]}",
            "source": src,
            "target": tgt,
            "kind": kind or "link",
        }
    )
    return canvas


def remove_edge(
    canvas: dict[str, Any],
    *,
    edge_id: str | None = None,
    source: str | None = None,
    target: str | None = None,
) -> dict[str, Any]:
    canvas = normalize_canvas_state(canvas)
    edges = list(canvas.get("edges") or [])
    if edge_id:
        edges = [e for e in edges if e.get("id") != edge_id]
    elif source and target:
        edges = [
            e
            for e in edges
            if not (e.get("source") == source and e.get("target") == target)
        ]
    canvas["edges"] = edges
    return canvas


def apply_canvas_to_graph(
    graph: dict[str, Any],
    canvas: dict[str, Any],
    *,
    persist: bool = False,
) -> dict[str, Any]:
    """Write normalized canvas onto graph; optionally persist via workflow_graph."""
    canvas = ensure_positions(graph, canvas)
    graph[FLOW_CANVAS_KEY] = canvas
    if persist:
        from app.core.services.misc import workflow_graph as wfg

        wfg.save_graph(graph)
    return graph


def serialize_flow_graph(graph: dict[str, Any]) -> dict[str, Any]:
    """Portable snapshot for save/export/tests: nodes + edges + view.

    Does not include secrets. Hierarchy edges are always included; extra
    canvas links are tagged kind=link.
    """
    canvas = ensure_positions(graph, get_canvas_state(graph))
    nodes_out: list[dict[str, Any]] = []
    for n in graph.get("nodes") or []:
        if not isinstance(n, dict) or not n.get("id"):
            continue
        nid = str(n["id"])
        pos = (canvas.get("positions") or {}).get(nid) or {"x": 0.0, "y": 0.0}
        nodes_out.append(
            {
                "id": nid,
                "title": n.get("title") or "",
                "type": n.get("type") or "agent",
                "parent_id": n.get("parent_id"),
                "order": n.get("order") or 0,
                "x": pos.get("x", 0.0),
                "y": pos.get("y", 0.0),
            }
        )
    return {
        "schema": "ai-agent-studio.flow_canvas",
        "version": FLOW_CANVAS_VERSION,
        "graph_id": graph.get("id"),
        "name": graph.get("name") or "",
        "zoom": canvas.get("zoom", 1.0),
        "pan_x": canvas.get("pan_x", 0.0),
        "pan_y": canvas.get("pan_y", 0.0),
        "nodes": nodes_out,
        "edges": merged_edges(graph, canvas),
        "extra_edges": list(canvas.get("edges") or []),
    }


def load_flow_graph(payload: dict[str, Any]) -> dict[str, Any]:
    """Load a serialize_flow_graph payload into an in-memory org graph + canvas.

    Returns ``{"graph": {...}, "canvas": {...}}``. Does not persist.
    Soft-degrades on partial/malformed payloads.
    """
    if not isinstance(payload, dict):
        raise ValueError("flow canvas payload must be a dict")

    nodes_in = payload.get("nodes")
    if not isinstance(nodes_in, list) or not nodes_in:
        raise ValueError("flow canvas payload requires nodes")

    nodes: list[dict[str, Any]] = []
    positions: dict[str, dict[str, float]] = {}
    for n in nodes_in:
        if not isinstance(n, dict) or not n.get("id"):
            continue
        nid = str(n["id"])
        nodes.append(
            {
                "id": nid,
                "title": n.get("title") or "Node",
                "type": n.get("type") or "agent",
                "parent_id": n.get("parent_id"),
                "order": n.get("order") or 0,
                "instructions": n.get("instructions") or "",
                "agent_id": n.get("agent_id") or "",
            }
        )
        try:
            positions[nid] = {"x": float(n.get("x", 0.0)), "y": float(n.get("y", 0.0))}
        except (TypeError, ValueError):
            positions[nid] = {"x": 0.0, "y": 0.0}

    if not nodes:
        raise ValueError("flow canvas payload has no valid nodes")

    # Extra edges: prefer explicit extra_edges; else non-hierarchy from edges
    parent_pairs = {
        (str(n.get("parent_id")), str(n.get("id")))
        for n in nodes
        if n.get("parent_id")
    }
    if isinstance(payload.get("extra_edges"), list):
        extra_src = list(payload["extra_edges"])
    else:
        rebuilt: list[dict[str, Any]] = []
        for e in payload.get("edges") or []:
            if not isinstance(e, dict):
                continue
            src, tgt = str(e.get("source") or ""), str(e.get("target") or "")
            kind = str(e.get("kind") or "")
            if kind in ("hierarchy", "tree"):
                continue
            if kind == "link" or (src, tgt) not in parent_pairs:
                rebuilt.append(e)
        extra_src = rebuilt

    canvas = normalize_canvas_state(
        {
            "version": payload.get("version") or FLOW_CANVAS_VERSION,
            "zoom": payload.get("zoom", 1.0),
            "pan_x": payload.get("pan_x", 0.0),
            "pan_y": payload.get("pan_y", 0.0),
            "positions": positions,
            "edges": extra_src,
        }
    )

    graph = {
        "id": str(payload.get("graph_id") or uuid.uuid4()),
        "name": str(payload.get("name") or "Flow canvas"),
        "nodes": nodes,
        FLOW_CANVAS_KEY: canvas,
    }
    return {"graph": graph, "canvas": canvas}


def sync_canvas_from_store(graph_id: str | None = None) -> dict[str, Any]:
    """Load active (or given) workflow graph, ensure canvas positions, persist."""
    from app.core.services.misc import workflow_graph as wfg

    if graph_id:
        g = wfg.get_graph(graph_id) or wfg.get_active_graph()
    else:
        g = wfg.get_active_graph()
    canvas = ensure_positions(g, get_canvas_state(g))
    apply_canvas_to_graph(g, canvas, persist=True)
    return {"graph": g, "canvas": canvas}


def roundtrip_ok(graph: dict[str, Any]) -> bool:
    """Serialize → load → compare node ids + edge pairs (for tests)."""
    snap = serialize_flow_graph(graph)
    loaded = load_flow_graph(snap)
    g2 = loaded["graph"]
    ids1 = sorted(str(n.get("id")) for n in (graph.get("nodes") or []) if n.get("id"))
    ids2 = sorted(str(n.get("id")) for n in (g2.get("nodes") or []) if n.get("id"))
    if ids1 != ids2:
        return False
    e1 = sorted(
        (e["source"], e["target"]) for e in merged_edges(graph, get_canvas_state(graph))
    )
    e2 = sorted(
        (e["source"], e["target"]) for e in merged_edges(g2, loaded["canvas"])
    )
    return e1 == e2
