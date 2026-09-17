"""Agents page — extracted from AppWindow."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import customtkinter as ctk

if TYPE_CHECKING:
    from app.ui.app_window import AppWindow

from app.services import storage


def page_agents(app) -> None:
    from app.ui.themes import style_chrome_button
    from app.ui.components.page_layout import attach_save_bar_to_form_panel, make_list_form_page

    layout = make_list_form_page(app.content, list_width=260)
    app._page_form_layout = layout
    app._page_save_handler = app._agent_save

    app._page_header(
        layout.header_parent,
        "Agents",
        "Scroll the form if needed. Save stays on the bar below — never off-screen. Empty LLM fields = Settings default.",
        columnspan=1,
        actions=[("New Agent", app._agent_new)],
    )

    assert layout.list_panel is not None and layout.list_scroll is not None
    ctk.CTkButton(
        layout.list_panel,
        text="New Agent",
        command=app._agent_new,
        **style_chrome_button(primary=True),
    ).grid(row=0, column=0, sticky="ew", padx=8, pady=8)
    app.agent_list = layout.list_scroll

    form = layout.form_scroll
    assert form is not None
    form.grid_columnconfigure(1, weight=1)

    app.agent_id_var = ctk.StringVar(value="")
    app.agent_name = ctk.CTkEntry(form, placeholder_text="Name")
    app.agent_role = ctk.CTkEntry(form, placeholder_text="Role")
    app.agent_goal = ctk.CTkEntry(form, placeholder_text="Goal")
    app.agent_backstory = ctk.CTkTextbox(form, height=70)
    app.agent_llm_model = ctk.CTkEntry(
        form, placeholder_text="e.g. gpt-4o-mini or grok-2 (empty=Settings)"
    )
    app.agent_llm_base = ctk.CTkEntry(
        form, placeholder_text="https://api.openai.com/v1 (empty=Settings)"
    )
    app.agent_llm_key = ctk.CTkEntry(
        form,
        placeholder_text="API key for this agent only (empty=Settings)",
        show="*",
    )
    app.agent_system_prompt = ctk.CTkTextbox(form, height=100)
    app.agent_error = ctk.CTkLabel(form, text="", text_color="tomato")

    labels = [
        "Name *",
        "Role *",
        "Goal *",
        "Backstory",
        "LLM model",
        "LLM base URL",
        "LLM API key",
        "System prompt",
    ]
    widgets = [
        app.agent_name,
        app.agent_role,
        app.agent_goal,
        app.agent_backstory,
        app.agent_llm_model,
        app.agent_llm_base,
        app.agent_llm_key,
        app.agent_system_prompt,
    ]
    for i, (lab, w) in enumerate(zip(labels, widgets)):
        ctk.CTkLabel(form, text=lab).grid(row=i, column=0, sticky="nw", padx=10, pady=6)
        w.grid(row=i, column=1, sticky="ew", padx=10, pady=6)

    app.agent_error.grid(row=8, column=0, columnspan=2, sticky="w", padx=10, pady=(4, 12))

    app._agent_save_bar = attach_save_bar_to_form_panel(
        layout,
        save_label="💾  Save agent",
        on_save=app._agent_save,
        secondary=[
            (
                "Delete",
                app._agent_delete,
                {"fg_color": "#a33", "hover_color": "#7f1d1d", "width": 90},
            ),
        ],
        hint="Edit fields above, then Save (Ctrl+S)",
    )

    def _mark_dirty(*_a: Any) -> None:
        try:
            app._agent_save_bar.mark_dirty(True)
        except Exception:  # noqa: BLE001
            pass

    for w in (
        app.agent_name,
        app.agent_role,
        app.agent_goal,
        app.agent_llm_model,
        app.agent_llm_base,
        app.agent_llm_key,
    ):
        try:
            w.bind("<KeyRelease>", _mark_dirty)
        except Exception:  # noqa: BLE001
            pass
    for tb in (app.agent_backstory, app.agent_system_prompt):
        try:
            tb.bind("<KeyRelease>", _mark_dirty)
        except Exception:  # noqa: BLE001
            pass

    app._refresh_agent_list()
    if not storage.list_agents():
        ctk.CTkLabel(app.agent_list, text="No agents yet.\nClick New Agent.").pack(
            padx=8, pady=16
        )
