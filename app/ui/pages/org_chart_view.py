"""
Visual organisation chart (company tree) for AI Agent Studio.

Layout inspired by classic org diagrams:
  CEO at top → directors/managers as branches → workers below each branch.
Each node is a card with avatar, name, role, status, + Add, and ▾ menu.
"""

from __future__ import annotations

import tkinter as tk
from typing import Any, Callable

import customtkinter as ctk

from app.ui.themes import UI as _UI
from app.ui.themes import style_chrome_button

_HC_MUTED = _UI["muted"]
_HC_LABEL = _UI["label"]

# Division / branch border colors (cycle by sibling index under CEO)
_BRANCH_COLORS = [
    ("#3b82f6", "#1d4ed8"),  # blue
    ("#f97316", "#c2410c"),  # orange
    ("#14b8a6", "#0f766e"),  # teal
    ("#a855f7", "#7e22ce"),  # purple
    ("#eab308", "#a16207"),  # yellow
    ("#ec4899", "#be185d"),  # pink
]

_CARD_H = 92
_GUTTER_W = 22  # width of one depth step in tree connector gutter
_LINE_W = 2

_STATUS_DOT = {
    "idle": "#94a3b8",
    "running": "#3b82f6",
    "thinking": "#8b5cf6",
    "waiting": "#f59e0b",
    "delegating": "#06b6d4",
    "completed": "#22c55e",
    "done": "#22c55e",
    "error": "#ef4444",
    "failed": "#ef4444",
    "disabled": "#64748b",
    "blocked": "#f97316",
}


def _avatar_color(name: str) -> str:
    colors = (
        "#0ea5e9",
        "#8b5cf6",
        "#10b981",
        "#f59e0b",
        "#ef4444",
        "#ec4899",
        "#14b8a6",
        "#6366f1",
    )
    return colors[sum(ord(c) for c in (name or "?")) % len(colors)]


