"""Workspace Channels page — shared user + model timeline (P1.2)."""

from __future__ import annotations

import threading
import tkinter.messagebox as messagebox
import tkinter.simpledialog as simpledialog
from typing import TYPE_CHECKING, Any

import customtkinter as ctk

from app.ui.themes import UI as _THEME_UI

_HC_MUTED = _THEME_UI["muted"]
_HC_LABEL = _THEME_UI["label"]

if TYPE_CHECKING:
    from app.ui.app_window import AppWindow


def page_channels(app: "AppWindow") -> None:
    from app.core.services.chat import channels_store as cs
    from app.ui.themes import style_chrome_button, style_entry, style_option_menu

    root = ctk.CTkFrame(app.content, fg_color="transparent")
    root.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
    root.grid_columnconfigure(0, weight=0, minsize=240)
    root.grid_columnconfigure(1, weight=1)
    root.grid_rowconfigure(1, weight=1)

    app._page_header(
        root,
        "Channels",
        "Shared timeline — post as you, @mention or pick a model to reply. Soft pins · reply threads. "
        "(Org Team goal channels stay under Team.)",
    )

    # ── left: channel list ───────────────────────────────────────────────
    left = ctk.CTkFrame(
        root,
        fg_color=_THEME_UI.get("top_bg", ("#f3f4f6", "#161a22")),
        corner_radius=10,
        border_width=1,
        border_color=_THEME_UI.get("top_border", ("#6b7280", "#4b5563")),
        width=260,
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
        placeholder_text="Search channels…",
        **style_entry(),
    )
    search_entry.grid(row=0, column=0, sticky="ew")

    btn_row = ctk.CTkFrame(left, fg_color="transparent")
    btn_row.grid(row=1, column=0, sticky="ew", padx=8, pady=4)

    list_scroll = ctk.CTkScrollableFrame(left, fg_color="transparent")
    list_scroll.grid(row=2, column=0, sticky="nsew", padx=4, pady=(0, 8))

    # ── right: timeline + composer ───────────────────────────────────────
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

    header = ctk.CTkFrame(right, fg_color="transparent")
    header.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
    header.grid_columnconfigure(0, weight=1)

    title_l = ctk.CTkLabel(
        header,
        text="Select or create a channel",
        font=ctk.CTkFont(size=16, weight="bold"),
        text_color=_HC_LABEL,
        anchor="w",
    )
    title_l.grid(row=0, column=0, sticky="ew")

    desc_l = ctk.CTkLabel(header, text="", text_color=_HC_MUTED, anchor="w")
    desc_l.grid(row=1, column=0, sticky="ew")

    pins_bar = ctk.CTkFrame(right, fg_color="transparent")
    pins_bar.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 4))

    timeline = ctk.CTkScrollableFrame(right, fg_color="transparent")
    timeline.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 4))

    composer = ctk.CTkFrame(right, fg_color="transparent")
    composer.grid(row=3, column=0, sticky="ew", padx=12, pady=(4, 10))
    composer.grid_columnconfigure(0, weight=1)

    reply_hint = ctk.CTkLabel(composer, text="", text_color=_HC_MUTED, anchor="w")
    reply_hint.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 2))

    input_box = ctk.CTkTextbox(composer, height=72, wrap="word", font=ctk.CTkFont(size=13))
    input_box.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(0, 6))

    model_choices = cs.list_model_choices()
    if not model_choices:
        model_choices = ["(no models)"]
    model_var = ctk.StringVar(value=model_choices[0])

    model_row = ctk.CTkFrame(composer, fg_color="transparent")
    model_row.grid(row=2, column=0, columnspan=4, sticky="ew")
    model_row.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(model_row, text="Model", text_color=_HC_MUTED, width=48).pack(side="left")
    model_menu = ctk.CTkOptionMenu(
        model_row,
        values=model_choices,
        variable=model_var,
        width=220,
        **style_option_menu(),
    )
    model_menu.pack(side="left", padx=(0, 8))

    status_l = ctk.CTkLabel(composer, text="", text_color=_HC_MUTED, anchor="w")
    status_l.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(6, 0))

    state: dict[str, Any] = {
        "id": None,
        "reply_to": None,
        "parent_id": None,
        "busy": False,
    }

    def _set_status(msg: str, *, ok: bool = True) -> None:
        color = _THEME_UI.get("success", _HC_LABEL) if ok else ("tomato", "#f87171")
        status_l.configure(text=msg, text_color=color)

    def _clear_reply_target() -> None:
        state["reply_to"] = None
        state["parent_id"] = None
        reply_hint.configure(text="")

    def _set_reply_target(msg: dict[str, Any], *, as_thread: bool = True) -> None:
        mid = msg.get("id")
        state["reply_to"] = mid
        state["parent_id"] = mid if as_thread else None
        who = msg.get("author") or msg.get("role") or "?"
        preview = cs.preview_text(str(msg.get("content") or ""), limit=60)
        reply_hint.configure(text=f"↩ Replying to {who}: {preview}   (Esc / Cancel reply to clear)")

    def refresh_list() -> None:
        for w in list_scroll.winfo_children():
            w.destroy()
        items = cs.list_channels(query=search_var.get())
        if not items:
            ctk.CTkLabel(
                list_scroll,
                text="No channels yet.\nClick New channel.",
                text_color=_HC_MUTED,
                justify="left",
            ).pack(anchor="w", padx=8, pady=16)
            return
        for item in items:
            cid = item["id"]
            row = ctk.CTkFrame(list_scroll, fg_color="transparent")
            row.pack(fill="x", pady=2, padx=2)
            is_sel = state["id"] == cid
            label = f"#{item.get('name') or 'channel'}"
            count = int(item.get("message_count") or 0)
            prev = item.get("last_preview") or ""
            text = f"{'● ' if is_sel else ''}{label} · {count}\n{prev}" if prev else f"{'● ' if is_sel else ''}{label} · {count}"
            btn = ctk.CTkButton(
                row,
                text=text[:120],
                anchor="w",
                justify="left",
                height=52,
                command=lambda i=cid: select_channel(i),
                **style_chrome_button(primary=is_sel),
            )
            btn.pack(fill="x")

    def _render_pins(ch: dict[str, Any] | None) -> None:
        for w in pins_bar.winfo_children():
            w.destroy()
        if not ch:
            return
        pinned = [m for m in (ch.get("messages") or []) if m.get("pinned")]
        if not pinned:
            return
        ctk.CTkLabel(pins_bar, text="📌 Pins:", text_color=_HC_MUTED, width=48).pack(side="left")
        for m in pinned[-6:]:
            who = m.get("author") or "?"
            prev = cs.preview_text(str(m.get("content") or ""), limit=36)
            ctk.CTkButton(
                pins_bar,
                text=f"{who}: {prev}",
                width=140,
                height=24,
                command=lambda msg=m: _set_reply_target(msg, as_thread=True),
                **style_chrome_button(),
            ).pack(side="left", padx=2)

    def _render_timeline(ch: dict[str, Any] | None) -> None:
        for w in timeline.winfo_children():
            w.destroy()
        if not ch:
            ctk.CTkLabel(
                timeline,
                text="Create a channel to start collaborating with models.",
                text_color=_HC_MUTED,
            ).pack(anchor="w", padx=8, pady=20)
            return
        msgs = ch.get("messages") or []
        if not msgs:
            ctk.CTkLabel(timeline, text="No messages yet.", text_color=_HC_MUTED).pack(
                anchor="w", padx=8, pady=12
            )
            return
        for m in msgs:
            role = m.get("role") or "user"
            who = m.get("author") or role
            pin_mark = "📌 " if m.get("pinned") else ""
            thread_mark = ""
            if m.get("parent_id") or m.get("reply_to"):
                thread_mark = "↩ "
            at = (m.get("at") or "")[:19].replace("T", " ")
            color = _HC_MUTED if role == "system" else _HC_LABEL
            if role == "model":
                accent = _THEME_UI.get("accent", ("#7c3aed", "#a78bfa"))
            elif role == "user":
                accent = _THEME_UI.get("success", ("#059669", "#34d399"))
            else:
                accent = _HC_MUTED

            card = ctk.CTkFrame(
                timeline,
                fg_color=_THEME_UI.get("card_bg", ("#e5e7eb", "#1f2430")),
                corner_radius=8,
            )
            card.pack(fill="x", padx=4, pady=3)
            head = ctk.CTkFrame(card, fg_color="transparent")
            head.pack(fill="x", padx=8, pady=(6, 0))
            ctk.CTkLabel(
                head,
                text=f"{pin_mark}{thread_mark}{who}",
                text_color=accent,
                font=ctk.CTkFont(size=12, weight="bold"),
                anchor="w",
            ).pack(side="left")
            ctk.CTkLabel(head, text=at, text_color=_HC_MUTED, font=ctk.CTkFont(size=10)).pack(
                side="right"
            )
            body = str(m.get("content") or "")
            ctk.CTkLabel(
                card,
                text=body,
                text_color=color,
                anchor="w",
                justify="left",
                wraplength=640,
            ).pack(fill="x", padx=8, pady=(2, 4))

            if role != "system":
                actions = ctk.CTkFrame(card, fg_color="transparent")
                actions.pack(fill="x", padx=6, pady=(0, 6))

                def _pin(msg=m):
                    if not state["id"]:
                        return
                    cs.toggle_pin(state["id"], msg["id"])
                    reload_current()
                    _set_status("Pin toggled", ok=True)

                def _reply(msg=m):
                    _set_reply_target(msg, as_thread=True)
                    input_box.focus_set()

                ctk.CTkButton(
                    actions, text="📌", width=36, height=24, command=_pin, **style_chrome_button()
                ).pack(side="left", padx=2)
                ctk.CTkButton(
                    actions, text="↩ Reply", width=70, height=24, command=_reply, **style_chrome_button()
                ).pack(side="left", padx=2)

        # auto-scroll toward bottom
        try:
            timeline._parent_canvas.yview_moveto(1.0)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass

    def reload_current() -> None:
        cid = state["id"]
        if not cid:
            title_l.configure(text="Select or create a channel")
            desc_l.configure(text="")
            _render_pins(None)
            _render_timeline(None)
            return
        ch = cs.get_channel(cid)
        if not ch:
            state["id"] = None
            title_l.configure(text="Channel missing")
            desc_l.configure(text="")
            _render_pins(None)
            _render_timeline(None)
            refresh_list()
            return
        title_l.configure(text=f"#{ch.get('name') or 'channel'}")
        desc = (ch.get("description") or "").strip()
        n = len(ch.get("messages") or [])
        desc_l.configure(text=desc or f"{n} messages · @model or picker to ask a model")
        _render_pins(ch)
        _render_timeline(ch)

    def select_channel(channel_id: str) -> None:
        state["id"] = channel_id
        cs.set_active_channel_id(channel_id)
        _clear_reply_target()
        reload_current()
        refresh_list()
        _set_status("Channel selected", ok=True)

    def new_channel() -> None:
        name = simpledialog.askstring("New channel", "Channel name:", parent=app)
        if name is None:
            return
        name = (name or "").strip() or "general"
        ch = cs.create_channel(name=name)
        state["id"] = ch["id"]
        _clear_reply_target()
        refresh_list()
        reload_current()
        _set_status(f"Created #{ch['name']}", ok=True)
        app.set_status(f"Channel #{ch['name']} created", toast=True)

    def rename_channel() -> None:
        cid = state["id"]
        if not cid:
            _set_status("Select a channel first", ok=False)
            return
        ch = cs.get_channel(cid)
        if not ch:
            return
        name = simpledialog.askstring(
            "Rename channel", "New name:", initialvalue=ch.get("name") or "", parent=app
        )
        if name is None:
            return
        updated = cs.rename_channel(cid, name)
        if updated:
            refresh_list()
            reload_current()
            _set_status(f"Renamed → #{updated['name']}", ok=True)

    def delete_channel() -> None:
        cid = state["id"]
        if not cid:
            _set_status("Nothing to delete", ok=False)
            return
        ch = cs.get_channel(cid)
        label = (ch or {}).get("name") or "channel"
        if not messagebox.askyesno("Delete channel", f"Delete #{label} and all messages?", parent=app):
            return
        cs.delete_channel(cid)
        state["id"] = cs.get_active_channel_id() or None
        _clear_reply_target()
        refresh_list()
        reload_current()
        _set_status("Deleted", ok=True)
        app.set_status("Channel deleted", toast=True)

    def _composer_text() -> str:
        return input_box.get("1.0", "end").rstrip("\n")

    def post_as_user() -> None:
        cid = state["id"]
        if not cid:
            _set_status("Create or select a channel first", ok=False)
            return
        text = _composer_text().strip()
        if not text:
            _set_status("Type a message first", ok=False)
            return
        res = cs.post_user_message(
            cid,
            text,
            reply_to=state.get("reply_to"),
            parent_id=state.get("parent_id"),
        )
        if not res:
            _set_status("Post failed", ok=False)
            return
        input_box.delete("1.0", "end")
        _clear_reply_target()
        refresh_list()
        reload_current()
        # If @mentions present, offer to also ask those models
        mentions = cs.extract_model_mentions(text)
        if mentions:
            _set_status(
                f"Posted · @mentions: {', '.join(mentions)} — use Ask model to fetch replies",
                ok=True,
            )
        else:
            _set_status("Posted", ok=True)

    def ask_model(*, use_mentions: bool = True) -> None:
        cid = state["id"]
        if not cid:
            _set_status("Create or select a channel first", ok=False)
            return
        if state.get("busy"):
            _set_status("Model already answering…", ok=False)
            return
        text = _composer_text().strip()
        picked = (model_var.get() or "").strip()
        if picked.startswith("("):
            picked = ""
        mentions = cs.extract_model_mentions(text) if use_mentions else []
        mid = mentions[0] if mentions else picked

        state["busy"] = True
        _set_status(f"Asking {mid or 'model'}…")
        app.set_status("Channel model reply…")
        app.update_idletasks()

        reply_to = state.get("reply_to")
        parent_id = state.get("parent_id")
        # Clear composer after capture
        input_box.delete("1.0", "end")
        _clear_reply_target()

        def work() -> None:
            res = cs.ask_model_reply(
                cid,
                model_id=mid,
                user_text=text,
                reply_to=reply_to,
                parent_id=parent_id,
                post_user=bool(text),
            )

            def apply() -> None:
                state["busy"] = False
                refresh_list()
                reload_current()
                ok = bool(res.get("ok"))
                _set_status(str(res.get("note") or ("Done" if ok else "Soft-degraded")), ok=ok)
                app.set_status(str(res.get("note") or "Channel ask done"), toast=True)

            try:
                app.after(0, apply)
            except Exception:  # noqa: BLE001
                apply()

        threading.Thread(target=work, daemon=True).start()

    def cancel_reply() -> None:
        _clear_reply_target()
        _set_status("Reply cleared", ok=True)

    def on_key(event: Any) -> str | None:
        # Ctrl+Enter → ask model; Enter alone stays in textbox (multiline)
        if event.state & 0x4 and event.keysym.lower() in ("return", "kp_enter"):
            ask_model()
            return "break"
        if event.keysym == "Escape":
            cancel_reply()
            return "break"
        return None

    input_box.bind("<KeyPress>", on_key)

    ctk.CTkButton(
        btn_row, text="＋ New", width=70, height=28, command=new_channel, **style_chrome_button(primary=True)
    ).pack(side="left", padx=(0, 4))
    ctk.CTkButton(
        btn_row, text="Rename", width=70, height=28, command=rename_channel, **style_chrome_button()
    ).pack(side="left", padx=(0, 4))
    ctk.CTkButton(
        btn_row, text="🗑", width=36, height=28, fg_color="#a33", hover_color="#822", command=delete_channel
    ).pack(side="left")

    ctk.CTkButton(
        model_row, text="Post", width=70, height=30, command=post_as_user, **style_chrome_button()
    ).pack(side="left", padx=4)
    ctk.CTkButton(
        model_row,
        text="Ask model",
        width=100,
        height=30,
        command=lambda: ask_model(use_mentions=True),
        **style_chrome_button(primary=True),
    ).pack(side="left", padx=4)
    ctk.CTkButton(
        model_row, text="Cancel reply", width=100, height=30, command=cancel_reply, **style_chrome_button()
    ).pack(side="left", padx=4)

    def on_search(*_a: Any) -> None:
        refresh_list()

    search_var.trace_add("write", on_search)

    refresh_list()
    # Open active or newest
    active = cs.get_active_channel_id()
    items = cs.list_channels()
    if active and any(i["id"] == active for i in items):
        select_channel(active)
    elif items:
        select_channel(items[0]["id"])
    else:
        reload_current()
