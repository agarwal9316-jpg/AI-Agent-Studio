"""Richer flow canvas view — nodes + edges on a pan/zoom tk.Canvas.

Soft-degrades: CustomTkinter + tk.Canvas only (no Electron / heavy deps).
Persists layout via ``app.core.services.misc.flow_canvas`` + workflow_graph store.
"""

from __future__ import annotations

import tkinter as tk
from typing import Any, Callable

import customtkinter as ctk

from app.ui.themes import UI as _UI
from app.ui.themes import style_chrome_button

_HC_MUTED = _UI["muted"]
_HC_LABEL = _UI["label"]

_NODE_W = 160
_NODE_H = 72

_TYPE_COLORS = {
    "ceo": ("#f59e0b", "#92400e"),
    "department": ("#3b82f6", "#1e40af"),
    "agent": ("#10b981", "#065f46"),
    "worker": ("#10b981", "#065f46"),
    "role": ("#10b981", "#065f46"),
    "flow": ("#8b5cf6", "#5b21b6"),
}


def _canvas_bg() -> str:
    try:
        mode = ctk.get_appearance_mode()
        return "#0f172a" if str(mode).lower() == "dark" else "#f1f5f9"
    except Exception:  # noqa: BLE001
        return "#0f172a"


def _text_fill() -> str:
    try:
        mode = ctk.get_appearance_mode()
        return "#f8fafc" if str(mode).lower() == "dark" else "#0f172a"
    except Exception:  # noqa: BLE001
        return "#f8fafc"


