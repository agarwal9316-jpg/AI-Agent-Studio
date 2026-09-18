"""Usage page — extracted from AppWindow."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import customtkinter as ctk
import tkinter.messagebox as messagebox

if TYPE_CHECKING:
    from app.ui.app_window import AppWindow


def page_usage(app) -> None:
    from app.ui.themes import UI as _UI
    _HC_MUTED = _UI["muted"]
    _HC_LABEL = _UI.get("label", _UI["muted"])
    from app.core.services.data.usage_meter import get_summary, reset_usage, format_status_line
    from app.core.services.tools.tool_budget import (
        get_budgets,
        set_budgets,
        DEFAULT_BUDGETS,
        get_parallel_caps,
        set_parallel_caps,
    )

    root = ctk.CTkFrame(app.content, fg_color="transparent")
    root.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
    root.grid_columnconfigure(0, weight=1)
    root.grid_rowconfigure(1, weight=1)

    app._page_header(
        root,
        "Usage & budgets",
        format_status_line() + "  ·  Estimates only (varies by provider pricing)",
        actions=[("Refresh", lambda: app.show_page("Usage"))],
    )

    body = ctk.CTkScrollableFrame(root)
    body.grid(row=1, column=0, sticky="nsew")

    s = get_summary()
    totals = s.get("totals") or {}
    box = ctk.CTkTextbox(body, height=220)
    box.pack(fill="x", padx=4, pady=4)
    lines = [
        "=== TOTALS ===",
        f"Prompt tokens:     {int(totals.get('prompt_tokens') or 0):,}",
        f"Completion tokens: {int(totals.get('completion_tokens') or 0):,}",
        f"Total tokens:      {int(totals.get('total_tokens') or 0):,}",
        f"Est. cost USD:     ${float(totals.get('est_cost_usd') or 0):.4f}",
        "",
        "=== BY MODEL ===",
    ]
    for k, v in sorted((s.get("by_model") or {}).items(), key=lambda x: -float(x[1].get("est_cost_usd") or 0)):
        lines.append(
            f"  {k}: {int(v.get('total_tokens') or 0):,} tok · ${float(v.get('est_cost_usd') or 0):.4f}"
        )
    lines.append("")
    lines.append("=== BY AGENT ===")
    for k, v in sorted((s.get("by_agent") or {}).items(), key=lambda x: -int(x[1].get("total_tokens") or 0)):
        lines.append(
            f"  {k}: {int(v.get('total_tokens') or 0):,} tok · ${float(v.get('est_cost_usd') or 0):.4f}"
        )
    lines.append("")
    lines.append("=== RECENT EVENTS ===")
    for e in (s.get("events") or [])[:25]:
        lines.append(
            f"  {e.get('at','')[:19]}  {e.get('agent')}  {e.get('model')}  "
            f"+{e.get('total_tokens')} tok  ${float(e.get('est_cost_usd') or 0):.5f}"
        )
    box.insert("1.0", "\n".join(lines))
    box.configure(state="disabled")

    ctk.CTkLabel(body, text="Tool budgets (max calls per run)", font=ctk.CTkFont(weight="bold")).pack(
        anchor="w", padx=4, pady=(12, 4)
    )
    budgets = get_budgets()
    entries: dict[str, ctk.CTkEntry] = {}
    grid = ctk.CTkFrame(body)
    grid.pack(fill="x", padx=4, pady=4)
    for i, (k, v) in enumerate(sorted(budgets.items())):
        ctk.CTkLabel(grid, text=k, width=100, anchor="w").grid(row=i // 3, column=(i % 3) * 2, padx=4, pady=2)
        e = ctk.CTkEntry(grid, width=60)
        e.insert(0, str(v))
        e.grid(row=i // 3, column=(i % 3) * 2 + 1, padx=4, pady=2)
        entries[k] = e

    ctk.CTkLabel(
        body,
        text="Parallel agents (caps)",
        font=ctk.CTkFont(weight="bold"),
    ).pack(anchor="w", padx=4, pady=(16, 4))
    ctk.CTkLabel(
        body,
        text="Limits concurrent subagents and wall-clock time. Use PARALLEL_AGENTS harness block.",
        text_color=_HC_MUTED,
    ).pack(anchor="w", padx=4)
    pcaps = get_parallel_caps()
    p_entries: dict[str, ctk.CTkEntry] = {}
    pgrid = ctk.CTkFrame(body)
    pgrid.pack(fill="x", padx=4, pady=4)
    p_labels = {
        "max_concurrent_subagents": "Max concurrent",
        "max_subagents_per_run": "Max per parent run",
        "max_parallel_batch": "Max batch size",
        "subagent_timeout_sec": "Subagent timeout (s)",
        "parallel_timeout_sec": "Batch timeout (s)",
    }
    for i, (k, lab) in enumerate(p_labels.items()):
        ctk.CTkLabel(pgrid, text=lab, width=160, anchor="w").grid(
            row=i // 2, column=(i % 2) * 2, padx=4, pady=3, sticky="w"
        )
        e = ctk.CTkEntry(pgrid, width=80)
        e.insert(0, str(int(pcaps.get(k) or 0)))
        e.grid(row=i // 2, column=(i % 2) * 2 + 1, padx=4, pady=3)
        p_entries[k] = e

    def save_b() -> None:
        new_b = {}
        for k, e in entries.items():
            try:
                new_b[k] = int(e.get().strip() or DEFAULT_BUDGETS.get(k, 10))
            except ValueError:
                new_b[k] = DEFAULT_BUDGETS.get(k, 10)
        set_budgets(new_b)
        new_p = {}
        for k, e in p_entries.items():
            try:
                new_p[k] = float(e.get().strip()) if "timeout" in k else int(e.get().strip())
            except ValueError:
                new_p[k] = pcaps.get(k)
        set_parallel_caps(new_p)
        app.set_status("Budgets + parallel caps saved", toast=True)
        messagebox.showinfo(
            "Budgets",
            "Saved tool budgets and parallel agent caps for future runs.",
            parent=app,
        )

    bar = ctk.CTkFrame(body, fg_color="transparent")
    bar.pack(fill="x", pady=8)
    ctk.CTkButton(bar, text="Save budgets", command=save_b).pack(side="left", padx=4)
    ctk.CTkButton(
        bar,
        text="Reset usage counters",
        fg_color="#a33",
        command=lambda: (reset_usage(), app.show_page("Usage")),
    ).pack(side="left", padx=4)
    ctk.CTkButton(bar, text="Refresh", command=lambda: app.show_page("Usage")).pack(
        side="left", padx=4
    )
