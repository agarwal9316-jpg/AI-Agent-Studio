"""Microsoft Teams–inspired multi-AI coordination workspace.

Live progress: each helper posts as they finish. Stop button cancels the run.
"""

from __future__ import annotations

import threading
import tkinter.messagebox as messagebox
from typing import TYPE_CHECKING, Any

import customtkinter as ctk

from app.ui.themes import UI as _UI
from app.ui.themes import style_chrome_button, style_card

if TYPE_CHECKING:
    from app.ui.app_window import AppWindow

_HC_MUTED = _UI["muted"]
_HC_LABEL = _UI["label"]


def page_team(app: AppWindow) -> None:
    """Team workspace: channels list · feed · roster."""
    from app.services import team_bg
    from app.services import team_channel as tc
    from app.services import workflow_graph as wfg

    # Ensure content area can grow when user drag-resizes the main window
    try:
        app.content.grid_columnconfigure(0, weight=1)
        app.content.grid_rowconfigure(0, weight=1)
    except Exception:  # noqa: BLE001
        pass

    from app.services import storage as _storage

    root = ctk.CTkFrame(app.content, fg_color="transparent")
    root.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
    # Excel-style columns: left | sash | chat | sash | right
    # Chat (col 2) takes all leftover width
    root.grid_columnconfigure(0, weight=0, minsize=0)
    root.grid_columnconfigure(1, weight=0, minsize=0)
    root.grid_columnconfigure(2, weight=1, minsize=240)
    root.grid_columnconfigure(3, weight=0, minsize=0)
    root.grid_columnconfigure(4, weight=0, minsize=0)
    root.grid_rowconfigure(2, weight=1)

    from app.ui.components.layman_copy import (
        TEAM_CHANNELS,
        TEAM_ROSTER,
        TEAM_FINAL,
        TEAM_EMPTY,
        TEAM_SEND,
        TEAM_RUN,
    )

    def _open_objective_dashboard() -> None:
        cid = state.get("channel_id") or tc.get_active_channel_id()
        ch0 = tc.load_channel(cid) if cid else None
        win = ctk.CTkToplevel(app)
        win.title("Objective dashboard")
        win.geometry("560x520")
        win.transient(app)
        box = ctk.CTkTextbox(win, wrap="word")
        box.pack(fill="both", expand=True, padx=12, pady=12)
        lines = ["OBJECTIVE DASHBOARD", ""]
        if not ch0:
            lines.append("Select or create a Team goal first.")
        else:
            lines.append(f"Channel: {ch0.get('title')}")
            lines.append(f"Objective: {ch0.get('goal') or '—'}")
            lines.append(f"Status: {ch0.get('status')}")
            lines.append(f"Mode: {ch0.get('mode')}")
            lines.append("")
            gid = str(ch0.get("goal_id") or "")
            if gid:
                try:
                    from app.services import company_store as _cs

                    dash = _cs.objective_dashboard(gid)
                    if dash.get("ok"):
                        lines.append(f"Company goal status: {dash.get('status')}")
                        lines.append(
                            f"Assignments: total={dash.get('assignments_total')} "
                            f"active={dash.get('active')} completed={dash.get('completed')} "
                            f"failed={dash.get('failed')}"
                        )
                        lines.append(f"By status: {dash.get('by_status')}")
                        if dash.get("ceo_assessment"):
                            lines.append(f"CEO assessment: {dash.get('ceo_assessment')}")
                        if dash.get("goals"):
                            lines.append("\nGOALS:")
                            for g in dash["goals"][:20]:
                                lines.append(
                                    f"  · [{g.get('status')}] {g.get('title')} ({g.get('kind')})"
                                )
                        if dash.get("open_issues"):
                            lines.append("\nOPEN ISSUES:")
                            for iss in dash["open_issues"][:10]:
                                lines.append(f"  · {iss if not isinstance(iss, dict) else iss.get('text') or iss}")
                except Exception as e:  # noqa: BLE001
                    lines.append(f"(dashboard error: {e})")
            lines.append("\nROSTER:")
            for r in ch0.get("roster") or []:
                lines.append(
                    f"  {r.get('status') or '○'}  {r.get('name')}  ·  {r.get('role')}  ·  {r.get('department')}"
                )
            try:
                from app.services import org_comms

                comms = org_comms.list_comms(objective_id=gid, limit=30) if gid else org_comms.list_comms(limit=20)
                lines.append("\n" + org_comms.format_comm_graph(comms))
            except Exception:  # noqa: BLE001
                pass
        box.insert("1.0", "\n".join(lines))
        box.configure(state="disabled")
        ctk.CTkButton(win, text="Close", command=win.destroy, width=100).pack(pady=8)

    def _open_comms() -> None:
        cid = state.get("channel_id") or tc.get_active_channel_id()
        ch0 = tc.load_channel(cid) if cid else None
        gid = str((ch0 or {}).get("goal_id") or "")
        win = ctk.CTkToplevel(app)
        win.title("Communication history")
        win.geometry("560x480")
        win.transient(app)
        box = ctk.CTkTextbox(win, wrap="word")
        box.pack(fill="both", expand=True, padx=12, pady=12)
        try:
            from app.services import org_comms

            comms = org_comms.list_comms(objective_id=gid, limit=50) if gid else org_comms.list_comms(limit=40)
            box.insert("1.0", org_comms.format_comm_graph(comms))
        except Exception as e:  # noqa: BLE001
            box.insert("1.0", f"No communication data yet.\n{e}")
        box.configure(state="disabled")
        ctk.CTkButton(win, text="Close", command=win.destroy, width=100).pack(pady=8)

    # Header
    app._page_header(
        root,
        "AI Team",
        "Hierarchical AI organisation: Goals | Chat | Members. Drag gray bars to resize. Use Org chart to structure workers.",
        actions=[
            ("← Start", lambda: app.show_page("Home")),
            ("Dashboard", _open_objective_dashboard),
            ("Comms", _open_comms),
            ("New goal", lambda: _open_new_goal_dialog(app, refresh_all, team_ctrl=ctrl)),
        ],
    )

    # Restore column widths from config
    try:
        _cfg0 = _storage.load_config()
        _left_w0 = int(_cfg0.get("team_left_width") or 200)
        _right_w0 = int(_cfg0.get("team_right_width") or 210)
    except Exception:  # noqa: BLE001
        _left_w0, _right_w0 = 200, 210
    _left_w0 = max(140, min(480, _left_w0))
    _right_w0 = max(140, min(480, _right_w0))

    # Local UI mirror — real job lives in team_bg (survives tab switch)
    state: dict[str, Any] = {
        "channel_id": team_bg.channel_id(app) or tc.get_active_channel_id() or "",
        "running": team_bg.is_running(app),
        "stop": False,
        "show_left": True,
        "show_right": True,
        "composer_tall": False,
        "left_w": _left_w0,
        "right_w": _right_w0,
        # Soft-refresh guards (stop full UI thrash while team runs)
        "last_msg_n": -1,
        "last_roster_sig": "",
        "last_feed_refresh_ms": 0.0,
        "poll_token": 0,
    }

    # Shared control object so New goal dialog can start a live run on this page
    ctrl: dict[str, Any] = {
        "state": state,
        "select_channel": None,  # filled after defs
        "refresh_all": None,
        "set_running_ui": None,
        "run_on_channel": None,
        "request_stop": None,
    }

    # ----- Live status banner (always visible) -----
    banner = ctk.CTkFrame(root, fg_color=("#e0f2fe", "#0c4a6e"), corner_radius=10)
    banner.grid(row=1, column=0, columnspan=5, sticky="ew", pady=(0, 6))
    live_lbl = ctk.CTkLabel(
        banner,
        text="Ready — create a New goal or pick one on the left, then Start team.",
        text_color=("#0c4a6e", "#e0f2fe"),
        font=ctk.CTkFont(size=13, weight="bold"),
        anchor="w",
        wraplength=700,
        justify="left",
    )
    live_lbl.pack(side="left", fill="x", expand=True, padx=14, pady=8)
    pause_btn = ctk.CTkButton(
        banner,
        text="⏸ Pause",
        width=100,
        height=32,
        state="disabled",
        command=lambda: request_pause_toggle(),
        **style_chrome_button(),
    )
    pause_btn.pack(side="right", padx=4, pady=6)
    stop_btn = ctk.CTkButton(
        banner,
        text="⏹ Stop team",
        width=120,
        height=32,
        state="disabled",
        fg_color=("#dc2626", "#7f1d1d"),
        hover_color=("#991b1b", "#450a0a"),
        command=lambda: request_stop(),
    )
    stop_btn.pack(side="right", padx=8, pady=6)

    # Layout toggles — full chat control
    layout_bar = ctk.CTkFrame(banner, fg_color="transparent")
    layout_bar.pack(side="right", padx=4)
    left_toggle_btn = ctk.CTkButton(
        layout_bar, text="◀ Goals", width=80, height=28, **style_chrome_button()
    )
    left_toggle_btn.pack(side="left", padx=2)
    right_toggle_btn = ctk.CTkButton(
        layout_bar, text="Members ▶", width=90, height=28, **style_chrome_button()
    )
    right_toggle_btn.pack(side="left", padx=2)
    focus_chat_btn = ctk.CTkButton(
        layout_bar,
        text="⛶ Chat only",
        width=100,
        height=28,
        **style_chrome_button(primary=True),
    )
    focus_chat_btn.pack(side="left", padx=2)

    # ----- Left: channel list (collapsible + width drag) -----
    left = ctk.CTkFrame(root, width=int(state["left_w"]), **style_card())
    left.grid(row=2, column=0, sticky="nsew", padx=(0, 0))
    left.grid_propagate(False)
    left.grid_rowconfigure(3, weight=1)
    left.grid_columnconfigure(0, weight=1)
    ctk.CTkLabel(
        left, text=TEAM_CHANNELS, font=ctk.CTkFont(size=13, weight="bold"), text_color=_HC_LABEL
    ).grid(row=0, column=0, sticky="w", padx=10, pady=(10, 4))
    ctk.CTkButton(
        left,
        text="+ New goal",
        command=lambda: _open_new_goal_dialog(app, refresh_all, team_ctrl=ctrl),
        **style_chrome_button(primary=True),
    ).grid(row=1, column=0, sticky="ew", padx=10, pady=4)
    goal_actions = ctk.CTkFrame(left, fg_color="transparent")
    goal_actions.grid(row=2, column=0, sticky="ew", padx=6, pady=2)
    ch_list = ctk.CTkScrollableFrame(left, fg_color="transparent")
    ch_list.grid(row=3, column=0, sticky="nsew", padx=6, pady=6)
    left.grid_rowconfigure(3, weight=1)

    # ----- Sash: Goals | Chat (drag like Excel column) -----
    sash_l = ctk.CTkFrame(
        root,
        width=8,
        cursor="sb_h_double_arrow",
        fg_color=("#cbd5e1", "#374151"),
        corner_radius=2,
    )
    sash_l.grid(row=2, column=1, sticky="ns", padx=2)
    sash_l.grid_propagate(False)
    ctk.CTkLabel(
        sash_l,
        text="⋮",
        text_color=("#64748b", "#9ca3af"),
        font=ctk.CTkFont(size=11),
    ).place(relx=0.5, rely=0.5, anchor="center")

    # ----- Center: CHAT (primary — grows with window) -----
    center = ctk.CTkFrame(root, **style_card())
    center.grid(row=2, column=2, sticky="nsew", padx=2)
    center.grid_rowconfigure(3, weight=1)
    center.grid_columnconfigure(0, weight=1)

    head = ctk.CTkFrame(center, fg_color="transparent")
    head.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
    title_lbl = ctk.CTkLabel(
        head,
        text="Pick a goal on the left, or create a new one",
        font=ctk.CTkFont(size=16, weight="bold"),
        text_color=_HC_LABEL,
        anchor="w",
    )
    title_lbl.pack(side="left", fill="x", expand=True)
    status_lbl = ctk.CTkLabel(head, text="", text_color=_HC_MUTED, font=ctk.CTkFont(size=12))
    status_lbl.pack(side="right", padx=6)

    # Task #6: living plan strip (updates while team runs)
    plan_box = ctk.CTkFrame(center, fg_color=("#f1f5f9", "#1e293b"), corner_radius=8)
    plan_box.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 4))
    plan_title = ctk.CTkLabel(
        plan_box,
        text="Living plan",
        font=ctk.CTkFont(size=12, weight="bold"),
        text_color=_HC_LABEL,
        anchor="w",
    )
    plan_title.pack(fill="x", padx=10, pady=(6, 0))
    plan_lbl = ctk.CTkLabel(
        plan_box,
        text="Start a team goal to see the live plan here.",
        text_color=_HC_MUTED,
        font=ctk.CTkFont(size=11),
        justify="left",
        anchor="w",
        wraplength=520,
    )
    plan_lbl.pack(fill="x", padx=10, pady=(2, 8))

    # Feed toolbar — always-available user controls
    feed_tools = ctk.CTkFrame(center, fg_color="transparent")
    feed_tools.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 4))

    feed = ctk.CTkScrollableFrame(center, fg_color="transparent")
    feed.grid(row=3, column=0, sticky="nsew", padx=8, pady=4)

    # Composer — full chat control (taller, expand, send/stop)
    composer = ctk.CTkFrame(center, **style_card())
    composer.grid(row=4, column=0, sticky="ew", padx=8, pady=8)
    composer.grid_columnconfigure(0, weight=1)
    ctk.CTkLabel(
        composer,
        text="Write a note to the team  ·  Enter not required — use Send note",
        text_color=_HC_MUTED,
        font=ctk.CTkFont(size=11),
        anchor="w",
    ).grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(8, 2))
    input_box = ctk.CTkTextbox(composer, height=90, font=ctk.CTkFont(size=14), wrap="word")
    input_box.grid(row=1, column=0, sticky="nsew", padx=(10, 6), pady=(0, 10))
    composer.grid_rowconfigure(1, weight=1)
    btn_col = ctk.CTkFrame(composer, fg_color="transparent")
    btn_col.grid(row=1, column=1, sticky="ns", padx=(0, 10), pady=(0, 10))

    # ----- Sash: Chat | Members -----
    sash_r = ctk.CTkFrame(
        root,
        width=8,
        cursor="sb_h_double_arrow",
        fg_color=("#cbd5e1", "#374151"),
        corner_radius=2,
    )
    sash_r.grid(row=2, column=3, sticky="ns", padx=2)
    sash_r.grid_propagate(False)
    ctk.CTkLabel(
        sash_r,
        text="⋮",
        text_color=("#64748b", "#9ca3af"),
        font=ctk.CTkFont(size=11),
    ).place(relx=0.5, rely=0.5, anchor="center")

    # ----- Right: roster (collapsible) -----
    right = ctk.CTkFrame(root, width=int(state["right_w"]), **style_card())
    right.grid(row=2, column=4, sticky="nsew", padx=(0, 0))
    right.grid_propagate(False)
    right.grid_rowconfigure(1, weight=1)
    right.grid_columnconfigure(0, weight=1)
    roster_head = ctk.CTkFrame(right, fg_color="transparent")
    roster_head.grid(row=0, column=0, sticky="ew", padx=6, pady=(10, 4))
    ctk.CTkLabel(
        roster_head, text=TEAM_ROSTER, font=ctk.CTkFont(size=13, weight="bold"), text_color=_HC_LABEL
    ).pack(side="left")
    ctk.CTkButton(
        roster_head,
        text="Org chart",
        width=80,
        height=26,
        command=lambda: app.show_page("Org chart"),
        **style_chrome_button(),
    ).pack(side="right", padx=2)
    roster_box = ctk.CTkScrollableFrame(right, fg_color="transparent")
    roster_box.grid(row=1, column=0, sticky="nsew", padx=6, pady=6)
    prog_lbl = ctk.CTkLabel(
        right,
        text="",
        text_color=_HC_MUTED,
        wraplength=max(120, int(state["right_w"]) - 24),
        justify="left",
    )
    prog_lbl.grid(row=2, column=0, sticky="ew", padx=10, pady=8)

    def _set_left_width(w: int) -> None:
        w = max(140, min(520, int(w)))
        state["left_w"] = w
        try:
            left.configure(width=w)
        except Exception:  # noqa: BLE001
            pass

    def _set_right_width(w: int) -> None:
        w = max(140, min(520, int(w)))
        state["right_w"] = w
        try:
            right.configure(width=w)
            prog_lbl.configure(wraplength=max(100, w - 24))
        except Exception:  # noqa: BLE001
            pass

    def _save_col_widths() -> None:
        try:
            cfg = _storage.load_config()
            cfg["team_left_width"] = int(state.get("left_w") or 200)
            cfg["team_right_width"] = int(state.get("right_w") or 210)
            _storage.save_config(cfg)
        except Exception:  # noqa: BLE001
            pass

    def _bind_sash(sash: Any, *, which: str) -> None:
        """Excel-like column drag on a vertical sash."""
        drag: dict[str, Any] = {"x": 0, "w0": 0}

        def on_enter(_e: Any = None) -> None:
            try:
                sash.configure(fg_color=("#94a3b8", "#4b5563"))
            except Exception:  # noqa: BLE001
                pass

        def on_leave(_e: Any = None) -> None:
            try:
                sash.configure(fg_color=("#cbd5e1", "#374151"))
            except Exception:  # noqa: BLE001
                pass

        def on_press(e: Any) -> None:
            drag["x"] = int(getattr(e, "x_root", 0) or 0)
            drag["w0"] = int(
                state.get("left_w") if which == "left" else state.get("right_w") or 200
            )
            try:
                sash.configure(fg_color=("#3b82f6", "#2563eb"))
            except Exception:  # noqa: BLE001
                pass

        def on_drag(e: Any) -> None:
            x = int(getattr(e, "x_root", 0) or 0)
            dx = x - int(drag.get("x") or x)
            if which == "left":
                # Drag right → wider goals column
                _set_left_width(int(drag["w0"]) + dx)
            else:
                # Drag left (negative dx) → wider members column
                _set_right_width(int(drag["w0"]) - dx)

        def on_release(_e: Any = None) -> None:
            on_leave()
            _save_col_widths()
            app.set_status(
                f"Columns: Goals {state.get('left_w')}px · Members {state.get('right_w')}px",
                toast=False,
            )

        for seq, fn in (
            ("<Enter>", on_enter),
            ("<Leave>", on_leave),
            ("<ButtonPress-1>", on_press),
            ("<B1-Motion>", on_drag),
            ("<ButtonRelease-1>", on_release),
        ):
            try:
                sash.bind(seq, fn)
                for child in sash.winfo_children():
                    child.bind(seq, fn)
            except Exception:  # noqa: BLE001
                pass

    _bind_sash(sash_l, which="left")
    _bind_sash(sash_r, which="right")

    def _apply_side_panels() -> None:
        """Show/hide goals & members so chat can use the full window."""
        try:
            if state.get("show_left"):
                left.grid()
                sash_l.grid()
                left_toggle_btn.configure(text="◀ Goals")
                _set_left_width(int(state.get("left_w") or 200))
            else:
                left.grid_remove()
                sash_l.grid_remove()
                left_toggle_btn.configure(text="▶ Goals")
            if state.get("show_right"):
                right.grid()
                sash_r.grid()
                right_toggle_btn.configure(text="Members ▶")
                _set_right_width(int(state.get("right_w") or 210))
            else:
                right.grid_remove()
                sash_r.grid_remove()
                right_toggle_btn.configure(text="◀ Members")
            # When both hidden, chat is true full-bleed
            if not state.get("show_left") and not state.get("show_right"):
                focus_chat_btn.configure(text="◫ Show sides")
            else:
                focus_chat_btn.configure(text="⛶ Chat only")
            try:
                live_lbl.configure(wraplength=max(400, int(app.winfo_width() or 800) - 360))
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            pass

    def toggle_left() -> None:
        state["show_left"] = not state.get("show_left", True)
        _apply_side_panels()

    def toggle_right() -> None:
        state["show_right"] = not state.get("show_right", True)
        _apply_side_panels()

    def toggle_focus_chat() -> None:
        if state.get("show_left") or state.get("show_right"):
            state["show_left"] = False
            state["show_right"] = False
        else:
            state["show_left"] = True
            state["show_right"] = True
        _apply_side_panels()

    left_toggle_btn.configure(command=toggle_left)
    right_toggle_btn.configure(command=toggle_right)
    focus_chat_btn.configure(command=toggle_focus_chat)
    _apply_side_panels()

    def toggle_composer_height() -> None:
        state["composer_tall"] = not state.get("composer_tall")
        try:
            input_box.configure(height=180 if state["composer_tall"] else 90)
            tall_btn.configure(text="▲ Smaller box" if state["composer_tall"] else "▼ Bigger box")
        except Exception:  # noqa: BLE001
            pass

    tall_btn = ctk.CTkButton(
        btn_col,
        text="▼ Bigger box",
        width=110,
        command=toggle_composer_height,
        **style_chrome_button(),
    )
    tall_btn.pack(pady=2)

    def set_live(msg: str, *, busy: bool = False) -> None:
        try:
            if not live_lbl.winfo_exists():
                return
            live_lbl.configure(text=msg[:280] if msg else "")
            if busy:
                banner.configure(fg_color=("#fef3c7", "#422006"))
                live_lbl.configure(text_color=("#92400e", "#fde68a"))
            else:
                banner.configure(fg_color=("#e0f2fe", "#0c4a6e"))
                live_lbl.configure(text_color=("#0c4a6e", "#e0f2fe"))
        except Exception:  # noqa: BLE001
            pass

    def set_running_ui(on: bool) -> None:
        state["running"] = on
        try:
            if on:
                stop_btn.configure(state="normal")
                pause_btn.configure(state="normal", text="⏸ Pause")
                run_btn.configure(state="disabled", text="Working…")
            else:
                stop_btn.configure(state="disabled")
                pause_btn.configure(state="disabled", text="⏸ Pause")
                run_btn.configure(state="normal", text=TEAM_RUN)
        except Exception:  # noqa: BLE001
            pass

    def request_pause_toggle() -> None:
        if not team_bg.is_running(app) and not state.get("running"):
            set_live("Nothing is running right now.")
            return
        now_paused = team_bg.toggle_pause(app)
        try:
            pause_btn.configure(text="▶ Resume" if now_paused else "⏸ Pause")
        except Exception:  # noqa: BLE001
            pass
        if now_paused:
            set_live("⏸ Paused — current helper may finish, then waits. Press Resume.", busy=True)
        else:
            set_live("▶ Resumed — team continuing…", busy=True)

    def request_stop() -> None:
        if not team_bg.is_running(app) and not state.get("running"):
            set_live("Nothing is running right now.")
            return
        state["stop"] = True
        team_bg.request_stop(app)
        try:
            pause_btn.configure(text="⏸ Pause")
        except Exception:  # noqa: BLE001
            pass
        set_live("Stopping… will finish the current helper, then cancel.", busy=True)

    def refresh_channel_list() -> None:
        for w in ch_list.winfo_children():
            w.destroy()
        for summary in tc.list_channels(limit=40):
            cid = str(summary.get("id") or "")
            # Auto-repair stuck "running" with finished answer
            try:
                tc.repair_stuck_channel(cid)
                summary = next(
                    (x for x in tc.list_channels(limit=40) if x.get("id") == cid),
                    summary,
                )
            except Exception:  # noqa: BLE001
                pass
            st = str(summary.get("status") or "")
            st_show = {
                "done": "✓ done",
                "running": "● working",
                "failed": "✗ failed",
                "cancelled": "⏹ stopped",
                "open": "○ open",
            }.get(st, st)
            lab = f"{summary.get('title') or 'Goal'}\n{st_show}"
            active = cid == state.get("channel_id")
            ctk.CTkButton(
                ch_list,
                text=lab[:80],
                anchor="w",
                height=48,
                fg_color=_UI.get("sidebar_active") if active else "transparent",
                command=lambda i=cid: select_channel(i),
            ).pack(fill="x", pady=2)
        _rebuild_goal_actions()

    def _rebuild_goal_actions() -> None:
        for w in goal_actions.winfo_children():
            w.destroy()
        cid = state.get("channel_id")
        if not cid:
            ctk.CTkLabel(
                goal_actions,
                text="Select a goal to edit/delete",
                text_color=_HC_MUTED,
                font=ctk.CTkFont(size=10),
            ).pack(anchor="w", padx=4)
            return
        row1 = ctk.CTkFrame(goal_actions, fg_color="transparent")
        row1.pack(fill="x", pady=1)
        ctk.CTkButton(
            row1, text="✏ Edit", width=70, height=26, command=lambda: _edit_goal(cid), **style_chrome_button()
        ).pack(side="left", padx=1)
        ctk.CTkButton(
            row1, text="✓ Done", width=70, height=26, command=lambda: _mark_done(cid), **style_chrome_button()
        ).pack(side="left", padx=1)
        row2 = ctk.CTkFrame(goal_actions, fg_color="transparent")
        row2.pack(fill="x", pady=1)
        ctk.CTkButton(
            row2, text="🗑 Delete", width=70, height=26, command=lambda: _delete_goal(cid),
            fg_color=("#dc2626", "#7f1d1d"), hover_color=("#991b1b", "#450a0a"),
        ).pack(side="left", padx=1)
        ctk.CTkButton(
            row2, text="Fix stuck", width=80, height=26, command=lambda: _fix_stuck(cid), **style_chrome_button()
        ).pack(side="left", padx=1)

    def _edit_goal(cid: str) -> None:
        ch = tc.load_channel(cid)
        if not ch:
            return
        win = ctk.CTkToplevel(app)
        win.title("Edit goal")
        win.geometry("520x420")
        win.minsize(400, 320)
        try:
            win.transient(app)
            win.resizable(True, True)
        except Exception:  # noqa: BLE001
            pass
        ctk.CTkLabel(win, text="Title", text_color=_HC_MUTED).pack(anchor="w", padx=14, pady=(12, 2))
        title_e = ctk.CTkEntry(win)
        title_e.pack(fill="x", padx=14, pady=4)
        title_e.insert(0, str(ch.get("title") or ""))
        ctk.CTkLabel(win, text="Goal (what you want done)", text_color=_HC_MUTED).pack(
            anchor="w", padx=14, pady=(8, 2)
        )
        goal_e = ctk.CTkTextbox(win, height=160, wrap="word")
        goal_e.pack(fill="both", expand=True, padx=14, pady=4)
        goal_e.insert("1.0", str(ch.get("goal") or ""))
        ctk.CTkLabel(
            win,
            text="Tip: short, finite goals finish better. Example: “List 5 public Telegram news channels with t.me links.”",
            text_color=_HC_MUTED,
            font=ctk.CTkFont(size=11),
            wraplength=480,
            justify="left",
        ).pack(anchor="w", padx=14, pady=4)

        def save() -> None:
            tc.update_channel(
                cid,
                title=title_e.get().strip(),
                goal=goal_e.get("1.0", "end").strip(),
            )
            try:
                win.destroy()
            except Exception:  # noqa: BLE001
                pass
            select_channel(cid)
            app.set_status("Goal updated — press Start team to run again", toast=True)

        bar = ctk.CTkFrame(win, fg_color="transparent")
        bar.pack(fill="x", padx=14, pady=12)
        ctk.CTkButton(bar, text="Save changes", command=save, **style_chrome_button(primary=True)).pack(
            side="left", padx=4
        )
        ctk.CTkButton(bar, text="Cancel", command=win.destroy, width=90).pack(side="left", padx=4)

    def _delete_goal(cid: str) -> None:
        ch = tc.load_channel(cid)
        title = (ch or {}).get("title") or "this goal"
        if not messagebox.askyesno(
            "Delete goal",
            f"Delete “{title}” forever?\n\nMessages and finished answer will be removed.",
            parent=app,
        ):
            return
        if team_bg.is_running(app) and team_bg.channel_id(app) == cid:
            team_bg.request_stop(app)
        tc.delete_channel(cid)
        state["channel_id"] = tc.get_active_channel_id() or ""
        refresh_all()
        app.set_status("Goal deleted", toast=True)

    def _mark_done(cid: str) -> None:
        ch = tc.load_channel(cid)
        if not ch:
            return
        final = str(ch.get("final_text") or "").strip()
        if not final:
            # Use last CEO/agent message as finished answer if any
            for m in reversed(ch.get("messages") or []):
                if (m.get("role") or "") in ("ceo", "agent") and (m.get("content") or "").strip():
                    final = str(m.get("content") or "").strip()
                    break
        if not final:
            final = f"(Marked done by user)\n\nGoal was:\n{ch.get('goal') or ''}"
        tc.set_final(ch, final)
        select_channel(cid)
        app.set_status("Marked complete ✓", toast=True)

    def _fix_stuck(cid: str) -> None:
        ch = tc.repair_stuck_channel(cid)
        if ch:
            select_channel(cid)
            app.set_status(f"Fixed · status={ch.get('status')}", toast=True)
        else:
            app.set_status("Could not fix goal", toast=True)

    def render_roster(ch: dict[str, Any] | None) -> None:
        """Members panel: hierarchical org when chart available, else channel roster."""
        for w in roster_box.winfo_children():
            w.destroy()
        icons = {
            "waiting": "○",
            "working": "●",
            "running": "●",
            "done": "✓",
            "completed": "✓",
            "failed": "✗",
            "error": "✗",
            "blocked": "◐",
            "idle": "○",
            "disabled": "⊘",
        }
        # Live status by org_node_id from channel roster
        status_by_node: dict[str, str] = {}
        if ch:
            for r in ch.get("roster") or []:
                nid = str(r.get("org_node_id") or "")
                if nid:
                    status_by_node[nid] = str(r.get("status") or "waiting")

        graph = None
        try:
            gid = str((ch or {}).get("org_graph_id") or "") if ch else ""
            graph = wfg.resolve_graph(graph_id=gid or None)
        except Exception:  # noqa: BLE001
            graph = None

        if graph and (graph.get("nodes") or []):
            ctk.CTkLabel(
                roster_box,
                text=f"Org: {graph.get('name') or 'Team'}",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=_HC_MUTED,
                anchor="w",
            ).pack(fill="x", padx=4, pady=(0, 4))

            def _add_under(node: dict[str, Any]) -> None:
                try:
                    child = wfg.add_ai_worker(
                        graph,
                        parent_id=str(node.get("id")),
                        title="New AI Worker",
                        role="Specialist",
                    )
                except Exception as e:  # noqa: BLE001
                    messagebox.showerror("Add AI Worker", str(e), parent=app)
                    return
                try:
                    from app.ui.pages.org_worker_dialogs import open_worker_config

                    open_worker_config(
                        app,
                        child,
                        wfg.get_graph(str(graph.get("id"))) or graph,
                        on_saved=lambda: render_roster(ch),
                    )
                except Exception:  # noqa: BLE001
                    pass
                render_roster(ch)
                app.set_status(f"Added AI Worker under {node.get('title')}", toast=True)

            def _inspect_node(node: dict[str, Any]) -> None:
                try:
                    from app.ui.pages.org_worker_dialogs import open_worker_inspector

                    open_worker_inspector(app, node=node, summary_only=True)
                except Exception as e:  # noqa: BLE001
                    messagebox.showinfo("Inspector", str(e), parent=app)

            for n in wfg.walk_tree(graph):
                d = int(n.get("_depth") or 0)
                pad = "  " * min(d, 6)
                nid = str(n.get("id") or "")
                st = status_by_node.get(nid) or n.get("_status") or n.get("status") or "idle"
                t = n.get("type")
                if t == "ceo":
                    tag = "CEO"
                elif t == "department":
                    tag = "DEPT"
                elif n.get("_is_manager"):
                    tag = "MGR"
                else:
                    tag = "W"
                row = ctk.CTkFrame(roster_box, fg_color="transparent")
                row.pack(fill="x", pady=1)
                color = tc.avatar_color(str(n.get("title") or "?"))
                av = ctk.CTkLabel(
                    row,
                    text=(str(n.get("title") or "?")[:1]).upper(),
                    width=24,
                    height=24,
                    corner_radius=12,
                    fg_color=color,
                    text_color=("#fff", "#fff"),
                    font=ctk.CTkFont(size=11, weight="bold"),
                )
                av.pack(side="left", padx=(2, 4))
                ctk.CTkLabel(
                    row,
                    text=f"{pad}{icons.get(st, '○')} [{tag}] {n.get('title')}",
                    anchor="w",
                    text_color=_HC_LABEL,
                    font=ctk.CTkFont(size=11),
                ).pack(side="left", fill="x", expand=True)
                ctk.CTkButton(
                    row,
                    text="+",
                    width=26,
                    height=24,
                    command=lambda node=n: _add_under(node),
                    **style_chrome_button(primary=True),
                ).pack(side="right", padx=1)
                ctk.CTkButton(
                    row,
                    text="i",
                    width=26,
                    height=24,
                    command=lambda node=n: _inspect_node(node),
                    **style_chrome_button(),
                ).pack(side="right", padx=1)
        elif ch and (ch.get("roster") or []):
            for r in ch.get("roster") or []:
                st = str(r.get("status") or "waiting")
                row = ctk.CTkFrame(roster_box, fg_color="transparent")
                row.pack(fill="x", pady=3)
                color = tc.avatar_color(str(r.get("name") or "?"))
                av = ctk.CTkLabel(
                    row,
                    text=(str(r.get("name") or "?")[:1]).upper(),
                    width=28,
                    height=28,
                    corner_radius=14,
                    fg_color=color,
                    text_color=("#fff", "#fff"),
                    font=ctk.CTkFont(size=12, weight="bold"),
                )
                av.pack(side="left", padx=(2, 6))
                ctk.CTkLabel(
                    row,
                    text=f"{icons.get(st, '○')} {r.get('name')}\n{r.get('role')} · {r.get('department')}",
                    anchor="w",
                    justify="left",
                    text_color=_HC_LABEL,
                    font=ctk.CTkFont(size=11),
                ).pack(side="left", fill="x", expand=True)
        else:
            ctk.CTkLabel(
                roster_box,
                text="No AI Workers yet\n\nOpen Org chart or create a goal\nto load the organisation.",
                text_color=_HC_MUTED,
                justify="left",
            ).pack(pady=12)
            ctk.CTkButton(
                roster_box,
                text="+ Add AI Worker",
                command=lambda: app.show_page("Org chart"),
                **style_chrome_button(primary=True),
            ).pack(pady=4)

        if ch:
            done = sum(1 for r in (ch.get("roster") or []) if r.get("status") == "done")
            total = len(ch.get("roster") or []) or 1
            mode = str(ch.get("mode") or "")
            mode_txt = (
                "one by one"
                if mode == "pipeline"
                else ("discuss together" if mode == "coordinate" else mode)
            )
            max_r = int((ch.get("settings") or {}).get("max_rounds") or 12)
            # Objective dashboard strip
            try:
                from app.services import company_store as _cs

                gid_goal = str(ch.get("goal_id") or "")
                dash_txt = ""
                if gid_goal:
                    dash = _cs.objective_dashboard(gid_goal)
                    if dash.get("ok"):
                        dash_txt = (
                            f"\nObj: {dash.get('status')} · "
                            f"active {dash.get('active')} · done {dash.get('completed')}"
                        )
            except Exception:  # noqa: BLE001
                dash_txt = ""
            prog_lbl.configure(
                text=(
                    f"{done}/{total} finished · {mode_txt}\n"
                    f"Turn {ch.get('round') or 0}/{max_r} · Stop anytime"
                    f"{dash_txt}"
                )
            )
        else:
            prog_lbl.configure(text="Create a New goal to run the AI organisation.")

    def _scroll_feed_end() -> None:
        try:
            feed._parent_canvas.yview_moveto(1.0)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            try:
                feed._scrollbar.set(1.0, 1.0)  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                pass

    def _clear_team_chat(ch: dict[str, Any] | None) -> None:
        if not ch or not ch.get("id"):
            app.set_status("Select a goal first", toast=True)
            return
        cid = str(ch.get("id"))
        if team_bg.is_running(app) and team_bg.channel_id(app) == cid:
            messagebox.showinfo(
                "Team still working",
                "Stop the team first (Stop team), then clear chat.",
                parent=app,
            )
            return
        n = len(ch.get("messages") or [])
        if not messagebox.askyesno(
            "Clear chat",
            f"Clear all {n} message(s) in this goal?\n\n"
            "• Goal title and goal text are kept\n"
            "• Finished answer is cleared\n"
            "• You can Start team again for a clean run",
            parent=app,
        ):
            return
        cleared = tc.clear_channel_messages(cid, keep_goal=True, clear_final=True)
        if cleared:
            select_channel(cid)
            app.set_status("Team chat cleared", toast=True)
        else:
            app.set_status("Could not clear chat", toast=True)

    def _feed_copy_all(ch: dict[str, Any] | None) -> None:
        from app.ui.components.message_box import copy_text

        if not ch:
            return
        lines: list[str] = [
            f"# {ch.get('title') or 'Goal'}",
            f"Goal: {ch.get('goal') or ''}",
            f"Status: {ch.get('status') or ''}",
            "",
        ]
        for m in ch.get("messages") or []:
            who = m.get("agent_name") or m.get("role") or "?"
            when = str(m.get("at") or "")[11:19]
            lines.append(f"## {who} ({when})")
            lines.append(str(m.get("content") or ""))
            lines.append("")
        if ch.get("final_text"):
            lines.append("## FINISHED ANSWER")
            lines.append(str(ch.get("final_text") or ""))
        copy_text(app, "\n".join(lines))

    def _feed_open_final(ch: dict[str, Any] | None) -> None:
        from app.ui.components.message_box import open_maximized_message

        if not ch or not ch.get("final_text"):
            app.set_status("No finished answer yet", toast=True)
            return
        open_maximized_message(
            app,
            title=f"Finished answer — {ch.get('title') or 'Goal'}",
            body=str(ch.get("final_text") or ""),
            subtitle="Select text · Ctrl+C · click blue links",
        )

    def _rebuild_feed_tools(ch: dict[str, Any] | None) -> None:
        for w in feed_tools.winfo_children():
            w.destroy()
        ctk.CTkLabel(
            feed_tools,
            text="Chat: select · Ctrl+C · blue links · Expand · Big",
            text_color=_HC_MUTED,
            font=ctk.CTkFont(size=11),
        ).pack(side="left", padx=(2, 8))
        ctk.CTkButton(
            feed_tools,
            text="📋 Copy all",
            width=100,
            height=28,
            command=lambda: _feed_copy_all(ch),
            **style_chrome_button(),
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            feed_tools,
            text="🗑 Clear chat",
            width=100,
            height=28,
            command=lambda: _clear_team_chat(ch),
            fg_color=("#dc2626", "#7f1d1d"),
            hover_color=("#991b1b", "#450a0a"),
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            feed_tools,
            text="⛶ Finished answer",
            width=140,
            height=28,
            command=lambda: _feed_open_final(ch),
            **style_chrome_button(primary=bool(ch and ch.get("final_text"))),
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            feed_tools,
            text="↓ Latest",
            width=80,
            height=28,
            command=lambda: _scroll_feed_end(),
            **style_chrome_button(),
        ).pack(side="left", padx=2)
        n_msg = len((ch or {}).get("messages") or []) if ch else 0
        ctk.CTkLabel(
            feed_tools,
            text=f"{n_msg} message(s)",
            text_color=_HC_MUTED,
            font=ctk.CTkFont(size=11),
        ).pack(side="right", padx=6)

    def _render_living_plan(ch: dict[str, Any] | None) -> None:
        try:
            if not ch:
                plan_lbl.configure(text="Start a team goal to see the live plan here.")
                return
            txt = tc.format_living_plan(ch)
            if not txt:
                txt = "Plan will appear when the team starts…"
            # Keep final note obvious when done
            if ch.get("final_text"):
                txt = (txt + "\n\n✓ Finished answer is ready below (green card).").strip()
            plan_lbl.configure(text=txt[:900])
            try:
                plan_lbl.configure(wraplength=max(280, int(center.winfo_width()) - 40))
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            pass

    def render_feed(ch: dict[str, Any] | None) -> None:
        for w in feed.winfo_children():
            w.destroy()
        _rebuild_feed_tools(ch)
        _render_living_plan(ch)
        if not ch:
            ctk.CTkLabel(
                feed,
                text=TEAM_EMPTY,
                text_color=_HC_MUTED,
            ).pack(pady=40)
            return
        title_lbl.configure(text=f"{ch.get('title') or 'Goal'}")
        status_lbl.configure(text=str(ch.get("status") or ""))
        for m in ch.get("messages") or []:
            _render_message_card(feed, m, app=app)
        # Final answer as proper chat box (selectable, maximize, links)
        # Always clean once more for older channels
        final = tc.clean_team_final_text(str(ch.get("final_text") or ""))
        if final:
            from app.ui.components.message_box import render_final_answer_card

            render_final_answer_card(
                feed,
                app=app,
                text=final,
                title=TEAM_FINAL,
            )

    def select_channel(cid: str) -> None:
        state["channel_id"] = cid
        tc.set_active_channel_id(cid)
        ch = tc.load_channel(cid)
        refresh_channel_list()
        render_feed(ch)
        render_roster(ch)

    def refresh_all() -> None:
        refresh_channel_list()
        cid = state.get("channel_id") or tc.get_active_channel_id()
        if cid:
            select_channel(cid)
        else:
            render_feed(None)
            render_roster(None)

    def _roster_sig(ch: dict[str, Any] | None) -> str:
        if not ch:
            return ""
        return "|".join(
            f"{r.get('name')}:{r.get('status')}" for r in (ch.get("roster") or [])
        )

    def _soft_refresh_feed(ch: dict[str, Any] | None, *, force: bool = False) -> None:
        """Rebuild message list only when data actually changed (or forced)."""
        import time as _time

        if not ch:
            return
        n = len(ch.get("messages") or [])
        sig = _roster_sig(ch)
        now = _time.time()
        # At most one full rebuild every 2.5s unless message count / roster changed
        changed = n != state.get("last_msg_n") or sig != state.get("last_roster_sig")
        if not force and not changed:
            return
        if not force and (now - float(state.get("last_feed_refresh_ms") or 0)) < 2.5:
            # Still allow if message count jumped (new posts)
            if n <= int(state.get("last_msg_n") or 0):
                return
        state["last_msg_n"] = n
        state["last_roster_sig"] = sig
        state["last_feed_refresh_ms"] = now
        try:
            render_feed(ch)
            render_roster(ch)
        except Exception:  # noqa: BLE001
            pass

    def ui_progress(msg: str, *, busy: bool = True) -> None:
        """Update banner only — do NOT rebuild the whole page every progress tick."""
        try:
            if not app.winfo_exists() or getattr(app, "_current_page", "") != "Team":
                return
            set_live(msg, busy=busy)
            try:
                if prog_lbl.winfo_exists():
                    prog_lbl.configure(text=(msg or "")[:200])
            except Exception:  # noqa: BLE001
                pass
            # Soft feed update only when channel gained messages (not every "thinking…" line)
            cid = team_bg.channel_id(app) or state.get("channel_id")
            if not cid:
                return
            if state.get("channel_id") != cid:
                state["channel_id"] = cid
            ch2 = tc.load_channel(cid)
            if ch2:
                _soft_refresh_feed(ch2, force=False)
        except Exception:  # noqa: BLE001
            pass

    def post_user() -> None:
        cid = state.get("channel_id")
        if not cid:
            messagebox.showinfo("Team", "Select or create a goal first.", parent=app)
            return
        text = input_box.get("1.0", "end").strip()
        if not text:
            return
        ch = tc.load_channel(cid)
        if not ch:
            return
        tc.append_message(ch, role="user", agent_name="You", agent_role="user", content=text)
        input_box.delete("1.0", "end")
        select_channel(cid)
        app.set_status("Note posted to the team", toast=True)

    def run_on_channel(cid: str, *, reset_if_done: bool = True) -> None:
        """Start pipeline/coordinate in app-level background (survives tab switch)."""
        if team_bg.is_running(app):
            app.set_status("Team already running in background — press Stop first", toast=True)
            set_live(team_bg.last_progress(app) or "Already running in background…", busy=True)
            return
        if not tc.load_channel(cid):
            return
        state["channel_id"] = cid
        state["stop"] = False
        set_running_ui(True)
        set_live(
            "Team is working in the background. You can open Chat or other pages — it will keep going.",
            busy=True,
        )
        select_channel(cid)

        def on_done(_res: dict[str, Any]) -> None:
            set_running_ui(False)
            state["stop"] = False
            try:
                if getattr(app, "_current_page", "") == "Team":
                    select_channel(cid)
            except Exception:  # noqa: BLE001
                pass

        team_bg.start_on_channel(app, cid, reset_if_done=reset_if_done, on_done=on_done)
        _start_page_poll()

    def _start_page_poll() -> None:
        """Light poll while running — never thrash full UI every tick."""
        # Invalidate any previous poll loop from an earlier Start click
        state["poll_token"] = int(state.get("poll_token") or 0) + 1
        my_token = int(state["poll_token"])

        def poll() -> None:
            if int(state.get("poll_token") or 0) != my_token:
                return  # superseded by a newer Start
            if not app.winfo_exists() or getattr(app, "_current_page", "") != "Team":
                return
            running = team_bg.is_running(app)
            set_running_ui(running)
            if not running:
                cid2 = team_bg.channel_id(app) or state.get("channel_id")
                if cid2:
                    try:
                        ch_done = tc.load_channel(cid2)
                        _soft_refresh_feed(ch_done, force=True)
                        refresh_channel_list()
                    except Exception:  # noqa: BLE001
                        pass
                return
            cid2 = team_bg.channel_id(app) or state.get("channel_id")
            prog = team_bg.last_progress(app)
            if prog:
                set_live(prog, busy=True)
                try:
                    if prog_lbl.winfo_exists():
                        prog_lbl.configure(text=prog[:200])
                except Exception:  # noqa: BLE001
                    pass
            if cid2:
                ch2 = tc.load_channel(cid2)
                if ch2:
                    _soft_refresh_feed(ch2, force=False)
            try:
                app.after(3000, poll)  # slower poll = less flicker
            except Exception:  # noqa: BLE001
                pass

        try:
            app.after(2500, poll)
        except Exception:  # noqa: BLE001
            pass

    def run_team() -> None:
        cid = state.get("channel_id")
        if not cid:
            _open_new_goal_dialog(app, refresh_all, team_ctrl=ctrl, auto_run=True)
            return
        run_on_channel(cid, reset_if_done=True)

    ctk.CTkButton(
        btn_col, text=TEAM_SEND, width=100, command=post_user, **style_chrome_button()
    ).pack(pady=2)
    run_btn = ctk.CTkButton(
        btn_col, text=TEAM_RUN, width=110, command=run_team, **style_chrome_button(primary=True)
    )
    run_btn.pack(pady=2)
    ctk.CTkButton(
        btn_col,
        text="⏹ Stop",
        width=100,
        command=request_stop,
        fg_color=("#dc2626", "#7f1d1d"),
        hover_color=("#991b1b", "#450a0a"),
    ).pack(pady=2)

    # Wire ctrl for New goal dialog
    ctrl["select_channel"] = select_channel
    ctrl["refresh_all"] = refresh_all
    ctrl["set_running_ui"] = set_running_ui
    ctrl["run_on_channel"] = run_on_channel
    ctrl["request_stop"] = request_stop
    ctrl["ui_progress"] = ui_progress
    ctrl["set_live"] = set_live
    ctrl["state"] = state

    # Background job hooks (must outlive this page)
    team_bg.bind_page_progress(app, ui_progress)
    app._team_page_refresh = refresh_all  # type: ignore[attr-defined]
    app._team_select_channel = select_channel  # type: ignore[attr-defined]
    app._team_ctrl = ctrl  # type: ignore[attr-defined]
    app._team_request_stop = request_stop  # type: ignore[attr-defined]

    refresh_all()

    # Reconnect UI if a job is already running in the background
    if team_bg.is_running(app):
        cid_bg = team_bg.channel_id(app)
        if cid_bg:
            state["channel_id"] = cid_bg
            select_channel(cid_bg)
        set_running_ui(True)
        set_live(
            team_bg.last_progress(app)
            or "Team still working in background… (you left and came back — that is fine)",
            busy=True,
        )
        _start_page_poll()
    else:
        set_live(
            "Ready — create a New goal or pick one on the left, then Start team. "
            "You can switch tabs while it works.",
            busy=False,
        )


