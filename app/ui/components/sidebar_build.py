"""Sidebar builder — extracted from AppWindow."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import customtkinter as ctk

from app.services import storage
from app.ui.components.navigation import NAV_ITEMS, hub_description, page_description
from app.ui.components.widget_names import (
    set_widget_name,
    build_name,
    REGION_SIDEBAR,
    PREFIX_FRAME,
    PREFIX_SCROLL,
    SIDEBAR_NAV,
    SIDEBAR_FOOTER,
    name_sidebar_hub_header,
    name_sidebar_hub_items_frame,
    name_sidebar_nav_button,
    name_sidebar_footer_button,
)

if TYPE_CHECKING:
    from app.ui.app_window import AppWindow


def refresh_nav_badges(app) -> None:
    """Update Approvals / Patches / Work badge text without full rebuild."""
    from app.ui.themes import UI

    for name, count_fn, alert in (
        ("Approvals", app._approval_badge_count, True),
        ("Patches", app._patches_badge_count, True),
        ("Work", app._work_running_count, False),
    ):
        btn = (getattr(app, "_nav_buttons", None) or {}).get(name)
        if not btn:
            continue
        try:
            n = count_fn()
            label = app._nav_label_for(name)
            is_cur = app._current_page == name
            if is_cur:
                btn.configure(
                    text=f"●  {label}",
                    text_color=UI["sidebar_active_text"],
                    fg_color=UI["sidebar_active"],
                )
            elif alert and n:
                btn.configure(
                    text=label,
                    text_color=("#991b1b", "#fecaca"),
                    fg_color=("#fee2e2", "#3f1d1d"),
                )
            elif n and name == "Work":
                btn.configure(
                    text=label,
                    text_color=("#1e40af", "#93c5fd"),
                    fg_color=("#dbeafe", "#1e293b"),
                )
            else:
                btn.configure(
                    text=label,
                    text_color=UI["sidebar_text"],
                    fg_color="transparent",
                )
        except Exception:  # noqa: BLE001
            pass


def build_sidebar(app) -> None:
    from app.ui.themes import UI, style_chrome_button

    old = getattr(app, "_sidebar_frame", None)
    if old is not None:
        try:
            old.destroy()
        except Exception:  # noqa: BLE001
            pass

    side = ctk.CTkFrame(app, width=212, corner_radius=0, fg_color=UI["sidebar_bg"])
    side.grid(row=0, column=0, sticky="nsw")
    side.grid_propagate(False)
    side.grid_rowconfigure(2, weight=1)
    side.grid_columnconfigure(0, weight=1)
    app._sidebar_frame = side
    set_widget_name(side, build_name("app", REGION_SIDEBAR, PREFIX_FRAME, "root"))

    accent = ctk.CTkFrame(side, height=4, fg_color=UI["brand_bar"], corner_radius=0)
    accent.grid(row=0, column=0, sticky="ew")
    set_widget_name(accent, build_name("app", REGION_SIDEBAR, PREFIX_FRAME, "accent"))

    brand = ctk.CTkFrame(side, fg_color="transparent")
    brand.grid(row=1, column=0, sticky="ew", padx=14, pady=(14, 8))
    set_widget_name(brand, build_name("app", REGION_SIDEBAR, PREFIX_FRAME, "brand"))
    ctk.CTkLabel(
        brand,
        text="AI Agent Studio",
        font=ctk.CTkFont(size=15, weight="bold"),
        text_color=UI["sidebar_text"],
    ).pack(anchor="w")
    ctk.CTkLabel(
        brand,
        text="Easy menu  ·  pick a page" if app._is_simple_ui() else "Full menu  ·  all tools",
        font=ctk.CTkFont(size=11),
        text_color=UI["sidebar_muted"],
    ).pack(anchor="w", pady=(3, 0))

    nav = ctk.CTkScrollableFrame(
        side,
        fg_color="transparent",
        width=196,
        corner_radius=0,
    )
    nav.grid(row=2, column=0, sticky="nsew", padx=2, pady=(2, 4))
    nav.grid_columnconfigure(0, weight=1)
    app._nav_scroll = nav
    set_widget_name(nav, build_name("app", REGION_SIDEBAR, SIDEBAR_NAV, PREFIX_SCROLL, "root"))

    app._hub_expanded: dict[str, bool] = getattr(app, "_hub_expanded", None) or {
        "START HERE": True,
        "PRIMARY": True,
        "WORKSPACE": False if app._is_simple_ui() else True,
        "MORE": False,
        "CHAT": True,
        "WORK": True,
        "LIBRARY": False,
        "SYSTEM": False,
    }
    if app._is_simple_ui():
        app._hub_expanded["MENU"] = True
        app._hub_expanded["START HERE"] = True

    app._nav_buttons: dict[str, ctk.CTkButton] = {}
    app._hub_item_frames: dict[str, ctk.CTkFrame] = {}
    app._hub_headers: dict[str, ctk.CTkButton] = {}

    for title, items in app._nav_hubs():
        expanded = bool(app._hub_expanded.get(title, True))
        hub_key = title.lower().replace(" ", "_")
        header = ctk.CTkButton(
            nav,
            text=f"{'▾' if expanded else '▸'}  {title}",
            anchor="w",
            height=22,
            corner_radius=6,
            fg_color="transparent",
            text_color=UI["sidebar_muted"],
            hover_color=UI["sidebar_hover"],
            font=ctk.CTkFont(size=10, weight="bold"),
            command=lambda t=title: app._toggle_nav_hub(t),
        )
        header.pack(fill="x", padx=10, pady=(8, 2))
        set_widget_name(header, name_sidebar_hub_header(hub_key))
        app._hub_headers[title] = header
        app._tooltip(header, hub_description(title))

        items_frame = ctk.CTkFrame(nav, fg_color="transparent")
        app._hub_item_frames[title] = items_frame
        set_widget_name(items_frame, name_sidebar_hub_items_frame(hub_key))
        if expanded:
            items_frame.pack(fill="x")
        for name in items:
            if name not in NAV_ITEMS:
                continue
            btn = ctk.CTkButton(
                items_frame,
                text=app._nav_label_for(name),
                anchor="w",
                height=40 if app._is_simple_ui() else 32,
                corner_radius=10,
                fg_color="transparent",
                text_color=UI["sidebar_text"],
                hover_color=UI["sidebar_hover"],
                font=ctk.CTkFont(size=14 if app._is_simple_ui() else 13),
                command=lambda n=name: app.show_page(n),
            )
            btn.pack(fill="x", padx=8, pady=2 if app._is_simple_ui() else 1)
            set_widget_name(btn, name_sidebar_nav_button(hub_key, name.lower()))
            app._nav_buttons[name] = btn
            app._tooltip(btn, page_description(name))

    foot = ctk.CTkFrame(
        side,
        fg_color=UI.get("hub_header_bg", "transparent"),
        corner_radius=12,
        border_width=0,
    )
    foot.grid(row=3, column=0, sticky="ew", padx=8, pady=(4, 10))
    set_widget_name(foot, build_name("app", REGION_SIDEBAR, SIDEBAR_FOOTER, PREFIX_FRAME, "root"))
    simple_on = app._is_simple_ui()
    ctk.CTkLabel(
        foot,
        text="Quick",
        font=ctk.CTkFont(size=10, weight="bold"),
        text_color=UI["sidebar_muted"],
        anchor="w",
    ).pack(fill="x", padx=10, pady=(8, 2))
    _easy_btn = ctk.CTkButton(
        foot,
        text="😊 Easy menu" if not simple_on else "🔧 Show all pages",
        height=32,
        corner_radius=10,
        command=lambda: app._set_simple_ui(not simple_on),
        **style_chrome_button(primary=simple_on),
    )
    _easy_btn.pack(fill="x", padx=8, pady=2)
    set_widget_name(_easy_btn, name_sidebar_footer_button("easy_toggle"))
    app._tooltip(
        _easy_btn,
        lambda: (
            "Show only the everyday screens to keep it simple."
            if not app._is_simple_ui()
            else "Show every screen, including advanced tools."
        ),
    )
    row2 = ctk.CTkFrame(foot, fg_color="transparent")
    row2.pack(fill="x", padx=6, pady=(2, 2))
    _key_btn = ctk.CTkButton(
        row2,
        text="⚙ Key",
        width=90,
        height=28,
        corner_radius=8,
        command=lambda: app.show_page("Settings"),
        **style_chrome_button(),
    )
    _key_btn.pack(side="left", padx=2, expand=True, fill="x")
    set_widget_name(_key_btn, name_sidebar_footer_button("settings"))
    app._tooltip(_key_btn, "Settings: add your AI connection key and adjust options.")
    _help_btn = ctk.CTkButton(
        row2,
        text="? Help",
        width=90,
        height=28,
        corner_radius=8,
        command=lambda: app.show_page("Help"),
        **style_chrome_button(primary=True),
    )
    _help_btn.pack(side="left", padx=2, expand=True, fill="x")
    set_widget_name(_help_btn, name_sidebar_footer_button("help"))
    app._tooltip(_help_btn, "Guides in plain English. Press F2 to open Help.")
    _search_btn = ctk.CTkButton(
        foot,
        text="⌨  Search pages  (Ctrl+K)",
        height=28,
        corner_radius=8,
        command=app._open_command_palette,
        **style_chrome_button(),
    )
    _search_btn.pack(fill="x", padx=8, pady=(2, 8))
    set_widget_name(_search_btn, name_sidebar_footer_button("search"))
    app._tooltip(_search_btn, "Jump straight to any page by typing its name. (Shortcut: Ctrl+K)")
    app._refresh_nav_badges()
    app._smooth_scroll(nav)


def toggle_nav_hub(app, title: str) -> None:
    if str(title).strip().upper() == "PRIMARY":
        app._hub_expanded[title] = True
        frame = (app._hub_item_frames or {}).get(title)
        header = (app._hub_headers or {}).get(title)
        if header:
            try:
                header.configure(text=f"▾  {title}")
            except Exception:  # noqa: BLE001
                pass
        if frame:
            try:
                if not frame.winfo_ismapped():
                    app._rebuild_sidebar_nav_only()
            except Exception:  # noqa: BLE001
                app._rebuild_sidebar_nav_only()
        app.set_status("Chat stays in PRIMARY — that menu stays open")
        return
    expanded = not bool((app._hub_expanded or {}).get(title, True))
    app._hub_expanded[title] = expanded
    frame = (app._hub_item_frames or {}).get(title)
    header = (app._hub_headers or {}).get(title)
    if header:
        try:
            header.configure(text=f"{'▾' if expanded else '▸'}  {title}")
        except Exception:  # noqa: BLE001
            pass
    if frame:
        if expanded:
            app._rebuild_sidebar_nav_only()
        else:
            try:
                frame.pack_forget()
            except Exception:  # noqa: BLE001
                pass


def ensure_nav_hub_for_page(app, page: str) -> None:
    hubs = getattr(app, "_nav_hubs", None)
    if not callable(hubs):
        return
    for title, items in hubs():
        if page not in items:
            continue
        if bool((app._hub_expanded or {}).get(title, True)):
            return
        app._hub_expanded[title] = True
        app._rebuild_sidebar_nav_only()
        return


def rebuild_sidebar_nav_only(app) -> None:
    try:
        if hasattr(app, "_sidebar_frame") and app._sidebar_frame.winfo_exists():
            app._sidebar_frame.destroy()
    except Exception:  # noqa: BLE001
        pass
    app._build_sidebar()
    app._ensure_app_sidebar()
    if app._current_page:
        from app.ui.themes import UI

        for n, btn in app._nav_buttons.items():
            label = app._nav_label_for(n)
            if n == app._current_page:
                btn.configure(
                    fg_color=UI["sidebar_active"],
                    text_color=UI["sidebar_active_text"],
                    text=f"●  {label}",
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    text_color=UI["sidebar_text"],
                    text=label,
                )


def ensure_app_sidebar(app) -> None:
    hidden = bool(getattr(app, "_sidebar_collapsed", False)) or bool(
        getattr(app, "_one_screen", False)
    )
    if hidden:
        try:
            if app._sidebar_alive():
                app._sidebar_frame.grid_remove()
        except Exception:  # noqa: BLE001
            pass
        exp = getattr(app, "_menu_expander", None)
        try:
            if exp is None or not bool(exp.winfo_exists()):
                app._build_menu_expander()
                exp = app._menu_expander
            exp.grid(row=0, column=0, sticky="nsw")
        except Exception:  # noqa: BLE001
            pass
        return
    if not app._sidebar_has_content():
        try:
            app._build_sidebar()
        except Exception:  # noqa: BLE001
            pass
    else:
        try:
            app._sidebar_frame.grid(row=0, column=0, sticky="nsw")
        except Exception:  # noqa: BLE001
            try:
                app._build_sidebar()
            except Exception:  # noqa: BLE001
                pass
    exp = getattr(app, "_menu_expander", None)
    try:
        if exp is not None and bool(exp.winfo_exists()):
            exp.grid_remove()
    except Exception:  # noqa: BLE001
        pass


def page_runs(app) -> None:
    from app.ui.themes import UI as _UI

    _HC_MUTED = _UI["muted"]
    root = ctk.CTkFrame(app.content, fg_color="transparent")
    root.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
    root.grid_columnconfigure(1, weight=1)
    root.grid_rowconfigure(1, weight=1)

    app._page_header(
        root,
        "Runs",
        "Sequential multi-task runs (mock or LLM).",
        columnspan=2,
    )

    left = ctk.CTkFrame(root)
    left.grid(row=1, column=0, sticky="nsw", padx=(0, 12))
    ctk.CTkButton(left, text="Start Run (mock)", command=lambda: app._start_run(False)).pack(
        fill="x", padx=8, pady=(8, 4)
    )
    ctk.CTkButton(
        left,
        text="Start Run (LLM)",
        command=lambda: app._start_run(True),
    ).pack(fill="x", padx=8, pady=(4, 8))
    ctk.CTkLabel(
        left,
        text="LLM needs API key\nin Settings",
        font=ctk.CTkFont(size=11),
        text_color=_HC_MUTED,
    ).pack(padx=8, pady=(0, 8))
    app.run_list = ctk.CTkScrollableFrame(left, width=240, height=420)
    app.run_list.pack(fill="both", expand=True, padx=8, pady=8)

    right = ctk.CTkFrame(root)
    right.grid(row=1, column=1, sticky="nsew")
    right.grid_rowconfigure(1, weight=1)
    right.grid_columnconfigure(0, weight=1)
    app.run_status_label = ctk.CTkLabel(right, text="Select a run or start a new one.")
    app.run_status_label.grid(row=0, column=0, sticky="w", padx=10, pady=8)
    app.run_log = ctk.CTkTextbox(right)
    app.run_log.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

    app._refresh_run_list()
    if not storage.list_runs():
        ctk.CTkLabel(app.run_list, text="No runs yet.").pack(padx=8, pady=16)
