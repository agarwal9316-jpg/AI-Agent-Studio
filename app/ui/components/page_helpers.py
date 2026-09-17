"""Page helpers — extracted from AppWindow."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import customtkinter as ctk

if TYPE_CHECKING:
    from app.ui.app_window import AppWindow


def page_header(
    app,
    parent: Any,
    title: str,
    subtitle: str = "",
    *,
    row: int = 0,
    columnspan: int = 1,
    actions: list[tuple[str, Any]] | None = None,
) -> None:
    """Consistent page title bar used across admin pages."""
    from app.ui.themes import UI as _UI, style_chrome_button, style_card

    bar = ctk.CTkFrame(parent, **style_card())
    bar.grid(row=row, column=0, columnspan=max(1, columnspan), sticky="ew", pady=(0, 12))
    if hasattr(parent, "grid_columnconfigure"):
        try:
            parent.grid_columnconfigure(0, weight=1)
        except Exception:  # noqa: BLE001
            pass
    left = ctk.CTkFrame(bar, fg_color="transparent")
    left.pack(side="left", fill="x", expand=True, padx=14, pady=12)
    ctk.CTkLabel(
        left, text=title, font=("Segoe UI", 20, "bold"), text_color=_UI["label"]
    ).pack(anchor="w")
    if subtitle:
        ctk.CTkLabel(
            left,
            text=subtitle,
            text_color=_UI["muted"],
            font=("Segoe UI", 12),
            wraplength=720,
            justify="left",
        ).pack(anchor="w", pady=(2, 0))
    if actions:
        right = ctk.CTkFrame(bar, fg_color="transparent")
        right.pack(side="right", padx=12, pady=10)
        for i, (lab, cmd) in enumerate(actions):
            ctk.CTkButton(
                right,
                text=lab,
                width=100,
                height=30,
                command=cmd,
                **style_chrome_button(primary=(i == 0)),
            ).pack(side="left", padx=3)


def show_shortcuts_help(app) -> None:
    win = ctk.CTkToplevel(app)
    win.title("Keyboard shortcuts")
    win.geometry("480x420")
    win.transient(app)
    text = (
        "Ctrl+N     New chat\n"
        "Ctrl+K     Command palette (pages + actions)\n"
        "Ctrl+\\    Focus mode (hide sidebar)\n"
        "Esc        Exit focus mode\n"
        "Ctrl+S     Save chat / current form (Agents, Tasks, …)\n"
        "Ctrl+E     Export chat\n"
        "Ctrl+L     Clear activity log\n"
        "Ctrl+M     Mic / speech-to-text\n"
        "Ctrl+B     Branch (fork) chat\n"
        "Ctrl+P     Pin / unpin chat\n"
        "Ctrl+G     Generate image\n"
        "Ctrl+Shift+T  Cycle UI theme\n"
        "Ctrl+Shift+A  Approvals queue\n"
        "Enter      Send message\n"
        "Shift+Enter  Newline\n"
        "F1         Keyboard list\n"
        "F2         How-to Help guide\n"
        "Ctrl+\\    Focus mode\n"
        "\n"
        "Slash (composer):\n"
        "  /plan  /action  /image …  /search …\n"
        "  /stop  /caps  /live  /new  /help\n"
        "  /compact  (toggle density)\n"
        "\n"
        "Hash inject (composer):\n"
        "  #filename.md   knowledge / local file\n"
        "  #./path/file   relative or absolute path\n"
        "  #https://…     fetch URL into this turn\n"
        "\n"
        "Chat: + menu · Mode/Tasks/Caps chips · tool traces\n"
        "Self-improve: BACKUP / SELF_IMPROVE blocks\n"
    )
    ctk.CTkLabel(win, text="Keyboard shortcuts", font=ctk.CTkFont(size=16, weight="bold")).pack(
        pady=12
    )
    box = ctk.CTkTextbox(win, font=ctk.CTkFont(family="Consolas", size=13))
    box.pack(fill="both", expand=True, padx=16, pady=8)
    box.insert("1.0", text)
    box.configure(state="disabled")
    ctk.CTkButton(win, text="Close", command=win.destroy).pack(pady=8)


def render_page_build_error(app, name: str, exc: BaseException) -> None:
    """Visible fallback when a page builder crashes (replaces blank white)."""
    import traceback

    tb = traceback.format_exc()
    try:
        app.set_status(f"{name} failed to open: {exc}")
    except Exception:  # noqa: BLE001
        pass
    try:
        from app.ui.themes import UI, style_chrome_button
    except Exception:  # noqa: BLE001
        UI = {"content_bg": ("#f7f7f8", "#0a0a0a"), "label": ("#111", "#eee"), "muted": ("#444", "#bbb")}
        style_chrome_button = lambda **_k: {}  # noqa: E731
    frame = ctk.CTkFrame(app.content, fg_color=UI.get("content_bg", ("#f7f7f8", "#0a0a0a")), corner_radius=12)
    frame.grid(row=0, column=0, sticky="nsew", padx=24, pady=24)
    ctk.CTkLabel(
        frame,
        text=f"{name} didn't open",
        font=ctk.CTkFont(size=22, weight="bold"),
        text_color=UI.get("label", ("#111827", "#f9fafb")),
    ).pack(anchor="w", padx=20, pady=(20, 6))
    ctk.CTkLabel(
        frame,
        text="The page hit an error while building. Retry, or go Home. This is a Studio bug — not your chat.",
        wraplength=720,
        justify="left",
        text_color=UI.get("muted", ("#374151", "#d1d5db")),
    ).pack(anchor="w", padx=20, pady=(0, 10))
    ctk.CTkLabel(
        frame,
        text=str(exc),
        wraplength=720,
        justify="left",
        font=ctk.CTkFont(family="Consolas", size=13),
    ).pack(anchor="w", padx=20, pady=(0, 12))
    bar = ctk.CTkFrame(frame, fg_color="transparent")
    bar.pack(anchor="w", padx=20, pady=(0, 8))
    ctk.CTkButton(
        bar,
        text="Retry this page",
        width=140,
        command=lambda: app.show_page(name),
        **style_chrome_button(primary=True),
    ).pack(side="left", padx=(0, 8))
    ctk.CTkButton(
        bar,
        text="Go to Home",
        width=110,
        command=lambda: app.show_page("Home"),
        **style_chrome_button(),
    ).pack(side="left")
    box = ctk.CTkTextbox(frame, height=180, font=ctk.CTkFont(family="Consolas", size=11), wrap="word")
    box.pack(fill="both", expand=True, padx=20, pady=(8, 20))
    try:
        box.insert("1.0", tb)
        box.configure(state="disabled")
    except Exception:  # noqa: BLE001
        pass
