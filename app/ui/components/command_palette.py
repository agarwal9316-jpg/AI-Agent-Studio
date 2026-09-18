"""Command palette — extracted from AppWindow."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

import customtkinter as ctk

if TYPE_CHECKING:
    from app.ui.app_window import AppWindow


def open_command_palette(app) -> None:
    """Ctrl+K: jump to pages and common actions."""
    from app.ui.themes import style_chrome_button, style_entry

    win = ctk.CTkToplevel(app)
    win.title("Command palette")
    win.geometry("480x520")
    win.transient(app)
    win.grab_set()
    ctk.CTkLabel(win, text="Commands (Ctrl+K)", font=ctk.CTkFont(size=15, weight="bold")).pack(
        anchor="w", padx=12, pady=(12, 4)
    )
    qvar = ctk.StringVar(value="")
    entry = ctk.CTkEntry(win, textvariable=qvar, placeholder_text="Filter…", width=440, **style_entry())
    entry.pack(padx=12, pady=6)
    entry.focus_set()
    box = ctk.CTkScrollableFrame(win, height=380)
    box.pack(fill="both", expand=True, padx=12, pady=6)

    from app.ui.components.navigation import all_nav_page_names
    actions: list[tuple[str, Callable[[], None]]] = []
    for name in all_nav_page_names(simple_ui=bool(getattr(app, "_is_simple_ui", lambda: True)())):
        actions.append((f"Go to {name}", lambda n=name: app.show_page(n)))
    actions.extend(
        [
            ("Mode → Action", lambda: (app.chat_mode_var.set("action"), app._on_chat_flags_save()) if hasattr(app, "chat_mode_var") else None),
            ("Mode → Plan", lambda: (app.chat_mode_var.set("plan"), app._on_chat_flags_save()) if hasattr(app, "chat_mode_var") else None),
            ("Toggle density", app._chat_toggle_density),
            ("One-screen view", lambda: app._set_one_screen(True)),
            ("Exit one-screen", lambda: app._set_one_screen(False)),
            ("Hide / show menu", app._toggle_app_menu),
            ("Hide / show CPU bar", app._toggle_sysmon_bar),
            ("Caps / capabilities", app._chat_open_caps_popover),
            ("Generate image", app._chat_image_gen_dialog),
            ("Web search", app._chat_web_search_dialog),
            ("New chat", app._shortcut_new_chat),
            ("Toggle Live panel", app._chat_toggle_live_panel),
            ("Approvals", lambda: app.show_page("Approvals")),
            ("Settings", lambda: app.show_page("Settings")),
            ("Shortcuts help", app._show_shortcuts_help),
        ]
    )

    def run_action(fn: Callable[[], None]) -> None:
        win.destroy()
        try:
            if fn:
                fn()
        except Exception as e:  # noqa: BLE001
            app.set_status(f"Command failed: {e}")

    def render(*_a: Any) -> None:
        for w in box.winfo_children():
            w.destroy()
        q = (qvar.get() or "").strip().lower()
        shown = 0
        for label, fn in actions:
            if q and q not in label.lower():
                continue
            ctk.CTkButton(
                box,
                text=label,
                anchor="w",
                command=lambda f=fn: run_action(f),
                **style_chrome_button(),
            ).pack(fill="x", pady=2)
            shown += 1
            if shown >= 40:
                break
        if not shown:
            ctk.CTkLabel(box, text="No matches").pack(anchor="w", padx=8, pady=8)

    qvar.trace_add("write", lambda *_: render())
    entry.bind("<Return>", lambda _e: None)
    render()
