"""Diff viewer — extracted from AppWindow."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import customtkinter as ctk
import tkinter.messagebox as messagebox
from pathlib import Path

if TYPE_CHECKING:
    from app.ui.app_window import AppWindow


def open_file_diff_viewer(app, file_diff: dict[str, Any] | None) -> None:
    """Task #8: popup unified diff with +/- color tags."""
    from app.ui.themes import style_chrome_button, UI as _UI

    fd = file_diff or {}
    diff_text = str(fd.get("diff") or "")
    path = str(fd.get("path") or "")
    summary = str(fd.get("summary") or "File change")
    if not diff_text and fd.get("content"):
        try:
            from app.core.services.tools.file_diff import extract_diff_from_text

            diff_text = extract_diff_from_text(str(fd.get("content") or ""))
        except Exception:  # noqa: BLE001
            diff_text = str(fd.get("content") or "")
    if not diff_text:
        messagebox.showinfo("Diff", "No diff available for this step.", parent=app)
        return
    win = ctk.CTkToplevel(app)
    win.title(f"Diff — {Path(path).name if path else 'file edit'}")
    win.geometry("760x520")
    win.minsize(480, 320)
    try:
        win.transient(app)
        win.resizable(True, True)
    except Exception:  # noqa: BLE001
        pass
    head = ctk.CTkFrame(win, fg_color="transparent")
    head.pack(fill="x", padx=12, pady=(12, 4))
    ctk.CTkLabel(
        head,
        text=summary,
        font=ctk.CTkFont(size=15, weight="bold"),
        text_color=_UI["label"],
        anchor="w",
    ).pack(fill="x")
    if path:
        ctk.CTkLabel(
            head,
            text=path,
            text_color=_UI["muted"],
            font=ctk.CTkFont(size=11),
            anchor="w",
        ).pack(fill="x", pady=(2, 0))
    tb = ctk.CTkTextbox(win, font=ctk.CTkFont(family="Consolas", size=12), wrap="none")
    tb.pack(fill="both", expand=True, padx=12, pady=8)
    tb.insert("1.0", diff_text if diff_text.endswith("\n") else diff_text + "\n")
    try:
        tw = tb._textbox  # type: ignore[attr-defined]
        tw.tag_configure("add", foreground="#16a34a")
        tw.tag_configure("del", foreground="#dc2626")
        tw.tag_configure("hunk", foreground="#2563eb")
        tw.tag_configure("meta", foreground="#6b7280")
        for i, line in enumerate(diff_text.splitlines(), 1):
            start = f"{i}.0"
            end = f"{i}.end"
            if line.startswith("+++") or line.startswith("---"):
                tw.tag_add("meta", start, end)
            elif line.startswith("@@"):
                tw.tag_add("hunk", start, end)
            elif line.startswith("+"):
                tw.tag_add("add", start, end)
            elif line.startswith("-"):
                tw.tag_add("del", start, end)
    except Exception:  # noqa: BLE001
        pass
    try:
        tb.configure(state="disabled")
    except Exception:  # noqa: BLE001
        pass
    bar = ctk.CTkFrame(win, fg_color="transparent")
    bar.pack(fill="x", padx=12, pady=(0, 12))

    def copy_diff() -> None:
        try:
            app.clipboard_clear()
            app.clipboard_append(diff_text)
            app.set_status("Diff copied", toast=True)
        except Exception:  # noqa: BLE001
            pass

    def open_file() -> None:
        if not path:
            return
        try:
            from app.ui.components.message_box import open_url_or_path
            from app.core.services.data.rag_knowledge import path_to_file_uri

            open_url_or_path(path_to_file_uri(path))
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Open file", str(e), parent=win)

    ctk.CTkButton(bar, text="Copy diff", width=100, command=copy_diff, **style_chrome_button()).pack(
        side="left", padx=4
    )
    if path:
        ctk.CTkButton(
            bar, text="Open file", width=100, command=open_file, **style_chrome_button()
        ).pack(side="left", padx=4)
    ctk.CTkButton(bar, text="Close", width=90, command=win.destroy, **style_chrome_button(primary=True)).pack(
        side="right", padx=4
    )
