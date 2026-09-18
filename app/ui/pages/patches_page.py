"""Patches page — extracted from AppWindow."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import customtkinter as ctk

if TYPE_CHECKING:
    from app.ui.app_window import AppWindow


def page_patches(app) -> None:
    from app.services import patch_review
    import tkinter.messagebox as messagebox

    root = ctk.CTkFrame(app.content, fg_color="transparent")
    root.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
    root.grid_columnconfigure(0, weight=1)
    root.grid_columnconfigure(1, weight=2)
    root.grid_rowconfigure(1, weight=1)

    app._page_header(
        root,
        "Patch review",
        "LLM-proposed code changes wait here. Review the diff, then Apply (backed up) or Reject.",
        columnspan=2,
        actions=[("Refresh", lambda: app.show_page("Patches"))],
    )

    left = ctk.CTkScrollableFrame(root)
    left.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
    right = ctk.CTkTextbox(root, wrap="none", font=ctk.CTkFont(family="Consolas", size=12))
    right.grid(row=1, column=1, sticky="nsew")

    state: dict[str, str] = {"id": ""}

    def show(p: dict) -> None:
        state["id"] = p.get("id") or ""
        right.delete("1.0", "end")
        right.insert(
            "1.0",
            f"Path: {p.get('path')}\nNote: {p.get('note')}\nStatus: {p.get('status')}\n\n"
            f"======== DIFF ========\n{p.get('diff') or ''}\n",
        )

    def refresh() -> None:
        for w in left.winfo_children():
            w.destroy()
        pending = patch_review.list_pending()
        if not pending:
            ctk.CTkLabel(left, text="No pending patches").pack(anchor="w", padx=6, pady=8)
        for p in pending:
            row = ctk.CTkFrame(left)
            row.pack(fill="x", pady=4, padx=4)
            ctk.CTkLabel(
                row,
                text=f"{p.get('path')}\n{(p.get('note') or '')[:80]}",
                anchor="w",
                justify="left",
                wraplength=260,
            ).pack(anchor="w", padx=6, pady=4)
            bar = ctk.CTkFrame(row, fg_color="transparent")
            bar.pack(fill="x", padx=4, pady=4)
            ctk.CTkButton(bar, text="View", width=60, command=lambda i=p: show(i)).pack(
                side="left", padx=2
            )
            ctk.CTkButton(
                bar,
                text="Apply",
                width=70,
                command=lambda i=p["id"]: (
                    messagebox.showinfo("Apply", str(patch_review.apply_patch(i)), parent=app),
                    refresh(),
                ),
            ).pack(side="left", padx=2)
            ctk.CTkButton(
                bar,
                text="Reject",
                width=70,
                fg_color="#a33",
                command=lambda i=p["id"]: (patch_review.reject_patch(i), refresh()),
            ).pack(side="left", padx=2)

    ctk.CTkButton(root, text="Refresh list", command=refresh).grid(row=2, column=0, sticky="w", pady=8)
    refresh()
