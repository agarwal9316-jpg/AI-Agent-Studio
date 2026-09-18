"""Chat cycle bar — extracted from AppWindow."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import customtkinter as ctk

from app.services import storage

if TYPE_CHECKING:
    from app.ui.app_window import AppWindow


def build_chat_cycle_bar(app, root: Any) -> None:
    """Always-visible Task / LLM status plus Run cycle / Stop cycle."""
    from app.ui.themes import UI as _UI, style_chrome_button

    bar = ctk.CTkFrame(
        root,
        height=40,
        corner_radius=0,
        fg_color=_UI.get("top_bg", _UI["chat_bg"]),
        border_width=1,
        border_color=_UI.get("top_border", ("#e5e5e5", "#2a2a2a")),
    )
    bar.grid(row=1, column=0, columnspan=2, sticky="ew")
    bar.grid_propagate(False)
    app._chat_cycle_bar = bar
    app._cycle_run_btn = ctk.CTkButton(
        bar,
        text="▶ Run cycle",
        width=108,
        height=28,
        corner_radius=8,
        command=app._start_task_cycle,
        **style_chrome_button(primary=True),
    )
    app._cycle_run_btn.pack(side="left", padx=(8, 3), pady=5)
    app._tooltip(
        app._cycle_run_btn,
        "Start the cycle: if the task is still open and the model goes idle, send Continue",
    )
    app._cycle_stop_btn = ctk.CTkButton(
        bar,
        text="■ Stop cycle",
        width=110,
        height=28,
        corner_radius=8,
        command=app._stop_task_cycle,
        fg_color=("#d1d5db", "#3f3f46"),
        hover_color=("#9ca3af", "#27272a"),
        text_color=("#52525b", "#a1a1aa"),
        state="disabled",
    )
    app._cycle_stop_btn.pack(side="left", padx=3, pady=5)
    app._tooltip(app._cycle_stop_btn, "Stop the watch cycle and the current model turn")
    app._task_status_btn = ctk.CTkButton(
        bar,
        text="Task · none",
        width=148,
        height=28,
        corner_radius=8,
        command=app._toggle_task_achieved,
        **style_chrome_button(primary=True),
    )
    app._task_status_btn.pack(side="left", padx=(14, 3), pady=5)
    app._tooltip(
        app._task_status_btn,
        "Task open or achieved. Click to mark done / reopen.",
    )
    app._llm_status_lbl = ctk.CTkLabel(
        bar,
        text="LLM · idle",
        width=128,
        height=28,
        corner_radius=8,
        fg_color=("#e5e7eb", "#27272a"),
        text_color=_UI.get("label", ("#111", "#eee")),
        font=ctk.CTkFont(size=12, weight="bold"),
    )
    app._llm_status_lbl.pack(side="left", padx=3, pady=5)
    app._tooltip(app._llm_status_lbl, "Current model state: working, idle, paused, or error")
    app._from_start_btn = ctk.CTkButton(
        bar,
        text="From start",
        width=96,
        height=28,
        corner_radius=8,
        command=app._chat_show_from_start,
        **style_chrome_button(),
    )
    app._from_start_btn.pack(side="left", padx=(14, 3), pady=5)
    app._tooltip(app._from_start_btn, "Scroll the whole chat from the first message")
    app._ctx_open_btn = ctk.CTkButton(
        bar,
        text="Context",
        width=86,
        height=28,
        corner_radius=8,
        command=app._chat_context_window_dialog,
        **style_chrome_button(primary=True),
    )
    app._ctx_open_btn.pack(side="left", padx=(10, 3), pady=5)
    app._tooltip(
        app._ctx_open_btn,
        "Context window size and the exact prompt text the model will see — both editable",
    )
    app._ctx_chip_lbl = ctk.CTkLabel(
        bar,
        text="ctx …",
        width=150,
        height=28,
        anchor="w",
        font=ctk.CTkFont(size=12),
        text_color=_UI.get("muted", ("#6b7280", "#9ca3af")),
    )
    app._ctx_chip_lbl.pack(side="left", padx=4, pady=5)
    try:
        app._refresh_context_chip()
    except Exception:  # noqa: BLE001
        pass
    try:
        app._refresh_task_llm_chips()
    except Exception:  # noqa: BLE001
        pass


def refresh_task_llm_chips(app) -> None:
    from app.core.services.chat.task_watch import (
        LLM_ERROR,
        LLM_IDLE,
        LLM_PAUSED,
        LLM_WORKING,
        TASK_ACHIEVED,
        TASK_BLOCKED,
        TASK_NONE,
        TASK_OPEN,
        infer_llm_status,
        infer_task_status,
        llm_chip_label,
        task_chip_label,
    )

    last_err = False
    try:
        msgs = list((app._chat_state or {}).get("messages") or [])
        if msgs and (msgs[-1].get("role") or "") == "error":
            last_err = True
    except Exception:  # noqa: BLE001
        msgs = []
    task = infer_task_status(
        msgs,
        user_pin=app._task_user_pin(),
        auto_count=int(getattr(app, "_auto_continue_count", 0) or 0),
    )
    llm = infer_llm_status(
        busy=bool(getattr(app, "_chat_busy", False)),
        paused=bool(getattr(app, "_chat_paused", False)),
        last_error=last_err,
    )
    app._task_status = task
    app._llm_phase = llm
    task_colors = {
        TASK_OPEN: (("#fff7ed", "#7c2d12"), ("#9a3412", "#fdba74")),
        TASK_ACHIEVED: (("#d1fae5", "#064e3b"), ("#065f46", "#6ee7b7")),
        TASK_BLOCKED: (("#fee2e2", "#7f1d1d"), ("#991b1b", "#fecaca")),
        TASK_NONE: (("#f3f4f6", "#27272a"), ("#52525b", "#a1a1aa")),
    }
    llm_colors = {
        LLM_WORKING: ("#dbeafe", "#1e3a8a"),
        LLM_PAUSED: ("#fef3c7", "#78350f"),
        LLM_ERROR: ("#fee2e2", "#7f1d1d"),
        LLM_IDLE: ("#e5e7eb", "#27272a"),
    }
    try:
        btn = getattr(app, "_task_status_btn", None)
        if btn is not None and btn.winfo_exists():
            bg, fg = task_colors.get(task, task_colors[TASK_NONE])
            btn.configure(text=task_chip_label(task), fg_color=bg, text_color=fg)
    except Exception:  # noqa: BLE001
        pass
    try:
        lbl = getattr(app, "_llm_status_lbl", None)
        if lbl is not None and lbl.winfo_exists():
            lbl.configure(
                text=llm_chip_label(llm),
                fg_color=llm_colors.get(llm, llm_colors[LLM_IDLE]),
            )
    except Exception:  # noqa: BLE001
        pass
    app._refresh_cycle_buttons()
    try:
        app._refresh_goal_banner()
    except Exception:  # noqa: BLE001
        pass


def update_composer_status(app) -> None:
    if not hasattr(app, "chat_attach_label"):
        return
    model = ""
    try:
        model = app.chat_model_var.get() if hasattr(app, "chat_model_var") else ""
    except Exception:  # noqa: BLE001
        model = storage.load_config().get("model") or ""
    if model and len(model) > 36:
        model = "…" + model[-34:]
    mode = app.chat_mode_var.get() if hasattr(app, "chat_mode_var") else "action"
    att = app._attachments_summary_short()
    try:
        from app.core.services.llm.providers import has_active_api_key

        key_ok = has_active_api_key()
    except Exception:  # noqa: BLE001
        key_ok = bool((storage.load_config().get("api_key") or "").strip())
    ready = "Ready" if key_ok else "No API key → Settings"
    budget_part = ""
    try:
        from app.core.services.llm.providers import estimate_request_budget

        prompt_chars = 0
        try:
            if hasattr(app, "chat_input") and not getattr(app, "_composer_is_placeholder", False):
                prompt_chars = len(app.chat_input.get("1.0", "end-1c") or "")
        except Exception:  # noqa: BLE001
            prompt_chars = 0
        bud = estimate_request_budget(prompt_chars=prompt_chars)
        max_out = bud.get("max_completion_tokens") or 0
        ptok = bud.get("prompt_tokens_est") or 0
        budget_part = f"  ·  ~{ptok}+{max_out} tok"
        note = str(bud.get("note") or "")
        if "OpenRouter" in note and ptok + max_out > 400:
            budget_part += " ⚠credits"
    except Exception:  # noqa: BLE001
        budget_part = ""
    risk_part = ""
    try:
        from app.services.agent_harness.permissions import risk_tier_badge

        risk_part = f"  ·  {risk_tier_badge()}"
        if hasattr(app, "_risk_chip_btn"):
            try:
                app._risk_chip_btn.configure(text=risk_tier_badge())
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        risk_part = ""
    folder_part = ""
    try:
        from pathlib import Path as _P

        kf = ""
        if getattr(app, "_chat_state", None):
            kf = str(
                app._chat_state.get("knowledge_folder")
                or app._chat_state.get("chat_folder")
                or ""
            )
        if kf:
            folder_part = f"  ·  📁 {_P(kf).name}"
    except Exception:  # noqa: BLE001
        folder_part = ""
    att_part = f"  ·  {att}" if att and att != "no attaches" else ""
    try:
        from app.core.services.chat.task_watch import llm_chip_label, task_chip_label

        cycle = "Cycle · on" if getattr(app, "_task_cycle_running", False) else "Cycle · off"
        watch = (
            f"{cycle}  ·  {task_chip_label(getattr(app, '_task_status', 'none'))}  ·  "
            f"{llm_chip_label(getattr(app, '_llm_phase', 'idle'))}  ·  "
        )
    except Exception:  # noqa: BLE001
        watch = ""
    line = f"{watch}{ready}  ·  {model}  ·  {mode}{budget_part}{risk_part}{folder_part}{att_part}"
    try:
        app.chat_attach_label.configure(text=line)
    except Exception:  # noqa: BLE001
        pass
