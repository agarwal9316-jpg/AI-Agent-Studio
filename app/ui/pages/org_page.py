"""Organisation structure page — visual company tree + worker configuration.

- Visual org chart (CEO → branches → workers) like a classic company diagram
- Fast selection (no full rebuild / flicker on click)
- Every worker has ▾ menu with full feature set from Company Structure upgrade
"""

from __future__ import annotations

import tkinter.messagebox as messagebox
from pathlib import Path
from typing import TYPE_CHECKING, Any

import customtkinter as ctk

from app.ui.themes import UI as _THEME_UI, style_chrome_button

_HC_MUTED = _THEME_UI["muted"]
_HC_LABEL = _THEME_UI["label"]

from app.services import storage as agent_storage
from app.services import workflow_graph as wfg
from app.ui.pages.org_chart_view import OrgChartPanel
from app.ui.pages.org_worker_dialogs import (
    confirm_remove_worker,
    open_move_worker,
    open_worker_config,
    open_worker_inspector,
)

if TYPE_CHECKING:
    from app.ui.app_window import AppWindow


def page_workflow(app: AppWindow) -> None:
    """Visual AI Organisation chart with + and full worker menus."""
    root = ctk.CTkFrame(app.content, fg_color="transparent")
    root.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
    # Chart (wide) | details (narrow)
    root.grid_columnconfigure(0, weight=3, minsize=420)
    root.grid_columnconfigure(1, weight=2, minsize=280)
    root.grid_rowconfigure(2, weight=1)

    ctk.CTkLabel(
        root,
        text="AI Organisation",
        font=ctk.CTkFont(size=22, weight="bold"),
        text_color=_HC_LABEL,
    ).grid(row=0, column=0, columnspan=2, sticky="w")
    ctk.CTkLabel(
        root,
        text=(
            "Right panel: All organisations (Test SWAT, Beta Org, …) — open / rename / delete with ☑. "
            "Workers in this org — tree with + / ☑. Click cards on the left or rows on the right."
        ),
        text_color=_HC_MUTED,
        wraplength=960,
        justify="left",
    ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 6))

    state: dict[str, Any] = {
        "graph": wfg.get_active_graph(),
        "selected_id": None,
        "gmap": {},
        "checked_ids": set(),  # worker multi-select (active chart)
        "chart_checked_ids": set(),  # organisation-chart multi-select
        "panel_expanded": True,
        "sec_charts": True,  # list of all created orgs
        "sec_list": True,
        "sec_details": True,
        "sec_preview": False,
        "check_vars": {},  # worker id -> BooleanVar
        "chart_check_vars": {},  # graph id -> BooleanVar
        "list_rows": {},  # worker id -> row frame (soft highlight)
        "list_name_btns": {},  # worker id -> name button
        "chart_rows": {},  # graph id -> row frame
    }

    # ========== LEFT: toolbar + visual chart ==========
    left = ctk.CTkFrame(root)
    left.grid(row=2, column=0, sticky="nsew", padx=(0, 8))
    left.grid_rowconfigure(2, weight=1)
    left.grid_columnconfigure(0, weight=1)

    top = ctk.CTkFrame(left, fg_color="transparent")
    top.grid(row=0, column=0, sticky="ew", padx=8, pady=6)
    gvar = ctk.StringVar(master=top, value=state["graph"].get("name") or "Company organisation")
    chart_menu = ctk.CTkOptionMenu(top, values=["Company organisation"], variable=gvar, width=180)
    chart_menu.pack(side="left", padx=2)

    def rebuild_chart_menu() -> None:
        graphs = wfg.list_graphs()
        gmap2: dict[str, str] = {}
        seen: dict[str, int] = {}
        for g in graphs:
            base = str(g.get("name") or g["id"][:8])
            n = seen.get(base, 0)
            seen[base] = n + 1
            label = base if n == 0 else f"{base} ({n + 1})"
            gmap2[label] = str(g["id"])
        state["gmap"] = gmap2
        names = list(gmap2.keys()) or ["Company organisation"]
        chart_menu.configure(values=names)
        active = wfg.get_active_graph()
        label = next(
            (lab for lab, gid in gmap2.items() if gid == active.get("id")),
            names[0],
        )
        gvar.set(label)
        # Keep right-panel "All organisations" list in sync when defined
        try:
            refresh_charts_list()  # type: ignore[name-defined]
        except Exception:  # noqa: BLE001
            pass

    def on_switch(name: str) -> None:
        gid = state["gmap"].get(name)
        if not gid:
            return
        wfg.set_active_graph(gid)
        state["graph"] = wfg.get_active_graph()
        state["selected_id"] = None
        refresh_structure()

    chart_menu.configure(command=on_switch)

    def new_org() -> None:
        wfg.new_graph("New organisation")
        rebuild_chart_menu()
        state["graph"] = wfg.get_active_graph()
        state["selected_id"] = None
        refresh_structure()
        app.set_status("New empty organisation created", toast=True)

    def rename_org() -> None:
        g = state["graph"]
        win = ctk.CTkToplevel(app)
        win.title("Rename organisation")
        win.geometry("420x140")
        win.transient(app)
        e = ctk.CTkEntry(win, placeholder_text="Chart name")
        e.pack(fill="x", padx=16, pady=16)
        e.insert(0, g.get("name") or "")

        def ok() -> None:
            wfg.rename_graph(str(g.get("id")), e.get().strip())
            rebuild_chart_menu()
            state["graph"] = wfg.get_active_graph()
            win.destroy()
            app.set_status("Organisation renamed", toast=True)

        ctk.CTkButton(win, text="Save name", command=ok, **style_chrome_button(primary=True)).pack(
            pady=8
        )

    def duplicate_org() -> None:
        g = state["graph"]
        ng = wfg.duplicate_graph(str(g.get("id")))
        if not ng:
            messagebox.showerror("Duplicate", "Could not duplicate.", parent=app)
            return
        wfg.set_active_graph(ng["id"])
        rebuild_chart_menu()
        state["graph"] = wfg.get_active_graph()
        state["selected_id"] = None
        refresh_structure()
        app.set_status(f"Duplicated: {ng.get('name')}", toast=True)

    def delete_org() -> None:
        g = state["graph"]
        if len(wfg.list_graphs()) <= 1:
            messagebox.showinfo("Delete", "Keep at least one organisation chart.", parent=app)
            return
        if not messagebox.askyesno(
            "Delete organisation",
            f"Delete chart “{g.get('name')}”? This cannot be undone.",
            parent=app,
        ):
            return
        if not wfg.delete_graph(str(g.get("id"))):
            messagebox.showerror("Delete", "Could not delete chart.", parent=app)
            return
        rebuild_chart_menu()
        state["graph"] = wfg.get_active_graph()
        state["selected_id"] = None
        refresh_structure()
        app.set_status("Organisation deleted", toast=True)

    def ai_create_org() -> None:
        """Ask what kind of org tree the user wants; LLM builds tree + worker prompts."""
        from app.services import providers as prov
        from app.services import storage as st

        win = ctk.CTkToplevel(app)
        win.title("✨ Design organisation with AI")
        win.geometry("580x760")
        win.transient(app)
        try:
            win.grab_set()
        except Exception:  # noqa: BLE001
            pass

        # Footer first (always visible status/buttons), then scroll body
        foot_holder = ctk.CTkFrame(
            win,
            fg_color=_THEME_UI.get("top_bg", ("#f3f4f6", "#161a22")),
            corner_radius=0,
        )
        foot_holder.pack(side="bottom", fill="x")
        body = ctk.CTkScrollableFrame(win, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=4, pady=4)

        ctk.CTkLabel(
            body,
            text="What organisation tree do you want?",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=_HC_LABEL,
        ).pack(anchor="w", padx=12, pady=(10, 2))
        ctk.CTkLabel(
            body,
            text=(
                "Describe the kind of company / team and your structure requirements. "
                "AI builds CEO → managers → workers and fills each seat with system + worker prompts."
            ),
            text_color=_HC_MUTED,
            wraplength=520,
            justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 8))

        # ---- LLM for this design call (Default = global Settings) ----
        active = {}
        try:
            active = prov.resolve_active_llm() or {}
        except Exception:  # noqa: BLE001
            active = {}
        def_name = str(active.get("provider_name") or active.get("provider_id") or "Settings")
        def_model = str(active.get("model") or "")
        def_base = str(active.get("base_url") or "")
        def_key = str(active.get("api_key") or "")
        try:
            key_mask = st.mask_api_key(def_key) if def_key else "(none in Settings)"
        except Exception:  # noqa: BLE001
            key_mask = "(set in Settings)" if not def_key else "••••"

        llm_box = ctk.CTkFrame(
            body,
            fg_color=_THEME_UI.get("top_bg", ("#f3f4f6", "#161a22")),
            corner_radius=10,
        )
        llm_box.pack(fill="x", padx=12, pady=(4, 10))
        # Saved LLM prefs for AI create (so user does not re-enter every time)
        saved_llm: dict[str, Any] = {}
        try:
            cfg0 = st.load_config()
            raw_pref = cfg0.get("org_ai_llm")
            if isinstance(raw_pref, dict):
                saved_llm = dict(raw_pref)
        except Exception:  # noqa: BLE001
            saved_llm = {}

        ctk.CTkLabel(
            llm_box,
            text="LLM for design (saved for next time)",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=_HC_LABEL,
        ).pack(anchor="w", padx=12, pady=(10, 2))
        ctk.CTkLabel(
            llm_box,
            text=(
                f"Global Settings fallback: {def_name} · {def_model or '(no model)'} · "
                f"{def_base or '(no base URL)'} · key {key_mask}\n"
                "Click “Save LLM settings” after choosing provider / URL / key / model."
            ),
            text_color=_HC_MUTED,
            font=ctk.CTkFont(size=11),
            wraplength=500,
            justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 6))

        providers = prov.list_providers()
        # label -> provider id; empty id means Default / global
        prov_choices: list[tuple[str, str]] = [
            ("Default — use global Settings", ""),
        ]
        for p in providers:
            lab = str(p.get("name") or p.get("id") or "Provider")
            pid = str(p.get("id") or "")
            prov_choices.append((f"{lab}", pid))
        prov_labels = [c[0] for c in prov_choices]
        # Restore saved provider if present
        saved_pid = str(saved_llm.get("provider_id") or "")
        initial_prov = prov_labels[0]
        for lab, pid in prov_choices:
            if pid and pid == saved_pid:
                initial_prov = lab
                break
        prov_var = ctk.StringVar(master=llm_box, value=initial_prov)

        ctk.CTkLabel(llm_box, text="Provider", text_color=_HC_MUTED, font=ctk.CTkFont(size=11)).pack(
            anchor="w", padx=12
        )
        prov_menu = ctk.CTkOptionMenu(llm_box, values=prov_labels, variable=prov_var, width=400)
        prov_menu.pack(fill="x", padx=12, pady=3)

        ctk.CTkLabel(llm_box, text="Base URL", text_color=_HC_MUTED, font=ctk.CTkFont(size=11)).pack(
            anchor="w", padx=12, pady=(6, 0)
        )
        base_e = ctk.CTkEntry(
            llm_box,
            placeholder_text=f"Empty = Default ({def_base or 'from Settings'})",
        )
        base_e.pack(fill="x", padx=12, pady=3)

        ctk.CTkLabel(llm_box, text="API key", text_color=_HC_MUTED, font=ctk.CTkFont(size=11)).pack(
            anchor="w", padx=12, pady=(6, 0)
        )
        key_e = ctk.CTkEntry(
            llm_box,
            placeholder_text=f"Empty = Default key {key_mask}",
            show="*",
        )
        key_e.pack(fill="x", padx=12, pady=3)

        ctk.CTkLabel(llm_box, text="Model", text_color=_HC_MUTED, font=ctk.CTkFont(size=11)).pack(
            anchor="w", padx=12, pady=(6, 0)
        )
        model_row = ctk.CTkFrame(llm_box, fg_color="transparent")
        model_row.pack(fill="x", padx=12, pady=3)
        model_e = ctk.CTkEntry(
            model_row,
            placeholder_text=f"Empty = Default ({def_model or 'from Settings'})",
        )
        model_e.pack(side="left", fill="x", expand=True, padx=(0, 4))
        model_pick_var = ctk.StringVar(master=model_row, value="(pick from list)")
        model_pick = ctk.CTkOptionMenu(
            model_row,
            variable=model_pick_var,
            values=["(pick from list)"],
            width=160,
        )
        model_pick.pack(side="left", padx=2)

        models_state: dict[str, list[str]] = {"all": []}

        def _pid_from_label() -> str:
            lab = prov_var.get()
            for label, pid in prov_choices:
                if label == lab:
                    return pid
            return ""

        def _fill_models_for_provider(pid: str) -> None:
            models: list[str] = []
            if not pid:
                try:
                    ap = prov.get_provider(str(active.get("provider_id") or "")) or {}
                    models = list(ap.get("models_cache") or [])
                except Exception:  # noqa: BLE001
                    models = []
                if def_model and def_model not in models:
                    models = [def_model] + models
            else:
                p = prov.get_provider(pid) or {}
                models = list(p.get("models_cache") or [])
            models_state["all"] = models[:120]
            vals = models_state["all"] or ["(type model id above)"]
            try:
                model_pick.configure(values=vals)
                cur_m = model_e.get().strip()
                if cur_m and cur_m in vals:
                    model_pick_var.set(cur_m)
                else:
                    model_pick_var.set(vals[0])
            except Exception:  # noqa: BLE001
                pass

        def _on_pick_model(m: str) -> None:
            if not m or m.startswith("("):
                return
            model_e.delete(0, "end")
            model_e.insert(0, m)

        model_pick.configure(command=_on_pick_model)

        def _apply_provider_defaults(*_a: Any) -> None:
            """When provider changes: fill base URL from provider; clear overrides for Default."""
            pid = _pid_from_label()
            base_e.delete(0, "end")
            key_e.delete(0, "end")
            model_e.delete(0, "end")
            if not pid:
                _fill_models_for_provider("")
                return
            p = prov.get_provider(pid) or {}
            bu = str(p.get("base_url") or "").rstrip("/")
            if bu:
                base_e.insert(0, bu)
            cache = list(p.get("models_cache") or [])
            if cache:
                model_e.insert(0, str(cache[0]))
            _fill_models_for_provider(pid)

        prov_menu.configure(command=lambda _x: _apply_provider_defaults())

        llm_status = ctk.CTkLabel(
            llm_box, text="", text_color=_HC_MUTED, font=ctk.CTkFont(size=11), wraplength=500
        )
        llm_status.pack(anchor="w", padx=12, pady=(0, 2))

        def _refresh_models() -> None:
            pid = _pid_from_label() or str(active.get("provider_id") or "")
            if not pid:
                llm_status.configure(
                    text="No provider id — pick a provider or set Default in Settings.",
                    text_color="tomato",
                )
                return
            try:
                models = prov.fetch_models(pid, force=True)
                llm_status.configure(
                    text=f"Loaded {len(models)} model(s) for this provider.",
                    text_color=_HC_MUTED,
                )
            except Exception as e:  # noqa: BLE001
                llm_status.configure(text=f"Model refresh: {e}", text_color="tomato")
            _fill_models_for_provider(_pid_from_label())

        def _save_llm_settings() -> None:
            """Persist provider/base/key/model for AI create (config.org_ai_llm)."""
            pid = _pid_from_label()
            base = base_e.get().strip()
            key = key_e.get().strip()
            model = model_e.get().strip()
            try:
                cfg = st.load_config()
                prev = cfg.get("org_ai_llm") if isinstance(cfg.get("org_ai_llm"), dict) else {}
                # Keep previous key if field left blank (so “empty = use saved/default” works)
                if not key and prev.get("api_key"):
                    key = str(prev.get("api_key") or "")
                cfg["org_ai_llm"] = {
                    "provider_id": pid,
                    "provider_label": prov_var.get(),
                    "base_url": base,
                    "api_key": key,
                    "model": model,
                }
                st.save_config(cfg)
                try:
                    app.cfg = cfg
                except Exception:  # noqa: BLE001
                    pass
                masked = ""
                try:
                    masked = st.mask_api_key(key) if key else "(none — will use Default)"
                except Exception:  # noqa: BLE001
                    masked = "saved" if key else "none"
                llm_status.configure(
                    text=f"✓ LLM settings saved · {prov_var.get()} · {model or '(default model)'} · key {masked}",
                    text_color=_THEME_UI.get("success", _HC_LABEL),
                )
                try:
                    app.set_status("Org AI LLM settings saved", toast=True)
                except Exception:  # noqa: BLE001
                    pass
            except Exception as e:  # noqa: BLE001
                llm_status.configure(text=f"Save failed: {e}", text_color="tomato")

        llm_btn_row = ctk.CTkFrame(llm_box, fg_color="transparent")
        llm_btn_row.pack(fill="x", padx=12, pady=(4, 10))
        ctk.CTkButton(
            llm_btn_row,
            text="💾 Save LLM settings",
            width=150,
            height=30,
            command=_save_llm_settings,
            **style_chrome_button(primary=True),
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            llm_btn_row,
            text="↻ Refresh models",
            width=130,
            height=30,
            command=_refresh_models,
            **style_chrome_button(),
        ).pack(side="left", padx=2)

        # Prefill from saved prefs (or leave empty for Default)
        if saved_llm:
            if saved_llm.get("base_url"):
                base_e.insert(0, str(saved_llm.get("base_url") or ""))
            # Do not put full key into UI unless user saved one — still allow blank = use saved at call time
            if saved_llm.get("api_key"):
                # Leave empty for security; mark that a key is stored
                key_e.configure(
                    placeholder_text=f"Saved key {st.mask_api_key(str(saved_llm.get('api_key')))} — type to replace"
                )
            if saved_llm.get("model"):
                model_e.insert(0, str(saved_llm.get("model") or ""))
            _fill_models_for_provider(saved_pid)
            llm_status.configure(
                text="Loaded saved LLM settings for AI create.",
                text_color=_HC_MUTED,
            )
        else:
            _fill_models_for_provider("")

        def _resolve_llm_kwargs() -> dict[str, str]:
            """
            Empty fields = Default global Settings, then saved org_ai_llm.
            Provider selected + empty key = first key on that provider or saved key.
            """
            pid = _pid_from_label()
            base = base_e.get().strip()
            key = key_e.get().strip()
            model = model_e.get().strip()
            # Fall back to last saved key/model/base when fields blank
            if not key and saved_llm.get("api_key"):
                key = str(saved_llm.get("api_key") or "")
            if not model and saved_llm.get("model") and (
                not pid or pid == str(saved_llm.get("provider_id") or "")
            ):
                model = str(saved_llm.get("model") or "")
            if not base and saved_llm.get("base_url") and (
                not pid or pid == str(saved_llm.get("provider_id") or "")
            ):
                base = str(saved_llm.get("base_url") or "")
            if not pid and not base and not key and not model:
                return {"api_key": "", "model": "", "base_url": ""}
            if not pid:
                return {
                    "api_key": key,
                    "model": model,
                    "base_url": base,
                }
            p = prov.get_provider(pid) or {}
            if not base:
                base = str(p.get("base_url") or "").rstrip("/")
            if not key:
                keys = p.get("keys") or []
                key = str((keys[0] or {}).get("key") or "") if keys else ""
            if not model:
                cache = list(p.get("models_cache") or [])
                model = str(cache[0]) if cache else ""
            return {"api_key": key, "model": model, "base_url": base}

        name_e = ctk.CTkEntry(body, placeholder_text="Chart name (optional) — e.g. Beta Product Org")
        name_e.pack(fill="x", padx=12, pady=3)

        ctk.CTkLabel(
            body,
            text="Kind of organisation",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=_HC_LABEL,
        ).pack(anchor="w", padx=12, pady=(8, 2))
        kind_e = ctk.CTkEntry(
            body,
            placeholder_text="e.g. Software product startup · Marketing agency · Research lab · SWAT investigation unit",
        )
        kind_e.pack(fill="x", padx=12, pady=2)

        ctk.CTkLabel(
            body,
            text="Requirements for the tree",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=_HC_LABEL,
        ).pack(anchor="w", padx=12, pady=(8, 2))
        req_box = ctk.CTkTextbox(body, height=120)
        req_box.pack(fill="x", padx=12, pady=2)
        req_box.insert(
            "1.0",
            "Examples you can replace:\n"
            "• Need a CEO, product + engineering managers, and specialists under each\n"
            "• Include security / legal review roles\n"
            "• Workers should hand off reports upward\n"
            "• Prefer 2 hierarchy levels under CEO",
        )

        size_row = ctk.CTkFrame(body, fg_color="transparent")
        size_row.pack(fill="x", padx=12, pady=(8, 2))
        ctk.CTkLabel(size_row, text="Size", text_color=_HC_MUTED).pack(side="left")
        size_var = ctk.StringVar(master=size_row, value="Medium (≈6–10 seats)")
        size_menu = ctk.CTkOptionMenu(
            size_row,
            variable=size_var,
            values=[
                "Small (≈3–5 seats)",
                "Medium (≈6–10 seats)",
                "Large (≈10–14 seats)",
                "Custom seat count…",
            ],
            width=200,
        )
        size_menu.pack(side="left", padx=8)
        ctk.CTkLabel(size_row, text="Seats", text_color=_HC_MUTED).pack(side="left", padx=(12, 4))
        seats_e = ctk.CTkEntry(
            size_row,
            width=64,
            placeholder_text="e.g. 8",
        )
        seats_e.pack(side="left")
        ctk.CTkLabel(
            size_row,
            text="(CEO + workers; used when Custom or filled)",
            text_color=_HC_MUTED,
            font=ctk.CTkFont(size=10),
        ).pack(side="left", padx=6)

        def _on_size_pick(val: str) -> None:
            if "custom" in (val or "").lower() and not seats_e.get().strip():
                seats_e.delete(0, "end")
                seats_e.insert(0, "8")

        size_menu.configure(command=_on_size_pick)

        chips = ctk.CTkFrame(body, fg_color="transparent")
        chips.pack(fill="x", padx=8, pady=(6, 2))
        ctk.CTkLabel(chips, text="Quick start:", text_color=_HC_MUTED, font=ctk.CTkFont(size=11)).pack(
            side="left", padx=4
        )

        examples = [
            (
                "SaaS startup",
                "Software-as-a-Service product company",
                "CEO oversees Product, Engineering, and Growth managers.\n"
                "Engineers (backend, frontend, QA) under Engineering.\n"
                "Content + ads under Growth. Product manager owns roadmap.\n"
                "Fill each with clear system prompts for their craft.",
            ),
            (
                "Marketing agency",
                "Digital marketing agency for B2B clients",
                "CEO + Account lead, Creative lead, Performance lead.\n"
                "Copywriter, designer, SEO, paid-ads specialists under leads.\n"
                "Emphasis on client briefs, brand voice, and measurable campaigns.",
            ),
            (
                "Research lab",
                "Applied AI research lab",
                "Director (CEO seat), Research managers by domain, research scientists and data engineers.\n"
                "Strong literature-review and experiment-design prompts.\n"
                "Include a reproducibility / eval specialist.",
            ),
            (
                "Ops / SWAT",
                "Rapid-response investigation unit (SWAT-style ops)",
                "Commander as CEO, intel lead, field lead, cyber lead.\n"
                "Analysts and operators under each lead.\n"
                "Prompts stress chain of command, evidence handling, and concise reporting.",
            ),
        ]

        def apply_example(kind: str, req: str, title: str) -> None:
            kind_e.delete(0, "end")
            kind_e.insert(0, kind)
            req_box.delete("1.0", "end")
            req_box.insert("1.0", req)
            if not name_e.get().strip():
                name_e.insert(0, title)

        for label, kind, req in examples:
            ctk.CTkButton(
                chips,
                text=label,
                width=100,
                height=26,
                command=lambda k=kind, r=req, t=label: apply_example(k, r, t),
                **style_chrome_button(),
            ).pack(side="left", padx=2)

        def _size_key() -> str:
            v = (size_var.get() or "").lower()
            if "custom" in v:
                return "custom"
            if "small" in v:
                return "small"
            if "large" in v:
                return "large"
            return "medium"

        def _parse_seats() -> int | None:
            raw = seats_e.get().strip()
            if not raw:
                if "custom" in (size_var.get() or "").lower():
                    return 8
                return None
            try:
                return max(2, min(19, int(float(raw))))
            except ValueError:
                return None

        # ---- Fixed footer: always-visible status + actions ----
        foot = foot_holder
        status = ctk.CTkLabel(
            foot,
            text="Ready — set LLM (Save LLM settings), describe the org, then Create.",
            text_color=_HC_MUTED,
            wraplength=540,
            justify="left",
            font=ctk.CTkFont(size=12),
        )
        status.pack(anchor="w", padx=14, pady=(10, 4))
        progress = ctk.CTkProgressBar(foot, height=8, mode="indeterminate")
        progress.pack(fill="x", padx=14, pady=(0, 6))
        progress.set(0)
        progress_running = {"on": False}

        def _set_status(msg: str, *, err: bool = False, busy: bool = False) -> None:
            try:
                status.configure(
                    text=msg[:900],
                    text_color="tomato" if err else _HC_MUTED,
                )
            except Exception:  # noqa: BLE001
                pass
            try:
                if busy and not progress_running["on"]:
                    progress_running["on"] = True
                    progress.configure(mode="indeterminate")
                    progress.start()
                elif not busy and progress_running["on"]:
                    progress_running["on"] = False
                    progress.stop()
                    progress.configure(mode="determinate")
                    progress.set(1.0 if not err else 0.0)
                elif not busy:
                    progress.set(0.0)
            except Exception:  # noqa: BLE001
                pass
            try:
                app.set_status(msg[:160], toast=False)
            except Exception:  # noqa: BLE001
                pass
            try:
                win.update_idletasks()
            except Exception:  # noqa: BLE001
                pass

        def run_ai() -> None:
            import threading
            import time

            from app.core.services.company.org_ai import generate_org_chart

            kind = kind_e.get().strip()
            req = req_box.get("1.0", "end").strip()
            if req.startswith("Examples you can replace:"):
                req = ""
            if not kind and not req:
                _set_status(
                    "Enter the kind of organisation and/or your tree requirements.",
                    err=True,
                )
                return
            seats = _parse_seats()
            if "custom" in (size_var.get() or "").lower() and seats is None:
                _set_status("Enter a seat count (2–19) for Custom.", err=True)
                return
            llm_kw = _resolve_llm_kwargs()
            # Always show the exact model the user chose (no silent switch)
            model_show = (llm_kw.get("model") or def_model or "?").strip()
            base_show = (llm_kw.get("base_url") or def_base or "?").strip()
            using = (
                f"{prov_var.get()} · model={model_show} · base={base_show}"
                + (f" · seats={seats}" if seats else f" · size={_size_key()}")
            )
            t0 = time.time()
            phase = {"text": "Starting…"}

            def _on_backend_status(msg: str) -> None:
                phase["text"] = (msg or "").strip() or phase["text"]
                # Thread → UI
                def _ui() -> None:
                    elapsed = int(time.time() - t0)
                    _set_status(
                        f"⏳ {elapsed}s · model stays: {model_show}\n{phase['text']}",
                        busy=True,
                    )

                try:
                    win.after(0, _ui)
                except Exception:  # noqa: BLE001
                    try:
                        app.after(0, _ui)
                    except Exception:  # noqa: BLE001
                        pass

            _set_status(
                f"⏳ 0s · model stays: {model_show}\n"
                f"Using your selection (will not auto-change model):\n{using}\n"
                f"Log: data/logs/org_ai.log — keep this window open.",
                busy=True,
            )
            try:
                create_btn.configure(state="disabled", text="⏳ Creating…")
            except Exception:  # noqa: BLE001
                pass

            # Live elapsed timer while waiting
            tick = {"n": 0, "stop": False}

            def _pulse() -> None:
                if tick["stop"]:
                    return
                try:
                    if not win.winfo_exists():
                        return
                except Exception:  # noqa: BLE001
                    return
                tick["n"] += 1
                elapsed = int(time.time() - t0)
                extra = phase.get("text") or "Waiting for provider…"
                _set_status(
                    f"⏳ {elapsed}s elapsed · model stays: {model_show}\n"
                    f"{extra}\n"
                    f"Still working — do not close. Log: data/logs/org_ai.log",
                    busy=True,
                )
                try:
                    win.after(1000, _pulse)
                except Exception:  # noqa: BLE001
                    pass

            try:
                win.after(1000, _pulse)
            except Exception:  # noqa: BLE001
                pass

            payload = {
                "org_kind": kind,
                "requirements": req,
                "size": _size_key(),
                "seat_count": seats,
                "name_hint": name_e.get().strip(),
                "api_key": llm_kw.get("api_key") or "",
                "model": llm_kw.get("model") or "",
                "base_url": llm_kw.get("base_url") or "",
            }

            def work() -> None:
                res = generate_org_chart(
                    org_kind=payload["org_kind"],
                    requirements=payload["requirements"],
                    size=payload["size"],
                    seat_count=payload["seat_count"],
                    name_hint=payload["name_hint"],
                    api_key=payload["api_key"],
                    model=payload["model"],
                    base_url=payload["base_url"],
                    make_active=True,
                    link_agents=True,
                    on_status=_on_backend_status,
                )

                def done() -> None:
                    tick["stop"] = True
                    try:
                        create_btn.configure(state="normal", text="✨ Create & save organisation")
                    except Exception:  # noqa: BLE001
                        pass
                    if not res.get("ok"):
                        err = str(res.get("error") or "Failed")
                        used = res.get("model") or model_show
                        _set_status(
                            f"{err}\n(Your model was not changed: {used})",
                            err=True,
                            busy=False,
                        )
                        try:
                            app.set_status(
                                f"Org AI failed on {used}: {err[:60]}",
                                toast=True,
                            )
                        except Exception:  # noqa: BLE001
                            pass
                        return
                    rebuild_chart_menu()
                    state["graph"] = wfg.get_active_graph()
                    state["selected_id"] = None
                    refresh_structure()
                    rat = (res.get("rationale") or "")[:120]
                    used = res.get("model") or model_show
                    ok_msg = (
                        f"✓ Saved “{res.get('graph_name')}” · model {used} · "
                        f"{res.get('node_count')} nodes · "
                        f"{res.get('prompted_workers') or 0} with system prompts · "
                        f"{res.get('elapsed_s', '?')}s"
                        + (f" — {rat}" if rat else "")
                    )
                    _set_status(ok_msg, busy=False)
                    try:
                        app.set_status(ok_msg[:160], toast=True)
                    except Exception:  # noqa: BLE001
                        pass
                    # Brief pause so user sees success, then close
                    def _close() -> None:
                        try:
                            win.destroy()
                        except Exception:  # noqa: BLE001
                            pass

                    try:
                        win.after(1200, _close)
                    except Exception:  # noqa: BLE001
                        _close()

                def _schedule_ui(fn) -> None:
                    """Marshal back to Tk main thread (safe if dialog already closed)."""
                    for host in (win, app):
                        try:
                            if host is not None and bool(host.winfo_exists()):
                                host.after(0, fn)
                                return
                        except Exception:  # noqa: BLE001
                            continue
                    # No mainloop / destroyed widgets (e.g. automated tests): run inline
                    try:
                        fn()
                    except Exception:  # noqa: BLE001
                        pass

                _schedule_ui(done)

            threading.Thread(target=work, daemon=True, name="org-ai-create").start()

        btn_row = ctk.CTkFrame(foot, fg_color="transparent")
        btn_row.pack(fill="x", padx=10, pady=(0, 10))
        create_btn = ctk.CTkButton(
            btn_row,
            text="✨ Create & save organisation",
            command=run_ai,
            height=36,
            **style_chrome_button(primary=True),
        )
        create_btn.pack(side="left", padx=4)
        ctk.CTkLabel(
            btn_row,
            text="Status shows above · LLM Save under provider section",
            text_color=_HC_MUTED,
            font=ctk.CTkFont(size=11),
        ).pack(side="left", padx=8)
        ctk.CTkButton(btn_row, text="Cancel", command=win.destroy, width=90, height=36).pack(
            side="right", padx=4
        )

    def export_org() -> None:
        from tkinter import filedialog
        import json

        g = state["graph"]
        safe = wfg.export_graph_safe(g)
        path = filedialog.asksaveasfilename(
            parent=app,
            title="Export organisation (no secrets)",
            defaultextension=".json",
            initialfile=f"{(g.get('name') or 'org').replace(' ', '_')}.json",
            filetypes=[("JSON", "*.json")],
        )
        if not path:
            return
        try:
            Path(path).write_text(
                json.dumps(safe, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            app.set_status(f"Exported org (no API keys): {path}", toast=True)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Export", str(e), parent=app)

    def import_org() -> None:
        from tkinter import filedialog
        import json

        path = filedialog.askopenfilename(
            parent=app,
            title="Import organisation",
            filetypes=[("JSON", "*.json")],
        )
        if not path:
            return
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            ng = wfg.import_graph_safe(payload, make_active=True)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Import", str(e), parent=app)
            return
        rebuild_chart_menu()
        state["graph"] = wfg.get_active_graph()
        state["selected_id"] = None
        refresh_structure()
        app.set_status(f"Imported: {ng.get('name')}", toast=True)

    for text, cmd, primary in (
        ("New org", new_org, False),
        ("✨ AI create", ai_create_org, True),
        ("Rename", rename_org, False),
        ("Copy", duplicate_org, False),
        ("Export", export_org, False),
        ("Import", import_org, False),
    ):
        kw = style_chrome_button(primary=primary) if primary else {}
        ctk.CTkButton(top, text=text, width=78 if len(text) < 10 else 90, command=cmd, **kw).pack(
            side="left", padx=2
        )
    ctk.CTkButton(top, text="Delete", width=70, fg_color="#a33", command=delete_org).pack(
        side="left", padx=2
    )
    rebuild_chart_menu()

    actions = ctk.CTkFrame(left, fg_color="transparent")
    actions.grid(row=1, column=0, sticky="ew", padx=8, pady=2)

    def add_worker_under_selected() -> None:
        g = state["graph"]
        parent = state.get("selected_id")
        if not parent:
            ceo = next((n for n in (g.get("nodes") or []) if n.get("type") == "ceo"), None)
            parent = ceo["id"] if ceo else None
        try:
            node = wfg.add_ai_worker(
                g,
                parent_id=parent,
                title="New AI Worker",
                role="Specialist",
                worker_prompt="You are an AI worker. Complete assignments carefully and report upward.",
            )
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Add AI Worker", str(e), parent=app)
            return
        state["graph"] = wfg.get_active_graph()
        state["selected_id"] = node["id"]
        refresh_structure()
        app.set_status("Added AI Worker", toast=True)
        open_worker_config(app, node, state["graph"], on_saved=_after_save)

    ctk.CTkButton(
        actions,
        text="+ Add AI Worker",
        command=add_worker_under_selected,
        width=140,
        **style_chrome_button(primary=True),
    ).pack(side="left", padx=2)
    search_e = ctk.CTkEntry(actions, placeholder_text="Search workers…", width=160)
    search_e.pack(side="left", padx=6)

    def on_search(*_a: Any) -> None:
        # Search focuses matching card if found (no full rebuild needed for empty)
        q = search_e.get().strip().lower()
        if not q:
            return
        hits = wfg.search_workers(state["graph"], q)
        if hits:
            select_node(hits[0], structure_changed=False)

    search_e.bind("<Return>", on_search)

    # Deferred handlers so chart can be constructed before form widgets exist
    _handlers: dict[str, Any] = {
        "select": lambda _n: None,
        "menu": lambda _a, _n: None,
    }

    def handle_menu_action(action: str, node: dict[str, Any]) -> None:
        """Full worker dropdown feature set."""
        nid = str(node.get("id") or "")
        # Refresh node from graph
        live = wfg.get_node(state["graph"], nid) or node

        if action == "add_child":
            try:
                child = wfg.add_ai_worker(
                    state["graph"],
                    parent_id=nid,
                    title="New AI Worker",
                    role="Specialist",
                    worker_prompt="You are an AI worker. Complete assignments carefully and report upward.",
                )
            except Exception as e:  # noqa: BLE001
                messagebox.showerror("Add AI Worker", str(e), parent=app)
                return
            state["graph"] = wfg.get_active_graph()
            state["selected_id"] = child["id"]
            refresh_structure()
            open_worker_config(app, child, state["graph"], on_saved=_after_save)
            return

        if action == "configure":
            select_node(live, structure_changed=False)
            open_worker_config(app, live, state["graph"], on_saved=_after_save)
            return

        if action == "view_goal":
            gtxt = (
                live.get("agent_goal")
                or live.get("worker_prompt")
                or live.get("instructions")
                or "(none set)"
            )
            messagebox.showinfo(
                "Current Goal",
                f"Worker: {live.get('title')}\n\n{gtxt}"[:2500],
                parent=app,
            )
            return

        if action in ("view_assignments", "view_execution", "view_reports"):
            select_node(live, structure_changed=False)
            open_worker_inspector(app, node=live)
            return

        if action == "view_comms":
            try:
                from app.services import org_comms

                rows = org_comms.list_comms(node_id=nid, limit=30)
                text = org_comms.format_comm_graph(rows)
            except Exception as e:  # noqa: BLE001
                text = f"No communication history yet.\n{e}"
            win = ctk.CTkToplevel(app)
            win.title(f"Communication — {live.get('title')}")
            win.geometry("520x420")
            win.transient(app)
            box = ctk.CTkTextbox(win, wrap="word")
            box.pack(fill="both", expand=True, padx=12, pady=12)
            box.insert("1.0", text)
            box.configure(state="disabled")
            ctk.CTkButton(win, text="Close", command=win.destroy, width=100).pack(pady=8)
            return

        if action == "duplicate":
            try:
                dup = wfg.duplicate_worker(state["graph"], nid)
            except Exception as e:  # noqa: BLE001
                messagebox.showerror("Duplicate", str(e), parent=app)
                return
            state["graph"] = wfg.get_active_graph()
            state["selected_id"] = dup["id"]
            refresh_structure()
            app.set_status(f"Duplicated: {dup.get('title')}", toast=True)
            return

        if action == "move":
            open_move_worker(
                app,
                live,
                state["graph"],
                on_moved=lambda: (
                    state.update({"graph": wfg.get_active_graph()}),
                    refresh_structure(),
                ),
            )
            return

        if action == "toggle":
            en = live.get("enabled") is not False
            wfg.update_node(state["graph"], nid, enabled=not en)
            state["graph"] = wfg.get_active_graph()
            refresh_structure()
            app.set_status(
                f"{'Disabled' if en else 'Enabled'}: {live.get('title')}",
                toast=True,
            )
            return

        if action == "remove":
            def _done() -> None:
                state["graph"] = wfg.get_active_graph()
                state["selected_id"] = None
                refresh_structure()
                clear_form()

            confirm_remove_worker(app, live, state["graph"], on_removed=_done)
            return

    _handlers["menu"] = handle_menu_action

    chart = OrgChartPanel(
        left,
        on_select=lambda n: _handlers["select"](n),
        on_menu_action=lambda a, n: _handlers["menu"](a, n),
    )
    chart.grid(row=2, column=0, sticky="nsew", padx=6, pady=6)

    # ========== RIGHT: collapsible panel (list + selection details) ==========
    right = ctk.CTkFrame(root)
    right.grid(row=2, column=1, sticky="nsew", padx=(8, 0))
    # row0 header · row1 scroll content · row2 ALWAYS-VISIBLE save bar
    right.grid_rowconfigure(1, weight=1)
    right.grid_columnconfigure(0, weight=1)

    # --- Panel header (expand / collapse whole right column) ---
    panel_hdr = ctk.CTkFrame(right, fg_color="transparent", height=36)
    panel_hdr.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 2))
    panel_title = ctk.CTkLabel(
        panel_hdr,
        text="Org panel",
        font=ctk.CTkFont(size=14, weight="bold"),
        text_color=_HC_LABEL,
    )
    panel_title.pack(side="left", padx=4)
    panel_hint = ctk.CTkLabel(
        panel_hdr,
        text="orgs · workers · details",
        text_color=_HC_MUTED,
        font=ctk.CTkFont(size=11),
    )
    panel_hint.pack(side="left", padx=6)

    # Collapsed strip (shown when panel is collapsed)
    collapsed_bar = ctk.CTkFrame(right, width=40, fg_color="transparent")
    # Expanded body = scrollable sections only (save bar is pinned below, not inside scroll)
    expanded_body = ctk.CTkFrame(right, fg_color="transparent")
    expanded_body.grid(row=1, column=0, sticky="nsew")
    expanded_body.grid_rowconfigure(0, weight=1)
    expanded_body.grid_columnconfigure(0, weight=1)

    form = ctk.CTkScrollableFrame(expanded_body, fg_color="transparent")
    form.grid(row=0, column=0, sticky="nsew")

    def _make_section(
        parent: Any,
        title: str,
        *,
        key: str,
        default_open: bool = True,
    ) -> tuple[ctk.CTkFrame, ctk.CTkFrame, Any]:
        """Collapsible section: header toggles body pack. Returns (wrap, body, toggle_fn)."""
        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        wrap.pack(fill="x", padx=4, pady=(6, 2))
        hdr = ctk.CTkFrame(
            wrap,
            fg_color=_THEME_UI.get("top_bg", ("#f3f4f6", "#161a22")),
            corner_radius=8,
            height=32,
        )
        hdr.pack(fill="x")
        arrow = ctk.CTkLabel(
            hdr,
            text="▾" if default_open else "▸",
            width=22,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=_HC_LABEL,
        )
        arrow.pack(side="left", padx=(8, 2), pady=4)
        ctk.CTkLabel(
            hdr,
            text=title,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=_HC_LABEL,
        ).pack(side="left", padx=2, pady=4)
        body = ctk.CTkFrame(wrap, fg_color="transparent")
        if default_open:
            body.pack(fill="x", padx=2, pady=(4, 2))
        state[key] = default_open

        def toggle(_e: Any = None) -> None:
            open_now = not bool(state.get(key))
            state[key] = open_now
            arrow.configure(text="▾" if open_now else "▸")
            if open_now:
                body.pack(fill="x", padx=2, pady=(4, 2))
            else:
                body.pack_forget()

        for w in (hdr, arrow):
            w.bind("<Button-1>", toggle)
        # Clickable whole header
        for child in hdr.winfo_children():
            child.bind("<Button-1>", toggle)
        return wrap, body, toggle

    # ----- Section 0: All organisation charts created (test swat, beta org, …) -----
    _sec0, charts_body, _ = _make_section(
        form, "All organisations", key="sec_charts", default_open=True
    )
    ctk.CTkLabel(
        charts_body,
        text="Every org chart you created · open to edit · ☑ multi-select · Delete / Rename / Copy",
        text_color=_HC_MUTED,
        font=ctk.CTkFont(size=11),
        wraplength=340,
        justify="left",
    ).pack(anchor="w", padx=8, pady=(0, 4))

    charts_tools = ctk.CTkFrame(charts_body, fg_color="transparent")
    charts_tools.pack(fill="x", padx=4, pady=2)
    chart_select_all_var = ctk.BooleanVar(master=charts_tools, value=False)
    charts_count_lbl = ctk.CTkLabel(
        charts_tools,
        text="0 selected",
        text_color=_HC_MUTED,
        font=ctk.CTkFont(size=11),
    )
    charts_total_lbl = ctk.CTkLabel(
        charts_tools,
        text="",
        text_color=_HC_MUTED,
        font=ctk.CTkFont(size=11),
    )

    def _sync_chart_checked() -> None:
        checked: set[str] = set()
        for gid, var in (state.get("chart_check_vars") or {}).items():
            try:
                if var.get():
                    checked.add(str(gid))
            except Exception:  # noqa: BLE001
                pass
        state["chart_checked_ids"] = checked
        charts_count_lbl.configure(text=f"{len(checked)} selected")
        try:
            vars_map = state.get("chart_check_vars") or {}
            if vars_map and all(v.get() for v in vars_map.values()):
                chart_select_all_var.set(True)
            else:
                chart_select_all_var.set(False)
        except Exception:  # noqa: BLE001
            pass

    def on_chart_select_all() -> None:
        on = bool(chart_select_all_var.get())
        for _gid, var in list((state.get("chart_check_vars") or {}).items()):
            try:
                var.set(on)
            except Exception:  # noqa: BLE001
                pass
        _sync_chart_checked()

    ctk.CTkCheckBox(
        charts_tools,
        text="Select all",
        variable=chart_select_all_var,
        command=on_chart_select_all,
        font=ctk.CTkFont(size=12),
        width=100,
    ).pack(side="left", padx=(4, 8))
    charts_count_lbl.pack(side="left", padx=4)
    charts_total_lbl.pack(side="right", padx=6)

    charts_bulk = ctk.CTkFrame(charts_body, fg_color="transparent")
    charts_bulk.pack(fill="x", padx=4, pady=(2, 4))

    def _checked_chart_ids() -> list[str]:
        _sync_chart_checked()
        return list(state.get("chart_checked_ids") or set())

    def open_chart_by_id(gid: str) -> None:
        """Make organisation active and show its tree/chart."""
        gid = str(gid or "").strip()
        if not gid or not wfg.get_graph(gid):
            return
        wfg.set_active_graph(gid)
        state["graph"] = wfg.get_active_graph()
        state["selected_id"] = None
        state["checked_ids"] = set()
        rebuild_chart_menu()
        clear_form()
        refresh_structure()
        app.set_status(
            f"Opened organisation: {state['graph'].get('name') or gid[:8]}",
            toast=True,
        )

    def rename_chart_by_id(gid: str) -> None:
        g = wfg.get_graph(gid)
        if not g:
            return
        win = ctk.CTkToplevel(app)
        win.title("Rename organisation")
        win.geometry("420x140")
        win.transient(app)
        e = ctk.CTkEntry(win, placeholder_text="Organisation name")
        e.pack(fill="x", padx=16, pady=16)
        e.insert(0, g.get("name") or "")
        e.focus_set()

        def ok() -> None:
            name = e.get().strip()
            wfg.rename_graph(str(g.get("id")), name)
            rebuild_chart_menu()
            state["graph"] = wfg.get_active_graph()
            refresh_charts_list()
            win.destroy()
            app.set_status(f"Renamed → {name or g.get('name')}", toast=True)

        ctk.CTkButton(win, text="Save name", command=ok, **style_chrome_button(primary=True)).pack(
            pady=8
        )
        e.bind("<Return>", lambda _e: ok())

    def duplicate_chart_by_id(gid: str) -> None:
        ng = wfg.duplicate_graph(gid)
        if not ng:
            messagebox.showerror("Copy", "Could not duplicate organisation.", parent=app)
            return
        wfg.set_active_graph(ng["id"])
        rebuild_chart_menu()
        state["graph"] = wfg.get_active_graph()
        state["selected_id"] = None
        refresh_structure()
        app.set_status(f"Copied organisation: {ng.get('name')}", toast=True)

    def delete_charts_by_ids(ids: list[str]) -> None:
        ids = [str(i).strip() for i in ids if str(i).strip()]
        if not ids:
            messagebox.showinfo(
                "Delete organisations",
                "Tick one or more organisations in the list first.",
                parent=app,
            )
            return
        graphs = {str(g.get("id")): g for g in wfg.list_graphs()}
        # Never allow deleting the last remaining chart
        remaining_after = len(graphs) - len([i for i in ids if i in graphs])
        if remaining_after < 1:
            messagebox.showinfo(
                "Delete organisations",
                "Keep at least one organisation chart. Uncheck one, or create another first.",
                parent=app,
            )
            return
        names = [str((graphs.get(i) or {}).get("name") or i[:8]) for i in ids if i in graphs]
        preview = ", ".join(names[:6])
        extra = f" (+{len(names) - 6} more)" if len(names) > 6 else ""
        if not messagebox.askyesno(
            "Delete organisations",
            f"Delete {len(names)} organisation chart(s)?\n\n{preview}{extra}\n\n"
            "Workers inside those charts are removed from the charts.\n"
            "Agent profiles / API keys are kept.",
            parent=app,
        ):
            return
        deleted = 0
        failed = 0
        for gid in ids:
            if gid not in graphs:
                continue
            if len(wfg.list_graphs()) <= 1:
                failed += 1
                break
            if wfg.delete_graph(gid):
                deleted += 1
            else:
                failed += 1
        state["chart_checked_ids"] = set()
        rebuild_chart_menu()
        state["graph"] = wfg.get_active_graph()
        state["selected_id"] = None
        clear_form()
        refresh_structure()
        msg = f"Deleted {deleted} organisation(s)"
        if failed:
            msg += f" · {failed} skipped"
        app.set_status(msg, toast=True)

    def bulk_delete_charts() -> None:
        delete_charts_by_ids(_checked_chart_ids())

    def bulk_open_chart() -> None:
        ids = _checked_chart_ids()
        if len(ids) != 1 and not state.get("graph"):
            messagebox.showinfo("Open", "Tick exactly one organisation, or click its name.", parent=app)
            return
        if len(ids) == 1:
            open_chart_by_id(ids[0])
        else:
            messagebox.showinfo("Open", "Tick exactly one organisation to open.", parent=app)

    def bulk_rename_chart() -> None:
        ids = _checked_chart_ids()
        if len(ids) != 1:
            # Prefer active if none / many
            if len(ids) == 0:
                rename_chart_by_id(str(state["graph"].get("id") or ""))
                return
            messagebox.showinfo("Rename", "Tick exactly one organisation to rename.", parent=app)
            return
        rename_chart_by_id(ids[0])

    def bulk_copy_charts() -> None:
        ids = _checked_chart_ids()
        if not ids:
            # Copy active
            gid = str(state["graph"].get("id") or "")
            if gid:
                duplicate_chart_by_id(gid)
            return
        last = None
        n_ok = 0
        for gid in ids:
            ng = wfg.duplicate_graph(gid)
            if ng:
                last = ng
                n_ok += 1
        if last:
            wfg.set_active_graph(last["id"])
            rebuild_chart_menu()
            state["graph"] = wfg.get_active_graph()
            state["selected_id"] = None
            refresh_structure()
        app.set_status(f"Copied {n_ok} organisation(s)", toast=True)

    def new_org_from_panel() -> None:
        new_org()
        refresh_charts_list()

    for label, cmd, danger in (
        ("Open", bulk_open_chart, False),
        ("Rename", bulk_rename_chart, False),
        ("Copy", bulk_copy_charts, False),
        ("New", new_org_from_panel, False),
        ("Delete", bulk_delete_charts, True),
    ):
        kw: dict[str, Any] = {"width": 70, "height": 28, "command": cmd}
        if danger:
            kw.update(
                fg_color=("#dc2626", "#7f1d1d"),
                hover_color=("#991b1b", "#450a0a"),
            )
        else:
            kw.update(style_chrome_button())
        ctk.CTkButton(charts_bulk, text=label, **kw).pack(side="left", padx=2, pady=2)

    charts_list_box = ctk.CTkScrollableFrame(
        charts_body, height=160, fg_color=("gray95", "#0f172a")
    )
    charts_list_box.pack(fill="both", expand=True, padx=4, pady=(2, 6))

    def refresh_charts_list() -> None:
        """List every saved organisation chart (test swat, beta org, …)."""
        for w in charts_list_box.winfo_children():
            try:
                w.destroy()
            except Exception:  # noqa: BLE001
                pass
        prev = set(state.get("chart_checked_ids") or set())
        state["chart_check_vars"] = {}
        graphs = wfg.list_graphs()
        active_id = str((wfg.get_active_graph() or {}).get("id") or "")
        try:
            charts_total_lbl.configure(text=f"{len(graphs)} org(s)")
        except Exception:  # noqa: BLE001
            pass
        if not graphs:
            ctk.CTkLabel(
                charts_list_box,
                text="No organisations yet — click New.",
                text_color=_HC_MUTED,
                font=ctk.CTkFont(size=12),
            ).pack(anchor="w", padx=8, pady=8)
            _sync_chart_checked()
            return
        # Newest first if updated_at present, else keep store order reversed for recency feel
        try:
            graphs = sorted(
                graphs,
                key=lambda g: str(g.get("updated_at") or g.get("created_at") or ""),
                reverse=True,
            )
        except Exception:  # noqa: BLE001
            pass
        for g in graphs:
            gid = str(g.get("id") or "")
            if not gid:
                continue
            name = str(g.get("name") or "Organisation").strip() or "Organisation"
            n_nodes = len(g.get("nodes") or [])
            is_active = gid == active_id
            row = ctk.CTkFrame(
                charts_list_box,
                fg_color=("#dbeafe", "#1e3a5f") if is_active else "transparent",
                corner_radius=6,
            )
            row.pack(fill="x", padx=2, pady=1)
            var = ctk.BooleanVar(master=row, value=gid in prev)
            state["chart_check_vars"][gid] = var
            ctk.CTkCheckBox(
                row,
                text="",
                variable=var,
                width=22,
                command=_sync_chart_checked,
            ).pack(side="left", padx=(2, 0), pady=2)
            badge = "● " if is_active else ""
            label = f"{badge}{name}"
            meta = f"{n_nodes} worker(s)" if n_nodes != 1 else "1 worker"
            name_btn = ctk.CTkButton(
                row,
                text=f"{label[:36]}{'…' if len(label) > 36 else ''}  · {meta}",
                anchor="w",
                height=30,
                fg_color="transparent",
                hover_color=_THEME_UI.get("sidebar_hover", ("#e5e7eb", "#1f2937")),
                text_color=_HC_LABEL,
                font=ctk.CTkFont(size=12, weight="bold" if is_active else "normal"),
                command=lambda i=gid: open_chart_by_id(i),
            )
            name_btn.pack(side="left", fill="x", expand=True, padx=2, pady=1)
            ctk.CTkButton(
                row,
                text="✎",
                width=28,
                height=26,
                command=lambda i=gid: rename_chart_by_id(i),
                **style_chrome_button(),
            ).pack(side="right", padx=1, pady=2)
            ctk.CTkButton(
                row,
                text="×",
                width=26,
                height=26,
                fg_color=("#dc2626", "#7f1d1d"),
                hover_color=("#991b1b", "#450a0a"),
                command=lambda i=gid: delete_charts_by_ids([i]),
            ).pack(side="right", padx=1, pady=2)
        _sync_chart_checked()

    # ----- Section 1: Full organisation tree list (every node + checkboxes + Add) -----
    _sec1, list_body, _ = _make_section(
        form, "Workers in this org", key="sec_list", default_open=True
    )
    ctk.CTkLabel(
        list_body,
        text="Full chart as a tree · ☑ multi-select · + adds under that person · click name to edit",
        text_color=_HC_MUTED,
        font=ctk.CTkFont(size=11),
        wraplength=340,
        justify="left",
    ).pack(anchor="w", padx=8, pady=(0, 4))
    list_tools = ctk.CTkFrame(list_body, fg_color="transparent")
    list_tools.pack(fill="x", padx=4, pady=2)
    select_all_var = ctk.BooleanVar(master=list_tools, value=False)
    list_count_lbl = ctk.CTkLabel(
        list_tools,
        text="0 selected",
        text_color=_HC_MUTED,
        font=ctk.CTkFont(size=11),
    )
    tree_total_lbl = ctk.CTkLabel(
        list_tools,
        text="",
        text_color=_HC_MUTED,
        font=ctk.CTkFont(size=11),
    )

    def _sync_checked_from_vars() -> None:
        checked: set[str] = set()
        for nid, var in (state.get("check_vars") or {}).items():
            try:
                if var.get():
                    checked.add(str(nid))
            except Exception:  # noqa: BLE001
                pass
        state["checked_ids"] = checked
        n = len(checked)
        list_count_lbl.configure(text=f"{n} selected")
        # Keep select-all checkbox honest
        try:
            vars_map = state.get("check_vars") or {}
            selectable = [
                nid
                for nid, v in vars_map.items()
                if (wfg.get_node(state["graph"], nid) or {}).get("type") != "ceo"
            ]
            if selectable and all(
                (vars_map[nid].get() if nid in vars_map else False) for nid in selectable
            ):
                select_all_var.set(True)
            else:
                select_all_var.set(False)
        except Exception:  # noqa: BLE001
            pass

    def _set_all_checks(on: bool) -> None:
        for nid, var in list((state.get("check_vars") or {}).items()):
            node = wfg.get_node(state["graph"], nid)
            if node and node.get("type") == "ceo":
                var.set(False)
                continue
            try:
                var.set(bool(on))
            except Exception:  # noqa: BLE001
                pass
        _sync_checked_from_vars()

    def on_select_all() -> None:
        _set_all_checks(bool(select_all_var.get()))

    ctk.CTkCheckBox(
        list_tools,
        text="Select all",
        variable=select_all_var,
        command=on_select_all,
        font=ctk.CTkFont(size=12),
        width=100,
    ).pack(side="left", padx=(4, 8))
    list_count_lbl.pack(side="left", padx=4)
    tree_total_lbl.pack(side="right", padx=6)

    bulk_row = ctk.CTkFrame(list_body, fg_color="transparent")
    bulk_row.pack(fill="x", padx=4, pady=(2, 4))

    def _checked_nodes() -> list[dict[str, Any]]:
        _sync_checked_from_vars()
        out: list[dict[str, Any]] = []
        for nid in list(state.get("checked_ids") or set()):
            n = wfg.get_node(state["graph"], nid)
            if n and n.get("type") != "ceo":
                out.append(n)
        return out

    def bulk_delete() -> None:
        nodes = _checked_nodes()
        if not nodes:
            messagebox.showinfo(
                "Delete",
                "Tick one or more workers in the list (CEO cannot be deleted).",
                parent=app,
            )
            return
        names = ", ".join((n.get("title") or "?")[:24] for n in nodes[:8])
        extra = f" (+{len(nodes) - 8} more)" if len(nodes) > 8 else ""
        if not messagebox.askyesno(
            "Delete selected",
            f"Delete {len(nodes)} worker(s)?\n\n{names}{extra}\n\n"
            "Descendants of each selected worker are also removed.\n"
            "Agent profiles and API keys are kept.",
            parent=app,
        ):
            return
        removed: set[str] = set()
        errors: list[str] = []
        # Delete deepest first so parent delete does not double-count
        ordered = sorted(
            nodes,
            key=lambda n: -int(
                next(
                    (
                        x.get("_depth") or 0
                        for x in wfg.walk_tree(state["graph"])
                        if x.get("id") == n.get("id")
                    ),
                    0,
                )
            ),
        )
        for n in ordered:
            nid = str(n.get("id") or "")
            if not nid or nid in removed:
                continue
            res = wfg.delete_node(state["graph"], nid, children_mode="delete")
            if res.get("ok"):
                for rid in res.get("removed_ids") or [nid]:
                    removed.add(str(rid))
            else:
                errors.append(str(res.get("error") or nid))
            state["graph"] = wfg.get_active_graph()
        state["checked_ids"] = set()
        if state.get("selected_id") in removed:
            state["selected_id"] = None
            clear_form()
        refresh_structure()
        msg = f"Deleted {len(removed)} node(s)"
        if errors:
            msg += f" · {len(errors)} failed"
        app.set_status(msg, toast=True)

    def bulk_set_enabled(enabled: bool) -> None:
        nodes = _checked_nodes()
        if not nodes:
            messagebox.showinfo("Selection", "Tick workers first.", parent=app)
            return
        for n in nodes:
            wfg.update_node(state["graph"], str(n["id"]), enabled=enabled)
            state["graph"] = wfg.get_active_graph()
        refresh_structure()
        app.set_status(
            f"{'Enabled' if enabled else 'Disabled'} {len(nodes)} worker(s)",
            toast=True,
        )

    def bulk_duplicate() -> None:
        nodes = _checked_nodes()
        if not nodes:
            messagebox.showinfo("Duplicate", "Tick workers first.", parent=app)
            return
        last_id = None
        n_ok = 0
        for n in nodes:
            try:
                dup = wfg.duplicate_worker(state["graph"], str(n["id"]))
                last_id = dup.get("id")
                n_ok += 1
                state["graph"] = wfg.get_active_graph()
            except Exception:  # noqa: BLE001
                pass
        if last_id:
            state["selected_id"] = last_id
        refresh_structure()
        app.set_status(f"Duplicated {n_ok} worker(s)", toast=True)

    def add_child_under(parent_id: str | None, *, open_config: bool = True) -> None:
        """Add AI Worker under a specific tree node (or CEO if parent empty)."""
        pid = (parent_id or "").strip() or None
        if not pid:
            ceo = next(
                (n for n in (state["graph"].get("nodes") or []) if n.get("type") == "ceo"),
                None,
            )
            pid = ceo["id"] if ceo else None
        if not pid:
            messagebox.showinfo("Add", "No parent found in organisation.", parent=app)
            return
        try:
            child = wfg.add_ai_worker(
                state["graph"],
                parent_id=pid,
                title="New AI Worker",
                role="Specialist",
                worker_prompt="You are an AI worker. Complete assignments carefully and report upward.",
            )
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Add AI Worker", str(e), parent=app)
            return
        state["graph"] = wfg.get_active_graph()
        state["selected_id"] = child["id"]
        refresh_structure()
        app.set_status(f"Added under parent · {child.get('title')}", toast=True)
        if open_config:
            open_worker_config(app, child, state["graph"], on_saved=_after_save)

    def bulk_add_child() -> None:
        nodes = _checked_nodes()
        parent_id = None
        if len(nodes) == 1:
            parent_id = str(nodes[0].get("id") or "")
        elif state.get("selected_id"):
            parent_id = str(state["selected_id"])
        else:
            parent_id = None
        add_child_under(parent_id)

    for label, cmd, danger in (
        ("Delete", bulk_delete, True),
        ("Enable", lambda: bulk_set_enabled(True), False),
        ("Disable", lambda: bulk_set_enabled(False), False),
        ("Duplicate", bulk_duplicate, False),
        ("+ Child", bulk_add_child, False),
    ):
        kw: dict[str, Any] = {"width": 72, "height": 28, "command": cmd}
        if danger:
            kw.update(
                fg_color=("#dc2626", "#7f1d1d"),
                hover_color=("#991b1b", "#450a0a"),
            )
        else:
            kw.update(style_chrome_button())
        ctk.CTkButton(bulk_row, text=label, **kw).pack(side="left", padx=2, pady=2)

    # Taller tree so the full organisation hierarchy is readable
    org_list_box = ctk.CTkScrollableFrame(
        list_body, height=320, fg_color=("gray95", "#0f172a")
    )
    org_list_box.pack(fill="both", expand=True, padx=4, pady=(2, 6))

    def refresh_org_list() -> None:
        """Rebuild full organisation tree list (every node) with checkbox + Add on each row."""
        for w in org_list_box.winfo_children():
            try:
                w.destroy()
            except Exception:  # noqa: BLE001
                pass
        prev_checked = set(state.get("checked_ids") or set())
        state["check_vars"] = {}
        state["list_rows"] = {}
        state["list_name_btns"] = {}
        g = state["graph"]
        selected = str(state.get("selected_id") or "")
        rows = wfg.walk_tree(g)
        raw_count = len(g.get("nodes") or [])
        try:
            tree_total_lbl.configure(text=f"{len(rows)} in tree · {raw_count} total")
        except Exception:  # noqa: BLE001
            pass
        if not rows:
            ctk.CTkLabel(
                org_list_box,
                text="Empty organisation — use + on toolbar or New org.",
                text_color=_HC_MUTED,
                font=ctk.CTkFont(size=12),
            ).pack(anchor="w", padx=8, pady=8)
            _sync_checked_from_vars()
            return

        # Precompute last-child flags for tree branch glyphs
        by_parent: dict[str | None, list[str]] = {}
        for n in rows:
            pid = n.get("parent_id")
            if pid is None or str(pid).strip() == "":
                key: str | None = None
            else:
                key = str(pid)
            by_parent.setdefault(key, []).append(str(n.get("id") or ""))

        for idx, n in enumerate(rows):
            nid = str(n.get("id") or "")
            if not nid:
                continue
            depth = int(n.get("_depth") or 0)
            is_ceo = n.get("type") == "ceo"
            title = str(n.get("title") or "Worker")
            role = str(
                n.get("_agent_role") or n.get("agent_role") or n.get("role") or n.get("type") or ""
            )
            disabled = n.get("enabled") is False
            # Tree branch drawing
            if depth <= 0:
                branch = ""
            else:
                pid = n.get("parent_id")
                pkey = None if pid is None or str(pid).strip() == "" else str(pid)
                siblings = by_parent.get(pkey) or []
                is_last = bool(siblings) and siblings[-1] == nid
                pad = "│  " * max(0, depth - 1)
                branch = pad + ("└─ " if is_last else "├─ ")
            if n.get("type") == "ceo":
                icon = "👑"
            elif n.get("type") == "department":
                icon = "🏢"
            elif n.get("_is_manager"):
                icon = "📋"
            else:
                icon = "👤"
            label = f"{branch}{icon} {title}"
            if role and role not in (n.get("type"), title):
                label += f"  · {role[:18]}"
            if disabled:
                label += "  (off)"
            if n.get("_orphan"):
                label += "  ⚠ unlinked"
            row = ctk.CTkFrame(
                org_list_box,
                fg_color=("#dbeafe", "#1e3a5f") if nid == selected else "transparent",
                corner_radius=6,
            )
            row.pack(fill="x", padx=2, pady=1)
            state["list_rows"][nid] = row
            var = ctk.BooleanVar(master=row, value=(nid in prev_checked) and not is_ceo)
            state["check_vars"][nid] = var

            def _on_check(*_a: Any, _id: str = nid) -> None:
                _sync_checked_from_vars()

            cb = ctk.CTkCheckBox(
                row,
                text="",
                variable=var,
                width=22,
                command=_on_check,
                state="disabled" if is_ceo else "normal",
            )
            cb.pack(side="left", padx=(2, 0), pady=2)
            name_btn = ctk.CTkButton(
                row,
                text=label[:48] + ("…" if len(label) > 48 else ""),
                anchor="w",
                height=28,
                fg_color="transparent",
                hover_color=_THEME_UI.get("sidebar_hover", ("#e5e7eb", "#1f2937")),
                text_color=_HC_MUTED if disabled else _HC_LABEL,
                font=ctk.CTkFont(
                    size=12,
                    weight="bold" if nid == selected else "normal",
                    family="Consolas",
                ),
                command=lambda i=nid: _select_from_list(i),
            )
            name_btn.pack(side="left", fill="x", expand=True, padx=1, pady=1)
            state["list_name_btns"][nid] = name_btn
            # + Add under THIS node (every row in the tree, including CEO)
            add_btn = ctk.CTkButton(
                row,
                text="+",
                width=28,
                height=26,
                corner_radius=6,
                command=lambda i=nid: add_child_under(i),
                **style_chrome_button(primary=True),
            )
            add_btn.pack(side="right", padx=(1, 2), pady=2)
            # Per-row remove (not for CEO)
            if not is_ceo:
                rm_btn = ctk.CTkButton(
                    row,
                    text="×",
                    width=26,
                    height=26,
                    corner_radius=6,
                    fg_color=("#dc2626", "#7f1d1d"),
                    hover_color=("#991b1b", "#450a0a"),
                    command=lambda i=nid: _remove_from_list(i),
                )
                rm_btn.pack(side="right", padx=1, pady=2)
        _sync_checked_from_vars()

    def _select_from_list(nid: str) -> None:
        n = wfg.get_node(state["graph"], nid)
        if n:
            select_node(n, structure_changed=False)

    def _remove_from_list(nid: str) -> None:
        n = wfg.get_node(state["graph"], nid)
        if not n:
            return

        def _done() -> None:
            state["graph"] = wfg.get_active_graph()
            if state.get("selected_id") == nid:
                state["selected_id"] = None
                clear_form()
            state["checked_ids"] = {
                i for i in (state.get("checked_ids") or set()) if i != nid
            }
            refresh_structure()

        confirm_remove_worker(app, n, state["graph"], on_removed=_done)

    # ----- Section 2: Selection details -----
    _sec2, details_body, _ = _make_section(
        form, "Selection details", key="sec_details", default_open=True
    )
    detail = ctk.CTkLabel(
        details_body,
        text="Click a card in the chart or a name in the list.",
        text_color=_HC_MUTED,
        wraplength=320,
        justify="left",
    )
    detail.pack(anchor="w", padx=8, pady=(2, 4))

    title_e = ctk.CTkEntry(details_body, placeholder_text="Selected node title")
    title_e.pack(fill="x", padx=8, pady=(6, 3))
    order_e = ctk.CTkEntry(details_body, placeholder_text="Order among siblings (0, 1, 2…)")
    order_e.pack(fill="x", padx=8, pady=3)
    instr_box = ctk.CTkTextbox(details_body, height=72)
    instr_box.pack(fill="x", padx=8, pady=4)
    agent_role_e = ctk.CTkEntry(details_body, placeholder_text="Role")
    agent_role_e.pack(fill="x", padx=8, pady=3)
    agent_goal_e = ctk.CTkEntry(details_body, placeholder_text="Standing goal")
    agent_goal_e.pack(fill="x", padx=8, pady=3)

    ctk.CTkLabel(
        details_body,
        text="System prompt (permanent identity — required for AI seats)",
        text_color=_HC_MUTED,
        font=ctk.CTkFont(size=11),
    ).pack(anchor="w", padx=8, pady=(8, 2))
    sys_prompt_box = ctk.CTkTextbox(details_body, height=70)
    sys_prompt_box.pack(fill="x", padx=8, pady=2)
    ctk.CTkLabel(
        details_body,
        text="Worker prompt (how this seat works day-to-day)",
        text_color=_HC_MUTED,
        font=ctk.CTkFont(size=11),
    ).pack(anchor="w", padx=8, pady=(6, 2))
    worker_prompt_box = ctk.CTkTextbox(details_body, height=60)
    worker_prompt_box.pack(fill="x", padx=8, pady=2)

    ctk.CTkLabel(
        details_body,
        text="Quick LLM (empty = Default). Full config via ⚙ Configure.",
        text_color=_HC_MUTED,
        font=ctk.CTkFont(size=11),
        wraplength=320,
        justify="left",
    ).pack(anchor="w", padx=8, pady=(8, 2))
    edit_llm_model = ctk.CTkEntry(details_body, placeholder_text="LLM model override")
    edit_llm_model.pack(fill="x", padx=8, pady=3)
    edit_llm_base = ctk.CTkEntry(details_body, placeholder_text="Base URL override")
    edit_llm_base.pack(fill="x", padx=8, pady=3)
    edit_llm_key = ctk.CTkEntry(details_body, placeholder_text="API key override (hidden)", show="*")
    edit_llm_key.pack(fill="x", padx=8, pady=3)

    # Save lives here too (not only at panel foot) so it is obvious after editing fields
    details_actions = ctk.CTkFrame(details_body, fg_color="transparent")
    details_actions.pack(fill="x", padx=8, pady=(8, 10))
    # Commands wired after save_selected is defined — placeholders filled later
    details_save_btn = ctk.CTkButton(
        details_actions,
        text="💾 Save selection",
        height=34,
        **style_chrome_button(primary=True),
    )
    details_save_btn.pack(side="left", padx=(0, 4))
    details_cfg_btn = ctk.CTkButton(
        details_actions,
        text="⚙ Full configure",
        height=34,
        width=120,
        **style_chrome_button(),
    )
    details_cfg_btn.pack(side="left", padx=2)
    ctk.CTkLabel(
        details_actions,
        text="Saves title, role, goal, instructions, LLM overrides",
        text_color=_HC_MUTED,
        font=ctk.CTkFont(size=10),
    ).pack(side="left", padx=6)

    # ----- Section 3: Tree preview -----
    _sec3, preview_body, _ = _make_section(
        form, "Tree preview", key="sec_preview", default_open=False
    )
    preview = ctk.CTkTextbox(preview_body, height=110)
    preview.pack(fill="x", padx=8, pady=(2, 10))

    def clear_form() -> None:
        for w in (title_e, order_e, agent_role_e, agent_goal_e, edit_llm_model, edit_llm_base, edit_llm_key):
            w.delete(0, "end")
        instr_box.delete("1.0", "end")
        sys_prompt_box.delete("1.0", "end")
        worker_prompt_box.delete("1.0", "end")
        detail.configure(text="Click a card in the chart or a name in the list.")

    def select_node(node: dict[str, Any], *, structure_changed: bool = False) -> None:
        """Select without destroying the chart (unless structure_changed)."""
        state["selected_id"] = node.get("id")
        try:
            chart.set_selection(str(node.get("id") or ""))
        except Exception:  # noqa: BLE001
            pass

        title_e.delete(0, "end")
        title_e.insert(0, node.get("title") or "")
        order_e.delete(0, "end")
        try:
            order_e.insert(0, str(int(node.get("order") or 0)))
        except Exception:  # noqa: BLE001
            order_e.insert(0, "0")
        instr_box.delete("1.0", "end")
        instr_box.insert("1.0", node.get("instructions") or "")
        agent_role_e.delete(0, "end")
        agent_goal_e.delete(0, "end")
        edit_llm_model.delete(0, "end")
        edit_llm_base.delete(0, "end")
        edit_llm_key.delete(0, "end")
        sys_prompt_box.delete("1.0", "end")
        worker_prompt_box.delete("1.0", "end")

        t = node.get("type")
        ag = None
        if node.get("agent_id"):
            ag = agent_storage.get_agent(node.get("agent_id") or "")
        # Prompts: node first, then linked agent profile
        sys_p = (
            node.get("system_prompt")
            or (ag or {}).get("system_prompt")
            or ""
        )
        work_p = (
            node.get("worker_prompt")
            or (ag or {}).get("worker_prompt")
            or ""
        )
        sys_prompt_box.insert("1.0", str(sys_p))
        worker_prompt_box.insert("1.0", str(work_p))

        if t in ("agent", "role", "worker"):
            agent_role_e.insert(0, (ag or {}).get("role") or node.get("agent_role") or "")
            agent_goal_e.insert(0, (ag or {}).get("goal") or node.get("agent_goal") or "")
            edit_llm_model.insert(0, (ag or {}).get("llm_model") or node.get("llm_model") or "")
            edit_llm_base.insert(0, (ag or {}).get("llm_base_url") or node.get("llm_base_url") or "")
            detail.configure(
                text=f"Worker “{node.get('title')}” — edit prompts + Save, or ⚙ Configure."
            )
        elif t == "department":
            detail.configure(
                text=f"Department “{node.get('title')}” — set order/instructions, + adds workers."
            )
        else:
            agent_role_e.insert(0, node.get("agent_role") or "CEO")
            agent_goal_e.insert(0, node.get("agent_goal") or "")
            detail.configure(
                text="CEO — edit system/worker prompts + Save. Use + to add workers under CEO."
            )
        try:
            save_status.configure(text="Selected — edit then Save", text_color=_HC_MUTED)
        except Exception:  # noqa: BLE001
            pass

        if structure_changed:
            refresh_structure()
        else:
            # Soft list highlight only — never rebuild lists on click (stops flicker)
            try:
                soft_highlight_org_list(str(node.get("id") or ""))
            except Exception:  # noqa: BLE001
                pass

    def soft_highlight_org_list(nid: str) -> None:
        """Update selected row colors without destroying list widgets."""
        rows = state.get("list_rows") or {}
        btns = state.get("list_name_btns") or {}
        for rid, row in rows.items():
            on = str(rid) == str(nid)
            try:
                row.configure(
                    fg_color=("#dbeafe", "#1e3a5f") if on else "transparent"
                )
            except Exception:  # noqa: BLE001
                pass
            btn = btns.get(rid)
            if btn is not None:
                try:
                    btn.configure(
                        font=ctk.CTkFont(
                            size=12,
                            weight="bold" if on else "normal",
                            family="Consolas",
                        )
                    )
                except Exception:  # noqa: BLE001
                    pass

    _handlers["select"] = lambda n: select_node(n, structure_changed=False)

    def refresh_structure(*, lists: bool = True, preview_text: bool = True) -> None:
        """Rebuild chart when hierarchy changes. Avoids work on pure selection."""
        state["graph"] = wfg.get_active_graph()
        g = state["graph"]
        # Drop checks for nodes that no longer exist
        live_ids = {str(n.get("id")) for n in (g.get("nodes") or [])}
        state["checked_ids"] = {i for i in (state.get("checked_ids") or set()) if i in live_ids}
        live_chart_ids = {str(x.get("id")) for x in wfg.list_graphs()}
        state["chart_checked_ids"] = {
            i for i in (state.get("chart_checked_ids") or set()) if i in live_chart_ids
        }
        try:
            # render() is soft when structure signature unchanged
            chart.render(g, selected_id=state.get("selected_id"))
        except Exception as e:  # noqa: BLE001
            app.set_status(f"Chart render error: {e}", toast=False)
        if lists:
            try:
                refresh_charts_list()
            except Exception:  # noqa: BLE001
                pass
            try:
                refresh_org_list()
            except Exception:  # noqa: BLE001
                pass
        if preview_text:
            try:
                preview.configure(state="normal")
                preview.delete("1.0", "end")
                preview.insert("1.0", wfg.tree_ascii(g))
                preview.configure(state="disabled")
            except Exception:  # noqa: BLE001
                pass

    def _after_save() -> None:
        state["graph"] = wfg.get_active_graph()
        refresh_structure()
        sid = state.get("selected_id")
        if sid:
            n = wfg.get_node(state["graph"], sid)
            if n:
                select_node(n, structure_changed=False)

    def save_selected() -> None:
        sid = state.get("selected_id")
        if not sid:
            messagebox.showinfo("Save", "Select a card or list row first.", parent=app)
            return
        node = wfg.get_node(state["graph"], sid)
        if not node:
            messagebox.showerror("Save", "Selected node not found.", parent=app)
            return
        sys_p = sys_prompt_box.get("1.0", "end").strip()
        work_p = worker_prompt_box.get("1.0", "end").strip()
        fields: dict[str, Any] = {
            "instructions": instr_box.get("1.0", "end").strip(),
            "system_prompt": sys_p,
            "worker_prompt": work_p,
        }
        if title_e.get().strip():
            fields["title"] = title_e.get().strip()
        if agent_role_e.get().strip():
            fields["agent_role"] = agent_role_e.get().strip()
        if agent_goal_e.get().strip():
            fields["agent_goal"] = agent_goal_e.get().strip()
        try:
            o_raw = order_e.get().strip()
            if o_raw != "":
                fields["order"] = int(float(o_raw))
        except ValueError:
            messagebox.showerror("Save", "Order must be a number.", parent=app)
            return
        try:
            wfg.update_node(state["graph"], sid, **fields)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Save", str(e), parent=app)
            return
        aid = (node.get("agent_id") or "").strip()
        if aid and node.get("type") in ("agent", "role", "worker", "ceo"):
            ag = agent_storage.get_agent(aid)
            if ag:
                if title_e.get().strip():
                    ag["name"] = title_e.get().strip()
                if agent_role_e.get().strip():
                    ag["role"] = agent_role_e.get().strip()
                if agent_goal_e.get().strip():
                    ag["goal"] = agent_goal_e.get().strip()
                if instr_box.get("1.0", "end").strip():
                    ag["backstory"] = instr_box.get("1.0", "end").strip()
                ag["system_prompt"] = sys_p
                ag["worker_prompt"] = work_p
                ag["llm_model"] = edit_llm_model.get().strip()
                ag["llm_base_url"] = edit_llm_base.get().strip()
                key = edit_llm_key.get().strip()
                if key:
                    ag["llm_api_key"] = key
                agent_storage.save_agent(ag)
        state["graph"] = wfg.get_active_graph()
        refresh_structure()
        app.set_status("Organisation node saved", toast=True)
        try:
            save_status.configure(
                text="✓ Saved", text_color=_THEME_UI.get("success", _HC_LABEL)
            )
        except Exception:  # noqa: BLE001
            pass

    def delete_selected() -> None:
        # Prefer multi-select if any boxes ticked
        if state.get("checked_ids"):
            bulk_delete()
            return
        sid = state.get("selected_id")
        if not sid:
            messagebox.showinfo("Remove", "Select or tick a worker first.", parent=app)
            return
        node = wfg.get_node(state["graph"], sid)
        if not node:
            return

        def _done() -> None:
            state["graph"] = wfg.get_active_graph()
            state["selected_id"] = None
            refresh_structure()
            clear_form()

        confirm_remove_worker(app, node, state["graph"], on_removed=_done)

    def open_config_selected() -> None:
        sid = state.get("selected_id")
        if not sid:
            messagebox.showinfo("Configure", "Select a worker first.", parent=app)
            return
        node = wfg.get_node(state["graph"], sid)
        if node:
            open_worker_config(app, node, state["graph"], on_saved=_after_save)

    def open_inspector_selected() -> None:
        sid = state.get("selected_id")
        node = wfg.get_node(state["graph"], sid) if sid else None
        open_worker_inspector(app, node=node)

    # Pinned footer on the RIGHT column (not inside scroll) so Save is always visible
    save_bar = ctk.CTkFrame(
        right,
        fg_color=_THEME_UI.get("top_bg", ("#f3f4f6", "#161a22")),
        corner_radius=10,
        border_width=1,
        border_color=_THEME_UI.get("top_border", ("#6b7280", "#4b5563")),
        height=52,
    )
    save_bar.grid(row=2, column=0, sticky="ew", padx=6, pady=(4, 8))
    save_bar.grid_propagate(False)
    ctk.CTkButton(
        save_bar,
        text="💾 Save",
        width=90,
        height=36,
        command=save_selected,
        **style_chrome_button(primary=True),
    ).pack(side="left", padx=6, pady=8)
    ctk.CTkButton(
        save_bar,
        text="⚙ Config",
        width=80,
        height=36,
        command=open_config_selected,
        **style_chrome_button(),
    ).pack(side="left", padx=2, pady=8)
    ctk.CTkButton(
        save_bar,
        text="🔍 Inspect",
        width=80,
        height=36,
        command=open_inspector_selected,
        **style_chrome_button(),
    ).pack(side="left", padx=2, pady=8)
    ctk.CTkButton(
        save_bar,
        text="Remove",
        width=72,
        height=36,
        fg_color=("#dc2626", "#7f1d1d"),
        hover_color=("#991b1b", "#450a0a"),
        command=delete_selected,
    ).pack(side="left", padx=2, pady=8)
    save_status = ctk.CTkLabel(
        save_bar,
        text="Select a worker → edit → Save",
        text_color=_HC_MUTED,
        font=ctk.CTkFont(size=11),
    )
    save_status.pack(side="left", padx=6)

    # Wire details-section Save (defined before save_selected existed)
    try:
        details_save_btn.configure(command=save_selected)
        details_cfg_btn.configure(command=open_config_selected)
    except Exception:  # noqa: BLE001
        pass

    # --- Whole-panel collapse / expand ---
    def apply_panel_layout() -> None:
        expanded = bool(state.get("panel_expanded", True))
        if expanded:
            try:
                collapsed_bar.grid_forget()
            except Exception:  # noqa: BLE001
                pass
            expanded_body.grid(row=1, column=0, sticky="nsew")
            save_bar.grid(row=2, column=0, sticky="ew", padx=6, pady=(4, 8))
            root.grid_columnconfigure(1, weight=2, minsize=300)
            panel_title.configure(text="Org panel")
            panel_hint.configure(text="orgs · workers · details · Save at bottom")
            collapse_btn.configure(text="Collapse ›")
        else:
            try:
                expanded_body.grid_forget()
            except Exception:  # noqa: BLE001
                pass
            try:
                save_bar.grid_forget()
            except Exception:  # noqa: BLE001
                pass
            collapsed_bar.grid(row=1, column=0, sticky="ns", padx=2, pady=4)
            root.grid_columnconfigure(1, weight=0, minsize=48)
            panel_title.configure(text="")
            panel_hint.configure(text="")
            collapse_btn.configure(text="‹ Expand")

    def toggle_panel() -> None:
        state["panel_expanded"] = not bool(state.get("panel_expanded", True))
        apply_panel_layout()

    collapse_btn = ctk.CTkButton(
        panel_hdr,
        text="Collapse ›",
        width=96,
        height=28,
        command=toggle_panel,
        **style_chrome_button(),
    )
    collapse_btn.pack(side="right", padx=4)

    ctk.CTkButton(
        collapsed_bar,
        text="‹\nE\nx\np\na\nn\nd",
        width=36,
        height=160,
        command=toggle_panel,
        **style_chrome_button(),
    ).pack(pady=8)

    apply_panel_layout()

    # Initial paint
    refresh_structure()
