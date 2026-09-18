"""Approvals page — extracted from AppWindow."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import customtkinter as ctk

from app.services import storage

if TYPE_CHECKING:
    from app.ui.app_window import AppWindow


def page_approvals(app) -> None:
    from app.ui.themes import UI as _UI
    _HC_MUTED = _UI["muted"]
    _HC_LABEL = _UI.get("label", _UI["muted"])
    from app.services import tool_approvals
    from app.services import company_store as company
    from app.core.services.chat.orchestrator import get_orchestrator

    root = ctk.CTkFrame(app.content, fg_color="transparent")
    root.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
    root.grid_columnconfigure(0, weight=1)
    root.grid_columnconfigure(1, weight=1)
    root.grid_rowconfigure(1, weight=1)

    app._page_header(
        root,
        "Approvals queue",
        "Tool actions (when Safety / tool approval is on) + company task approvals. Chat stays free.",
        columnspan=2,
        actions=[
            ("Refresh", lambda: app.show_page("Approvals")),
            ("Work", lambda: app.show_page("Work")),
        ],
    )

    left = ctk.CTkScrollableFrame(root)
    left.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
    right = ctk.CTkScrollableFrame(root)
    right.grid(row=1, column=1, sticky="nsew", padx=(8, 0))

    cfg = storage.load_config()
    top = ctk.CTkFrame(root)
    top.grid(row=2, column=0, columnspan=2, sticky="ew", pady=8)
    req_var = ctk.BooleanVar(value=bool(cfg.get("tool_approval_required")))

    def toggle_req() -> None:
        c = storage.load_config()
        c["tool_approval_required"] = bool(req_var.get())
        storage.save_config(c)
        app.set_status(
            "Tool approval ON — risky tools wait here"
            if req_var.get()
            else "Tool approval OFF — tools run immediately"
        )

    ctk.CTkSwitch(
        top, text="Require tool approval (terminal/GUI/pip/MCP)", variable=req_var, command=toggle_req
    ).pack(side="left", padx=8)
    ctk.CTkButton(
        top, text="Approve all tools", width=120, command=lambda: (tool_approvals.approve_all_pending(), refresh())
    ).pack(side="left", padx=8)
    ctk.CTkButton(top, text="Refresh", width=80, command=lambda: refresh()).pack(side="left", padx=4)

    def refresh() -> None:
        for w in left.winfo_children():
            w.destroy()
        for w in right.winfo_children():
            w.destroy()
        ctk.CTkLabel(left, text="Tool approvals", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=6, pady=4
        )
        pending = tool_approvals.list_pending()
        if not pending:
            ctk.CTkLabel(left, text="No pending tool approvals").pack(anchor="w", padx=8, pady=6)
        for ap in pending:
            row = ctk.CTkFrame(left)
            row.pack(fill="x", pady=4, padx=4)
            ctk.CTkLabel(
                row,
                text=f"[{ap.get('tool')}] {ap.get('summary')}",
                wraplength=340,
                justify="left",
                anchor="w",
            ).pack(anchor="w", padx=6, pady=4)
            bar = ctk.CTkFrame(row, fg_color="transparent")
            bar.pack(fill="x", padx=6, pady=4)
            ctk.CTkButton(
                bar,
                text="Approve",
                width=80,
                command=lambda i=ap["id"]: (tool_approvals.approve(i), refresh()),
            ).pack(side="left", padx=2)
            ctk.CTkButton(
                bar,
                text="Reject",
                width=80,
                fg_color="#a33",
                command=lambda i=ap["id"]: (tool_approvals.reject(i), refresh()),
            ).pack(side="left", padx=2)

        ctk.CTkLabel(right, text="Company task approvals", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=6, pady=4
        )
        for ap in company.list_approvals(status="pending"):
            row = ctk.CTkFrame(right)
            row.pack(fill="x", pady=4, padx=4)
            ctk.CTkLabel(
                row,
                text=(ap.get("summary") or "")[:220],
                wraplength=340,
                justify="left",
                anchor="w",
            ).pack(anchor="w", padx=6, pady=4)
            bar = ctk.CTkFrame(row, fg_color="transparent")
            bar.pack(fill="x", padx=6, pady=4)
            ctk.CTkButton(
                bar,
                text="Approve",
                width=80,
                command=lambda i=ap["id"]: (
                    get_orchestrator().approve(i),
                    refresh(),
                ),
            ).pack(side="left", padx=2)
            ctk.CTkButton(
                bar,
                text="Reject",
                width=80,
                fg_color="#a33",
                command=lambda i=ap["id"]: (
                    get_orchestrator().reject(i),
                    refresh(),
                ),
            ).pack(side="left", padx=4)
        if not company.list_approvals(status="pending"):
            ctk.CTkLabel(right, text="No pending company approvals").pack(anchor="w", padx=8, pady=6)

        ctk.CTkLabel(left, text="Recent tool decisions", text_color=_HC_MUTED).pack(
            anchor="w", padx=6, pady=(12, 4)
        )
        for ap in tool_approvals.list_all(12):
            if ap.get("status") == "pending":
                continue
            ctk.CTkLabel(
                left,
                text=f"{ap.get('status')}: [{ap.get('tool')}] {str(ap.get('summary') or '')[:80]}",
                text_color=_HC_MUTED,
                anchor="w",
                wraplength=340,
            ).pack(anchor="w", padx=8, pady=1)

    refresh()
