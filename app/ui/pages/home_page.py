"""Home page — extracted from AppWindow."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import customtkinter as ctk

from app.services import storage
from app.ui.components.widget_names import set_widget_name, name_page_root, PAGE_HOME

if TYPE_CHECKING:
    from app.ui.app_window import AppWindow


def page_home(app) -> None:
    """Simple guided home — 4 big steps matching the product objective."""
    from app.ui.themes import style_chrome_button, style_card, UI as _UI

    frame = ctk.CTkFrame(app.content, fg_color="transparent")
    frame.grid(row=0, column=0, sticky="nsew", padx=24, pady=20)
    frame.grid_columnconfigure(0, weight=1)
    frame.grid_rowconfigure(2, weight=1)
    set_widget_name(frame, name_page_root(PAGE_HOME))

    try:
        from app.core.services.llm.providers import has_active_api_key

        key_ok = has_active_api_key()
    except Exception:  # noqa: BLE001
        key_ok = bool((storage.load_config().get("api_key") or "").strip())

    hero = ctk.CTkFrame(frame, **style_card())
    hero.grid(row=0, column=0, sticky="ew", pady=(0, 14))
    try:
        from app.core.services.system import branding as _branding

        _home_mark = _branding.ctk_brand_image(48)
        if _home_mark is not None:
            app._home_brand_image = _home_mark
            ctk.CTkLabel(hero, text="", image=_home_mark).pack(
                anchor="w", padx=20, pady=(16, 0)
            )
    except Exception:  # noqa: BLE001
        pass
    ctk.CTkLabel(
        hero,
        text="Welcome — pick one thing to do",
        font=ctk.CTkFont(size=26, weight="bold"),
        text_color=_UI["label"],
    ).pack(anchor="w", padx=20, pady=(18, 4))
    ctk.CTkLabel(
        hero,
        text=(
            "You do not need to be technical. Click one big button below.\n"
            "Left side = menu. Window top bar (OS) = minimize · maximize · close."
        ),
        text_color=_UI["muted"],
        font=ctk.CTkFont(size=14),
        justify="left",
    ).pack(anchor="w", padx=20, pady=(0, 8))

    if not key_ok:
        warn = ctk.CTkFrame(hero, fg_color=("#fef3c7", "#422006"), corner_radius=10)
        warn.pack(fill="x", padx=16, pady=(4, 8))
        ctk.CTkLabel(
            warn,
            text="First time? Tap the button to connect your AI account (like a password).",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=("#92400e", "#fde68a"),
        ).pack(side="left", padx=14, pady=12)
        ctk.CTkButton(
            warn,
            text="Connect now",
            width=130,
            command=app._show_onboarding_wizard,
            **style_chrome_button(primary=True),
        ).pack(side="right", padx=14, pady=10)
    else:
        ctk.CTkLabel(
            hero,
            text="✓ Ready — choose a step below",
            text_color=_UI["success"],
            font=ctk.CTkFont(size=13),
        ).pack(anchor="w", padx=20, pady=(0, 4))

    mode_row = ctk.CTkFrame(hero, fg_color="transparent")
    mode_row.pack(fill="x", padx=16, pady=(4, 14))
    simple = app._is_simple_ui()
    ctk.CTkButton(
        mode_row,
        text="😊 Easy (for everyone)" if simple else "Use Easy mode",
        width=180,
        command=lambda: app._set_simple_ui(True),
        **style_chrome_button(primary=simple),
    ).pack(side="left", padx=4)
    ctk.CTkButton(
        mode_row,
        text="🔧 Expert (all pages)" if not simple else "Show expert pages",
        width=180,
        command=lambda: app._set_simple_ui(False),
        **style_chrome_button(primary=not simple),
    ).pack(side="left", padx=4)
    ctk.CTkButton(
        mode_row,
        text="✦ Use Grok as my AI",
        width=200,
        height=32,
        command=app._use_grok_as_agent,
        **style_chrome_button(primary=True),
    ).pack(side="left", padx=8)

    preset_wrap = ctk.CTkFrame(hero, fg_color="transparent")
    preset_wrap.pack(fill="x", padx=16, pady=(0, 14))
    ctk.CTkLabel(
        preset_wrap,
        text="Quick start modes (sets tools for you):",
        font=ctk.CTkFont(size=13, weight="bold"),
        text_color=_UI["label"],
    ).pack(anchor="w", pady=(0, 6))
    preset_row = ctk.CTkFrame(preset_wrap, fg_color="transparent")
    preset_row.pack(fill="x")
    try:
        from app.core.services.misc.home_presets import list_presets

        for p in list_presets():
            ctk.CTkButton(
                preset_row,
                text=f"{p.get('icon', '')} {p.get('label')}",
                width=120,
                height=36,
                command=lambda pid=p["id"]: app._apply_home_preset(pid),
                **style_chrome_button(primary=True),
            ).pack(side="left", padx=4, pady=2)
    except Exception:  # noqa: BLE001
        pass

    from app.ui.components.ui_steps import build_step_strip, open_create_llm_wizard

    steps = [
        {
            "n": "1",
            "title": "Talk to AI",
            "body": (
                "Like WhatsApp: type a message at the bottom and press Enter.\n"
                "Examples: “What is on my Desktop?” or “Search the web for weather today.”"
            ),
            "btn": "Start talking",
            "page": "Chat",
            "prep": "chat",
        },
        {
            "n": "2",
            "title": "Use an AI team",
            "body": (
                "Several helpers work on one job and write messages you can read.\n"
                "Click Start team, write your goal in normal words, then wait for the final answer."
            ),
            "btn": "Start AI team",
            "page": "Team",
            "prep": None,
        },
        {
            "n": "3",
            "title": "Make my own AI",
            "body": (
                "Give it a name and a personality. No technical knowledge needed.\n"
                "One guided wizard — then you can chat with it."
            ),
            "btn": "✨ Make my AI",
            "page": "wizard",
            "prep": "wizard",
        },
        {
            "n": "4",
            "title": "See activity",
            "body": (
                "See if the computer is busy, if a job finished, or if something failed.\n"
                "Open this while the AI is working."
            ),
            "btn": "See activity",
            "page": "Monitor",
            "prep": None,
        },
    ]

    strip_bar = ctk.CTkFrame(frame, **style_card())
    strip_bar.grid(row=1, column=0, sticky="ew", pady=(0, 10))
    ctk.CTkLabel(
        strip_bar,
        text="Your path (all steps always visible):",
        font=ctk.CTkFont(size=12, weight="bold"),
        text_color=_UI["label"],
    ).pack(anchor="w", padx=14, pady=(10, 4))
    build_step_strip(
        strip_bar,
        ["Talk", "AI team", "Make my AI", "Activity"],
        current=0,
    ).pack(anchor="w", padx=14, pady=(0, 12))

    scroll = ctk.CTkScrollableFrame(frame, fg_color="transparent")
    scroll.grid(row=2, column=0, sticky="nsew")
    frame.grid_rowconfigure(2, weight=1)
    scroll.grid_columnconfigure(0, weight=1)

    def go(step: dict) -> None:
        if step.get("prep") == "wizard" or step.get("page") == "wizard":
            open_create_llm_wizard(app)
            return
        if step.get("prep") == "chat":
            if hasattr(app, "_chat_state"):
                app._chat_state["mode"] = "action"
                app._chat_state["terminal_enabled"] = True
                app._chat_state["use_workflow_graph"] = False
            if hasattr(app, "chat_mode_var"):
                try:
                    app.chat_mode_var.set("action")
                except Exception:  # noqa: BLE001
                    pass
            if hasattr(app, "chat_terminal_var"):
                try:
                    app.chat_terminal_var.set(True)
                except Exception:  # noqa: BLE001
                    pass
        app.show_page(str(step["page"]))

    for s in steps:
        card = ctk.CTkFrame(scroll, **style_card())
        card.pack(fill="x", pady=10, padx=4)
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=4, pady=4)
        strip = ctk.CTkFrame(
            inner, width=4, fg_color=_UI["accent"], corner_radius=2
        )
        strip.pack(side="left", fill="y", padx=(8, 0), pady=8)
        body_col = ctk.CTkFrame(inner, fg_color="transparent")
        body_col.pack(side="left", fill="both", expand=True, padx=8)
        top = ctk.CTkFrame(body_col, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(14, 4))
        badge = ctk.CTkLabel(
            top,
            text=s["n"],
            width=44,
            height=44,
            corner_radius=22,
            fg_color=_UI["btn_primary_bg"],
            text_color=_UI["btn_primary_text"],
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        badge.pack(side="left", padx=(0, 14))
        ctk.CTkLabel(
            top,
            text=s["title"],
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=_UI["label"],
            anchor="w",
        ).pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(
            body_col,
            text=s["body"],
            text_color=_UI["muted"],
            font=ctk.CTkFont(size=14),
            justify="left",
            wraplength=740,
            anchor="w",
        ).pack(anchor="w", padx=70, pady=(0, 10))
        ctk.CTkButton(
            body_col,
            text=s["btn"] + "  →",
            width=200,
            height=40,
            corner_radius=12,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=lambda st=s: go(st),
            **style_chrome_button(primary=True),
        ).pack(anchor="w", padx=70, pady=(0, 18))

    faq = ctk.CTkFrame(frame, **style_card())
    faq.grid(row=3, column=0, sticky="ew", pady=(12, 0))
    ctk.CTkLabel(
        faq,
        text="Quick answers",
        font=ctk.CTkFont(size=14, weight="bold"),
        text_color=_UI["label"],
    ).pack(anchor="w", padx=16, pady=(12, 4))
    faq_text = (
        "• Make an AI: tap “Make my AI” (step 3). Answer 3 short questions.\n"
        "• Talk to AI: tap “Start talking”, type, press Enter.\n"
        "• Window too small? Use the OS maximize button on the top title bar.\n"
        "• More options? Left bottom “Show all pages”.\n"
        "• Stuck? Left bottom “Help me”."
    )
    ctk.CTkLabel(
        faq,
        text=faq_text,
        text_color=_UI["muted"],
        font=ctk.CTkFont(size=12),
        justify="left",
        wraplength=760,
        anchor="w",
    ).pack(anchor="w", padx=16, pady=(0, 14))


def apply_home_preset(app, preset_id: str) -> None:
    """Task #5: apply Research / Control PC / Code / Team tool flags and open page."""
    from app.core.services.misc.home_presets import get_preset, apply_preset_to_chat_state
    from app.services import chat_store as chat_svc

    p = get_preset(preset_id)
    if not p:
        app.set_status(f"Unknown preset: {preset_id}", toast=True)
        return
    try:
        from app.services.agent_harness.permissions import set_risk_tier

        set_risk_tier(str(p.get("risk_tier") or "ask"))
    except Exception:  # noqa: BLE001
        pass
    try:
        if not getattr(app, "_chat_state", None):
            app._chat_state = app._load_active_chat()
        apply_preset_to_chat_state(app._chat_state, str(p["id"]))
        chat_svc.save_chat(app._chat_state)
    except Exception:  # noqa: BLE001
        try:
            if hasattr(app, "_chat_state") and app._chat_state is not None:
                apply_preset_to_chat_state(app._chat_state, str(p["id"]))
        except Exception:  # noqa: BLE001
            pass
    try:
        if hasattr(app, "chat_mode_var"):
            app.chat_mode_var.set(str(p.get("mode") or "action"))
        if hasattr(app, "chat_terminal_var"):
            app.chat_terminal_var.set(bool(p.get("terminal_enabled")))
        if hasattr(app, "chat_laptop_var"):
            app.chat_laptop_var.set(bool(p.get("laptop_enabled")))
        if hasattr(app, "chat_skills_var"):
            app.chat_skills_var.set(bool(p.get("skills_enabled", True)))
        if hasattr(app, "chat_mcp_var"):
            app.chat_mcp_var.set(bool(p.get("mcp_enabled", True)))
        if hasattr(app, "chat_safety_var"):
            app.chat_safety_var.set(bool(p.get("safety_mode")))
        if hasattr(app, "chat_workflow_var"):
            app.chat_workflow_var.set(bool(p.get("use_workflow_graph")))
        if hasattr(app, "_on_chat_flags_save"):
            try:
                app._on_chat_flags_save()
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass

    page = str(p.get("page") or "Chat")
    app.set_status(str(p.get("status") or p.get("label")), toast=True)
    app.show_page(page)
    starter = str(p.get("starter") or "")
    if page == "Chat" and starter:

        def _fill() -> None:
            try:
                if hasattr(app, "chat_input"):
                    app._composer_is_placeholder = False
                    app.chat_input.delete("1.0", "end")
                    app.chat_input.insert("1.0", starter)
                    from app.ui.themes import UI as _UI

                    app.chat_input.configure(text_color=_UI["label"])
                    app._update_composer_status()
            except Exception:  # noqa: BLE001
                pass

        try:
            app.after(120, _fill)
        except Exception:  # noqa: BLE001
            _fill()
