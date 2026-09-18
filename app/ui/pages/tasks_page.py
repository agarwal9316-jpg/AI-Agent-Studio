"""Tasks page — extracted from AppWindow."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import customtkinter as ctk

if TYPE_CHECKING:
    from app.ui.app_window import AppWindow

from app.services import storage


def page_tasks(app) -> None:
    from app.ui.themes import style_chrome_button
    from app.ui.components.page_layout import attach_save_bar_to_form_panel, make_list_form_page

    layout = make_list_form_page(app.content, list_width=260)
    app._page_form_layout = layout
    app._page_save_handler = app._task_save

    app._page_header(
        layout.header_parent,
        "Tasks",
        "Assign work items to agents for multi-task Runs. Save bar stays visible under the form.",
        columnspan=1,
        actions=[("New Task", app._task_new)],
    )

    assert layout.list_panel is not None and layout.list_scroll is not None
    ctk.CTkButton(
        layout.list_panel,
        text="New Task",
        command=app._task_new,
        **style_chrome_button(primary=True),
    ).grid(row=0, column=0, sticky="ew", padx=8, pady=8)
    app.task_list = layout.list_scroll

    form = layout.form_scroll
    assert form is not None
    form.grid_columnconfigure(1, weight=1)

    app.task_name = ctk.CTkEntry(form, placeholder_text="Task name")
    app.task_desc = ctk.CTkTextbox(form, height=100)
    app.task_expected = ctk.CTkEntry(form, placeholder_text="Expected output")
    agents = storage.list_agents()
    agent_labels = ["(none)"] + [
        f"{a.get('name') or a.get('role')}|{a['id']}" for a in agents
    ]
    app._agent_choices = agent_labels
    app.task_agent = ctk.CTkOptionMenu(
        form, values=[x.split("|")[0] for x in agent_labels]
    )
    app.task_error = ctk.CTkLabel(form, text="", text_color="tomato")

    rows = [
        ("Name", app.task_name),
        ("Description", app.task_desc),
        ("Expected output", app.task_expected),
        ("Assign agent", app.task_agent),
    ]
    for i, (lab, w) in enumerate(rows):
        ctk.CTkLabel(form, text=lab).grid(row=i, column=0, sticky="nw", padx=10, pady=8)
        w.grid(row=i, column=1, sticky="ew", padx=10, pady=8)

    app.task_error.grid(row=4, column=0, columnspan=2, sticky="w", padx=10, pady=(4, 12))

    app._task_save_bar = attach_save_bar_to_form_panel(
        layout,
        save_label="💾  Save task",
        on_save=app._task_save,
        secondary=[
            (
                "Delete",
                app._task_delete,
                {"fg_color": "#a33", "hover_color": "#7f1d1d", "width": 90},
            ),
        ],
        hint="Edit fields above, then Save (Ctrl+S)",
    )

    app._refresh_task_list()
    if not storage.list_tasks():
        ctk.CTkLabel(app.task_list, text="No tasks yet.\nClick New Task.").pack(
            padx=8, pady=16
        )
