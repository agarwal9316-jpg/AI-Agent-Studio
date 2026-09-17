"""Chat panels — extracted from AppWindow."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import customtkinter as ctk

if TYPE_CHECKING:
    from app.ui.app_window import AppWindow


def build_panel_toolbar(app, mode: str) -> None:
    """Build/rebuild the panel toolbar for the given mode."""
    if not hasattr(app, "panel_toolbar") or not app.panel_toolbar.winfo_exists():
        return
    for w in app.panel_toolbar.winfo_children():
        try:
            w.destroy()
        except Exception:
            pass

    if mode == "Activity":
        ctk.CTkButton(app.panel_toolbar, text="Clear", width=60, command=app._clear_activity).pack(side="left", padx=2)
        ctk.CTkButton(app.panel_toolbar, text="Copy", width=60, command=app._copy_activity).pack(side="left", padx=2)
        ctk.CTkButton(app.panel_toolbar, text="Export", width=70, command=app._export_activity).pack(side="left", padx=2)
        ctk.CTkButton(app.panel_toolbar, text="↻ Refresh", width=80, command=app._refresh_activity_panel).pack(side="left", padx=2)
    elif mode == "Agents":
        ctk.CTkButton(app.panel_toolbar, text="Clear", width=60, command=app._clear_agent_track).pack(side="left", padx=2)
        ctk.CTkButton(app.panel_toolbar, text="Copy", width=60, command=app._copy_agent_track).pack(side="left", padx=2)
        ctk.CTkButton(app.panel_toolbar, text="↻ Refresh", width=80, command=lambda: app._fill_agent_track_box()).pack(side="left", padx=2)
    elif mode == "Artifacts":
        mode_var = getattr(app, "_artifacts_mode_seg_var", None)
        if mode_var is None:
            app._artifacts_mode_seg_var = ctk.StringVar(
                master=app,
                value="Saved" if getattr(app, "_artifacts_library_mode", "turn") == "saved" else "This turn",
            )
            mode_var = app._artifacts_mode_seg_var
        else:
            mode_var.set("Saved" if getattr(app, "_artifacts_library_mode", "turn") == "saved" else "This turn")

        def _set_art_mode(v: str) -> None:
            app._artifacts_library_mode = "saved" if v == "Saved" else "turn"
            app._refresh_artifacts_panel()
            app._build_panel_toolbar("Artifacts")

        ctk.CTkSegmentedButton(
            app.panel_toolbar,
            values=["This turn", "Saved"],
            variable=mode_var,
            command=_set_art_mode,
            width=160,
            height=26,
        ).pack(side="left", padx=2)
        ctk.CTkButton(app.panel_toolbar, text="↻ Refresh", width=80, command=app._refresh_artifacts_panel).pack(side="left", padx=2)
    elif mode == "Terminal":
        ctk.CTkButton(app.panel_toolbar, text="Clear", width=60, command=app._clear_terminal).pack(side="left", padx=2)
        ctk.CTkButton(app.panel_toolbar, text="Copy", width=60, command=app._copy_terminal).pack(side="left", padx=2)


def toggle_live_thinking(app) -> None:
    """Toggle Live thinking panel visibility."""
    try:
        app._live_panel_visible = not bool(getattr(app, "_live_panel_visible", False))
        app._chat_apply_mid_columns()
        if hasattr(app, "_live_btn"):
            from app.ui.themes import style_chrome_button
            app._live_btn.configure(
                text="Live ●" if app._live_panel_visible else "Live",
                **style_chrome_button(active=app._live_panel_visible),
            )
    except Exception:
        pass


def bind_terminal_log(app) -> None:
    """Subscribe terminal box to activity_log terminal lines."""
    from app.core.services.misc.activity_log import add_listener
    import re

    app._terminal_log_lines = getattr(app, "_terminal_log_lines", [])

    def on_line(line: str) -> None:
        def ui() -> None:
            try:
                if not app.winfo_exists():
                    return
                box = getattr(app, "terminal_box", None)
                if box is None or not box.winfo_exists():
                    return
                source_match = re.search(r"\[(\w+)\]", line)
                source = source_match.group(1).lower() if source_match else ""
                if source not in ("terminal", "stdout", "stderr"):
                    return
                lower = line.lower()
                if not (
                    source in ("terminal", "stdout", "stderr")
                    or "$ " in lower
                    or "command:" in lower
                    or "exit=" in lower
                    or "cwd:" in lower
                ):
                    return
                app._terminal_log_lines.append(line)
                if len(app._terminal_log_lines) > 500:
                    app._terminal_log_lines = app._terminal_log_lines[-500:]
                if getattr(app, "side_panel_mode", None) and app.side_panel_mode.get() == "Terminal":
                    box.configure(state="normal")
                    tag = "info"
                    if lower.startswith("$ ") or "command:" in lower:
                        tag = "cmd"
                    elif source == "stdout":
                        tag = "stdout"
                    elif source == "stderr":
                        tag = "stderr"
                    elif "exit=" in lower:
                        tag = "exit"
                    elif "cwd:" in lower:
                        tag = "cwd"
                    box.insert("end", line + "\n", tag)
                    box.see("end")
                    box.configure(state="disabled")
            except Exception:
                pass

        app._ui_call(ui)

    add_listener(on_line)
