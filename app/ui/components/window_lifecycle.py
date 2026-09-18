"""Window lifecycle — extracted from AppWindow."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import customtkinter as ctk

from app.services import storage

if TYPE_CHECKING:
    from app.ui.app_window import AppWindow


def start_native_background_services(app) -> None:
    """Clipboard watch, file watcher, scheduler — non-blocking."""
    try:
        from app.services import clipboard_watch, file_watcher, scheduler_service

        clipboard_watch.start()

        def on_clip(ev: dict) -> None:
            def ui() -> None:
                if not app.winfo_exists():
                    return
                kind = ev.get("kind")
                if kind in ("file_paths", "image_paths") and ev.get("paths"):
                    try:
                        from app.core.services.misc.attachments import sanitize_attachment_paths

                        ev_paths = sanitize_attachment_paths(list(ev.get("paths") or []))
                    except Exception:  # noqa: BLE001
                        ev_paths = list(ev.get("paths") or [])
                    for p in ev_paths:
                        if p not in app._chat_attachments:
                            app._chat_attachments.append(p)
                        if kind == "image_paths":
                            imgs = getattr(app, "_pending_images", [])
                            if p not in imgs:
                                imgs.append(p)
                            app._pending_images = imgs
                    app._update_composer_status()
                    app.set_status(f"Clipboard: attached {len(ev.get('paths') or [])} path(s)")
                elif kind == "url":
                    app.set_status(f"Clipboard URL: {str(ev.get('text') or '')[:60]}")

            try:
                app.after(0, ui)
            except Exception:  # noqa: BLE001
                pass

        clipboard_watch.add_listener(on_clip)
        if file_watcher.load_watches():
            file_watcher.start()
        if scheduler_service.load_schedules():
            scheduler_service.start()
        try:
            from app.core.services.chat import automations_store as _aus

            if any(a.get("enabled") for a in _aus.list_automations()):
                _aus.start()
        except Exception:  # noqa: BLE001
            pass
    except Exception:  # noqa: BLE001
        pass
    try:
        from app.services import global_hotkeys

        def on_hotkey(ev: dict) -> None:
            def ui() -> None:
                if not app.winfo_exists():
                    return
                if ev.get("type") == "clipboard":
                    app._ask_about_clipboard(
                        str(ev.get("text") or ""), source=str(ev.get("label") or "")
                    )
                elif ev.get("type") == "error":
                    app.set_status(f"Hotkey: {ev.get('error')}", toast=True)

            try:
                app.after(0, ui)
            except Exception:  # noqa: BLE001
                pass

        global_hotkeys.set_listener(on_hotkey)
        if global_hotkeys.start():
            app.set_status("Hotkey Ctrl+Shift+G: ask about clipboard", toast=False)
    except Exception:  # noqa: BLE001
        pass


def set_one_screen(app, on: bool) -> None:
    on = bool(on)
    app._one_screen = on
    app._focus_mode = on
    rail = getattr(app, "_chat_rail_frame", None)
    if on:
        app._set_app_menu_collapsed(True, persist=False)
        app._set_sysmon_collapsed(True, persist=False)
        app._chat_rail_collapsed = True
        try:
            if rail is not None:
                rail.grid_remove()
        except Exception:  # noqa: BLE001
            pass
        try:
            app._ensure_live_monitor_open(tab="Terminal")
        except Exception:  # noqa: BLE001
            pass
        try:
            if bool(getattr(app, "_chat_setup_expanded", False)):
                app._chat_toggle_setup_panel()
        except Exception:  # noqa: BLE001
            pass
        if getattr(app, "_chat_density", "compact") != "compact":
            app._chat_density = "compact"
            try:
                app._apply_chat_density_layout()
            except Exception:  # noqa: BLE001
                pass
        app._persist_chrome()
        app._refresh_view_buttons()
        app.set_status("One-screen view — Esc, ☰, or Exit one-screen restores the menu")
    else:
        app._set_app_menu_collapsed(False, persist=False)
        app._set_sysmon_collapsed(False, persist=False)
        app._chat_rail_collapsed = False
        app._persist_chrome()
        app._refresh_view_buttons()
        if getattr(app, "_chat_rail_list", None) is None:
            app.show_page("Chat", rebuild=True)
        else:
            app._apply_chat_rail_layout()
        app.set_status("Full view — menu and chat list are back")


def on_close(app) -> None:
    if not getattr(app, "_tray_quitting", False):
        try:
            from app.services import system_tray as tray

            if tray.should_use_tray() and tray.close_to_tray():
                app._hide_to_tray()
                return
        except Exception:  # noqa: BLE001
            pass
    try:
        from app.services import chat_store as chat_svc

        if getattr(app, "_chat_state", None):
            chat_svc.save_chat(app._chat_state)
    except Exception:  # noqa: BLE001
        pass
    try:
        cfg = storage.load_config()
        cfg["session_unclean"] = False
        cfg["session_active_chat"] = ""
        try:
            try:
                is_max = str(app.state()) == "zoomed"
            except Exception:  # noqa: BLE001
                is_max = bool(getattr(app, "_win_maximized", False))
            cfg["window_maximized"] = is_max
            app._win_maximized = is_max
            if not is_max:
                try:
                    if str(app.state()) != "withdrawn":
                        cfg["window_geometry"] = app.geometry()
                except Exception:  # noqa: BLE001
                    cfg["window_geometry"] = app.geometry()
        except Exception:  # noqa: BLE001
            pass
        storage.save_config(cfg)
    except Exception:  # noqa: BLE001
        pass
    try:
        from app.core.services.chat.orchestrator import get_orchestrator

        get_orchestrator().stop()
    except Exception:  # noqa: BLE001
        pass
    try:
        from app.core.services.system.terminal_tool import kill_active_terminal

        kill_active_terminal()
    except Exception:  # noqa: BLE001
        pass
    try:
        from app.services import global_hotkeys

        global_hotkeys.stop()
    except Exception:  # noqa: BLE001
        pass
    try:
        from app.services import system_tray

        system_tray.stop()
    except Exception:  # noqa: BLE001
        pass
    try:
        app._sysmon_running = False
    except Exception:  # noqa: BLE001
        pass
    app.destroy()


def ui_pump(app) -> None:
    q = getattr(app, "_ui_queue", None)
    if q is None:
        return
    n = 0
    while n < 24:
        try:
            fn = q.get_nowait()
        except Exception:  # noqa: BLE001
            break
        n += 1
        try:
            fn()
        except Exception:  # noqa: BLE001
            pass
    more = False
    try:
        more = not q.empty()
    except Exception:  # noqa: BLE001
        more = False
    delay = 8 if more else 33
    try:
        if app.winfo_exists() and bool(app.attributes("-topmost")):
            app.attributes("-topmost", False)
    except Exception:  # noqa: BLE001
        pass
    try:
        app.after(delay, app._ui_pump)
        app._ui_pump_scheduled = True
    except Exception:  # noqa: BLE001
        app._ui_pump_scheduled = False


def refresh_cycle_buttons(app) -> None:
    running = bool(getattr(app, "_task_cycle_running", False))
    try:
        run_btn = getattr(app, "_cycle_run_btn", None)
        if run_btn is not None and run_btn.winfo_exists():
            from app.ui.themes import style_chrome_button

            if running:
                run_btn.configure(
                    text="▶ Running",
                    state="disabled",
                    fg_color=("#bbf7d0", "#14532d"),
                    text_color=("#14532d", "#bbf7d0"),
                )
            else:
                run_btn.configure(
                    text="▶ Run cycle",
                    state="normal",
                    **style_chrome_button(primary=True),
                )
    except Exception:  # noqa: BLE001
        pass
    try:
        stop_btn = getattr(app, "_cycle_stop_btn", None)
        if stop_btn is not None and stop_btn.winfo_exists():
            if running:
                stop_btn.configure(
                    text="■ Stop cycle",
                    state="normal",
                    fg_color=("#dc2626", "#7f1d1d"),
                    hover_color=("#b91c1c", "#450a0a"),
                    text_color=("#ffffff", "#fecaca"),
                )
            else:
                stop_btn.configure(
                    text="■ Stop cycle",
                    state="disabled",
                    fg_color=("#d1d5db", "#3f3f46"),
                    hover_color=("#9ca3af", "#27272a"),
                    text_color=("#52525b", "#a1a1aa"),
                )
    except Exception:  # noqa: BLE001
        pass


def ensure_live_monitor_open(app, tab: str = "Terminal") -> None:
    app._live_panel_visible = True
    app._live_panel_user_on = True
    try:
        cfg = storage.load_config()
        cfg["chat_auto_live_panel"] = True
        storage.save_config(cfg)
        app.cfg = cfg
    except Exception:  # noqa: BLE001
        pass
    try:
        app._chat_apply_mid_columns()
    except Exception:  # noqa: BLE001
        pass
    try:
        if hasattr(app, "side_panel_mode") and tab:
            app.side_panel_mode.set(tab)
    except Exception:  # noqa: BLE001
        pass
    try:
        app._refresh_side_panel()
    except Exception:  # noqa: BLE001
        pass
    from app.ui.themes import style_chrome_button

    if hasattr(app, "_live_btn"):
        try:
            app._live_btn.configure(text="Live ●", **style_chrome_button(active=True))
        except Exception:  # noqa: BLE001
            pass


def setup_system_tray(app) -> None:
    try:
        from app.services import system_tray as tray

        if not tray.should_use_tray():
            return

        def _show() -> None:
            try:
                app.after(0, app._show_from_tray)
            except Exception:  # noqa: BLE001
                pass

        def _hide() -> None:
            try:
                app.after(0, app._hide_to_tray)
            except Exception:  # noqa: BLE001
                pass

        def _quit() -> None:
            try:
                app.after(0, app._quit_from_tray)
            except Exception:  # noqa: BLE001
                pass

        tray.set_callbacks(show=_show, hide=_hide, quit_app=_quit)
        if tray.start():
            try:
                app.bind("<Unmap>", app._on_unmap_minimize, add="+")
            except Exception:  # noqa: BLE001
                pass
            try:
                app.set_status("System tray ready — close/minimize can run in background", toast=False)
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass


def hide_to_tray(app) -> None:
    try:
        from app.services import system_tray as tray

        if not tray.should_use_tray():
            return
        if not tray.start():
            return
    except Exception:  # noqa: BLE001
        return
    app._hidden_in_tray = True
    try:
        try:
            st = str(app.state() or "")
            if st != "zoomed" and st != "iconic":
                cfg = storage.load_config()
                cfg["window_geometry"] = app.geometry()
                storage.save_config(cfg)
                if isinstance(getattr(app, "cfg", None), dict):
                    app.cfg["window_geometry"] = cfg["window_geometry"]
        except Exception:  # noqa: BLE001
            pass
        app.withdraw()
        try:
            app.set_status("Running in tray — right-click tray icon → Show / Quit", toast=True)
        except Exception:  # noqa: BLE001
            pass
    except Exception:  # noqa: BLE001
        app._hidden_in_tray = False


def show_from_tray(app) -> None:
    app._hidden_in_tray = False
    try:
        app.deiconify()
        try:
            app.state("normal")
        except Exception:  # noqa: BLE001
            pass
        app.lift()
        app.focus_force()
        try:
            app.attributes("-topmost", True)
            app.after(200, lambda: app.attributes("-topmost", False))
        except Exception:  # noqa: BLE001
            pass
        try:
            app.set_status("Restored from tray", toast=True)
        except Exception:  # noqa: BLE001
            pass
    except Exception:  # noqa: BLE001
        pass
