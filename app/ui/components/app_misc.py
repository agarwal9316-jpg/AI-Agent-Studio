"""App misc — extracted from AppWindow."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import customtkinter as ctk

if TYPE_CHECKING:
    from app.ui.app_window import AppWindow


def reload_chat_view_after_delete(app) -> None:
    """
    After deleting the open chat: show the new active chat without a full
    show_page destroy/rebuild (that path freezes CustomTkinter on Windows).
    """
    if getattr(app, "_current_page", "") != "Chat":
        try:
            app.show_page("Chat")
        except Exception:  # noqa: BLE001
            pass
        return
    try:
        if hasattr(app, "chat_title_label"):
            st = getattr(app, "_chat_state", None) or {}
            pin = "📌 " if st.get("pinned") else ""
            name = str(st.get("title") or "Chat")
            try:
                app.chat_title_label.configure(text=f"{pin}{name}  ·  rename")
            except Exception:  # noqa: BLE001
                pass
        try:
            app._chat_render_transcript()
        except Exception:  # noqa: BLE001
            pass
        try:
            app._refresh_chat_rail_history()
        except Exception:  # noqa: BLE001
            pass
        try:
            app._refresh_chat_tabs_bar()
        except Exception:  # noqa: BLE001
            pass
        try:
            app._refresh_context_chip()
        except Exception:  # noqa: BLE001
            pass
        try:
            app._update_composer_status()
        except Exception:  # noqa: BLE001
            pass
        try:
            app._chat_scroll_to_end(force=True)
        except Exception:  # noqa: BLE001
            pass
    except Exception:  # noqa: BLE001
        try:
            app.show_page("Chat")
        except Exception:  # noqa: BLE001
            pass
