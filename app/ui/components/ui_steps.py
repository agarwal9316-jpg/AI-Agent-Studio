"""Visible multi-step progress strip for layman-friendly wizards."""

from __future__ import annotations

from typing import Any, Callable

import customtkinter as ctk

from app.ui.themes import UI as _UI


def build_step_strip(
    parent: Any,
    steps: list[str],
    *,
    current: int = 0,
    font_size: int = 12,
) -> ctk.CTkFrame:
    """
    Horizontal step indicator: ① Label — ② Label — ③ Label
    current is 0-based index of active step (highlighted).
    """
    bar = ctk.CTkFrame(parent, fg_color="transparent")
    for i, label in enumerate(steps):
        active = i == current
        done = i < current
        bg = (
            ("#22c55e", "#166534")
            if done
            else (("#3b82f6", "#1d4ed8") if active else ("#e5e7eb", "#374151"))
        )
        fg = ("#ffffff", "#ffffff") if (active or done) else _UI["muted"]
        cell = ctk.CTkFrame(bar, fg_color="transparent")
        cell.pack(side="left", padx=(0, 6))
        num = ctk.CTkLabel(
            cell,
            text=str(i + 1),
            width=28,
            height=28,
            corner_radius=14,
            fg_color=bg,
            text_color=fg,
            font=ctk.CTkFont(size=font_size, weight="bold"),
        )
        num.pack(side="left", padx=(0, 6))
        ctk.CTkLabel(
            cell,
            text=label,
            text_color=_UI["label"] if active or done else _UI["muted"],
            font=ctk.CTkFont(size=font_size, weight="bold" if active else "normal"),
        ).pack(side="left")
        if i < len(steps) - 1:
            ctk.CTkLabel(bar, text="→", text_color=_UI["muted"]).pack(side="left", padx=4)
    return bar


