"""Roadmap — Richer flow canvas (1.28.0).

Graph model serialize/load round-trip; edges from tree + extra links;
positions auto-layout; soft-degrade on bad payloads.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.version import __version__  # noqa: E402
from app.core.services.misc import flow_canvas as fc  # noqa: E402


def test_version():
    assert __version__ == "1.28.0", __version__
    print("✓ version 1.28.0")


def _sample_graph() -> dict:
    return {
        "id": "g-test-flow",
        "name": "Flow test org",
        "nodes": [
            {
                "id": "ceo-1",
                "type": "ceo",
                "title": "CEO",
                "parent_id": None,
                "order": 0,
            },
            {
                "id": "dept-a",
                "type": "department",
                "title": "Engineering",
                "parent_id": "ceo-1",
                "order": 0,
            },
            {
                "id": "w1",
                "type": "agent",
                "title": "Builder",
                "parent_id": "dept-a",
                "order": 0,
            },
            {
                "id": "w2",
                "type": "agent",
                "title": "Reviewer",
                "parent_id": "dept-a",
                "order": 1,
            },
        ],
    }


def test_empty_and_normalize():
    empty = fc.empty_canvas_state()
    assert empty["version"] == fc.FLOW_CANVAS_VERSION
    assert empty["positions"] == {}
    assert empty["edges"] == []
    bad = fc.normalize_canvas_state({"zoom": "nope", "positions": "x", "edges": [1, {"source": "a"}]})
    assert bad["zoom"] == 1.0
    assert bad["positions"] == {}
    assert bad["edges"] == []
    print("✓ empty + normalize soft-degrade")


def test_tree_edges_and_auto_layout():
    g = _sample_graph()
    edges = fc.tree_edges(g)
    pairs = {(e["source"], e["target"]) for e in edges}
    assert ("ceo-1", "dept-a") in pairs
    assert ("dept-a", "w1") in pairs
    assert ("dept-a", "w2") in pairs
    pos = fc.auto_layout_positions(g)
    assert set(pos) == {"ceo-1", "dept-a", "w1", "w2"}
    # CEO above children
    assert pos["ceo-1"]["y"] < pos["dept-a"]["y"]
    assert pos["dept-a"]["y"] < pos["w1"]["y"]
    print("✓ tree edges + auto layout")


def test_ensure_positions_and_extra_edges():
    g = _sample_graph()
    canvas = fc.ensure_positions(g, None)
    assert "w1" in canvas["positions"]
    canvas = fc.add_edge(canvas, "w1", "w2", kind="link")
    merged = fc.merged_edges(g, canvas)
    kinds = {(e["source"], e["target"]): e["kind"] for e in merged}
    assert kinds[("w1", "w2")] == "link"
    assert kinds[("ceo-1", "dept-a")] == "hierarchy"
    canvas = fc.remove_edge(canvas, source="w1", target="w2")
    assert not any(e["source"] == "w1" and e["target"] == "w2" for e in canvas["edges"])
    print("✓ positions + extra edges add/remove")


def test_serialize_load_roundtrip():
    g = _sample_graph()
    canvas = fc.ensure_positions(g, None)
    canvas = fc.add_edge(canvas, "w1", "w2", kind="link")
    canvas["zoom"] = 1.25
    canvas["pan_x"] = 12.5
    g = fc.apply_canvas_to_graph(g, canvas, persist=False)

    snap = fc.serialize_flow_graph(g)
    assert snap["schema"] == "ai-agent-studio.flow_canvas"
    assert snap["zoom"] == 1.25
    assert len(snap["nodes"]) == 4
    assert any(e.get("kind") == "link" for e in snap["edges"])

    loaded = fc.load_flow_graph(snap)
    g2, c2 = loaded["graph"], loaded["canvas"]
    assert {n["id"] for n in g2["nodes"]} == {"ceo-1", "dept-a", "w1", "w2"}
    assert abs(float(c2["zoom"]) - 1.25) < 1e-9
    assert any(e["source"] == "w1" and e["target"] == "w2" for e in c2["edges"])
    # positions survived
    assert "w1" in c2["positions"]
    assert abs(c2["positions"]["w1"]["x"] - canvas["positions"]["w1"]["x"]) < 1e-6
    assert fc.roundtrip_ok(g)
    print("✓ serialize → load round-trip")


def test_load_rejects_empty():
    try:
        fc.load_flow_graph({})
        assert False, "expected ValueError"
    except ValueError:
        pass
    try:
        fc.load_flow_graph({"nodes": []})
        assert False, "expected ValueError"
    except ValueError:
        pass
    print("✓ load rejects empty payload")


def test_set_node_position():
    c = fc.empty_canvas_state()
    c = fc.set_node_position(c, "n1", 10.5, 20.25)
    assert c["positions"]["n1"] == {"x": 10.5, "y": 20.25}
    print("✓ set_node_position")


def test_apply_without_persist_leaves_key():
    g = _sample_graph()
    c = fc.ensure_positions(g, None)
    g2 = fc.apply_canvas_to_graph(copy.deepcopy(g), c, persist=False)
    assert fc.FLOW_CANVAS_KEY in g2
    assert g2[fc.FLOW_CANVAS_KEY]["positions"]
    print("✓ apply_canvas_to_graph (no persist)")


def test_module_import_path():
    # Soft-degrade path used by UI
    from app.core.services.misc.flow_canvas import serialize_flow_graph, load_flow_graph

    g = _sample_graph()
    snap = serialize_flow_graph(g)
    again = load_flow_graph(snap)
    assert again["graph"]["name"] == "Flow test org"
    print("✓ module import path")


if __name__ == "__main__":
    test_version()
    test_empty_and_normalize()
    test_tree_edges_and_auto_layout()
    test_ensure_positions_and_extra_edges()
    test_serialize_load_roundtrip()
    test_load_rejects_empty()
    test_set_node_position()
    test_apply_without_persist_leaves_key()
    test_module_import_path()
    print("\nAll flow canvas tests passed.")
