"""Help page — extracted from AppWindow."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import customtkinter as ctk

from app.ui.components.widget_names import set_widget_name, name_page_root, PAGE_HELP

if TYPE_CHECKING:
    from app.ui.app_window import AppWindow


def page_help(app) -> None:
    """In-app how-to-use guide for new users."""
    from app.ui.themes import style_chrome_button, style_card, UI as _UI
    from app.core.services.misc.user_guide import help_sections, SHORTCUTS_FRIENDLY

    root = ctk.CTkFrame(app.content, fg_color="transparent")
    root.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
    root.grid_columnconfigure(0, weight=1)
    root.grid_rowconfigure(2, weight=1)
    set_widget_name(root, name_page_root(PAGE_HELP))

    app._page_header(
        root,
        "How to use this app",
        "Written for everyone — not only technical people. Press F2 anytime to open this page.",
        actions=[
            ("Talk to AI", lambda: app.show_page("Chat")),
            ("Connect account", app._show_onboarding_wizard),
            ("Shortcuts", app._show_shortcuts_help),
        ],
    )

    how = ctk.CTkFrame(root, **style_card())
    how.grid(row=1, column=0, sticky="ew", pady=(0, 10))
    ctk.CTkLabel(
        how,
        text="How to chat (start here)",
        font=ctk.CTkFont(size=15, weight="bold"),
        text_color=_UI["label"],
    ).pack(anchor="w", padx=16, pady=(12, 4))
    ctk.CTkLabel(
        how,
        text=(
            "1. Open Talk to AI from the left menu.\n"
            "2. Type in the big box at the bottom (like a text message).\n"
            "3. Press Enter to send · Shift+Enter for a new line.\n"
            "4. Wait for the answer above — use ■ Stop if you need to cancel.\n"
            "5. Optional: Ctrl+\\ hides sidebars for a wider chat; Esc brings them back."
        ),
        text_color=_UI["muted"],
        font=ctk.CTkFont(size=13),
        justify="left",
        anchor="w",
    ).pack(anchor="w", padx=16, pady=(0, 12))

    scroll = ctk.CTkScrollableFrame(root, fg_color="transparent")
    scroll.grid(row=2, column=0, sticky="nsew")
    scroll.grid_columnconfigure(0, weight=1)

    for sec in help_sections():
        card = ctk.CTkFrame(scroll, **style_card())
        card.pack(fill="x", pady=8, padx=2)
        ctk.CTkLabel(
            card,
            text=sec["title"],
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=_UI["label"],
        ).pack(anchor="w", padx=14, pady=(12, 6))
        for item in sec.get("items") or []:
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=4)
            ctk.CTkLabel(
                row,
                text=item.get("title") or "",
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=_UI["label"],
                anchor="w",
            ).pack(anchor="w")
            ctk.CTkLabel(
                row,
                text=item.get("body") or "",
                text_color=_UI["muted"],
                font=ctk.CTkFont(size=12),
                wraplength=780,
                justify="left",
                anchor="w",
            ).pack(anchor="w")
            page = item.get("page")
            if page:
                from app.ui.components.layman_copy import friendly_name as _fn

                ctk.CTkButton(
                    row,
                    text=f"Open {_fn(page, simple=app._is_simple_ui())} →",
                    width=140,
                    height=26,
                    command=lambda p=page: app.show_page(p),
                    **style_chrome_button(),
                ).pack(anchor="w", pady=(4, 2))

    sc = ctk.CTkFrame(scroll, **style_card())
    sc.pack(fill="x", pady=8, padx=2)
    ctk.CTkLabel(
        sc,
        text="Keyboard & tips",
        font=ctk.CTkFont(size=16, weight="bold"),
        text_color=_UI["label"],
    ).pack(anchor="w", padx=14, pady=(12, 4))
    box = ctk.CTkTextbox(sc, height=220, font=ctk.CTkFont(family="Consolas", size=12))
    box.pack(fill="x", padx=12, pady=(0, 12))
    box.insert("1.0", SHORTCUTS_FRIENDLY)
    box.configure(state="disabled")
    ctk.CTkButton(
        sc,
        text="Show chat coach bar again",
        command=app._enable_chat_tips,
        **style_chrome_button(primary=True),
    ).pack(anchor="w", padx=14, pady=(0, 14))