def open_create_llm_wizard(app: Any) -> None:
    """One-flow wizard so a layman can create a usable LLM with few clicks."""
    from app.services import model_profiles as mp
    from app.ui.themes import style_chrome_button, style_card
    from app.core.services.system.ops_monitor import log_event

    win = ctk.CTkToplevel(app)
    win.title("Make my AI")
    win.geometry("560x540")
    win.minsize(480, 420)
    try:
        win.transient(app)
        win.grab_set()
    except Exception:  # noqa: BLE001
        pass

    steps = ["Name", "Style", "Where it runs", "Finish"]
    state = {"i": 0, "name": "My AI", "persona": "general", "where": "cloud"}

    header = ctk.CTkFrame(win, fg_color="transparent")
    header.pack(fill="x", padx=16, pady=(16, 8))
    ctk.CTkLabel(
        header,
        text="Make my AI",
        font=ctk.CTkFont(size=22, weight="bold"),
        text_color=_UI["label"],
    ).pack(anchor="w")
    ctk.CTkLabel(
        header,
        text="Like adding a new contact. Answer three easy questions, then press the green button.",
        text_color=_UI["muted"],
    ).pack(anchor="w")

    strip_host = ctk.CTkFrame(win, fg_color="transparent")
    strip_host.pack(fill="x", padx=16, pady=8)

    body = ctk.CTkFrame(win, **style_card())
    body.pack(fill="both", expand=True, padx=16, pady=8)

    status = ctk.CTkLabel(win, text="", text_color=_UI["muted"])
    status.pack(anchor="w", padx=16)

    foot = ctk.CTkFrame(win, fg_color="transparent")
    foot.pack(fill="x", padx=16, pady=12)

    personas = {
        "general": (
            "Everyday helper (recommended)",
            "You are a friendly, clear assistant. Explain simply. Use tools when they help.",
        ),
        "coder": (
            "Helps with computer / code",
            "You are a software engineer on the user's Windows PC. Prefer TERMINAL and files. Write working code.",
        ),
        "research": (
            "Looks things up online",
            "You research with WEB_SEARCH and DEEP_RESEARCH. Give sources and clear summaries.",
        ),
        "operator": (
            "Controls this PC carefully",
            "You control the Windows PC with TERMINAL, GUI, and SCREENSHOT. Act carefully and report results.",
        ),
    }

    widgets: dict[str, Any] = {}

    def paint_strip() -> None:
        for w in strip_host.winfo_children():
            w.destroy()
        build_step_strip(strip_host, steps, current=state["i"]).pack(anchor="w")

    def clear_body() -> None:
        for w in body.winfo_children():
            w.destroy()

    def paint() -> None:
        paint_strip()
        clear_body()
        i = state["i"]
        if i == 0:
            ctk.CTkLabel(
                body,
                text="What should we call your AI?",
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color=_UI["label"],
            ).pack(anchor="w", padx=16, pady=(16, 8))
            e = ctk.CTkEntry(body, placeholder_text="e.g. Office Buddy, Code Helper")
            e.pack(fill="x", padx=16, pady=8)
            e.insert(0, state.get("name") or "My AI")
            widgets["name"] = e
            ctk.CTkLabel(
                body,
                text="This is just a friendly name. You can change it later.",
                text_color=_UI["muted"],
            ).pack(anchor="w", padx=16, pady=(0, 16))
        elif i == 1:
            ctk.CTkLabel(
                body,
                text="What should it be good at?",
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color=_UI["label"],
            ).pack(anchor="w", padx=16, pady=(16, 8))
            var = ctk.StringVar(value=state.get("persona") or "general")
            widgets["persona"] = var
            for key, (title, _sys) in personas.items():
                ctk.CTkRadioButton(
                    body, text=title, variable=var, value=key
                ).pack(anchor="w", padx=20, pady=4)
            ctk.CTkLabel(
                body,
                text="We write the instructions for you. You do not need to edit anything.",
                text_color=_UI["muted"],
            ).pack(anchor="w", padx=16, pady=12)
        elif i == 2:
            from app.ui.components.layman_copy import WIZARD_WHERE_CLOUD, WIZARD_WHERE_LOCAL

            ctk.CTkLabel(
                body,
                text="Where should it run?",
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color=_UI["label"],
            ).pack(anchor="w", padx=16, pady=(16, 8))
            var = ctk.StringVar(value=state.get("where") or "cloud")
            widgets["where"] = var
            ctk.CTkRadioButton(
                body,
                text=WIZARD_WHERE_CLOUD,
                variable=var,
                value="cloud",
            ).pack(anchor="w", padx=20, pady=6)
            ctk.CTkRadioButton(
                body,
                text=WIZARD_WHERE_LOCAL,
                variable=var,
                value="ollama",
            ).pack(anchor="w", padx=20, pady=6)
            ctk.CTkLabel(
                body,
                text="If you are not sure, keep “Internet AI”. You can change later.",
                text_color=_UI["muted"],
            ).pack(anchor="w", padx=16, pady=12)
        else:
            from app.ui.components.layman_copy import WIZARD_RUNS_CLOUD, WIZARD_RUNS_LOCAL

            ctk.CTkLabel(
                body,
                text="Ready — one click finishes setup",
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color=_UI["label"],
            ).pack(anchor="w", padx=16, pady=(16, 8))
            persona_title = personas.get(state.get("persona") or "general", ("General", ""))[0]
            where = WIZARD_RUNS_CLOUD if state.get("where") == "cloud" else WIZARD_RUNS_LOCAL
            ctk.CTkLabel(
                body,
                text=(
                    f"Name: {state.get('name')}\n"
                    f"Style: {persona_title}\n"
                    f"Runs on: {where}\n\n"
                    "Press the green button below."
                ),
                text_color=_UI["muted"],
                justify="left",
            ).pack(anchor="w", padx=16, pady=8)

        # Footer buttons
        for w in foot.winfo_children():
            w.destroy()
        if state["i"] > 0:
            ctk.CTkButton(
                foot, text="← Back", width=100, command=back, **style_chrome_button()
            ).pack(side="left", padx=4)
        ctk.CTkButton(foot, text="Cancel", width=90, command=win.destroy, **style_chrome_button()).pack(
            side="left", padx=4
        )
        if state["i"] < 3:
            ctk.CTkButton(
                foot, text="Next →", width=120, command=next_step, **style_chrome_button(primary=True)
            ).pack(side="right", padx=4)
        else:
            ctk.CTkButton(
                foot,
                text="✨ Make my AI",
                width=160,
                command=finish_create,
                **style_chrome_button(primary=True),
            ).pack(side="right", padx=4)

    def save_step() -> bool:
        i = state["i"]
        if i == 0:
            name = widgets.get("name")
            if name is not None:
                state["name"] = name.get().strip() or "My AI"
        elif i == 1:
            var = widgets.get("persona")
            if var is not None:
                state["persona"] = var.get()
        elif i == 2:
            var = widgets.get("where")
            if var is not None:
                state["where"] = var.get()
        return True

    def next_step() -> None:
        if not save_step():
            return
        state["i"] = min(3, state["i"] + 1)
        paint()

    def back() -> None:
        save_step()
        state["i"] = max(0, state["i"] - 1)
        paint()

    def finish_create() -> None:
        save_step()
        name = state.get("name") or "My AI"
        persona = state.get("persona") or "general"
        where = state.get("where") or "cloud"
        _title, system = personas.get(persona, personas["general"])
        status.configure(text="Creating…")
        win.update_idletasks()
        try:
            if where == "ollama":
                from app.core.services.misc.cloud_finetune import create_ollama_modelfile_model
                from app.core.services.llm.model_profiles import ollama_list_models

                ol = ollama_list_models()
                if not ol.get("running"):
                    # Still create a profile pointing at Ollama defaults
                    prof = mp.create_profile(
                        name,
                        kind="ollama",
                        base_url="http://127.0.0.1:11434/v1",
                        model="llama3.2",
                        api_key="ollama",
                        system_prompt=system,
                        notes="Created by easy wizard (start Ollama to use)",
                    )
                    status.configure(
                        text="Saved. Install and start free Ollama software, then try again.",
                        text_color=_UI.get("warning", _UI["muted"]),
                    )
                else:
                    models = ol.get("models") or []
                    base = str((models[0] or {}).get("name") or "llama3.2")
                    slug = name.lower().replace(" ", "-")[:32] or "my-ai"
                    res = create_ollama_modelfile_model(
                        slug, from_model=base, system_prompt=system
                    )
                    if res.get("ok"):
                        prof = res.get("profile")
                    else:
                        prof = mp.create_profile(
                            name,
                            kind="ollama",
                            base_url="http://127.0.0.1:11434/v1",
                            model=base,
                            api_key="ollama",
                            system_prompt=system,
                            notes=str(res.get("error") or ""),
                        )
            else:
                from app.core.services.llm.providers import resolve_active_llm

                active = resolve_active_llm()
                prof = mp.create_profile(
                    name,
                    kind="cloud",
                    base_url=str(active.get("base_url") or "https://openrouter.ai/api/v1"),
                    model=str(active.get("model") or "openai/gpt-4o-mini"),
                    api_key=str(active.get("api_key") or ""),
                    system_prompt=system,
                    notes=f"Easy wizard · {persona}",
                )
            log_event("model_profile", f"Easy wizard created {name}", source="wizard")
            # Offer chat
            def open_chat() -> None:
                try:
                    win.destroy()
                except Exception:  # noqa: BLE001
                    pass
                # Stash preferred system prompt into chat if possible
                try:
                    if hasattr(app, "cfg") and isinstance(app.cfg, dict) and prof:
                        # user can pick model in chat; set status
                        pass
                    app.show_page("Chat")
                    if hasattr(app, "chat_input"):
                        app.chat_input.delete("1.0", "end")
                        app.chat_input.insert(
                            "1.0",
                            f"Hi — you are now talking with me as “{name}”. Introduce yourself briefly.",
                        )
                    app.set_status(f"Created AI “{name}” — say hi in Chat", toast=True)
                except Exception:  # noqa: BLE001
                    pass

            for w in body.winfo_children():
                w.destroy()
            ctk.CTkLabel(
                body,
                text=f"✓ “{name}” is ready!",
                font=ctk.CTkFont(size=18, weight="bold"),
                text_color=_UI.get("success", _UI["label"]),
            ).pack(anchor="w", padx=16, pady=(20, 8))
            from app.ui.components.layman_copy import WIZARD_SUCCESS_HINT

            ctk.CTkLabel(
                body,
                text=WIZARD_SUCCESS_HINT,
                text_color=_UI["muted"],
            ).pack(anchor="w", padx=16, pady=4)
            ctk.CTkButton(
                body,
                text="Talk to my AI →",
                width=180,
                command=open_chat,
                **style_chrome_button(primary=True),
            ).pack(anchor="w", padx=16, pady=16)
            for w in foot.winfo_children():
                w.destroy()
            ctk.CTkButton(foot, text="Close", command=win.destroy, **style_chrome_button()).pack(
                side="right"
            )
            paint_strip()
            state["i"] = 3
        except Exception as e:  # noqa: BLE001
            status.configure(text=f"Failed: {e}", text_color="tomato")

    paint()