def _initials(title: str) -> str:
    parts = [p for p in (title or "?").split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


# Full menu items required by Company Structure upgrade
WORKER_MENU_ITEMS: list[tuple[str, str]] = [
    ("add_child", "Add AI Worker"),
    ("configure", "Configure Worker"),
    ("view_goal", "View Current Goal"),
    ("view_assignments", "View Assignments"),
    ("view_execution", "View Execution"),
    ("view_reports", "View Reports"),
    ("view_comms", "View Communication"),
    ("duplicate", "Duplicate Worker"),
    ("move", "Move under…"),
    ("toggle", "Enable / Disable"),
    ("remove", "Remove Worker"),
]


class WorkerCard(ctk.CTkFrame):
    """Single org-chart node card with + and dropdown."""

    def __init__(
        self,
        master: Any,
        node: dict[str, Any],
        *,
        border_color: str | tuple[str, str],
        selected: bool,
        on_select: Callable[[dict[str, Any]], None],
        on_menu: Callable[[dict[str, Any], int, int], None],
        on_add: Callable[[dict[str, Any]], None],
        width: int = 168,
        **kwargs: Any,
    ) -> None:
        bc = border_color if isinstance(border_color, (tuple, list)) else (border_color, border_color)
        self._default_border = bc
        super().__init__(
            master,
            width=width,
            height=_CARD_H,
            corner_radius=10,
            border_width=2 if not selected else 3,
            border_color=bc if not selected else ("#2563eb", "#3b82f6"),
            fg_color=("#ffffff", "#1e293b") if not selected else ("#eff6ff", "#1e3a5f"),
            **kwargs,
        )
        self.grid_propagate(False)
        self.pack_propagate(False)
        self._node = node
        self._on_select = on_select
        self._on_menu = on_menu
        self._on_add = on_add

        title = str(node.get("title") or "Worker")
        role = str(
            node.get("_agent_role")
            or node.get("agent_role")
            or node.get("type")
            or "AI Worker"
        )
        ntype = str(node.get("type") or "agent")
        status = str(node.get("_status") or node.get("status") or "idle")
        if node.get("enabled") is False:
            status = "disabled"
        dot = _STATUS_DOT.get(status.lower(), "#94a3b8")

        # Top row: avatar + text
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=6, pady=(6, 0))

        av = ctk.CTkLabel(
            top,
            text=_initials(title),
            width=30,
            height=30,
            corner_radius=15,
            fg_color=_avatar_color(title),
            text_color="#ffffff",
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        av.pack(side="left", padx=(0, 6))

        text_col = ctk.CTkFrame(top, fg_color="transparent")
        text_col.pack(side="left", fill="x", expand=True)
        name_lbl = ctk.CTkLabel(
            text_col,
            text=title[:22] + ("…" if len(title) > 22 else ""),
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=_HC_LABEL,
            anchor="w",
        )
        name_lbl.pack(fill="x")
        role_lbl = ctk.CTkLabel(
            text_col,
            text=role[:28] + ("…" if len(role) > 28 else ""),
            font=ctk.CTkFont(size=10),
            text_color=_HC_MUTED,
            anchor="w",
        )
        role_lbl.pack(fill="x")

        # Bottom: type/status + actions
        bot = ctk.CTkFrame(self, fg_color="transparent")
        bot.pack(fill="x", padx=6, pady=(4, 6))
        type_tag = {
            "ceo": "CEO",
            "department": "DEPT",
            "agent": "WORKER",
            "worker": "WORKER",
            "role": "WORKER",
        }.get(ntype, ntype.upper()[:6])
        if node.get("_is_manager") and ntype not in ("ceo", "department"):
            type_tag = "MGR"
        ctk.CTkLabel(
            bot,
            text=f"● {type_tag} · {status}",
            font=ctk.CTkFont(size=9),
            text_color=dot,
            anchor="w",
        ).pack(side="left", fill="x", expand=True)

        ctk.CTkButton(
            bot,
            text="+",
            width=28,
            height=24,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=lambda: self._on_add(self._node),
            **style_chrome_button(primary=True),
        ).pack(side="right", padx=(2, 0))
        menu_btn = ctk.CTkButton(
            bot,
            text="▾",
            width=28,
            height=24,
            command=self._popup_menu,
            **style_chrome_button(),
        )
        menu_btn.pack(side="right", padx=2)

        # Click card to select (not buttons)
        for w in (self, top, text_col, name_lbl, role_lbl, av):
            w.bind("<Button-1>", self._click_select)
            w.bind("<Button-3>", self._right_click)

    def _click_select(self, _e: Any = None) -> None:
        self._on_select(self._node)

    def _right_click(self, e: Any) -> None:
        self._on_menu(self._node, int(e.x_root), int(e.y_root))

    def _popup_menu(self) -> None:
        try:
            x = self.winfo_rootx() + self.winfo_width() - 20
            y = self.winfo_rooty() + self.winfo_height() - 10
        except Exception:  # noqa: BLE001
            x, y = 200, 200
        self._on_menu(self._node, x, y)


def popup_worker_menu(
    parent: Any,
    node: dict[str, Any],
    x: int,
    y: int,
    *,
    handlers: dict[str, Callable[[dict[str, Any]], None]],
    is_ceo: bool = False,
) -> None:
    """
    Native Tk menu (fast, no flicker) with full worker actions.
    handlers: action_id → callback(node)
    """
    menu = tk.Menu(parent, tearoff=0)
    title = str(node.get("title") or "Worker")
    menu.add_command(label=f"── {title[:28]} ──", state="disabled")
    menu.add_separator()

    for action_id, label in WORKER_MENU_ITEMS:
        if is_ceo and action_id in ("remove", "move", "duplicate"):
            if action_id == "remove":
                menu.add_command(label="Remove Worker (protected)", state="disabled")
                continue
            if action_id == "move":
                menu.add_command(label="Move under… (CEO is root)", state="disabled")
                continue
        cb = handlers.get(action_id)
        if not cb:
            menu.add_command(label=label, state="disabled")
            continue
        # Closures need default-arg capture
        menu.add_command(
            label=label,
            command=lambda a=action_id, n=node, h=handlers: h[a](n) if a in h else None,
        )

    try:
        menu.tk_popup(x, y)
    finally:
        try:
            menu.grab_release()
        except Exception:  # noqa: BLE001
            pass


def _canvas_bg() -> str:
    try:
        mode = ctk.get_appearance_mode()
        return "#0f172a" if str(mode).lower() == "dark" else "#f8fafc"
    except Exception:  # noqa: BLE001
        return "#0f172a"


def _line_color(branch_color: str | tuple[str, str]) -> str:
    if isinstance(branch_color, (tuple, list)):
        try:
            mode = ctk.get_appearance_mode()
            return str(branch_color[1 if str(mode).lower() == "dark" else 0])
        except Exception:  # noqa: BLE001
            return str(branch_color[0])
    return str(branch_color)


def _tree_connector(
    parent: Any,
    *,
    depth: int,
    is_last: bool,
    open_above: list[bool],
    color: str,
    height: int = _CARD_H,
) -> tk.Canvas:
    """
    Continuous org-tree gutter for one row.
    open_above[i] = draw a full vertical spine at depth i (ancestor has more siblings below).
    """
    depth = max(0, int(depth))
    width = max(_GUTTER_W, depth * _GUTTER_W + 8)
    bg = _canvas_bg()
    cv = tk.Canvas(
        parent,
        width=width,
        height=height,
        highlightthickness=0,
        bd=0,
        bg=bg,
    )
    mid_y = height // 2
    # Spines for ancestors that continue past this row
    for d in range(max(0, depth - 1)):
        if d < len(open_above) and open_above[d]:
            x = d * _GUTTER_W + _GUTTER_W // 2
            cv.create_line(x, 0, x, height, fill=color, width=_LINE_W)
    if depth <= 0:
        return cv
    # Elbow for this node under its parent
    x = (depth - 1) * _GUTTER_W + _GUTTER_W // 2
    x_end = width - 2
    if is_last:
        # └─  vertical from top to mid, then horizontal
        cv.create_line(x, 0, x, mid_y, fill=color, width=_LINE_W)
    else:
        # ├─  full vertical + horizontal
        cv.create_line(x, 0, x, height, fill=color, width=_LINE_W)
    cv.create_line(x, mid_y, x_end, mid_y, fill=color, width=_LINE_W)
    return cv


def _v_line(parent: Any, *, color: str, height: int = 18, width: int = 24) -> tk.Canvas:
    """Short centered vertical connector (CEO stem / column drop)."""
    bg = _canvas_bg()
    cv = tk.Canvas(parent, width=width, height=height, highlightthickness=0, bd=0, bg=bg)
    x = width // 2
    cv.create_line(x, 0, x, height, fill=color, width=_LINE_W)
    return cv


def _h_bus(parent: Any, *, color: str, width: int, height: int = 16) -> tk.Canvas:
    """Horizontal bus under CEO linking branch columns."""
    bg = _canvas_bg()
    cv = tk.Canvas(parent, width=max(40, width), height=height, highlightthickness=0, bd=0, bg=bg)
    y = height // 2
    # Horizontal span with small end caps
    cv.create_line(8, y, max(40, width) - 8, y, fill=color, width=_LINE_W)
    return cv


def build_branch_columns(
    graph: dict[str, Any],
    *,
    collapsed: set[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Return layout columns for visual chart.

    Each column is a list of nodes in depth-first order under one CEO child.
    CEO is separate (root). Nodes under a collapsed parent are omitted.
    """
    from app.services import workflow_graph as wfg

    collapsed = collapsed or set()
    ceo = next((n for n in (graph.get("nodes") or []) if n.get("type") == "ceo"), None)
    if not ceo:
        roots = wfg.children_of(graph, None)
        ceo = roots[0] if roots else None
    if not ceo:
        return []

    # If CEO is collapsed, show no branch columns
    if str(ceo.get("id") or "") in collapsed:
        return []

    columns: list[dict[str, Any]] = []
    kids = wfg.children_of(graph, str(ceo.get("id")))
    if not kids:
        others = [n for n in wfg.walk_tree(graph) if n.get("type") != "ceo"]
        if others:
            columns.append({"head": others[0], "nodes": others, "color_idx": 0})
        return columns

    for i, head in enumerate(kids):
        col_nodes: list[dict[str, Any]] = []

        def walk(nid: str, depth: int) -> None:
            n = wfg.get_node(graph, nid)
            if not n:
                return
            item = dict(n)
            kids_here = wfg.children_of(graph, nid)
            item["_depth"] = depth
            item["_is_manager"] = len(kids_here) > 0
            item["_has_children"] = len(kids_here) > 0
            item["_collapsed"] = nid in collapsed
            item["_status"] = n.get("status") or "idle"
            # Sibling position (for continuous tree lines)
            parent = n.get("parent_id")
            sibs = wfg.children_of(graph, parent)
            sib_ids = [str(s.get("id") or "") for s in sibs]
            try:
                sidx = sib_ids.index(nid)
            except ValueError:
                sidx = 0
            item["_sib_index"] = sidx
            item["_sib_count"] = len(sib_ids)
            item["_is_last_sibling"] = sidx >= len(sib_ids) - 1
            if n.get("agent_id"):
                try:
                    from app.core.services.data.storage import get_agent

                    ag = get_agent(str(n["agent_id"]))
                    if ag:
                        item["_agent_role"] = ag.get("role")
                        item["_agent_name"] = ag.get("name")
                except Exception:  # noqa: BLE001
                    pass
            col_nodes.append(item)
            if nid in collapsed:
                return  # team collapsed — hide descendants
            for c in kids_here:
                walk(str(c["id"]), depth + 1)

        walk(str(head["id"]), 0)
        columns.append({"head": head, "nodes": col_nodes, "color_idx": i})
    return columns


class OrgChartPanel(ctk.CTkFrame):
    """
    Visual org chart: CEO on top, branch columns below.

    - Expand / collapse teams (▸ ▾ on managers)
    - Free-drag pan of the view (drag empty space or middle-mouse)
    - Bottom Reset → CEO at top + collapse all teams
    Soft-updates selection without full destroy when possible.
    """

    def __init__(
        self,
        master: Any,
        *,
        on_select: Callable[[dict[str, Any]], None],
        on_menu_action: Callable[[str, dict[str, Any]], None],
        **kwargs: Any,
    ) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self._on_select = on_select
        self._on_menu_action = on_menu_action
        self._graph: dict[str, Any] | None = None
        self._selected_id: str | None = None
        self._cards: dict[str, WorkerCard] = {}
        self._structure_sig: str = ""
        # Node ids whose children are hidden
        self._collapsed: set[str] = set()
        self._pan_mode = False  # optional hand tool (always can middle-drag)
        self._scroll_job: str | None = None
        self._rebuild_lock = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ---- Top toolbar ----
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        ctk.CTkLabel(
            bar,
            text="Organisation chart",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=_HC_LABEL,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            bar,
            text="Expand all",
            width=88,
            height=28,
            command=self.expand_all,
            **style_chrome_button(),
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            bar,
            text="Collapse all",
            width=96,
            height=28,
            command=self.collapse_all_teams,
            **style_chrome_button(),
        ).pack(side="left", padx=2)
        self._pan_btn = ctk.CTkButton(
            bar,
            text="🖐 Drag view",
            width=96,
            height=28,
            command=self._toggle_pan_mode,
            **style_chrome_button(),
        )
        self._pan_btn.pack(side="left", padx=2)

        self._hint = ctk.CTkLabel(
            bar,
            text="▸/▾ = team · drag empty area or middle-mouse to pan · wheel to scroll",
            text_color=_HC_MUTED,
            font=ctk.CTkFont(size=11),
        )
        self._hint.pack(side="right", padx=4)

        # ---- Pan / scroll canvas (free drag view) ----
        self._canvas_wrap = ctk.CTkFrame(
            self, fg_color=("#f8fafc", "#0f172a"), corner_radius=8
        )
        self._canvas_wrap.grid(row=1, column=0, sticky="nsew")
        self._canvas_wrap.grid_columnconfigure(0, weight=1)
        self._canvas_wrap.grid_rowconfigure(0, weight=1)

        # Match appearance mode for canvas bg
        try:
            mode = ctk.get_appearance_mode()
            bg = "#0f172a" if str(mode).lower() == "dark" else "#f8fafc"
        except Exception:  # noqa: BLE001
            bg = "#0f172a"

        self._canvas = tk.Canvas(
            self._canvas_wrap,
            highlightthickness=0,
            bd=0,
            bg=bg,
            cursor="arrow",
        )
        self._canvas.grid(row=0, column=0, sticky="nsew")

        # Scrollbars (optional thin aids)
        self._vsb = ctk.CTkScrollbar(
            self._canvas_wrap, orientation="vertical", command=self._canvas.yview
        )
        self._vsb.grid(row=0, column=1, sticky="ns")
        self._hsb = ctk.CTkScrollbar(
            self._canvas_wrap, orientation="horizontal", command=self._canvas.xview
        )
        self._hsb.grid(row=1, column=0, sticky="ew")
        self._canvas.configure(
            yscrollcommand=self._vsb.set,
            xscrollcommand=self._hsb.set,
        )

        self._inner = ctk.CTkFrame(self._canvas, fg_color="transparent")
        self._win_id = self._canvas.create_window(0, 0, window=self._inner, anchor="nw")

        self._inner.bind("<Configure>", self._on_inner_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)

        # Pan: middle-mouse always; left-drag when pan mode or on empty canvas
        self._canvas.bind("<ButtonPress-2>", self._pan_start)
        self._canvas.bind("<B2-Motion>", self._pan_move)
        self._canvas.bind("<ButtonRelease-2>", self._pan_end)
        self._canvas.bind("<ButtonPress-1>", self._left_press)
        self._canvas.bind("<B1-Motion>", self._left_drag)
        self._canvas.bind("<ButtonRelease-1>", self._left_release)
        # Mouse wheel (Windows)
        self._canvas.bind("<Enter>", lambda _e: self._canvas.focus_set())
        self._canvas.bind("<MouseWheel>", self._on_wheel)
        self._canvas.bind("<Shift-MouseWheel>", self._on_shift_wheel)
        # Also bind on inner so wheel works over cards
        self._inner.bind("<MouseWheel>", self._on_wheel)
        self._inner.bind("<Shift-MouseWheel>", self._on_shift_wheel)

        self._drag = {
            "active": False,
            "moved": False,
            "x": 0,
            "y": 0,
            "from_pan_mode": False,
        }

        # ---- Bottom bar: Reset to CEO view ----
        foot = ctk.CTkFrame(
            self,
            fg_color=_UI.get("top_bg", ("#f3f4f6", "#161a22")),
            corner_radius=8,
            height=44,
        )
        foot.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        foot.grid_propagate(False)
        ctk.CTkLabel(
            foot,
            text="View",
            text_color=_HC_MUTED,
            font=ctk.CTkFont(size=11),
        ).pack(side="left", padx=(10, 4), pady=8)
        ctk.CTkButton(
            foot,
            text="↺ Reset · CEO top + collapse teams",
            height=32,
            command=self.reset_ceo_view,
            **style_chrome_button(primary=True),
        ).pack(side="left", padx=4, pady=6)
        ctk.CTkButton(
            foot,
            text="Scroll to CEO",
            width=110,
            height=32,
            command=self.scroll_to_ceo,
            **style_chrome_button(),
        ).pack(side="left", padx=4, pady=6)
        self._view_status = ctk.CTkLabel(
            foot,
            text="Drag empty space to pan",
            text_color=_HC_MUTED,
            font=ctk.CTkFont(size=11),
        )
        self._view_status.pack(side="right", padx=12)

    # ----- Expand / collapse -----
    def expand_all(self) -> None:
        self._collapsed.clear()
        self._force_rebuild()
        self._set_view_status("All teams expanded")

    def collapse_all_teams(self) -> None:
        """Collapse every node that has children (CEO + managers) — hide team members."""
        g = self._graph
        if not g:
            return
        from app.services import workflow_graph as wfg

        self._collapsed.clear()
        for n in g.get("nodes") or []:
            nid = str(n.get("id") or "")
            if not nid:
                continue
            if wfg.children_of(g, nid):
                self._collapsed.add(nid)
        self._force_rebuild()
        self._set_view_status("All teams collapsed")

    def toggle_node(self, node_id: str) -> None:
        nid = str(node_id or "")
        if not nid:
            return
        if nid in self._collapsed:
            self._collapsed.discard(nid)
        else:
            self._collapsed.add(nid)
        self._force_rebuild()

    def reset_ceo_view(self) -> None:
        """CEO at top of viewport + collapse all team members."""
        self.collapse_all_teams()
        self.scroll_to_ceo()
        self._set_view_status("Reset: CEO top · teams collapsed")

    def scroll_to_ceo(self) -> None:
        """Move pan so CEO (top of chart content) is visible."""
        try:
            self._canvas.xview_moveto(0)
            self._canvas.yview_moveto(0)
            # Keep window anchored top-left of scrollregion
            self._canvas.coords(self._win_id, 0, 0)
        except Exception:  # noqa: BLE001
            pass
        self._update_scrollregion()

    def _force_rebuild(self) -> None:
        self._structure_sig = ""
        if self._graph is not None:
            self._rebuild(self._graph, self._selected_id)

    def _toggle_pan_mode(self) -> None:
        self._pan_mode = not self._pan_mode
        try:
            self._canvas.configure(cursor="fleur" if self._pan_mode else "arrow")
            self._pan_btn.configure(
                text="🖐 Drag ON" if self._pan_mode else "🖐 Drag view",
                fg_color=("#2563eb", "#1d4ed8") if self._pan_mode else None,
            )
            if not self._pan_mode:
                # reset to default chrome style when off
                self._pan_btn.configure(**style_chrome_button())
                self._pan_btn.configure(text="🖐 Drag view")
        except Exception:  # noqa: BLE001
            pass
        self._set_view_status(
            "Pan mode ON — drag anywhere" if self._pan_mode else "Pan mode off — drag empty / middle-mouse"
        )

    def _set_view_status(self, text: str) -> None:
        try:
            self._view_status.configure(text=text)
        except Exception:  # noqa: BLE001
            pass

    # ----- Canvas layout / pan -----
    def _schedule_scrollregion(self, _e: Any = None) -> None:
        """Debounce scrollregion updates — Configure fires a lot and caused flicker."""
        try:
            if self._scroll_job is not None:
                self.after_cancel(self._scroll_job)
        except Exception:  # noqa: BLE001
            pass
        try:
            self._scroll_job = self.after(80, self._update_scrollregion)
        except Exception:  # noqa: BLE001
            self._update_scrollregion()

    def _on_inner_configure(self, _e: Any = None) -> None:
        self._schedule_scrollregion()

    def _on_canvas_configure(self, _e: Any = None) -> None:
        self._schedule_scrollregion()

    def _update_scrollregion(self) -> None:
        self._scroll_job = None
        if self._rebuild_lock:
            return
        try:
            bbox = self._canvas.bbox(self._win_id)
            if bbox:
                x1, y1, x2, y2 = bbox
                pad = 60
                self._canvas.configure(
                    scrollregion=(x1 - pad, y1 - pad, x2 + pad, y2 + pad)
                )
            else:
                self._canvas.configure(scrollregion=self._canvas.bbox("all") or (0, 0, 100, 100))
        except Exception:  # noqa: BLE001
            pass

    def _pointer_on_canvas(self) -> tuple[int, int]:
        """Event coords may be from child widgets — always map to canvas."""
        try:
            x = int(self._canvas.winfo_pointerx() - self._canvas.winfo_rootx())
            y = int(self._canvas.winfo_pointery() - self._canvas.winfo_rooty())
            return x, y
        except Exception:  # noqa: BLE001
            return 0, 0

    def _pan_start(self, _e: Any = None) -> None:
        x, y = self._pointer_on_canvas()
        self._drag = {
            "active": True,
            "moved": False,
            "x": x,
            "y": y,
            "from_pan_mode": True,
        }
        try:
            self._canvas.scan_mark(x, y)
            self._canvas.configure(cursor="fleur")
        except Exception:  # noqa: BLE001
            pass

    def _pan_move(self, _e: Any = None) -> None:
        if not self._drag.get("active"):
            return
        try:
            x, y = self._pointer_on_canvas()
            if abs(x - int(self._drag.get("x") or 0)) > 2 or abs(
                y - int(self._drag.get("y") or 0)
            ) > 2:
                self._drag["moved"] = True
            self._canvas.scan_dragto(x, y, gain=1)
        except Exception:  # noqa: BLE001
            pass

    def _pan_end(self, _e: Any = None) -> None:
        self._drag["active"] = False
        try:
            self._canvas.configure(cursor="fleur" if self._pan_mode else "arrow")
        except Exception:  # noqa: BLE001
            pass

    def _left_press(self, e: Any) -> None:
        # Canvas empty area, or pan mode — start drag
        if self._pan_mode or e.widget is self._canvas:
            self._pan_start(e)
            self._drag["from_pan_mode"] = self._pan_mode

    def _left_drag(self, e: Any) -> None:
        if self._drag.get("active"):
            self._pan_move(e)

    def _left_release(self, e: Any) -> None:
        was = self._drag.get("active")
        moved = self._drag.get("moved")
        self._pan_end(e)
        if was and moved:
            self._set_view_status("View panned — Reset returns to CEO top")

    def _on_wheel(self, e: Any) -> str | None:
        try:
            delta = int(e.delta)
            steps = -1 if delta > 0 else 1
            self._canvas.yview_scroll(steps, "units")
        except Exception:  # noqa: BLE001
            pass
        return "break"

    def _on_shift_wheel(self, e: Any) -> str | None:
        try:
            delta = int(e.delta)
            steps = -1 if delta > 0 else 1
            self._canvas.xview_scroll(steps, "units")
        except Exception:  # noqa: BLE001
            pass
        return "break"

    def _bind_pan_on_background(self, widget: Any) -> None:
        """Allow drag-pan starting from empty frames (not cards/buttons)."""

        def press(_e: Any) -> None:
            # Only start pan if pan mode OR not over a button-like target
            if self._pan_mode:
                self._pan_start(_e)
            else:
                # Empty frame drag = pan
                self._pan_start(_e)

        def drag(_e: Any) -> None:
            self._pan_move(_e)

        def release(_e: Any) -> None:
            self._left_release(_e)

        widget.bind("<ButtonPress-1>", press, add="+")
        widget.bind("<B1-Motion>", drag, add="+")
        widget.bind("<ButtonRelease-1>", release, add="+")
        widget.bind("<ButtonPress-2>", press, add="+")
        widget.bind("<B2-Motion>", drag, add="+")
        widget.bind("<ButtonRelease-2>", release, add="+")
        widget.bind("<MouseWheel>", self._on_wheel, add="+")

    def _sig(self, graph: dict[str, Any]) -> str:
        """Structure signature — exclude live status (status changes must not rebuild)."""
        parts = []
        for n in graph.get("nodes") or []:
            parts.append(
                f"{n.get('id')}:{n.get('parent_id')}:{n.get('title')}:{n.get('order')}:"
                f"{n.get('type')}:{n.get('enabled')}"
            )
        parts.append("C:" + ",".join(sorted(self._collapsed)))
        return "|".join(parts)

    def set_selection(self, node_id: str | None) -> None:
        """Soft selection only — never rebuild (prevents flicker on every click)."""
        node_id = str(node_id) if node_id else None
        prev = str(self._selected_id) if self._selected_id else None
        if prev == node_id:
            return
        self._selected_id = node_id

        def _style(card: WorkerCard, selected: bool) -> None:
            try:
                card.configure(
                    border_width=3 if selected else 2,
                    border_color=("#2563eb", "#3b82f6") if selected else getattr(
                        card, "_default_border", ("#64748b", "#94a3b8")
                    ),
                    fg_color=("#eff6ff", "#1e3a5f") if selected else ("#ffffff", "#1e293b"),
                )
            except Exception:  # noqa: BLE001
                try:
                    card.configure(
                        border_width=3 if selected else 2,
                        fg_color=("#eff6ff", "#1e3a5f") if selected else ("#ffffff", "#1e293b"),
                    )
                except Exception:  # noqa: BLE001
                    pass

        if prev and prev in self._cards:
            _style(self._cards[prev], False)
        if node_id and node_id in self._cards:
            _style(self._cards[node_id], True)

    def render(self, graph: dict[str, Any], selected_id: str | None = None) -> None:
        """Rebuild chart only when structure/collapse changes; else just reselect."""
        self._graph = graph
        # Drop collapse ids for nodes that no longer exist
        live = {str(n.get("id") or "") for n in (graph.get("nodes") or [])}
        self._collapsed = {i for i in self._collapsed if i in live}
        sig = self._sig(graph)
        if sig == self._structure_sig and self._cards:
            self.set_selection(selected_id)
            return
        self._structure_sig = sig
        self._selected_id = selected_id
        self._rebuild(graph, selected_id)

    def _node_has_children(self, graph: dict[str, Any], nid: str) -> bool:
        from app.services import workflow_graph as wfg

        return bool(wfg.children_of(graph, nid))

    def _rebuild(self, graph: dict[str, Any], selected_id: str | None) -> None:
        self._rebuild_lock = True
        # Freeze geometry noise while destroying/rebuilding
        try:
            self._inner.unbind("<Configure>")
        except Exception:  # noqa: BLE001
            pass

        for w in self._inner.winfo_children():
            try:
                w.destroy()
            except Exception:  # noqa: BLE001
                pass
        self._cards.clear()

        from app.services import workflow_graph as wfg

        muted_line = _line_color(("#94a3b8", "#64748b"))

        ceo = next((n for n in (graph.get("nodes") or []) if n.get("type") == "ceo"), None)
        if not ceo:
            ctk.CTkLabel(
                self._inner,
                text="No AI Workers yet\n\nCreate your first AI Worker",
                text_color=_HC_MUTED,
                font=ctk.CTkFont(size=14),
            ).pack(pady=40)
            self._bind_pan_on_background(self._inner)
            self._finish_rebuild()
            return

        ceo_id = str(ceo.get("id") or "")
        ceo_has_kids = self._node_has_children(graph, ceo_id)
        ceo_collapsed = ceo_id in self._collapsed

        # --- CEO row (centered) ---
        ceo_row = ctk.CTkFrame(self._inner, fg_color="transparent")
        ceo_row.pack(fill="x", pady=(12, 0))
        self._bind_pan_on_background(ceo_row)
        ceo_row.grid_columnconfigure(0, weight=1)
        ceo_row.grid_columnconfigure(1, weight=0)
        ceo_row.grid_columnconfigure(2, weight=1)

        ceo_wrap = ctk.CTkFrame(ceo_row, fg_color="transparent")
        ceo_wrap.grid(row=0, column=1, pady=2)

        if ceo_has_kids:
            ctk.CTkButton(
                ceo_wrap,
                text="▸" if ceo_collapsed else "▾",
                width=28,
                height=28,
                font=ctk.CTkFont(size=14, weight="bold"),
                command=lambda i=ceo_id: self.toggle_node(i),
                **style_chrome_button(),
            ).pack(side="left", padx=(0, 4))

        ceo_item = dict(ceo)
        ceo_item["_is_manager"] = True
        ceo_item["_has_children"] = ceo_has_kids
        ceo_item["_collapsed"] = ceo_collapsed
        ceo_item["_status"] = ceo.get("status") or "idle"
        ceo_card = WorkerCard(
            ceo_wrap,
            ceo_item,
            border_color=("#64748b", "#94a3b8"),
            selected=ceo_id == str(selected_id or ""),
            on_select=self._on_select,
            on_menu=self._menu_at,
            on_add=lambda n: self._on_menu_action("add_child", n),
            width=200,
        )
        ceo_card.pack(side="left")
        self._cards[ceo_id] = ceo_card

        if ceo_collapsed:
            stem = _v_line(self._inner, color=muted_line, height=14, width=40)
            stem.pack()
            ctk.CTkLabel(
                self._inner,
                text="Teams collapsed — click ▸ on CEO or Expand all",
                text_color=_HC_MUTED,
                font=ctk.CTkFont(size=12),
            ).pack(pady=(4, 16))
            self._bind_pan_on_background(self._inner)
            self._finish_rebuild()
            return

        columns = build_branch_columns(graph, collapsed=self._collapsed)
        if not columns:
            stem = _v_line(self._inner, color=muted_line, height=16, width=40)
            stem.pack()
            empty = ctk.CTkFrame(self._inner, fg_color="transparent")
            empty.pack(pady=8)
            self._bind_pan_on_background(empty)
            ctk.CTkButton(
                empty,
                text="+ Add AI Worker under CEO",
                command=lambda: self._on_menu_action("add_child", ceo_item),
                **style_chrome_button(primary=True),
            ).pack()
            self._finish_rebuild()
            return

        # ---- Continuous connectors: CEO stem → horizontal bus → column drops ----
        n_cols = len(columns)
        col_w = 220  # card 168 + gutter + padding
        bus_w = max(col_w, n_cols * col_w)

        # Vertical stem from CEO
        stem = _v_line(self._inner, color=muted_line, height=20, width=40)
        stem.pack()

        # Horizontal bus linking all branch columns
        bus_row = ctk.CTkFrame(self._inner, fg_color="transparent")
        bus_row.pack(fill="x")
        self._bind_pan_on_background(bus_row)
        bus = _h_bus(bus_row, color=muted_line, width=bus_w, height=14)
        bus.pack()
        # T-junction under CEO (center of bus)
        try:
            bx = bus_w // 2
            bus.create_line(bx, 0, bx, 14, fill=muted_line, width=_LINE_W)
            # Drops into each column center
            for i in range(n_cols):
                cx = int((i + 0.5) * (bus_w / n_cols))
                bus.create_line(cx, 7, cx, 14, fill=muted_line, width=_LINE_W)
        except Exception:  # noqa: BLE001
            pass

        branches = ctk.CTkFrame(self._inner, fg_color="transparent")
        branches.pack(fill="both", expand=True, pady=(0, 12), padx=8)
        self._bind_pan_on_background(branches)

        for i, col in enumerate(columns):
            color_pair = _BRANCH_COLORS[col["color_idx"] % len(_BRANCH_COLORS)]
            color = _line_color(color_pair)
            col_frame = ctk.CTkFrame(branches, fg_color="transparent", width=col_w)
            col_frame.pack(side="left", fill="y", padx=6, anchor="n")
            col_frame.pack_propagate(True)
            self._bind_pan_on_background(col_frame)

            # Drop from bus into this column
            drop = _v_line(col_frame, color=color, height=16, width=40)
            drop.pack()

            # continued[i] = keep vertical spine at indent i for following rows
            continued: list[bool] = []

            for node in col["nodes"]:
                depth = int(node.get("_depth") or 0)
                nid = str(node.get("id") or "")
                has_kids = bool(node.get("_has_children"))
                is_col = bool(node.get("_collapsed"))
                is_last = bool(node.get("_is_last_sibling"))

                # Drop deeper flags when walking back up the tree
                continued = continued[:depth]
                while len(continued) < depth:
                    continued.append(False)
                open_above = continued[: max(0, depth - 1)]

                row = ctk.CTkFrame(col_frame, fg_color="transparent")
                row.pack(fill="x", pady=0)

                if depth > 0:
                    gut = _tree_connector(
                        row,
                        depth=depth,
                        is_last=is_last,
                        open_above=open_above,
                        color=color,
                        height=_CARD_H,
                    )
                    gut.pack(side="left")
                else:
                    # Column head: short vertical from drop into card midline
                    head_g = tk.Canvas(
                        row,
                        width=16,
                        height=_CARD_H,
                        highlightthickness=0,
                        bd=0,
                        bg=_canvas_bg(),
                    )
                    head_g.create_line(
                        8, 0, 8, _CARD_H // 2, fill=color, width=_LINE_W
                    )
                    head_g.create_line(
                        8, _CARD_H // 2, 16, _CARD_H // 2, fill=color, width=_LINE_W
                    )
                    head_g.pack(side="left")

                # Keep spine open at this depth if more siblings follow
                if depth >= 1:
                    if len(continued) < depth:
                        continued.extend([False] * (depth - len(continued)))
                    continued[depth - 1] = not is_last
                    continued = continued[:depth]

                if has_kids:
                    ctk.CTkButton(
                        row,
                        text="▸" if is_col else "▾",
                        width=26,
                        height=26,
                        font=ctk.CTkFont(size=13, weight="bold"),
                        command=lambda i=nid: self.toggle_node(i),
                        **style_chrome_button(),
                    ).pack(side="left", padx=(2, 3), pady=(_CARD_H - 26) // 2)
                else:
                    ctk.CTkLabel(row, text="", width=26).pack(side="left")

                card = WorkerCard(
                    row,
                    node,
                    border_color=color_pair,
                    selected=nid == str(selected_id or ""),
                    on_select=self._on_select,
                    on_menu=self._menu_at,
                    on_add=lambda n: self._on_menu_action("add_child", n),
                    width=168,
                )
                card.pack(side="left", pady=4)
                self._cards[nid] = card

                if is_col and has_kids:
                    ctk.CTkLabel(
                        row,
                        text="collapsed",
                        text_color=_HC_MUTED,
                        font=ctk.CTkFont(size=9),
                    ).pack(side="left", padx=4)

        self._bind_pan_on_background(self._inner)
        self._finish_rebuild()

    def _finish_rebuild(self) -> None:
        try:
            self._inner.bind("<Configure>", self._on_inner_configure)
        except Exception:  # noqa: BLE001
            pass
        self._rebuild_lock = False
        self._schedule_scrollregion()

    def _menu_at(self, node: dict[str, Any], x: int, y: int) -> None:
        is_ceo = str(node.get("type") or "") == "ceo"
        handlers = {
            aid: (lambda n, a=aid: self._on_menu_action(a, n))
            for aid, _ in WORKER_MENU_ITEMS
        }
        root = self.winfo_toplevel()
        popup_worker_menu(
            root,
            node,
            x,
            y,
            handlers=handlers,
            is_ceo=is_ceo,
        )
