"""Track page — extracted from AppWindow."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import customtkinter as ctk

if TYPE_CHECKING:
    from app.ui.app_window import AppWindow


def page_track(app) -> None:
    """Full agent tracking: active agent, inputs, outputs."""
    from app.services import agent_tracker
    from app.ui.themes import UI as _UI
    _HC_MUTED = _UI["muted"]

    root = ctk.CTkFrame(app.content, fg_color="transparent")
    root.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
    root.grid_columnconfigure(0, weight=1)
    root.grid_columnconfigure(1, weight=1)
    root.grid_rowconfigure(2, weight=1)

    ctk.CTkLabel(
        root, text="Agent track", font=ctk.CTkFont(size=22, weight="bold")
    ).grid(row=0, column=0, columnspan=2, sticky="w")
    ctk.CTkLabel(
        root,
        text="See which agent is active, what it received (input), and what it produced (output).",
        text_color=_HC_MUTED,
    ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 8))

    left = ctk.CTkFrame(root)
    left.grid(row=2, column=0, sticky="nsew", padx=(0, 8))
    left.grid_rowconfigure(1, weight=1)
    ctk.CTkLabel(left, text="Active / recent agents", font=ctk.CTkFont(weight="bold")).grid(
        row=0, column=0, sticky="w", padx=10, pady=8
    )
    list_box = ctk.CTkScrollableFrame(left)
    list_box.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)

    right = ctk.CTkFrame(root)
    right.grid(row=2, column=1, sticky="nsew")
    right.grid_rowconfigure(1, weight=1)
    ctk.CTkLabel(right, text="Input / Output detail", font=ctk.CTkFont(weight="bold")).grid(
        row=0, column=0, sticky="w", padx=10, pady=8
    )
    detail = ctk.CTkTextbox(right, wrap="word")
    detail.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)

    search_e = ctk.CTkEntry(root, placeholder_text="Search agent runs…")
    search_e.grid(row=3, column=0, sticky="ew", padx=(0, 8), pady=8)

    def show_run(run: dict) -> None:
        detail.delete("1.0", "end")
        detail.insert(
            "1.0",
            f"Status: {run.get('status')}\n"
            f"Agent: {run.get('agent_name')} ({run.get('agent_role')})\n"
            f"Model: {run.get('model')}\n"
            f"Task: {run.get('task_title')}\n"
            f"Task id: {run.get('task_id')}\n"
            f"Goal id: {run.get('goal_id')}\n"
            f"Started: {run.get('started_at')}\n"
            f"Finished: {run.get('finished_at') or '—'}\n"
            f"Error: {run.get('error') or '—'}\n\n"
            f"======== INPUT ========\n{run.get('input') or ''}\n\n"
            f"======== OUTPUT ========\n{run.get('output') or '(none yet)'}\n",
        )

    def render(runs: list | None = None) -> None:
        for w in list_box.winfo_children():
            w.destroy()
        active = agent_tracker.get_active()
        if active:
            ctk.CTkLabel(
                list_box,
                text=f"▶ RUNNING: {active.get('agent_name')} — {active.get('task_title')}",
                text_color=("#1d4ed8", "#93c5fd"),
                font=ctk.CTkFont(weight="bold"),
            ).pack(fill="x", pady=4)
            ctk.CTkButton(
                list_box,
                text="View active I/O",
                command=lambda: show_run(active),
            ).pack(fill="x", pady=2)
        for r in runs if runs is not None else agent_tracker.list_recent(40):
            label = f"[{r.get('status')}] {r.get('agent_name')} · {r.get('task_title')}"
            ctk.CTkButton(
                list_box,
                text=label,
                anchor="w",
                fg_color="transparent",
                command=lambda run=r: show_run(run),
            ).pack(fill="x", pady=1)

    def do_search() -> None:
        q = search_e.get().strip()
        render(agent_tracker.search_runs(q))

    ctk.CTkButton(root, text="Search runs", command=do_search).grid(
        row=3, column=1, sticky="w", pady=8
    )
    ctk.CTkButton(root, text="Refresh", command=lambda: render()).grid(
        row=4, column=0, sticky="w", pady=4
    )
    render()
    active = agent_tracker.get_active()
    if active:
        show_run(active)
    else:
        rec = agent_tracker.list_recent(1)
        if rec:
            show_run(rec[0])