def _render_message_card(parent: Any, m: dict[str, Any], *, app: Any = None) -> None:
    from app.services import team_channel as tc
    from app.ui.components.message_box import render_chat_message_card

    name = str(m.get("agent_name") or m.get("role") or "?")
    role = str(m.get("agent_role") or m.get("role") or "")
    body = str(m.get("content") or "")
    at = str(m.get("at") or "")[11:19]
    color = tc.avatar_color(name)
    role_l = str(m.get("role") or "").lower()
    if role_l in ("user",) or name.lower() in ("you", "user"):
        kind = "user"
    elif role_l in ("ceo",) or "ceo" in name.lower() or "planner" in name.lower():
        kind = "ceo"
    elif role_l in ("system",) or name.lower() in ("system", "progress"):
        kind = "system"
    else:
        kind = "agent"

    render_chat_message_card(
        parent,
        app=app,
        name=name,
        role=role,
        body=body,
        at=at,
        avatar_color=color,
        kind=kind,
    )


def _open_new_goal_dialog(
    app: AppWindow,
    on_done: Any,
    *,
    auto_run: bool = False,
    team_ctrl: dict[str, Any] | None = None,
) -> None:
    from app.services import workflow_graph as wfg
    from app.core.services.company.team_coordinator import start_team_goal

    from app.ui.components.layman_copy import (
        TEAM_NEW_TITLE,
        TEAM_NEW_HINT,
        TEAM_ORG_LABEL,
        TEAM_ORG_AUTO,
        TEAM_MODE_LABEL,
        TEAM_MODE_PIPELINE,
        TEAM_MODE_COORDINATE,
        TEAM_MODE_HINT,
        TEAM_RUN,
    )

    win = ctk.CTkToplevel(app)
    win.title(TEAM_NEW_TITLE)
    win.geometry("580x620")
    win.transient(app)

    ctk.CTkLabel(
        win,
        text=TEAM_NEW_HINT,
        text_color=_HC_MUTED,
        wraplength=540,
        justify="left",
    ).pack(anchor="w", padx=16, pady=(14, 6))

    tip = ctk.CTkFrame(win, fg_color=("#ecfdf5", "#14532d"), corner_radius=8)
    tip.pack(fill="x", padx=16, pady=(0, 6))
    ctk.CTkLabel(
        tip,
        text=(
            "Goals that finish well:\n"
            "• Prefer “One by one” (not Discuss)\n"
            "• Max turns 4–6\n"
            "• Finite ask: “List 5 items with links” not “find everything forever”\n"
            "• Team chat has no live Telegram browser — it drafts from knowledge, then you verify links"
        ),
        text_color=("#166534", "#bbf7d0"),
        font=ctk.CTkFont(size=11),
        justify="left",
        wraplength=520,
    ).pack(anchor="w", padx=10, pady=8)

    title_e = ctk.CTkEntry(win, placeholder_text="Short title (optional) — e.g. Launch plan")
    title_e.pack(fill="x", padx=16, pady=4)
    goal_box = ctk.CTkTextbox(win, height=100)
    goal_box.pack(fill="both", expand=True, padx=16, pady=6)
    goal_box.insert("1.0", "Example: List 5 public Telegram news channels with working t.me links and a one-line note each.")

    graphs = wfg.list_graphs()
    gmap = {str(g.get("name") or g["id"][:8]): str(g["id"]) for g in graphs}
    org_labels = [TEAM_ORG_AUTO] + list(gmap.keys())
    org_var = ctk.StringVar(master=win, value=org_labels[0] if org_labels else TEAM_ORG_AUTO)
    mode_display = ctk.StringVar(master=win, value=TEAM_MODE_PIPELINE)
    mode_map = {
        TEAM_MODE_PIPELINE: "pipeline",
        TEAM_MODE_COORDINATE: "coordinate",
    }

    row = ctk.CTkFrame(win, fg_color="transparent")
    row.pack(fill="x", padx=16, pady=4)
    ctk.CTkLabel(row, text=TEAM_ORG_LABEL, text_color=_HC_MUTED).pack(side="left")
    ctk.CTkOptionMenu(row, variable=org_var, values=org_labels, width=280).pack(side="left", padx=8)
    ctk.CTkLabel(row, text=TEAM_MODE_LABEL, text_color=_HC_MUTED).pack(side="left", padx=(12, 4))
    ctk.CTkOptionMenu(
        row,
        variable=mode_display,
        values=[TEAM_MODE_PIPELINE, TEAM_MODE_COORDINATE],
        width=160,
    ).pack(side="left")

    ctk.CTkLabel(
        win,
        text=TEAM_MODE_HINT,
        text_color=_HC_MUTED,
        font=ctk.CTkFont(size=11),
        wraplength=540,
        justify="left",
    ).pack(anchor="w", padx=16, pady=2)

    # Loop / time control (especially for "discuss together" mode)
    rounds_row = ctk.CTkFrame(win, fg_color="transparent")
    rounds_row.pack(fill="x", padx=16, pady=(8, 2))
    ctk.CTkLabel(
        rounds_row,
        text="Max turns (stops endless talk)",
        text_color=_HC_MUTED,
    ).pack(side="left")
    # 4=fast · 6=default · 12=long (old default) · 20=max practical
    rounds_var = ctk.StringVar(master=rounds_row, value="6")
    ctk.CTkOptionMenu(
        rounds_row,
        variable=rounds_var,
        values=["3", "4", "6", "8", "10", "12", "16", "20"],
        width=80,
    ).pack(side="left", padx=8)
    ctk.CTkLabel(
        rounds_row,
        text="(each turn ≈ 1–2 min)",
        text_color=_HC_MUTED,
        font=ctk.CTkFont(size=11),
    ).pack(side="left", padx=4)
    ctk.CTkLabel(
        win,
        text=(
            "Tip: “One by one” runs each helper once (no loop). "
            "“Discuss together” can loop until Max turns — use 4–6 for short runs, "
            "or press Stop team anytime."
        ),
        text_color=_HC_MUTED,
        font=ctk.CTkFont(size=11),
        wraplength=540,
        justify="left",
    ).pack(anchor="w", padx=16, pady=(2, 4))

    status = ctk.CTkLabel(win, text="", text_color=_HC_MUTED, wraplength=520, justify="left")
    status.pack(anchor="w", padx=16, pady=4)

    dlg_state: dict[str, Any] = {"stop": False, "started": False, "channel_id": ""}

    def dlg_stop() -> None:
        from app.services import team_bg as tbg

        dlg_state["stop"] = True
        tbg.request_stop(app)
        status.configure(text="Stop requested…", text_color=_UI.get("warning", _HC_MUTED))

    def start() -> None:
        from app.services import team_bg as tbg

        if dlg_state.get("started"):
            return
        if tbg.is_running(app):
            status.configure(
                text="A team is already running in the background. Stop it first.",
                text_color="tomato",
            )
            return
        goal = goal_box.get("1.0", "end").strip()
        if not goal or goal.startswith("Example:"):
            status.configure(text="Enter a real goal (delete the example text).", text_color="tomato")
            return
        lab = org_var.get()
        if lab == TEAM_ORG_AUTO or lab.startswith("✨"):
            org_mode = "llm_create"
            gid = ""
        else:
            org_mode = "fixed"
            gid = gmap.get(lab, "")
        run_mode = mode_map.get(mode_display.get(), "pipeline")
        try:
            max_rounds = int(rounds_var.get() or "6")
        except ValueError:
            max_rounds = 6
        max_rounds = max(2, min(40, max_rounds))
        dlg_state["started"] = True
        dlg_state["stop"] = False
        # Mark app-level job so tab switch cannot orphan stop/progress
        j = tbg.job(app)
        j["running"] = True
        j["stop"] = False
        j["channel_id"] = ""
        j["progress"] = "Starting team…"
        j["error"] = ""
        status.configure(
            text=f"Starting… max {max_rounds} turns · works even if you switch tabs.",
            text_color=_HC_MUTED,
        )
        try:
            start_btn.configure(state="disabled", text="Working…")
            stop_dlg_btn.configure(state="normal")
        except Exception:  # noqa: BLE001
            pass
        win.update_idletasks()

        def worker() -> None:
            def on_progress(msg: str) -> None:
                tbg.set_progress(app, msg)

                def ui() -> None:
                    try:
                        if win.winfo_exists():
                            status.configure(text=str(msg)[:200], text_color=_HC_MUTED)
                    except Exception:  # noqa: BLE001
                        pass

                try:
                    app.after(0, ui)
                except Exception:  # noqa: BLE001
                    pass

            def on_channel_ready(ch: dict[str, Any]) -> None:
                cid = str(ch.get("id") or "")
                dlg_state["channel_id"] = cid
                j2 = tbg.job(app)
                j2["channel_id"] = cid
                j2["running"] = True

                def ui() -> None:
                    try:
                        if win.winfo_exists():
                            win.destroy()
                    except Exception:  # noqa: BLE001
                        pass
                    # Open Team so user sees feed; work continues if they leave again
                    app.show_page("Team")
                    ctrl = getattr(app, "_team_ctrl", None) or team_ctrl or {}
                    try:
                        if callable(ctrl.get("select_channel")):
                            ctrl["select_channel"](cid)
                        if callable(ctrl.get("set_running_ui")):
                            ctrl["set_running_ui"](True)
                        if callable(ctrl.get("set_live")):
                            ctrl["set_live"](
                                "Team working in background — switch tabs freely. Status bar shows progress.",
                                busy=True,
                            )
                    except Exception:  # noqa: BLE001
                        pass
                    app.set_status(
                        "Team running in background — you can open other pages",
                        toast=True,
                    )

                try:
                    app.after(0, ui)
                except Exception:  # noqa: BLE001
                    pass

            def should_stop() -> bool:
                return bool(dlg_state.get("stop")) or tbg.should_stop(app)

            res = start_team_goal(
                goal,
                title=title_e.get().strip(),
                org_mode=org_mode,
                org_graph_id=gid,
                run_mode=run_mode,
                max_rounds=max_rounds,
                on_progress=on_progress,
                on_channel_ready=on_channel_ready,
                should_stop=should_stop,
            )

            def done() -> None:
                cid = str(res.get("channel_id") or dlg_state.get("channel_id") or "")
                j3 = tbg.job(app)
                j3["running"] = False
                j3["stop"] = False
                j3["channel_id"] = cid or j3.get("channel_id") or ""
                j3["cancelled"] = bool(res.get("cancelled"))
                j3["ok"] = bool(res.get("ok"))
                j3["error"] = str(res.get("error") or "")
                if res.get("cancelled"):
                    j3["progress"] = "Stopped."
                elif res.get("error") and not res.get("ok"):
                    j3["progress"] = f"Error: {str(res.get('error'))[:100]}"
                else:
                    j3["progress"] = "Done ✓"

                ctrl = getattr(app, "_team_ctrl", None) or team_ctrl or {}
                try:
                    if callable(ctrl.get("set_running_ui")):
                        ctrl["set_running_ui"](False)
                except Exception:  # noqa: BLE001
                    pass

                if not res.get("ok") and not res.get("channel") and not cid:
                    try:
                        if win.winfo_exists():
                            status.configure(
                                text=str(res.get("error") or "Failed"),
                                text_color="tomato",
                            )
                            start_btn.configure(state="normal", text=TEAM_RUN)
                            stop_dlg_btn.configure(state="disabled")
                            dlg_state["started"] = False
                    except Exception:  # noqa: BLE001
                        pass
                    app.set_status(f"Team failed: {str(res.get('error') or '')[:60]}", toast=True)
                    return

                if getattr(app, "_current_page", "") != "Team":
                    # Stay on user's current tab; toast is enough
                    pass
                else:
                    app.show_page("Team")
                try:
                    ctrl2 = getattr(app, "_team_ctrl", None) or {}
                    if cid and callable(ctrl2.get("select_channel")):
                        ctrl2["select_channel"](cid)
                    elif cid and hasattr(app, "_team_select_channel"):
                        app._team_select_channel(cid)  # type: ignore[attr-defined]
                except Exception:  # noqa: BLE001
                    pass

                if res.get("cancelled"):
                    app.set_status("Team stopped", toast=True)
                elif not res.get("ok") and res.get("error"):
                    app.set_status(f"Team error: {str(res.get('error'))[:60]}", toast=True)
                else:
                    app.set_status(
                        f"Team done · open AI Team · {(res.get('final_text') or '')[:40]}",
                        toast=True,
                    )
                try:
                    if win.winfo_exists():
                        win.destroy()
                except Exception:  # noqa: BLE001
                    pass

            try:
                app.after(0, done)
            except Exception:  # noqa: BLE001
                j4 = tbg.job(app)
                j4["running"] = False
                j4["stop"] = False

        threading.Thread(target=worker, daemon=True, name="team-new-goal").start()

    bar = ctk.CTkFrame(win, fg_color="transparent")
    bar.pack(fill="x", padx=16, pady=12)
    start_btn = ctk.CTkButton(
        bar, text=TEAM_RUN, command=start, **style_chrome_button(primary=True)
    )
    start_btn.pack(side="left", padx=4)
    stop_dlg_btn = ctk.CTkButton(
        bar,
        text="⏹ Stop",
        width=90,
        state="disabled",
        command=dlg_stop,
        fg_color=("#dc2626", "#7f1d1d"),
        hover_color=("#991b1b", "#450a0a"),
    )
    stop_dlg_btn.pack(side="left", padx=4)
    ctk.CTkButton(bar, text="Cancel", command=win.destroy, width=90).pack(side="left", padx=4)

    if auto_run:
        pass  # user still fills form
