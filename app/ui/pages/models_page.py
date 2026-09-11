"""Models hub: profiles, Ollama, create LLM, train lab."""

from __future__ import annotations

import threading
import tkinter.messagebox as messagebox
from typing import TYPE_CHECKING, Any

import customtkinter as ctk

from app.ui.themes import UI as _UI
from app.ui.themes import style_chrome_button, style_card

if TYPE_CHECKING:
    from app.ui.app_window import AppWindow

_HC_MUTED = _UI["muted"]
_HC_LABEL = _UI["label"]


def page_models(app: AppWindow) -> None:
    from app.services import model_profiles as mp
    from app.services import train_lab as tl
    from app.ui.components.layman_copy import (
        MODELS_SAVED,
        MODELS_ADVANCED_TOGGLE,
        MODELS_ADVANCED_HIDE,
        MODELS_EASY_BANNER,
        MODELS_EASY_NOTE,
    )

    simple = bool(getattr(app, "_is_simple_ui", lambda: True)())

    root = ctk.CTkFrame(app.content, fg_color="transparent")
    root.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
    root.grid_columnconfigure(0, weight=1)
    root.grid_rowconfigure(3, weight=1)

    app._page_header(
        root,
        "My AIs",
        (
            "Make a personal helper. Tap the big button — no coding needed."
            if simple
            else "Profiles, Ollama, create, and train tools for advanced users."
        ),
        actions=[
            ("← Start", lambda: app.show_page("Home")),
            ("See activity", lambda: app.show_page("Monitor")),
        ],
    )

    row = 1
    # Easy-mode orientation strip
    if simple:
        tip = ctk.CTkFrame(
            root, fg_color=_UI.get("accent_soft", ("#dbeafe", "#1e293b")), corner_radius=10
        )
        tip.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        row += 1
        ctk.CTkLabel(
            tip,
            text="Tip: Start with “Make my AI now”. Expert tools stay hidden until you open full menu.",
            text_color=_HC_LABEL,
            font=ctk.CTkFont(size=12),
            anchor="w",
        ).pack(fill="x", padx=14, pady=10)

    # One-click create for laymen
    from app.ui.components.ui_steps import build_step_strip, open_create_llm_wizard

    easy = ctk.CTkFrame(root, **style_card())
    easy.grid(row=row, column=0, sticky="ew", pady=(0, 8))
    row += 1
    ctk.CTkLabel(
        easy,
        text=MODELS_EASY_BANNER,
        font=ctk.CTkFont(size=16, weight="bold"),
        text_color=_HC_LABEL,
    ).pack(anchor="w", padx=14, pady=(14, 4))
    build_step_strip(
        easy, ["Give a name", "Pick a style", "Choose internet or this PC", "Finish"], current=0
    ).pack(anchor="w", padx=14, pady=6)
    ctk.CTkButton(
        easy,
        text="✨ Make my AI now",
        width=260,
        height=48,
        command=lambda: open_create_llm_wizard(app),
        **style_chrome_button(primary=True),
    ).pack(anchor="w", padx=14, pady=(8, 6))
    ctk.CTkLabel(
        easy,
        text=MODELS_EASY_NOTE,
        text_color=_HC_MUTED,
        font=ctk.CTkFont(size=12),
        justify="left",
        wraplength=900,
        anchor="w",
    ).pack(anchor="w", padx=14, pady=(0, 14))

    # Easy mode: list saved AIs simply + hide advanced until asked
    if simple:
        saved_card = ctk.CTkFrame(root, **style_card())
        saved_card.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        row += 1
        ctk.CTkLabel(
            saved_card,
            text=MODELS_SAVED,
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=_HC_LABEL,
        ).pack(anchor="w", padx=14, pady=(12, 6))
        saved_list = ctk.CTkFrame(saved_card, fg_color="transparent")
        saved_list.pack(fill="x", padx=10, pady=(0, 8))
        profiles = list(mp.list_profiles() or [])
        if not profiles:
            ctk.CTkLabel(
                saved_list,
                text="None yet. Tap “Make my AI now” above.",
                text_color=_HC_MUTED,
            ).pack(anchor="w", padx=8, pady=8)
        else:
            for p in profiles[:20]:
                prow = ctk.CTkFrame(saved_list, fg_color="transparent")
                prow.pack(fill="x", pady=3)
                ctk.CTkLabel(
                    prow,
                    text=f"●  {p.get('name') or 'AI'}",
                    text_color=_HC_LABEL,
                    font=ctk.CTkFont(size=14),
                    anchor="w",
                ).pack(side="left", padx=8)

                pname = str(p.get("name") or "AI")

                def _chat_as(name: str = pname) -> None:
                    app.show_page("Chat")
                    try:
                        if hasattr(app, "chat_input"):
                            app.chat_input.delete("1.0", "end")
                            app.chat_input.insert(
                                "1.0",
                                f"Hi — talk to me as “{name}”. Introduce yourself briefly.",
                            )
                        app.set_status(
                            f"Ready to chat as “{name}” — press Send message", toast=True
                        )
                    except Exception:  # noqa: BLE001
                        pass

                ctk.CTkButton(
                    prow,
                    text="Talk to this AI",
                    width=130,
                    command=_chat_as,
                    **style_chrome_button(primary=True),
                ).pack(side="right", padx=8)

        adv_host = ctk.CTkFrame(root, fg_color="transparent")
        adv_host.grid(row=row, column=0, sticky="nsew")
        root.grid_rowconfigure(row, weight=1)
        adv_body_holder: dict[str, Any] = {"built": False, "frame": None}

        def toggle_advanced() -> None:
            if not adv_body_holder["built"]:
                body = ctk.CTkScrollableFrame(adv_host, fg_color="transparent")
                body.pack(fill="both", expand=True)
                body.grid_columnconfigure((0, 1), weight=1)
                adv_body_holder["frame"] = body
                adv_body_holder["built"] = True
                _build_advanced_models(app, body, mp, tl)
                toggle_btn.configure(text=MODELS_ADVANCED_HIDE)
            else:
                fr = adv_body_holder.get("frame")
                if fr is not None:
                    try:
                        if fr.winfo_ismapped():
                            fr.pack_forget()
                            toggle_btn.configure(text=MODELS_ADVANCED_TOGGLE)
                        else:
                            fr.pack(fill="both", expand=True)
                            toggle_btn.configure(text=MODELS_ADVANCED_HIDE)
                    except Exception:  # noqa: BLE001
                        pass

        toggle_btn = ctk.CTkButton(
            saved_card,
            text=MODELS_ADVANCED_TOGGLE,
            command=toggle_advanced,
            **style_chrome_button(),
        )
        toggle_btn.pack(anchor="w", padx=14, pady=(4, 14))
        return

    body = ctk.CTkScrollableFrame(root, fg_color="transparent")
    body.grid(row=2, column=0, sticky="nsew")
    root.grid_rowconfigure(2, weight=1)
    body.grid_columnconfigure((0, 1), weight=1)
    _build_advanced_models(app, body, mp, tl)