class FlowCanvasPanel(ctk.CTkFrame):
    """Interactive node-edge canvas for organisation / workflow graphs."""

    def __init__(
        self,
        master: Any,
        *,
        on_select: Callable[[dict[str, Any]], None] | None = None,
        on_changed: Callable[[], None] | None = None,
        on_menu_action: Callable[[str, dict[str, Any]], None] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self._on_select = on_select or (lambda _n: None)
        self._on_changed = on_changed or (lambda: None)
        self._on_menu_action = on_menu_action or (lambda _a, _n: None)

        self._graph: dict[str, Any] | None = None
        self._canvas_state: dict[str, Any] = {}
        self._selected_id: str | None = None
        self._node_items: dict[str, dict[str, Any]] = {}  # id -> canvas item ids
        self._edge_items: list[int] = []
        self._connect_mode = False
        self._connect_from: str | None = None
        self._pan_mode = False
        self._drag_node: str | None = None
        self._drag_offset = (0.0, 0.0)
        self._panning = False
        self._pan_last = (0, 0)
        self._dirty = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 4))

        ctk.CTkLabel(
            bar,
            text="Flow canvas",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=_HC_LABEL,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            bar, text="+ Node", width=72, height=28,
            command=self._add_node, **style_chrome_button(primary=True),
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            bar, text="Link", width=56, height=28,
            command=self._toggle_connect, **style_chrome_button(),
        ).pack(side="left", padx=2)
        self._link_btn = bar.winfo_children()[-1]
        ctk.CTkButton(
            bar, text="Unlink", width=64, height=28,
            command=self._unlink_selected, **style_chrome_button(),
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            bar, text="Delete", width=64, height=28,
            command=self._delete_selected, **style_chrome_button(),
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            bar, text="Auto layout", width=96, height=28,
            command=self._auto_layout, **style_chrome_button(),
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            bar, text="Fit", width=48, height=28,
            command=self._fit_view, **style_chrome_button(),
        ).pack(side="left", padx=2)
        self._pan_btn = ctk.CTkButton(
            bar, text="🖐 Pan", width=64, height=28,
            command=self._toggle_pan, **style_chrome_button(),
        )
        self._pan_btn.pack(side="left", padx=2)
        ctk.CTkButton(
            bar, text="Save layout", width=96, height=28,
            command=self._save, **style_chrome_button(primary=True),
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            bar, text="−", width=32, height=28,
            command=lambda: self._bump_zoom(0.9), **style_chrome_button(),
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            bar, text="+", width=32, height=28,
            command=lambda: self._bump_zoom(1.1), **style_chrome_button(),
        ).pack(side="left", padx=2)

        self._hint = ctk.CTkLabel(
            bar,
            text="Drag nodes · wheel zoom · middle-drag pan · Link then click A→B",
            text_color=_HC_MUTED,
            font=ctk.CTkFont(size=11),
        )
        self._hint.pack(side="right", padx=4)

        wrap = ctk.CTkFrame(self, fg_color=("#f1f5f9", "#0f172a"), corner_radius=8)
        wrap.grid(row=1, column=0, sticky="nsew")
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_rowconfigure(0, weight=1)

        self._canvas = tk.Canvas(
            wrap,
            bg=_canvas_bg(),
            highlightthickness=0,
            bd=0,
        )
        self._canvas.grid(row=0, column=0, sticky="nsew")

        self._canvas.bind("<ButtonPress-1>", self._on_press)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self._canvas.bind("<ButtonPress-2>", self._pan_start)
        self._canvas.bind("<B2-Motion>", self._pan_move)
        self._canvas.bind("<ButtonRelease-2>", self._pan_end)
        self._canvas.bind("<MouseWheel>", self._on_wheel)
        self._canvas.bind("<Control-MouseWheel>", self._on_ctrl_wheel)
        # Linux
        self._canvas.bind("<Button-4>", lambda e: self._bump_zoom(1.1, e))
        self._canvas.bind("<Button-5>", lambda e: self._bump_zoom(0.9, e))
        self._canvas.bind("<Enter>", lambda _e: self._canvas.focus_set())
        self._canvas.bind("<Double-Button-1>", self._on_double)

    # ---- public API -------------------------------------------------
    def render(self, graph: dict[str, Any], *, selected_id: str | None = None) -> None:
        from app.core.services.misc import flow_canvas as fc

        self._graph = graph
        self._selected_id = selected_id or self._selected_id
        self._canvas_state = fc.ensure_positions(graph, fc.get_canvas_state(graph))
        self._redraw()

    def set_selection(self, node_id: str | None) -> None:
        self._selected_id = node_id
        self._redraw_selection()

    def get_canvas_state(self) -> dict[str, Any]:
        return dict(self._canvas_state or {})

    # ---- drawing ----------------------------------------------------
    def _zoom(self) -> float:
        try:
            return float((self._canvas_state or {}).get("zoom") or 1.0)
        except (TypeError, ValueError):
            return 1.0

    def _world_to_screen(self, x: float, y: float) -> tuple[float, float]:
        z = self._zoom()
        px = float((self._canvas_state or {}).get("pan_x") or 0.0)
        py = float((self._canvas_state or {}).get("pan_y") or 0.0)
        return x * z + px, y * z + py

    def _screen_to_world(self, sx: float, sy: float) -> tuple[float, float]:
        z = self._zoom() or 1.0
        px = float((self._canvas_state or {}).get("pan_x") or 0.0)
        py = float((self._canvas_state or {}).get("pan_y") or 0.0)
        return (sx - px) / z, (sy - py) / z

    def _redraw(self) -> None:
        c = self._canvas
        c.delete("all")
        self._node_items.clear()
        self._edge_items.clear()
        if not self._graph:
            c.create_text(
                24, 24, anchor="nw", fill=_HC_MUTED[1] if isinstance(_HC_MUTED, tuple) else "#94a3b8",
                text="No organisation graph loaded.",
                font=("Segoe UI", 12),
            )
            return

        from app.core.services.misc import flow_canvas as fc

        z = self._zoom()
        nw, nh = _NODE_W * z, _NODE_H * z
        edges = fc.merged_edges(self._graph, self._canvas_state)
        positions = (self._canvas_state or {}).get("positions") or {}
        by_id = {
            str(n.get("id")): n
            for n in (self._graph.get("nodes") or [])
            if n.get("id")
        }

        # Edges under nodes
        for e in edges:
            src, tgt = e.get("source"), e.get("target")
            if src not in positions or tgt not in positions:
                continue
            s = positions[src]
            t = positions[tgt]
            x1, y1 = self._world_to_screen(s["x"] + _NODE_W / 2, s["y"] + _NODE_H)
            x2, y2 = self._world_to_screen(t["x"] + _NODE_W / 2, t["y"])
            color = "#64748b" if e.get("kind") == "hierarchy" else "#a855f7"
            width = 2 if e.get("kind") == "hierarchy" else 2
            dash = () if e.get("kind") == "hierarchy" else (6, 4)
            item = c.create_line(
                x1, y1, x2, y2,
                fill=color, width=width, arrow=tk.LAST, dash=dash,
                tags=("edge", f"edge-{e.get('id')}"),
            )
            self._edge_items.append(item)

        fill_text = _text_fill()
        for nid, node in by_id.items():
            pos = positions.get(nid)
            if not pos:
                continue
            x, y = self._world_to_screen(pos["x"], pos["y"])
            ntype = str(node.get("type") or "agent")
            fill, outline = _TYPE_COLORS.get(ntype, ("#6366f1", "#312e81"))
            selected = nid == self._selected_id
            border = "#2563eb" if selected else outline
            bw = 3 if selected else 2
            rect = c.create_rectangle(
                x, y, x + nw, y + nh,
                fill=fill, outline=border, width=bw,
                tags=("node", f"node-{nid}"),
            )
            title = str(node.get("title") or "Node")[:28]
            subtitle = ntype.upper()
            t1 = c.create_text(
                x + nw / 2, y + nh * 0.38,
                text=title, fill="#ffffff",
                font=("Segoe UI", max(8, int(11 * z)), "bold"),
                tags=("node", f"node-{nid}"),
            )
            t2 = c.create_text(
                x + nw / 2, y + nh * 0.72,
                text=subtitle, fill="#e2e8f0",
                font=("Segoe UI", max(7, int(9 * z))),
                tags=("node", f"node-{nid}"),
            )
            # connection port (bottom)
            port = c.create_oval(
                x + nw / 2 - 5, y + nh - 5,
                x + nw / 2 + 5, y + nh + 5,
                fill="#f8fafc", outline=border,
                tags=("port", f"node-{nid}"),
            )
            self._node_items[nid] = {
                "rect": rect, "t1": t1, "t2": t2, "port": port, "node": node,
            }

        if self._dirty:
            try:
                self._hint.configure(text="Unsaved layout — click Save layout")
            except Exception:  # noqa: BLE001
                pass

    def _redraw_selection(self) -> None:
        # Cheaper path: full redraw is fine for modest org sizes
        self._redraw()

    def _hit_node(self, sx: float, sy: float) -> str | None:
        wx, wy = self._screen_to_world(sx, sy)
        positions = (self._canvas_state or {}).get("positions") or {}
        # topmost = last drawn; scan reverse
        for nid in reversed(list(positions.keys())):
            p = positions[nid]
            if p["x"] <= wx <= p["x"] + _NODE_W and p["y"] <= wy <= p["y"] + _NODE_H:
                return nid
        return None

    # ---- events -----------------------------------------------------
    def _on_press(self, e: Any) -> None:
        if self._pan_mode:
            self._pan_start(e)
            return
        nid = self._hit_node(e.x, e.y)
        if self._connect_mode and nid:
            if not self._connect_from:
                self._connect_from = nid
                self._selected_id = nid
                self._hint.configure(text=f"Link from “{nid[:8]}…” — click target")
                self._redraw()
                return
            if nid == self._connect_from:
                self._connect_from = None
                self._hint.configure(text="Link cancelled")
                return
            self._link(self._connect_from, nid)
            self._connect_from = None
            return
        if nid:
            self._selected_id = nid
            node = (self._node_items.get(nid) or {}).get("node") or {"id": nid}
            try:
                self._on_select(node)
            except Exception:  # noqa: BLE001
                pass
            pos = (self._canvas_state.get("positions") or {}).get(nid) or {"x": 0, "y": 0}
            wx, wy = self._screen_to_world(e.x, e.y)
            self._drag_node = nid
            self._drag_offset = (wx - pos["x"], wy - pos["y"])
            self._redraw()
        else:
            self._selected_id = None
            self._pan_start(e)

    def _on_drag(self, e: Any) -> None:
        if self._panning or self._pan_mode:
            self._pan_move(e)
            return
        if not self._drag_node:
            return
        from app.core.services.misc import flow_canvas as fc

        wx, wy = self._screen_to_world(e.x, e.y)
        nx = wx - self._drag_offset[0]
        ny = wy - self._drag_offset[1]
        self._canvas_state = fc.set_node_position(
            self._canvas_state, self._drag_node, nx, ny
        )
        self._dirty = True
        self._redraw()

    def _on_release(self, e: Any) -> None:
        self._drag_node = None
        if self._panning:
            self._pan_end(e)

    def _on_double(self, e: Any) -> None:
        nid = self._hit_node(e.x, e.y)
        if not nid:
            return
        node = (self._node_items.get(nid) or {}).get("node") or {"id": nid}
        try:
            self._on_menu_action("configure", node)
        except Exception:  # noqa: BLE001
            pass

    def _pan_start(self, e: Any) -> None:
        self._panning = True
        self._pan_last = (e.x, e.y)
        try:
            self._canvas.configure(cursor="fleur")
        except Exception:  # noqa: BLE001
            pass

    def _pan_move(self, e: Any) -> None:
        if not self._panning and not self._pan_mode:
            return
        dx = e.x - self._pan_last[0]
        dy = e.y - self._pan_last[1]
        self._pan_last = (e.x, e.y)
        self._canvas_state["pan_x"] = float(self._canvas_state.get("pan_x") or 0) + dx
        self._canvas_state["pan_y"] = float(self._canvas_state.get("pan_y") or 0) + dy
        self._dirty = True
        self._redraw()

    def _pan_end(self, _e: Any = None) -> None:
        self._panning = False
        try:
            self._canvas.configure(cursor="fleur" if self._pan_mode else "arrow")
        except Exception:  # noqa: BLE001
            pass

    def _on_wheel(self, e: Any) -> None:
        # Without Ctrl: vertical pan; with Ctrl handled separately
        delta = getattr(e, "delta", 0) or 0
        self._canvas_state["pan_y"] = float(self._canvas_state.get("pan_y") or 0) + (
            40 if delta > 0 else -40
        )
        self._redraw()

    def _on_ctrl_wheel(self, e: Any) -> None:
        delta = getattr(e, "delta", 0) or 0
        self._bump_zoom(1.1 if delta > 0 else 0.9, e)

    def _bump_zoom(self, factor: float, e: Any | None = None) -> None:
        z = self._zoom() * factor
        z = max(0.35, min(2.5, z))
        # Zoom toward pointer if available
        if e is not None:
            wx, wy = self._screen_to_world(e.x, e.y)
            self._canvas_state["zoom"] = z
            sx, sy = self._world_to_screen(wx, wy)
            self._canvas_state["pan_x"] = float(self._canvas_state.get("pan_x") or 0) + (
                e.x - sx
            )
            self._canvas_state["pan_y"] = float(self._canvas_state.get("pan_y") or 0) + (
                e.y - sy
            )
        else:
            self._canvas_state["zoom"] = z
        self._dirty = True
        self._redraw()

    def _toggle_pan(self) -> None:
        self._pan_mode = not self._pan_mode
        self._connect_mode = False
        try:
            self._pan_btn.configure(
                text="🖐 Pan ON" if self._pan_mode else "🖐 Pan",
                fg_color=("#2563eb", "#1d4ed8") if self._pan_mode else None,
            )
            self._canvas.configure(cursor="fleur" if self._pan_mode else "arrow")
        except Exception:  # noqa: BLE001
            pass

    def _toggle_connect(self) -> None:
        self._connect_mode = not self._connect_mode
        self._connect_from = None
        self._pan_mode = False
        try:
            self._link_btn.configure(
                text="Link ON" if self._connect_mode else "Link",
                fg_color=("#7c3aed", "#6d28d9") if self._connect_mode else None,
            )
            self._hint.configure(
                text="Click source then target" if self._connect_mode else "Link mode off"
            )
        except Exception:  # noqa: BLE001
            pass

    def _link(self, src: str, tgt: str) -> None:
        from app.core.services.misc import flow_canvas as fc

        try:
            self._canvas_state = fc.add_edge(self._canvas_state, src, tgt, kind="link")
            self._dirty = True
            self._hint.configure(text=f"Linked {src[:6]}→{tgt[:6]} — Save layout to persist")
            self._redraw()
            self._on_changed()
        except Exception as ex:  # noqa: BLE001
            self._hint.configure(text=f"Link failed: {ex}")

    def _unlink_selected(self) -> None:
        from app.core.services.misc import flow_canvas as fc

        sid = self._selected_id
        if not sid or not self._graph:
            return
        # Remove extra (non-hierarchy) edges touching selection
        edges = list((self._canvas_state or {}).get("edges") or [])
        kept = [e for e in edges if e.get("source") != sid and e.get("target") != sid]
        removed = len(edges) - len(kept)
        self._canvas_state["edges"] = kept
        # Soft: also clear parent_id? No — keep org tree intact; only canvas links
        if removed:
            self._dirty = True
            self._hint.configure(text=f"Removed {removed} canvas link(s)")
            self._redraw()
            self._on_changed()
        else:
            self._hint.configure(
                text="No extra canvas links on selection (hierarchy edges stay)"
            )

    def _delete_selected(self) -> None:
        if not self._selected_id or not self._graph:
            return
        node = (self._node_items.get(self._selected_id) or {}).get("node")
        if not node:
            return
        if node.get("type") == "ceo":
            self._hint.configure(text="CEO root cannot be deleted")
            return
        try:
            self._on_menu_action("remove", node)
        except Exception as ex:  # noqa: BLE001
            self._hint.configure(text=f"Delete: {ex}")

    def _add_node(self) -> None:
        if not self._graph:
            return
        # Parent = selected, else CEO
        parent = self._selected_id
        node = {"id": "", "title": "New worker", "parent_id": parent, "type": "agent"}
        try:
            self._on_menu_action("add_child", node if parent else {"id": parent or "", "type": "ceo"})
        except Exception:
            # Fallback: call workflow_graph directly
            try:
                from app.core.services.misc import workflow_graph as wfg
                from app.core.services.misc import flow_canvas as fc

                parent_id = parent
                if not parent_id:
                    ceo = next(
                        (n for n in (self._graph.get("nodes") or []) if n.get("type") == "ceo"),
                        None,
                    )
                    parent_id = ceo["id"] if ceo else None
                created = wfg.add_ai_worker(
                    self._graph, parent_id=parent_id, title="New worker"
                )
                # Place near parent
                positions = self._canvas_state.setdefault("positions", {})
                base = positions.get(str(parent_id)) or {"x": 80, "y": 60}
                positions[created["id"]] = {
                    "x": base["x"] + 40,
                    "y": base["y"] + _NODE_H + 40,
                }
                self._canvas_state = fc.ensure_positions(self._graph, self._canvas_state)
                self._selected_id = created["id"]
                self._dirty = True
                self._redraw()
                self._on_changed()
            except Exception as ex:  # noqa: BLE001
                self._hint.configure(text=f"Add node failed: {ex}")

    def _auto_layout(self) -> None:
        from app.core.services.misc import flow_canvas as fc

        if not self._graph:
            return
        self._canvas_state["positions"] = fc.auto_layout_positions(self._graph)
        self._dirty = True
        self._redraw()

    def _fit_view(self) -> None:
        positions = (self._canvas_state or {}).get("positions") or {}
        if not positions:
            return
        xs = [p["x"] for p in positions.values()]
        ys = [p["y"] for p in positions.values()]
        min_x, max_x = min(xs), max(xs) + _NODE_W
        min_y, max_y = min(ys), max(ys) + _NODE_H
        try:
            cw = max(100, int(self._canvas.winfo_width()))
            ch = max(100, int(self._canvas.winfo_height()))
        except Exception:  # noqa: BLE001
            cw, ch = 800, 600
        bw = max(1.0, max_x - min_x)
        bh = max(1.0, max_y - min_y)
        z = min(cw / (bw + 80), ch / (bh + 80), 1.5)
        z = max(0.35, z)
        self._canvas_state["zoom"] = z
        self._canvas_state["pan_x"] = (cw - bw * z) / 2 - min_x * z
        self._canvas_state["pan_y"] = (ch - bh * z) / 2 - min_y * z
        self._dirty = True
        self._redraw()

    def _save(self) -> None:
        from app.core.services.misc import flow_canvas as fc

        if not self._graph:
            return
        try:
            fc.apply_canvas_to_graph(self._graph, self._canvas_state, persist=True)
            self._dirty = False
            self._hint.configure(text="Layout saved to organisation store")
            self._on_changed()
        except Exception as ex:  # noqa: BLE001
            self._hint.configure(text=f"Save failed (soft-degrade): {ex}")
