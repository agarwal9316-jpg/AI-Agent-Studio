"""Worker configuration, remove confirmation, and execution inspector dialogs."""

from __future__ import annotations

import tkinter.messagebox as messagebox
from typing import TYPE_CHECKING, Any, Callable

import customtkinter as ctk

from app.ui.themes import UI as _UI
from app.ui.themes import style_chrome_button

if TYPE_CHECKING:
    from app.ui.app_window import AppWindow

_HC_MUTED = _UI["muted"]
_HC_LABEL = _UI["label"]


def _section(parent: Any, title: str) -> ctk.CTkFrame:
    wrap = ctk.CTkFrame(parent, fg_color="transparent")
    wrap.pack(fill="x", padx=8, pady=(10, 2))
    ctk.CTkLabel(
        wrap,
        text=title,
        font=ctk.CTkFont(size=13, weight="bold"),
        text_color=_HC_LABEL,
        anchor="w",
    ).pack(fill="x")
    body = ctk.CTkFrame(wrap, fg_color=("#f8fafc", "#1e293b"), corner_radius=8)
    body.pack(fill="x", pady=(4, 0))
    return body


def open_worker_config(
    app: AppWindow,
    node: dict[str, Any],
    graph: dict[str, Any],
    *,
    on_saved: Callable[[], None] | None = None,
) -> None:
    """Full worker configuration panel with Default/override inheritance."""
    from app.services import storage as st
    from app.services import workflow_graph as wfg
    from app.services import providers as prov

    win = ctk.CTkToplevel(app)
    title = node.get("title") or "AI Worker"
    win.title(f"Configure Worker — {title}")
    win.geometry("560x720")
    win.transient(app)
    try:
        win.grab_set()
    except Exception:  # noqa: BLE001
        pass

    dirty = {"v": False}

    def mark_dirty(*_a: Any) -> None:
        dirty["v"] = True
        try:
            status_lbl.configure(text="Unsaved changes", text_color="#f59e0b")
        except Exception:  # noqa: BLE001
            pass

    scroll = ctk.CTkScrollableFrame(win, fg_color="transparent")
    scroll.pack(fill="both", expand=True, padx=8, pady=8)

    ag = st.get_agent(node.get("agent_id") or "") if node.get("agent_id") else None
    llm = st.resolve_worker_llm(node, ag)

    # --- Identity ---
    body = _section(scroll, "Identity")
    name_e = ctk.CTkEntry(body, placeholder_text="Worker name")
    name_e.pack(fill="x", padx=10, pady=(10, 4))
    name_e.insert(0, node.get("title") or "")
    name_e.bind("<KeyRelease>", mark_dirty)
    role_e = ctk.CTkEntry(body, placeholder_text="Role")
    role_e.pack(fill="x", padx=10, pady=4)
    role_e.insert(0, (ag or {}).get("role") or node.get("agent_role") or "")
    role_e.bind("<KeyRelease>", mark_dirty)
    goal_e = ctk.CTkEntry(body, placeholder_text="Standing goal")
    goal_e.pack(fill="x", padx=10, pady=(4, 10))
    goal_e.insert(0, (ag or {}).get("goal") or node.get("agent_goal") or "")
    goal_e.bind("<KeyRelease>", mark_dirty)

    enabled_var = ctk.BooleanVar(value=node.get("enabled") is not False)
    ctk.CTkCheckBox(
        body, text="Enabled", variable=enabled_var, command=mark_dirty
    ).pack(anchor="w", padx=10, pady=(0, 10))

    # --- Provider / LLM ---
    llm_body = _section(scroll, "LLM configuration (empty = Default / global Settings)")
    ctk.CTkLabel(
        llm_body,
        text=f"Effective now: {llm.get('display_provider')} · {llm.get('display_model')}",
        text_color=_HC_MUTED,
        font=ctk.CTkFont(size=11),
        wraplength=500,
        justify="left",
    ).pack(anchor="w", padx=10, pady=(8, 4))

    providers = prov.list_providers()
    prov_labels = ["Default — global Settings"] + [
        f"{p.get('name') or p.get('id')}|{p.get('id')}" for p in providers
    ]
    prov_display = [x.split("|")[0] for x in prov_labels]
    cur_pid = (ag or {}).get("llm_provider_id") or node.get("llm_provider_id") or ""
    cur_prov_label = "Default — global Settings"
    for raw in prov_labels:
        if "|" in raw and raw.split("|")[-1] == cur_pid:
            cur_prov_label = raw.split("|")[0]
            break
    prov_var = ctk.StringVar(value=cur_prov_label)
    ctk.CTkLabel(llm_body, text="Provider", text_color=_HC_LABEL, anchor="w").pack(
        anchor="w", padx=10
    )
    prov_menu = ctk.CTkOptionMenu(
        llm_body, values=prov_display, variable=prov_var, command=lambda _x: mark_dirty()
    )
    prov_menu.pack(fill="x", padx=10, pady=4)

    base_e = ctk.CTkEntry(llm_body, placeholder_text="Base URL (empty = Default)")
    base_e.pack(fill="x", padx=10, pady=4)
    base_e.insert(0, (ag or {}).get("llm_base_url") or node.get("llm_base_url") or "")
    base_e.bind("<KeyRelease>", mark_dirty)

    key_e = ctk.CTkEntry(
        llm_body,
        placeholder_text=f"API key (empty = Default)  current: {st.mask_api_key((ag or {}).get('llm_api_key') or '')}",
        show="*",
    )
    key_e.pack(fill="x", padx=10, pady=4)
    key_e.bind("<KeyRelease>", mark_dirty)

    ctk.CTkLabel(llm_body, text="Model", text_color=_HC_LABEL, anchor="w").pack(
        anchor="w", padx=10, pady=(6, 0)
    )
    model_e = ctk.CTkEntry(
        llm_body, placeholder_text="Model id (empty = Default global model)"
    )
    model_e.pack(fill="x", padx=10, pady=4)
    model_e.insert(0, (ag or {}).get("llm_model") or node.get("llm_model") or "")
    model_e.bind("<KeyRelease>", mark_dirty)

    model_list_frame = ctk.CTkFrame(llm_body, fg_color="transparent")
    model_list_frame.pack(fill="x", padx=10, pady=4)
    model_search = ctk.CTkEntry(model_list_frame, placeholder_text="Search models…")
    model_search.pack(side="left", fill="x", expand=True, padx=(0, 4))
    models_state: dict[str, list[str]] = {"all": [], "filtered": []}

    def apply_model_filter(*_a: Any) -> None:
        q = model_search.get().strip().lower()
        src = models_state["all"]
        models_state["filtered"] = [m for m in src if not q or q in m.lower()][:80]
        vals = models_state["filtered"] or ["(no models — type manually)"]
        try:
            model_pick.configure(values=vals)
            if vals and not vals[0].startswith("("):
                model_pick.set(vals[0])
        except Exception:  # noqa: BLE001
            pass

    def pick_model(m: str) -> None:
        if m.startswith("("):
            return
        model_e.delete(0, "end")
        model_e.insert(0, m)
        mark_dirty()

    model_pick = ctk.CTkOptionMenu(
        llm_body, values=["(refresh models)"], command=pick_model
    )
    model_pick.pack(fill="x", padx=10, pady=4)
    model_search.bind("<KeyRelease>", apply_model_filter)

    def refresh_models() -> None:
        # Resolve provider id
        label = prov_var.get()
        pid = ""
        for raw in prov_labels:
            if raw.split("|")[0] == label and "|" in raw:
                pid = raw.split("|")[-1]
                break
        if not pid:
            try:
                active = prov.resolve_active_llm()
                pid = str(active.get("provider_id") or "")
            except Exception:  # noqa: BLE001
                pid = ""
        if not pid:
            status_lbl.configure(
                text="Select a specific provider (or set active provider) to refresh models",
                text_color="#f59e0b",
            )
            return
        status_lbl.configure(text="Fetching models…", text_color=_HC_MUTED)
        win.update_idletasks()
        try:
            models = prov.fetch_models(pid, force=True)
            models_state["all"] = list(models)
            apply_model_filter()
            status_lbl.configure(
                text=f"Loaded {len(models)} models", text_color=_UI.get("success", _HC_LABEL)
            )
        except Exception as e:  # noqa: BLE001
            status_lbl.configure(text=f"Model fetch failed: {e}", text_color="tomato")
            messagebox.showwarning(
                "Models",
                f"Could not refresh models:\n{e}\n\nYou can still type a model id manually.",
                parent=win,
            )

    btn_row = ctk.CTkFrame(llm_body, fg_color="transparent")
    btn_row.pack(fill="x", padx=10, pady=(4, 10))
    ctk.CTkButton(
        btn_row, text="Refresh models", width=130, command=refresh_models, **style_chrome_button()
    ).pack(side="left", padx=2)

    def reset_llm_defaults() -> None:
        prov_var.set("Default — global Settings")
        base_e.delete(0, "end")
        key_e.delete(0, "end")
        model_e.delete(0, "end")
        mark_dirty()
        status_lbl.configure(text="Reset to Default (save to apply)", text_color=_HC_MUTED)

    ctk.CTkButton(
        btn_row, text="Reset to Default", width=130, command=reset_llm_defaults, **style_chrome_button()
    ).pack(side="left", padx=2)

    # Caps
    from app.core.services.misc.worker_attachments import (
        format_capabilities_line,
        model_capability_flags,
    )

    def refresh_caps(*_a: Any) -> None:
        mid = model_e.get().strip() or str(llm.get("model") or "")
        label = prov_var.get()
        pid = ""
        for raw in prov_labels:
            if raw.split("|")[0] == label and "|" in raw:
                pid = raw.split("|")[-1]
                break
        flags = model_capability_flags(mid, pid or str(llm.get("provider_id") or ""))
        caps_lbl.configure(
            text=f"Model: {mid or 'Default'}\n{format_capabilities_line(flags)}"
        )

    caps_lbl = ctk.CTkLabel(
        llm_body,
        text="Capabilities: …",
        text_color=_HC_MUTED,
        font=ctk.CTkFont(size=11),
        wraplength=500,
        justify="left",
    )
    caps_lbl.pack(anchor="w", padx=10, pady=(0, 10))
    model_e.bind("<KeyRelease>", lambda e: (mark_dirty(), refresh_caps()))
    prov_menu.configure(command=lambda _x: (mark_dirty(), refresh_caps()))
    refresh_caps()

    # --- Fallback ---
    fb_body = _section(scroll, "Fallback model (optional — never silent)")
    fb_en = ctk.BooleanVar(value=bool((ag or {}).get("fallback_enabled") or node.get("fallback_enabled")))
    ctk.CTkCheckBox(
        fb_body, text="Enable explicit fallback if primary fails", variable=fb_en, command=mark_dirty
    ).pack(anchor="w", padx=10, pady=(10, 4))
    fb_model = ctk.CTkEntry(fb_body, placeholder_text="Fallback model id")
    fb_model.pack(fill="x", padx=10, pady=4)
    fb_model.insert(0, (ag or {}).get("fallback_model") or node.get("fallback_model") or "")
    fb_model.bind("<KeyRelease>", mark_dirty)
    fb_base = ctk.CTkEntry(fb_body, placeholder_text="Fallback base URL (optional)")
    fb_base.pack(fill="x", padx=10, pady=(4, 10))
    fb_base.insert(0, (ag or {}).get("fallback_base_url") or node.get("fallback_base_url") or "")
    fb_base.bind("<KeyRelease>", mark_dirty)

    # --- Prompts ---
    sp_body = _section(scroll, "System prompt (permanent)")
    sys_box = ctk.CTkTextbox(sp_body, height=80)
    sys_box.pack(fill="x", padx=10, pady=10)
    sys_box.insert(
        "1.0",
        (ag or {}).get("system_prompt") or node.get("system_prompt") or "",
    )
    sys_box.bind("<KeyRelease>", mark_dirty)

    wp_body = _section(scroll, "Worker prompt (permanent role — not temporary tasks)")
    work_box = ctk.CTkTextbox(wp_body, height=100)
    work_box.pack(fill="x", padx=10, pady=10)
    work_box.insert(
        "1.0",
        (ag or {}).get("worker_prompt")
        or node.get("worker_prompt")
        or node.get("instructions")
        or "",
    )
    work_box.bind("<KeyRelease>", mark_dirty)

    instr_body = _section(scroll, "Standing instructions / notes")
    instr_box = ctk.CTkTextbox(instr_body, height=70)
    instr_box.pack(fill="x", padx=10, pady=10)
    instr_box.insert("1.0", node.get("instructions") or "")
    instr_box.bind("<KeyRelease>", mark_dirty)

    # --- Attachments ---
    att_body = _section(scroll, "Persistent attachments (PDF/DOCX/TXT/CSV/images/code)")
    att_list_frame = ctk.CTkFrame(att_body, fg_color="transparent")
    att_list_frame.pack(fill="x", padx=8, pady=6)
    aid = str(node.get("agent_id") or (ag or {}).get("id") or "")

    def reload_atts() -> None:
        for w in att_list_frame.winfo_children():
            w.destroy()
        ag2 = st.get_agent(aid) if aid else None
        atts2 = list((ag2 or {}).get("attachments") or [])
        if not atts2:
            ctk.CTkLabel(
                att_list_frame,
                text="No attachments yet. Images on text-only models use OCR → text.",
                text_color=_HC_MUTED,
                wraplength=480,
                justify="left",
            ).pack(anchor="w", padx=6, pady=4)
            return
        for a in atts2[:20]:
            if not isinstance(a, dict):
                continue
            row = ctk.CTkFrame(att_list_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)
            size_kb = int(a.get("size") or 0) // 1024
            ctk.CTkLabel(
                row,
                text=(
                    f"· {a.get('name') or 'file'}  |  {a.get('type') or '?'}  |  "
                    f"{size_kb} KB  |  {a.get('status') or 'pending'}"
                    + (f"  |  {a.get('chars')} chars" if a.get("chars") else "")
                ),
                text_color=_HC_LABEL,
                anchor="w",
                font=ctk.CTkFont(size=11),
            ).pack(side="left", fill="x", expand=True)

            def _rm(att_id: str = str(a.get("id") or "")) -> None:
                if not aid or not att_id:
                    return
                try:
                    from app.core.services.misc.worker_attachments import remove_attachment

                    remove_attachment(aid, att_id)
                    reload_atts()
                    mark_dirty()
                except Exception as e:  # noqa: BLE001
                    messagebox.showerror("Remove", str(e), parent=win)

            ctk.CTkButton(row, text="Remove", width=70, height=24, command=_rm).pack(
                side="right", padx=2
            )

    def add_att() -> None:
        if not aid:
            messagebox.showinfo(
                "Attachments",
                "Save/create the worker first so it has an agent profile.",
                parent=win,
            )
            return
        from tkinter import filedialog

        path = filedialog.askopenfilename(
            parent=win,
            title="Add worker attachment",
            filetypes=[
                ("All supported", "*.pdf;*.docx;*.txt;*.md;*.csv;*.json;*.py;*.png;*.jpg;*.jpeg;*.webp"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        try:
            from app.core.services.misc.worker_attachments import add_attachment_to_agent

            add_attachment_to_agent(aid, path, copy_file=True)
            reload_atts()
            mark_dirty()
            status_lbl.configure(text=f"Attached: {Path(path).name}", text_color=_HC_MUTED)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Attach", str(e), parent=win)

    from pathlib import Path

    ctk.CTkButton(
        att_body, text="+ Add attachment", command=add_att, **style_chrome_button()
    ).pack(anchor="w", padx=10, pady=(0, 8))
    reload_atts()

    # --- Tool permissions ---
    tool_body = _section(scroll, "Tool permissions")
    tp = dict((ag or {}).get("tool_permissions") or node.get("tool_permissions") or {})
    term_var = ctk.BooleanVar(value=tp.get("terminal", True) is not False)
    web_var = ctk.BooleanVar(value=tp.get("web", True) is not False)
    ctk.CTkCheckBox(
        tool_body, text="Allow terminal tools", variable=term_var, command=mark_dirty
    ).pack(anchor="w", padx=10, pady=(8, 2))
    ctk.CTkCheckBox(
        tool_body, text="Allow web search / fetch", variable=web_var, command=mark_dirty
    ).pack(anchor="w", padx=10, pady=(2, 10))

    # Footer
    foot = ctk.CTkFrame(win, fg_color="transparent")
    foot.pack(fill="x", padx=12, pady=10)
    status_lbl = ctk.CTkLabel(foot, text="Ready", text_color=_HC_MUTED)
    status_lbl.pack(side="left")

    def on_close() -> None:
        if dirty["v"]:
            if not messagebox.askyesno(
                "Unsaved changes",
                "You have unsaved changes.\n\nDiscard and close?",
                parent=win,
            ):
                return
        win.destroy()

    def save() -> None:
        label = prov_var.get()
        pid = ""
        for raw in prov_labels:
            if raw.split("|")[0] == label and "|" in raw:
                pid = raw.split("|")[-1]
                break
        fields: dict[str, Any] = {
            "title": name_e.get().strip() or title,
            "agent_role": role_e.get().strip(),
            "agent_goal": goal_e.get().strip(),
            "system_prompt": sys_box.get("1.0", "end").strip(),
            "worker_prompt": work_box.get("1.0", "end").strip(),
            "instructions": instr_box.get("1.0", "end").strip(),
            "llm_provider_id": pid,
            "llm_model": model_e.get().strip(),
            "llm_base_url": base_e.get().strip(),
            "enabled": bool(enabled_var.get()),
            "fallback_enabled": bool(fb_en.get()),
            "fallback_model": fb_model.get().strip(),
            "fallback_base_url": fb_base.get().strip(),
            "tool_permissions": {
                "terminal": bool(term_var.get()),
                "web": bool(web_var.get()),
            },
        }
        key = key_e.get().strip()
        if key:
            fields["llm_api_key"] = key
        try:
            wfg.update_node(graph, str(node.get("id")), **fields)
            # Sync tool permissions onto agent profile
            aid2 = str(node.get("agent_id") or "")
            if aid2:
                ag2 = st.get_agent(aid2)
                if ag2:
                    ag2["tool_permissions"] = fields["tool_permissions"]
                    ag2["fallback_enabled"] = fields["fallback_enabled"]
                    ag2["fallback_model"] = fields["fallback_model"]
                    ag2["fallback_base_url"] = fields["fallback_base_url"]
                    st.save_agent(ag2)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Save", str(e), parent=win)
            return
        dirty["v"] = False
        status_lbl.configure(text="✓ Saved", text_color=_UI.get("success", _HC_LABEL))
        if on_saved:
            try:
                on_saved()
            except Exception:  # noqa: BLE001
                pass
        try:
            app.set_status(f"Worker saved: {fields['title']}", toast=True)
        except Exception:  # noqa: BLE001
            pass

    ctk.CTkButton(
        foot, text="Save", width=100, command=save, **style_chrome_button(primary=True)
    ).pack(side="right", padx=4)
    ctk.CTkButton(foot, text="Close", width=90, command=on_close).pack(side="right", padx=4)
    win.protocol("WM_DELETE_WINDOW", on_close)


def confirm_remove_worker(
    app: AppWindow,
    node: dict[str, Any],
    graph: dict[str, Any],
    *,
    on_removed: Callable[[], None] | None = None,
) -> None:
    """Remove worker with confirmation and child handling."""
    from app.services import workflow_graph as wfg

    if node.get("type") == "ceo":
        messagebox.showinfo(
            "CEO protected",
            "The CEO root cannot be removed. Create a new organisation chart instead.",
            parent=app,
        )
        return

    kids = wfg.children_of(graph, str(node.get("id") or ""))
    name = node.get("title") or "Worker"
    if not kids:
        if not messagebox.askyesno(
            "Remove AI Worker",
            f"Remove AI Worker “{name}”?\n\n"
            "Linked agent profile and credentials are kept (not deleted).",
            parent=app,
        ):
            return
        res = wfg.delete_node(graph, str(node["id"]), children_mode="delete")
        if not res.get("ok"):
            messagebox.showerror("Remove", res.get("error") or "Failed", parent=app)
            return
        if on_removed:
            on_removed()
        return

    win = ctk.CTkToplevel(app)
    win.title("Remove AI Worker")
    win.geometry("440x280")
    win.transient(app)
    ctk.CTkLabel(
        win,
        text=f"“{name}” has {len(kids)} child worker(s).\nWhat should happen to them?",
        font=ctk.CTkFont(size=14, weight="bold"),
        text_color=_HC_LABEL,
        justify="left",
    ).pack(anchor="w", padx=16, pady=(16, 8))
    mode = ctk.StringVar(value="promote")
    ctk.CTkRadioButton(
        win, text="Remove worker and promote children to parent", variable=mode, value="promote"
    ).pack(anchor="w", padx=20, pady=4)
    ctk.CTkRadioButton(
        win, text="Remove worker and all descendants", variable=mode, value="delete"
    ).pack(anchor="w", padx=20, pady=4)
    ctk.CTkLabel(
        win,
        text="Shared agent profiles, files, and API keys are never deleted.",
        text_color=_HC_MUTED,
        wraplength=400,
        justify="left",
    ).pack(anchor="w", padx=16, pady=8)

    def do_remove() -> None:
        res = wfg.delete_node(
            graph, str(node["id"]), children_mode=mode.get() or "promote"
        )
        if not res.get("ok"):
            messagebox.showerror("Remove", res.get("error") or "Failed", parent=win)
            return
        win.destroy()
        if on_removed:
            on_removed()
        try:
            app.set_status(f"Removed worker: {name}", toast=True)
        except Exception:  # noqa: BLE001
            pass

    row = ctk.CTkFrame(win, fg_color="transparent")
    row.pack(fill="x", padx=16, pady=16)
    ctk.CTkButton(
        row,
        text="Remove AI Worker",
        fg_color=("#dc2626", "#7f1d1d"),
        hover_color=("#991b1b", "#450a0a"),
        command=do_remove,
    ).pack(side="left", padx=4)
    ctk.CTkButton(row, text="Cancel", command=win.destroy, width=90).pack(side="left", padx=4)


def open_move_worker(
    app: AppWindow,
    node: dict[str, Any],
    graph: dict[str, Any],
    *,
    on_moved: Callable[[], None] | None = None,
) -> None:
    """Move worker under a new parent (reparent) with circular-hierarchy protection."""
    from app.services import workflow_graph as wfg

    if node.get("type") == "ceo":
        messagebox.showinfo("Move", "CEO root cannot be moved.", parent=app)
        return

    win = ctk.CTkToplevel(app)
    win.title(f"Move — {node.get('title')}")
    win.geometry("420x360")
    win.transient(app)
    ctk.CTkLabel(
        win,
        text=f"Move “{node.get('title')}” under:",
        font=ctk.CTkFont(size=14, weight="bold"),
        text_color=_HC_LABEL,
    ).pack(anchor="w", padx=14, pady=(14, 6))

    options: list[str] = []
    id_by_label: dict[str, str] = {}
    for n in wfg.walk_tree(graph):
        nid = str(n.get("id") or "")
        if nid == str(node.get("id")):
            continue
        if nid in set(wfg.descendants_of(graph, str(node.get("id")))):
            continue  # cannot move under own descendant
        pad = "  " * int(n.get("_depth") or 0)
        label = f"{pad}{n.get('title')} ({n.get('type')})"
        # disambiguate
        base = label
        k = 1
        while label in id_by_label:
            k += 1
            label = f"{base} #{k}"
        id_by_label[label] = nid
        options.append(label)
    if not options:
        ctk.CTkLabel(win, text="No valid parent targets.", text_color=_HC_MUTED).pack(
            padx=14, pady=20
        )
        ctk.CTkButton(win, text="Close", command=win.destroy).pack(pady=8)
        return

    var = ctk.StringVar(value=options[0])
    ctk.CTkOptionMenu(win, values=options, variable=var, width=360).pack(
        padx=14, pady=8, fill="x"
    )

    def do_move() -> None:
        pid = id_by_label.get(var.get())
        try:
            wfg.reparent_node(graph, str(node.get("id")), pid)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Move", str(e), parent=win)
            return
        win.destroy()
        if on_moved:
            on_moved()
        try:
            app.set_status(f"Moved {node.get('title')}", toast=True)
        except Exception:  # noqa: BLE001
            pass

    row = ctk.CTkFrame(win, fg_color="transparent")
    row.pack(fill="x", padx=14, pady=16)
    ctk.CTkButton(
        row, text="Move worker", command=do_move, **style_chrome_button(primary=True)
    ).pack(side="left", padx=4)
    ctk.CTkButton(row, text="Cancel", command=win.destroy, width=90).pack(side="left")


def open_worker_inspector(
    app: AppWindow,
    task: dict[str, Any] | None = None,
    *,
    node: dict[str, Any] | None = None,
    summary_only: bool = False,
) -> None:
    """Worker execution inspector — summary or full structured view."""
    from app.services import company_store as company
    from app.core.services.company.org_execution import format_inspector_text, worker_inspector_payload

    win = ctk.CTkToplevel(app)
    wname = (node or {}).get("title") or (task or {}).get("agent_name") or "Worker"
    win.title(f"Worker Inspector — {wname}")
    win.geometry("640x720")
    win.transient(app)

    # Prefer latest assignment for this org node
    if task is None and node:
        nid = str(node.get("id") or "")
        for t in company.list_work_tasks():
            if str(t.get("org_node_id") or "") == nid:
                task = t
                break

    if not task:
        ctk.CTkLabel(
            win,
            text=(
                f"Worker: {wname}\n\n"
                "No assignment/execution history yet.\n"
                "Run a Team goal or Org pipeline to populate the inspector."
            ),
            text_color=_HC_MUTED,
            justify="left",
            wraplength=580,
        ).pack(anchor="w", padx=20, pady=20)
        ctk.CTkButton(win, text="Close", command=win.destroy, width=100).pack(pady=10)
        return

    payload = worker_inspector_payload(task)
    head = ctk.CTkFrame(win, fg_color=("#f1f5f9", "#1e293b"), corner_radius=10)
    head.pack(fill="x", padx=12, pady=12)
    status = payload.get("status") or "?"
    ctk.CTkLabel(
        head,
        text=f"{payload.get('worker')}  ·  ● {status}",
        font=ctk.CTkFont(size=16, weight="bold"),
        text_color=_HC_LABEL,
        anchor="w",
    ).pack(fill="x", padx=12, pady=(10, 2))
    ctk.CTkLabel(
        head,
        text=(
            f"Goal: {payload.get('current_goal') or '—'}\n"
            f"Assignment: {(payload.get('current_assignment') or '—')[:200]}\n"
            f"Assigned by: {payload.get('assigned_by') or '—'}"
        ),
        text_color=_HC_MUTED,
        justify="left",
        anchor="w",
        wraplength=580,
    ).pack(fill="x", padx=12, pady=(0, 10))

    if summary_only:
        ctk.CTkButton(
            win,
            text="View full execution",
            command=lambda: (win.destroy(), open_worker_inspector(app, task=task, node=node)),
            **style_chrome_button(primary=True),
        ).pack(pady=8)
        return

    scroll = ctk.CTkScrollableFrame(win, fg_color="transparent")
    scroll.pack(fill="both", expand=True, padx=8, pady=4)
    text = ctk.CTkTextbox(scroll, height=520, wrap="word")
    text.pack(fill="both", expand=True, padx=4, pady=4)
    text.insert("1.0", format_inspector_text(payload))
    # Extra sections
    sec = payload.get("sections") or {}
    extra_parts = []
    for key, label in (
        ("activity", "ACTIVITY TIMELINE"),
        ("tools", "TOOLS USED"),
        ("findings", "FINDINGS"),
        ("revisions", "REVISIONS"),
        ("runtime_llm", "RUNTIME LLM"),
    ):
        val = sec.get(key)
        if val:
            import json

            try:
                blob = json.dumps(val, indent=2, default=str)[:4000]
            except Exception:  # noqa: BLE001
                blob = str(val)[:4000]
            extra_parts.append(f"\n## {label}\n{blob}")
    if extra_parts:
        text.insert("end", "\n".join(extra_parts))
    text.configure(state="disabled")
    ctk.CTkButton(win, text="Close", command=win.destroy, width=100).pack(pady=8)