def _build_advanced_models(app: AppWindow, body: Any, mp: Any, tl: Any) -> None:
    """Expert: profiles, Ollama, train lab — only when requested."""
    # ----- Profiles -----
    left = ctk.CTkFrame(body, **style_card())
    left.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=6)
    ctk.CTkLabel(
        left, text="Model profiles (expert)", font=ctk.CTkFont(size=15, weight="bold"), text_color=_HC_LABEL
    ).pack(anchor="w", padx=12, pady=(12, 4))
    prof_list = ctk.CTkScrollableFrame(left, height=220, fg_color="transparent")
    prof_list.pack(fill="both", expand=True, padx=8, pady=4)

    form = ctk.CTkFrame(left, fg_color="transparent")
    form.pack(fill="x", padx=10, pady=8)
    name_e = ctk.CTkEntry(form, placeholder_text="Profile name")
    name_e.pack(fill="x", pady=2)
    kind_var = ctk.StringVar(master=form, value="ollama")
    ctk.CTkOptionMenu(
        form, variable=kind_var, values=["ollama", "openai_compatible", "cloud"], width=200
    ).pack(anchor="w", pady=2)
    base_e = ctk.CTkEntry(form, placeholder_text="Base URL")
    base_e.insert(0, "http://127.0.0.1:11434/v1")
    base_e.pack(fill="x", pady=2)
    model_e = ctk.CTkEntry(form, placeholder_text="Model id")
    model_e.insert(0, "llama3.2")
    model_e.pack(fill="x", pady=2)
    key_e = ctk.CTkEntry(form, placeholder_text="API key (ollama ok for local)", show="*")
    key_e.insert(0, "ollama")
    key_e.pack(fill="x", pady=2)
    sys_e = ctk.CTkTextbox(form, height=50)
    sys_e.pack(fill="x", pady=2)
    adapter_e = ctk.CTkEntry(form, placeholder_text="Adapter path (optional)")
    adapter_e.pack(fill="x", pady=2)
    status_l = ctk.CTkLabel(form, text="", text_color=_HC_MUTED)
    status_l.pack(anchor="w")

    state: dict[str, Any] = {"profile_id": ""}

    def refresh_profiles() -> None:
        for w in prof_list.winfo_children():
            w.destroy()
        for p in mp.list_profiles():
            lab = f"{p.get('name')} · {p.get('model')}"
            ctk.CTkButton(
                prof_list,
                text=lab[:60],
                anchor="w",
                fg_color="transparent",
                command=lambda i=p["id"]: select_profile(i),
            ).pack(fill="x", pady=1)

    def select_profile(pid: str) -> None:
        p = mp.get_profile(pid)
        if not p:
            return
        state["profile_id"] = pid
        name_e.delete(0, "end")
        name_e.insert(0, p.get("name") or "")
        kind_var.set(p.get("kind") or "openai_compatible")
        base_e.delete(0, "end")
        base_e.insert(0, p.get("base_url") or "")
        model_e.delete(0, "end")
        model_e.insert(0, p.get("model") or "")
        key_e.delete(0, "end")
        key_e.insert(0, p.get("api_key") or "")
        sys_e.delete("1.0", "end")
        sys_e.insert("1.0", p.get("system_prompt") or "")
        adapter_e.delete(0, "end")
        adapter_e.insert(0, p.get("adapter_path") or "")
        status_l.configure(text=f"Editing {pid[:8]}…")

    def save_prof() -> None:
        p = {
            "id": state.get("profile_id") or "",
            "name": name_e.get().strip() or "My model",
            "kind": kind_var.get(),
            "base_url": base_e.get().strip(),
            "model": model_e.get().strip(),
            "api_key": key_e.get().strip(),
            "system_prompt": sys_e.get("1.0", "end").strip(),
            "adapter_path": adapter_e.get().strip(),
        }
        saved = mp.save_profile(p)
        state["profile_id"] = saved["id"]
        refresh_profiles()
        status_l.configure(text="✓ Profile saved", text_color=_UI.get("success", _HC_LABEL))
        app.set_status(f"Model profile saved: {saved.get('name')}", toast=True)

    def test_prof() -> None:
        p = {
            "api_key": key_e.get().strip() or "ollama",
            "model": model_e.get().strip(),
            "base_url": base_e.get().strip(),
        }
        status_l.configure(text="Testing…")
        root.update_idletasks()

        def work() -> None:
            res = mp.test_profile_completion(p)

            def done() -> None:
                if res.get("ok"):
                    status_l.configure(
                        text=f"✓ OK · {res.get('latency_ms')}ms · {str(res.get('reply'))[:40]}",
                        text_color=_UI.get("success", _HC_LABEL),
                    )
                else:
                    status_l.configure(text=f"✗ {res.get('error')}", text_color="tomato")

            try:
                app.after(0, done)
            except Exception:  # noqa: BLE001
                pass

        threading.Thread(target=work, daemon=True).start()

    def del_prof() -> None:
        pid = state.get("profile_id")
        if not pid:
            return
        if messagebox.askyesno("Delete", "Delete this profile?", parent=app):
            mp.delete_profile(str(pid))
            state["profile_id"] = ""
            refresh_profiles()

    btns = ctk.CTkFrame(form, fg_color="transparent")
    btns.pack(fill="x", pady=6)
    ctk.CTkButton(btns, text="💾 Save profile", command=save_prof, **style_chrome_button(primary=True)).pack(
        side="left", padx=2
    )
    ctk.CTkButton(btns, text="Test", width=70, command=test_prof).pack(side="left", padx=2)
    ctk.CTkButton(btns, text="Delete", width=70, fg_color="#a33", command=del_prof).pack(side="left", padx=2)

    # Ollama
    ol = ctk.CTkFrame(left, fg_color="transparent")
    ol.pack(fill="x", padx=10, pady=(0, 12))
    ctk.CTkLabel(ol, text="Ollama (local)", font=ctk.CTkFont(weight="bold"), text_color=_HC_LABEL).pack(
        anchor="w"
    )
    ol_status = ctk.CTkLabel(ol, text="", text_color=_HC_MUTED, wraplength=320, justify="left")
    ol_status.pack(anchor="w")
    pull_e = ctk.CTkEntry(ol, placeholder_text="model to pull e.g. qwen2.5:7b")
    pull_e.pack(fill="x", pady=4)

    def refresh_ollama() -> None:
        r = mp.ollama_list_models()
        if r.get("running"):
            names = ", ".join(str(m.get("name")) for m in (r.get("models") or [])[:12]) or "(none)"
            ol_status.configure(text=f"● Ollama running · {names}", text_color=_UI.get("success", _HC_LABEL))
        else:
            ol_status.configure(
                text=f"○ Ollama not reachable ({r.get('error')}) — start ollama serve",
                text_color=_UI.get("warning", _HC_MUTED),
            )

    def do_pull() -> None:
        name = pull_e.get().strip()
        if not name:
            return
        ol_status.configure(text=f"Pulling {name}…")

        def work() -> None:
            res = mp.ollama_pull(name, on_line=lambda c: None)

            def done() -> None:
                if res.get("ok"):
                    ol_status.configure(text=f"✓ Pulled {name} + profile created")
                    refresh_profiles()
                    refresh_ollama()
                else:
                    ol_status.configure(text=f"✗ {res.get('error')}", text_color="tomato")

            try:
                app.after(0, done)
            except Exception:  # noqa: BLE001
                pass

        threading.Thread(target=work, daemon=True).start()

    obr = ctk.CTkFrame(ol, fg_color="transparent")
    obr.pack(fill="x")
    ctk.CTkButton(obr, text="Refresh Ollama", command=refresh_ollama, width=120).pack(side="left", padx=2)
    ctk.CTkButton(obr, text="Pull model", command=do_pull, **style_chrome_button(primary=True)).pack(
        side="left", padx=2
    )

    # Ollama Modelfile create
    mf = ctk.CTkFrame(left, fg_color="transparent")
    mf.pack(fill="x", padx=10, pady=(0, 10))
    ctk.CTkLabel(mf, text="Create structure (local Modelfile)", font=ctk.CTkFont(weight="bold"), text_color=_HC_LABEL).pack(anchor="w")
    mf_name = ctk.CTkEntry(mf, placeholder_text="new model name e.g. my-coder")
    mf_name.pack(fill="x", pady=2)
    mf_from = ctk.CTkEntry(mf, placeholder_text="FROM base e.g. llama3.2")
    mf_from.insert(0, "llama3.2")
    mf_from.pack(fill="x", pady=2)
    mf_sys = ctk.CTkEntry(mf, placeholder_text="SYSTEM prompt for the new model")
    mf_sys.pack(fill="x", pady=2)
    mf_st = ctk.CTkLabel(mf, text="", text_color=_HC_MUTED)
    mf_st.pack(anchor="w")

    def do_modelfile() -> None:
        from app.core.services.misc.cloud_finetune import create_ollama_modelfile_model

        mf_st.configure(text="Creating…")

        def work() -> None:
            res = create_ollama_modelfile_model(
                mf_name.get().strip(),
                from_model=mf_from.get().strip(),
                system_prompt=mf_sys.get().strip(),
            )

            def done() -> None:
                if res.get("ok"):
                    mf_st.configure(text=f"✓ Created {res.get('model')}", text_color=_UI.get("success", _HC_LABEL))
                    refresh_profiles()
                else:
                    mf_st.configure(text=f"✗ {res.get('error')}", text_color="tomato")

            try:
                app.after(0, done)
            except Exception:  # noqa: BLE001
                pass

        threading.Thread(target=work, daemon=True).start()

    ctk.CTkButton(mf, text="Create Ollama model", command=do_modelfile, **style_chrome_button(primary=True)).pack(
        anchor="w", pady=4
    )

    # ----- Structure methods catalog + cloud FT -----
    mid = ctk.CTkFrame(body, **style_card())
    mid.grid(row=1, column=0, columnspan=2, sticky="ew", padx=0, pady=6)
    ctk.CTkLabel(
        mid,
        text="LLM structure methods (all known ways)",
        font=ctk.CTkFont(size=15, weight="bold"),
        text_color=_HC_LABEL,
    ).pack(anchor="w", padx=12, pady=(12, 2))
    ctk.CTkLabel(
        mid,
        text=(
            "OpenAI = hosted fine-tune (SFT/DPO). OpenRouter = teacher for distillation + chat "
            "(not hosted FT). Local = LoRA/Modelfile/profiles/RAG/org."
        ),
        text_color=_HC_MUTED,
        wraplength=900,
        justify="left",
    ).pack(anchor="w", padx=12, pady=(0, 6))
    methods_box = ctk.CTkTextbox(mid, height=120, font=ctk.CTkFont(size=11))
    methods_box.pack(fill="x", padx=10, pady=(0, 8))
    try:
        from app.core.services.llm.llm_structure_methods import methods_help_text

        methods_box.insert("1.0", methods_help_text())
    except Exception:  # noqa: BLE001
        methods_box.insert("1.0", "(methods catalog unavailable)")
    methods_box.configure(state="disabled")

    # ----- Train lab -----
    right = ctk.CTkFrame(body, **style_card())
    right.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=6)
    ctk.CTkLabel(
        right, text="Train lab · local + cloud", font=ctk.CTkFont(size=15, weight="bold"), text_color=_HC_LABEL
    ).pack(anchor="w", padx=12, pady=(12, 4))
    ctk.CTkLabel(
        right,
        text="Export → pick method (local LoRA or OpenAI SFT / distill) → Start. Full hyperparams + logs.",
        text_color=_HC_MUTED,
        wraplength=360,
        justify="left",
    ).pack(anchor="w", padx=12)

    ds_frame = ctk.CTkFrame(right, fg_color="transparent")
    ds_frame.pack(fill="x", padx=10, pady=6)

    def exp_chat() -> None:
        meta = tl.export_chat_dataset()
        app.set_status(f"Dataset {meta.get('id')}: {meta.get('count')} pairs", toast=True)
        refresh_ds()
        refresh_jobs()

    def exp_team() -> None:
        meta = tl.export_team_dataset()
        app.set_status(f"Team dataset {meta.get('id')}: {meta.get('count')} pairs", toast=True)
        refresh_ds()

    ctk.CTkButton(ds_frame, text="Export Chat → dataset", command=exp_chat).pack(side="left", padx=2)
    ctk.CTkButton(ds_frame, text="Export Team → dataset", command=exp_team).pack(side="left", padx=2)

    ds_var = ctk.StringVar(master=right, value="")
    ds_menu = ctk.CTkOptionMenu(right, variable=ds_var, values=["(export first)"], width=320)
    ds_menu.pack(anchor="w", padx=12, pady=4)
    ds_map: dict[str, str] = {}

    def refresh_ds() -> None:
        nonlocal ds_map
        ds_map = {}
        labels = []
        for d in tl.list_datasets():
            lab = f"{d.get('name')} · {d.get('count')} · {d.get('id')}"
            ds_map[lab] = str(d.get("id"))
            labels.append(lab)
        ds_menu.configure(values=labels or ["(export first)"])
        if labels:
            ds_var.set(labels[0])

    # Hyperparams
    hp = ctk.CTkFrame(right, fg_color="transparent")
    hp.pack(fill="x", padx=10, pady=6)
    job_name = ctk.CTkEntry(hp, placeholder_text="Job name")
    job_name.insert(0, "lora-chat-v1")
    job_name.pack(fill="x", pady=2)
    base_m = ctk.CTkEntry(hp, placeholder_text="Base model id / HF name")
    base_m.insert(0, "qwen2.5:7b")
    base_m.pack(fill="x", pady=2)
    row = ctk.CTkFrame(hp, fg_color="transparent")
    row.pack(fill="x", pady=2)
    epochs_e = ctk.CTkEntry(row, width=70, placeholder_text="epochs")
    epochs_e.insert(0, "1")
    epochs_e.pack(side="left", padx=2)
    lr_e = ctk.CTkEntry(row, width=90, placeholder_text="lr")
    lr_e.insert(0, "0.0002")
    lr_e.pack(side="left", padx=2)
    steps_e = ctk.CTkEntry(row, width=70, placeholder_text="steps")
    steps_e.insert(0, "40")
    steps_e.pack(side="left", padx=2)
    r_e = ctk.CTkEntry(row, width=50, placeholder_text="r")
    r_e.insert(0, "8")
    r_e.pack(side="left", padx=2)
    alpha_e = ctk.CTkEntry(row, width=60, placeholder_text="alpha")
    alpha_e.insert(0, "16")
    alpha_e.pack(side="left", padx=2)
    method_var = ctk.StringVar(master=hp, value="lora")
    ctk.CTkOptionMenu(
        hp,
        variable=method_var,
        values=[
            "lora",
            "qlora",
            "full",
            "openai_sft",
            "openai_dpo",
            "distill_then_sft",
        ],
        width=160,
    ).pack(anchor="w", pady=2)
    ctk.CTkLabel(
        hp,
        text="openai_sft needs OpenAI key (not OpenRouter). distill uses teacher then optional SFT.",
        text_color=_HC_MUTED,
        font=ctk.CTkFont(size=10),
        wraplength=340,
        justify="left",
    ).pack(anchor="w", pady=2)
    teacher_e = ctk.CTkEntry(hp, placeholder_text="Teacher model (distill) e.g. openai/gpt-4o-mini")
    teacher_e.insert(0, "openai/gpt-4o-mini")
    teacher_e.pack(fill="x", pady=2)
    openai_base_e = ctk.CTkEntry(hp, placeholder_text="OpenAI FT base e.g. gpt-4o-mini-2024-07-18")
    openai_base_e.insert(0, "gpt-4o-mini-2024-07-18")
    openai_base_e.pack(fill="x", pady=2)
    dry_var = ctk.BooleanVar(master=hp, value=True)
    ctk.CTkSwitch(
        hp,
        text="Dry-run local LoRA only (ignored for OpenAI SFT)",
        variable=dry_var,
    ).pack(anchor="w", pady=2)

    job_log = ctk.CTkTextbox(right, height=140)
    job_log.pack(fill="both", expand=True, padx=10, pady=6)
    job_list = ctk.CTkScrollableFrame(right, height=100, fg_color="transparent")
    job_list.pack(fill="x", padx=8, pady=4)

    def refresh_jobs() -> None:
        for w in job_list.winfo_children():
            w.destroy()
        for j in tl.list_jobs(limit=15):
            lab = f"[{j.get('status')}] {j.get('name')} · {int(float(j.get('progress') or 0)*100)}%"
            ctk.CTkButton(
                job_list,
                text=lab[:70],
                anchor="w",
                fg_color="transparent",
                command=lambda i=j["id"]: show_job(i),
            ).pack(fill="x", pady=1)

    def show_job(jid: str) -> None:
        j = tl.get_job(jid)
        if not j:
            return
        job_log.delete("1.0", "end")
        job_log.insert(
            "1.0",
            f"Job {j.get('name')} [{j.get('status')}]\n"
            f"base={j.get('base_model')} method={j.get('method')}\n"
            f"adapter={j.get('adapter_path')}\n"
            f"error={j.get('error')}\n\n"
            + "\n".join(j.get("logs") or [])
            + "\n\nloss="
            + str((j.get("metrics") or {}).get("loss") or [])[-20:],
        )

    def _poll_job(jid: str) -> None:
        def poll() -> None:
            j = tl.get_job(jid)
            if j:
                show_job(jid)
                refresh_jobs()
                if j.get("status") in ("running", "queued"):
                    try:
                        app.after(1500, poll)
                    except Exception:  # noqa: BLE001
                        pass
                elif j.get("status") == "done":
                    refresh_profiles()
                    app.set_status("Train job done — profile may be registered", toast=True)

        try:
            app.after(800, poll)
        except Exception:  # noqa: BLE001
            pass

    def create_and_start() -> None:
        lab = ds_var.get()
        ds_id = ds_map.get(lab, "")
        method = method_var.get() or "lora"
        if not ds_id and method not in ("distill_then_sft",):
            messagebox.showinfo("Train", "Export a dataset first.", parent=app)
            return
        try:
            epochs = int(epochs_e.get() or "1")
            lr = float(lr_e.get() or "0.0002")
            steps = int(steps_e.get() or "40")
            r = int(r_e.get() or "8")
            alpha = int(alpha_e.get() or "16")
        except ValueError:
            messagebox.showerror("Train", "Invalid hyperparams", parent=app)
            return

        # Cloud OpenAI SFT / DPO
        if method in ("openai_sft", "openai_dpo"):
            from app.core.services.misc.cloud_finetune import start_openai_sft_from_dataset

            job_log.delete("1.0", "end")
            job_log.insert("1.0", "Starting OpenAI fine-tune…\n")

            def work() -> None:
                res = start_openai_sft_from_dataset(
                    ds_id,
                    base_model=openai_base_e.get().strip() or "gpt-4o-mini-2024-07-18",
                    name=job_name.get().strip() or "openai-sft",
                    n_epochs=epochs,
                    method="dpo" if method == "openai_dpo" else "supervised",
                    on_progress=lambda m: None,
                )

                def done() -> None:
                    if not res.get("ok"):
                        messagebox.showerror("OpenAI FT", str(res.get("error") or "failed"), parent=app)
                        return
                    jid = str(res.get("job_id") or "")
                    app.set_status(f"OpenAI FT job {jid[:8]}…", toast=True)
                    refresh_jobs()
                    if jid:
                        show_job(jid)
                        _poll_job(jid)

                try:
                    app.after(0, done)
                except Exception:  # noqa: BLE001
                    pass

            threading.Thread(target=work, daemon=True).start()
            return

        # Distill with teacher (OpenRouter/OpenAI) then optional note for SFT
        if method == "distill_then_sft":
            from app.core.services.misc.cloud_finetune import distill_from_dataset_prompts, distill_with_teacher

            if not ds_id:
                # distill from a few default prompts if no dataset
                prompts = [
                    "Explain what you can do as an AI agent on a Windows PC.",
                    "Write a short project plan for a multi-agent research task.",
                    "How do you use tools safely and effectively?",
                ]
            else:
                prompts = []

            job_log.delete("1.0", "end")
            job_log.insert("1.0", "Distilling with teacher…\n")

            def work() -> None:
                if ds_id:
                    res = distill_from_dataset_prompts(
                        ds_id,
                        teacher_model=teacher_e.get().strip() or "openai/gpt-4o-mini",
                    )
                else:
                    res = distill_with_teacher(
                        prompts,
                        teacher_model=teacher_e.get().strip() or "openai/gpt-4o-mini",
                    )

                def done() -> None:
                    if not res.get("ok"):
                        messagebox.showerror("Distill", str(res.get("error") or "failed"), parent=app)
                        return
                    meta = res.get("dataset") or {}
                    app.set_status(
                        f"Distilled {meta.get('count')} pairs → dataset {meta.get('id')}. "
                        f"Select it and run openai_sft or lora.",
                        toast=True,
                    )
                    refresh_ds()
                    job_log.insert("end", f"\nDataset {meta.get('id')} count={meta.get('count')}\n")

                try:
                    app.after(0, done)
                except Exception:  # noqa: BLE001
                    pass

            threading.Thread(target=work, daemon=True).start()
            return

        job = tl.create_job(
            name=job_name.get().strip() or "train",
            base_model=base_m.get().strip(),
            dataset_id=ds_id,
            method=method,
            epochs=epochs,
            lr=lr,
            lora_r=r,
            lora_alpha=alpha,
            max_steps=steps,
            dry_run=bool(dry_var.get()),
        )
        tl.start_job(str(job["id"]))
        app.set_status(f"Train job started: {job.get('name')}", toast=True)
        refresh_jobs()
        show_job(str(job["id"]))
        _poll_job(str(job["id"]))

    def stop() -> None:
        tl.stop_job()
        try:
            from app.core.services.misc.cloud_finetune import cancel_openai_ft_job, list_openai_ft_jobs

            # best-effort: cancel latest running cloud job if any local job has cloud_job_id
            for j in tl.list_jobs(limit=10):
                cid = j.get("cloud_job_id")
                if cid and j.get("status") == "running":
                    cancel_openai_ft_job(str(cid))
        except Exception:  # noqa: BLE001
            pass
        app.set_status("Stop signal sent to train job")

    def run_ab() -> None:
        """A/B eval first two profiles."""
        from app.core.services.misc.cloud_finetune import ab_eval_profiles

        profs = mp.list_profiles()
        if len(profs) < 2:
            messagebox.showinfo("A/B", "Need at least 2 model profiles.", parent=app)
            return
        prompts = [
            "Say hello in one sentence.",
            "What tools can you use on a Windows PC?",
        ]
        job_log.delete("1.0", "end")
        job_log.insert("1.0", "Running A/B eval…\n")

        def work() -> None:
            res = ab_eval_profiles(str(profs[0]["id"]), str(profs[1]["id"]), prompts)

            def done() -> None:
                if not res.get("ok"):
                    job_log.insert("end", str(res.get("error")))
                    return
                job_log.insert("end", f"A={res.get('profile_a')} vs B={res.get('profile_b')}\n\n")
                for row in res.get("rows") or []:
                    job_log.insert(
                        "end",
                        f"Q: {row.get('prompt')}\n"
                        f"A: {row.get('a') or row.get('error_a')}\n"
                        f"B: {row.get('b') or row.get('error_b')}\n\n",
                    )

            try:
                app.after(0, done)
            except Exception:  # noqa: BLE001
                pass

        threading.Thread(target=work, daemon=True).start()

    def list_cloud_jobs() -> None:
        from app.core.services.misc.cloud_finetune import list_openai_ft_jobs

        job_log.delete("1.0", "end")
        job_log.insert("1.0", "Listing OpenAI fine-tune jobs…\n")

        def work() -> None:
            res = list_openai_ft_jobs(limit=15)

            def done() -> None:
                if not res.get("ok"):
                    job_log.insert("end", f"Error: {res.get('error')}\n(Use OpenAI key in Settings, not only OpenRouter.)\n")
                    return
                for j in res.get("jobs") or []:
                    job_log.insert(
                        "end",
                        f"{j.get('id')}  status={j.get('status')}  "
                        f"model={j.get('fine_tuned_model') or j.get('model')}\n",
                    )

            try:
                app.after(0, done)
            except Exception:  # noqa: BLE001
                pass

        threading.Thread(target=work, daemon=True).start()

    jbtn = ctk.CTkFrame(right, fg_color="transparent")
    jbtn.pack(fill="x", padx=10, pady=(0, 12))
    ctk.CTkButton(
        jbtn, text="▶ Start job", command=create_and_start, **style_chrome_button(primary=True)
    ).pack(side="left", padx=2)
    ctk.CTkButton(jbtn, text="■ Stop", width=60, command=stop, fg_color="#a33").pack(side="left", padx=2)
    ctk.CTkButton(jbtn, text="A/B test", width=70, command=run_ab).pack(side="left", padx=2)
    ctk.CTkButton(jbtn, text="Cloud jobs", width=80, command=list_cloud_jobs).pack(side="left", padx=2)

    refresh_profiles()
    refresh_ollama()
    refresh_ds()
    refresh_jobs()
