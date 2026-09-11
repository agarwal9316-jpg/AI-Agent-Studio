"""Notes workspace page — list / create / edit / delete / search / attach / AI rewrite."""

from __future__ import annotations

import tkinter.messagebox as messagebox
from typing import TYPE_CHECKING, Any

import customtkinter as ctk

from app.ui.themes import UI as _THEME_UI

_HC_MUTED = _THEME_UI["muted"]
_HC_LABEL = _THEME_UI["label"]

if TYPE_CHECKING:
    from app.ui.app_window import AppWindow


def page_notes(app: "AppWindow") -> None:
    from app.core.services.chat import notes_store
    from app.ui.themes import style_chrome_button, style_entry

    root = ctk.CTkFrame(app.content, fg_color="transparent")
    root.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
    root.grid_columnconfigure(0, weight=0, minsize=260)
    root.grid_columnconfigure(1, weight=1)
    root.grid_rowconfigure(1, weight=1)

    app._page_header(
        root,
        "Notes",
        "Write markdown/plain notes. Attach to Chat to inject full context on the next send.",
    )

    # ── left: search + list ──────────────────────────────────────────────
    left = ctk.CTkFrame(
        root,
        fg_color=_THEME_UI.get("top_bg", ("#f3f4f6", "#161a22")),
        corner_radius=10,
        border_width=1,
        border_color=_THEME_UI.get("top_border", ("#6b7280", "#4b5563")),
        width=280,
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
        placeholder_text="Search notes…",
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
    right.grid_rowconfigure(2, weight=1)

    title_var = ctk.StringVar(value="")
    title_entry = ctk.CTkEntry(
        right,
        textvariable=title_var,
        placeholder_text="Note title",
        height=36,
        font=ctk.CTkFont(size=15, weight="bold"),
        **style_entry(),
    )
    title_entry.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))

    toolbar = ctk.CTkFrame(right, fg_color="transparent")
    toolbar.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 6))

    body = ctk.CTkTextbox(right, wrap="word", font=ctk.CTkFont(size=14))
    body.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 6))

    status_l = ctk.CTkLabel(right, text="Select or create a note", text_color=_HC_MUTED, anchor="w")
    status_l.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 10))

    state: dict[str, Any] = {"id": None, "dirty": False}

    def _set_status(msg: str, *, ok: bool = True) -> None:
        color = _THEME_UI.get("success", _HC_LABEL) if ok else ("tomato", "#f87171")
        status_l.configure(text=msg, text_color=color)

    def _mark_dirty(*_a: Any) -> None:
        if state["id"]:
            state["dirty"] = True

    title_var.trace_add("write", _mark_dirty)
    body.bind("<KeyRelease>", _mark_dirty)

    def _load_into_editor(note: dict[str, Any] | None) -> None:
        state["dirty"] = False
        if not note:
            state["id"] = None
            title_var.set("")
            body.delete("1.0", "end")
            _set_status("Select or create a note")
            return
        state["id"] = note["id"]
        title_var.set(note.get("title") or "")
        body.delete("1.0", "end")
        body.insert("1.0", note.get("body") or "")
        state["dirty"] = False
        updated = (note.get("updated_at") or "")[:19].replace("T", " ")
        _set_status(f"Editing · updated {updated}" if updated else "Editing")

    def refresh_list() -> None:
        for w in list_scroll.winfo_children():
            w.destroy()
        q = search_var.get().strip()
        items = notes_store.list_notes(query=q)
        if not items:
            ctk.CTkLabel(
                list_scroll,
                text="No notes yet.\nClick New note.",
                text_color=_HC_MUTED,
                justify="left",
            ).pack(anchor="w", padx=8, pady=16)
            return
        for item in items:
            nid = item["id"]
            row = ctk.CTkFrame(list_scroll, fg_color="transparent")
            row.pack(fill="x", pady=2, padx=2)
            is_sel = state["id"] == nid
            label = (item.get("title") or "Untitled")[:48]
            preview = notes_store.preview_text(item, limit=60)
            btn = ctk.CTkButton(
                row,
                text=f"{'● ' if is_sel else ''}{label}\n{preview}" if preview else label,
                anchor="w",
                justify="left",
                height=52,
                command=lambda i=nid: select_note(i),
                **style_chrome_button(primary=is_sel),
            )
            btn.pack(fill="x")

    def select_note(note_id: str) -> None:
        if state["dirty"] and state["id"]:
            if not messagebox.askyesno(
                "Unsaved changes",
                "Save current note before switching?",
                parent=app,
            ):
                # discard
                pass
            else:
                save_current(silent=True)
        note = notes_store.get_note(note_id)
        _load_into_editor(note)
        refresh_list()

    def new_note() -> None:
        if state["dirty"] and state["id"]:
            if messagebox.askyesno("Unsaved changes", "Save current note first?", parent=app):
                save_current(silent=True)
        note = notes_store.create_note(title="Untitled", body="")
        _load_into_editor(note)
        refresh_list()
        title_entry.focus_set()
        _set_status("Created — type a title and body, then Save", ok=True)
        app.set_status("Note created", toast=True)

    def save_current(*, silent: bool = False) -> None:
        nid = state["id"]
        if not nid:
            # create from editor contents
            note = notes_store.create_note(
                title=title_var.get().strip() or "Untitled",
                body=body.get("1.0", "end").rstrip("\n"),
            )
            _load_into_editor(note)
            refresh_list()
            if not silent:
                _set_status("✓ Saved", ok=True)
                app.set_status("Note saved", toast=True)
            return
        updated = notes_store.update_note(
            nid,
            title=title_var.get(),
            body=body.get("1.0", "end").rstrip("\n"),
        )
        if not updated:
            _set_status("Save failed — note missing", ok=False)
            return
        state["dirty"] = False
        _load_into_editor(updated)
        refresh_list()
        if not silent:
            _set_status("✓ Saved", ok=True)
            app.set_status("Note saved", toast=True)

    def delete_current() -> None:
        nid = state["id"]
        if not nid:
            _set_status("Nothing to delete", ok=False)
            return
        title = title_var.get().strip() or "Untitled"
        if not messagebox.askyesno("Delete note", f"Delete “{title}”?", parent=app):
            return
        notes_store.delete_note(nid)
        # detach if attached
        try:
            app.detach_note_from_chat(nid)
        except Exception:  # noqa: BLE001
            pass
        _load_into_editor(None)
        refresh_list()
        _set_status("Deleted", ok=True)
        app.set_status("Note deleted", toast=True)

    def attach_current() -> None:
        nid = state["id"]
        if not nid:
            # save first so there is an id
            save_current(silent=True)
            nid = state["id"]
        if not nid:
            _set_status("Create a note first", ok=False)
            return
        if state["dirty"]:
            save_current(silent=True)
        try:
            app.attach_note_to_chat(nid)
            title = title_var.get().strip() or "Untitled"
            _set_status(f"Attached “{title}” → Chat (next send)", ok=True)
            app.set_status(f"Note attached: {title}", toast=True)
        except Exception as e:  # noqa: BLE001
            _set_status(f"Attach failed: {e}", ok=False)

    def ai_rewrite_selected() -> None:
        try:
            selected = body.get("sel.first", "sel.last")
        except Exception:  # noqa: BLE001
            selected = ""
        if not selected.strip():
            # fallback: whole body
            selected = body.get("1.0", "end").rstrip("\n")
            if not selected.strip():
                _set_status("Select text (or write a body) to rewrite", ok=False)
                return
            use_whole = True
        else:
            use_whole = False

        _set_status("Rewriting with AI…")
        app.set_status("Notes AI rewrite…")
        app.update_idletasks()

        def do_rewrite() -> None:
            res = notes_store.rewrite_text(selected)

            def apply() -> None:
                if not res.get("ok"):
                    _set_status(str(res.get("note") or "Rewrite soft-degraded"), ok=False)
                    app.set_status(str(res.get("note") or "Rewrite soft-degraded"), toast=True)
                    return
                new_text = str(res.get("text") or "")
                if use_whole:
                    body.delete("1.0", "end")
                    body.insert("1.0", new_text)
                else:
                    try:
                        body.delete("sel.first", "sel.last")
                        body.insert("insert", new_text)
                    except Exception:  # noqa: BLE001
                        body.delete("1.0", "end")
                        body.insert("1.0", new_text)
                state["dirty"] = True
                _set_status("✓ Rewritten — Save to keep", ok=True)
                app.set_status("Note rewritten", toast=True)

            try:
                app.after(0, apply)
            except Exception:  # noqa: BLE001
                apply()

        import threading

        threading.Thread(target=do_rewrite, daemon=True).start()

    ctk.CTkButton(
        btn_row, text="＋ New", width=70, height=28, command=new_note, **style_chrome_button(primary=True)
    ).pack(side="left", padx=(0, 4))
    ctk.CTkButton(
        btn_row, text="↻", width=36, height=28, command=refresh_list, **style_chrome_button()
    ).pack(side="left")

    ctk.CTkButton(
        toolbar, text="💾 Save", width=80, height=30, command=save_current, **style_chrome_button(primary=True)
    ).pack(side="left", padx=(0, 4))
    ctk.CTkButton(
        toolbar, text="📎 Attach to chat", width=130, height=30, command=attach_current, **style_chrome_button()
    ).pack(side="left", padx=4)
    ctk.CTkButton(
        toolbar, text="✨ AI rewrite", width=110, height=30, command=ai_rewrite_selected, **style_chrome_button()
    ).pack(side="left", padx=4)
    ctk.CTkButton(
        toolbar,
        text="🗑 Delete",
        width=80,
        height=30,
        fg_color="#a33",
        hover_color="#822",
        command=delete_current,
    ).pack(side="right")

    def on_search(*_a: Any) -> None:
        refresh_list()

    search_var.trace_add("write", on_search)
    app._page_save_handler = save_current
    refresh_list()
    # If notes already exist, open the newest
    items = notes_store.list_notes()
    if items and not state["id"]:
        _load_into_editor(items[0])
        refresh_list()
