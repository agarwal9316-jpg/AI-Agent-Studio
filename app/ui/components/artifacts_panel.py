"""Artifacts panel — extracted from AppWindow."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import customtkinter as ctk

if TYPE_CHECKING:
    from app.ui.app_window import AppWindow


def refresh_artifacts_panel(app) -> None:
    """List This-turn artifacts or Saved library (P2.2)."""
    from app.ui.themes import style_chrome_button, UI as _UI
    from app.services import artifacts as arts

    if not hasattr(app, "artifacts_frame"):
        return
    for w in app.artifacts_frame.winfo_children():
        try:
            w.destroy()
        except Exception:  # noqa: BLE001
            pass

    mode = getattr(app, "_artifacts_library_mode", "turn")
    if mode == "saved":
        app._render_saved_artifacts_library(_UI, style_chrome_button)
        return

    chat = getattr(app, "_chat_state", None) or {}
    try:
        bundle = arts.collect_artifacts(
            messages=list(chat.get("messages") or []),
            chat_id=str(chat.get("id") or ""),
            pending_images=list(getattr(app, "_pending_images", []) or []),
            pending_videos=list(getattr(app, "_pending_videos", []) or []),
            attachments=list(getattr(app, "_chat_attachments", []) or []),
            this_turn_only=False,
        )
    except Exception as e:  # noqa: BLE001
        ctk.CTkLabel(
            app.artifacts_frame,
            text=f"Artifacts error: {e}",
            text_color=_UI["muted"],
        ).pack(anchor="w", padx=6, pady=8)
        return
    app._last_artifacts_bundle = bundle
    ctk.CTkLabel(
        app.artifacts_frame,
        text=str(bundle.get("summary") or "Artifacts"),
        font=ctk.CTkFont(size=12, weight="bold"),
        text_color=_UI["label"],
        anchor="w",
        wraplength=220,
    ).pack(fill="x", padx=4, pady=(4, 6))
    items = list(bundle.get("items") or [])
    if not items:
        ctk.CTkLabel(
            app.artifacts_frame,
            text=(
                "Nothing yet.\n"
                "Images, file edits, research reports,\n"
                "and attachments show up here.\n"
                "Use Save to keep them in Saved."
            ),
            text_color=_UI["muted"],
            justify="left",
            anchor="w",
        ).pack(anchor="w", padx=6, pady=8)
        return
    icons = {
        "image": "🖼",
        "video": "🎬",
        "diff": "📄",
        "report": "📑",
        "code": "💻",
        "file": "📎",
        "link": "🔗",
    }
    for it in items[:40]:
        kind = str(it.get("kind") or "file")
        title = str(it.get("title") or kind)
        if len(title) > 36:
            title = title[:33] + "…"
        row = ctk.CTkFrame(app.artifacts_frame, fg_color=("gray92", "gray18"), corner_radius=8)
        row.pack(fill="x", pady=3, padx=2)
        ctk.CTkLabel(
            row,
            text=f"{icons.get(kind, '•')} {title}",
            anchor="w",
            text_color=_UI["label"],
            font=ctk.CTkFont(size=11),
        ).pack(fill="x", padx=6, pady=(4, 0))
        meta = str(it.get("meta") or "")
        if meta:
            ctk.CTkLabel(
                row,
                text=meta,
                anchor="w",
                text_color=_UI["muted"],
                font=ctk.CTkFont(size=10),
            ).pack(fill="x", padx=6)
        btns = ctk.CTkFrame(row, fg_color="transparent")
        btns.pack(fill="x", padx=4, pady=(2, 4))
        path = str(it.get("path") or "")
        if kind == "diff" and (it.get("file_diff") or it.get("diff")):
            fd = it.get("file_diff") if isinstance(it.get("file_diff"), dict) else {
                "path": path,
                "diff": it.get("diff") or "",
                "summary": it.get("title") or "File edit",
            }
            ctk.CTkButton(
                btns,
                text="Diff",
                width=50,
                height=24,
                command=lambda f=fd: app._open_file_diff_viewer(f),
                **style_chrome_button(primary=True),
            ).pack(side="left", padx=2)
        if path:
            ctk.CTkButton(
                btns,
                text="Open",
                width=50,
                height=24,
                command=lambda p=path: app._open_artifact_path(p),
                **style_chrome_button(),
            ).pack(side="left", padx=2)
            ctk.CTkButton(
                btns,
                text="Copy",
                width=50,
                height=24,
                command=lambda p=path: app._copy_artifact_path(p),
                **style_chrome_button(),
            ).pack(side="left", padx=2)
        if kind == "image" and path:
            ctk.CTkButton(
                btns,
                text="View",
                width=50,
                height=24,
                command=lambda p=path: app._open_image_lightbox(p),
                **style_chrome_button(),
            ).pack(side="left", padx=2)
        ctk.CTkButton(
            btns,
            text="Save",
            width=50,
            height=24,
            command=lambda item=it: app._save_turn_artifact(item),
            **style_chrome_button(primary=True),
        ).pack(side="left", padx=2)


def render_saved_artifacts_library(app, _UI, style_chrome_button) -> None:
    """P2.2 Saved library: search / open / reveal / export / delete."""
    from app.core.services.misc import artifacts_store as astore

    status = astore.store_status()
    head = ctk.CTkFrame(app.artifacts_frame, fg_color="transparent")
    head.pack(fill="x", padx=4, pady=(4, 2))
    ctk.CTkLabel(
        head,
        text=f"Saved library · {status.get('count', 0)}",
        font=ctk.CTkFont(size=12, weight="bold"),
        text_color=_UI["label"],
        anchor="w",
    ).pack(fill="x")
    if not status.get("ok"):
        ctk.CTkLabel(
            app.artifacts_frame,
            text=str(status.get("note") or "Store unavailable (soft-degrade)"),
            text_color=_UI["muted"],
            wraplength=220,
            justify="left",
            anchor="w",
        ).pack(fill="x", padx=6, pady=4)

    search_row = ctk.CTkFrame(app.artifacts_frame, fg_color="transparent")
    search_row.pack(fill="x", padx=4, pady=4)
    if not hasattr(app, "_artifacts_search_var"):
        app._artifacts_search_var = ctk.StringVar(master=app, value="")
    entry = ctk.CTkEntry(
        search_row,
        textvariable=app._artifacts_search_var,
        placeholder_text="Search saved…",
        height=28,
        width=160,
    )
    entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
    ctk.CTkButton(
        search_row,
        text="Go",
        width=40,
        height=28,
        command=app._refresh_artifacts_panel,
        **style_chrome_button(),
    ).pack(side="left")

    q = ""
    try:
        q = str(app._artifacts_search_var.get() or "")
    except Exception:  # noqa: BLE001
        q = ""
    try:
        items = astore.list_artifacts(query=q)
    except Exception as e:  # noqa: BLE001
        ctk.CTkLabel(
            app.artifacts_frame,
            text=f"Saved library error: {e}",
            text_color=_UI["muted"],
        ).pack(anchor="w", padx=6, pady=8)
        return

    if not items:
        ctk.CTkLabel(
            app.artifacts_frame,
            text=(
                "No saved artifacts yet.\n"
                "Open This turn → Save on an item,\n"
                "or Save all. Survives restarts."
            ),
            text_color=_UI["muted"],
            justify="left",
            anchor="w",
        ).pack(anchor="w", padx=6, pady=8)
        return

    icons = {
        "image": "🖼",
        "video": "🎬",
        "diff": "📄",
        "report": "📑",
        "code": "💻",
        "file": "📎",
        "link": "🔗",
    }
    for it in items[:60]:
        kind = str(it.get("kind") or "file")
        title = str(it.get("title") or kind)
        if len(title) > 34:
            title = title[:31] + "…"
        row = ctk.CTkFrame(app.artifacts_frame, fg_color=("gray92", "gray18"), corner_radius=8)
        row.pack(fill="x", pady=3, padx=2)
        ctk.CTkLabel(
            row,
            text=f"{icons.get(kind, '•')} {title}",
            anchor="w",
            text_color=_UI["label"],
            font=ctk.CTkFont(size=11),
        ).pack(fill="x", padx=6, pady=(4, 0))
        meta_bits = [str(it.get("mime") or ""), f"{int(it.get('size') or 0)} B"]
        tags = it.get("tags") or []
        if tags:
            meta_bits.append(", ".join(str(t) for t in tags[:4]))
        created = str(it.get("created_at") or "")[:19].replace("T", " ")
        if created:
            meta_bits.append(created)
        ctk.CTkLabel(
            row,
            text=" · ".join(b for b in meta_bits if b),
            anchor="w",
            text_color=_UI["muted"],
            font=ctk.CTkFont(size=9),
            wraplength=220,
        ).pack(fill="x", padx=6)
        btns = ctk.CTkFrame(row, fg_color="transparent")
        btns.pack(fill="x", padx=4, pady=(2, 4))
        aid = str(it.get("id") or "")
        ctk.CTkButton(
            btns,
            text="Open",
            width=48,
            height=24,
            command=lambda i=aid: app._open_saved_artifact(i),
            **style_chrome_button(primary=True),
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            btns,
            text="Reveal",
            width=54,
            height=24,
            command=lambda i=aid: app._reveal_saved_artifact(i),
            **style_chrome_button(),
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            btns,
            text="Export",
            width=54,
            height=24,
            command=lambda i=aid: app._export_saved_artifact(i),
            **style_chrome_button(),
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            btns,
            text="Del",
            width=40,
            height=24,
            command=lambda i=aid: app._delete_saved_artifact(i),
            **style_chrome_button(),
        ).pack(side="left", padx=2)
