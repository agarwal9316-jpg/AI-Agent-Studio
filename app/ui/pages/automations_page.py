"""Automations workspace — list / create / edit / enable / Run now / open last chat."""

from __future__ import annotations

import threading
import tkinter.messagebox as messagebox
from typing import TYPE_CHECKING, Any

import customtkinter as ctk

from app.ui.themes import UI as _THEME_UI

_HC_MUTED = _THEME_UI["muted"]
_HC_LABEL = _THEME_UI["label"]

if TYPE_CHECKING:
    from app.ui.app_window import AppWindow

_KIND_LABELS = {
    "hourly": "Hourly",
    "daily": "Daily",
    "weekday": "Weekdays (Mon–Fri)",
    "interval": "Every N minutes",
}


def page_automations(app: "AppWindow") -> None:
    from app.core.services.chat import automations_store as aus
    from app.ui.themes import style_chrome_button, style_entry

    root = ctk.CTkFrame(app.content, fg_color="transparent")
    root.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
    root.grid_columnconfigure(0, weight=0, minsize=280)
    root.grid_columnconfigure(1, weight=1)
    root.grid_rowconfigure(1, weight=1)

    app._page_header(
        root,
        "Automations",
        "Schedule prompts on a recurring cadence. Each run opens a linked chat with the result. "
        "Separate from Company Schedule (org agent tasks).",
    )

    # ── left: search + list ──────────────────────────────────────────────
    left = ctk.CTkFrame(
        root,
        fg_color=_THEME_UI.get("top_bg", ("#f3f4f6", "#161a22")),
        corner_radius=10,
        border_width=1,
        border_color=_THEME_UI.get("top_border", ("#6b7280", "#4b5563")),
        width=300,
    )
    left.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
    left.grid_propagate(False)
    left.grid_columnconfigure(0, weight=1)
    left.grid_rowconfigure(2, weight=1)

    search_var = ctk.StringVar(value="")
    search_row = ctk.CTkFrame(left, fg_color="transparent")
    search_row.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
    search_row.grid_columnconfigure(0, weight=1)
    search_entry = ctk.CTkEntry(
        search_row,
        textvariable=search_var,
        placeholder_text="Search automations…",
        **style_entry(),
    )
    search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 4))

    btn_row = ctk.CTkFrame(left, fg_color="transparent")
    btn_row.grid(row=1, column=0, sticky="ew", padx=8, pady=4)

    list_scroll = ctk.CTkScrollableFrame(left, fg_color="transparent")
    list_scroll.grid(row=2, column=0, sticky="nsew", padx=4, pady=(0, 8))

    # ── right: editor ────────────────────────────────────────────────────
    right = ctk.CTkFrame(
        root,
        fg_color=_THEME_UI.get("top_bg", ("#f3f4f6", "#161a22")),
        corner_radius=10,
        border_width=1,
        border_color=_THEME_UI.get("top_border", ("#6b7280", "#4b5563")),
    )
    right.grid(row=1, column=1, sticky="nsew")
    right.grid_columnconfigure(0, weight=1)
    right.grid_rowconfigure(3, weight=1)

    name_var = ctk.StringVar(value="")
    name_entry = ctk.CTkEntry(
        right,
        textvariable=name_var,
        placeholder_text="Automation name",
        height=36,
        font=ctk.CTkFont(size=15, weight="bold"),
        **style_entry(),
    )
    name_entry.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))

    sched_row = ctk.CTkFrame(right, fg_color="transparent")
    sched_row.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 6))
    sched_row.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(sched_row, text="Schedule", text_color=_HC_MUTED, width=72).grid(
        row=0, column=0, sticky="w", padx=(0, 6)
    )
    kind_var = ctk.StringVar(value="Daily")
    kind_menu = ctk.CTkOptionMenu(
        sched_row,
        variable=kind_var,
        values=list(_KIND_LABELS.values()),
        width=180,
    )
    kind_menu.grid(row=0, column=1, sticky="w", padx=(0, 8))

    ctk.CTkLabel(sched_row, text="Hour", text_color=_HC_MUTED, width=40).grid(
        row=0, column=2, sticky="w"
    )
    hour_var = ctk.StringVar(value="9")
    hour_entry = ctk.CTkEntry(sched_row, textvariable=hour_var, width=48, **style_entry())
    hour_entry.grid(row=0, column=3, sticky="w", padx=(4, 8))

    ctk.CTkLabel(sched_row, text="Min", text_color=_HC_MUTED, width=32).grid(
        row=0, column=4, sticky="w"
    )
    minute_var = ctk.StringVar(value="0")
    minute_entry = ctk.CTkEntry(sched_row, textvariable=minute_var, width=48, **style_entry())
    minute_entry.grid(row=0, column=5, sticky="w", padx=(4, 8))

    ctk.CTkLabel(sched_row, text="Every N min", text_color=_HC_MUTED).grid(
        row=0, column=6, sticky="w"
    )
    interval_var = ctk.StringVar(value="60")
    interval_entry = ctk.CTkEntry(
        sched_row, textvariable=interval_var, width=56, **style_entry()
    )
    interval_entry.grid(row=0, column=7, sticky="w", padx=(4, 0))

    toolbar = ctk.CTkFrame(right, fg_color="transparent")
    toolbar.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 6))

    prompt_box = ctk.CTkTextbox(right, wrap="word", font=ctk.CTkFont(size=14))
    prompt_box.grid(row=3, column=0, sticky="nsew", padx=12, pady=(0, 6))

    meta_l = ctk.CTkLabel(right, text="", text_color=_HC_MUTED, anchor="w", justify="left")
    meta_l.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 4))

    status_l = ctk.CTkLabel(
        right, text="Select or create an automation", text_color=_HC_MUTED, anchor="w"
    )
    status_l.grid(row=5, column=0, sticky="ew", padx=12, pady=(0, 10))

    state: dict[str, Any] = {"id": None, "dirty": False, "enabled": True}

    def _kind_key_from_label(label: str) -> str:
        for k, v in _KIND_LABELS.items():
            if v == label:
                return k
        return "daily"

    def _set_status(msg: str, *, ok: bool = True) -> None:
        color = _THEME_UI.get("success", _HC_LABEL) if ok else ("tomato", "#f87171")
        status_l.configure(text=msg, text_color=color)

    def _mark_dirty(*_a: Any) -> None:
        if state["id"]:
            state["dirty"] = True

    name_var.trace_add("write", _mark_dirty)
    prompt_box.bind("<KeyRelease>", _mark_dirty)
    for v in (hour_var, minute_var, interval_var, kind_var):
        try:
            v.trace_add("write", _mark_dirty)
        except Exception:  # noqa: BLE001
            pass

    def _parse_int(s: str, default: int, lo: int, hi: int) -> int:
        try:
            n = int(str(s).strip())
        except (TypeError, ValueError):
            n = default
        return max(lo, min(hi, n))

    def _meta_text(item: dict[str, Any] | None) -> str:
        if not item:
            return ""
        bits = [
            f"Schedule: {aus.schedule_label(item)}",
            f"Enabled: {'yes' if item.get('enabled') else 'no'}",
            f"Next: {item.get('next_run') or '—'}",
            f"Last: {item.get('last_run') or 'never'}",
        ]
        if item.get("last_status"):
            bits.append(f"Last status: {item.get('last_status')}")
        if item.get("last_error"):
            bits.append(f"Error: {str(item.get('last_error'))[:120]}")
        if item.get("last_chat_id"):
            bits.append(f"Last chat: {str(item.get('last_chat_id'))[:8]}…")
        bits.append(f"Runs: {item.get('run_count') or 0}")
        return "  ·  ".join(bits)

    def _load_into_editor(item: dict[str, Any] | None) -> None:
        state["dirty"] = False
        if not item:
            state["id"] = None
            state["enabled"] = True
            name_var.set("")
            kind_var.set(_KIND_LABELS["daily"])
            hour_var.set("9")
            minute_var.set("0")
            interval_var.set("60")
            prompt_box.delete("1.0", "end")
            meta_l.configure(text="")
            _set_status("Select or create an automation")
            return
        state["id"] = item["id"]
        state["enabled"] = bool(item.get("enabled", True))
        name_var.set(item.get("name") or "")
        kind = str(item.get("schedule_kind") or "daily")
        kind_var.set(_KIND_LABELS.get(kind, _KIND_LABELS["daily"]))
        hour_var.set(str(int(item.get("hour") if item.get("hour") is not None else 9)))
        minute_var.set(str(int(item.get("minute") or 0)))
        interval_var.set(str(int(item.get("interval_minutes") or 60)))
        prompt_box.delete("1.0", "end")
        prompt_box.insert("1.0", item.get("prompt") or "")
        meta_l.configure(text=_meta_text(item))
        en = "ON" if item.get("enabled") else "OFF"
        _set_status(f"Loaded · {en}")

    def _refresh_list() -> None:
        for w in list_scroll.winfo_children():
            w.destroy()
        q = search_var.get()
        items = aus.list_automations(query=q)
        if not items:
            ctk.CTkLabel(
                list_scroll,
                text="No automations yet.\nClick New to schedule a prompt.",
                text_color=_HC_MUTED,
                justify="left",
            ).pack(anchor="w", padx=8, pady=8)
            return
        for item in items:
            row = ctk.CTkFrame(list_scroll, fg_color="transparent")
            row.pack(fill="x", padx=4, pady=2)
            en = "●" if item.get("enabled") else "○"
            st = item.get("last_status") or ""
            badge = f" [{st}]" if st else ""
            label = f"{en} {item.get('name') or 'Untitled'}{badge}"
            preview = aus.schedule_label(item)

            def _sel(i=item):
                _load_into_editor(aus.get_automation(i["id"]) or i)

            b = ctk.CTkButton(
                row,
                text=label[:48],
                anchor="w",
                command=_sel,
                **style_chrome_button(),
            )
            b.pack(fill="x")
            ctk.CTkLabel(row, text=preview, text_color=_HC_MUTED, anchor="w", font=ctk.CTkFont(size=11)).pack(
                fill="x", padx=6
            )

    def _new() -> None:
        item = aus.create_automation(
            name="New automation",
            prompt="",
            schedule_kind="daily",
            hour=9,
            minute=0,
        )
        _refresh_list()
        _load_into_editor(item)
        _set_status("Created — edit the prompt and Save")
        try:
            app.set_status("Automation created", toast=True)
        except Exception:  # noqa: BLE001
            pass

    def _collect_fields() -> dict[str, Any]:
        return {
            "name": name_var.get().strip() or "Untitled",
            "prompt": prompt_box.get("1.0", "end-1c"),
            "schedule_kind": _kind_key_from_label(kind_var.get()),
            "hour": _parse_int(hour_var.get(), 9, 0, 23),
            "minute": _parse_int(minute_var.get(), 0, 0, 59),
            "interval_minutes": _parse_int(interval_var.get(), 60, 1, 10080),
        }

    def _save() -> None:
        nid = state.get("id")
        fields = _collect_fields()
        if not nid:
            item = aus.create_automation(**fields, enabled=True)
            state["id"] = item["id"]
        else:
            item = aus.update_automation(nid, **fields)
            if item is None:
                _set_status("Save failed — automation missing", ok=False)
                return
        state["dirty"] = False
        _refresh_list()
        _load_into_editor(item)
        _set_status("Saved")
        try:
            app.set_status("Automation saved", toast=True)
        except Exception:  # noqa: BLE001
            pass

    def _toggle_enabled() -> None:
        nid = state.get("id")
        if not nid:
            _set_status("Select an automation first", ok=False)
            return
        cur = aus.get_automation(nid)
        if not cur:
            _set_status("Missing automation", ok=False)
            return
        item = aus.set_enabled(nid, not bool(cur.get("enabled")))
        _refresh_list()
        _load_into_editor(item)
        _set_status("Enabled" if item and item.get("enabled") else "Disabled")

    def _delete() -> None:
        nid = state.get("id")
        if not nid:
            return
        cur = aus.get_automation(nid)
        name = (cur or {}).get("name") or "this automation"
        if not messagebox.askyesno("Delete automation", f"Delete “{name}”?", parent=app):
            return
        aus.delete_automation(nid)
        state["id"] = None
        _refresh_list()
        _load_into_editor(None)
        _set_status("Deleted")

    def _open_last_chat() -> None:
        nid = state.get("id")
        if not nid:
            _set_status("Select an automation first", ok=False)
            return
        cur = aus.get_automation(nid)
        cid = str((cur or {}).get("last_chat_id") or "").strip()
        if not cid:
            _set_status("No linked chat yet — Run now first", ok=False)
            return
        try:
            from app.core.services.chat import chat_store

            chat_store.set_active_chat_id(cid)
            app._chat_state = app._load_active_chat()  # type: ignore[attr-defined]
            app.show_page("Chat")
            app.set_status("Opened automation result chat", toast=True)
        except Exception as e:  # noqa: BLE001
            _set_status(f"Could not open chat: {e}", ok=False)

    def _run_now() -> None:
        nid = state.get("id")
        if not nid:
            _set_status("Select an automation first", ok=False)
            return
        if state.get("dirty"):
            _save()
            nid = state.get("id")
        _set_status("Running…")

        def worker() -> None:
            try:
                res = aus.run_automation(str(nid), force=True)
            except Exception as e:  # noqa: BLE001
                res = {"ok": False, "error": str(e), "automation": None}

            def ui() -> None:
                if not app.winfo_exists():
                    return
                item = res.get("automation") or aus.get_automation(str(nid))
                _refresh_list()
                _load_into_editor(item)
                if res.get("ok"):
                    _set_status("Run succeeded — open last chat to view")
                    try:
                        app.set_status("Automation run OK", toast=True)
                    except Exception:  # noqa: BLE001
                        pass
                else:
                    err = str(res.get("error") or "failed")
                    _set_status(f"Run failed: {err[:140]}", ok=False)

            try:
                app.after(0, ui)
            except Exception:  # noqa: BLE001
                pass

        threading.Thread(target=worker, daemon=True, name="automation-run-now").start()

    ctk.CTkButton(btn_row, text="New", width=70, command=_new, **style_chrome_button()).pack(
        side="left", padx=(0, 4)
    )
    ctk.CTkButton(
        btn_row, text="Refresh", width=70, command=_refresh_list, **style_chrome_button()
    ).pack(side="left")

    ctk.CTkButton(toolbar, text="Save", width=80, command=_save, **style_chrome_button()).pack(
        side="left", padx=(0, 4)
    )
    ctk.CTkButton(
        toolbar, text="Enable/Disable", width=110, command=_toggle_enabled, **style_chrome_button()
    ).pack(side="left", padx=(0, 4))
    ctk.CTkButton(
        toolbar, text="Run now", width=90, command=_run_now, **style_chrome_button()
    ).pack(side="left", padx=(0, 4))
    ctk.CTkButton(
        toolbar, text="Open last chat", width=110, command=_open_last_chat, **style_chrome_button()
    ).pack(side="left", padx=(0, 4))
    ctk.CTkButton(
        toolbar, text="Delete", width=80, command=_delete, **style_chrome_button()
    ).pack(side="left", padx=(0, 4))

    def _on_search(*_a: Any) -> None:
        _refresh_list()

    search_var.trace_add("write", _on_search)
    _refresh_list()
    # Ensure ticker is up if any enabled exist
    try:
        if any(a.get("enabled") for a in aus.list_automations()):
            aus.start()
    except Exception:  # noqa: BLE001
        pass
