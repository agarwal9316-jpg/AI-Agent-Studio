"""Schedule page — extracted from AppWindow."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import customtkinter as ctk

if TYPE_CHECKING:
    from app.ui.app_window import AppWindow


def page_schedule(app) -> None:
    from app.ui.themes import UI as _UI
    _HC_MUTED = _UI["muted"]
    _HC_LABEL = _UI.get("label", _UI["muted"])
    from app.services import scheduler_service as sched
    from app.ui.themes import style_chrome_button

    root = ctk.CTkFrame(app.content, fg_color="transparent")
    root.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
    root.grid_columnconfigure(0, weight=1)
    root.grid_rowconfigure(2, weight=1)

    app._page_header(
        root,
        "Scheduled agents",
        "Recurring company tasks. Sticky Add bar stays fixed; schedule list scrolls below.",
        actions=[("Work board", lambda: app.show_page("Work"))],
    )

    form = ctk.CTkFrame(
        root,
        fg_color=_UI.get("top_bg", ("#f3f4f6", "#161a22")),
        corner_radius=10,
        border_width=1,
        border_color=_UI.get("top_border", ("#6b7280", "#4b5563")),
    )
    form.grid(row=1, column=0, sticky="ew", pady=(0, 8))
    title_e = ctk.CTkEntry(form, placeholder_text="Title", width=180)
    title_e.pack(side="left", padx=(10, 4), pady=10)
    mins_e = ctk.CTkEntry(form, placeholder_text="Minutes", width=70)
    mins_e.insert(0, "60")
    mins_e.pack(side="left", padx=4, pady=10)
    prompt_e = ctk.CTkEntry(form, placeholder_text="Task prompt / description", width=280)
    prompt_e.pack(side="left", padx=4, pady=10, fill="x", expand=True)

    list_f = ctk.CTkScrollableFrame(root, fg_color="transparent")
    list_f.grid(row=2, column=0, sticky="nsew", pady=0)

    def refresh() -> None:
        for w in list_f.winfo_children():
            w.destroy()
        items = sched.load_schedules()
        if not items:
            ctk.CTkLabel(
                list_f,
                text="No schedules yet. Fill the bar above and click Add schedule.",
                text_color=_HC_MUTED,
            ).pack(padx=12, pady=20)
            return
        for s in items:
            row = ctk.CTkFrame(list_f)
            row.pack(fill="x", pady=3)
            en = "ON" if s.get("enabled") else "OFF"
            ctk.CTkLabel(
                row,
                text=(
                    f"[{en}] every {s.get('interval_minutes')}m · {s.get('title')}\n"
                    f"runs={s.get('run_count')} last={str(s.get('last_run') or '—')[:19]}\n"
                    f"{(s.get('prompt') or '')[:120]}"
                ),
                anchor="w",
                justify="left",
                wraplength=700,
            ).pack(side="left", fill="x", expand=True, padx=8, pady=6)
            ctk.CTkButton(
                row,
                text="Toggle",
                width=70,
                command=lambda i=s["id"], e=not s.get("enabled"): (
                    sched.set_enabled(i, e),
                    refresh(),
                ),
            ).pack(side="right", padx=4)
            ctk.CTkButton(
                row,
                text="Delete",
                width=70,
                fg_color="#a33",
                command=lambda i=s["id"]: (sched.delete_schedule(i), refresh()),
            ).pack(side="right", padx=4)

    def add() -> None:
        try:
            mins = int(mins_e.get().strip() or "60")
        except ValueError:
            mins = 60
        sched.add_schedule(
            title=title_e.get().strip() or "Scheduled",
            prompt=prompt_e.get().strip() or title_e.get().strip(),
            interval_minutes=mins,
        )
        sched.start()
        title_e.delete(0, "end")
        prompt_e.delete(0, "end")
        refresh()
        app.set_status("Schedule added", toast=True)

    ctk.CTkButton(
        form,
        text="💾  Add schedule",
        width=140,
        height=34,
        command=add,
        **style_chrome_button(primary=True),
    ).pack(side="left", padx=6, pady=10)
    ctk.CTkButton(
        form,
        text="Run due now",
        width=110,
        height=34,
        command=lambda: (sched.tick(), refresh()),
    ).pack(side="left", padx=4, pady=10)
    app._page_save_handler = add
    refresh()
