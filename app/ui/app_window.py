"""Main window: sidebar + pages. Started only via Launch / python -m app."""

from __future__ import annotations

import threading
import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox
import tkinter.simpledialog as simpledialog
from pathlib import Path
from typing import Any, Callable

import customtkinter as ctk

from app.ui.themes import UI as _THEME_UI
from app.ui.components import (
    build_name,
    set_widget_name,
    name_sidebar_nav_button,
    name_sidebar_hub_header,
    name_sidebar_hub_items_frame,
    name_sidebar_footer_button,
    name_page_root,
    name_page_header,
    name_page_body,
    name_page_save_bar,
    name_page_sidebar,
    name_chat_messages_scroll,
    name_chat_composer_input,
    name_chat_composer_send_btn,
    name_chat_composer_attach_btn,
    name_chat_composer_mic_btn,
    name_chat_composer_speak_btn,
    name_chat_composer_mode_chip,
    name_chat_toolbar_button,
    name_chat_toolbar_provider_menu,
    name_chat_toolbar_model_menu,
    name_chat_toolbar_model_search,
    name_chat_sidebar_panel,
    name_chat_sidebar_button,
    name_chat_sidebar_search,
    name_chat_topbar_title,
    name_chat_topbar_mode_chip,
    name_chat_topbar_tasks_chip,
    name_chat_topbar_risk_chip,
    name_chat_topbar_caps_chip,
    name_status_bar_label,
    name_system_monitor_metric,
    name_dialog,
    PAGE_HOME, PAGE_HELP, PAGE_CHAT, PAGE_TEAM, PAGE_MODELS,
    PAGE_MONITOR, PAGE_CHATS, PAGE_TRACK, PAGE_WORK,
    PAGE_APPROVALS, PAGE_PATCHES, PAGE_KNOWLEDGE, PAGE_SCHEDULE,
    PAGE_ORG_CHART, PAGE_MEMORY, PAGE_PROJECTS, PAGE_COMPANY,
    PAGE_CEO, PAGE_AGENTS, PAGE_TASKS, PAGE_RUNS, PAGE_USAGE,
    PAGE_SETTINGS, PAGE_ABOUT,
    REGION_SIDEBAR, REGION_CONTENT, REGION_STATUS_BAR,
    REGION_SYSTEM_MONITOR, REGION_COMMAND_PALETTE,
    SIDEBAR_NAV, SIDEBAR_FOOTER,
    HUB_PRIMARY, HUB_WORKSPACE, HUB_MORE,
    CHAT_MESSAGES, CHAT_COMPOSER, CHAT_SIDEBAR, CHAT_TOOLBAR,
    PREFIX_BUTTON, PREFIX_LABEL, PREFIX_FRAME, PREFIX_SCROLL,
    PREFIX_TEXTBOX, PREFIX_ENTRY, PREFIX_PANEL, PREFIX_HEADER,
    PREFIX_BAR,
)
from app.core.services.misc.hover_help import chat_control_help, hub_description, page_description
from app.ui.components.scroll import apply_smooth_scroll, bind_smooth_text_wheel
from app.ui.components.tooltip import add_tooltip

_HC_MUTED = _THEME_UI["muted"]
_HC_LABEL = _THEME_UI["label"]


from app.paths import app_root, data_dir
from app.core.services.chat import chat as chat_svc
from app.services import storage
from app.core.services.misc.attachments import (
    CHOICE_BOTH,
    CHOICE_FULL,
    CHOICE_HEAD,
    CHOICE_PATH_ONLY,
    CHOICE_SKIP,
    CHOICE_TAIL,
)
from app.services import chat_store
from app.core.services.misc.default_prompts import get_default_system_prompt
from app.core.services.llm.llm import LLMError
from app.core.services.chat.memory_store import memory_prompt_block
from app.core.services.chat.orchestrator import get_orchestrator
from app.core.services.misc.runner import run_pipeline
from app.core.services.tools.skills_registry import discover_skills
from app.ui import mgmt_pages
from app.ui.pages import notes_page
from app.version import APP_NAME, __version__

NAV_ITEMS = (
    "Home",
    "Help",
    "Chat",
    "Team",
    "Models",
    "Monitor",
    "Chats",
    "Track",
    "Work",
    "Approvals",
    "Patches",
    "Knowledge",
    "Notes",
    "Schedule",
    "Org chart",
    "Memory",
    "Projects",
    "Company",
    "CEO",
    "Agents",
    "Tasks",
    "Runs",
    "Usage",
    "Settings",
    "About",
)

# Grok-style chat (inspired by grok.com): dark canvas, soft user pill, flat assistant
# Each value: (bg light/dark, text light/dark) for CTk dual-mode tuples
_BUBBLE = {
    # High-contrast cards (flat-on-canvas + tiny wrap made text unreadable)
    "user": (("#dbeafe", "#1e3a5f"), ("#0f172a", "#f8fafc")),
    "assistant": (("#ffffff", "#18181b"), ("#111827", "#f4f4f5")),
    "tool": (("#ecfdf5", "#0c1a14"), ("#065f46", "#a7f3d0")),
    "error": (("#fef2f2", "#1a0a0a"), ("#991b1b", "#fecaca")),
    "system": (("#f4f4f5", "#18181b"), ("#1f2937", "#e5e7eb")),
}
# Accent rings / avatar fills (light, dark)
_BUBBLE_ACCENT = {
    "user": ("#3b82f6", "#60a5fa"),
    "assistant": ("#a78bfa", "#c4b5fd"),  # Grok violet spark
    "tool": ("#10b981", "#34d399"),
    "error": ("#ef4444", "#f87171"),
    "system": ("#64748b", "#94a3b8"),
}
# Max readable column width (Grok centers content ~720px)
# Message column target width (Grok-like but wider so half the screen is not empty gutters)
_GROK_CHAT_COL = 860


class AppWindow(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        # Ensure this window is the default root for tkinter font/widget operations
        import tkinter as _tk
        _tk._default_root = self
        # Soft launch: stay visible (never alpha=0 — that left a permanent invisible window
        # when deiconify/reveal failed on some Windows + CustomTkinter builds).
        self._startup_hidden = False
        self._revealed = False
        # Ensure we are mapped if CTk titlebar init withdrew the window
        try:
            self.attributes("-alpha", 1.0)
        except Exception:  # noqa: BLE001
            pass
        try:
            self.deiconify()
        except Exception:  # noqa: BLE001
            pass

        try:
            self._init_ui()
        except Exception as e:  # noqa: BLE001
            # Always surface the window even if page build fails
            try:
                from app.core.services.misc.app_log import log_event

                log_event("startup_ui_error", level="error", error=str(e)[:500])
            except Exception:  # noqa: BLE001
                pass
            try:
                self._force_show_window()
            except Exception:  # noqa: BLE001
                pass
            raise
        # Reveal is idempotent; also schedule a safety net if something re-withdraws
        self._force_show_window()
        self.after(100, self._force_show_window)
        self.after(500, self._force_show_window)
        self.after(200, self._post_startup_services)

    def _init_ui(self) -> None:
        """Build chrome + first page. Window stays visible (no hide-until-ready)."""
        self.cfg = storage.load_config()
        # Detect previous unclean exit before we mark this session dirty
        self._crash_restore_chat_id = None
        try:
            if self.cfg.get("session_unclean") and self.cfg.get("session_active_chat"):
                self._crash_restore_chat_id = str(self.cfg.get("session_active_chat") or "")
        except Exception:  # noqa: BLE001
            pass
        # Theme is preferably applied in run_app() before CTk exists.
        if not getattr(AppWindow, "_theme_preapplied", False):
            try:
                from app.ui.themes import apply_theme

                apply_theme(self.cfg.get("ui_theme") or "Readable Dark")
            except Exception:  # noqa: BLE001
                theme = self.cfg.get("theme") or "dark"
                ctk.set_appearance_mode("Dark" if theme == "dark" else "Light")
                ctk.set_default_color_theme("blue")

        self.title(f"{APP_NAME}  v{__version__}")
        try:
            from app.core.services.llm.providers import ensure_builtin_providers, resolve_active_llm

            ensure_builtin_providers()
            resolve_active_llm()  # pin NVIDIA Nemotron 550 if the catalog drifted
        except Exception:  # noqa: BLE001
            pass
        self.minsize(720, 480)
        try:
            scale = float(self.cfg.get("ui_scale") or 1.0)
            scale = max(0.9, min(1.25, scale))
            ctk.set_widget_scaling(scale)
            try:
                ctk.set_window_scaling(1.0)
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            pass
        try:
            geo = str(self.cfg.get("window_geometry") or "").strip()
            if geo and "x" in geo:
                self.geometry(geo)
            else:
                self.geometry("1280x840")
        except Exception:  # noqa: BLE001
            self.geometry("1280x840")
        try:
            self.resizable(True, True)
            self.wm_resizable(True, True)
        except Exception:  # noqa: BLE001
            pass
        self._win_maximized = False
        self._want_maximized = bool(self.cfg.get("window_maximized"))
        # Maximize only after map (avoids withdraw race)
        if self._want_maximized:
            try:
                self.after(150, self._apply_startup_maximized)
            except Exception:  # noqa: BLE001
                pass

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        self._current_page = ""
        self._selected_agent_id: str | None = None
        self._selected_task_id: str | None = None
        self._selected_run_id: str | None = None
        self._chat_busy = False
        self._chat_cancel = False
        self._chat_paused = False
        self._chat_busy_started = 0.0
        self._chat_stop_click_ts = 0.0
        self._chat_show_tools = False
        # P0.2 multi-model compare / arena (OWUI-style)
        self._compare_mode = bool((self.cfg or {}).get("compare_mode", False))
        self._compare_models: list[str] = list(
            (self.cfg or {}).get("compare_models") or []
        )[:3]
        self._compare_layout = str((self.cfg or {}).get("compare_layout") or "stacked")
        self._chat_page_gen = 0
        self._task_status = "none"
        self._llm_phase = "idle"
        self._auto_continue_count = 0
        self._auto_continue_last_ts = 0.0
        self._auto_continue_hold_until = 0.0
        self._auto_error_retries = 0
        self._task_watch_started = False
        self._task_cycle_running = False
        self._chat_history_window = 80
        self._chat_state = self._load_active_chat()
        # Clear zombie agent runs left as "running" after crashes / hung sends
        try:
            from app.core.services.data.agent_tracker import abandon_stale_runs

            abandon_stale_runs(max_age_sec=120.0)
        except Exception:  # noqa: BLE001
            pass
        self._team_job: dict[str, Any] = {
            "running": False,
            "stop": False,
            "channel_id": "",
            "progress": "",
            "error": "",
            "cancelled": False,
            "ok": False,
            "thread": None,
        }
        self._team_ui_on_progress = None
        self._chat_attachments: list[str] = []
        self._chat_attached_notes: list[str] = []  # note ids for next-send inject
        self._chat_terminal_cwd = str(app_root())
        # Thread → UI bridge (Tk is not thread-safe; never touch widgets from workers)
        import queue as _queue

        self._ui_queue: _queue.SimpleQueue = _queue.SimpleQueue()
        self._ui_pump_scheduled = False
        self._thinking_ui_last = 0.0
        self._thinking_ui_pending: str | None = None
        self._side_panel_refresh_after: str | None = None
        self._stream_scroll_pending = False

        self._orch = get_orchestrator()
        self._orch.add_listener(
            lambda m: self._ui_call(lambda msg=m: self._on_orch_status(msg))
        )
        # Start draining worker→UI callbacks
        try:
            self.after(50, self._ui_pump)
        except Exception:  # noqa: BLE001
            pass

        self._build_sidebar()
        from app.ui.themes import UI as _SHELL_UI

        self._main_col = ctk.CTkFrame(self, corner_radius=0, fg_color=_SHELL_UI["content_bg"])
        self._main_col.grid(row=0, column=1, sticky="nsew")
        self._main_col.grid_columnconfigure(0, weight=1)
        # Row 0: System monitor bar (fixed height)
        # Row 1: Content (expands)
        self._main_col.grid_rowconfigure(0, weight=0)
        self._main_col.grid_rowconfigure(1, weight=1)

        self._ensure_window_resize_ok()

        # --- System Monitor Bar (top of main content) ---
        self._build_system_monitor_bar()

        self.content = ctk.CTkFrame(
            self._main_col, corner_radius=0, fg_color=_SHELL_UI["content_bg"]
        )
        self.content.grid(row=1, column=0, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)
        self._focus_mode = bool((self.cfg or {}).get("chat_one_screen", False))
        self._one_screen = self._focus_mode
        self._sidebar_collapsed = bool((self.cfg or {}).get("sidebar_collapsed", False))
        self._sysmon_collapsed = bool((self.cfg or {}).get("sysmon_collapsed", False))
        self._build_menu_expander()
        try:
            self.after(80, self._apply_saved_chrome)
        except Exception:  # noqa: BLE001
            pass

        # Logical names for main window regions
        set_widget_name(self, "app")
        if hasattr(self, "_sidebar_frame") and self._sidebar_frame:
            set_widget_name(self._sidebar_frame, build_name("app", REGION_SIDEBAR, PREFIX_FRAME, "root"))
        set_widget_name(self._main_col, build_name("app", REGION_CONTENT, PREFIX_FRAME, "main_col"))
        set_widget_name(self.content, build_name("app", REGION_CONTENT, PREFIX_FRAME, "root"))

        self.status = ctk.CTkLabel(
            self,
            text=self._status_text(),
            anchor="w",
            height=30,
            padx=14,
            fg_color=_SHELL_UI["status_bg"],
            text_color=_SHELL_UI["status_text"],
            font=ctk.CTkFont(size=12),
        )
        self.status.grid(row=1, column=0, columnspan=2, sticky="ew")
        set_widget_name(self.status, name_status_bar_label("main"))

        try:
            # Open Chat when a session exists — Home first left a blank Org/Chat hybrid
            start = "Chat" if (self.cfg or {}).get("active_chat_id") else "Home"
            self.show_page(start)
        except Exception as e:  # noqa: BLE001
            # Fallback empty content so chrome still shows
            try:
                ctk.CTkLabel(
                    self.content,
                    text=f"Home failed to load:\n{e}\n\nUse the sidebar to open Chat.",
                    text_color=_SHELL_UI["muted"],
                    justify="left",
                ).grid(row=0, column=0, sticky="nw", padx=20, pady=20)
            except Exception:  # noqa: BLE001
                pass
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._hidden_in_tray = False
        self._tray_quitting = False
        self._setup_system_tray()
        self._bind_global_shortcuts()
        self._start_autosave_timer()
        self._start_status_refresh()
        self._start_task_watch()
        self._bind_tool_approvals()
        try:
            cfg = storage.load_config()
            cfg["session_unclean"] = True
            cfg["session_active_chat"] = chat_store.get_active_chat_id() or ""
            storage.save_config(cfg)
            self.cfg = cfg
        except Exception:  # noqa: BLE001
            pass

    def _force_show_window(self) -> None:
        """Guarantee the main window is visible (never leave withdrawn/alpha-0)."""
        # Respect intentional tray hide / start-minimized (PENDING #19)
        if getattr(self, "_hidden_in_tray", False):
            return
        try:
            self.attributes("-alpha", 1.0)
        except Exception:  # noqa: BLE001
            pass
        try:
            # CTk may have left us withdrawn after titlebar color
            st = str(self.state() or "")
            if st == "withdrawn" or st == "iconic":
                self.deiconify()
            else:
                self.deiconify()
        except Exception:  # noqa: BLE001
            try:
                self.deiconify()
            except Exception:  # noqa: BLE001
                pass
        try:
            self.lift()
            self.focus_force()
        except Exception:  # noqa: BLE001
            pass
        self._startup_hidden = False
        self._revealed = True

    def _apply_startup_maximized(self) -> None:
        try:
            if getattr(self, "_want_maximized", False):
                self.state("zoomed")
                self._win_maximized = True
        except Exception:  # noqa: BLE001
            pass
        self._force_show_window()

    def _post_startup_services(self) -> None:
        """Background services + deferred dialogs after first paint."""
        try:
            self._start_native_background_services()
        except Exception:  # noqa: BLE001
            pass
        self.after(800, self._maybe_show_onboarding)
        self.after(1000, self._maybe_offer_crash_restore)
        self.after(4000, self._maybe_check_updates_on_start)
        self.after(300, self._ensure_window_resize_ok)

    def _reveal_window(self) -> None:
        """Compat alias — always force-show."""
        self._force_show_window()
        self._post_startup_services()

    def _load_active_chat(self) -> dict:
        return chat_svc.load_chat()

    def _on_orch_status(self, msg: str) -> None:
        if self.winfo_exists():
            self.status.configure(text=f"BG: {msg}  |  v{__version__}")

    def _status_text(self) -> str:
        bg = ""
        usage = ""
        hw = ""
        try:
            bg = f"  |  BG: {get_orchestrator().status}"
        except Exception:  # noqa: BLE001
            pass
        try:
            from app.core.services.data.usage_meter import format_status_line

            usage = f"  |  {format_status_line()}"
        except Exception:  # noqa: BLE001
            pass
        try:
            from app.core.services.system.ops_monitor import hardware_snapshot

            snap = hardware_snapshot()
            cpu = snap.get("cpu_percent")
            ram = snap.get("ram") or {}
            gpu = (snap.get("gpu") or [{}])[0] if snap.get("gpu") else {}
            if cpu is not None:
                hw = f"  |  CPU {cpu}%  ·  RAM {ram.get('used_gb', 0):.1f}/{ram.get('total_gb', 0):.1f} GB ({ram.get('percent', '?')}%)  ·  GPU {gpu.get('util_percent', '—')}%"
        except Exception:  # noqa: BLE001
            pass
        task_llm = ""
        try:
            from app.core.services.chat.task_watch import llm_chip_label, task_chip_label

            task_llm = (
                f"{task_chip_label(getattr(self, '_task_status', 'none'))}  |  "
                f"{llm_chip_label(getattr(self, '_llm_phase', 'idle'))}  |  "
            )
        except Exception:  # noqa: BLE001
            task_llm = ""
        return f"{task_llm}Ready  |  data: {data_dir()}{bg}{usage}{hw}  |  v{__version__}"

    def _ui_call(self, fn: Callable[[], Any]) -> None:
        """
        Schedule fn on the Tk main thread (safe from worker threads).
        Only puts on a queue — never calls Tk after()/widgets from workers.
        The main-thread _ui_pump drains the queue.
        """
        try:
            self._ui_queue.put(fn)
        except Exception:  # noqa: BLE001
            pass

    def _ui_pump(self) -> None:
        """Drain queued UI callbacks; keep batches short so the window stays interactive."""
        q = getattr(self, "_ui_queue", None)
        if q is None:
            return
        n = 0
        # Cap work per tick so long streams don't freeze mouse/keyboard
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
        # Always reschedule from main thread only (this method runs via after)
        delay = 8 if more else 33
        # Safety net: ensure -topmost never sticks on the main window
        try:
            if self.winfo_exists() and bool(self.attributes("-topmost")):
                self.attributes("-topmost", False)
        except Exception:  # noqa: BLE001
            pass
        try:
            self.after(delay, self._ui_pump)
            self._ui_pump_scheduled = True
        except Exception:  # noqa: BLE001
            self._ui_pump_scheduled = False

    def set_status(self, text: str | None = None, *, toast: bool = False) -> None:
        msg = text or self._status_text()
        # Always keep version visible (Team progress used to wipe it)
        try:
            ver = f"v{__version__}"
            if ver not in (msg or ""):
                msg = f"{msg}  |  {ver}"
        except Exception:  # noqa: BLE001
            pass
        try:
            self.status.configure(text=msg)
        except Exception:  # noqa: BLE001
            pass
        if toast and text:
            kind = "info"
            low = text.lower()
            if any(x in low for x in ("fail", "error", "denied")):
                kind = "err"
            elif any(x in low for x in ("ok", "done", "saved", "ready", "complete")):
                kind = "ok"
            elif "approval" in low or "warn" in low:
                kind = "warn"
            self._toast(text, kind=kind)

    def _toast(self, message: str, *, kind: str = "info", ms: int = 2800) -> None:
        """Non-blocking toast in the top-right of the main window."""
        try:
            from app.ui.themes import UI as _UI

            # Destroy previous toast
            old = getattr(self, "_toast_win", None)
            if old is not None:
                try:
                    old.destroy()
                except Exception:  # noqa: BLE001
                    pass
            colors = {
                "info": _UI["accent_soft"],
                "ok": (("#d1fae5", "#064e3b")),
                "warn": (("#fef3c7", "#78350f")),
                "err": (("#fee2e2", "#7f1d1d")),
            }
            fg = colors.get(kind, colors["info"])
            fr = ctk.CTkFrame(self, fg_color=fg, corner_radius=12, border_width=1, border_color=_UI["top_border"])
            self._toast_win = fr
            ctk.CTkLabel(
                fr,
                text=(message or "")[:120],
                text_color=_UI["label"],
                font=ctk.CTkFont(size=12),
                wraplength=360,
                justify="left",
            ).pack(padx=14, pady=10)
            # Avoid update_idletasks here — forces full layout and freezes after delete/rebuild
            fr.place(relx=0.98, rely=0.06, anchor="ne")
            self.after(ms, lambda: self._destroy_toast(fr))
        except Exception:  # noqa: BLE001
            pass

    def _destroy_toast(self, fr: Any) -> None:
        try:
            if getattr(self, "_toast_win", None) is fr:
                self._toast_win = None
            fr.destroy()
        except Exception:  # noqa: BLE001
            pass

    def _tooltip(self, widget: Any, text: str) -> None:
        """Attach a friendly hover tooltip to a widget (safe no-op on failure)."""
        try:
            add_tooltip(widget, text)
        except Exception:  # noqa: BLE001
            pass

    def _smooth_scroll(self, scrollable: Any) -> None:
        """Apply smooth mousewheel/trackpad scrolling to a scrollable frame (safe)."""
        try:
            apply_smooth_scroll(scrollable, animate=True, momentum=True)
        except Exception:  # noqa: BLE001
            pass
    def _page_header(
        self,
        parent: Any,
        title: str,
        subtitle: str = "",
        *,
        row: int = 0,
        columnspan: int = 1,
        actions: list[tuple[str, Any]] | None = None,
    ) -> None:
        """Consistent page title bar used across admin pages."""
        from app.ui.themes import UI as _UI, style_chrome_button, style_card

        bar = ctk.CTkFrame(parent, **style_card())
        bar.grid(row=row, column=0, columnspan=max(1, columnspan), sticky="ew", pady=(0, 12))
        if hasattr(parent, "grid_columnconfigure"):
            try:
                parent.grid_columnconfigure(0, weight=1)
            except Exception:  # noqa: BLE001
                pass
        left = ctk.CTkFrame(bar, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True, padx=14, pady=12)
        ctk.CTkLabel(
            left, text=title, font=("Segoe UI", 20, "bold"), text_color=_UI["label"]
        ).pack(anchor="w")
        if subtitle:
            ctk.CTkLabel(
                left,
                text=subtitle,
                text_color=_UI["muted"],
                font=("Segoe UI", 12),
                wraplength=720,
                justify="left",
            ).pack(anchor="w", pady=(2, 0))
        if actions:
            right = ctk.CTkFrame(bar, fg_color="transparent")
            right.pack(side="right", padx=12, pady=10)
            for i, (lab, cmd) in enumerate(actions):
                ctk.CTkButton(
                    right,
                    text=lab,
                    width=100,
                    height=30,
                    command=cmd,
                    **style_chrome_button(primary=(i == 0)),
                ).pack(side="left", padx=3)

    def _bind_global_shortcuts(self) -> None:
        """Keyboard shortcuts for power users."""
        self.bind_all("<Control-n>", lambda _e: self._shortcut_new_chat())
        self.bind_all("<Control-N>", lambda _e: self._shortcut_new_chat())
        self.bind_all("<Control-e>", lambda _e: self._shortcut_export_chat())
        self.bind_all("<Control-E>", lambda _e: self._shortcut_export_chat())
        self.bind_all("<Control-l>", lambda _e: self._shortcut_clear_log())
        self.bind_all("<Control-L>", lambda _e: self._shortcut_clear_log())
        self.bind_all("<Control-m>", lambda _e: self._shortcut_mic())
        self.bind_all("<Control-M>", lambda _e: self._shortcut_mic())
        self.bind_all("<Control-b>", lambda _e: self._shortcut_branch())
        self.bind_all("<Control-B>", lambda _e: self._shortcut_branch())
        self.bind_all("<Control-p>", lambda _e: self._shortcut_pin())
        self.bind_all("<Control-P>", lambda _e: self._shortcut_pin())
        self.bind_all("<Control-Shift-T>", lambda _e: self._shortcut_cycle_theme())
        self.bind_all("<Control-Shift-t>", lambda _e: self._shortcut_cycle_theme())
        self.bind_all("<Control-g>", lambda _e: self._shortcut_image_gen())
        self.bind_all("<Control-G>", lambda _e: self._shortcut_image_gen())
        self.bind_all("<F1>", lambda _e: self._show_shortcuts_help())
        self.bind_all("<F2>", lambda _e: self.show_page("Help"))
        self.bind_all("<Control-Shift-A>", lambda _e: self.show_page("Approvals"))
        self.bind_all("<Control-s>", lambda _e: self._shortcut_save())
        self.bind_all("<Control-S>", lambda _e: self._shortcut_save())
        self.bind_all("<Control-k>", lambda _e: self._open_command_palette())
        self.bind_all("<Control-K>", lambda _e: self._open_command_palette())
        self.bind_all("<Control-backslash>", lambda _e: self._toggle_focus_mode())
        self.bind_all("<Escape>", lambda _e: self._focus_mode_off())

    def _start_autosave_timer(self) -> None:
        """Crash-safe periodic chat autosave every 30s."""

        def tick() -> None:
            try:
                if self.winfo_exists() and getattr(self, "_chat_state", None):
                    if self._chat_state.get("id") and self._chat_state.get("messages") is not None:
                        chat_svc.save_chat(self._chat_state)
            except Exception:  # noqa: BLE001
                pass
            try:
                if self.winfo_exists():
                    self.after(30000, tick)
            except Exception:  # noqa: BLE001
                pass

        self.after(30000, tick)

    def _start_status_refresh(self) -> None:
        """Periodic status bar refresh with system metrics (every 3s)."""

        def tick() -> None:
            try:
                if self.winfo_exists():
                    self.set_status()  # calls _status_text() which now includes hardware
            except Exception:  # noqa: BLE001
                pass
            try:
                if self.winfo_exists():
                    self.after(3000, tick)
            except Exception:  # noqa: BLE001
                pass

        self.after(3000, tick)

    def _start_task_watch(self) -> None:
        """Keep Task/LLM chips live and auto-continue when the model goes idle."""
        if getattr(self, "_task_watch_started", False):
            return
        self._task_watch_started = True

        def tick() -> None:
            try:
                if self.winfo_exists():
                    self._task_watch_tick()
            except Exception:  # noqa: BLE001
                pass
            try:
                if self.winfo_exists():
                    self.after(2500, tick)
            except Exception:  # noqa: BLE001
                pass

        self.after(2000, tick)

    def _bind_tool_approvals(self) -> None:
        try:
            from app.services import tool_approvals

            def on_change() -> None:
                try:
                    self.after(0, self._on_approvals_changed)
                except Exception:  # noqa: BLE001
                    pass

            tool_approvals.add_listener(on_change)
        except Exception:  # noqa: BLE001
            pass

    def _start_native_background_services(self) -> None:
        """Clipboard watch, file watcher, scheduler — non-blocking."""
        try:
            from app.services import clipboard_watch, file_watcher, scheduler_service

            clipboard_watch.start()

            def on_clip(ev: dict) -> None:
                def ui() -> None:
                    if not self.winfo_exists():
                        return
                    kind = ev.get("kind")
                    if kind in ("file_paths", "image_paths") and ev.get("paths"):
                        try:
                            from app.core.services.misc.attachments import sanitize_attachment_paths

                            ev_paths = sanitize_attachment_paths(list(ev.get("paths") or []))
                        except Exception:  # noqa: BLE001
                            ev_paths = list(ev.get("paths") or [])
                        for p in ev_paths:
                            if p not in self._chat_attachments:
                                self._chat_attachments.append(p)
                            if kind == "image_paths":
                                imgs = getattr(self, "_pending_images", [])
                                if p not in imgs:
                                    imgs.append(p)
                                self._pending_images = imgs
                        self._update_composer_status()
                        self.set_status(f"Clipboard: attached {len(ev.get('paths') or [])} path(s)")
                    elif kind == "url":
                        self.set_status(f"Clipboard URL: {str(ev.get('text') or '')[:60]}")

                try:
                    self.after(0, ui)
                except Exception:  # noqa: BLE001
                    pass

            clipboard_watch.add_listener(on_clip)
            if file_watcher.load_watches():
                file_watcher.start()
            if scheduler_service.load_schedules():
                scheduler_service.start()
        except Exception:  # noqa: BLE001
            pass
        # Task #13: global hotkey ask-about-clipboard
        try:
            from app.services import global_hotkeys

            def on_hotkey(ev: dict) -> None:
                def ui() -> None:
                    if not self.winfo_exists():
                        return
                    if ev.get("type") == "ask_clipboard":
                        self._ask_about_clipboard(str(ev.get("text") or ""), source=str(ev.get("label") or ""))
                    elif ev.get("type") == "error":
                        self.set_status(f"Hotkey: {ev.get('error')}", toast=True)

                try:
                    self.after(0, ui)
                except Exception:  # noqa: BLE001
                    pass

            global_hotkeys.set_listener(on_hotkey)
            if global_hotkeys.start():
                self.set_status("Hotkey Ctrl+Shift+G: ask about clipboard", toast=False)
        except Exception:  # noqa: BLE001
            pass

    def _ask_about_clipboard(self, text: str = "", *, source: str = "") -> None:
        """Bring Studio to front and prefill Chat with clipboard content (Task #13)."""
        def _clear_topmost() -> None:
            try:
                if self.winfo_exists():
                    self.attributes("-topmost", False)
            except Exception:  # noqa: BLE001
                pass

        try:
            self.deiconify()
            self.lift()
            self.focus_force()
            try:
                self.attributes("-topmost", True)
                # Schedule cleanup; also bind to <Map> as a safety net in case after() doesn't fire
                self.after(200, _clear_topmost)
                self.bind("<Map>", lambda e: _clear_topmost(), add=True)
            except Exception:  # noqa: BLE001
                _clear_topmost()
        except Exception:  # noqa: BLE001
            _clear_topmost()
        clip = (text or "").strip()
        if not clip:
            try:
                from app.core.services.system.clipboard_watch import _read_clipboard_text

                clip = (_read_clipboard_text() or "").strip()
            except Exception:  # noqa: BLE001
                clip = ""
        if not clip:
            self.set_status("Clipboard is empty — copy text first, then Ctrl+Shift+G", toast=True)
            return
        # Truncate huge pastes for the composer
        body = clip if len(clip) <= 6000 else clip[:6000] + "\n…(truncated)"
        prompt = (
            "Please explain or help me with the following (from my clipboard"
            + (f" via {source}" if source else "")
            + "):\n\n"
            + body
        )
        try:
            if self._current_page != "Chat":
                self.show_page("Chat")
        except Exception:  # noqa: BLE001
            pass

        def fill() -> None:
            try:
                if hasattr(self, "chat_input"):
                    self._composer_is_placeholder = False
                    self.chat_input.delete("1.0", "end")
                    self.chat_input.insert("1.0", prompt)
                    from app.ui.themes import UI as _UI

                    self.chat_input.configure(text_color=_UI["label"])
                    self._update_composer_status()
                    self.chat_input.focus_set()
            except Exception:  # noqa: BLE001
                pass

        try:
            self.after(150, fill)
        except Exception:  # noqa: BLE001
            fill()
        self.set_status(
            "Clipboard ready in chat — press Send (or edit first)",
            toast=True,
        )

    def _on_approvals_changed(self) -> None:
        try:
            n = self._approval_badge_count()
            self._refresh_nav_badges()
            if n:
                self.set_status(
                    f"⏳ {n} approval(s) waiting — open Approvals (Ctrl+Shift+A)",
                    toast=True,
                )
            if self._current_page == "Approvals":
                self.show_page("Approvals")
        except Exception:  # noqa: BLE001
            pass

    def _shortcut_new_chat(self) -> None:
        self._open_new_chat(source="Ctrl+N")

    def _shortcut_export_chat(self) -> None:
        if self._current_page == "Chat" or True:
            try:
                self._chat_export()
            except Exception:  # noqa: BLE001
                pass

    def _shortcut_clear_log(self) -> None:
        try:
            self._clear_activity()
        except Exception:  # noqa: BLE001
            pass

    def _shortcut_mic(self) -> None:
        try:
            self._chat_mic()
        except Exception:  # noqa: BLE001
            pass

    def _shortcut_branch(self) -> None:
        try:
            self._chat_branch()
        except Exception:  # noqa: BLE001
            pass

    def _shortcut_pin(self) -> None:
        try:
            self._chat_toggle_pin()
        except Exception:  # noqa: BLE001
            pass

    def _shortcut_cycle_theme(self) -> None:
        try:
            from app.ui.themes import theme_names, apply_theme

            names = theme_names()
            cur = self.cfg.get("ui_theme") or "Dark Blue"
            i = names.index(cur) if cur in names else 0
            nxt = names[(i + 1) % len(names)]
            apply_theme(nxt)
            self.cfg["ui_theme"] = nxt
            storage.save_config(self.cfg)
            self.set_status(f"Theme: {nxt} (Ctrl+Shift+T)")
        except Exception as e:  # noqa: BLE001
            self.set_status(f"Theme cycle failed: {e}")

    def _shortcut_image_gen(self) -> None:
        try:
            self._chat_image_gen_dialog()
        except Exception:  # noqa: BLE001
            pass

    def _shortcut_save(self) -> None:
        """Ctrl+S: page-aware save (form pages) or chat save."""
        page = str(getattr(self, "_current_page", "") or "")
        handler = getattr(self, "_page_save_handler", None)
        if callable(handler) and page in (
            "Agents",
            "Tasks",
            "Settings",
            "Memory",
            "Projects",
            "Schedule",
            "Org chart",
            "Company",
        ):
            try:
                handler()
                return
            except Exception as e:  # noqa: BLE001
                self.set_status(f"Save failed: {e}")
                return
        try:
            chat_svc.save_chat(self._chat_state)
            self.set_status("Chat saved (Ctrl+S)")
        except Exception as e:  # noqa: BLE001
            self.set_status(f"Save failed: {e}")

    def _show_shortcuts_help(self) -> None:
        win = ctk.CTkToplevel(self)
        win.title("Keyboard shortcuts")
        win.geometry("480x420")
        win.transient(self)
        text = (
            "Ctrl+N     New chat\n"
            "Ctrl+K     Command palette (pages + actions)\n"
            "Ctrl+\\    Focus mode (hide sidebar)\n"
            "Esc        Exit focus mode\n"
            "Ctrl+S     Save chat / current form (Agents, Tasks, …)\n"
            "Ctrl+E     Export chat\n"
            "Ctrl+L     Clear activity log\n"
            "Ctrl+M     Mic / speech-to-text\n"
            "Ctrl+B     Branch (fork) chat\n"
            "Ctrl+P     Pin / unpin chat\n"
            "Ctrl+G     Generate image\n"
            "Ctrl+Shift+T  Cycle UI theme\n"
            "Ctrl+Shift+A  Approvals queue\n"
            "Enter      Send message\n"
            "Shift+Enter  Newline\n"
            "F1         Keyboard list\n"
            "F2         How-to Help guide\n"
            "Ctrl+\\    Focus mode\n"
            "\n"
            "Slash (composer):\n"
            "  /plan  /action  /image …  /search …\n"
            "  /stop  /caps  /live  /new  /help\n"
            "  /compact  (toggle density)\n"
            "\n"
            "Hash inject (composer):\n"
            "  #filename.md   knowledge / local file\n"
            "  #./path/file   relative or absolute path\n"
            "  #https://…     fetch URL into this turn\n"
            "\n"
            "Chat: + menu · Mode/Tasks/Caps chips · tool traces\n"
            "Self-improve: BACKUP / SELF_IMPROVE blocks\n"
        )
        ctk.CTkLabel(win, text="Keyboard shortcuts", font=ctk.CTkFont(size=16, weight="bold")).pack(
            pady=12
        )
        box = ctk.CTkTextbox(win, font=ctk.CTkFont(family="Consolas", size=13))
        box.pack(fill="both", expand=True, padx=16, pady=8)
        box.insert("1.0", text)
        box.configure(state="disabled")
        ctk.CTkButton(win, text="Close", command=win.destroy).pack(pady=8)

    def _ensure_window_resize_ok(self) -> None:
        """Keep native frame resizable (edge drag). Single pass — no double after() flash."""
        try:
            self.resizable(True, True)
            self.wm_resizable(True, True)
            self.minsize(720, 480)
            try:
                if bool(self.attributes("-fullscreen")):
                    self.attributes("-fullscreen", False)
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            pass

    def _build_window_controls(self) -> None:
        """Deprecated: OS title bar owns min/max/close. Kept as alias for callers."""
        self._ensure_window_resize_ok()

    def _is_simple_ui(self) -> bool:
        """Simple UI: few menu items + guided Home. Default ON for clarity."""
        try:
            cfg = self.cfg if isinstance(getattr(self, "cfg", None), dict) else storage.load_config()
            # Default True — power users turn off in Home or Settings
            return bool(cfg.get("simple_ui", True))
        except Exception:  # noqa: BLE001
            return True

    def _set_simple_ui(self, on: bool) -> None:
        cfg = storage.load_config()
        cfg["simple_ui"] = bool(on)
        storage.save_config(cfg)
        self.cfg = cfg
        # Rebuild sidebar + stay on Home
        try:
            self._build_sidebar()
        except Exception:  # noqa: BLE001
            pass
        self.show_page("Home")
        from app.ui.components.layman_copy import STATUS_SIMPLE_ON, STATUS_EXPERT_ON

        self.set_status(STATUS_SIMPLE_ON if on else STATUS_EXPERT_ON, toast=True)

    def _nav_hubs(self) -> list[tuple[str, tuple[str, ...]]]:
        """Simple mode: 5 pages only. Full mode: Primary + Workspace + More."""
        if self._is_simple_ui():
            return [
                (
                    "MENU",
                    ("Home", "Chat", "Team", "Models", "Monitor"),
                ),
            ]
        return [
            ("PRIMARY", ("Home", "Chat", "Team", "Models", "Monitor", "Help")),
            ("WORKSPACE", ("Work", "Approvals", "Knowledge", "Notes", "Org chart")),
            (
                "MORE",
                (
                    "Chats",
                    "Track",
                    "Company",
                    "CEO",
                    "Schedule",
                    "Patches",
                    "Agents",
                    "Tasks",
                    "Runs",
                    "Projects",
                    "Memory",
                    "Usage",
                    "Settings",
                    "About",
                ),
            ),
        ]

    def _approval_badge_count(self) -> int:
        n = 0
        try:
            from app.services import tool_approvals

            n += len(tool_approvals.list_pending())
        except Exception:  # noqa: BLE001
            pass
        try:
            from app.services import company_store as company

            n += len(company.list_approvals(status="pending") or [])
        except Exception:  # noqa: BLE001
            pass
        return n

    def _patches_badge_count(self) -> int:
        try:
            from app.services import patch_review

            return len(patch_review.list_pending() or [])
        except Exception:  # noqa: BLE001
            return 0

    def _work_running_count(self) -> int:
        n = 0
        try:
            from app.services import company_store as company

            for t in company.list_work_tasks() or []:
                st = str(t.get("status") or "").lower()
                if st in ("running", "in_progress", "active"):
                    n += 1
        except Exception:  # noqa: BLE001
            pass
        return n

    def _nav_label_for(self, name: str) -> str:
        from app.ui.themes import nav_icon
        from app.ui.components.layman_copy import friendly_name

        icon = nav_icon(name)
        label = friendly_name(name, simple=self._is_simple_ui())
        if name == "Approvals":
            n = self._approval_badge_count()
            return f" {icon}  {label}  ({n})" if n else f" {icon}  {label}"
        if name == "Patches":
            n = self._patches_badge_count()
            return f" {icon}  {label}  ({n})" if n else f" {icon}  {label}"
        if name == "Work":
            n = self._work_running_count()
            return f" {icon}  {label}  ({n} run)" if n else f" {icon}  {label}"
        return f" {icon}  {label}"

    def _build_menu_expander(self) -> None:
        """Thin ☰ strip when the left menu is collapsed — always a way back."""
        from app.ui.themes import UI, style_chrome_button

        exp = ctk.CTkFrame(self, width=40, corner_radius=0, fg_color=UI["sidebar_bg"])
        exp.grid(row=0, column=0, sticky="nsw")
        exp.grid_propagate(False)
        exp.grid_remove()
        self._menu_expander = exp
        btn = ctk.CTkButton(
            exp,
            text="☰",
            width=32,
            height=36,
            corner_radius=8,
            command=self._expand_app_menu,
            **style_chrome_button(primary=True),
        )
        btn.pack(padx=4, pady=(10, 4))
        self._tooltip(btn, "Show the left menu (Home, Chat, Team…).")
        exit_btn = ctk.CTkButton(
            exp,
            text="▣",
            width=32,
            height=36,
            corner_radius=8,
            command=lambda: self._set_one_screen(False),
            **style_chrome_button(),
        )
        exit_btn.pack(padx=4, pady=4)
        self._tooltip(exit_btn, "Exit one-screen view and show the full layout.")

    def _persist_chrome(self) -> None:
        try:
            cfg = storage.load_config()
            cfg["chat_one_screen"] = bool(getattr(self, "_one_screen", False))
            cfg["sidebar_collapsed"] = bool(getattr(self, "_sidebar_collapsed", False))
            cfg["sysmon_collapsed"] = bool(getattr(self, "_sysmon_collapsed", False))
            cfg["chat_rail_collapsed"] = bool(getattr(self, "_chat_rail_collapsed", False))
            storage.save_config(cfg)
            self.cfg = cfg
        except Exception:  # noqa: BLE001
            pass

    def _sidebar_alive(self) -> bool:
        try:
            w = getattr(self, "_sidebar_frame", None)
            return w is not None and bool(w.winfo_exists())
        except Exception:  # noqa: BLE001
            return False

    def _sidebar_has_content(self) -> bool:
        if not self._sidebar_alive():
            return False
        if not getattr(self, "_nav_buttons", None):
            return False
        try:
            return bool(self._sidebar_frame.winfo_children())
        except Exception:  # noqa: BLE001
            return False

    def _ensure_app_sidebar(self) -> None:
        """Always show either the full menu or the ☰ strip — never a white hole."""
        hidden = bool(getattr(self, "_sidebar_collapsed", False)) or bool(
            getattr(self, "_one_screen", False)
        )
        if hidden:
            try:
                if self._sidebar_alive():
                    self._sidebar_frame.grid_remove()
            except Exception:  # noqa: BLE001
                pass
            exp = getattr(self, "_menu_expander", None)
            try:
                if exp is None or not bool(exp.winfo_exists()):
                    self._build_menu_expander()
                    exp = self._menu_expander
                exp.grid(row=0, column=0, sticky="nsw")
            except Exception:  # noqa: BLE001
                pass
            return
        if not self._sidebar_has_content():
            try:
                self._build_sidebar()
            except Exception:  # noqa: BLE001
                pass
        else:
            try:
                self._sidebar_frame.grid(row=0, column=0, sticky="nsw")
            except Exception:  # noqa: BLE001
                try:
                    self._build_sidebar()
                except Exception:  # noqa: BLE001
                    pass
        exp = getattr(self, "_menu_expander", None)
        try:
            if exp is not None and bool(exp.winfo_exists()):
                exp.grid_remove()
        except Exception:  # noqa: BLE001
            pass

    def _set_app_menu_collapsed(self, hidden: bool, *, persist: bool = True) -> None:
        self._sidebar_collapsed = bool(hidden)
        self._ensure_app_sidebar()
        if persist:
            self._persist_chrome()
        self._refresh_view_buttons()

    def _set_sysmon_collapsed(self, hidden: bool, *, persist: bool = True) -> None:
        self._sysmon_collapsed = bool(hidden)
        bar = getattr(self, "_sysmon_bar", None)
        try:
            if bar is not None:
                if hidden:
                    bar.grid_remove()
                else:
                    bar.grid()
        except Exception:  # noqa: BLE001
            pass
        if persist:
            self._persist_chrome()
        self._refresh_view_buttons()

    def _collapse_app_menu(self) -> None:
        self._set_app_menu_collapsed(True)
        self.set_status("Menu hidden — click ☰ on the left to show it")

    def _expand_app_menu(self) -> None:
        self._one_screen = False
        self._focus_mode = False
        self._set_app_menu_collapsed(False)
        self.set_status("Menu shown")

    def _toggle_app_menu(self) -> None:
        if bool(getattr(self, "_sidebar_collapsed", False)):
            self._expand_app_menu()
        else:
            self._collapse_app_menu()

    def _toggle_sysmon_bar(self) -> None:
        nxt = not bool(getattr(self, "_sysmon_collapsed", False))
        self._set_sysmon_collapsed(nxt)
        self.set_status("CPU bar hidden" if nxt else "CPU bar shown")

    def _set_one_screen(self, on: bool) -> None:
        """One-screen view: hide chrome in place. Do not rebuild Chat (that wiped messages)."""
        on = bool(on)
        self._one_screen = on
        self._focus_mode = on
        rail = getattr(self, "_chat_rail_frame", None)
        if on:
            self._set_app_menu_collapsed(True, persist=False)
            self._set_sysmon_collapsed(True, persist=False)
            self._chat_rail_collapsed = True
            try:
                if rail is not None:
                    rail.grid_remove()
            except Exception:  # noqa: BLE001
                pass
            # Keep Live / Thinking / Terminal visible — that is the monitor
            try:
                self._ensure_live_monitor_open(tab="Terminal")
            except Exception:  # noqa: BLE001
                pass
            try:
                if bool(getattr(self, "_chat_setup_expanded", False)):
                    self._chat_toggle_setup_panel()
            except Exception:  # noqa: BLE001
                pass
            if getattr(self, "_chat_density", "compact") != "compact":
                self._chat_density = "compact"
                try:
                    self._apply_chat_density_layout()
                except Exception:  # noqa: BLE001
                    pass
            self._persist_chrome()
            self._refresh_view_buttons()
            self.set_status("One-screen view — Esc, ☰, or Exit one-screen restores the menu")
        else:
            self._set_app_menu_collapsed(False, persist=False)
            self._set_sysmon_collapsed(False, persist=False)
            self._chat_rail_collapsed = False
            self._persist_chrome()
            self._refresh_view_buttons()
            # Rail may have been built as a 52px icon strip with no list.
            # Rebuild Chat so the full history list comes back.
            if getattr(self, "_chat_rail_list", None) is None:
                self.show_page("Chat", rebuild=True)
            else:
                self._apply_chat_rail_layout()
            self.set_status("Full view — menu and chat list are back")

    def _toggle_one_screen(self) -> None:
        self._set_one_screen(not bool(getattr(self, "_one_screen", False)))

    def _toggle_focus_mode(self) -> None:
        """Ctrl+\\ — same as One-screen view."""
        self._toggle_one_screen()

    def _restore_focus_sidebars(self) -> None:
        self._set_one_screen(False)

    def _focus_mode_off(self) -> None:
        if getattr(self, "_one_screen", False) or getattr(self, "_focus_mode", False):
            self._set_one_screen(False)

    def _apply_saved_chrome(self) -> None:
        if bool(getattr(self, "_one_screen", False)):
            self._set_one_screen(True)
            return
        self._set_app_menu_collapsed(bool(getattr(self, "_sidebar_collapsed", False)), persist=False)
        self._set_sysmon_collapsed(bool(getattr(self, "_sysmon_collapsed", False)), persist=False)

    def _build_chat_view_bar(self, root: Any) -> None:
        """Always-visible collapse / expand / one-screen controls."""
        from app.ui.themes import UI as _UI, style_chrome_button

        bar = ctk.CTkFrame(
            root,
            height=46,
            corner_radius=0,
            fg_color=_UI.get("top_bg", _UI["chat_bg"]),
            border_width=1,
            border_color=_UI.get("top_border", ("#e5e5e5", "#2a2a2a")),
        )
        bar.grid(row=0, column=0, columnspan=2, sticky="ew")
        bar.grid_propagate(False)
        self._chat_view_bar = bar
        hid_menu = bool(getattr(self, "_sidebar_collapsed", False))
        self._menu_toggle_btn = ctk.CTkButton(
            bar,
            text="☰ Show menu" if hid_menu else "☰ Hide menu",
            width=108,
            height=30,
            command=self._toggle_app_menu,
            **style_chrome_button(),
        )
        self._menu_toggle_btn.pack(side="left", padx=(8, 4), pady=7)
        self._tooltip(self._menu_toggle_btn, chat_control_help("collapse_menu"))
        hid_chats = bool(getattr(self, "_chat_rail_collapsed", False))
        self._chats_toggle_btn = ctk.CTkButton(
            bar,
            text="Show chats" if hid_chats else "Hide chats",
            width=92,
            height=30,
            command=self._chat_toggle_history_rail,
            **style_chrome_button(),
        )
        self._chats_toggle_btn.pack(side="left", padx=3, pady=7)
        self._tooltip(self._chats_toggle_btn, chat_control_help("collapse_chats"))
        one = bool(getattr(self, "_one_screen", False))
        self._one_screen_btn = ctk.CTkButton(
            bar,
            text="Exit one-screen" if one else "One screen",
            width=120,
            height=30,
            command=self._toggle_one_screen,
            **style_chrome_button(primary=True),
        )
        self._one_screen_btn.pack(side="left", padx=3, pady=7)
        self._tooltip(self._one_screen_btn, chat_control_help("one_screen"))
        self._cpu_toggle_btn = ctk.CTkButton(
            bar,
            text="CPU bar",
            width=72,
            height=30,
            command=self._toggle_sysmon_bar,
            **style_chrome_button(),
        )
        self._cpu_toggle_btn.pack(side="left", padx=3, pady=7)
        self._tooltip(self._cpu_toggle_btn, chat_control_help("collapse_cpu"))

    def _build_chat_cycle_bar(self, root: Any) -> None:
        """Always-visible Task / LLM status plus Run cycle / Stop cycle."""
        from app.ui.themes import UI as _UI, style_chrome_button

        bar = ctk.CTkFrame(
            root,
            height=40,
            corner_radius=0,
            fg_color=_UI.get("top_bg", _UI["chat_bg"]),
            border_width=1,
            border_color=_UI.get("top_border", ("#e5e5e5", "#2a2a2a")),
        )
        bar.grid(row=1, column=0, columnspan=2, sticky="ew")
        bar.grid_propagate(False)
        self._chat_cycle_bar = bar
        self._cycle_run_btn = ctk.CTkButton(
            bar,
            text="▶ Run cycle",
            width=108,
            height=28,
            corner_radius=8,
            command=self._start_task_cycle,
            **style_chrome_button(primary=True),
        )
        self._cycle_run_btn.pack(side="left", padx=(8, 3), pady=5)
        self._tooltip(
            self._cycle_run_btn,
            "Start the cycle: if the task is still open and the model goes idle, send Continue",
        )
        self._cycle_stop_btn = ctk.CTkButton(
            bar,
            text="■ Stop cycle",
            width=110,
            height=28,
            corner_radius=8,
            command=self._stop_task_cycle,
            fg_color=("#d1d5db", "#3f3f46"),
            hover_color=("#9ca3af", "#27272a"),
            text_color=("#52525b", "#a1a1aa"),
            state="disabled",
        )
        self._cycle_stop_btn.pack(side="left", padx=3, pady=5)
        self._tooltip(self._cycle_stop_btn, "Stop the watch cycle and the current model turn")
        self._task_status_btn = ctk.CTkButton(
            bar,
            text="Task · none",
            width=148,
            height=28,
            corner_radius=8,
            command=self._toggle_task_achieved,
            **style_chrome_button(primary=True),
        )
        self._task_status_btn.pack(side="left", padx=(14, 3), pady=5)
        self._tooltip(
            self._task_status_btn,
            "Task open or achieved. Click to mark done / reopen.",
        )
        self._llm_status_lbl = ctk.CTkLabel(
            bar,
            text="LLM · idle",
            width=128,
            height=28,
            corner_radius=8,
            fg_color=("#e5e7eb", "#27272a"),
            text_color=_UI.get("label", ("#111", "#eee")),
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self._llm_status_lbl.pack(side="left", padx=3, pady=5)
        self._tooltip(self._llm_status_lbl, "Current model state: working, idle, paused, or error")
        self._from_start_btn = ctk.CTkButton(
            bar,
            text="From start",
            width=96,
            height=28,
            corner_radius=8,
            command=self._chat_show_from_start,
            **style_chrome_button(),
        )
        self._from_start_btn.pack(side="left", padx=(14, 3), pady=5)
        self._tooltip(self._from_start_btn, "Scroll the whole chat from the first message")
        self._ctx_open_btn = ctk.CTkButton(
            bar,
            text="Context",
            width=86,
            height=28,
            corner_radius=8,
            command=self._chat_context_window_dialog,
            **style_chrome_button(primary=True),
        )
        self._ctx_open_btn.pack(side="left", padx=(10, 3), pady=5)
        self._tooltip(
            self._ctx_open_btn,
            "Context window size and the exact prompt text the model will see — both editable",
        )
        self._ctx_chip_lbl = ctk.CTkLabel(
            bar,
            text="ctx …",
            width=150,
            height=28,
            anchor="w",
            font=ctk.CTkFont(size=12),
            text_color=_UI.get("muted", ("#6b7280", "#9ca3af")),
        )
        self._ctx_chip_lbl.pack(side="left", padx=4, pady=5)
        try:
            self._refresh_context_chip()
        except Exception:  # noqa: BLE001
            pass
        try:
            self._refresh_task_llm_chips()
        except Exception:  # noqa: BLE001
            pass

    def _build_chat_goal_banner(self, root: Any) -> None:
        """Top strip: pending/working/done + the current LLM goal."""
        from app.ui.themes import UI as _UI

        bar = ctk.CTkFrame(
            root,
            height=88,
            corner_radius=0,
            fg_color=("#fff7ed", "#1c1917"),
            border_width=1,
            border_color=_UI.get("top_border", ("#e5e5e5", "#2a2a2a")),
        )
        bar.grid(row=2, column=0, columnspan=2, sticky="ew")
        bar.grid_propagate(False)
        self._chat_goal_bar = bar
        self._findings_lbl = ctk.CTkLabel(
            bar,
            text="Findings · (none yet — tools will list errors and edits here)",
            anchor="w",
            justify="left",
            font=ctk.CTkFont(size=12),
            text_color=("#9a3412", "#fdba74"),
        )
        self._findings_lbl.pack(side="bottom", fill="x", padx=10, pady=(0, 4))
        try:
            self._findings_lbl.bind("<Button-1>", lambda _e: self._open_findings_window())
            self._tooltip(self._findings_lbl, "Click to open the findings list — check = still open")
        except Exception:  # noqa: BLE001
            pass
        try:
            from app.ui.themes import style_chrome_button as _scb

            self._findings_btn = ctk.CTkButton(
                bar,
                text="Findings",
                width=78,
                height=26,
                command=self._open_findings_window,
                **_scb(primary=True),
            )
            self._findings_btn.pack(side="right", padx=(4, 8), pady=(4, 0))
        except Exception:  # noqa: BLE001
            pass
        self._now_doing_lbl = ctk.CTkLabel(
            bar,
            text="NOW · waiting for the model…",
            anchor="w",
            justify="left",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=("#1d4ed8", "#93c5fd"),
        )
        self._now_doing_lbl.pack(side="bottom", fill="x", padx=10, pady=(0, 2))
        self._goal_status_lbl = ctk.CTkLabel(
            bar,
            text="NONE",
            width=86,
            height=26,
            corner_radius=8,
            fg_color=("#e5e7eb", "#27272a"),
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self._goal_status_lbl.pack(side="left", padx=(8, 6), pady=(4, 0))
        self._goal_summary_lbl = ctk.CTkLabel(
            bar,
            text="Goal: (none yet)",
            anchor="w",
            justify="left",
            font=ctk.CTkFont(size=13),
            text_color=_UI.get("label", ("#111", "#eee")),
        )
        self._goal_summary_lbl.pack(side="left", fill="x", expand=True, padx=(0, 8), pady=(4, 0))
        self._tooltip(self._goal_status_lbl, "Click the goal text to edit what the model should pursue")
        try:
            self._goal_summary_lbl.bind("<Button-1>", lambda _e: self._edit_current_goal())
        except Exception:  # noqa: BLE001
            pass
        try:
            self._refresh_goal_banner()
        except Exception:  # noqa: BLE001
            pass

    def _refresh_view_buttons(self) -> None:
        one = bool(getattr(self, "_one_screen", False))
        try:
            if hasattr(self, "_one_screen_btn") and self._one_screen_btn.winfo_exists():
                from app.ui.themes import style_chrome_button

                self._one_screen_btn.configure(
                    text="Exit one-screen" if one else "One screen",
                    **style_chrome_button(primary=one),
                )
        except Exception:  # noqa: BLE001
            pass
        try:
            if hasattr(self, "_menu_toggle_btn") and self._menu_toggle_btn.winfo_exists():
                hid = bool(getattr(self, "_sidebar_collapsed", False))
                self._menu_toggle_btn.configure(text="☰ Show menu" if hid else "☰ Hide menu")
        except Exception:  # noqa: BLE001
            pass
        try:
            if hasattr(self, "_chats_toggle_btn") and self._chats_toggle_btn.winfo_exists():
                hid = bool(getattr(self, "_chat_rail_collapsed", False))
                self._chats_toggle_btn.configure(text="Show chats" if hid else "Hide chats")
        except Exception:  # noqa: BLE001
            pass
        try:
            self._refresh_task_llm_chips()
        except Exception:  # noqa: BLE001
            pass

    def _task_user_pin(self) -> str | None:
        try:
            pin = str((self._chat_state or {}).get("task_status_user_pin") or "").strip().lower()
        except Exception:  # noqa: BLE001
            pin = ""
        return pin or None

    def _refresh_task_llm_chips(self) -> None:
        from app.core.services.chat.task_watch import (
            LLM_ERROR,
            LLM_IDLE,
            LLM_PAUSED,
            LLM_WORKING,
            TASK_ACHIEVED,
            TASK_BLOCKED,
            TASK_NONE,
            TASK_OPEN,
            infer_llm_status,
            infer_task_status,
            llm_chip_label,
            task_chip_label,
        )

        last_err = False
        try:
            msgs = list((self._chat_state or {}).get("messages") or [])
            if msgs and (msgs[-1].get("role") or "") == "error":
                last_err = True
        except Exception:  # noqa: BLE001
            msgs = []
        task = infer_task_status(
            msgs,
            user_pin=self._task_user_pin(),
            auto_count=int(getattr(self, "_auto_continue_count", 0) or 0),
        )
        llm = infer_llm_status(
            busy=bool(getattr(self, "_chat_busy", False)),
            paused=bool(getattr(self, "_chat_paused", False)),
            last_error=last_err,
        )
        self._task_status = task
        self._llm_phase = llm
        task_colors = {
            TASK_OPEN: (("#fff7ed", "#7c2d12"), ("#9a3412", "#fdba74")),
            TASK_ACHIEVED: (("#d1fae5", "#064e3b"), ("#065f46", "#6ee7b7")),
            TASK_BLOCKED: (("#fee2e2", "#7f1d1d"), ("#991b1b", "#fecaca")),
            TASK_NONE: (("#f3f4f6", "#27272a"), ("#52525b", "#a1a1aa")),
        }
        llm_colors = {
            LLM_WORKING: ("#dbeafe", "#1e3a8a"),
            LLM_PAUSED: ("#fef3c7", "#78350f"),
            LLM_ERROR: ("#fee2e2", "#7f1d1d"),
            LLM_IDLE: ("#e5e7eb", "#27272a"),
        }
        try:
            btn = getattr(self, "_task_status_btn", None)
            if btn is not None and btn.winfo_exists():
                bg, fg = task_colors.get(task, task_colors[TASK_NONE])
                btn.configure(text=task_chip_label(task), fg_color=bg, text_color=fg)
        except Exception:  # noqa: BLE001
            pass
        try:
            lbl = getattr(self, "_llm_status_lbl", None)
            if lbl is not None and lbl.winfo_exists():
                lbl.configure(
                    text=llm_chip_label(llm),
                    fg_color=llm_colors.get(llm, llm_colors[LLM_IDLE]),
                )
        except Exception:  # noqa: BLE001
            pass
        self._refresh_cycle_buttons()
        try:
            self._refresh_goal_banner()
        except Exception:  # noqa: BLE001
            pass

    def _refresh_goal_banner(self) -> None:
        from app.core.services.chat.task_watch import current_goal_text, goal_banner_status

        msgs = list((getattr(self, "_chat_state", None) or {}).get("messages") or [])
        ov = ""
        pin = False
        try:
            ov = str((self._chat_state or {}).get("current_goal") or "")
            pin = bool((self._chat_state or {}).get("current_goal_user_pin"))
        except Exception:  # noqa: BLE001
            ov = ""
            pin = False
        goal = current_goal_text(msgs, override=ov, user_pin=pin)
        phase = goal_banner_status(
            str(getattr(self, "_task_status", "none")),
            str(getattr(self, "_llm_phase", "idle")),
        )
        colors = {
            "PENDING": (("#fff7ed", "#7c2d12"), ("#9a3412", "#fdba74")),
            "WORKING": (("#dbeafe", "#1e3a8a"), ("#1e40af", "#93c5fd")),
            "PAUSED": (("#fef3c7", "#78350f"), ("#92400e", "#fcd34d")),
            "DONE": (("#d1fae5", "#064e3b"), ("#065f46", "#6ee7b7")),
            "BLOCKED": (("#fee2e2", "#7f1d1d"), ("#991b1b", "#fecaca")),
            "ERROR": (("#fee2e2", "#7f1d1d"), ("#991b1b", "#fecaca")),
            "NONE": (("#e5e7eb", "#27272a"), ("#52525b", "#a1a1aa")),
        }
        bg, fg = colors.get(phase, colors["NONE"])
        try:
            st = getattr(self, "_goal_status_lbl", None)
            if st is not None and st.winfo_exists():
                st.configure(text=phase, fg_color=bg, text_color=fg)
        except Exception:  # noqa: BLE001
            pass
        try:
            sm = getattr(self, "_goal_summary_lbl", None)
            if sm is not None and sm.winfo_exists():
                if goal:
                    sm.configure(text=f"Goal: {goal}")
                else:
                    sm.configure(text="Goal: (none yet — send a task in chat)")
        except Exception:  # noqa: BLE001
            pass
        try:
            from app.core.services.chat.task_ledger import (
                format_for_gui,
                load_ledger,
                sync_chat_ledger,
            )

            st = getattr(self, "_chat_state", None) or {}
            led = load_ledger(st, str(st.get("id") or ""))
            if not (led.get("findings") or []) and (st.get("messages") or []):
                led = sync_chat_ledger(st)
                self._chat_state = st
            fl = getattr(self, "_findings_lbl", None)
            if fl is not None and fl.winfo_exists():
                fl.configure(text=format_for_gui(led))
        except Exception:  # noqa: BLE001
            pass

    def _set_now_doing(self, text: str, *, idle: bool = False) -> None:
        """Always-visible one line: what the model is doing right now."""
        line = " ".join((text or "").split())
        if len(line) > 160:
            line = line[:157] + "…"
        self._now_doing_text = line
        lbl = getattr(self, "_now_doing_lbl", None)
        if lbl is None:
            return
        try:
            if not lbl.winfo_exists():
                return
            if idle:
                lbl.configure(
                    text=("LAST · " + line) if line else "NOW · idle",
                    text_color=("#52525b", "#a1a1aa"),
                )
            else:
                lbl.configure(
                    text=("NOW · " + (line or "working…")),
                    text_color=("#1d4ed8", "#93c5fd"),
                )
        except Exception:  # noqa: BLE001
            pass

    def _open_findings_window(self) -> None:
        """List every stored finding. Checkbox on = still open (you or the LLM can toggle)."""
        from app.core.services.chat.task_ledger import (
            finding_key,
            format_for_prompt,
            load_ledger,
            save_ledger,
            set_finding_open,
            sync_chat_ledger,
        )
        from app.ui.themes import UI as _UI, style_chrome_button

        st = getattr(self, "_chat_state", None) or {}
        led = load_ledger(st, str(st.get("id") or ""))
        if not (led.get("findings") or []) and (st.get("messages") or []):
            led = sync_chat_ledger(st)
            self._chat_state = st

        old = getattr(self, "_findings_win", None)
        try:
            if old is not None and old.winfo_exists():
                old.lift()
                old.focus_force()
                return
        except Exception:  # noqa: BLE001
            pass

        win = ctk.CTkToplevel(self)
        win.title("Findings — task memory")
        win.geometry("720x520")
        win.transient(self)
        self._findings_win = win
        ctk.CTkLabel(
            win,
            text="Checked = still open (sent to the model). Uncheck = resolved. You or the LLM can change this.",
            text_color=_UI.get("muted", ("#6b7280", "#9ca3af")),
            wraplength=680,
            justify="left",
        ).pack(anchor="w", padx=14, pady=(12, 4))

        filt = ctk.CTkFrame(win, fg_color="transparent")
        filt.pack(fill="x", padx=14, pady=(0, 6))
        show_err = ctk.BooleanVar(value=True)
        show_ok = ctk.BooleanVar(value=True)
        show_note = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(filt, text="Errors", variable=show_err, width=90).pack(side="left", padx=(0, 8))
        ctk.CTkCheckBox(filt, text="Edits / OK", variable=show_ok, width=100).pack(side="left", padx=8)
        ctk.CTkCheckBox(filt, text="Notes", variable=show_note, width=90).pack(side="left", padx=8)

        body = ctk.CTkScrollableFrame(win, fg_color=_UI.get("chat_bg", ("#fff", "#111")))
        body.pack(fill="both", expand=True, padx=14, pady=6)
        vars_by_key: dict[str, Any] = {}

        def persist() -> None:
            try:
                if getattr(self, "_chat_state", None) is None:
                    self._chat_state = {}
                save_ledger(self._chat_state, led)
                chat_svc.save_chat(self._chat_state)
            except Exception:  # noqa: BLE001
                pass
            try:
                self._refresh_goal_banner()
            except Exception:  # noqa: BLE001
                pass

        def on_toggle(key: str, var: Any) -> None:
            set_finding_open(led, key, bool(var.get()))
            persist()

        def render(_e: Any = None) -> None:
            for w in list(body.winfo_children()):
                try:
                    w.destroy()
                except Exception:  # noqa: BLE001
                    pass
            vars_by_key.clear()
            want = {
                "error": bool(show_err.get()),
                "success": bool(show_ok.get()),
                "fact": bool(show_note.get()),
            }
            rows = list(led.get("findings") or [])
            shown = 0
            for f in reversed(rows):
                k = str(f.get("kind") or "fact")
                if not want.get(k, True):
                    continue
                key = finding_key(f)
                row = ctk.CTkFrame(body, fg_color="transparent")
                row.pack(fill="x", pady=3)
                var = ctk.BooleanVar(value=f.get("open") is not False)
                vars_by_key[key] = var
                mark = {"error": "ERR", "success": "OK", "fact": "NOTE"}.get(k, "NOTE")
                path = str(f.get("path") or "")
                label = f"{mark}  {f.get('text') or ''}"
                if path:
                    label += f"   [{path}]"
                cb = ctk.CTkCheckBox(
                    row,
                    text=label[:220],
                    variable=var,
                    command=lambda kk=key, vv=var: on_toggle(kk, vv),
                    font=ctk.CTkFont(size=13),
                    checkbox_width=20,
                    checkbox_height=20,
                )
                cb.pack(side="left", fill="x", expand=True, padx=4)
                shown += 1
            if shown == 0:
                ctk.CTkLabel(
                    body,
                    text="No findings in this filter yet. Run the cycle — errors and edits appear here.",
                    text_color=_UI.get("muted", ("#6b7280", "#9ca3af")),
                    wraplength=640,
                    justify="left",
                ).pack(anchor="w", padx=8, pady=16)

        show_err.trace_add("write", lambda *_a: render())
        show_ok.trace_add("write", lambda *_a: render())
        show_note.trace_add("write", lambda *_a: render())
        render()

        btns = ctk.CTkFrame(win, fg_color="transparent")
        btns.pack(fill="x", padx=14, pady=(4, 12))

        def copy_all() -> None:
            try:
                self.clipboard_clear()
                self.clipboard_append(format_for_prompt(led, max_items=40))
                self.set_status("Findings copied", toast=True)
            except Exception:  # noqa: BLE001
                pass

        ctk.CTkButton(btns, text="Copy list", width=90, command=copy_all, **style_chrome_button()).pack(
            side="left", padx=4
        )
        ctk.CTkButton(btns, text="Close", width=80, command=win.destroy, **style_chrome_button()).pack(
            side="right", padx=4
        )

    def _edit_current_goal(self) -> None:
        from app.core.services.chat.task_watch import current_goal_text

        msgs = list((getattr(self, "_chat_state", None) or {}).get("messages") or [])
        cur = str((self._chat_state or {}).get("current_goal") or "") or current_goal_text(msgs)
        val = simpledialog.askstring(
            "Current LLM goal",
            "What should the model keep working on?",
            initialvalue=cur,
            parent=self,
        )
        if val is None:
            return
        if getattr(self, "_chat_state", None) is None:
            self._chat_state = {}
        self._chat_state["current_goal"] = (val or "").strip()
        self._chat_state["current_goal_user_pin"] = bool((val or "").strip())
        self._chat_state["current_goal_source"] = "user"
        try:
            chat_svc.save_chat(self._chat_state)
        except Exception:  # noqa: BLE001
            pass
        self._refresh_goal_banner()
        self.set_status("Goal updated", toast=True)

    def _refresh_cycle_buttons(self) -> None:
        running = bool(getattr(self, "_task_cycle_running", False))
        try:
            run_btn = getattr(self, "_cycle_run_btn", None)
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
            stop_btn = getattr(self, "_cycle_stop_btn", None)
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

    def _start_task_cycle(self) -> None:
        from app.core.services.chat.task_watch import TASK_ACHIEVED, TASK_OPEN

        if getattr(self, "_task_status", "") == TASK_ACHIEVED:
            if getattr(self, "_chat_state", None) is not None:
                self._chat_state["task_status_user_pin"] = TASK_OPEN
        self._task_cycle_running = True
        self._auto_continue_count = 0
        self._auto_error_retries = 0
        self._auto_error_gave_up = False
        self._auto_continue_hold_until = 0.0
        self._refresh_task_llm_chips()
        self.set_status("Cycle running — auto-continue while task is open and the model is idle", toast=True)
        try:
            self._maybe_auto_continue_task()
        except Exception:  # noqa: BLE001
            pass

    def _stop_task_cycle(self) -> None:
        import time as _time

        self._task_cycle_running = False
        self._auto_continue_hold_until = _time.monotonic() + 3600.0
        self._refresh_cycle_buttons()
        if bool(getattr(self, "_chat_busy", False)):
            try:
                self._chat_stop()
            except Exception:  # noqa: BLE001
                pass
        self.set_status("Cycle stopped — no auto-continue until you press Run cycle", toast=True)

    def _toggle_task_achieved(self) -> None:
        from app.core.services.chat.task_watch import TASK_ACHIEVED, TASK_OPEN

        cur = getattr(self, "_task_status", TASK_OPEN)
        nxt = TASK_OPEN if cur == TASK_ACHIEVED else TASK_ACHIEVED
        if getattr(self, "_chat_state", None) is None:
            self._chat_state = {}
        self._chat_state["task_status_user_pin"] = nxt
        self._auto_continue_count = 0
        if nxt == TASK_ACHIEVED:
            self._task_cycle_running = False
        try:
            chat_svc.save_chat(self._chat_state)
        except Exception:  # noqa: BLE001
            pass
        self._refresh_task_llm_chips()
        self.set_status(
            "Task marked achieved — cycle stopped"
            if nxt == TASK_ACHIEVED
            else "Task reopened — press ▶ Run cycle to auto-continue",
            toast=True,
        )

    def _composer_has_user_draft(self) -> bool:
        try:
            if getattr(self, "_composer_is_placeholder", False):
                return False
            if not hasattr(self, "chat_input"):
                return False
            t = (self.chat_input.get("1.0", "end") or "").strip()
            if not t:
                return False
            from app.core.services.chat.task_watch import is_auto_continue_text

            return not is_auto_continue_text(t)
        except Exception:  # noqa: BLE001
            return False

    def _task_watch_tick(self) -> None:
        self._refresh_task_llm_chips()
        try:
            self._maybe_auto_continue_task()
        except Exception:  # noqa: BLE001
            pass

    def _maybe_auto_continue_task(self) -> None:
        import time as _time

        from app.core.services.chat.task_watch import (
            MAX_ERROR_RETRIES,
            is_retryable_llm_error,
            should_auto_continue,
        )

        hold_until = float(getattr(self, "_auto_continue_hold_until", 0.0) or 0.0)
        last = float(getattr(self, "_auto_continue_last_ts", 0.0) or 0.0)
        now = _time.monotonic()
        retryable = False
        last_err_text = ""
        try:
            msgs = list((getattr(self, "_chat_state", None) or {}).get("messages") or [])
            if msgs and (msgs[-1].get("role") or "") == "error":
                last_err_text = str(msgs[-1].get("content") or "")
                retryable = is_retryable_llm_error(last_err_text)
        except Exception:  # noqa: BLE001
            retryable = False
        err_n = int(getattr(self, "_auto_error_retries", 0) or 0)
        if (
            bool(getattr(self, "_task_cycle_running", False))
            and retryable
            and err_n >= MAX_ERROR_RETRIES
            and not getattr(self, "_auto_error_gave_up", False)
        ):
            self._auto_error_gave_up = True
            self.set_status(
                f"Cycle held after {MAX_ERROR_RETRIES} provider errors — press ▶ Run cycle to retry",
                toast=True,
            )
        if should_auto_continue(
            task=str(getattr(self, "_task_status", "none")),
            llm=str(getattr(self, "_llm_phase", "idle")),
            user_typing=self._composer_has_user_draft(),
            hold=now < hold_until,
            auto_count=int(getattr(self, "_auto_continue_count", 0) or 0),
            seconds_since_last_auto=(now - last) if last else 999.0,
            page_is_chat=getattr(self, "_current_page", "") == "Chat"
            and bool(hasattr(self, "chat_input")),
            cycle_running=bool(getattr(self, "_task_cycle_running", False)),
            retryable_error=retryable,
            error_retries=err_n,
        ):
            self._chat_auto_continue()

    def _chat_send_text(self, text: str) -> None:
        """Send a message without relying on the placeholder composer."""
        text = (text or "").strip()
        if not text:
            return
        if not hasattr(self, "chat_input"):
            return
        try:
            self._composer_is_placeholder = False
            self.chat_input.delete("1.0", "end")
            self.chat_input.insert("1.0", text)
        except Exception:  # noqa: BLE001
            return
        self._chat_send()

    def _chat_auto_continue(self) -> None:
        import time as _time

        from app.core.services.chat.task_watch import auto_continue_text, current_goal_text

        if bool(getattr(self, "_chat_busy", False)):
            return
        st = getattr(self, "_chat_state", None) or {}
        goal = current_goal_text(
            st.get("messages") or [],
            override=str(st.get("current_goal") or ""),
            user_pin=bool(st.get("current_goal_user_pin")),
        )
        self._auto_continue_count = int(getattr(self, "_auto_continue_count", 0) or 0) + 1
        self._auto_continue_last_ts = _time.monotonic()
        last_was_err = False
        try:
            msgs = list((getattr(self, "_chat_state", None) or {}).get("messages") or [])
            last_was_err = bool(msgs) and (msgs[-1].get("role") or "") == "error"
        except Exception:  # noqa: BLE001
            last_was_err = False
        if last_was_err:
            self._auto_error_retries = int(getattr(self, "_auto_error_retries", 0) or 0) + 1
        short = (goal[:90] + "…") if len(goal) > 90 else (goal or "task still open")
        n_err = int(getattr(self, "_auto_error_retries", 0) or 0)
        self.set_status(
            f"Auto-continue {self._auto_continue_count} — {short}"
            + (f" (retry after provider error {n_err})" if last_was_err else ""),
            toast=True,
        )
        poke = auto_continue_text(goal, ledger=(st.get("task_ledger") if isinstance(st, dict) else None))
        if last_was_err:
            poke += (
                "\nThe last call hit a transient provider error (HTTP 5xx/429/timeout). "
                "Retry the same live goal. Do not treat that error as task done."
            )
        self._chat_send_text(poke)

    def _refresh_nav_badges(self) -> None:
        """Update Approvals / Patches / Work badge text without full rebuild."""
        from app.ui.themes import UI

        for name, count_fn, alert in (
            ("Approvals", self._approval_badge_count, True),
            ("Patches", self._patches_badge_count, True),
            ("Work", self._work_running_count, False),
        ):
            btn = (getattr(self, "_nav_buttons", None) or {}).get(name)
            if not btn:
                continue
            try:
                n = count_fn()
                label = self._nav_label_for(name)
                is_cur = self._current_page == name
                if is_cur:
                    btn.configure(
                        text=f"●  {label}",
                        text_color=UI["sidebar_active_text"],
                        fg_color=UI["sidebar_active"],
                    )
                elif alert and n:
                    # Alert badge — readable red, soft fill (not pure noise)
                    btn.configure(
                        text=label,
                        text_color=("#991b1b", "#fecaca"),
                        fg_color=("#fee2e2", "#3f1d1d"),
                    )
                elif n and name == "Work":
                    btn.configure(
                        text=label,
                        text_color=("#1e40af", "#93c5fd"),
                        fg_color=("#dbeafe", "#1e293b"),
                    )
                else:
                    btn.configure(
                        text=label,
                        text_color=UI["sidebar_text"],
                        fg_color="transparent",
                    )
            except Exception:  # noqa: BLE001
                pass

    def _build_sidebar(self) -> None:
        # Fixed-width rail with scroll so Settings/About are always reachable
        from app.ui.themes import UI, style_chrome_button

        # Rebuild-safe: destroy previous sidebar if any
        old = getattr(self, "_sidebar_frame", None)
        if old is not None:
            try:
                old.destroy()
            except Exception:  # noqa: BLE001
                pass

        side = ctk.CTkFrame(self, width=212, corner_radius=0, fg_color=UI["sidebar_bg"])
        side.grid(row=0, column=0, sticky="nsw")
        side.grid_propagate(False)
        side.grid_rowconfigure(2, weight=1)
        side.grid_columnconfigure(0, weight=1)
        self._sidebar_frame = side
        set_widget_name(side, build_name("app", REGION_SIDEBAR, PREFIX_FRAME, "root"))

        # Accent brand strip
        accent = ctk.CTkFrame(side, height=4, fg_color=UI["brand_bar"], corner_radius=0)
        accent.grid(row=0, column=0, sticky="ew")
        set_widget_name(accent, build_name("app", REGION_SIDEBAR, PREFIX_FRAME, "accent"))

        brand = ctk.CTkFrame(side, fg_color="transparent")
        brand.grid(row=1, column=0, sticky="ew", padx=14, pady=(14, 8))
        set_widget_name(brand, build_name("app", REGION_SIDEBAR, PREFIX_FRAME, "brand"))
        ctk.CTkLabel(
            brand,
            text="AI Agent Studio",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=UI["sidebar_text"],
        ).pack(anchor="w")
        ctk.CTkLabel(
            brand,
            text="Easy menu  ·  pick a page" if self._is_simple_ui() else "Full menu  ·  all tools",
            font=ctk.CTkFont(size=11),
            text_color=UI["sidebar_muted"],
        ).pack(anchor="w", pady=(3, 0))

        nav = ctk.CTkScrollableFrame(
            side,
            fg_color="transparent",
            width=196,
            corner_radius=0,
        )
        nav.grid(row=2, column=0, sticky="nsew", padx=2, pady=(2, 4))
        nav.grid_columnconfigure(0, weight=1)
        self._nav_scroll = nav
        set_widget_name(nav, build_name("app", REGION_SIDEBAR, SIDEBAR_NAV, PREFIX_SCROLL, "root"))

        # Collapsed hub state (True = expanded)
        self._hub_expanded: dict[str, bool] = getattr(self, "_hub_expanded", None) or {
            "START HERE": True,
            "PRIMARY": True,
            "WORKSPACE": False if self._is_simple_ui() else True,
            "MORE": False,
            "CHAT": True,
            "WORK": True,
            "LIBRARY": False,
            "SYSTEM": False,
        }
        if self._is_simple_ui():
            self._hub_expanded["MENU"] = True
            self._hub_expanded["START HERE"] = True

        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        self._hub_item_frames: dict[str, ctk.CTkFrame] = {}
        self._hub_headers: dict[str, ctk.CTkButton] = {}

        for title, items in self._nav_hubs():
            expanded = bool(self._hub_expanded.get(title, True))
            hub_key = title.lower().replace(" ", "_")
            header = ctk.CTkButton(
                nav,
                text=f"{'▾' if expanded else '▸'}  {title}",
                anchor="w",
                height=22,
                corner_radius=6,
                fg_color="transparent",
                text_color=UI["sidebar_muted"],
                hover_color=UI["sidebar_hover"],
                font=ctk.CTkFont(size=10, weight="bold"),
                command=lambda t=title: self._toggle_nav_hub(t),
            )
            header.pack(fill="x", padx=10, pady=(8, 2))
            set_widget_name(header, name_sidebar_hub_header(hub_key))
            self._hub_headers[title] = header
            self._tooltip(header, hub_description(title))

            items_frame = ctk.CTkFrame(nav, fg_color="transparent")
            self._hub_item_frames[title] = items_frame
            set_widget_name(items_frame, name_sidebar_hub_items_frame(hub_key))
            if expanded:
                items_frame.pack(fill="x")
            for name in items:
                if name not in NAV_ITEMS:
                    continue
                btn = ctk.CTkButton(
                    items_frame,
                    text=self._nav_label_for(name),
                    anchor="w",
                    height=40 if self._is_simple_ui() else 32,
                    corner_radius=10,
                    fg_color="transparent",
                    text_color=UI["sidebar_text"],
                    hover_color=UI["sidebar_hover"],
                    font=ctk.CTkFont(size=14 if self._is_simple_ui() else 13),
                    command=lambda n=name: self.show_page(n),
                )
                btn.pack(fill="x", padx=8, pady=2 if self._is_simple_ui() else 1)
                set_widget_name(btn, name_sidebar_nav_button(hub_key, name.lower()))
                self._nav_buttons[name] = btn
                self._tooltip(btn, page_description(name))

        # Footer: grouped actions (Batch 3) — mode vs help vs tools
        foot = ctk.CTkFrame(
            side,
            fg_color=UI.get("hub_header_bg", "transparent"),
            corner_radius=12,
            border_width=0,
        )
        foot.grid(row=3, column=0, sticky="ew", padx=8, pady=(4, 10))
        set_widget_name(foot, build_name("app", REGION_SIDEBAR, SIDEBAR_FOOTER, PREFIX_FRAME, "root"))
        simple_on = self._is_simple_ui()
        ctk.CTkLabel(
            foot,
            text="Quick",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=UI["sidebar_muted"],
            anchor="w",
        ).pack(fill="x", padx=10, pady=(8, 2))
        _easy_btn = ctk.CTkButton(
            foot,
            text="😊 Easy menu" if not simple_on else "🔧 Show all pages",
            height=32,
            corner_radius=10,
            command=lambda: self._set_simple_ui(not simple_on),
            **style_chrome_button(primary=simple_on),
        )
        _easy_btn.pack(fill="x", padx=8, pady=2)
        set_widget_name(_easy_btn, name_sidebar_footer_button("easy_toggle"))
        self._tooltip(
            _easy_btn,
            lambda: ("Show only the everyday screens to keep it simple."
                     if not self._is_simple_ui() else "Show every screen, including advanced tools."),
        )
        row2 = ctk.CTkFrame(foot, fg_color="transparent")
        row2.pack(fill="x", padx=6, pady=(2, 2))
        _key_btn = ctk.CTkButton(
            row2,
            text="⚙ Key",
            width=90,
            height=28,
            corner_radius=8,
            command=lambda: self.show_page("Settings"),
            **style_chrome_button(),
        )
        _key_btn.pack(side="left", padx=2, expand=True, fill="x")
        set_widget_name(_key_btn, name_sidebar_footer_button("settings"))
        self._tooltip(_key_btn, "Settings: add your AI connection key and adjust options.")
        _help_btn = ctk.CTkButton(
            row2,
            text="? Help",
            width=90,
            height=28,
            corner_radius=8,
            command=lambda: self.show_page("Help"),
            **style_chrome_button(primary=True),
        )
        _help_btn.pack(side="left", padx=2, expand=True, fill="x")
        set_widget_name(_help_btn, name_sidebar_footer_button("help"))
        self._tooltip(_help_btn, "Guides in plain English. Press F2 to open Help.")
        _search_btn = ctk.CTkButton(
            foot,
            text="⌨  Search pages  (Ctrl+K)",
            height=28,
            corner_radius=8,
            command=self._open_command_palette,
            **style_chrome_button(),
        )
        _search_btn.pack(fill="x", padx=8, pady=(2, 8))
        set_widget_name(_search_btn, name_sidebar_footer_button("search"))
        self._tooltip(_search_btn, "Jump straight to any page by typing its name. (Shortcut: Ctrl+K)")
        self._refresh_nav_badges()
        self._smooth_scroll(nav)

    def _toggle_nav_hub(self, title: str) -> None:
        # PRIMARY holds Chat/Home — collapsing it looks like the app vanished
        if str(title).strip().upper() == "PRIMARY":
            self._hub_expanded[title] = True
            frame = (self._hub_item_frames or {}).get(title)
            header = (self._hub_headers or {}).get(title)
            if header:
                try:
                    header.configure(text=f"▾  {title}")
                except Exception:  # noqa: BLE001
                    pass
            if frame:
                try:
                    if not frame.winfo_ismapped():
                        self._rebuild_sidebar_nav_only()
                except Exception:  # noqa: BLE001
                    self._rebuild_sidebar_nav_only()
            self.set_status("Chat stays in PRIMARY — that menu stays open")
            return
        expanded = not bool((self._hub_expanded or {}).get(title, True))
        self._hub_expanded[title] = expanded
        frame = (self._hub_item_frames or {}).get(title)
        header = (self._hub_headers or {}).get(title)
        if header:
            try:
                header.configure(text=f"{'▾' if expanded else '▸'}  {title}")
            except Exception:  # noqa: BLE001
                pass
        if frame:
            if expanded:
                # re-pack after header: find sibling order is hard — destroy rebuild simpler
                self._rebuild_sidebar_nav_only()
            else:
                try:
                    frame.pack_forget()
                except Exception:  # noqa: BLE001
                    pass

    def _ensure_nav_hub_for_page(self, page: str) -> None:
        """Keep the hub that contains this page expanded (Chat must stay findable)."""
        hubs = getattr(self, "_nav_hubs", None)
        if not callable(hubs):
            return
        for title, items in hubs():
            if page not in items:
                continue
            if bool((self._hub_expanded or {}).get(title, True)):
                return
            self._hub_expanded[title] = True
            self._rebuild_sidebar_nav_only()
            return

    def _rebuild_sidebar_nav_only(self) -> None:
        """Rebuild sidebar while preserving hub expand state."""
        # Full rebuild of left rail
        try:
            if hasattr(self, "_sidebar_frame") and self._sidebar_frame.winfo_exists():
                self._sidebar_frame.destroy()
        except Exception:  # noqa: BLE001
            pass
        self._build_sidebar()
        self._ensure_app_sidebar()
        # re-highlight current page
        if self._current_page:
            from app.ui.themes import UI

            for n, btn in self._nav_buttons.items():
                label = self._nav_label_for(n)
                if n == self._current_page:
                    btn.configure(
                        fg_color=UI["sidebar_active"],
                        text_color=UI["sidebar_active_text"],
                        text=f"●  {label}",
                    )
                else:
                    btn.configure(
                        fg_color="transparent",
                        text_color=UI["sidebar_text"],
                        text=label,
                    )

    def _build_system_monitor_bar(self) -> None:
        """Build the system resource monitoring bar at top of main content."""
        from app.ui.themes import UI as _UI
        
        self._sysmon_bar = ctk.CTkFrame(
            self._main_col,
            height=42,
            corner_radius=0,
            fg_color=_UI["top_bg"],
            border_width=1,
            border_color=_UI["top_border"],
        )
        self._sysmon_bar.grid(row=0, column=0, sticky="ew")
        self._sysmon_bar.grid_propagate(False)
        self._sysmon_bar.grid_columnconfigure(0, weight=1)
        set_widget_name(self._sysmon_bar, build_name("app", REGION_SYSTEM_MONITOR, PREFIX_FRAME, "bar"))
        
        inner = ctk.CTkFrame(self._sysmon_bar, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=4)
        set_widget_name(inner, build_name("app", REGION_SYSTEM_MONITOR, PREFIX_FRAME, "inner"))
        
        self._sysmon_metrics = [
            ("cpu", "CPU", "🖥", ("#3b82f6", "#60a5fa")),
            ("gpu", "GPU", "🎮", ("#8b5cf6", "#a78bfa")),
            ("disk", "DISK", "💾", ("#f59e0b", "#fbbf24")),
            ("net", "NET", "📡", ("#10b981", "#34d399")),
        ]
        
        self._sysmon_labels = {}
        self._sysmon_graphs = {}
        self._sysmon_history = {key: [] for key, _, _, _ in self._sysmon_metrics}
        self._sysmon_max_points = 50
        
        for i, (key, label, icon, color) in enumerate(self._sysmon_metrics):
            mframe = ctk.CTkFrame(inner, fg_color="transparent")
            mframe.pack(side="left", fill="y", padx=(0, 16))
            set_widget_name(mframe, name_system_monitor_metric(key))
            
            top_row = ctk.CTkFrame(mframe, fg_color="transparent")
            top_row.pack(fill="x")
            
            ctk.CTkLabel(
                top_row,
                text=f"{icon} {label}",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=_UI["label"],
            ).pack(side="left")
            
            pct_label = ctk.CTkLabel(
                top_row,
                text="0%",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=color[1],
                width=40,
            )
            pct_label.pack(side="right", padx=(4, 0))
            self._sysmon_labels[key] = pct_label
            set_widget_name(pct_label, build_name("app", REGION_SYSTEM_MONITOR, PREFIX_LABEL, f"{key}_pct"))

            # Speed label row for NET and DISK
            if key in ("net", "disk"):
                speed_row = ctk.CTkFrame(mframe, fg_color="transparent")
                speed_row.pack(fill="x", pady=(2, 0))
                if key == "net":
                    # Download / Upload labels
                    self._sysmon_net_down_label = ctk.CTkLabel(
                        speed_row,
                        text="↓ 0.0 Mbps",
                        font=ctk.CTkFont(size=9),
                        text_color=("#10b981", "#34d399"),
                    )
                    self._sysmon_net_down_label.pack(side="left", padx=(2, 8))
                    set_widget_name(self._sysmon_net_down_label, build_name("app", REGION_SYSTEM_MONITOR, PREFIX_LABEL, "net_down"))
                    self._sysmon_net_up_label = ctk.CTkLabel(
                        speed_row,
                        text="↑ 0.0 Mbps",
                        font=ctk.CTkFont(size=9),
                        text_color=("#ef4444", "#f87171"),
                    )
                    self._sysmon_net_up_label.pack(side="left")
                    set_widget_name(self._sysmon_net_up_label, build_name("app", REGION_SYSTEM_MONITOR, PREFIX_LABEL, "net_up"))
                elif key == "disk":
                    # Read / Write labels
                    self._sysmon_disk_read_label = ctk.CTkLabel(
                        speed_row,
                        text="R 0.0 MB/s",
                        font=ctk.CTkFont(size=9),
                        text_color=("#3b82f6", "#60a5fa"),
                    )
                    self._sysmon_disk_read_label.pack(side="left", padx=(2, 8))
                    set_widget_name(self._sysmon_disk_read_label, build_name("app", REGION_SYSTEM_MONITOR, PREFIX_LABEL, "disk_read"))
                    self._sysmon_disk_write_label = ctk.CTkLabel(
                        speed_row,
                        text="W 0.0 MB/s",
                        font=ctk.CTkFont(size=9),
                        text_color=("#f59e0b", "#fbbf24"),
                    )
                    self._sysmon_disk_write_label.pack(side="left")
                    set_widget_name(self._sysmon_disk_write_label, build_name("app", REGION_SYSTEM_MONITOR, PREFIX_LABEL, "disk_write"))

            graph_frame = ctk.CTkFrame(
                mframe,
                height=18,
                fg_color=_UI["top_bg"],
                corner_radius=3,
                border_width=0,
            )
            graph_frame.pack(fill="x", pady=(2, 0))
            graph_frame.pack_propagate(False)
            self._sysmon_graphs[key] = graph_frame
            set_widget_name(graph_frame, build_name("app", REGION_SYSTEM_MONITOR, PREFIX_FRAME, f"{key}_graph"))
        
        self._sysmon_running = True
        self._update_system_monitor()

    def _update_system_monitor(self) -> None:
        """Update system monitor metrics and graphs."""
        if not getattr(self, "_sysmon_running", False):
            return
        if not self.winfo_exists():
            return
            
        try:
            import psutil
            import platform
            
            # CPU usage
            cpu_pct = psutil.cpu_percent(interval=None)
            
            # GPU usage (try nvidia-smi for NVIDIA GPUs)
            gpu_pct = 0.0
            try:
                import subprocess
                result = subprocess.run(
                    ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=1.0
                )
                if result.returncode == 0:
                    gpu_vals = [float(x.strip()) for x in result.stdout.strip().split("\n") if x.strip()]
                    gpu_pct = sum(gpu_vals) / len(gpu_vals) if gpu_vals else 0.0
            except Exception:
                pass
            
            # Disk usage
            disk_pct = 0.0
            try:
                if platform.system() == "Windows":
                    disk = psutil.disk_usage("C:\\")
                else:
                    disk = psutil.disk_usage("/")
                disk_pct = disk.percent
            except Exception:
                pass
            
            # Disk usage and I/O
            disk_pct = 0.0
            disk_read_mbps = 0.0
            disk_write_mbps = 0.0
            try:
                if platform.system() == "Windows":
                    disk = psutil.disk_usage("C:\\")
                else:
                    disk = psutil.disk_usage("/")
                disk_pct = disk.percent

                # Disk I/O
                disk_io = psutil.disk_io_counters()
                if disk_io:
                    current_read = disk_io.read_bytes
                    current_write = disk_io.write_bytes
                    if hasattr(self, "_sysmon_last_disk_read") and hasattr(self, "_sysmon_last_disk_write"):
                        read_delta = current_read - self._sysmon_last_disk_read
                        write_delta = current_write - self._sysmon_last_disk_write
                        # Convert to MB/s (2 second interval)
                        disk_read_mbps = read_delta / 1024 / 1024 / 2
                        disk_write_mbps = write_delta / 1024 / 1024 / 2
                    self._sysmon_last_disk_read = current_read
                    self._sysmon_last_disk_write = current_write
            except Exception:
                pass

            # Network I/O (bytes per second)
            net_pct = 0.0
            net_down_mbps = 0.0
            net_up_mbps = 0.0
            try:
                net_io = psutil.net_io_counters()
                current_recv = net_io.bytes_recv
                current_sent = net_io.bytes_sent
                if hasattr(self, "_sysmon_last_net_recv") and hasattr(self, "_sysmon_last_net_sent"):
                    recv_delta = current_recv - self._sysmon_last_net_recv
                    sent_delta = current_sent - self._sysmon_last_net_sent
                    # Convert to Mbps (2 second interval, bits not bytes)
                    net_down_mbps = (recv_delta * 8) / 1024 / 1024 / 2
                    net_up_mbps = (sent_delta * 8) / 1024 / 1024 / 2
                    # Normalize to 0-100 scale (assuming ~100Mbps as 100%)
                    total_mbps = net_down_mbps + net_up_mbps
                    net_pct = min(100, total_mbps)
                self._sysmon_last_net_recv = current_recv
                self._sysmon_last_net_sent = current_sent
            except Exception:
                pass
            
            metrics = {
                "cpu": cpu_pct,
                "gpu": gpu_pct,
                "disk": disk_pct,
                "net": net_pct,
            }
            
            for key, value in metrics.items():
                history = self._sysmon_history[key]
                history.append(value)
                if len(history) > self._sysmon_max_points:
                    history.pop(0)
                
                label = self._sysmon_labels.get(key)
                if label and label.winfo_exists():
                    # Color based on usage: green < 50%, yellow < 80%, red >= 80%
                    if value < 50:
                        color = ("#059669", "#34d399")  # Green
                    elif value < 80:
                        color = ("#d97706", "#fbbf24")  # Amber
                    else:
                        color = ("#dc2626", "#ef4444")  # Red
                    try:
                        label.configure(text=f"{value:.0f}%", text_color=color[1])
                    except Exception:
                        pass
                
                graph = self._sysmon_graphs.get(key)
                if graph and graph.winfo_exists():
                    self._draw_mini_graph(graph, history, key)

            # Update speed labels
            # Network download/upload
            if hasattr(self, "_sysmon_net_down_label") and self._sysmon_net_down_label.winfo_exists():
                self._sysmon_net_down_label.configure(text=f"↓ {net_down_mbps:.1f} Mbps")
            if hasattr(self, "_sysmon_net_up_label") and self._sysmon_net_up_label.winfo_exists():
                self._sysmon_net_up_label.configure(text=f"↑ {net_up_mbps:.1f} Mbps")

            # Disk read/write
            if hasattr(self, "_sysmon_disk_read_label") and self._sysmon_disk_read_label.winfo_exists():
                self._sysmon_disk_read_label.configure(text=f"R {disk_read_mbps:.1f} MB/s")
            if hasattr(self, "_sysmon_disk_write_label") and self._sysmon_disk_write_label.winfo_exists():
                self._sysmon_disk_write_label.configure(text=f"W {disk_write_mbps:.1f} MB/s")
                    
        except Exception:
            pass
        
        # Schedule next update (every 2 seconds)
        try:
            self.after(2000, self._update_system_monitor)
        except Exception:
            pass

    def _draw_mini_graph(self, graph_frame, history, key) -> None:
        """Draw a mini sparkline graph in the frame."""
        if not history:
            return
            
        try:
            # Clear previous graph
            for w in graph_frame.winfo_children():
                try:
                    w.destroy()
                except Exception:
                    pass
            
            if len(history) < 2:
                return
            
            # Colors for each metric
            metric_colors = {
                "cpu": ("#3b82f6", "#60a5fa"),
                "gpu": ("#8b5cf6", "#a78bfa"),
                "disk": ("#f59e0b", "#fbbf24"),
                "net": ("#10b981", "#34d399"),
            }
            color = metric_colors.get(key, ("#64748b", "#94a3b8"))[1]
            
            width = 120
            height = 16
            padding = 2
            
            max_val = max(history) if history else 1
            max_val = max(max_val, 1)
            
            bar_width = max(1, width // len(history))
            for i, val in enumerate(history):
                bar_height = int((val / max_val) * (height - padding * 2))
                bar_height = max(1, bar_height)
                
                bar = ctk.CTkFrame(
                    graph_frame,
                    width=bar_width,
                    height=bar_height,
                    fg_color=color,
                    corner_radius=0,
                )
                bar.place(x=i * bar_width, y=height - padding - bar_height)
                
        except Exception:
            pass

    def show_page(self, name: str, *, rebuild: bool = False) -> None:
        already = getattr(self, "_current_page", None)
        self._current_page = name
        # Clear page-specific Ctrl+S handler unless the new page re-registers it
        self._page_save_handler = None
        self._page_form_layout = None
        from app.ui.themes import UI

        # Reset content frame background to default (fixes blank white screen after Chat page)
        # Chat page changes content fg_color to chat_bg; other pages use transparent frames
        try:
            self.content.configure(fg_color=UI["content_bg"])
        except Exception:  # noqa: BLE001
            pass

        # Ensure a solid background frame exists at the bottom of content stacking order
        # This guarantees correct background even if page frames have padding/transparency
        bg = getattr(self, "_content_bg_frame", None)
        bg_ok = False
        try:
            bg_ok = bg is not None and bool(bg.winfo_exists())
        except Exception:  # noqa: BLE001
            bg_ok = False
        if not bg_ok:
            self._content_bg_frame = ctk.CTkFrame(
                self.content, fg_color=UI["content_bg"], corner_radius=0
            )
            self._content_bg_frame.grid(row=0, column=0, sticky="nsew")
            self._content_bg_frame.lower()  # Keep at bottom
        else:
            try:
                self._content_bg_frame.configure(fg_color=UI["content_bg"])
            except Exception:  # noqa: BLE001
                pass

        for n, btn in self._nav_buttons.items():
            label = self._nav_label_for(n)
            if n == name:
                # Stronger active state (Grok-like focus) — prefix marker + fill
                btn.configure(
                    fg_color=UI["sidebar_active"],
                    text_color=UI["sidebar_active_text"],
                    text=f"●  {label}",
                    border_width=0,
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    text_color=UI["sidebar_text"],
                    text=label,
                    border_width=0,
                )
        self._refresh_nav_badges()

        # Restore used to call show_page("Chat") three times. Each pass destroyed
        # chat_scroll while an earlier render was still packing bubbles → white canvas.
        # Hide/Show chats MUST pass rebuild=True — skip left the rail stuck empty.
        if (
            name == "Chat"
            and already == "Chat"
            and not rebuild
            and self._chat_scroll_alive()
        ):
            try:
                inp = getattr(self, "chat_input", None)
                if inp is not None and bool(inp.winfo_exists()):
                    try:
                        self._chat_state = self._load_active_chat()
                    except Exception:  # noqa: BLE001
                        pass
                    self._chat_render_transcript()
                    return
            except Exception:  # noqa: BLE001
                pass

        self._chat_page_gen = int(getattr(self, "_chat_page_gen", 0) or 0) + 1
        for child in list(self.content.winfo_children()):
            try:
                child.destroy()
            except Exception:  # noqa: BLE001
                pass

        builders: dict[str, Callable[[], None]] = {
            "Home": self._page_home,
            "Help": self._page_help,
            "Chat": self._page_chat,
            "Team": lambda: __import__(
                "app.ui.pages.team_page", fromlist=["page_team"]
            ).page_team(self),
            "Models": lambda: __import__(
                "app.ui.pages.models_page", fromlist=["page_models"]
            ).page_models(self),
            "Monitor": lambda: __import__(
                "app.ui.pages.monitor_page", fromlist=["page_monitor"]
            ).page_monitor(self),
            "Chats": lambda: mgmt_pages.page_chats(self),
            "Track": self._page_track,
            "Work": self._page_work_board,
            "Approvals": self._page_approvals,
            "Patches": self._page_patches,
            "Knowledge": self._page_knowledge,
            "Notes": lambda: notes_page.page_notes(self),
            "Schedule": self._page_schedule,
            "Memory": lambda: mgmt_pages.page_memory(self),
            "Projects": lambda: mgmt_pages.page_projects(self),
            "Org chart": lambda: __import__(
                "app.ui.pages.org_page", fromlist=["page_workflow"]
            ).page_workflow(self),
            "Workflow": lambda: __import__(
                "app.ui.pages.org_page", fromlist=["page_workflow"]
            ).page_workflow(self),
            "Company": lambda: mgmt_pages.page_company(self),
            "CEO": lambda: mgmt_pages.page_ceo(self),
            "Agents": self._page_agents,
            "Tasks": self._page_tasks,
            "Runs": self._page_runs,
            "Usage": self._page_usage,
            "Settings": self._page_settings,
            "About": self._page_about,
        }
        try:
            builders.get(name, self._page_home)()
        except Exception as exc:  # noqa: BLE001
            # Never leave a silent white pane — naming/build bugs used to do this on Chat
            self._render_page_build_error(name, exc)
            return
        try:
            self._ensure_nav_hub_for_page(name)
        except Exception:  # noqa: BLE001
            pass
        try:
            self._ensure_app_sidebar()
        except Exception:  # noqa: BLE001
            pass
        # Contextual one-line tip for the page
        try:
            from app.core.services.misc.user_guide import PAGE_TIPS

            tip = PAGE_TIPS.get(name)
            if tip and not self._chat_busy:
                self.set_status(f"Tip: {tip}")
        except Exception:  # noqa: BLE001
            self.set_status()

    def _render_page_build_error(self, name: str, exc: BaseException) -> None:
        """Visible fallback when a page builder crashes (replaces blank white)."""
        import traceback

        tb = traceback.format_exc()
        try:
            self.set_status(f"{name} failed to open: {exc}")
        except Exception:  # noqa: BLE001
            pass
        try:
            from app.ui.themes import UI, style_chrome_button
        except Exception:  # noqa: BLE001
            UI = {"content_bg": ("#f7f7f8", "#0a0a0a"), "label": ("#111", "#eee"), "muted": ("#444", "#bbb")}
            style_chrome_button = lambda **_k: {}  # noqa: E731
        frame = ctk.CTkFrame(self.content, fg_color=UI.get("content_bg", ("#f7f7f8", "#0a0a0a")), corner_radius=12)
        frame.grid(row=0, column=0, sticky="nsew", padx=24, pady=24)
        ctk.CTkLabel(
            frame,
            text=f"{name} didn't open",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=UI.get("label", ("#111827", "#f9fafb")),
        ).pack(anchor="w", padx=20, pady=(20, 6))
        ctk.CTkLabel(
            frame,
            text="The page hit an error while building. Retry, or go Home. This is a Studio bug — not your chat.",
            wraplength=720,
            justify="left",
            text_color=UI.get("muted", ("#374151", "#d1d5db")),
        ).pack(anchor="w", padx=20, pady=(0, 10))
        ctk.CTkLabel(
            frame,
            text=str(exc),
            wraplength=720,
            justify="left",
            font=ctk.CTkFont(family="Consolas", size=13),
        ).pack(anchor="w", padx=20, pady=(0, 12))
        bar = ctk.CTkFrame(frame, fg_color="transparent")
        bar.pack(anchor="w", padx=20, pady=(0, 8))
        ctk.CTkButton(
            bar,
            text="Retry this page",
            width=140,
            command=lambda: self.show_page(name),
            **style_chrome_button(primary=True),
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            bar,
            text="Go to Home",
            width=110,
            command=lambda: self.show_page("Home"),
            **style_chrome_button(),
        ).pack(side="left")
        box = ctk.CTkTextbox(frame, height=180, font=ctk.CTkFont(family="Consolas", size=11), wrap="word")
        box.pack(fill="both", expand=True, padx=20, pady=(8, 20))
        try:
            box.insert("1.0", tb)
            box.configure(state="disabled")
        except Exception:  # noqa: BLE001
            pass

    # ---- pages ----

    def _maybe_show_onboarding(self) -> None:
        """3-step first-run wizard when not completed."""
        try:
            cfg = storage.load_config()
            if cfg.get("onboarding_done"):
                return
            key = (cfg.get("api_key") or "").strip()
            # Still show once even if key exists (intro), skip only if done
            self._show_onboarding_wizard()
        except Exception:  # noqa: BLE001
            pass

    def _show_onboarding_wizard(self) -> None:
        from app.ui.themes import style_chrome_button, style_entry
        from app.services import providers as prov

        win = ctk.CTkToplevel(self)
        win.title("Welcome — how to use")
        win.geometry("560x480")
        win.transient(self)
        win.grab_set()
        step = {"i": 0}

        title = ctk.CTkLabel(win, text="", font=ctk.CTkFont(size=18, weight="bold"))
        title.pack(anchor="w", padx=20, pady=(18, 6))
        body = ctk.CTkLabel(win, text="", justify="left", wraplength=500)
        body.pack(anchor="w", padx=20, pady=6)
        mid = ctk.CTkFrame(win, fg_color="transparent")
        mid.pack(fill="both", expand=True, padx=20, pady=8)

        key_var = ctk.StringVar(master=win, value=(storage.load_config().get("api_key") or ""))
        prov_var = ctk.StringVar(master=win, value="OpenRouter")

        def paint() -> None:
            for w in mid.winfo_children():
                w.destroy()
            i = step["i"]
            if i == 0:
                title.configure(text="1 · What is this app?")
                body.configure(
                    text=(
                        "AI Agent Studio is a portable Windows app to chat with an AI that can use "
                        "your PC (terminal, browser, files) and run multi-agent company work.\n\n"
                        "You will:\n"
                        "  1) Add an API key\n"
                        "  2) Open Chat in Action mode\n"
                        "  3) Ask questions — tools run when needed\n\n"
                        "Press F2 anytime for the full How-to guide."
                    )
                )
            elif i == 1:
                title.configure(text="2 · API key (required for answers)")
                body.configure(
                    text=(
                        "Paste an OpenAI-compatible key. OpenRouter works for many models.\n"
                        "Without a key you can explore the UI, but Chat cannot call an LLM."
                    )
                )
                ctk.CTkLabel(mid, text="Provider").pack(anchor="w")
                names = [p.get("name") or p["id"] for p in prov.list_providers()] or [
                    "OpenRouter",
                    "OpenAI",
                ]
                ctk.CTkOptionMenu(mid, values=names, variable=prov_var, width=200).pack(
                    anchor="w", pady=4
                )
                ctk.CTkLabel(mid, text="API key").pack(anchor="w", pady=(8, 0))
                ctk.CTkEntry(mid, textvariable=key_var, width=400, show="*", **style_entry()).pack(
                    anchor="w", pady=4
                )
            elif i == 2:
                title.configure(text="3 · How Chat controls work")
                body.configure(
                    text=(
                        "Top bar:\n"
                        "  • Mode = Action (tools) or Plan (no tools)\n"
                        "  • Caps ▾ = Terminal / Skills / MCP / Laptop\n"
                        "  • Comfort = show all switches\n"
                        "  • Provider / Model = which LLM to use\n\n"
                        "Composer: type → Enter to send · ■ Stop cancels\n"
                        "Empty chat shows starter chips — click one and Send."
                    )
                )
            else:
                title.configure(text="4 · You're ready")
                body.configure(
                    text=(
                        "Recommended first message:\n"
                        '  "What can you do on this PC?"\n\n'
                        "Also try:\n"
                        "  • Help page (F2) for the full guide\n"
                        "  • Ctrl+K command palette\n"
                        "  • Knowledge to index your files\n"
                        "  • Work board for company tasks\n"
                    )
                )
                ctk.CTkButton(
                    mid,
                    text="Open Chat now",
                    command=lambda: (finish(True), self.show_page("Chat")),
                    **style_chrome_button(primary=True),
                ).pack(anchor="w", pady=8)
                ctk.CTkButton(
                    mid,
                    text="Open Help guide",
                    command=lambda: (finish(False), self.show_page("Help")),
                    **style_chrome_button(),
                ).pack(anchor="w", pady=4)

        def save_key() -> None:
            cfg = storage.load_config()
            k = key_var.get().strip()
            if k:
                cfg["api_key"] = k
                storage.save_config(cfg)
                self.cfg = cfg
                try:
                    pid = "openrouter" if "openrouter" in prov_var.get().lower() else "openai"
                    if "openai" in prov_var.get().lower() and "router" not in prov_var.get().lower():
                        pid = "openai"
                    prov.set_active(pid)
                    # also store on provider if API supports
                    p = prov.get_provider(pid) or {}
                    if "api_key" in p or True:
                        from app.services import providers as P

                        # best-effort: many installs use config.api_key
                        pass
                except Exception:  # noqa: BLE001
                    pass

        def finish(open_chat: bool = False) -> None:
            save_key()
            cfg = storage.load_config()
            cfg["onboarding_done"] = True
            storage.save_config(cfg)
            self.cfg = cfg
            try:
                win.destroy()
            except Exception:  # noqa: BLE001
                pass
            if open_chat:
                self.show_page("Chat")
            self.set_status("Setup complete")

        def next_step() -> None:
            if step["i"] == 1:
                save_key()
            if step["i"] >= 3:
                finish(True)
                return
            step["i"] += 1
            paint()

        bar = ctk.CTkFrame(win, fg_color="transparent")
        bar.pack(fill="x", padx=16, pady=12)
        ctk.CTkButton(bar, text="Skip", width=80, command=lambda: finish(False), **style_chrome_button()).pack(
            side="left"
        )
        ctk.CTkButton(bar, text="Next →", width=100, command=next_step, **style_chrome_button(primary=True)).pack(
            side="right"
        )
        paint()

    def _test_active_llm_connection(self) -> None:
        """Task #2: Health-check active provider/model with clear next actions."""
        from app.services import providers as prov
        from app.core.services.llm.llm import LLMError, chat_completion, format_llm_error_message

        try:
            active = prov.resolve_active_llm()
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Test connection", str(e), parent=self)
            return
        key = (active.get("api_key") or "").strip()
        model = (active.get("model") or "").strip()
        base = (active.get("base_url") or "").strip()
        pid = active.get("provider_id") or "?"
        if not key:
            if str(pid) == "ollama" or "ollama" in (active.get("provider_name") or "").lower():
                messagebox.showwarning(
                    "Test connection",
                    "Offline · Ollama (local) needs a key field (use “ollama”) and a running daemon.\n\n"
                    "Next:\n"
                    "• Install from https://ollama.com if needed\n"
                    "• Start Ollama (ollama serve)\n"
                    "• Settings → Offline · Ollama (local) → base http://127.0.0.1:11434/v1\n"
                    "• Add key labeled ollama, Fetch models, Set active",
                    parent=self,
                )
                return
            messagebox.showwarning(
                "Test connection",
                f"No API key for provider “{active.get('provider_name') or pid}”.\n\n"
                "Next: Settings → select provider → Add key\n"
                "Or Home → ✦ Connect Grok (xAI key from console.x.ai)",
                parent=self,
            )
            return
        self.set_status(f"Testing {pid} / {model}…")
        try:
            out = chat_completion(
                api_key=key,
                messages=[{"role": "user", "content": "Reply with exactly: OK"}],
                model=model,
                base_url=base,
                timeout=45.0,
                max_tokens=16,
                temperature=0,
                tools=None,
                normalize_tools=False,
                _transient_retry=False,
            )
            snippet = (out or "").strip()[:120]
            messagebox.showinfo(
                "Connection OK",
                f"Provider: {active.get('provider_name')}\n"
                f"Base: {base}\n"
                f"Model: {model}\n\n"
                f"Reply: {snippet or '(empty)'}",
                parent=self,
            )
            self.set_status(f"Test OK · {model}", toast=True)
        except LLMError as e:
            err = format_llm_error_message(e)
            low = err.lower()
            actions = []
            if "402" in err or "credit" in low or "payment" in low:
                actions.append("• Add OpenRouter credits OR switch to xAI (console.x.ai key)")
            if "400" in err or "model not found" in low or "invalid" in low:
                actions.append("• Use Grok button (fixes host/model mismatch)")
                actions.append("• Or Fetch models and pick a valid id")
            if "401" in err or "403" in err or "key" in low:
                actions.append("• Paste a valid key for this provider in Settings")
            if str(pid) == "ollama" or "11434" in (base or ""):
                actions = [
                    "• Offline · Ollama (local) — install from https://ollama.com if needed",
                    "• Start Ollama (app or: ollama serve)",
                    "• Confirm base URL http://127.0.0.1:11434/v1 and Fetch models",
                ]
            if not actions:
                actions.append("• Check base URL, model name, and network")
            messagebox.showerror(
                "Connection failed",
                f"{err}\n\nWhat to do next:\n" + "\n".join(actions),
                parent=self,
            )
            self.set_status("Test failed", toast=True)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Test connection", str(e), parent=self)
            self.set_status(f"Test error: {e}")

    def _use_grok_as_agent(self) -> None:
        """Use Grok via direct xAI API (no CLI, no OpenRouter required)."""
        from app.services import providers as prov
        from app.ui.themes import style_chrome_button, style_entry, UI as _UI

        self.set_status("Switching to direct xAI Grok…")
        try:
            # Default: direct api.x.ai — not OpenRouter (avoids 402 credits trap)
            result = prov.activate_grok_as_agent(prefer="xai", fetch=True)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Use Grok", str(e), parent=self)
            self.set_status(f"Grok switch failed: {e}")
            return

        if result.get("need_key"):
            # Always collect a direct xAI key first
            win = ctk.CTkToplevel(self)
            win.title("Use Grok directly (xAI)")
            win.geometry("560x400")
            win.transient(self)
            win.grab_set()
            ctk.CTkLabel(
                win,
                text="Connect Grok via xAI API",
                font=ctk.CTkFont(size=18, weight="bold"),
                text_color=_UI["label"],
            ).pack(anchor="w", padx=18, pady=(16, 6))
            ctk.CTkLabel(
                win,
                text=(
                    "This uses Grok inside Studio (no CLI).\n\n"
                    "You need an xAI API key from https://console.x.ai\n"
                    "• grok.com website login is NOT enough\n"
                    "• OpenRouter is optional and needs separate paid credits\n\n"
                    "Paste your xAI API key below:"
                ),
                text_color=_UI["muted"],
                justify="left",
                wraplength=520,
            ).pack(anchor="w", padx=18, pady=(0, 10))
            key_var = ctk.StringVar(master=win, value="")
            ctk.CTkEntry(
                win,
                textvariable=key_var,
                width=480,
                show="*",
                placeholder_text="xAI API key (from console.x.ai)",
                **style_entry(),
            ).pack(anchor="w", padx=18, pady=8)

            def save_and_activate() -> None:
                k = (key_var.get() or "").strip()
                if not k:
                    messagebox.showinfo(
                        "Key required",
                        "Paste your xAI API key from https://console.x.ai",
                        parent=win,
                    )
                    return
                if k.startswith("sk-or-"):
                    messagebox.showwarning(
                        "Wrong key type",
                        "That looks like an OpenRouter key (sk-or-…).\n\n"
                        "For direct Grok, create a key at https://console.x.ai\n"
                        "and paste that instead.",
                        parent=win,
                    )
                    return
                try:
                    prov.ensure_builtin_providers()
                    prov.add_key("xai", k, label="grok")
                    r2 = prov.activate_grok_as_agent(prefer="xai", fetch=True)
                except Exception as e:  # noqa: BLE001
                    messagebox.showerror("Use Grok", str(e), parent=win)
                    return
                try:
                    win.destroy()
                except Exception:  # noqa: BLE001
                    pass
                self._after_grok_activated(r2)

            def use_openrouter_instead() -> None:
                try:
                    win.destroy()
                except Exception:  # noqa: BLE001
                    pass
                try:
                    r2 = prov.activate_grok_as_agent(prefer="openrouter", fetch=True)
                    self._after_grok_activated(r2)
                except Exception as e:  # noqa: BLE001
                    messagebox.showerror("OpenRouter Grok", str(e), parent=self)

            ctk.CTkButton(
                win,
                text="Save xAI key & use Grok",
                width=240,
                height=38,
                command=save_and_activate,
                **style_chrome_button(primary=True),
            ).pack(anchor="w", padx=18, pady=(12, 6))
            ctk.CTkButton(
                win,
                text="Use OpenRouter instead (needs credits)",
                width=280,
                height=30,
                command=use_openrouter_instead,
                **style_chrome_button(),
            ).pack(anchor="w", padx=18, pady=4)
            ctk.CTkButton(win, text="Cancel", width=100, command=win.destroy).pack(
                anchor="w", padx=18, pady=(8, 12)
            )
            try:
                import webbrowser

                ctk.CTkButton(
                    win,
                    text="Open console.x.ai",
                    width=160,
                    command=lambda: webbrowser.open("https://console.x.ai"),
                    **style_chrome_button(),
                ).pack(anchor="w", padx=18, pady=(0, 12))
            except Exception:  # noqa: BLE001
                pass
            return

        self._after_grok_activated(result)

    def _after_grok_activated(self, result: dict) -> None:
        """Refresh chat UI after Grok is set active."""
        msg = str(result.get("message") or "Grok activated")
        model = str(result.get("model") or "")
        if result.get("ok"):
            # Sync chat menus if present
            try:
                if hasattr(self, "chat_provider_var") and result.get("provider_name"):
                    self.chat_provider_var.set(str(result.get("provider_name")))
                if hasattr(self, "chat_model_var") and model:
                    # Ensure model is in dropdown list
                    choices = list(getattr(self, "_chat_model_choices", None) or [])
                    if model not in choices:
                        choices = [model] + choices
                        self._chat_model_choices = choices[:120]
                        self._sync_model_menus(select=model)
                    self.chat_model_var.set(model)
                if hasattr(self, "_on_chat_provider_change") and result.get("provider_name"):
                    try:
                        self._on_chat_provider_change(str(result.get("provider_name")))
                    except Exception:  # noqa: BLE001
                        pass
            except Exception:  # noqa: BLE001
                pass
            try:
                self._update_composer_status()
            except Exception:  # noqa: BLE001
                pass
            messagebox.showinfo("Grok is your agent", msg, parent=self)
            self.set_status(f"Agent: Grok · {model}", toast=True)
            # Land on Chat ready to talk
            try:
                if self._current_page != "Chat":
                    self.show_page("Chat")
                else:
                    self.show_page("Chat")  # rebuild menus
            except Exception:  # noqa: BLE001
                pass
        else:
            messagebox.showwarning("Use Grok", msg, parent=self)
            self.set_status("Grok not activated")

    def _page_home(self) -> None:
        """Simple guided home — 4 big steps matching the product objective."""
        from app.ui.themes import style_chrome_button, style_card, UI as _UI

        frame = ctk.CTkFrame(self.content, fg_color="transparent")
        frame.grid(row=0, column=0, sticky="nsew", padx=24, pady=20)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(2, weight=1)
        set_widget_name(frame, name_page_root(PAGE_HOME))

        try:
            from app.core.services.llm.providers import has_active_api_key

            key_ok = has_active_api_key()
        except Exception:  # noqa: BLE001
            key_ok = bool((storage.load_config().get("api_key") or "").strip())

        # Title
        hero = ctk.CTkFrame(frame, **style_card())
        hero.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        ctk.CTkLabel(
            hero,
            text="Welcome — pick one thing to do",
            font=ctk.CTkFont(size=26, weight="bold"),
            text_color=_UI["label"],
        ).pack(anchor="w", padx=20, pady=(18, 4))
        ctk.CTkLabel(
            hero,
            text=(
                "You do not need to be technical. Click one big button below.\n"
                "Left side = menu. Window top bar (OS) = minimize · maximize · close."
            ),
            text_color=_UI["muted"],
            font=ctk.CTkFont(size=14),
            justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 8))

        if not key_ok:
            warn = ctk.CTkFrame(hero, fg_color=("#fef3c7", "#422006"), corner_radius=10)
            warn.pack(fill="x", padx=16, pady=(4, 8))
            ctk.CTkLabel(
                warn,
                text="First time? Tap the button to connect your AI account (like a password).",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color=("#92400e", "#fde68a"),
            ).pack(side="left", padx=14, pady=12)
            ctk.CTkButton(
                warn,
                text="Connect now",
                width=130,
                command=self._show_onboarding_wizard,
                **style_chrome_button(primary=True),
            ).pack(side="right", padx=14, pady=10)
        else:
            ctk.CTkLabel(
                hero,
                text="✓ Ready — choose a step below",
                text_color=_UI["success"],
                font=ctk.CTkFont(size=13),
            ).pack(anchor="w", padx=20, pady=(0, 4))

        mode_row = ctk.CTkFrame(hero, fg_color="transparent")
        mode_row.pack(fill="x", padx=16, pady=(4, 14))
        simple = self._is_simple_ui()
        ctk.CTkButton(
            mode_row,
            text="😊 Easy (for everyone)" if simple else "Use Easy mode",
            width=180,
            command=lambda: self._set_simple_ui(True),
            **style_chrome_button(primary=simple),
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            mode_row,
            text="🔧 Expert (all pages)" if not simple else "Show expert pages",
            width=180,
            command=lambda: self._set_simple_ui(False),
            **style_chrome_button(primary=not simple),
        ).pack(side="left", padx=4)
        # Use Grok as the agent brain (replaces day-to-day CLI chat)
        ctk.CTkButton(
            mode_row,
            text="✦ Use Grok as my AI",
            width=200,
            height=32,
            command=self._use_grok_as_agent,
            **style_chrome_button(primary=True),
        ).pack(side="left", padx=8)

        # Task #5: one-click work presets
        preset_wrap = ctk.CTkFrame(hero, fg_color="transparent")
        preset_wrap.pack(fill="x", padx=16, pady=(0, 14))
        ctk.CTkLabel(
            preset_wrap,
            text="Quick start modes (sets tools for you):",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=_UI["label"],
        ).pack(anchor="w", pady=(0, 6))
        preset_row = ctk.CTkFrame(preset_wrap, fg_color="transparent")
        preset_row.pack(fill="x")
        try:
            from app.core.services.misc.home_presets import list_presets

            for p in list_presets():
                ctk.CTkButton(
                    preset_row,
                    text=f"{p.get('icon', '')} {p.get('label')}",
                    width=120,
                    height=36,
                    command=lambda pid=p["id"]: self._apply_home_preset(pid),
                    **style_chrome_button(primary=True),
                ).pack(side="left", padx=4, pady=2)
        except Exception:  # noqa: BLE001
            pass

        from app.ui.components.ui_steps import build_step_strip, open_create_llm_wizard

        steps = [
            {
                "n": "1",
                "title": "Talk to AI",
                "body": (
                    "Like WhatsApp: type a message at the bottom and press Enter.\n"
                    "Examples: “What is on my Desktop?” or “Search the web for weather today.”"
                ),
                "btn": "Start talking",
                "page": "Chat",
                "prep": "chat",
            },
            {
                "n": "2",
                "title": "Use an AI team",
                "body": (
                    "Several helpers work on one job and write messages you can read.\n"
                    "Click Start team, write your goal in normal words, then wait for the final answer."
                ),
                "btn": "Start AI team",
                "page": "Team",
                "prep": None,
            },
            {
                "n": "3",
                "title": "Make my own AI",
                "body": (
                    "Give it a name and a personality. No technical knowledge needed.\n"
                    "One guided wizard — then you can chat with it."
                ),
                "btn": "✨ Make my AI",
                "page": "wizard",
                "prep": "wizard",
            },
            {
                "n": "4",
                "title": "See activity",
                "body": (
                    "See if the computer is busy, if a job finished, or if something failed.\n"
                    "Open this while the AI is working."
                ),
                "btn": "See activity",
                "page": "Monitor",
                "prep": None,
            },
        ]

        # Step progress always visible
        strip_bar = ctk.CTkFrame(frame, **style_card())
        strip_bar.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        ctk.CTkLabel(
            strip_bar,
            text="Your path (all steps always visible):",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=_UI["label"],
        ).pack(anchor="w", padx=14, pady=(10, 4))
        build_step_strip(
            strip_bar,
            ["Talk", "AI team", "Make my AI", "Activity"],
            current=0,
        ).pack(anchor="w", padx=14, pady=(0, 12))

        # Giant step cards
        scroll = ctk.CTkScrollableFrame(frame, fg_color="transparent")
        scroll.grid(row=2, column=0, sticky="nsew")
        frame.grid_rowconfigure(2, weight=1)
        scroll.grid_columnconfigure(0, weight=1)

        def go(step: dict) -> None:
            if step.get("prep") == "wizard" or step.get("page") == "wizard":
                open_create_llm_wizard(self)
                return
            if step.get("prep") == "chat":
                if hasattr(self, "_chat_state"):
                    self._chat_state["mode"] = "action"
                    self._chat_state["terminal_enabled"] = True
                    self._chat_state["use_workflow_graph"] = False
                if hasattr(self, "chat_mode_var"):
                    try:
                        self.chat_mode_var.set("action")
                    except Exception:  # noqa: BLE001
                        pass
                if hasattr(self, "chat_terminal_var"):
                    try:
                        self.chat_terminal_var.set(True)
                    except Exception:  # noqa: BLE001
                        pass
            self.show_page(str(step["page"]))

        for s in steps:
            card = ctk.CTkFrame(scroll, **style_card())
            card.pack(fill="x", pady=10, padx=4)
            # Soft left accent strip for hierarchy
            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(fill="x", padx=4, pady=4)
            strip = ctk.CTkFrame(
                inner, width=4, fg_color=_UI["accent"], corner_radius=2
            )
            strip.pack(side="left", fill="y", padx=(8, 0), pady=8)
            body_col = ctk.CTkFrame(inner, fg_color="transparent")
            body_col.pack(side="left", fill="both", expand=True, padx=8)
            top = ctk.CTkFrame(body_col, fg_color="transparent")
            top.pack(fill="x", padx=12, pady=(14, 4))
            badge = ctk.CTkLabel(
                top,
                text=s["n"],
                width=44,
                height=44,
                corner_radius=22,
                fg_color=_UI["btn_primary_bg"],
                text_color=_UI["btn_primary_text"],
                font=ctk.CTkFont(size=18, weight="bold"),
            )
            badge.pack(side="left", padx=(0, 14))
            ctk.CTkLabel(
                top,
                text=s["title"],
                font=ctk.CTkFont(size=20, weight="bold"),
                text_color=_UI["label"],
                anchor="w",
            ).pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(
                body_col,
                text=s["body"],
                text_color=_UI["muted"],
                font=ctk.CTkFont(size=14),
                justify="left",
                wraplength=740,
                anchor="w",
            ).pack(anchor="w", padx=70, pady=(0, 10))
            # One primary CTA per card
            ctk.CTkButton(
                body_col,
                text=s["btn"] + "  →",
                width=200,
                height=40,
                corner_radius=12,
                font=ctk.CTkFont(size=14, weight="bold"),
                command=lambda st=s: go(st),
                **style_chrome_button(primary=True),
            ).pack(anchor="w", padx=70, pady=(0, 18))

        # Mini FAQ
        faq = ctk.CTkFrame(frame, **style_card())
        faq.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        ctk.CTkLabel(
            faq,
            text="Quick answers",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=_UI["label"],
        ).pack(anchor="w", padx=16, pady=(12, 4))
        faq_text = (
            "• Make an AI: tap “Make my AI” (step 3). Answer 3 short questions.\n"
            "• Talk to AI: tap “Start talking”, type, press Enter.\n"
            "• Window too small? Use the OS maximize button on the top title bar.\n"
            "• More options? Left bottom “Show all pages”.\n"
            "• Stuck? Left bottom “Help me”."
        )
        ctk.CTkLabel(
            faq,
            text=faq_text,
            text_color=_UI["muted"],
            font=ctk.CTkFont(size=12),
            justify="left",
            wraplength=760,
            anchor="w",
        ).pack(anchor="w", padx=16, pady=(0, 14))

    def _apply_home_preset(self, preset_id: str) -> None:
        """Task #5: apply Research / Control PC / Code / Team tool flags and open page."""
        from app.core.services.misc.home_presets import get_preset, apply_preset_to_chat_state
        from app.services import chat_store as chat_svc

        p = get_preset(preset_id)
        if not p:
            self.set_status(f"Unknown preset: {preset_id}", toast=True)
            return
        # Risk tier first
        try:
            from app.services.agent_harness.permissions import set_risk_tier

            set_risk_tier(str(p.get("risk_tier") or "ask"))
        except Exception:  # noqa: BLE001
            pass
        # Chat state flags (persist even before Chat page builds vars)
        try:
            if not getattr(self, "_chat_state", None):
                self._chat_state = self._load_active_chat()
            apply_preset_to_chat_state(self._chat_state, str(p["id"]))
            chat_svc.save_chat(self._chat_state)
        except Exception:  # noqa: BLE001
            try:
                if hasattr(self, "_chat_state") and self._chat_state is not None:
                    apply_preset_to_chat_state(self._chat_state, str(p["id"]))
            except Exception:  # noqa: BLE001
                pass
        # Sync UI vars if Chat already built
        try:
            if hasattr(self, "chat_mode_var"):
                self.chat_mode_var.set(str(p.get("mode") or "action"))
            if hasattr(self, "chat_terminal_var"):
                self.chat_terminal_var.set(bool(p.get("terminal_enabled")))
            if hasattr(self, "chat_laptop_var"):
                self.chat_laptop_var.set(bool(p.get("laptop_enabled")))
            if hasattr(self, "chat_skills_var"):
                self.chat_skills_var.set(bool(p.get("skills_enabled", True)))
            if hasattr(self, "chat_mcp_var"):
                self.chat_mcp_var.set(bool(p.get("mcp_enabled", True)))
            if hasattr(self, "chat_safety_var"):
                self.chat_safety_var.set(bool(p.get("safety_mode")))
            if hasattr(self, "chat_workflow_var"):
                self.chat_workflow_var.set(bool(p.get("use_workflow_graph")))
            if hasattr(self, "_on_chat_flags_save"):
                try:
                    self._on_chat_flags_save()
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            pass

        page = str(p.get("page") or "Chat")
        self.set_status(str(p.get("status") or p.get("label")), toast=True)
        self.show_page(page)
        # Prefill composer for chat-based presets
        starter = str(p.get("starter") or "")
        if page == "Chat" and starter:
            def _fill() -> None:
                try:
                    if hasattr(self, "chat_input"):
                        self._composer_is_placeholder = False
                        self.chat_input.delete("1.0", "end")
                        self.chat_input.insert("1.0", starter)
                        from app.ui.themes import UI as _UI

                        self.chat_input.configure(text_color=_UI["label"])
                        self._update_composer_status()
                except Exception:  # noqa: BLE001
                    pass

            try:
                self.after(120, _fill)
            except Exception:  # noqa: BLE001
                _fill()

    def _enable_chat_tips(self) -> None:
        cfg = storage.load_config()
        cfg["show_chat_coach"] = True
        cfg["dismiss_chat_coach"] = False
        storage.save_config(cfg)
        self.cfg = cfg
        self.set_status("Chat tips enabled — open Chat to see the coach bar", toast=True)
        self.show_page("Chat")

    def _dismiss_chat_coach(self) -> None:
        cfg = storage.load_config()
        cfg["dismiss_chat_coach"] = True
        storage.save_config(cfg)
        self.cfg = cfg
        self.show_page("Chat")
        self.set_status("Tips hidden — re-enable from Home or Help", toast=True)

    def _page_help(self) -> None:
        """In-app how-to-use guide for new users."""
        from app.ui.themes import style_chrome_button, style_card, UI as _UI
        from app.core.services.misc.user_guide import help_sections, SHORTCUTS_FRIENDLY

        root = ctk.CTkFrame(self.content, fg_color="transparent")
        root.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(2, weight=1)
        set_widget_name(root, name_page_root(PAGE_HELP))

        self._page_header(
            root,
            "How to use this app",
            "Written for everyone — not only technical people. Press F2 anytime to open this page.",
            actions=[
                ("Talk to AI", lambda: self.show_page("Chat")),
                ("Connect account", self._show_onboarding_wizard),
                ("Shortcuts", self._show_shortcuts_help),
            ],
        )

        # How to chat — always on top (Batch 3 / layman)
        how = ctk.CTkFrame(root, **style_card())
        how.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        ctk.CTkLabel(
            how,
            text="How to chat (start here)",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=_UI["label"],
        ).pack(anchor="w", padx=16, pady=(12, 4))
        ctk.CTkLabel(
            how,
            text=(
                "1. Open Talk to AI from the left menu.\n"
                "2. Type in the big box at the bottom (like a text message).\n"
                "3. Press Enter to send · Shift+Enter for a new line.\n"
                "4. Wait for the answer above — use ■ Stop if you need to cancel.\n"
                "5. Optional: Ctrl+\\ hides sidebars for a wider chat; Esc brings them back."
            ),
            text_color=_UI["muted"],
            font=ctk.CTkFont(size=13),
            justify="left",
            anchor="w",
        ).pack(anchor="w", padx=16, pady=(0, 12))

        scroll = ctk.CTkScrollableFrame(root, fg_color="transparent")
        scroll.grid(row=2, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)

        for sec in help_sections():
            card = ctk.CTkFrame(scroll, **style_card())
            card.pack(fill="x", pady=8, padx=2)
            ctk.CTkLabel(
                card,
                text=sec["title"],
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color=_UI["label"],
            ).pack(anchor="w", padx=14, pady=(12, 6))
            for item in sec.get("items") or []:
                row = ctk.CTkFrame(card, fg_color="transparent")
                row.pack(fill="x", padx=12, pady=4)
                ctk.CTkLabel(
                    row,
                    text=item.get("title") or "",
                    font=ctk.CTkFont(size=13, weight="bold"),
                    text_color=_UI["label"],
                    anchor="w",
                ).pack(anchor="w")
                ctk.CTkLabel(
                    row,
                    text=item.get("body") or "",
                    text_color=_UI["muted"],
                    font=ctk.CTkFont(size=12),
                    wraplength=780,
                    justify="left",
                    anchor="w",
                ).pack(anchor="w")
                page = item.get("page")
                if page:
                    from app.ui.components.layman_copy import friendly_name as _fn

                    ctk.CTkButton(
                        row,
                        text=f"Open {_fn(page, simple=self._is_simple_ui())} →",
                        width=140,
                        height=26,
                        command=lambda p=page: self.show_page(p),
                        **style_chrome_button(),
                    ).pack(anchor="w", pady=(4, 2))

        sc = ctk.CTkFrame(scroll, **style_card())
        sc.pack(fill="x", pady=8, padx=2)
        ctk.CTkLabel(
            sc,
            text="Keyboard & tips",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=_UI["label"],
        ).pack(anchor="w", padx=14, pady=(12, 4))
        box = ctk.CTkTextbox(sc, height=220, font=ctk.CTkFont(family="Consolas", size=12))
        box.pack(fill="x", padx=12, pady=(0, 12))
        box.insert("1.0", SHORTCUTS_FRIENDLY)
        box.configure(state="disabled")
        ctk.CTkButton(
            sc,
            text="Show chat coach bar again",
            command=self._enable_chat_tips,
            **style_chrome_button(primary=True),
        ).pack(anchor="w", padx=14, pady=(0, 14))

    def _page_work_board(self) -> None:
        """Unified work board: company tasks by status + approvals badge."""
        from app.services import company_store as company
        from app.ui.themes import UI as _UI, style_chrome_button

        root = ctk.CTkFrame(self.content, fg_color="transparent")
        root.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
        root.grid_columnconfigure((0, 1, 2, 3), weight=1)
        root.grid_rowconfigure(1, weight=1)

        self._page_header(
            root,
            "Work board",
            "Company tasks by status — Chat stays free while workers run.",
            columnspan=4,
            actions=[
                ("Refresh", lambda: self.show_page("Work")),
                ("Approvals", lambda: self.show_page("Approvals")),
                ("CEO", lambda: self.show_page("CEO")),
            ],
        )

        tasks: list[dict] = []
        try:
            if hasattr(company, "list_work_tasks"):
                tasks = list(company.list_work_tasks() or [])
        except Exception:  # noqa: BLE001
            tasks = []
        if not tasks:
            try:
                from app.paths import data_dir
                import json as _json

                wdir = data_dir() / "company" / "work_tasks"
                for p in sorted(wdir.glob("*.json"), reverse=True)[:80]:
                    try:
                        tasks.append(_json.loads(p.read_text(encoding="utf-8")))
                    except Exception:  # noqa: BLE001
                        pass
            except Exception:  # noqa: BLE001
                tasks = []

        cols = {
            "queued": ("Todo / queued", []),
            "running": ("Running", []),
            "waiting": ("Waiting approval", []),
            "done": ("Done", []),
        }
        for t in tasks:
            st = str(t.get("status") or "queued").lower()
            if st in ("pending_approval", "waiting", "needs_approval"):
                cols["waiting"][1].append(t)
            elif st in ("running", "in_progress", "active"):
                cols["running"][1].append(t)
            elif st in ("done", "completed", "success", "failed", "error"):
                cols["done"][1].append(t)
            else:
                cols["queued"][1].append(t)

        # Pending company approvals also in waiting
        try:
            for ap in company.list_approvals(status="pending") or []:
                cols["waiting"][1].append(
                    {
                        "title": f"Approval: {ap.get('title') or ap.get('id', '')[:8]}",
                        "status": "pending_approval",
                        "description": str(ap.get("summary") or ap.get("description") or "")[:200],
                    }
                )
        except Exception:  # noqa: BLE001
            pass

        for i, key in enumerate(("queued", "running", "waiting", "done")):
            title, items = cols[key]
            col = ctk.CTkScrollableFrame(root, fg_color=_UI["top_bg"], corner_radius=10)
            col.grid(row=1, column=i, sticky="nsew", padx=4, pady=8)
            ctk.CTkLabel(
                col, text=f"{title} ({len(items)})", font=ctk.CTkFont(weight="bold"), text_color=_UI["label"]
            ).pack(anchor="w", padx=8, pady=8)
            if not items:
                ctk.CTkLabel(col, text="—", text_color=_UI["muted"]).pack(anchor="w", padx=8, pady=4)
            for t in items[:40]:
                card = ctk.CTkFrame(col, corner_radius=8)
                card.pack(fill="x", padx=6, pady=4)
                ctk.CTkLabel(
                    card,
                    text=(t.get("title") or t.get("name") or t.get("id") or "task")[:60],
                    font=ctk.CTkFont(size=12, weight="bold"),
                    anchor="w",
                    text_color=_UI["label"],
                ).pack(anchor="w", padx=8, pady=(6, 2))
                ctk.CTkLabel(
                    card,
                    text=f"{t.get('status') or ''} · {t.get('role_id') or t.get('role') or ''}",
                    text_color=_UI["muted"],
                    font=ctk.CTkFont(size=11),
                    anchor="w",
                ).pack(anchor="w", padx=8, pady=(0, 6))

        bar = ctk.CTkFrame(root, fg_color="transparent")
        bar.grid(row=2, column=0, columnspan=4, sticky="ew", pady=8)
        ctk.CTkButton(bar, text="CEO", command=lambda: self.show_page("CEO"), **style_chrome_button()).pack(
            side="left", padx=4
        )
        ctk.CTkButton(
            bar, text="Approvals", command=lambda: self.show_page("Approvals"), **style_chrome_button(primary=True)
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            bar, text="Schedule", command=lambda: self.show_page("Schedule"), **style_chrome_button()
        ).pack(side="left", padx=4)

    def _page_chat(self) -> None:
        """Grok-style chat: slim chrome, message-first, tools in overflow menu."""
        from app.services import providers as prov
        from app.ui.themes import (
            UI as _UI,
            style_chrome_button,
            style_entry,
            style_option_menu,
            style_segmented,
            style_switch,
        )

        self._chat_ui = _UI
        self._style_chrome_button = style_chrome_button
        self._style_option_menu = style_option_menu
        self._style_entry = style_entry
        self._style_segmented = style_segmented
        self._style_switch = style_switch
        self._chat_page_gen = int(getattr(self, "_chat_page_gen", 0) or 0) + 1

        # Match grok.com canvas to content area
        try:
            self.content.configure(fg_color=_UI["chat_bg"])
        except Exception:  # noqa: BLE001
            pass
        root = ctk.CTkFrame(self.content, fg_color=_UI["chat_bg"])
        root.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        # Shell: [History rail | main chat] — rail fixed width, main takes rest
        root.grid_columnconfigure(0, weight=0, minsize=0)
        root.grid_columnconfigure(1, weight=1)
        root.grid_rowconfigure(0, weight=0, minsize=46)
        root.grid_rowconfigure(1, weight=0, minsize=40)
        root.grid_rowconfigure(2, weight=0, minsize=36)
        root.grid_rowconfigure(3, weight=1)
        self._chat_root = root
        set_widget_name(root, name_page_root(PAGE_CHAT))
        self._build_chat_view_bar(root)
        self._build_chat_cycle_bar(root)
        self._build_chat_goal_banner(root)
        self._sanitize_chat_attachments()
        self._chat_rail_collapsed = bool(
            (self.cfg or storage.load_config()).get("chat_rail_collapsed", False)
        )
        if bool(getattr(self, "_one_screen", False)):
            self._chat_rail_collapsed = True

        # Density: default compact so the reply list gets max vertical space.
        # Extra bars only when user clicks "Comfort" (saved in config).
        try:
            cfg_d = storage.load_config()
            # One-time layout fix (1.23.3): reclaim reply space if Comfort was left on
            if not cfg_d.get("chat_layout_v1233") and cfg_d.get("chat_density") == "comfortable":
                cfg_d["chat_density"] = "compact"
            # 1.27.46: Comfort bars hide the answer. Compact unless the user just chose Comfort.
            if cfg_d.get("chat_density") == "comfortable" and not cfg_d.get("chat_density_keep_comfort"):
                cfg_d["chat_density"] = "compact"
                cfg_d["chat_density_user_set"] = True
                storage.save_config(cfg_d)
                self.cfg = cfg_d
                cfg_d["chat_layout_v1233"] = True
                storage.save_config(cfg_d)
                self.cfg = cfg_d
            dens = str(cfg_d.get("chat_density") or "compact").lower()
        except Exception:  # noqa: BLE001
            dens = "compact"
        if dens not in ("compact", "comfortable"):
            dens = "compact"
        self._chat_density = dens
        # Grok-like: hide coach tips by default in Easy mode
        if self._is_simple_ui():
            try:
                cfg_c = storage.load_config()
                if "dismiss_chat_coach" not in cfg_c:
                    cfg_c["dismiss_chat_coach"] = True
                    storage.save_config(cfg_c)
                    self.cfg = cfg_c
            except Exception:  # noqa: BLE001
                pass

        # --- state defaults (vars must exist for send / overflow menu) ---
        self.chat_terminal_var = ctk.BooleanVar(master=self, value=bool(self._chat_state.get("terminal_enabled", True)))
        self.chat_skills_var = ctk.BooleanVar(master=self, value=bool(self._chat_state.get("skills_enabled", True)))
        self.chat_mcp_var = ctk.BooleanVar(master=self, value=bool(self._chat_state.get("mcp_enabled", True)))
        self.chat_safety_var = ctk.BooleanVar(master=self, value=bool(self._chat_state.get("safety_mode", False)))
        self.chat_laptop_var = ctk.BooleanVar(master=self, value=bool(self._chat_state.get("laptop_enabled", True)))
        # Org pipeline default OFF — normal chat is single-reply; pipeline is opt-in
        self.chat_workflow_var = ctk.BooleanVar(
            master=self, value=bool(self._chat_state.get("use_workflow_graph", False))
        )
        # Org chart for pipeline: fixed saved chart or LLM creates for goal
        self._LLM_CREATE_ORG_LABEL = "✨ LLM creates org for goal"
        self._chat_org_gmap: dict[str, str] = {}
        org_mode = str(self._chat_state.get("org_mode") or "fixed").lower()
        if org_mode not in ("fixed", "llm_create"):
            org_mode = "fixed"
        self._chat_org_mode = org_mode
        self.chat_org_chart_var = ctk.StringVar(master=self, value=self._LLM_CREATE_ORG_LABEL if org_mode == "llm_create" else "")
        mode = (self._chat_state.get("mode") or "action").lower()
        self.chat_mode_var = ctk.StringVar(master=self, value=mode if mode in ("plan", "action") else "action")
        self.chat_show_tools_var = ctk.BooleanVar(master=self, value=bool(getattr(self, "_chat_show_tools", False)))
        self.chat_search_var = ctk.StringVar(master=self, value="")
        cfg_live = self.cfg or storage.load_config()
        # Live / Thinking / Terminal is the monitor — default ON so the main chat stays an answer
        if getattr(self, "_live_panel_user_on", None) is not None:
            self._live_panel_visible = bool(self._live_panel_user_on)
        else:
            self._live_panel_visible = cfg_live.get("chat_auto_live_panel", True) is not False
        # Right Setup panel (system prompt + params + tools) — persisted expand/collapse
        self._chat_setup_expanded = bool(cfg_live.get("chat_setup_panel_open", False))
        self._chat_setup_sections: dict[str, bool] = dict(
            getattr(self, "_chat_setup_sections", None)
            or {
                "connection": True,
                "prompt": True,
                "params": True,
                "tools": True,
            }
        )
        self._chat_setup_width = int(cfg_live.get("chat_setup_panel_width") or 340)
        self._chat_setup_width = max(280, min(480, self._chat_setup_width))

        # Provider / model state (used by overflow + status line)
        try:
            active = prov.resolve_active_llm()
        except Exception:  # noqa: BLE001
            active = {"provider_id": "openai", "model": "gpt-4o-mini", "provider_name": "OpenAI"}
        providers = prov.list_providers()
        pnames = [p.get("name") or p["id"] for p in providers] or ["OpenAI"]
        self._provider_name_to_id = {p.get("name") or p["id"]: p["id"] for p in providers}
        self.chat_provider_var = ctk.StringVar(master=self, value=active.get("provider_name") or pnames[0])
        pid = active.get("provider_id") or "openai"
        pobj = prov.get_provider(pid) or {}
        models = list(pobj.get("models_cache") or [])
        active_model = self._pinned_or_active_model(active)
        if active_model and active_model not in models:
            models = [active_model] + models
        if active_model and active_model in models:
            models = [active_model] + [m for m in models if m != active_model]
        if not models:
            models = [active_model or "gpt-4o-mini"]
        self._ignore_model_callback = True
        self.chat_model_var = ctk.StringVar(master=self, value=active_model or models[0])
        self._chat_model_choices = models[:80]
        if active_model and active_model not in self._chat_model_choices:
            self._chat_model_choices = [active_model] + self._chat_model_choices
        try:
            from app.services import providers as _prov_pin

            if active_model:
                _prov_pin.set_active(pid, model=active_model)
                cfg_m = storage.load_config()
                cfg_m["model"] = active_model
                storage.save_config(cfg_m)
                self.cfg = cfg_m
        except Exception:  # noqa: BLE001
            pass
        self.after(400, lambda: setattr(self, "_ignore_model_callback", False))
        self._chat_all_models = list(pobj.get("models_cache") or models)
        self._chat_provider_choices = pnames

        agents = storage.list_agents()
        self._chat_agent_choices = ["Default assistant"] + [
            f"{a.get('name') or a.get('role') or 'Agent'}|{a['id']}" for a in agents
        ]
        current_aid = self._chat_state.get("agent_id") or ""
        current_label = "Default assistant"
        for choice in self._chat_agent_choices:
            if "|" in choice and choice.split("|")[-1] == current_aid:
                current_label = choice.split("|")[0]
                break
        self._chat_agent_display = current_label

        # Chat list cache for overflow switcher
        chats = chat_store.list_chats()
        if not chats:
            c = chat_store.new_chat("Main chat")
            self._chat_state = self._load_active_chat()
            chats = chat_store.list_chats()
        self._chat_switch_choices = [
            f"{('📌 ' if c.get('pinned') else '')}{c.get('title') or c['id'][:6]}|{c['id']}"
            for c in chats[:40]
        ]

        # Main column holds all existing chat chrome (features preserved)
        main = ctk.CTkFrame(root, fg_color=_UI["chat_bg"], corner_radius=0)
        main.grid(row=3, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        self._chat_main = main
        self._build_chat_history_rail(root)

        # ========== ROW 0: slim top (grok.com is nearly chrome-free) ==========
        top = ctk.CTkFrame(
            main,
            fg_color=_UI.get("top_bg", _UI["chat_bg"]),
            corner_radius=0,
            height=52,
            border_width=1,
            border_color=_UI.get("top_border", ("#e5e5e5", "#2a2a2a")),
        )
        top.grid(row=0, column=0, sticky="ew", pady=(0, 0))
        top.grid_columnconfigure(2, weight=1)
        top.grid_propagate(False)
        main.grid_rowconfigure(0, minsize=52, weight=0)
        self._chat_top_bar = top

        top.grid_columnconfigure(1, weight=1)
        self._chat_tabs_bar = ctk.CTkFrame(top, fg_color="transparent")
        self._chat_tabs_bar.grid(row=0, column=0, sticky="w", padx=4, pady=4)
        self._open_chat_tabs = list(getattr(self, "_open_chat_tabs", []) or [])
        aid = chat_store.get_active_chat_id()
        if aid and aid not in self._open_chat_tabs:
            self._open_chat_tabs.insert(0, aid)
        self._open_chat_tabs = self._open_chat_tabs[:6]
        self._refresh_chat_tabs_bar()

        pin_mark = "📌 " if self._chat_state.get("pinned") else ""
        # Clear rename affordance (Batch 3) — title + “Rename” cue
        title_txt = f"{pin_mark}{self._chat_state.get('title') or 'Chat'}"
        self.chat_title_label = ctk.CTkButton(
            top,
            text=f"{title_txt}  ·  rename",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
            command=self._chat_rename,
            **style_chrome_button(),
        )
        self.chat_title_label.grid(row=0, column=1, sticky="ew", padx=4)
        set_widget_name(self.chat_title_label, name_chat_topbar_title())

        right = ctk.CTkFrame(top, fg_color="transparent")
        right.grid(row=0, column=2, sticky="e", padx=4, pady=4)
        self._chat_top_right = right

        # Compact chips (always on top row; primary chrome in compact density)
        from app.services import company_store as _company

        co_mode0 = _company.get_approval_mode()
        self.chat_company_approval_var = ctk.StringVar(
            master=self, value="auto" if co_mode0 == "auto" else "manual"
        )
        cfg0 = storage.load_config()
        self.chat_tool_approval_var = ctk.BooleanVar(
            master=self, value=bool(cfg0.get("tool_approval_required"))
        )

        # Layman: show "Can use tools" instead of Action/Plan jargon
        if self._is_simple_ui():
            from app.ui.components.layman_copy import MODE_TOOLS_ON, MODE_PLAN_ONLY

            mode_txt = (
                MODE_TOOLS_ON
                if (self.chat_mode_var.get() or "action") == "action"
                else MODE_PLAN_ONLY
            )
            self._mode_chip_btn = ctk.CTkButton(
                right,
                text=mode_txt,
                width=150,
                height=28,
                command=self._chat_cycle_mode_chip,
                **style_chrome_button(active=(self.chat_mode_var.get() == "action")),
            )
        else:
            # Expert: short labels (Batch 2) — full names in Caps / ⋯
            mode_txt = "Act" if (self.chat_mode_var.get() or "action") == "action" else "Plan"
            self._mode_chip_btn = ctk.CTkButton(
                right,
                text=mode_txt,
                width=52,
                height=28,
                command=self._chat_cycle_mode_chip,
                **style_chrome_button(active=(self.chat_mode_var.get() == "action")),
            )
        self._mode_chip_btn.pack(side="left", padx=1)
        set_widget_name(self._mode_chip_btn, name_chat_topbar_mode_chip())
        # P0.2: Compare / Multi-model chip
        self._compare_chip_btn = ctk.CTkButton(
            right,
            text="Compare" if not self._compare_mode else "Compare●",
            width=72,
            height=28,
            command=self._chat_toggle_compare_mode,
            **style_chrome_button(active=bool(self._compare_mode)),
        )
        self._compare_chip_btn.pack(side="left", padx=1)
        self._tooltip(
            self._compare_chip_btn,
            chat_control_help("compare"),
        )
        if not self._is_simple_ui():
            ctk.CTkButton(
                right,
                text="?",
                width=26,
                height=28,
                command=self._chat_mode_help,
                **style_chrome_button(),
            ).pack(side="left", padx=1)

        simple_chat = self._is_simple_ui()
        if not simple_chat:
            tasks_txt = (self.chat_company_approval_var.get() or "manual").lower()
            self._tasks_chip_btn = ctk.CTkButton(
                right,
                text=f"T:{tasks_txt[:3]}",
                width=48,
                height=28,
                command=self._chat_cycle_tasks_chip,
                **style_chrome_button(),
            )
            self._tasks_chip_btn.pack(side="left", padx=1)
            set_widget_name(self._tasks_chip_btn, name_chat_topbar_tasks_chip())

        # Task #4: Risk tier badge (Read-only / Ask / Full) — visible in Easy + Expert
        try:
            from app.services.agent_harness.permissions import risk_tier_badge

            _risk_txt = risk_tier_badge()
        except Exception:  # noqa: BLE001
            _risk_txt = "✋ Ask"
        self._risk_chip_btn = ctk.CTkButton(
            right,
            text=_risk_txt,
            width=78 if simple_chat else 72,
            height=28,
            command=self._chat_cycle_risk_tier,
            **style_chrome_button(),
        )
        self._risk_chip_btn.pack(side="left", padx=1)
        set_widget_name(self._risk_chip_btn, name_chat_topbar_risk_chip())

        if not simple_chat:
            self._caps_chip_btn = ctk.CTkButton(
                right,
                text="Caps",
                width=48,
                height=28,
                command=self._chat_open_caps_popover,
                **style_chrome_button(),
            )
            self._caps_chip_btn.pack(side="left", padx=1)
            set_widget_name(self._caps_chip_btn, name_chat_topbar_caps_chip())
        else:
            # Layman: Mode chip + risk badge; tools stay on by default
            self._caps_chip_btn = None  # type: ignore

        # Ensure OpenRouter appears even if store is empty/corrupt
        if "OpenRouter" not in self._chat_provider_choices:
            self._chat_provider_choices = ["OpenRouter"] + list(self._chat_provider_choices)
            self._provider_name_to_id.setdefault("OpenRouter", "openrouter")

        # Easy mode (Batch 1): Mode · Model · Live · ⋯ only — provider in ⋯ / Comfort
        # Expert: provider + model on the bar (shorter widths)
        self.chat_provider_menu = ctk.CTkOptionMenu(
            right,
            values=self._chat_provider_choices,
            variable=self.chat_provider_var,
            command=self._on_chat_provider_change,
            width=100,
            height=28,
            **style_option_menu(),
        )
        if not simple_chat:
            self.chat_provider_menu.pack(side="left", padx=2)
        else:
            self.chat_provider_menu.pack_forget()
        self._tooltip(self.chat_provider_menu, chat_control_help("provider"))

        self.chat_model_menu = ctk.CTkOptionMenu(
            right,
            values=self._chat_model_choices or ["(fetch models)"],
            variable=self.chat_model_var,
            command=self._on_chat_model_change,
            width=130 if simple_chat else 140,
            height=28,
            **style_option_menu(),
        )
        self.chat_model_menu.pack(side="left", padx=2)
        self._tooltip(self.chat_model_menu, chat_control_help("models"))

        if not simple_chat:
            dens_lbl = "Comfort" if self._chat_density == "compact" else "Compact"
            self._density_btn = ctk.CTkButton(
                right,
                text=dens_lbl,
                width=64,
                height=28,
                command=self._chat_toggle_density,
                **style_chrome_button(),
            )
            self._density_btn.pack(side="left", padx=2)
            self._tooltip(self._density_btn, chat_control_help("density"))

        self._live_btn = ctk.CTkButton(
            right,
            text="Live ●" if self._live_panel_visible else "Live",
            width=56,
            height=28,
            command=self._chat_toggle_live_panel,
            **style_chrome_button(active=bool(self._live_panel_visible)),
        )
        self._live_btn.pack(side="left", padx=2)
        self._tooltip(self._live_btn, chat_control_help("live"))
        # Right drawer: system prompt, model params, tool switches
        _setup_on = bool(getattr(self, "_chat_setup_expanded", False))
        self._setup_btn = ctk.CTkButton(
            right,
            text="Setup ●" if _setup_on else "Setup",
            width=64,
            height=28,
            command=self._chat_toggle_setup_panel,
            **style_chrome_button(active=_setup_on),
        )
        self._setup_btn.pack(side="left", padx=2)
        self._tooltip(self._setup_btn, chat_control_help("setup"))
        if not simple_chat:
            _search_bar_btn = ctk.CTkButton(
                right,
                text="🔍",
                width=32,
                height=28,
                command=self._chat_open_search,
                **style_chrome_button(),
            )
            _search_bar_btn.pack(side="left", padx=1)
            self._tooltip(_search_bar_btn, chat_control_help("search_internal"))
        # One-click: make Grok the agent model (no CLI needed)
        _grok_btn = ctk.CTkButton(
            right,
            text="✦ Grok",
            width=64,
            height=28,
            command=self._use_grok_as_agent,
            **style_chrome_button(primary=True),
        )
        _grok_btn.pack(side="left", padx=2)
        self._tooltip(_grok_btn, chat_control_help("grok"))
        _overflow_btn = ctk.CTkButton(
            right,
            text="⋯",
            width=36,
            height=28,
            font=ctk.CTkFont(size=16),
            command=self._chat_open_overflow_menu,
            **style_chrome_button(),
        )
        _overflow_btn.pack(side="left", padx=2)
        self._tooltip(_overflow_btn, chat_control_help("overflow"))

        # Coach bar teaches controls until dismissed (row 1 when visible)
        show_coach = not bool((self.cfg or {}).get("dismiss_chat_coach"))
        coach_row = 1 if show_coach else 0
        llm_row = 2 if show_coach else 1
        modes_row = 3 if show_coach else 2
        mid_row = 4 if show_coach else 3
        composer_row = 5 if show_coach else 4
        self._chat_grid_rows = {
            "coach": coach_row if show_coach else None,
            "llm": llm_row,
            "modes": modes_row,
            "mid": mid_row,
            "composer": composer_row,
        }

        if show_coach:
            from app.core.services.misc.user_guide import coach_banner_text

            coach = ctk.CTkFrame(
                main,
                fg_color=_UI["accent_soft"],
                corner_radius=12,
                border_width=1,
                border_color=_UI["top_border"],
            )
            coach.grid(row=coach_row, column=0, sticky="ew", pady=(0, 6))
            ctk.CTkLabel(
                coach,
                text="Quick tips (you can hide this)",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=_UI["label"],
            ).pack(anchor="w", padx=12, pady=(8, 2))
            ctk.CTkLabel(
                coach,
                text=coach_banner_text(),
                text_color=_UI["muted"],
                font=ctk.CTkFont(size=12 if self._is_simple_ui() else 11),
                wraplength=980,
                justify="left",
            ).pack(anchor="w", padx=12, pady=(0, 4))
            cbar = ctk.CTkFrame(coach, fg_color="transparent")
            cbar.pack(fill="x", padx=8, pady=(0, 8))
            ctk.CTkButton(
                cbar,
                text="Open Help (F2)",
                width=120,
                height=26,
                command=lambda: self.show_page("Help"),
                **style_chrome_button(primary=True),
            ).pack(side="left", padx=4)
            ctk.CTkButton(
                cbar,
                text="Dismiss tips",
                width=100,
                height=26,
                command=self._dismiss_chat_coach,
                **style_chrome_button(),
            ).pack(side="left", padx=4)

        # ========== ROW: provider / model + search (comfortable only) ==========
        llm_bar = ctk.CTkFrame(main, fg_color=_UI["top_bg"], corner_radius=10, height=44)
        self._chat_llm_bar = llm_bar
        llm_bar.grid(row=llm_row, column=0, sticky="ew", pady=(0, 6))
        llm_bar.grid_propagate(False)
        llm_inner = ctk.CTkFrame(llm_bar, fg_color="transparent")
        llm_inner.pack(side="left", fill="x", expand=True, padx=8, pady=5)

        ctk.CTkLabel(
            llm_inner,
            text="Provider",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=_UI["label"],
        ).pack(side="left", padx=(0, 4))
        # Comfortable bar keeps wider menus (synced with top compact menus via same vars)
        self.chat_provider_menu_wide = ctk.CTkOptionMenu(
            llm_inner,
            values=self._chat_provider_choices,
            variable=self.chat_provider_var,
            command=self._on_chat_provider_change,
            width=130,
            height=30,
            **style_option_menu(),
        )
        self.chat_provider_menu_wide.pack(side="left", padx=2)
        set_widget_name(self.chat_provider_menu_wide, name_chat_toolbar_provider_menu())

        ctk.CTkLabel(
            llm_inner,
            text="Model",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=_UI["label"],
        ).pack(side="left", padx=(10, 4))
        self.chat_model_menu_wide = ctk.CTkOptionMenu(
            llm_inner,
            values=self._chat_model_choices or ["(fetch models)"],
            variable=self.chat_model_var,
            command=self._on_chat_model_change,
            width=200,
            height=30,
            **style_option_menu(),
        )
        self.chat_model_menu_wide.pack(side="left", padx=2)
        set_widget_name(self.chat_model_menu_wide, name_chat_toolbar_model_menu())
        self.chat_model_search_var = ctk.StringVar(master=self, value="")
        self.chat_model_search = ctk.CTkEntry(
            llm_inner,
            textvariable=self.chat_model_search_var,
            placeholder_text="Search models… e.g. claude, llama, gpt",
            width=200,
            height=30,
            **style_entry(),
        )
        self.chat_model_search.pack(side="left", padx=6)
        set_widget_name(self.chat_model_search, name_chat_toolbar_model_search())
        self.chat_model_search.bind("<Return>", lambda _e: self._chat_filter_models())
        self.chat_model_search.bind("<KeyRelease>", lambda _e: self._chat_filter_models_live())
        find_models_btn = ctk.CTkButton(
            llm_inner,
            text="Find",
            width=56,
            height=30,
            command=self._chat_open_model_picker,
            **style_chrome_button(primary=True),
        )
        find_models_btn.pack(side="left", padx=2)
        set_widget_name(find_models_btn, name_chat_toolbar_button("find_models"))
        refresh_models_btn = ctk.CTkButton(
            llm_inner,
            text="↻ models",
            width=78,
            height=30,
            command=self._chat_fetch_models,
            **style_chrome_button(),
        )
        refresh_models_btn.pack(side="left", padx=4)
        set_widget_name(refresh_models_btn, name_chat_toolbar_button("refresh_models"))

        # Hidden stubs still used by older callbacks
        self.chat_agent_menu = ctk.CTkOptionMenu(
            llm_inner,
            values=[x.split("|")[0] for x in self._chat_agent_choices],
            command=self._on_chat_agent_change,
            width=1,
            height=1,
        )
        self.chat_agent_menu.set(current_label)
        self.chat_agent_menu.pack_forget()
        self.chat_switch_menu = ctk.CTkOptionMenu(
            llm_inner,
            values=[x.split("|")[0] for x in self._chat_switch_choices] or ["Main"],
            command=self._on_chat_switch,
            width=1,
            height=1,
        )
        self.chat_switch_menu.pack_forget()

        # ========== ROW 2: modes (hidden in Easy — grok.com has no second toolbar) ==========
        modes_bar = ctk.CTkFrame(main, fg_color=_UI["top_bg"], corner_radius=10)
        self._chat_modes_bar = modes_bar
        modes_inner = ctk.CTkFrame(modes_bar, fg_color="transparent")
        modes_inner.pack(side="left", fill="x", expand=True, padx=8, pady=6)

        if self._is_simple_ui():
            # Ensure tools useful defaults — no visible modes bar (like grok.com)
            try:
                self.chat_mode_var.set("action")
                self.chat_terminal_var.set(True)
                self.chat_laptop_var.set(True)
                self.chat_skills_var.set(True)
                self.chat_mcp_var.set(True)
                self.chat_workflow_var.set(False)
            except Exception:  # noqa: BLE001
                pass
            self.chat_mode_seg = None  # type: ignore
            self.chat_org_chart_menu = None  # type: ignore
            self._ctx_chip_lbl = ctk.CTkLabel(modes_inner, text="")
            # Do not pack modes_bar — message list goes edge-to-edge under slim top
            modes_bar.grid_remove()
        else:
            modes_bar.grid(row=modes_row, column=0, sticky="ew", pady=(0, 6))
            ctk.CTkLabel(
                modes_inner,
                text="Mode",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=_UI["label"],
            ).pack(side="left", padx=(0, 4))
            self.chat_mode_seg = ctk.CTkSegmentedButton(
                modes_inner,
                values=["plan", "action"],
                variable=self.chat_mode_var,
                command=lambda _v: (self._on_chat_flags_save(), self._refresh_mode_tasks_chips()),
                width=150,
                height=30,
                **style_segmented(),
            )
            self.chat_mode_seg.pack(side="left", padx=(0, 12))
            self._tooltip(self.chat_mode_seg, chat_control_help("mode"))

            ctk.CTkLabel(
                modes_inner,
                text="Tasks",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=_UI["label"],
            ).pack(side="left", padx=(0, 4))
            self.chat_company_approval_seg = ctk.CTkSegmentedButton(
                modes_inner,
                values=["manual", "auto"],
                variable=self.chat_company_approval_var,
                command=lambda v: (
                    self._on_chat_company_approval_change(v),
                    self._refresh_mode_tasks_chips(),
                ),
                width=150,
                height=30,
                **style_segmented(),
            )
            self.chat_company_approval_seg.pack(side="left", padx=(0, 12))

            ctk.CTkSwitch(
                modes_inner,
                text="Tool approval",
                variable=self.chat_tool_approval_var,
                command=self._on_chat_tool_approval_toggle,
                width=120,
                **style_switch(),
            ).pack(side="left", padx=(0, 10))

            for text, var, width in (
                ("Terminal", self.chat_terminal_var, 90),
                ("Skills", self.chat_skills_var, 80),
                ("MCP", self.chat_mcp_var, 70),
                ("Laptop", self.chat_laptop_var, 80),
                ("Org pipeline", self.chat_workflow_var, 110),
                ("Safety", self.chat_safety_var, 80),
            ):
                ctk.CTkSwitch(
                    modes_inner,
                    text=text,
                    variable=var,
                    command=self._on_chat_flags_save,
                    width=width,
                    **style_switch(),
                ).pack(side="left", padx=2)

            ctk.CTkLabel(
                modes_inner,
                text="Org chart",
                text_color=_UI["muted"],
                font=ctk.CTkFont(size=11),
            ).pack(side="left", padx=(8, 2))
            self.chat_org_chart_menu = ctk.CTkOptionMenu(
                modes_inner,
                variable=self.chat_org_chart_var,
                values=[self._LLM_CREATE_ORG_LABEL],
                width=200,
                height=28,
                command=lambda _v: self._on_chat_org_chart_change(),
            )
            self.chat_org_chart_menu.pack(side="left", padx=2)
            self._refresh_chat_org_chart_menu()

            _agent_btn = ctk.CTkButton(
                modes_inner,
                text="Agent…",
                width=70,
                height=28,
                command=self._chat_pick_agent_dialog,
                **style_chrome_button(),
            )
            _agent_btn.pack(side="left", padx=(8, 2))
            set_widget_name(_agent_btn, name_chat_toolbar_button("agent"))
            self._tooltip(_agent_btn, chat_control_help("agent"))
            _context_btn = ctk.CTkButton(
                modes_inner,
                text="Context…",
                width=78,
                height=28,
                command=self._chat_context_window_dialog,
                **style_chrome_button(primary=True),
            )
            _context_btn.pack(side="left", padx=2)
            set_widget_name(_context_btn, name_chat_toolbar_button("context"))
            self._tooltip(_context_btn, chat_control_help("context"))
            self._ctx_chip_lbl_modes = ctk.CTkLabel(
                modes_inner,
                text="",
                text_color=_UI["muted"],
                font=ctk.CTkFont(size=11),
                anchor="w",
            )
            self._ctx_chip_lbl_modes.pack(side="left", padx=(6, 4))
            try:
                self.after(200, self._refresh_context_chip)
            except Exception:  # noqa: BLE001
                pass
        _more_btn = ctk.CTkButton(
            modes_inner,
            text="More…",
            width=64,
            height=28,
            command=self._chat_open_overflow_menu,
            **style_chrome_button(primary=True),
        )
        _more_btn.pack(side="left", padx=2)
        set_widget_name(_more_btn, name_chat_toolbar_button("more"))
        self._tooltip(_more_btn, chat_control_help("more"))

        # ========== ROW 3: messages (+ optional live) ==========
        mid = ctk.CTkFrame(main, fg_color="transparent")
        mid.grid(row=mid_row, column=0, sticky="nsew", pady=(0, 6))
        mid.grid_columnconfigure(0, weight=1)
        mid.grid_rowconfigure(0, weight=1)
        main.grid_rowconfigure(mid_row, weight=1)
        self._chat_mid = mid
        set_widget_name(mid, build_name("app", REGION_CONTENT, CHAT_MESSAGES, PREFIX_FRAME, "mid"))
        self._apply_chat_density_layout()

        self.chat_scroll = ctk.CTkScrollableFrame(
            mid,
            fg_color=_UI["chat_bg"],
            corner_radius=0,  # grok.com: edge-to-edge message canvas
        )
        self.chat_scroll.grid(row=0, column=0, sticky="nsew")
        self.chat_scroll.grid_columnconfigure(0, weight=1)
        set_widget_name(self.chat_scroll, name_chat_messages_scroll())
        try:
            c0 = self._chat_canvas()
            if c0 is not None:
                c0.bind("<Configure>", lambda _e: self._fit_chat_scroll_inner(), add="+")
        except Exception:  # noqa: BLE001
            pass
        try:
            # Prefer a grab-friendly vertical bar
            sb = getattr(self.chat_scroll, "_scrollbar", None)
            if sb is not None:
                sb.configure(width=14)
        except Exception:  # noqa: BLE001
            pass

        # Live panel (created but may be hidden)
        act = ctk.CTkFrame(
            mid,
            corner_radius=14,
            width=260,
            fg_color=_UI["top_bg"],
            border_width=1,
            border_color=_UI["top_border"],
        )
        self._chat_live_frame = act
        act.grid_rowconfigure(2, weight=1)
        act.grid_rowconfigure(3, weight=0)  # toolbar row
        act.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            act,
            text="💭 Thinking / tools",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=_UI["label"],
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 2))
        self.side_panel_mode = ctk.StringVar(master=self, value="Terminal")
        ctk.CTkSegmentedButton(
            act,
            values=["Activity", "Agents", "Artifacts", "Terminal"],
            variable=self.side_panel_mode,
            command=lambda _v: self._refresh_side_panel(),
            width=300,
        ).grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        from app.ui.themes import style_textbox

        # Content area (row 2) - panels will be shown/hidden by _refresh_side_panel
        self.activity_box = ctk.CTkTextbox(
            act,
            wrap="word",
            font=ctk.CTkFont(family="Consolas", size=11),
            **style_textbox(),
        )
        self.activity_box.grid(row=2, column=0, sticky="nsew", padx=6, pady=(0, 4))
        
        self.agent_track_box = ctk.CTkTextbox(
            act,
            wrap="word",
            font=ctk.CTkFont(family="Consolas", size=11),
            **style_textbox(),
        )
        
        # Task #12: scrollable artifacts list (buttons per item)
        self.artifacts_frame = ctk.CTkScrollableFrame(act, fg_color="transparent")
        
        # Thinking panel: collapsible per-step cards (current + raw)
        self.thinking_box = ctk.CTkTextbox(
            act,
            wrap="word",
            font=ctk.CTkFont(family="Consolas", size=11),
            **style_textbox(),
        )
        self.thinking_list = ctk.CTkScrollableFrame(act, fg_color="transparent")
        self._thinking_card_widgets: list[dict[str, Any]] = []
        self._thinking_pinned: set[int] = set()
        self._thinking_follow_bottom = True
        self._thinking_scroll_end_ts = 0.0
        self._thinking_scroll_idle = None
        try:
            # No animated scroller here — live card updates + after(16) yview
            # was the Tcl "scroll error" / jump-loop.
            self._thinking_bind_wheel(self.thinking_list)
            canvas = getattr(self.thinking_list, "_parent_canvas", None)
            if canvas is not None:
                canvas.bind("<MouseWheel>", self._on_thinking_mousewheel)
                canvas.bind("<Button-4>", self._on_thinking_mousewheel)
                canvas.bind("<Button-5>", self._on_thinking_mousewheel)
                canvas.bind("<Configure>", lambda _e: self._fit_thinking_scroll_inner(), add="+")
        except Exception:  # noqa: BLE001
            pass
        
        # Terminal panel - shows terminal tool output with command prompt, stdout/stderr
        self.terminal_box = ctk.CTkTextbox(
            act,
            wrap="word",
            font=ctk.CTkFont(family="Consolas", size=11),
            **style_textbox(),
        )
        # Configure text tags for color-coded terminal output
        self.terminal_box.tag_config("cmd", foreground="#3b82f6")      # Blue for commands
        self.terminal_box.tag_config("stdout", foreground="#10b981")   # Green for stdout
        self.terminal_box.tag_config("stderr", foreground="#ef4444")   # Red for stderr
        self.terminal_box.tag_config("exit", foreground="#f59e0b")     # Amber for exit codes
        self.terminal_box.tag_config("cwd", foreground="#8b5cf6")      # Purple for paths
        self.terminal_box.tag_config("info", foreground="#6b7280")     # Gray for info

        # Shared toolbar (row 3) - buttons change based on active tab
        self.panel_toolbar = ctk.CTkFrame(act, fg_color="transparent")
        self.panel_toolbar.grid(row=3, column=0, sticky="ew", padx=6, pady=(0, 4))
        self._build_panel_toolbar("Activity")  # Initial toolbar for Activity tab
        
        from app.core.services.data.activity_log import get_text as _act_get

        self.activity_box.insert("1.0", _act_get() or "Activity appears here while tools run…\n")
        self._bind_activity_log()
        self._bind_agent_tracker()
        self._bind_terminal_log()
        # Right Setup drawer (system prompt + params) — expand/collapse
        self._build_chat_setup_panel(mid)
        self._chat_apply_mid_columns()
        try:
            mid.bind("<Configure>", lambda _e: self._chat_apply_mid_columns(), add="+")
        except Exception:  # noqa: BLE001
            pass
        self._refresh_side_panel()

        # ========== ROW 4: ChatGPT/Grok composer — calm pill, tools in + ==========
        # Pattern (ChatGPT 2026 teardown): calm default bar → + menu → chips → round send
        # Pattern (Grok): wide bottom bar, “What's on your mind?”, model near send
        composer_outer = ctk.CTkFrame(main, fg_color="transparent")
        composer_outer.grid(row=composer_row, column=0, sticky="ew", pady=(2, 6))
        composer_outer.grid_columnconfigure(0, weight=1)
        # Center composer like Grok/ChatGPT (~max readable width)
        side_pad = max(12, min(48, self._chat_side_pad()))
        composer = ctk.CTkFrame(
            composer_outer,
            corner_radius=28,
            fg_color=_UI.get("composer_bg", ("#ffffff", "#1a1a1a")),
            border_width=1,
            border_color=_UI.get("composer_border", ("#e5e5e5", "#2a2a2a")),
        )
        composer.pack(fill="x", padx=side_pad, pady=(0, 4))
        composer.grid_columnconfigure(1, weight=1)
        set_widget_name(composer, name_page_body(PAGE_CHAT, "composer"))

        from app.ui.components.layman_copy import (
            COMPOSER_WHATS_ON_MIND,
            COMPOSER_ASK_ANYTHING,
            send_label as _send_lbl,
            STOP_LABEL,
        )

        mode_now = (self.chat_mode_var.get() if hasattr(self, "chat_mode_var") else "action") or "action"
        self._composer_hint = ctk.CTkLabel(
            composer,
            text=self._composer_hint_text(mode_now),
            text_color=_UI["muted"],
            font=ctk.CTkFont(size=1),
            height=1,
        )
        self._composer_hint.grid_remove()

        def tool_btn(
            parent: Any,
            label: str,
            cmd: Any,
            *,
            primary: bool = False,
            width: int = 40,
            help: str | None = None,
        ) -> Any:
            b = ctk.CTkButton(
                parent,
                text=label,
                width=width,
                height=36,
                corner_radius=18,
                font=ctk.CTkFont(size=13 if self._is_simple_ui() else 12),
                command=cmd,
                **style_chrome_button(primary=primary),
            )
            b.pack(side="left", padx=2, pady=2)
            if help:
                self._tooltip(b, help)
            return b

        # Row 0: [+] [ multi-line input ................ ] [model] [↑]
        left_bar = ctk.CTkFrame(composer, fg_color="transparent")
        left_bar.grid(row=0, column=0, sticky="sw", padx=(10, 4), pady=(10, 10))
        plus_btn = tool_btn(
            left_bar,
            "＋",
            self._chat_open_plus_menu,
            primary=False,
            width=36,
            help="Attach, search, image, folder — tools stay behind + (ChatGPT pattern)",
        )
        set_widget_name(plus_btn, name_chat_composer_attach_btn())

        ph = COMPOSER_WHATS_ON_MIND if self._is_simple_ui() else COMPOSER_ASK_ANYTHING
        self._composer_placeholder = ph
        try:
            win_h = int(self.winfo_height() or 900)
        except Exception:  # noqa: BLE001
            win_h = 900
        input_h = max(52, min(96, win_h // 14))
        input_h = int(getattr(self, "_chat_input_height", 0) or input_h)
        input_h = max(52, min(max(100, win_h // 4), input_h))
        self.chat_input = ctk.CTkTextbox(
            composer,
            height=input_h,
            corner_radius=12,
            font=ctk.CTkFont(size=15),
            wrap="word",
            fg_color=_UI.get("composer_input", ("#ffffff", "#1a1a1a")),
            text_color=_UI.get("composer_text", ("#0d0d0d", "#ececec")),
            border_width=0,
            activate_scrollbars=True,
        )
        self.chat_input.grid(row=0, column=1, sticky="ew", padx=4, pady=(10, 8))
        set_widget_name(self.chat_input, name_chat_composer_input())
        self.chat_input.bind("<Control-Return>", lambda _e: self._chat_send())
        self.chat_input.bind("<Return>", self._chat_enter_send)
        self.chat_input.bind("<KeyRelease>", lambda _e: self._chat_on_input_key())
        self.chat_input.bind("<FocusIn>", lambda _e: self._composer_clear_placeholder())
        self.chat_input.bind("<FocusOut>", lambda _e: self._composer_maybe_placeholder())
        draft = str(self._chat_state.get("draft") or "").strip()
        if draft in {"?", "??", "???", "????", "...", "…"}:
            draft = ""
            try:
                self._chat_state["draft"] = ""
                chat_svc.save_chat(self._chat_state)
            except Exception:  # noqa: BLE001
                pass
        if draft:
            try:
                self.chat_input.insert("1.0", draft)
                self._composer_is_placeholder = False
            except Exception:  # noqa: BLE001
                self._composer_is_placeholder = False
        else:
            try:
                self.chat_input.insert("1.0", ph)
                self.chat_input.configure(text_color=_UI["muted"])
                self._composer_is_placeholder = True
            except Exception:  # noqa: BLE001
                self._composer_is_placeholder = False

        right_bar = ctk.CTkFrame(composer, fg_color="transparent")
        right_bar.grid(row=0, column=2, sticky="se", padx=(4, 10), pady=(10, 10))
        self.chat_model_menu_composer = ctk.CTkOptionMenu(
            right_bar,
            values=self._chat_model_choices or ["(fetch models)"],
            variable=self.chat_model_var,
            command=self._on_chat_model_change,
            width=140 if self._is_simple_ui() else 160,
            height=34,
            **style_option_menu(),
        )
        self.chat_model_menu_composer.pack(side="left", padx=(0, 6))
        set_widget_name(self.chat_model_menu_composer, name_chat_composer_mode_chip())
        self._tooltip(self.chat_model_menu_composer, chat_control_help("models"))
        self.chat_mic_btn = tool_btn(
            right_bar, "🎤", self._chat_mic, width=36, help=chat_control_help("mic")
        )
        set_widget_name(self.chat_mic_btn, name_chat_composer_mic_btn())
        self.chat_speak_btn = tool_btn(
            right_bar, "🔊", self._chat_speak_last, width=36, help=chat_control_help("speak")
        )
        set_widget_name(self.chat_speak_btn, name_chat_composer_speak_btn())
        try:
            self._voice_refresh_composer_buttons()
        except Exception:  # noqa: BLE001
            pass

        _simple_send = self._is_simple_ui()
        self.chat_send_btn = ctk.CTkButton(
            right_bar,
            text="↑",
            width=40,
            height=40,
            corner_radius=20,
            font=ctk.CTkFont(size=15 if _simple_send else 13, weight="bold"),
            command=self._chat_send,
            **style_chrome_button(primary=True),
        )
        self.chat_send_btn.pack(side="left", padx=2)
        set_widget_name(self.chat_send_btn, name_chat_composer_send_btn())
        self._tooltip(self.chat_send_btn, "Send · Enter  (Shift+Enter = new line)")
        # Pause/Stop sit under the pill when busy (shown via state enable)
        ctl_row = ctk.CTkFrame(composer_outer, fg_color="transparent")
        ctl_row.pack(fill="x", padx=side_pad, pady=(0, 0))
        self.chat_pause_btn = ctk.CTkButton(
            ctl_row,
            text="⏸ Pause",
            width=80,
            height=28,
            corner_radius=8,
            command=self._chat_toggle_pause,
            state="disabled",
            **style_chrome_button(),
        )
        self.chat_pause_btn.pack(side="right", padx=2)
        self._tooltip(self.chat_pause_btn, chat_control_help("pause"))
        self.chat_stop_btn = ctk.CTkButton(
            ctl_row,
            text="■ Stop",
            width=72,
            height=28,
            corner_radius=8,
            fg_color=("#d1d5db", "#3f3f46"),
            hover_color=("#9ca3af", "#27272a"),
            text_color=("#52525b", "#a1a1aa"),
            command=self._chat_stop,
            state="disabled",
        )
        self.chat_stop_btn.pack(side="right", padx=2)
        self._tooltip(self.chat_stop_btn, chat_control_help("stop"))

        # Status line (attachments / tokens) — quiet, under composer
        self.chat_attach_label = ctk.CTkLabel(
            composer_outer,
            text="",
            text_color=_HC_MUTED,
            anchor="w",
            font=ctk.CTkFont(size=11),
            height=16,
        )
        self.chat_attach_label.pack(fill="x", padx=side_pad + 6, pady=(2, 0))
        self.chat_status = self.chat_attach_label
        self._note_chips_host = ctk.CTkFrame(composer_outer, fg_color="transparent")
        self._note_chips_host.pack(fill="x", padx=side_pad + 6, pady=(0, 0))
        try:
            self._refresh_note_attach_chips()
        except Exception:  # noqa: BLE001
            pass
        tip = (
            "Enter send · Shift+Enter newline · ＋ tools · right-click chats to pin/delete"
            if self._is_simple_ui()
            else "Enter send · Shift+Enter newline · Ctrl+\\ focus · Ctrl+K · ＋ attach/search/image"
        )
        ctk.CTkLabel(
            composer_outer,
            text=tip,
            text_color=_HC_MUTED,
            anchor="w",
            font=ctk.CTkFont(size=10),
            height=14,
        ).pack(fill="x", padx=side_pad + 6, pady=(0, 2))
        try:
            _cwd0 = str(
                (self._chat_state or {}).get("terminal_cwd")
                or self._chat_terminal_cwd
                or app_root()
            )
            self._chat_terminal_cwd = _cwd0
            _lock0 = bool((self._chat_state or {}).get("cwd_lock"))
        except Exception:  # noqa: BLE001
            _cwd0 = str(self._chat_terminal_cwd or app_root())
            _lock0 = False
        lock_mark = " 🔒" if _lock0 else ""
        self.chat_cwd_label = ctk.CTkLabel(
            composer_outer,
            text=f"cwd: {_cwd0}{lock_mark}",
            text_color=_HC_MUTED,
            anchor="w",
            font=ctk.CTkFont(size=10),
            height=14,
        )
        if not self._is_simple_ui():
            self.chat_cwd_label.pack(fill="x", padx=side_pad + 6, pady=(0, 2))
        else:
            self.chat_cwd_label.pack_forget()
        self._update_composer_status()

        self._bind_chat_mousewheel()
        # Immediate render (truncated). after() left a blank canvas while a huge
        # transcript rebuild ran on the Tk thread.
        self._chat_render_transcript()
        if bool(getattr(self, "_one_screen", False)):
            self._set_app_menu_collapsed(True, persist=False)
            self._set_sysmon_collapsed(True, persist=False)
            rail = getattr(self, "_chat_rail_frame", None)
            try:
                if rail is not None:
                    rail.grid_remove()
            except Exception:  # noqa: BLE001
                pass
        self._refresh_view_buttons()

    def _build_chat_history_rail(self, root: Any) -> None:
        """Left rail: folders, multi-select, New Chat, Search, History."""
        from app.ui.themes import style_chrome_button, style_entry, UI as _UI

        collapsed = bool(getattr(self, "_chat_rail_collapsed", False))
        # Wider when open: room for checkbox + folder labels
        rail_w = 52 if collapsed else 248
        rail = ctk.CTkFrame(
            root,
            width=rail_w,
            corner_radius=0,
            fg_color=_UI.get("chat_rail_bg", _UI["chat_bg"]),
            border_width=1,
            border_color=_UI.get("chat_rail_border", _UI.get("top_border")),
        )
        # Fill full height so the list is not clipped / non-interactive
        rail.grid(row=3, column=0, sticky="nsew")
        rail.grid_propagate(False)
        rail.grid_rowconfigure(1, weight=1)
        rail.grid_columnconfigure(0, weight=1)
        self._chat_rail_frame = rail
        set_widget_name(rail, name_page_sidebar(PAGE_CHAT, "history_rail"))
        self._chat_rail_drag = {"id": "", "y": 0, "index": -1}
        if not hasattr(self, "_chat_rail_selected") or not isinstance(
            getattr(self, "_chat_rail_selected", None), set
        ):
            self._chat_rail_selected: set[str] = set()
        if not hasattr(self, "_chat_rail_select_vars"):
            self._chat_rail_select_vars: dict[str, Any] = {}
        # Default folder for new chats (optional)
        if not hasattr(self, "_chat_rail_new_folder_id"):
            self._chat_rail_new_folder_id = ""

        # Top chrome
        head = ctk.CTkFrame(rail, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=6, pady=(10, 4))
        _hide_btn = ctk.CTkButton(
            head,
            text="☰" if collapsed else "◀",
            width=36 if collapsed else 36,
            height=32,
            corner_radius=10,
            font=("Segoe UI", 13),
            command=self._chat_toggle_history_rail,
            **style_chrome_button(),
        )
        _hide_btn.pack(side="left")
        set_widget_name(_hide_btn, name_chat_sidebar_button("toggle_rail"))
        self._tooltip(_hide_btn, "Hide or show the chat list (more room for replies).")
        if not collapsed:
            ctk.CTkLabel(
                head,
                text="Chats",
                font=("Segoe UI", 13, "bold"),
                text_color=_UI["label"],
            ).pack(side="left", padx=8)

        if collapsed:
            body = ctk.CTkFrame(rail, fg_color="transparent")
            body.grid(row=1, column=0, sticky="nsew")
            _cnew_btn = ctk.CTkButton(
                body,
                text="＋",
                width=36,
                height=36,
                corner_radius=10,
                command=self._chat_new_session,
                **style_chrome_button(primary=True),
            )
            _cnew_btn.pack(padx=8, pady=6)
            set_widget_name(_cnew_btn, name_chat_sidebar_button("new_chat"))
            self._tooltip(_cnew_btn, chat_control_help("new_chat"))
            _csearch_btn = ctk.CTkButton(
                body,
                text="🔍",
                width=36,
                height=36,
                corner_radius=10,
                command=self._chat_open_search,
                **style_chrome_button(),
            )
            _csearch_btn.pack(padx=8, pady=4)
            set_widget_name(_csearch_btn, name_chat_sidebar_button("search"))
            self._tooltip(_csearch_btn, chat_control_help("search_internal"))
            return

        body = ctk.CTkFrame(rail, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_rowconfigure(4, weight=1)
        body.grid_columnconfigure(0, weight=1)

        # New chat + New folder
        actions = ctk.CTkFrame(body, fg_color="transparent")
        actions.grid(row=0, column=0, sticky="ew", padx=8, pady=(4, 2))
        actions.grid_columnconfigure(0, weight=1)
        actions.grid_columnconfigure(1, weight=0)
        _newchat_btn = ctk.CTkButton(
            actions,
            text="＋ New",
            anchor="w",
            height=34,
            corner_radius=10,
            command=self._chat_new_session,
            **style_chrome_button(primary=True),
        )
        _newchat_btn.grid(row=0, column=0, sticky="ew", padx=(2, 3))
        set_widget_name(_newchat_btn, name_chat_sidebar_button("new_chat"))
        self._tooltip(_newchat_btn, chat_control_help("new_chat"))
        _newfold_btn = ctk.CTkButton(
            actions,
            text="📁＋",
            width=44,
            height=34,
            corner_radius=10,
            command=self._chat_rail_new_folder,
            **style_chrome_button(),
        )
        _newfold_btn.grid(row=0, column=1, sticky="e", padx=(0, 2))
        set_widget_name(_newfold_btn, name_chat_sidebar_button("new_folder"))
        self._tooltip(_newfold_btn, "Create a folder to organize chats.")

        search_fr = ctk.CTkFrame(body, fg_color="transparent")
        search_fr.grid(row=1, column=0, sticky="ew", padx=10, pady=(2, 2))
        self._chat_rail_search_var = ctk.StringVar(value="")
        se = ctk.CTkEntry(
            search_fr,
            textvariable=self._chat_rail_search_var,
            placeholder_text="Search chats…",
            height=30,
            **style_entry(),
        )
        se.pack(fill="x")
        set_widget_name(se, name_chat_sidebar_search())
        self._tooltip(
            se,
            "Find a past chat. Use checkboxes to select many; right-click for pin / move / delete.",
        )
        se.bind("<KeyRelease>", lambda _e: self._refresh_chat_rail_history())
        se.bind("<Return>", lambda _e: self._chat_open_search())

        # Multi-select toolbar
        sel_bar = ctk.CTkFrame(body, fg_color="transparent")
        sel_bar.grid(row=2, column=0, sticky="ew", padx=8, pady=(2, 2))
        self._chat_rail_sel_bar = sel_bar
        self._chat_rail_select_all_var = ctk.BooleanVar(value=False)
        self._chat_rail_select_all_cb = ctk.CTkCheckBox(
            sel_bar,
            text="All",
            variable=self._chat_rail_select_all_var,
            width=52,
            checkbox_width=18,
            checkbox_height=18,
            font=ctk.CTkFont(size=11),
            command=self._chat_rail_toggle_select_all,
        )
        self._chat_rail_select_all_cb.pack(side="left", padx=(2, 2))
        self._tooltip(self._chat_rail_select_all_cb, "Select all visible chats (or clear selection).")
        self._chat_rail_sel_count_lbl = ctk.CTkLabel(
            sel_bar,
            text="",
            text_color=_UI["muted"],
            font=ctk.CTkFont(size=11),
            width=40,
            anchor="w",
        )
        self._chat_rail_sel_count_lbl.pack(side="left", padx=2)
        self._chat_rail_move_btn = ctk.CTkButton(
            sel_bar,
            text="Move",
            width=48,
            height=26,
            corner_radius=8,
            command=self._chat_rail_bulk_move,
            **style_chrome_button(),
        )
        self._chat_rail_move_btn.pack(side="left", padx=1)
        set_widget_name(self._chat_rail_move_btn, name_chat_sidebar_button("move"))
        self._tooltip(self._chat_rail_move_btn, "Move selected chats into a folder (or out of folders).")
        self._chat_rail_del_btn = ctk.CTkButton(
            sel_bar,
            text="Del",
            width=40,
            height=26,
            corner_radius=8,
            command=self._chat_rail_bulk_delete,
            **style_chrome_button(),
        )
        self._chat_rail_del_btn.pack(side="left", padx=1)
        set_widget_name(self._chat_rail_del_btn, name_chat_sidebar_button("delete"))
        self._tooltip(self._chat_rail_del_btn, "Delete selected chats.")
        self._chat_rail_clear_sel_btn = ctk.CTkButton(
            sel_bar,
            text="×",
            width=28,
            height=26,
            corner_radius=8,
            command=self._chat_rail_clear_selection,
            **style_chrome_button(),
        )
        self._chat_rail_clear_sel_btn.pack(side="right", padx=1)
        set_widget_name(self._chat_rail_clear_sel_btn, name_chat_sidebar_button("clear_selection"))
        self._tooltip(self._chat_rail_clear_sel_btn, "Clear selection.")

        ctk.CTkLabel(
            body,
            text="Folders & history",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=_UI["muted"],
            anchor="w",
        ).grid(row=3, column=0, sticky="ew", padx=14, pady=(6, 2))

        self._chat_rail_list = ctk.CTkScrollableFrame(
            body,
            fg_color="transparent",
            corner_radius=0,
        )
        self._chat_rail_list.grid(row=4, column=0, sticky="nsew", padx=4, pady=(0, 4))
        self._smooth_scroll(self._chat_rail_list)
        self._refresh_chat_rail_history()

        foot = ctk.CTkFrame(body, fg_color="transparent")
        foot.grid(row=5, column=0, sticky="ew", padx=8, pady=(0, 10))
        _allchats_btn = ctk.CTkButton(
            foot,
            text="All chats…",
            anchor="w",
            height=30,
            command=lambda: self.show_page("Chats"),
            **style_chrome_button(),
        )
        _allchats_btn.pack(fill="x", pady=2)
        set_widget_name(_allchats_btn, name_chat_sidebar_button("all_chats"))
        self._tooltip(_allchats_btn, "Open the full list of your saved chats.")

    def _hide_chat_rail(self) -> None:
        if not bool(getattr(self, "_chat_rail_collapsed", False)):
            self._chat_toggle_history_rail()

    def _show_chat_rail(self) -> None:
        if bool(getattr(self, "_chat_rail_collapsed", False)):
            self._chat_toggle_history_rail()

    def _apply_chat_rail_layout(self) -> None:
        """Show or hide the chat list without wiping the transcript."""
        rail = getattr(self, "_chat_rail_frame", None)
        if rail is None:
            return
        hide = bool(getattr(self, "_chat_rail_collapsed", False)) or bool(
            getattr(self, "_one_screen", False)
        )
        try:
            if hide:
                rail.grid_remove()
                return
            rail.grid(row=3, column=0, sticky="nsew")
            try:
                rail.configure(width=248)
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            pass
        if getattr(self, "_chat_rail_list", None) is None:
            try:
                self.show_page("Chat", rebuild=True)
            except Exception:  # noqa: BLE001
                pass
            return
        try:
            self._refresh_chat_rail_history()
        except Exception:  # noqa: BLE001
            pass

    def _chat_toggle_history_rail(self) -> None:
        """Collapse/expand in-chat History rail (Grok Toggle Sidebar)."""
        if bool(getattr(self, "_one_screen", False)):
            self._set_one_screen(False)
            return
        self._chat_rail_collapsed = not bool(getattr(self, "_chat_rail_collapsed", False))
        try:
            cfg = storage.load_config()
            cfg["chat_rail_collapsed"] = self._chat_rail_collapsed
            storage.save_config(cfg)
            self.cfg = cfg
        except Exception:  # noqa: BLE001
            pass
        self._apply_chat_rail_layout()
        self._refresh_view_buttons()
        self.set_status(
            "History rail hidden" if self._chat_rail_collapsed else "History rail shown"
        )

    def _refresh_chat_rail_history(self) -> None:
        """Populate History: folders (collapse) + chats with multi-select checkboxes."""
        box = getattr(self, "_chat_rail_list", None)
        if box is None:
            return
        from app.ui.themes import UI as _UI

        for w in box.winfo_children():
            try:
                w.destroy()
            except Exception:  # noqa: BLE001
                pass
        self._chat_rail_select_vars = {}
        q = ""
        try:
            q = (self._chat_rail_search_var.get() or "").strip().lower()
        except Exception:  # noqa: BLE001
            q = ""
        try:
            if not getattr(self, "_chat_titles_repaired", False):
                chat_store.repair_chat_titles()
                chat_store.prune_empty_stub_chats(keep_active=True, keep_extra=0)
                self._chat_titles_repaired = True
        except Exception:  # noqa: BLE001
            pass

        selected = getattr(self, "_chat_rail_selected", None)
        if not isinstance(selected, set):
            selected = set()
            self._chat_rail_selected = selected

        chats = chat_store.list_chats()
        folders = chat_store.list_folders()
        active = chat_store.get_active_chat_id() or ""
        empty_new_kept = 0
        shown = 0
        visible_ids: list[str] = []
        max_rows = 80

        def matches_search(meta: dict[str, Any]) -> bool:
            if not q:
                return True
            cid = str(meta.get("id") or "")
            title = str(meta.get("title") or cid or "Chat").strip() or "Chat"
            fname = ""
            fid = str(meta.get("folder_id") or "")
            if fid:
                fo = chat_store.get_folder(fid)
                fname = str((fo or {}).get("name") or "")
            return q in f"{title} {cid} {fname}".lower()

        def is_listable_stub(meta: dict[str, Any], *, consume: bool = False) -> bool:
            """Whether an empty stub should appear (at most one spare + active)."""
            nonlocal empty_new_kept
            cid = str(meta.get("id") or "")
            title = str(meta.get("title") or cid or "Chat").strip() or "Chat"
            pin = bool(meta.get("pinned"))
            try:
                is_empty_stub = chat_store.is_empty_stub(meta, cid)
            except Exception:  # noqa: BLE001
                is_empty_stub = title.lower() in ("new chat", "main chat", "chat") and not pin
            if not is_empty_stub or pin:
                return True
            if cid == active:
                return True
            if empty_new_kept >= 1:
                return False
            if consume:
                empty_new_kept += 1
            return True

        def keep_chat(meta: dict[str, Any], *, consume_stub: bool = False) -> bool:
            if not matches_search(meta):
                return False
            return is_listable_stub(meta, consume=consume_stub)

        def count_in_folder(folder_id: str) -> int:
            fid = str(folder_id or "").strip()
            n = 0
            for c in chats:
                cf = str(c.get("folder_id") or "").strip()
                if cf != fid:
                    continue
                if matches_search(c):
                    n += 1
            return n

        def add_folder_header(folder: dict[str, Any] | None) -> None:
            """folder=None → Uncategorized root section."""
            if folder is None:
                fid = ""
                name = "Uncategorized"
                collapsed = False
                count = count_in_folder("")
                if not count and folders and not q:
                    return
            else:
                fid = str(folder.get("id") or "")
                name = str(folder.get("name") or "Folder").strip() or "Folder"
                collapsed = bool(folder.get("collapsed")) and not q
                count = count_in_folder(fid)

            row = ctk.CTkFrame(box, fg_color="transparent")
            row.pack(fill="x", pady=(6, 1))
            chev = "▸" if collapsed else "▾"
            icon = "📂" if not collapsed else "📁"
            label = f"{chev} {icon} {name}"
            if count:
                label = f"{label}  ({count})"
            if len(label) > 30:
                label = label[:27] + "…"
            btn = ctk.CTkButton(
                row,
                text=label,
                anchor="w",
                height=30,
                corner_radius=8,
                font=ctk.CTkFont(size=12, weight="bold"),
                fg_color="transparent",
                hover_color=_UI["sidebar_hover"],
                text_color=_UI["label"],
                command=(
                    (lambda i=fid: self._chat_rail_toggle_folder(i))
                    if fid
                    else (lambda: None)
                ),
            )
            btn.pack(side="left", fill="x", expand=True)
            if fid:
                more = ctk.CTkButton(
                    row,
                    text="⋯",
                    width=26,
                    height=26,
                    corner_radius=8,
                    fg_color="transparent",
                    hover_color=_UI["sidebar_hover"],
                    text_color=_UI["muted"],
                    command=lambda i=fid, n=name: self._chat_rail_folder_menu(i, n),
                )
                more.pack(side="right")
                # New chat inside this folder (full session — same as top ＋ New)
                plus = ctk.CTkButton(
                    row,
                    text="＋",
                    width=28,
                    height=28,
                    corner_radius=8,
                    fg_color=_UI.get("accent_soft", "transparent"),
                    hover_color=_UI["sidebar_hover"],
                    text_color=_UI["label"],
                    font=ctk.CTkFont(size=14, weight="bold"),
                    command=lambda i=fid: self._chat_rail_new_in_folder(i),
                )
                plus.pack(side="right", padx=(0, 1))
                self._tooltip(plus, f"New full chat inside “{name}”")
                self._tooltip(btn, "Click to expand/collapse folder")

        def add_chat_row(meta: dict[str, Any], *, indent: bool = False) -> bool:
            nonlocal shown
            if shown >= max_rows:
                return False
            cid = str(meta.get("id") or "")
            if not cid or not keep_chat(meta, consume_stub=True):
                return False
            title = str(meta.get("title") or cid or "Chat").strip() or "Chat"
            pin = bool(meta.get("pinned"))
            pin_mark = "📌 " if pin else ""
            label = f"{pin_mark}{title}"
            is_active = cid == active
            disp = label if len(label) <= (22 if indent else 24) else label[: (19 if indent else 21)] + "…"
            if is_active:
                disp = f"● {disp}"
            active_bg = _UI.get("chat_rail_active", _UI["sidebar_active"])
            active_fg = _UI.get("chat_rail_active_text", _UI["sidebar_active_text"])

            row = ctk.CTkFrame(box, fg_color="transparent")
            row.pack(fill="x", pady=1, padx=(12 if indent else 0, 0))

            var = ctk.BooleanVar(value=cid in selected)
            self._chat_rail_select_vars[cid] = var
            cb = ctk.CTkCheckBox(
                row,
                text="",
                variable=var,
                width=22,
                checkbox_width=16,
                checkbox_height=16,
                command=lambda i=cid, v=var: self._chat_rail_on_check(i, v),
            )
            cb.pack(side="left", padx=(2, 0))

            btn = ctk.CTkButton(
                row,
                text=disp,
                anchor="w",
                height=34,
                corner_radius=10,
                fg_color=active_bg if is_active else "transparent",
                hover_color=_UI["sidebar_hover"],
                text_color=active_fg if is_active else _UI["sidebar_text"],
                font=ctk.CTkFont(size=12, weight="bold" if is_active else "normal"),
                command=lambda: None,
            )
            btn.pack(side="left", fill="x", expand=True)
            more = ctk.CTkButton(
                row,
                text="⋯",
                width=26,
                height=28,
                corner_radius=8,
                fg_color="transparent",
                hover_color=_UI["sidebar_hover"],
                text_color=_UI["muted"],
                command=lambda i=cid, t=title, p=pin: self._chat_rail_context_menu_btn(
                    i, t, p
                ),
            )
            more.pack(side="right", padx=(1, 0))
            for w in (btn, row):
                w.bind(
                    "<Button-3>",
                    lambda e, i=cid, t=title, p=pin: self._chat_rail_context_menu(
                        e, i, t, p
                    ),
                )
            btn.bind(
                "<ButtonPress-1>",
                lambda e, i=cid, ix=shown: self._chat_rail_drag_start(e, i, ix),
            )
            btn.bind("<B1-Motion>", lambda e, i=cid: self._chat_rail_drag_motion(e, i))
            btn.bind(
                "<ButtonRelease-1>",
                lambda e, i=cid: self._chat_rail_click_or_drop(e, i),
            )
            visible_ids.append(cid)
            shown += 1
            return True

        # Folders first
        for folder in folders:
            fid = str(folder.get("id") or "")
            add_folder_header(folder)
            collapsed = bool(folder.get("collapsed")) and not q
            if collapsed:
                continue
            for c in chats:
                if str(c.get("folder_id") or "") != fid:
                    continue
                if not add_chat_row(c, indent=True):
                    break

        # Uncategorized / root
        add_folder_header(None)
        for c in chats:
            if str(c.get("folder_id") or "").strip():
                continue
            if not add_chat_row(c, indent=False):
                break

        self._chat_rail_visible_ids = visible_ids
        # Keep selection for collapsed-folder chats; only drop deleted ids
        all_ids = {str(c.get("id") or "") for c in chats}
        self._chat_rail_selected = {i for i in selected if i in all_ids}
        self._chat_rail_update_sel_ui()

        if not shown and not folders:
            ctk.CTkLabel(
                box,
                text="No chats yet\n＋ New · 📁＋ folder",
                text_color=_UI["muted"],
                font=ctk.CTkFont(size=12),
                justify="left",
            ).pack(anchor="w", padx=8, pady=8)

    def _chat_rail_update_sel_ui(self) -> None:
        """Refresh select-all checkbox + count + bulk button state."""
        selected = getattr(self, "_chat_rail_selected", None) or set()
        visible = list(getattr(self, "_chat_rail_visible_ids", None) or [])
        n = len(selected)
        lbl = getattr(self, "_chat_rail_sel_count_lbl", None)
        if lbl is not None:
            try:
                lbl.configure(text=f"{n}" if n else "")
            except Exception:  # noqa: BLE001
                pass
        var = getattr(self, "_chat_rail_select_all_var", None)
        if var is not None and visible:
            try:
                all_on = bool(visible) and all(i in selected for i in visible)
                var.set(all_on)
            except Exception:  # noqa: BLE001
                pass
        for attr in ("_chat_rail_move_btn", "_chat_rail_del_btn", "_chat_rail_clear_sel_btn"):
            btn = getattr(self, attr, None)
            if btn is None:
                continue
            try:
                btn.configure(state="normal" if n else "disabled")
            except Exception:  # noqa: BLE001
                pass

    def _chat_rail_on_check(self, chat_id: str, var: Any) -> None:
        sel = getattr(self, "_chat_rail_selected", None)
        if not isinstance(sel, set):
            sel = set()
            self._chat_rail_selected = sel
        cid = str(chat_id or "")
        try:
            on = bool(var.get())
        except Exception:  # noqa: BLE001
            on = False
        if on:
            sel.add(cid)
        else:
            sel.discard(cid)
        self._chat_rail_selected = sel
        self._chat_rail_update_sel_ui()

    def _chat_rail_toggle_select_all(self) -> None:
        visible = list(getattr(self, "_chat_rail_visible_ids", None) or [])
        var = getattr(self, "_chat_rail_select_all_var", None)
        want = bool(var.get()) if var is not None else False
        sel = getattr(self, "_chat_rail_selected", None)
        if not isinstance(sel, set):
            sel = set()
        if want:
            for cid in visible:
                sel.add(cid)
        else:
            for cid in visible:
                sel.discard(cid)
        self._chat_rail_selected = sel
        # Sync row checkboxes without full rebuild if possible
        for cid, v in (getattr(self, "_chat_rail_select_vars", None) or {}).items():
            try:
                v.set(cid in sel)
            except Exception:  # noqa: BLE001
                pass
        self._chat_rail_update_sel_ui()

    def _chat_rail_clear_selection(self) -> None:
        self._chat_rail_selected = set()
        for v in (getattr(self, "_chat_rail_select_vars", None) or {}).values():
            try:
                v.set(False)
            except Exception:  # noqa: BLE001
                pass
        var = getattr(self, "_chat_rail_select_all_var", None)
        if var is not None:
            try:
                var.set(False)
            except Exception:  # noqa: BLE001
                pass
        self._chat_rail_update_sel_ui()

    def _chat_rail_new_folder(self) -> None:
        from tkinter import simpledialog

        name = simpledialog.askstring(
            "New folder",
            "Folder name:",
            initialvalue="New folder",
            parent=self,
        )
        if name is None:
            return
        name = (name or "").strip() or "New folder"
        try:
            f = chat_store.create_folder(name)
            self._refresh_chat_rail_history()
            self.set_status(f"Folder “{f.get('name')}” created", toast=True)
        except Exception as e:  # noqa: BLE001
            self.set_status(f"Folder failed: {e}")

    def _chat_rail_toggle_folder(self, folder_id: str) -> None:
        try:
            chat_store.toggle_folder_collapsed(folder_id)
            self._refresh_chat_rail_history()
        except Exception as e:  # noqa: BLE001
            self.set_status(f"Folder toggle failed: {e}")

    def _chat_rail_new_in_folder(self, folder_id: str) -> None:
        """Folder ＋ / menu: create a full chat session inside that folder."""
        fid = str(folder_id or "").strip()

        def go() -> None:
            try:
                self._open_new_chat(folder_id=fid, source="folder")
            except Exception as e:  # noqa: BLE001
                try:
                    self.set_status(f"New chat in folder failed: {e}")
                except Exception:  # noqa: BLE001
                    pass

        # after_idle: finish current click/menu unpost, then open full Chat.
        # (after(10) was flaky under rapid rebuilds and easy to race.)
        try:
            self.after_idle(go)
        except Exception:  # noqa: BLE001
            try:
                self.after(1, go)
            except Exception:  # noqa: BLE001
                go()

    def _chat_rail_folder_menu(self, folder_id: str, name: str) -> None:
        import tkinter as tk

        try:
            x = int(self.winfo_pointerx())
            y = int(self.winfo_pointery())
        except Exception:  # noqa: BLE001
            x, y = 200, 200
        menu = tk.Menu(self, tearoff=0)

        def later(fn: Callable[[], None]) -> None:
            try:
                menu.grab_release()
            except Exception:  # noqa: BLE001
                pass
            try:
                menu.unpost()
            except Exception:  # noqa: BLE001
                pass
            self.after(20, fn)

        menu.add_command(
            label=f"New chat in “{(name or 'Folder')[:20]}”",
            command=lambda: later(lambda: self._chat_rail_new_in_folder(folder_id)),
        )
        menu.add_command(
            label="Rename folder…",
            command=lambda: later(lambda: self._chat_rail_rename_folder(folder_id, name)),
        )
        menu.add_separator()
        menu.add_command(
            label="Delete folder…",
            command=lambda: later(lambda: self._chat_rail_delete_folder(folder_id, name)),
        )
        try:
            menu.tk_popup(x, y)
        finally:
            try:
                menu.grab_release()
            except Exception:  # noqa: BLE001
                pass

    def _chat_rail_rename_folder(self, folder_id: str, cur: str) -> None:
        from tkinter import simpledialog

        name = simpledialog.askstring(
            "Rename folder",
            "Folder name:",
            initialvalue=cur or "Folder",
            parent=self,
        )
        if name is None:
            return
        try:
            chat_store.rename_folder(folder_id, name.strip() or cur or "Folder")
            self._refresh_chat_rail_history()
            self.set_status("Folder renamed", toast=True)
        except Exception as e:  # noqa: BLE001
            self.set_status(f"Rename folder failed: {e}")

    def _chat_rail_delete_folder(self, folder_id: str, name: str) -> None:
        if not messagebox.askyesno(
            "Delete folder",
            f"Delete folder “{name or 'Folder'}”?\n\n"
            "Chats inside move to Uncategorized (they are not deleted).",
            parent=self,
        ):
            return
        try:
            chat_store.delete_folder(folder_id)
            self._refresh_chat_rail_history()
            self.set_status("Folder deleted — chats kept", toast=True)
        except Exception as e:  # noqa: BLE001
            self.set_status(f"Delete folder failed: {e}")

    def _chat_rail_pick_folder(self, title: str = "Move to folder") -> str | None:
        """
        Ask user which folder (or Uncategorized). Returns folder_id, '' for root,
        or None if cancelled.
        """
        folders = chat_store.list_folders()
        labels = ["— Uncategorized (no folder) —"] + [
            str(f.get("name") or "Folder") for f in folders
        ]
        id_by = {"— Uncategorized (no folder) —": ""}
        # Disambiguate duplicate names
        seen: dict[str, int] = {}
        labels = ["— Uncategorized (no folder) —"]
        id_by = {labels[0]: ""}
        for f in folders:
            nm = str(f.get("name") or "Folder")
            n = seen.get(nm, 0) + 1
            seen[nm] = n
            lab = nm if n == 1 else f"{nm} ({n})"
            labels.append(lab)
            id_by[lab] = str(f.get("id") or "")

        win = ctk.CTkToplevel(self)
        win.title(title)
        win.geometry("360x160")
        win.transient(self)
        win.grab_set()
        result: dict[str, Any] = {"v": None}
        ctk.CTkLabel(win, text=title, font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=16, pady=(14, 6)
        )
        var = ctk.StringVar(value=labels[0])
        from app.ui.themes import style_option_menu, style_chrome_button

        ctk.CTkOptionMenu(
            win, variable=var, values=labels, width=300, **style_option_menu()
        ).pack(padx=16, pady=8)

        def ok() -> None:
            result["v"] = id_by.get(var.get(), "")
            win.destroy()

        def cancel() -> None:
            result["v"] = None
            win.destroy()

        bar = ctk.CTkFrame(win, fg_color="transparent")
        bar.pack(fill="x", padx=16, pady=10)
        ctk.CTkButton(
            bar, text="Move", width=90, command=ok, **style_chrome_button(primary=True)
        ).pack(side="right", padx=4)
        ctk.CTkButton(
            bar, text="Cancel", width=80, command=cancel, **style_chrome_button()
        ).pack(side="right", padx=4)
        win.wait_window()
        return result["v"]  # type: ignore[return-value]

    def _chat_rail_bulk_move(self) -> None:
        sel = list(getattr(self, "_chat_rail_selected", None) or [])
        if not sel:
            self.set_status("Select chats first", toast=True)
            return
        dest = self._chat_rail_pick_folder(f"Move {len(sel)} chat(s) to…")
        if dest is None:
            return
        try:
            n = chat_store.move_chats_to_folder(sel, dest or "")
            self._chat_rail_clear_selection()
            self._refresh_chat_rail_history()
            fo = chat_store.get_folder(dest) if dest else None
            where = (fo or {}).get("name") if fo else "Uncategorized"
            self.set_status(f"Moved {n} chat(s) → {where}", toast=True)
        except Exception as e:  # noqa: BLE001
            self.set_status(f"Move failed: {e}")

    def _chat_rail_bulk_delete(self) -> None:
        sel = list(getattr(self, "_chat_rail_selected", None) or [])
        if not sel:
            self.set_status("Select chats first", toast=True)
            return
        # Defer past any menu/grab so Windows does not freeze the UI
        ids = list(sel)
        self.after(10, lambda: self._chat_rail_bulk_delete_do(ids))

    def _chat_rail_bulk_delete_do(self, sel: list[str]) -> None:
        sel = [str(x) for x in (sel or []) if x]
        if not sel:
            return
        if not messagebox.askyesno(
            "Delete chats",
            f"Delete {len(sel)} selected chat(s)?\n\nThis cannot be undone.",
            parent=self,
        ):
            return
        try:
            active = chat_store.get_active_chat_id() or ""
            ui_id = str((self._chat_state or {}).get("id") or "")
            hit_active = active in sel or ui_id in sel
            n = chat_store.delete_chats(sel)
            self._chat_rail_selected = set()
            try:
                tabs = list(getattr(self, "_open_chat_tabs", []) or [])
                self._open_chat_tabs = [t for t in tabs if str(t) not in set(sel)]
            except Exception:  # noqa: BLE001
                pass
            if hit_active:
                self._chat_state = self._load_active_chat()
                self._reload_chat_view_after_delete()
            else:
                self._refresh_chat_rail_history()
            self.set_status(f"Deleted {n} chat(s)", toast=True)
        except Exception as e:  # noqa: BLE001
            self.set_status(f"Delete failed: {e}")

    def _chat_rail_context_menu_btn(self, chat_id: str, title: str, pinned: bool) -> None:
        """⋯ button: open menu near the pointer/widget."""
        try:
            x = int(self.winfo_pointerx())
            y = int(self.winfo_pointery())
        except Exception:  # noqa: BLE001
            x, y = 200, 200

        class _E:
            x_root = x
            y_root = y

        self._chat_rail_context_menu(_E(), chat_id, title, pinned)

    def _chat_rail_context_menu(
        self, event: Any, chat_id: str, title: str, pinned: bool
    ) -> None:
        """Right-click / ⋯ menu: open, pin, rename, delete, move (ChatGPT sidebar pattern)."""
        import tkinter as tk

        menu = tk.Menu(self, tearoff=0)

        def later(fn: Callable[[], None]) -> None:
            """Run after menu unposts — prevents Windows freeze while grab is held."""
            try:
                menu.grab_release()
            except Exception:  # noqa: BLE001
                pass
            try:
                menu.unpost()
            except Exception:  # noqa: BLE001
                pass
            self.after(20, fn)

        menu.add_command(
            label=f"Open “{(title or 'Chat')[:24]}”",
            command=lambda: later(lambda: self._chat_switch_by_id(chat_id)),
        )
        menu.add_separator()
        menu.add_command(
            label="Unpin" if pinned else "Pin to top",
            command=lambda: later(lambda: self._chat_rail_pin(chat_id)),
        )
        menu.add_command(
            label="Rename…",
            command=lambda: later(lambda: self._chat_rail_rename(chat_id, title)),
        )
        menu.add_command(
            label="Duplicate / branch",
            command=lambda: later(lambda: self._chat_rail_branch(chat_id)),
        )
        menu.add_separator()
        menu.add_command(
            label="Move up",
            command=lambda: later(lambda: self._chat_rail_move(chat_id, -1)),
        )
        menu.add_command(
            label="Move down",
            command=lambda: later(lambda: self._chat_rail_move(chat_id, 1)),
        )
        menu.add_command(
            label="Move to folder…",
            command=lambda: later(lambda: self._chat_rail_move_one_to_folder(chat_id)),
        )
        menu.add_separator()
        menu.add_command(
            label="Delete chat…",
            command=lambda: later(lambda: self._chat_rail_delete(chat_id, title)),
        )
        try:
            menu.tk_popup(int(event.x_root), int(event.y_root))
        finally:
            try:
                menu.grab_release()
            except Exception:  # noqa: BLE001
                pass

    def _chat_rail_move_one_to_folder(self, chat_id: str) -> None:
        dest = self._chat_rail_pick_folder("Move chat to folder")
        if dest is None:
            return
        try:
            chat_store.move_chat_to_folder(chat_id, dest or "")
            self._refresh_chat_rail_history()
            fo = chat_store.get_folder(dest) if dest else None
            where = (fo or {}).get("name") if fo else "Uncategorized"
            self.set_status(f"Moved → {where}", toast=True)
        except Exception as e:  # noqa: BLE001
            self.set_status(f"Move failed: {e}")

    def _chat_rail_pin(self, chat_id: str) -> None:
        try:
            chat_store.toggle_pin(chat_id)
            if chat_id == (self._chat_state.get("id") or chat_store.get_active_chat_id()):
                self._chat_state = self._load_active_chat()
            self._refresh_chat_rail_history()
            self.set_status("Chat pin updated", toast=True)
        except Exception as e:  # noqa: BLE001
            self.set_status(f"Pin failed: {e}")

    def _chat_rail_rename(self, chat_id: str, cur_title: str) -> None:
        from tkinter import simpledialog

        name = simpledialog.askstring(
            "Rename chat",
            "Chat name:",
            initialvalue=cur_title or "Chat",
            parent=self,
        )
        if name is None:
            return
        name = name.strip() or cur_title or "Chat"
        try:
            chat_store.rename_chat(chat_id, name)
            if chat_id == (self._chat_state.get("id") or ""):
                self._chat_state = self._load_active_chat()
                if hasattr(self, "chat_title_label"):
                    pin = "📌 " if self._chat_state.get("pinned") else ""
                    self.chat_title_label.configure(text=f"{pin}{name}  ·  rename")
            self._refresh_chat_rail_history()
            self.set_status(f"Renamed → {name}", toast=True)
        except Exception as e:  # noqa: BLE001
            self.set_status(f"Rename failed: {e}")

    def _chat_rail_branch(self, chat_id: str) -> None:
        try:
            c = chat_store.branch_chat(chat_id)
            self._chat_state = self._load_active_chat()
            self.show_page("Chat")
            self.set_status(f"Branched → {c.get('title')}", toast=True)
        except Exception as e:  # noqa: BLE001
            self.set_status(f"Branch failed: {e}")

    def _chat_rail_delete(self, chat_id: str, title: str) -> None:
        chat_id = str(chat_id or "").strip()
        if not chat_id:
            self.set_status("Delete failed: missing chat id")
            return
        if not messagebox.askyesno(
            "Delete chat",
            f"Delete “{title or 'Chat'}”?\n\nThis cannot be undone.",
            parent=self,
        ):
            return
        # Heavy UI work next tick — avoids freeze right after modal / menu
        cid, ttl = chat_id, title or "Chat"
        self.after(1, lambda: self._chat_rail_delete_do(cid, ttl))

    def _chat_rail_delete_do(self, chat_id: str, title: str) -> None:
        chat_id = str(chat_id or "").strip()
        if not chat_id:
            return
        try:
            was_active = chat_id == (chat_store.get_active_chat_id() or "")
            was_ui = chat_id == str((self._chat_state or {}).get("id") or "")
            ok = chat_store.delete_chat(chat_id)
            # Drop closed tab refs so UI does not revive the deleted id
            try:
                tabs = list(getattr(self, "_open_chat_tabs", []) or [])
                self._open_chat_tabs = [t for t in tabs if str(t) != chat_id]
            except Exception:  # noqa: BLE001
                pass
            try:
                sel = getattr(self, "_chat_rail_selected", None)
                if isinstance(sel, set):
                    sel.discard(chat_id)
            except Exception:  # noqa: BLE001
                pass
            if was_active or was_ui:
                self._chat_state = self._load_active_chat()
                self._reload_chat_view_after_delete()
            else:
                self._refresh_chat_rail_history()
            if ok:
                self.set_status("Chat deleted", toast=True)
            else:
                self.set_status("Chat already removed", toast=True)
        except Exception as e:  # noqa: BLE001
            self.set_status(f"Delete failed: {e}")

    def _reload_chat_view_after_delete(self) -> None:
        """
        After deleting the open chat: show the new active chat without a full
        show_page destroy/rebuild (that path freezes CustomTkinter on Windows).
        """
        if getattr(self, "_current_page", "") != "Chat":
            try:
                self.show_page("Chat")
            except Exception:  # noqa: BLE001
                pass
            return
        try:
            # Title
            if hasattr(self, "chat_title_label"):
                st = getattr(self, "_chat_state", None) or {}
                pin = "📌 " if st.get("pinned") else ""
                name = str(st.get("title") or "Chat")
                try:
                    self.chat_title_label.configure(text=f"{pin}{name}  ·  rename")
                except Exception:  # noqa: BLE001
                    pass
            # Transcript + chrome only
            try:
                self._chat_render_transcript()
            except Exception:  # noqa: BLE001
                pass
            try:
                self._refresh_chat_rail_history()
            except Exception:  # noqa: BLE001
                pass
            try:
                self._refresh_chat_tabs_bar()
            except Exception:  # noqa: BLE001
                pass
            try:
                self._refresh_context_chip()
            except Exception:  # noqa: BLE001
                pass
            try:
                self._update_composer_status()
            except Exception:  # noqa: BLE001
                pass
            try:
                self._chat_scroll_to_end(force=True)
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            # Last resort full rebuild
            try:
                self.show_page("Chat")
            except Exception:  # noqa: BLE001
                pass

    def _chat_rail_move(self, chat_id: str, delta: int) -> None:
        ids = list(getattr(self, "_chat_rail_visible_ids", []) or [])
        if chat_id not in ids:
            chats = chat_store.list_chats()
            ids = [str(c.get("id")) for c in chats]
        try:
            i = ids.index(chat_id)
        except ValueError:
            return
        j = max(0, min(len(ids) - 1, i + int(delta)))
        if j == i:
            return
        try:
            chat_store.reorder_chat(chat_id, j)
            self._refresh_chat_rail_history()
        except Exception as e:  # noqa: BLE001
            self.set_status(f"Move failed: {e}")

    def _chat_rail_drag_start(self, event: Any, chat_id: str, index: int) -> None:
        self._chat_rail_drag = {
            "id": chat_id,
            "y": int(getattr(event, "y_root", 0) or 0),
            "index": index,
            "moved": False,
        }

    def _chat_rail_drag_motion(self, event: Any, chat_id: str) -> None:
        d = getattr(self, "_chat_rail_drag", None) or {}
        if d.get("id") != chat_id:
            return
        y0 = int(d.get("y") or 0)
        y1 = int(getattr(event, "y_root", 0) or 0)
        if abs(y1 - y0) > 8:
            d["moved"] = True
            self._chat_rail_drag = d

    def _chat_rail_click_or_drop(self, event: Any, chat_id: str) -> None:
        """Open chat on click; reorder on drag."""
        d = getattr(self, "_chat_rail_drag", None) or {}
        moved = bool(d.get("moved")) and d.get("id") == chat_id
        if not moved:
            self._chat_rail_drag = {"id": "", "y": 0, "index": -1}
            self._chat_switch_by_id(chat_id)
            return
        # Map release Y to index in list
        box = getattr(self, "_chat_rail_list", None)
        ids = list(getattr(self, "_chat_rail_visible_ids", []) or [])
        if not box or not ids or chat_id not in ids:
            self._chat_rail_drag = {"id": "", "y": 0, "index": -1}
            return
        try:
            children = [w for w in box.winfo_children() if isinstance(w, ctk.CTkFrame)]
            y = int(getattr(event, "y_root", 0) or 0)
            target = len(ids) - 1
            for i, row in enumerate(children):
                try:
                    top = row.winfo_rooty()
                    bot = top + max(1, row.winfo_height())
                    if top <= y <= bot:
                        target = i
                        break
                    if y < top:
                        target = max(0, i - 1)
                        break
                except Exception:  # noqa: BLE001
                    continue
            if 0 <= target < len(ids) and ids[target] != chat_id:
                chat_store.reorder_chat(chat_id, target)
                self._refresh_chat_rail_history()
                self.set_status("Chat reordered", toast=False)
        except Exception as e:  # noqa: BLE001
            self.set_status(f"Reorder failed: {e}")
        self._chat_rail_drag = {"id": "", "y": 0, "index": -1}

    def _chat_switch_by_id(self, chat_id: str) -> None:
        """Switch active chat by id (History rail / tabs)."""
        if not chat_id:
            return
        try:
            chat_store.set_active_chat_id(chat_id)
            self._chat_state = self._load_active_chat()
            # Keep multi-tab strip in sync
            tabs = list(getattr(self, "_open_chat_tabs", []) or [])
            if chat_id not in tabs:
                tabs.insert(0, chat_id)
            self._open_chat_tabs = tabs[:6]
            self.show_page("Chat")
        except Exception as e:  # noqa: BLE001
            self.set_status(f"Could not open chat: {e}")

    def _composer_clear_placeholder(self) -> None:
        """Clear Grok-style placeholder when user focuses the box."""
        if not getattr(self, "_composer_is_placeholder", False):
            return
        if not hasattr(self, "chat_input"):
            return
        from app.ui.themes import UI as _UI

        try:
            self.chat_input.delete("1.0", "end")
            self.chat_input.configure(
                text_color=_UI.get("composer_text", _UI["label"])
            )
            self._composer_is_placeholder = False
        except Exception:  # noqa: BLE001
            self._composer_is_placeholder = False

    def _composer_set_text(self, text: str, *, append: bool = False) -> None:
        """Write real text into composer (never leave placeholder flag stuck)."""
        if not hasattr(self, "chat_input"):
            return
        from app.ui.themes import UI as _UI

        try:
            if getattr(self, "_composer_is_placeholder", False) or not append:
                self.chat_input.delete("1.0", "end")
            self._composer_is_placeholder = False
            if text:
                self.chat_input.insert("end" if append else "1.0", text)
            self.chat_input.configure(
                text_color=_UI.get("composer_text", _UI["label"])
            )
        except Exception:  # noqa: BLE001
            self._composer_is_placeholder = False

    def _composer_maybe_placeholder(self) -> None:
        """Restore placeholder when empty on blur (live Grok: What's on your mind?)."""
        if not hasattr(self, "chat_input"):
            return
        if getattr(self, "_composer_is_placeholder", False):
            return
        try:
            t = self.chat_input.get("1.0", "end").strip()
        except Exception:  # noqa: BLE001
            return
        if t:
            return
        from app.ui.themes import UI as _UI
        from app.ui.components.layman_copy import COMPOSER_WHATS_ON_MIND, COMPOSER_ASK_ANYTHING

        ph = getattr(self, "_composer_placeholder", None) or (
            COMPOSER_WHATS_ON_MIND if self._is_simple_ui() else COMPOSER_ASK_ANYTHING
        )
        try:
            self.chat_input.delete("1.0", "end")
            self.chat_input.insert("1.0", ph)
            self.chat_input.configure(text_color=_UI["muted"])
            self._composer_is_placeholder = True
        except Exception:  # noqa: BLE001
            pass

    def _update_composer_status(self) -> None:
        if not hasattr(self, "chat_attach_label"):
            return
        model = ""
        try:
            model = self.chat_model_var.get() if hasattr(self, "chat_model_var") else ""
        except Exception:  # noqa: BLE001
            model = storage.load_config().get("model") or ""
        # Short model tail for space
        if model and len(model) > 36:
            model = "…" + model[-34:]
        mode = self.chat_mode_var.get() if hasattr(self, "chat_mode_var") else "action"
        att = self._attachments_summary_short()
        try:
            from app.core.services.llm.providers import has_active_api_key

            key_ok = has_active_api_key()
        except Exception:  # noqa: BLE001
            key_ok = bool((storage.load_config().get("api_key") or "").strip())
        ready = "Ready" if key_ok else "No API key → Settings"
        # Task #3: pre-send token budget (avoids OpenRouter 402 surprise)
        budget_part = ""
        try:
            from app.core.services.llm.providers import estimate_request_budget

            prompt_chars = 0
            try:
                if hasattr(self, "chat_input") and not getattr(self, "_composer_is_placeholder", False):
                    prompt_chars = len(self.chat_input.get("1.0", "end-1c") or "")
            except Exception:  # noqa: BLE001
                prompt_chars = 0
            bud = estimate_request_budget(prompt_chars=prompt_chars)
            max_out = bud.get("max_completion_tokens") or 0
            ptok = bud.get("prompt_tokens_est") or 0
            budget_part = f"  ·  ~{ptok}+{max_out} tok"
            # Short OpenRouter credit hint when relevant
            note = str(bud.get("note") or "")
            if "OpenRouter" in note and ptok + max_out > 400:
                budget_part += " ⚠credits"
        except Exception:  # noqa: BLE001
            budget_part = ""
        # Task #4: risk tier short tag
        risk_part = ""
        try:
            from app.services.agent_harness.permissions import risk_tier_badge

            risk_part = f"  ·  {risk_tier_badge()}"
            if hasattr(self, "_risk_chip_btn"):
                try:
                    self._risk_chip_btn.configure(text=risk_tier_badge())
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            risk_part = ""
        # Task #7: folder-scoped chat
        folder_part = ""
        try:
            from pathlib import Path as _P

            kf = ""
            if getattr(self, "_chat_state", None):
                kf = str(
                    self._chat_state.get("knowledge_folder")
                    or self._chat_state.get("chat_folder")
                    or ""
                )
            if kf:
                folder_part = f"  ·  📁 {_P(kf).name}"
        except Exception:  # noqa: BLE001
            folder_part = ""
        # One short line under the slim pill — full detail stays in window status bar
        att_part = f"  ·  {att}" if att and att != "no attaches" else ""
        try:
            from app.core.services.chat.task_watch import llm_chip_label, task_chip_label

            cycle = "Cycle · on" if getattr(self, "_task_cycle_running", False) else "Cycle · off"
            watch = (
                f"{cycle}  ·  {task_chip_label(getattr(self, '_task_status', 'none'))}  ·  "
                f"{llm_chip_label(getattr(self, '_llm_phase', 'idle'))}  ·  "
            )
        except Exception:  # noqa: BLE001
            watch = ""
        line = f"{watch}{ready}  ·  {model}  ·  {mode}{budget_part}{risk_part}{folder_part}{att_part}"
        try:
            self.chat_attach_label.configure(text=line)
        except Exception:  # noqa: BLE001
            pass

    def _attachments_summary_short(self) -> str:
        n = len(self._chat_attachments or [])
        ni = len(getattr(self, "_pending_images", []) or [])
        nv = len(getattr(self, "_pending_videos", []) or [])
        nn = len(getattr(self, "_chat_attached_notes", None) or [])
        if not n and not ni and not nv and not nn:
            return "no attaches"
        parts = []
        if n:
            parts.append(f"{n} file(s)")
        if ni:
            parts.append(f"{ni} img")
        if nv:
            parts.append(f"{nv} vid")
        if nn:
            parts.append(f"{nn} note(s)")
        return ", ".join(parts)

    def _ensure_live_monitor_open(self, tab: str = "Terminal") -> None:
        """Force Live open so thinking/terminal don't dump into the main answer."""
        self._live_panel_visible = True
        self._live_panel_user_on = True
        try:
            cfg = storage.load_config()
            cfg["chat_auto_live_panel"] = True
            storage.save_config(cfg)
            self.cfg = cfg
        except Exception:  # noqa: BLE001
            pass
        try:
            self._chat_apply_mid_columns()
        except Exception:  # noqa: BLE001
            pass
        try:
            if hasattr(self, "side_panel_mode") and tab:
                self.side_panel_mode.set(tab)
        except Exception:  # noqa: BLE001
            pass
        try:
            self._refresh_side_panel()
        except Exception:  # noqa: BLE001
            pass
        from app.ui.themes import style_chrome_button

        if hasattr(self, "_live_btn"):
            try:
                self._live_btn.configure(
                    text="Live ●",
                    **style_chrome_button(active=True),
                )
            except Exception:  # noqa: BLE001
                pass

    def _chat_toggle_live_panel(self) -> None:
        self._live_panel_visible = not bool(getattr(self, "_live_panel_visible", False))
        self._live_panel_user_on = bool(self._live_panel_visible)
        self._chat_apply_mid_columns()
        if self._live_panel_visible:
            self._refresh_side_panel()
        from app.ui.themes import style_chrome_button

        if hasattr(self, "_live_btn"):
            try:
                self._live_btn.configure(
                    text="Live ●" if self._live_panel_visible else "Live",
                    **style_chrome_button(active=bool(self._live_panel_visible)),
                )
            except Exception:  # noqa: BLE001
                pass

    def _chat_toggle_setup_panel(self) -> None:
        """Expand / collapse the right Setup drawer (prompt + params + tools)."""
        self._chat_setup_expanded = not bool(getattr(self, "_chat_setup_expanded", False))
        try:
            cfg = storage.load_config()
            cfg["chat_setup_panel_open"] = bool(self._chat_setup_expanded)
            storage.save_config(cfg)
            self.cfg = cfg
        except Exception:  # noqa: BLE001
            pass
        if self._chat_setup_expanded:
            try:
                self._populate_chat_setup_panel()
            except Exception:  # noqa: BLE001
                pass
        self._chat_apply_mid_columns()
        from app.ui.themes import style_chrome_button

        if hasattr(self, "_setup_btn"):
            try:
                on = bool(self._chat_setup_expanded)
                self._setup_btn.configure(
                    text="Setup ●" if on else "Setup",
                    **style_chrome_button(active=on),
                )
            except Exception:  # noqa: BLE001
                pass
        self.set_status(
            "Setup panel open — system prompt & parameters"
            if self._chat_setup_expanded
            else "Setup panel collapsed",
            toast=True,
        )

    def _chat_apply_mid_columns(self) -> None:
        """Lay out message column + optional Live + Setup (expanded or thin strip)."""
        if getattr(self, "_applying_mid_cols", False):
            return
        mid = getattr(self, "_chat_mid", None)
        if mid is None:
            return
        self._applying_mid_cols = True
        try:
            self._chat_apply_mid_columns_body()
        finally:
            self._applying_mid_cols = False

    def _chat_apply_mid_columns_body(self) -> None:
        mid = getattr(self, "_chat_mid", None)
        if mid is None:
            return
        live = getattr(self, "_chat_live_frame", None)
        setup = getattr(self, "_chat_setup_frame", None)
        strip = getattr(self, "_chat_setup_strip", None)
        try:
            mid.grid_columnconfigure(0, weight=1, minsize=360)
            mid.grid_columnconfigure(1, weight=0)
            mid.grid_columnconfigure(2, weight=0)
        except Exception:  # noqa: BLE001
            pass

        # Live (col 1) — wide enough to read Thinking / Terminal (was a 260px sliver)
        if live is not None:
            if bool(getattr(self, "_live_panel_visible", False)):
                live_w = 340
                try:
                    mw = int(mid.winfo_width() or 0)
                    if mw >= 200:
                        live_w = max(300, min(440, int(mw * 0.40)))
                        if mw - live_w < 300:
                            live_w = max(280, mw - 300)
                except Exception:  # noqa: BLE001
                    live_w = 340
                try:
                    live.configure(width=live_w)
                    live.grid_propagate(False)
                except Exception:  # noqa: BLE001
                    pass
                try:
                    mid.grid_columnconfigure(1, weight=0, minsize=live_w)
                    live.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
                except Exception:  # noqa: BLE001
                    pass
            else:
                try:
                    live.grid_remove()
                except Exception:  # noqa: BLE001
                    pass

        # Setup drawer (col 2) — full panel or collapse strip
        expanded = bool(getattr(self, "_chat_setup_expanded", False))
        w = int(getattr(self, "_chat_setup_width", 340) or 340)
        w = max(280, min(480, w))
        if expanded:
            if strip is not None:
                try:
                    strip.grid_remove()
                except Exception:  # noqa: BLE001
                    pass
            if setup is not None:
                try:
                    setup.configure(width=w)
                    setup.grid_propagate(False)
                    setup.grid(row=0, column=2, sticky="nsew", padx=(6, 0))
                except Exception:  # noqa: BLE001
                    pass
        else:
            if setup is not None:
                try:
                    setup.grid_remove()
                except Exception:  # noqa: BLE001
                    pass
            if strip is not None:
                try:
                    strip.grid(row=0, column=2, sticky="ns", padx=(4, 0))
                except Exception:  # noqa: BLE001
                    pass

    def _build_chat_setup_panel(self, mid: Any) -> None:
        """Create right Setup drawer + thin collapsed strip (content filled when opened)."""
        from app.ui.themes import UI as _UI, style_chrome_button

        # Collapsed strip (always available to expand)
        strip = ctk.CTkFrame(
            mid,
            width=36,
            corner_radius=12,
            fg_color=_UI["top_bg"],
            border_width=1,
            border_color=_UI["top_border"],
        )
        strip.grid_propagate(False)
        self._chat_setup_strip = strip
        ctk.CTkButton(
            strip,
            text="⚙\n▸",
            width=28,
            height=72,
            corner_radius=10,
            font=ctk.CTkFont(size=14),
            command=self._chat_toggle_setup_panel,
            **style_chrome_button(active=False),
        ).pack(padx=3, pady=8)
        self._tooltip(strip.winfo_children()[0] if strip.winfo_children() else strip, "Open Setup panel")

        # Expanded panel shell
        panel = ctk.CTkFrame(
            mid,
            width=int(getattr(self, "_chat_setup_width", 340) or 340),
            corner_radius=14,
            fg_color=_UI["top_bg"],
            border_width=1,
            border_color=_UI["top_border"],
        )
        panel.grid_propagate(False)
        panel.grid_rowconfigure(1, weight=1)
        panel.grid_columnconfigure(0, weight=1)
        self._chat_setup_frame = panel

        hdr = ctk.CTkFrame(panel, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        hdr.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            hdr,
            text="⚙ Setup",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=_UI["label"],
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            hdr,
            text="◂ Hide",
            width=64,
            height=26,
            command=self._chat_toggle_setup_panel,
            **style_chrome_button(),
        ).grid(row=0, column=1, sticky="e", padx=(4, 0))
        self._tooltip(
            hdr.winfo_children()[-1],
            "Collapse Setup panel (keeps a thin ⚙ strip on the right)",
        )

        body = ctk.CTkScrollableFrame(panel, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 8))
        body.grid_columnconfigure(0, weight=1)
        self._chat_setup_body = body
        self._smooth_scroll(body)

        # Footer status
        self._chat_setup_status = ctk.CTkLabel(
            panel,
            text="Prompt · params · tools",
            text_color=_UI["muted"],
            font=ctk.CTkFont(size=11),
            anchor="w",
        )
        self._chat_setup_status.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 8))

        if bool(getattr(self, "_chat_setup_expanded", False)):
            try:
                self._populate_chat_setup_panel()
            except Exception:  # noqa: BLE001
                pass

    def _chat_setup_section_open(self, key: str) -> bool:
        secs = getattr(self, "_chat_setup_sections", None) or {}
        return bool(secs.get(key, True))

    def _chat_toggle_setup_section(self, key: str) -> None:
        secs = dict(getattr(self, "_chat_setup_sections", None) or {})
        secs[key] = not bool(secs.get(key, True))
        self._chat_setup_sections = secs
        try:
            self._populate_chat_setup_panel()
        except Exception:  # noqa: BLE001
            pass

    def _populate_chat_setup_panel(self) -> None:
        """Fill Setup drawer with collapsible sections (connection, prompt, params, tools)."""
        from app.ui.themes import UI as _UI, style_chrome_button, style_entry, style_option_menu
        from app.core.services.llm.model_params import get_model_params
        from app.services import prompt_library as plib
        from app.services import project_store
        from app.services import providers as prov

        body = getattr(self, "_chat_setup_body", None)
        if body is None:
            return
        for w in list(body.winfo_children()):
            try:
                w.destroy()
            except Exception:  # noqa: BLE001
                pass

        wrap = 300

        def section_header(parent: Any, key: str, title: str) -> Any | None:
            open_ = self._chat_setup_section_open(key)
            chev = "▾" if open_ else "▸"
            bar = ctk.CTkFrame(parent, fg_color="transparent")
            bar.pack(fill="x", pady=(10, 2))
            btn = ctk.CTkButton(
                bar,
                text=f"{chev}  {title}",
                anchor="w",
                height=30,
                corner_radius=8,
                font=ctk.CTkFont(size=13, weight="bold"),
                command=lambda k=key: self._chat_toggle_setup_section(k),
                **style_chrome_button(active=open_),
            )
            btn.pack(fill="x")
            if not open_:
                return None
            box = ctk.CTkFrame(
                parent,
                fg_color=_UI.get("card_bg", ("#f8fafc", "#141414")),
                corner_radius=10,
                border_width=1,
                border_color=_UI.get("top_border"),
            )
            box.pack(fill="x", pady=(0, 4))
            return box

        # ── Connection ──
        conn = section_header(body, "connection", "Connection")
        if conn is not None:
            try:
                active = prov.resolve_active_llm()
            except Exception:  # noqa: BLE001
                active = {}
            base = str(active.get("base_url") or "")
            host = base.replace("https://", "").replace("http://", "").split("/")[0] or "—"
            pid = str(active.get("provider_name") or active.get("provider_id") or "—")
            model = str(active.get("model") or "—")
            key_ok = bool((active.get("api_key") or "").strip())
            ctk.CTkLabel(
                conn,
                text=f"{pid}\n{host}\n{model}\nKey: {'✓ set' if key_ok else '✗ missing'}",
                justify="left",
                anchor="w",
                wraplength=wrap,
                text_color=_UI["label"],
                font=ctk.CTkFont(size=12),
            ).pack(fill="x", padx=10, pady=(8, 4))
            row = ctk.CTkFrame(conn, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=(0, 8))
            ctk.CTkButton(
                row,
                text="↻ Models",
                width=88,
                height=28,
                command=self._chat_fetch_models,
                **style_chrome_button(),
            ).pack(side="left", padx=2)
            ctk.CTkButton(
                row,
                text="Providers",
                width=88,
                height=28,
                command=lambda: self.show_page("Settings"),
                **style_chrome_button(),
            ).pack(side="left", padx=2)
            ctk.CTkButton(
                row,
                text="Find…",
                width=64,
                height=28,
                command=self._chat_open_model_picker,
                **style_chrome_button(),
            ).pack(side="left", padx=2)

        # ── System prompt ──
        prompt_box = section_header(body, "prompt", "System prompt")
        if prompt_box is not None:
            cfg = storage.load_config()
            proj = None
            try:
                pid_p = project_store.get_active_project_id()
                proj = project_store.load_project(pid_p) if pid_p else None
            except Exception:  # noqa: BLE001
                proj = None
            current = plib.resolve_effective_system_prompt(
                config_prompt=str(cfg.get("system_prompt") or ""),
                project=proj,
                chat=getattr(self, "_chat_state", None),
            )
            presets = plib.list_presets()
            labels = [f"{p.get('name')}" for p in presets] or ["Default"]
            id_by_label = {
                f"{p.get('name')}": str(p.get("id")) for p in presets
            }
            # Disambiguate duplicate names
            if len(id_by_label) < len(presets):
                labels = [f"{p.get('name')} ({p.get('id')})" for p in presets]
                id_by_label = {
                    f"{p.get('name')} ({p.get('id')})": str(p.get("id")) for p in presets
                }
            active_id = plib.get_active_preset_id()
            active_label = next(
                (lb for lb, i in id_by_label.items() if i == active_id),
                labels[0],
            )
            preset_var = ctk.StringVar(value=active_label)
            self._setup_preset_var = preset_var
            self._setup_preset_ids = id_by_label

            prow = ctk.CTkFrame(prompt_box, fg_color="transparent")
            prow.pack(fill="x", padx=8, pady=(8, 4))
            ctk.CTkLabel(prow, text="Library", text_color=_UI["muted"], width=56).pack(
                side="left"
            )
            ctk.CTkOptionMenu(
                prow,
                variable=preset_var,
                values=labels,
                width=200,
                height=28,
                **style_option_menu(),
            ).pack(side="left", padx=4)

            def load_preset() -> None:
                pid2 = id_by_label.get(preset_var.get()) or "default"
                try:
                    body_txt = plib.resolve_prompt_body(pid2)
                    tb = getattr(self, "_setup_prompt_box", None)
                    if tb is not None:
                        tb.delete("1.0", "end")
                        tb.insert("1.0", body_txt)
                    plib.set_active_preset_id(pid2)
                    self._setup_set_status(f"Loaded preset: {pid2}")
                except Exception as e:  # noqa: BLE001
                    self._setup_set_status(f"Preset error: {e}")

            ctk.CTkButton(
                prow,
                text="Load",
                width=56,
                height=28,
                command=load_preset,
                **style_chrome_button(),
            ).pack(side="left", padx=2)

            tb = ctk.CTkTextbox(
                prompt_box,
                height=140,
                wrap="word",
                font=ctk.CTkFont(size=12),
                border_width=1,
                border_color=_UI.get("top_border"),
            )
            tb.pack(fill="x", padx=8, pady=4)
            tb.insert("1.0", current)
            self._setup_prompt_box = tb

            brow = ctk.CTkFrame(prompt_box, fg_color="transparent")
            brow.pack(fill="x", padx=8, pady=(2, 8))

            def save_prompt() -> None:
                try:
                    text = tb.get("1.0", "end").strip()
                    cfg2 = storage.load_config()
                    cfg2["system_prompt"] = text
                    pid2 = id_by_label.get(preset_var.get()) or cfg2.get(
                        "active_prompt_preset_id"
                    ) or "default"
                    cfg2["active_prompt_preset_id"] = pid2
                    storage.save_config(cfg2)
                    self.cfg = cfg2
                    plib.set_active_preset_id(str(pid2))
                    self._setup_set_status("System prompt saved")
                    self.set_status("System prompt updated", toast=True)
                except Exception as e:  # noqa: BLE001
                    self._setup_set_status(f"Save failed: {e}")

            def reset_prompt() -> None:
                try:
                    default = get_default_system_prompt()
                    tb.delete("1.0", "end")
                    tb.insert("1.0", default)
                    cfg2 = storage.load_config()
                    cfg2["system_prompt"] = ""
                    cfg2["active_prompt_preset_id"] = "default"
                    storage.save_config(cfg2)
                    self.cfg = cfg2
                    plib.set_active_preset_id("default")
                    self._setup_set_status("Reset to default prompt")
                except Exception as e:  # noqa: BLE001
                    self._setup_set_status(str(e))

            ctk.CTkButton(
                brow,
                text="Save prompt",
                width=100,
                height=28,
                command=save_prompt,
                **style_chrome_button(primary=True),
            ).pack(side="left", padx=2)
            ctk.CTkButton(
                brow,
                text="Reset",
                width=64,
                height=28,
                command=reset_prompt,
                **style_chrome_button(),
            ).pack(side="left", padx=2)
            ctk.CTkButton(
                brow,
                text="Full editor…",
                width=96,
                height=28,
                command=self._chat_edit_system_prompt,
                **style_chrome_button(),
            ).pack(side="left", padx=2)

        # ── Parameters ──
        params_box = section_header(body, "params", "Model parameters")
        if params_box is not None:
            p = get_model_params()
            fields = [
                ("temperature", "Temperature", str(p.get("temperature", 0.4))),
                ("top_p", "Top P", str(p.get("top_p", 1.0))),
                ("max_tokens", "Max tokens (0=auto)", str(p.get("max_tokens", 0))),
                ("context_window", "Context window", str(p.get("context_window", 128000))),
                ("context_reserve_reply", "Reserve reply", str(p.get("context_reserve_reply", 8000))),
                ("presence_penalty", "Presence pen.", str(p.get("presence_penalty", 0))),
                ("frequency_penalty", "Frequency pen.", str(p.get("frequency_penalty", 0))),
            ]
            entries: dict[str, Any] = {}
            grid = ctk.CTkFrame(params_box, fg_color="transparent")
            grid.pack(fill="x", padx=8, pady=8)
            grid.grid_columnconfigure(1, weight=1)
            for i, (key, label, val) in enumerate(fields):
                ctk.CTkLabel(
                    grid,
                    text=label,
                    anchor="w",
                    text_color=_UI["label"],
                    font=ctk.CTkFont(size=12),
                ).grid(row=i, column=0, sticky="w", padx=(2, 6), pady=3)
                e = ctk.CTkEntry(grid, width=110, height=28, **style_entry())
                e.insert(0, val)
                e.grid(row=i, column=1, sticky="e", pady=3)
                entries[key] = e
            self._setup_param_entries = entries

            prow2 = ctk.CTkFrame(params_box, fg_color="transparent")
            prow2.pack(fill="x", padx=8, pady=(0, 8))

            def save_params() -> None:
                from app.core.services.llm.model_params import save_model_params

                raw: dict[str, Any] = {}
                try:
                    for k, e in entries.items():
                        v = e.get().strip()
                        if k in ("max_tokens", "context_window", "context_reserve_reply"):
                            raw[k] = int(float(v))
                        else:
                            raw[k] = float(v)
                except ValueError:
                    self._setup_set_status("Invalid number in parameters")
                    return
                save_model_params(raw)
                try:
                    self._refresh_context_chip()
                except Exception:  # noqa: BLE001
                    pass
                self._setup_set_status(
                    f"Params saved · temp={raw.get('temperature')} · ctx={raw.get('context_window')}"
                )
                self.set_status("Model parameters saved", toast=True)

            ctk.CTkButton(
                prow2,
                text="Save params",
                width=100,
                height=28,
                command=save_params,
                **style_chrome_button(primary=True),
            ).pack(side="left", padx=2)
            ctk.CTkButton(
                prow2,
                text="Context…",
                width=80,
                height=28,
                command=self._chat_context_window_dialog,
                **style_chrome_button(),
            ).pack(side="left", padx=2)
            ctk.CTkButton(
                prow2,
                text="Full…",
                width=64,
                height=28,
                command=self._chat_model_params_dialog,
                **style_chrome_button(),
            ).pack(side="left", padx=2)

            # Stream replies toggle
            stream_var = ctk.BooleanVar(
                value=bool((storage.load_config() or {}).get("stream_replies", True))
            )
            self._setup_stream_var = stream_var

            def on_stream() -> None:
                try:
                    cfg2 = storage.load_config()
                    cfg2["stream_replies"] = bool(stream_var.get())
                    storage.save_config(cfg2)
                    self.cfg = cfg2
                    self._setup_set_status(
                        "Streaming ON" if stream_var.get() else "Streaming OFF"
                    )
                except Exception:  # noqa: BLE001
                    pass

            ctk.CTkCheckBox(
                params_box,
                text="Stream replies live",
                variable=stream_var,
                command=on_stream,
                font=ctk.CTkFont(size=12),
            ).pack(anchor="w", padx=12, pady=(0, 8))

        # ── Tools & mode ──
        tools_box = section_header(body, "tools", "Tools & mode")
        if tools_box is not None:
            tgrid = ctk.CTkFrame(tools_box, fg_color="transparent")
            tgrid.pack(fill="x", padx=10, pady=8)

            def switch_row(text: str, var: Any) -> None:
                if var is None:
                    return
                ctk.CTkCheckBox(
                    tgrid,
                    text=text,
                    variable=var,
                    command=self._on_chat_flags_save,
                    font=ctk.CTkFont(size=12),
                ).pack(anchor="w", pady=2)

            switch_row("Terminal", getattr(self, "chat_terminal_var", None))
            switch_row("Skills", getattr(self, "chat_skills_var", None))
            switch_row("MCP tools", getattr(self, "chat_mcp_var", None))
            switch_row("Laptop / GUI", getattr(self, "chat_laptop_var", None))
            switch_row("Safety limits", getattr(self, "chat_safety_var", None))
            switch_row("Org pipeline", getattr(self, "chat_workflow_var", None))
            if getattr(self, "chat_show_tools_var", None) is not None:
                ctk.CTkCheckBox(
                    tgrid,
                    text="Show tool msgs",
                    variable=self.chat_show_tools_var,
                    command=self._on_show_tools_toggle,
                    font=ctk.CTkFont(size=12),
                ).pack(anchor="w", pady=2)

            mode_row = ctk.CTkFrame(tools_box, fg_color="transparent")
            mode_row.pack(fill="x", padx=10, pady=(0, 8))
            ctk.CTkLabel(mode_row, text="Mode", text_color=_UI["muted"]).pack(
                side="left", padx=(0, 8)
            )
            if hasattr(self, "chat_mode_var"):
                ctk.CTkSegmentedButton(
                    mode_row,
                    values=["plan", "action"],
                    variable=self.chat_mode_var,
                    command=lambda _v: self._on_chat_flags_save(),
                    width=160,
                    height=28,
                ).pack(side="left")

            ctk.CTkButton(
                tools_box,
                text="Capabilities…",
                width=120,
                height=28,
                command=self._chat_open_caps_popover,
                **style_chrome_button(),
            ).pack(anchor="w", padx=10, pady=(0, 10))

        # Width control
        wrow = ctk.CTkFrame(body, fg_color="transparent")
        wrow.pack(fill="x", pady=(12, 4))
        ctk.CTkLabel(wrow, text="Panel width", text_color=_UI["muted"], font=ctk.CTkFont(size=11)).pack(
            side="left"
        )

        def set_width(delta: int) -> None:
            cur = int(getattr(self, "_chat_setup_width", 340) or 340)
            nxt = max(280, min(480, cur + delta))
            self._chat_setup_width = nxt
            try:
                cfg = storage.load_config()
                cfg["chat_setup_panel_width"] = nxt
                storage.save_config(cfg)
            except Exception:  # noqa: BLE001
                pass
            self._chat_apply_mid_columns()
            self._setup_set_status(f"Width {nxt}px")

        ctk.CTkButton(
            wrow, text="−", width=32, height=26, command=lambda: set_width(-40), **style_chrome_button()
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            wrow, text="+", width=32, height=26, command=lambda: set_width(40), **style_chrome_button()
        ).pack(side="left")

    def _setup_set_status(self, text: str) -> None:
        lbl = getattr(self, "_chat_setup_status", None)
        if lbl is None:
            return
        try:
            lbl.configure(text=(text or "")[:80])
        except Exception:  # noqa: BLE001
            pass

    def _chat_open_search(self) -> None:
        win = ctk.CTkToplevel(self)
        win.title("Search chats")
        win.geometry("420x120")
        win.transient(self)
        win.grab_set()
        e = ctk.CTkEntry(win, placeholder_text="Search in this chat…", width=360)
        e.pack(padx=16, pady=(16, 8))
        e.focus_set()

        def go() -> None:
            self.chat_search_var.set(e.get())
            self._chat_search()
            win.destroy()

        def go_all() -> None:
            self.chat_search_var.set(e.get())
            self._chat_search_all()
            win.destroy()

        bar = ctk.CTkFrame(win, fg_color="transparent")
        bar.pack(pady=8)
        ctk.CTkButton(bar, text="This chat", width=100, command=go).pack(side="left", padx=6)
        ctk.CTkButton(bar, text="All chats", width=100, command=go_all).pack(side="left", padx=6)
        e.bind("<Return>", lambda _e: go())

    def _chat_open_overflow_menu(self) -> None:
        """Grok-style ⋯ menu: all secondary tools in one scrollable panel."""
        win = ctk.CTkToplevel(self)
        win.title("Chat menu")
        win.geometry("520x640")
        win.transient(self)
        win.grab_set()
        scroll = ctk.CTkScrollableFrame(win)
        scroll.pack(fill="both", expand=True, padx=12, pady=12)

        def section(title: str) -> ctk.CTkFrame:
            ctk.CTkLabel(scroll, text=title, font=ctk.CTkFont(weight="bold", size=13)).pack(
                anchor="w", pady=(12, 4)
            )
            f = ctk.CTkFrame(scroll, fg_color=("gray90", "gray20"))
            f.pack(fill="x", pady=2)
            return f

        def row_btns(parent: ctk.CTkFrame, items: list[tuple[str, Callable[[], None]]]) -> None:
            bar = ctk.CTkFrame(parent, fg_color="transparent")
            bar.pack(fill="x", padx=8, pady=6)
            for label, cmd in items:
                ctk.CTkButton(
                    bar,
                    text=label,
                    width=110,
                    height=30,
                    command=lambda c=cmd: (c(), win.destroy() if label not in ("↻ models",) else None),
                ).pack(side="left", padx=3, pady=2)

        # Model / provider (Easy mode hides provider on top bar — available here)
        f_llm = section("Model & provider")
        row_btns(
            f_llm,
            [
                ("✦ Use Grok", self._use_grok_as_agent),
                ("↻ models", self._chat_fetch_models),
                ("Find model…", self._chat_open_model_picker),
                ("Params", self._chat_model_params_dialog),
                ("Context…", self._chat_context_window_dialog),
            ],
        )
        try:
            from app.ui.themes import style_option_menu

            ctk.CTkLabel(f_llm, text="Provider", anchor="w").pack(anchor="w", padx=12, pady=(6, 0))
            ctk.CTkOptionMenu(
                f_llm,
                values=list(getattr(self, "_chat_provider_choices", None) or ["OpenRouter"]),
                variable=self.chat_provider_var,
                command=lambda v: (self._on_chat_provider_change(v),),
                width=280,
                height=30,
                **style_option_menu(),
            ).pack(anchor="w", padx=12, pady=4)
            ctk.CTkLabel(f_llm, text="Model", anchor="w").pack(anchor="w", padx=12, pady=(4, 0))
            ctk.CTkOptionMenu(
                f_llm,
                values=list(getattr(self, "_chat_model_choices", None) or ["(fetch models)"]),
                variable=self.chat_model_var,
                command=lambda v: (self._on_chat_model_change(v),),
                width=280,
                height=30,
                **style_option_menu(),
            ).pack(anchor="w", padx=12, pady=(0, 8))
        except Exception:  # noqa: BLE001
            pass

        # Chat
        f_view = section("View / one-screen")
        row_btns(
            f_view,
            [
                ("One screen", lambda: self._set_one_screen(True)),
                ("Exit one-screen", lambda: self._set_one_screen(False)),
                ("Hide menu", self._collapse_app_menu),
                ("Show menu", self._expand_app_menu),
                ("Hide chats", self._hide_chat_rail),
                ("Show chats", self._show_chat_rail),
                ("CPU bar", self._toggle_sysmon_bar),
            ],
        )

        f = section("Chat")
        row_btns(
            f,
            [
                ("Rename", self._chat_rename),
                ("Pin", self._chat_toggle_pin),
                ("Branch", self._chat_branch),
                ("Export", self._chat_export),
                ("Clear chat", self._chat_clear),
                ("→ Project", self._chat_save_to_project),
                ("System prompt", self._chat_edit_system_prompt),
            ],
        )
        ctk.CTkCheckBox(
            f,
            text="Show tool messages in chat",
            variable=self.chat_show_tools_var,
            command=self._on_show_tools_toggle,
        ).pack(anchor="w", padx=12, pady=6)

        # Model / mode
        f = section("Model & mode")
        row = ctk.CTkFrame(f, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=6)
        ctk.CTkLabel(row, text="Provider").pack(side="left", padx=4)
        ctk.CTkOptionMenu(
            row,
            values=self._chat_provider_choices,
            variable=self.chat_provider_var,
            command=self._on_chat_provider_change,
            width=120,
        ).pack(side="left", padx=4)
        ctk.CTkLabel(row, text="Model").pack(side="left", padx=4)
        ctk.CTkOptionMenu(
            row,
            values=self._chat_model_choices,
            variable=self.chat_model_var,
            command=self._on_chat_model_change,
            width=160,
        ).pack(side="left", padx=4)
        ctk.CTkButton(row, text="↻ models", width=80, command=self._chat_fetch_models).pack(
            side="left", padx=4
        )
        row2 = ctk.CTkFrame(f, fg_color="transparent")
        row2.pack(fill="x", padx=8, pady=6)
        ctk.CTkLabel(row2, text="Mode").pack(side="left", padx=4)
        ctk.CTkSegmentedButton(
            row2,
            values=["plan", "action"],
            variable=self.chat_mode_var,
            command=lambda _v: self._on_chat_flags_save(),
            width=160,
        ).pack(side="left", padx=4)
        ctk.CTkLabel(row2, text="Agent").pack(side="left", padx=8)
        ctk.CTkOptionMenu(
            row2,
            values=[x.split("|")[0] for x in self._chat_agent_choices],
            command=self._on_chat_agent_change,
            width=140,
        ).pack(side="left", padx=4)

        # Approvals (same controls as chat bar + CEO / Approvals pages)
        f = section("Approvals")
        from app.services import company_store as _co_ov

        if not hasattr(self, "chat_company_approval_var"):
            self.chat_company_approval_var = ctk.StringVar(
                value="auto" if _co_ov.get_approval_mode() == "auto" else "manual"
            )
        else:
            self.chat_company_approval_var.set(
                "auto" if _co_ov.get_approval_mode() == "auto" else "manual"
            )
        if not hasattr(self, "chat_tool_approval_var"):
            self.chat_tool_approval_var = ctk.BooleanVar(
                value=bool(storage.load_config().get("tool_approval_required"))
            )
        else:
            self.chat_tool_approval_var.set(
                bool(storage.load_config().get("tool_approval_required"))
            )
        ap_row = ctk.CTkFrame(f, fg_color="transparent")
        ap_row.pack(fill="x", padx=8, pady=6)
        ctk.CTkLabel(ap_row, text="Company tasks").pack(side="left", padx=4)
        ctk.CTkSegmentedButton(
            ap_row,
            values=["manual", "auto"],
            variable=self.chat_company_approval_var,
            command=self._on_chat_company_approval_change,
            width=160,
        ).pack(side="left", padx=4)
        ctk.CTkSwitch(
            f,
            text="Require tool approval (terminal / GUI / pip / MCP)",
            variable=self.chat_tool_approval_var,
            command=self._on_chat_tool_approval_toggle,
        ).pack(anchor="w", padx=12, pady=6)
        ctk.CTkLabel(
            f,
            text="manual = CEO must approve · auto = tasks run · tool approval = Approvals page queue",
            text_color=_HC_MUTED,
            wraplength=460,
            justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 6))

        # Capabilities
        f = section("Capabilities (for this chat)")
        for text, var in (
            ("Terminal", self.chat_terminal_var),
            ("Skills", self.chat_skills_var),
            ("MCP", self.chat_mcp_var),
            ("Laptop GUI", self.chat_laptop_var),
            ("Org pipeline", self.chat_workflow_var),
            ("Safety limits", self.chat_safety_var),
        ):
            ctk.CTkSwitch(f, text=text, variable=var, command=self._on_chat_flags_save).pack(
                anchor="w", padx=12, pady=3
            )
        row_btns(
            f,
            [
                ("Cwd…", self._chat_pick_cwd),
                ("Lock folder 🔒", self._chat_toggle_cwd_lock),
                ("Skills on/off", self._chat_skills_manager),
                ("Tools list", self._chat_tools_list),
                ("Marketplace", self._chat_marketplace),
                ("How LLM works", self._chat_how_it_works),
                ("Run org pipeline now", self._chat_run_via_workflow),
            ],
        )
        ctk.CTkLabel(
            f,
            text=f"cwd: {self._chat_terminal_cwd}",
            text_color=_HC_MUTED,
            wraplength=460,
            anchor="w",
            justify="left",
        ).pack(anchor="w", padx=12, pady=4)

        # Media
        f = section("Media & tools")
        row_btns(
            f,
            [
                ("Image", self._chat_attach_image),
                ("Video", self._chat_attach_video),
                ("Clear attaches", self._chat_clear_attachments),
                ("Speak", self._chat_speak_last),
                ("Search web", self._chat_web_search_dialog),
                ("OCR", self._chat_ocr_dialog),
                ("Gen image", self._chat_image_gen_dialog),
            ],
        )

        ctk.CTkButton(win, text="Done", command=lambda: (self._update_composer_status(), win.destroy())).pack(
            pady=8
        )

    def _attachments_summary(self) -> str:
        files = list(self._chat_attachments or [])
        notes = list(getattr(self, "_chat_attached_notes", None) or [])
        if not files and not notes:
            return (
                "Attachments: (none) — Attach files… / notes via ＋ or Notes page | "
                "Large files will ask what to include | "
                "Terminal/Skills/MCP ON by default; Safety limits OFF"
            )
        parts: list[str] = []
        if files:
            parts.append("files: " + ", ".join(Path(p).name for p in files))
        if notes:
            try:
                from app.core.services.chat import notes_store as _ns
                titles = []
                for nid in notes:
                    n = _ns.get_note(nid)
                    titles.append((n or {}).get("title") or nid[:8])
                parts.append("notes: " + ", ".join(titles))
            except Exception:  # noqa: BLE001
                parts.append("notes: " + ", ".join(notes))
        return "Attachments: " + " · ".join(parts)

    def _ask_on_ui_thread(self, fn: Callable[[], Any], default: Any = None) -> Any:
        """Run a UI dialog from a worker thread and wait for the result."""
        box: dict[str, Any] = {}
        ev = threading.Event()

        def run() -> None:
            try:
                box["v"] = fn()
            except Exception as e:  # noqa: BLE001
                box["e"] = e
                box["v"] = default
            finally:
                ev.set()

        # Queue to main thread (safe); do not call Tk after() from workers
        self._ui_call(run)
        ev.wait(timeout=600)
        return box.get("v", default)

    def _ask_large_file(self, path: str, size: int) -> str:
        """User options when a file is large — no silent skip."""

        def dlg() -> str:
            name = Path(path).name
            mb = size / (1024 * 1024)
            msg = (
                f"Large file:\n{name}\n{size} bytes ({mb:.2f} MB)\n\n"
                "Choose how to include it for the LLM:\n\n"
                "  full  = entire file (no truncation)\n"
                "  head  = first ~80k characters\n"
                "  tail  = last ~80k characters\n"
                "  both  = head + tail\n"
                "  path  = path/name only\n"
                "  skip  = do not include\n"
            )
            # simpledialog returns string; also offer buttons via askstring with default full
            choice = simpledialog.askstring(
                "Large attachment",
                msg + "\nType one of: full / head / tail / both / path / skip",
                initialvalue="full",
                parent=self,
            )
            if not choice:
                return CHOICE_FULL
            c = choice.strip().lower()
            mapping = {
                "full": CHOICE_FULL,
                "head": CHOICE_HEAD,
                "tail": CHOICE_TAIL,
                "both": CHOICE_BOTH,
                "path": CHOICE_PATH_ONLY,
                "path_only": CHOICE_PATH_ONLY,
                "skip": CHOICE_SKIP,
            }
            return mapping.get(c, CHOICE_FULL)

        return self._ask_on_ui_thread(dlg, CHOICE_FULL)

    def _ask_large_output(self, length: int, _preview: str) -> str:
        def dlg() -> str:
            choice = simpledialog.askstring(
                "Large terminal output",
                f"Command output is large ({length} characters).\n\n"
                "Type: full / head / tail / truncate\n"
                "(Default full = no restriction)",
                initialvalue="full",
                parent=self,
            )
            if not choice:
                return "full"
            c = choice.strip().lower()
            return c if c in ("full", "head", "tail", "truncate") else "full"

        return self._ask_on_ui_thread(dlg, "full")

    def _chat_with_folder(self) -> None:
        """Task #7: index a folder and scope this chat's RAG to it."""
        from app.services import rag_knowledge as rag
        from app.services import chat_store as chat_svc

        path = filedialog.askdirectory(title="Chat with folder — pick a folder to index")
        if not path:
            return
        self.set_status("Indexing folder for chat…")
        try:
            r = rag.chat_with_folder(path)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Chat with folder", str(e), parent=self)
            self.set_status(f"Folder index failed: {e}")
            return
        if not r.get("ok"):
            messagebox.showerror(
                "Chat with folder",
                str(r.get("error") or "Index failed"),
                parent=self,
            )
            return
        folder = str(r.get("path_prefix") or path)
        try:
            if getattr(self, "_chat_state", None) is None:
                self._chat_state = self._load_active_chat()
            self._chat_state["knowledge_folder"] = folder
            self._chat_state["chat_folder"] = folder
            chat_svc.save_chat(self._chat_state)
        except Exception:  # noqa: BLE001
            pass
        # Optional embeddings re-rank (best effort)
        try:
            from app.services import local_embeddings

            local_embeddings.index_embeddings_for_all()
        except Exception:  # noqa: BLE001
            pass
        n = int(r.get("indexed") or 0)
        messagebox.showinfo(
            "Chat with folder",
            f"Ready.\n\nFolder:\n{folder}\n\n"
            f"Indexed {n} file(s).\n"
            "Ask questions in chat — answers will cite local files "
            "(click blue file:// links to open).",
            parent=self,
        )
        self.set_status(f"Folder chat: {n} files · {folder}", toast=True)
        try:
            self._update_composer_status()
        except Exception:  # noqa: BLE001
            pass

    def _chat_attach(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Attach files to chat",
            filetypes=[
                ("All files", "*.*"),
                (
                    "Text / code",
                    "*.txt;*.md;*.py;*.js;*.ts;*.json;*.yaml;*.yml;*.csv;*.log;*.xml;*.html;*.css;*.ps1;*.bat",
                ),
                ("Images", "*.png;*.jpg;*.jpeg;*.gif;*.webp;*.bmp"),
                ("Video", "*.mp4;*.webm;*.mkv;*.avi;*.mov"),
            ],
        )
        if not paths:
            return
        for p in paths:
            if p not in self._chat_attachments:
                self._chat_attachments.append(p)
        self._refresh_attach_label()
        self.set_status(f"Attached {len(paths)} file(s)")


    def attach_note_to_chat(self, note_id: str) -> None:
        """Attach a note id for full-context inject on the next chat send."""
        nid = (note_id or "").strip()
        if not nid:
            return
        notes = list(getattr(self, "_chat_attached_notes", None) or [])
        if nid not in notes:
            notes.append(nid)
        self._chat_attached_notes = notes
        try:
            self._refresh_note_attach_chips()
        except Exception:  # noqa: BLE001
            pass
        try:
            self._refresh_attach_label()
        except Exception:  # noqa: BLE001
            pass

    def detach_note_from_chat(self, note_id: str) -> None:
        nid = (note_id or "").strip()
        notes = [n for n in (getattr(self, "_chat_attached_notes", None) or []) if n != nid]
        self._chat_attached_notes = notes
        try:
            self._refresh_note_attach_chips()
        except Exception:  # noqa: BLE001
            pass
        try:
            self._refresh_attach_label()
        except Exception:  # noqa: BLE001
            pass

    def _chat_attach_note_dialog(self) -> None:
        """Pick one or more notes to attach for the next send."""
        from app.core.services.chat import notes_store
        from app.ui.themes import style_chrome_button, style_entry

        items = notes_store.list_notes()
        if not items:
            messagebox.showinfo(
                "Attach note",
                "No notes yet. Open Notes (sidebar → Workspace) and create one first.",
                parent=self,
            )
            return
        win = ctk.CTkToplevel(self)
        win.title("Attach note(s)")
        win.geometry("420x460")
        win.transient(self)
        win.grab_set()
        ctk.CTkLabel(
            win,
            text="Attach notes → next chat send (full context)",
            font=ctk.CTkFont(weight="bold"),
        ).pack(anchor="w", padx=12, pady=(12, 6))
        qvar = ctk.StringVar(value="")
        entry = ctk.CTkEntry(win, textvariable=qvar, placeholder_text="Filter…", **style_entry())
        entry.pack(fill="x", padx=12, pady=4)
        box = ctk.CTkScrollableFrame(win, height=320)
        box.pack(fill="both", expand=True, padx=12, pady=6)
        vars_by_id: dict[str, Any] = {}

        def rebuild(*_a: Any) -> None:
            for w in box.winfo_children():
                w.destroy()
            q = qvar.get().strip().lower()
            for it in items:
                title = it.get("title") or "Untitled"
                hay = f"{title}\n{it.get('body') or ''}".lower()
                if q and q not in hay:
                    continue
                var = vars_by_id.get(it["id"])
                if var is None:
                    var = ctk.BooleanVar(value=it["id"] in (getattr(self, "_chat_attached_notes", None) or []))
                    vars_by_id[it["id"]] = var
                ctk.CTkCheckBox(box, text=title[:80], variable=var).pack(anchor="w", pady=2)

        qvar.trace_add("write", rebuild)
        rebuild()

        def apply() -> None:
            for nid, var in vars_by_id.items():
                if var.get():
                    self.attach_note_to_chat(nid)
                else:
                    self.detach_note_from_chat(nid)
            win.destroy()
            n = len(getattr(self, "_chat_attached_notes", None) or [])
            self.set_status(f"Attached notes: {n}", toast=True)

        ctk.CTkButton(win, text="Apply", command=apply, **style_chrome_button(primary=True)).pack(pady=8)

    def _refresh_note_attach_chips(self) -> None:
        """Show / refresh attached-note chips under the composer."""
        from app.core.services.chat import notes_store
        from app.ui.themes import style_chrome_button, UI as _UI

        host = getattr(self, "_note_chips_host", None)
        if host is None or not str(getattr(host, "winfo_exists", lambda: 0)()):
            return
        for w in host.winfo_children():
            try:
                w.destroy()
            except Exception:  # noqa: BLE001
                pass
        ids = list(getattr(self, "_chat_attached_notes", None) or [])
        if not ids:
            return
        ctk.CTkLabel(host, text="Notes:", text_color=_UI["muted"], width=48).pack(side="left", padx=(0, 4))
        for nid in ids:
            note = notes_store.get_note(nid)
            title = (note or {}).get("title") or (nid[:8] + "…")
            chip = ctk.CTkFrame(host, fg_color=_UI.get("top_bg", ("#e5e7eb", "#1f2937")), corner_radius=12)
            chip.pack(side="left", padx=2, pady=2)
            ctk.CTkLabel(chip, text=f"📝 {title[:28]}", text_color=_UI["label"]).pack(side="left", padx=(8, 2), pady=2)
            ctk.CTkButton(
                chip,
                text="×",
                width=24,
                height=22,
                corner_radius=10,
                command=lambda i=nid: self.detach_note_from_chat(i),
                **style_chrome_button(),
            ).pack(side="left", padx=(0, 4), pady=2)

    def _chat_attach_image(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Attach images",
            filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.gif;*.webp;*.bmp"), ("All", "*.*")],
        )
        for p in paths or []:
            if p not in self._chat_attachments:
                self._chat_attachments.append(p)
            # also track as image on next user message via pending
            self._pending_images = getattr(self, "_pending_images", [])
            if p not in self._pending_images:
                self._pending_images.append(p)
        self._refresh_attach_label()
        self.set_status(f"Images: {len(paths or [])}")

    def _chat_attach_video(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Attach video",
            filetypes=[("Video", "*.mp4;*.webm;*.mkv;*.avi;*.mov"), ("All", "*.*")],
        )
        for p in paths or []:
            if p not in self._chat_attachments:
                self._chat_attachments.append(p)
            self._pending_videos = getattr(self, "_pending_videos", [])
            if p not in self._pending_videos:
                self._pending_videos.append(p)
        self._refresh_attach_label()
        self.set_status(f"Videos: {len(paths or [])}")

    def _refresh_attach_label(self) -> None:
        if hasattr(self, "chat_attach_label"):
            n_skills = len(discover_skills())
            imgs = len(getattr(self, "_pending_images", []) or [])
            vids = len(getattr(self, "_pending_videos", []) or [])
            self.chat_attach_label.configure(
                text=self._attachments_summary()
                + f"  |  img={imgs} vid={vids}  |  skills={n_skills}"
            )

    def _chat_export(self) -> None:
        from app.core.services.chat.chat_export import export_chat

        path = filedialog.asksaveasfilename(
            title="Export chat",
            defaultextension=".md",
            filetypes=[
                ("Markdown", "*.md"),
                ("JSON", "*.json"),
                ("Text", "*.txt"),
            ],
        )
        if not path:
            return
        fmt = "json" if path.lower().endswith(".json") else ("txt" if path.lower().endswith(".txt") else "md")
        out = export_chat(self._chat_state, fmt=fmt, path=Path(path))
        messagebox.showinfo("Export", f"Saved:\n{out}", parent=self)
        self.set_status(f"Exported {out.name}")

    def _chat_speak_last(self) -> None:
        """Speak last assistant reply (soft-degrades if TTS off/unavailable)."""
        try:
            from app.core.services.ai import voice_settings as _vs
            from app.core.services.ai.tts_service import is_speaking, speak_text, stop_speaking, tts_capability
        except Exception as e:  # noqa: BLE001
            messagebox.showinfo("Speak", f"TTS unavailable: {e}", parent=self)
            return

        if not _vs.tts_enabled():
            messagebox.showinfo(
                "Speak",
                "TTS is disabled in Settings → Voice. Enable “TTS / Speak button” to use read-aloud.",
                parent=self,
            )
            return

        if is_speaking():
            stop_speaking()
            self.set_status("Stopped speaking")
            return

        cap = tts_capability()
        if not cap.get("available"):
            messagebox.showinfo(
                "Speak",
                (cap.get("detail") or "TTS unavailable")
                + ("\n" + (cap.get("hint") or "")).rstrip(),
                parent=self,
            )
            self.set_status(f"TTS unavailable: {(cap.get('detail') or '')[:80]}")
            return

        text = ""
        for m in reversed(self._chat_state.get("messages") or []):
            if m.get("role") == "assistant" and m.get("content"):
                text = str(m["content"])
                break
        if not text:
            messagebox.showinfo("Speak", "No assistant message to speak.", parent=self)
            return
        res = speak_text(text, async_play=True)
        if not res.get("ok"):
            messagebox.showinfo("Speak", str(res.get("error") or "TTS failed"), parent=self)
            return
        self.set_status("Speaking last assistant reply…")

    def _clear_activity(self) -> None:
        from app.core.services.data.activity_log import clear

        clear()
        if hasattr(self, "activity_box"):
            self.activity_box.delete("1.0", "end")

    def _copy_activity(self) -> None:
        from app.core.services.data.activity_log import get_text

        text = get_text(2000)
        try:
            self.clipboard_clear()
            self.clipboard_append(text or "")
            self.set_status("Activity log copied to clipboard")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Copy log", str(e), parent=self)

    def _export_activity(self) -> None:
        from app.core.services.data.activity_log import export_log

        path = filedialog.asksaveasfilename(
            title="Export activity log",
            defaultextension=".log",
            filetypes=[("Log", "*.log"), ("Text", "*.txt"), ("All", "*.*")],
        )
        try:
            out = export_log(Path(path) if path else None)
            messagebox.showinfo("Export log", f"Saved:\n{out}", parent=self)
            self.set_status(f"Log exported: {out.name}")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Export log", str(e), parent=self)

    def _export_tool_audit(self, fmt: str = "json"):
        """PENDING #16: export tool-call audit log as JSON or CSV."""
        from tkinter import filedialog
        from pathlib import Path as _P

        from app.core.services.data import audit_log as _audit

        fmt = (fmt or "json").lower().strip()
        if fmt not in ("json", "csv"):
            fmt = "json"
        path = filedialog.asksaveasfilename(
            parent=self,
            title=f"Export tool audit ({fmt.upper()})",
            defaultextension=f".{fmt}",
            initialfile=f"tool_audit.{fmt}",
            filetypes=[(fmt.upper(), f"*.{fmt}"), ("All", "*.*")],
        )
        if not path:
            return None
        try:
            out = _audit.export_json(_P(path)) if fmt == "json" else _audit.export_csv(_P(path))
            messagebox.showinfo("Audit export", f"Saved:\n{out}", parent=self)
            self.set_status(f"Exported audit log → {out.name}", toast=True)
            return out
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Audit export", str(e), parent=self)
            return None
            messagebox.showinfo("Audit export", "Saved:\n" + str(out), parent=self)
    def _thinking_export_text(self) -> str:
        """Plain text of every step: title, current, raw."""
        lines: list[str] = []
        for i, step in enumerate(list(getattr(self, "_thinking_steps", None) or []), 1):
            if isinstance(step, dict):
                title = str(step.get("title") or step.get("text") or f"Step {i}")
                current = str(step.get("current") or step.get("text") or "")
                raw = str(step.get("raw") or step.get("text") or "")
            else:
                title = current = raw = str(step)
            lines.append(f"## {i}. {title}")
            if current and current != title:
                lines.append(f"Current: {current}")
            if raw:
                lines.append("Raw:")
                lines.append(raw)
            lines.append("")
        return "\n".join(lines).strip()

    def _clear_thinking_panel(self) -> None:
        """Clear the thinking panel display (does not clear chat history)."""
        self._thinking_steps = []
        self._thinking_pinned = set()
        self._thinking_destroy_cards()
        self.set_status("Thinking panel cleared")

    def _copy_thinking_panel(self) -> None:
        """Copy thinking steps to clipboard."""
        try:
            text = self._thinking_export_text()
            if not text:
                self.set_status("No thinking steps to copy")
                return
            self.clipboard_clear()
            self.clipboard_append(text)
            self.set_status("Thinking steps copied to clipboard")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Copy thinking", str(e), parent=self)

    def _export_thinking_panel(self) -> None:
        """Export thinking steps to a file."""
        try:
            text = self._thinking_export_text()
            if not text:
                self.set_status("No thinking steps to export")
                return
            from tkinter import filedialog

            path = filedialog.asksaveasfilename(
                title="Export thinking steps",
                defaultextension=".txt",
                filetypes=[("Text", "*.txt"), ("Markdown", "*.md"), ("All", "*.*")],
            )
            if path:
                from pathlib import Path

                Path(path).write_text(text, encoding="utf-8")
                messagebox.showinfo("Export thinking", f"Saved:\n{path}", parent=self)
                self.set_status(f"Thinking exported: {Path(path).name}")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Export thinking", str(e), parent=self)

    # --- Toolbar builder for side panel ---
    def _build_panel_toolbar(self, mode: str) -> None:
        """Build/rebuild the panel toolbar for the given mode."""
        if not hasattr(self, "panel_toolbar") or not self.panel_toolbar.winfo_exists():
            return
        # Clear existing buttons
        for w in self.panel_toolbar.winfo_children():
            try:
                w.destroy()
            except Exception:
                pass
        
        if mode == "Activity":
            ctk.CTkButton(self.panel_toolbar, text="Clear", width=60, command=self._clear_activity).pack(side="left", padx=2)
            ctk.CTkButton(self.panel_toolbar, text="Copy", width=60, command=self._copy_activity).pack(side="left", padx=2)
            ctk.CTkButton(self.panel_toolbar, text="Export", width=70, command=self._export_activity).pack(side="left", padx=2)
            ctk.CTkButton(self.panel_toolbar, text="↻ Refresh", width=80, command=self._refresh_activity_panel).pack(side="left", padx=2)
        elif mode == "Agents":
            ctk.CTkButton(self.panel_toolbar, text="Clear", width=60, command=self._clear_agent_track).pack(side="left", padx=2)
            ctk.CTkButton(self.panel_toolbar, text="Copy", width=60, command=self._copy_agent_track).pack(side="left", padx=2)
            ctk.CTkButton(self.panel_toolbar, text="↻ Refresh", width=80, command=lambda: self._fill_agent_track_box()).pack(side="left", padx=2)
        elif mode == "Artifacts":
            ctk.CTkButton(self.panel_toolbar, text="Clear", width=60, command=self._clear_artifacts_panel).pack(side="left", padx=2)
            ctk.CTkButton(self.panel_toolbar, text="↻ Refresh", width=80, command=self._refresh_artifacts_panel).pack(side="left", padx=2)
        elif mode == "Thinking":
            ctk.CTkButton(self.panel_toolbar, text="Clear", width=60, command=self._clear_thinking_panel).pack(side="left", padx=2)
            ctk.CTkButton(self.panel_toolbar, text="Copy", width=60, command=self._copy_thinking_panel).pack(side="left", padx=2)
            ctk.CTkButton(self.panel_toolbar, text="Export", width=70, command=self._export_thinking_panel).pack(side="left", padx=2)
            ctk.CTkButton(self.panel_toolbar, text="Collapse all", width=90, command=self._thinking_collapse_all).pack(side="left", padx=2)
            ctk.CTkButton(self.panel_toolbar, text="Expand last", width=88, command=self._thinking_expand_last).pack(side="left", padx=2)
        elif mode == "Terminal":
            ctk.CTkButton(self.panel_toolbar, text="Clear", width=60, command=self._clear_terminal_panel).pack(side="left", padx=2)
            ctk.CTkButton(self.panel_toolbar, text="Copy", width=60, command=self._copy_terminal_panel).pack(side="left", padx=2)
            ctk.CTkButton(self.panel_toolbar, text="Export", width=70, command=self._export_terminal_panel).pack(side="left", padx=2)
            ctk.CTkButton(self.panel_toolbar, text="↻ Refresh", width=80, command=self._refresh_terminal_panel).pack(side="left", padx=2)

    def _toggle_thinking_raw(self) -> None:
        """Legacy toggle — cards always show current + raw; expand last."""
        self._thinking_expand_last()

    def _thinking_destroy_cards(self) -> None:
        idle = getattr(self, "_thinking_scroll_idle", None)
        if idle is not None:
            try:
                self.after_cancel(idle)
            except Exception:  # noqa: BLE001
                pass
            self._thinking_scroll_idle = None
        cards = list(getattr(self, "_thinking_card_widgets", None) or [])
        self._thinking_card_widgets = []
        for card in cards:
            rb = card.get("raw_box")
            try:
                sc = getattr(rb, "_smooth_scroller", None) if rb is not None else None
                if sc is not None:
                    sc.stop()
            except Exception:  # noqa: BLE001
                pass
        lst = getattr(self, "thinking_list", None)
        if lst is not None:
            try:
                for w in list(lst.winfo_children()):
                    w.destroy()
            except Exception:  # noqa: BLE001
                pass
        for card in cards:
            fr = card.get("frame")
            try:
                if fr is not None and fr.winfo_exists():
                    fr.destroy()
            except Exception:  # noqa: BLE001
                pass

    def _thinking_step_bits(self, step: Any, idx: int) -> tuple[str, str, str]:
        if isinstance(step, dict):
            raw = str(
                step.get("raw")
                or step.get("text")
                or step.get("msg")
                or step.get("detail")
                or step.get("content")
                or ""
            ).strip()
            current = str(
                step.get("current")
                or step.get("text")
                or step.get("msg")
                or step.get("detail")
                or raw
                or ""
            ).strip()
            title = str(step.get("title") or "").strip()
            if not title:
                title = self._humanize_thinking_step(step) or current or raw or f"Step {idx + 1}"
            if not current:
                current = self._humanize_thinking_step(step) or raw or title
            if not raw:
                raw = current or title
        else:
            s = str(step or "").strip()
            title = self._humanize_thinking_step(s) or s or f"Step {idx + 1}"
            current = title
            raw = s or title
        if len(title) > 72:
            title = title[:69] + "…"
        return title, current, raw

    def _thinking_set_open(self, idx: int, open_now: bool) -> None:
        cards = getattr(self, "_thinking_card_widgets", None) or []
        if idx < 0 or idx >= len(cards):
            return
        card = cards[idx]
        if bool(card.get("open")) == bool(open_now) and card.get("_packed") == bool(open_now):
            return
        card["open"] = bool(open_now)
        card["_packed"] = bool(open_now)
        try:
            n = idx + 1
            title = card.get("title_text") or f"Step {n}"
            card["toggle"].configure(text=f"{'▼' if open_now else '▶'}  {n}. {title}")
        except Exception:  # noqa: BLE001
            pass
        body = card.get("body")
        try:
            if open_now:
                body.pack(fill="x", padx=8, pady=(0, 6))
            else:
                body.pack_forget()
        except Exception:  # noqa: BLE001
            pass

    def _thinking_toggle_card(self, idx: int) -> None:
        cards = getattr(self, "_thinking_card_widgets", None) or []
        if idx < 0 or idx >= len(cards):
            return
        new = not bool(cards[idx].get("open"))
        self._thinking_set_open(idx, new)
        pinned: set[int] = set(getattr(self, "_thinking_pinned", None) or set())
        if new:
            pinned.add(idx)
        else:
            pinned.discard(idx)
        self._thinking_pinned = pinned

    def _thinking_collapse_except(self, keep: int) -> None:
        pinned = set(getattr(self, "_thinking_pinned", None) or set())
        for i, card in enumerate(getattr(self, "_thinking_card_widgets", None) or []):
            want = i == keep or i in pinned
            if bool(card.get("open")) != want:
                self._thinking_set_open(i, want)

    def _thinking_collapse_all(self) -> None:
        self._thinking_pinned = set()
        for i, _c in enumerate(getattr(self, "_thinking_card_widgets", None) or []):
            self._thinking_set_open(i, False)
        self.set_status("Thinking steps collapsed")

    def _thinking_expand_last(self) -> None:
        cards = getattr(self, "_thinking_card_widgets", None) or []
        if not cards:
            return
        last = len(cards) - 1
        self._thinking_collapse_except(last)
        self._thinking_set_open(last, True)
        self._thinking_follow_bottom = True
        self._thinking_scroll_to_end(force=True)

    def _thinking_canvas(self) -> Any:
        lst = getattr(self, "thinking_list", None)
        if lst is None:
            return None
        try:
            if not lst.winfo_exists():
                return None
        except Exception:  # noqa: BLE001
            return None
        return getattr(lst, "_parent_canvas", None)

    def _fit_thinking_scroll_inner(self) -> None:
        """Keep Thinking cards as wide as the Live pane (avoid 2-letter wrap)."""
        try:
            lst = getattr(self, "thinking_list", None)
            canvas = self._thinking_canvas()
            if lst is None or canvas is None:
                return
            cw = int(canvas.winfo_width() or 0)
            if cw < 80:
                return
            win_id = getattr(lst, "_create_window_id", None) or getattr(lst, "_window_id", None)
            if win_id is not None:
                canvas.itemconfigure(win_id, width=cw)
            inner = getattr(lst, "_scrollable_frame", None)
            if inner is not None:
                try:
                    inner.configure(width=max(180, cw - 4))
                except Exception:  # noqa: BLE001
                    pass
            wrap = max(160, cw - 36)
            for card in list(getattr(self, "_thinking_card_widgets", None) or []):
                lbl = card.get("current_lbl")
                if lbl is not None:
                    try:
                        lbl.configure(wraplength=wrap)
                    except Exception:  # noqa: BLE001
                        pass
        except Exception:  # noqa: BLE001
            pass

    def _thinking_bind_wheel(self, widget: Any) -> None:
        if widget is None:
            return
        try:
            if bool(getattr(widget, "_own_smooth_scroll", False)):
                return
        except Exception:  # noqa: BLE001
            pass
        try:
            widget.bind("<MouseWheel>", self._on_thinking_mousewheel)
            widget.bind("<Button-4>", self._on_thinking_mousewheel)
            widget.bind("<Button-5>", self._on_thinking_mousewheel)
        except Exception:  # noqa: BLE001
            pass
        try:
            for ch in widget.winfo_children():
                self._thinking_bind_wheel(ch)
        except Exception:  # noqa: BLE001
            pass

    def _on_thinking_mousewheel(self, event: Any) -> str | None:
        """Scroll the Thinking list. Nested raw boxes call this at their edge."""
        canvas = self._thinking_canvas()
        if canvas is None:
            return None
        try:
            delta = int(getattr(event, "delta", 0) or 0)
            if delta:
                steps = int(round(-delta / 20.0))
                if steps == 0:
                    steps = -1 if delta > 0 else 1
                steps = max(-12, min(12, steps))
                self._thinking_scroll_units(steps)
            elif getattr(event, "num", None) == 4:
                self._thinking_scroll_units(-4)
            elif getattr(event, "num", None) == 5:
                self._thinking_scroll_units(4)
            return "break"
        except Exception:  # noqa: BLE001
            return None

    def _thinking_scroll_units(self, steps: int) -> None:
        if steps == 0:
            return
        canvas = self._thinking_canvas()
        if canvas is None:
            return
        try:
            canvas.yview_scroll(int(steps), "units")
            _y0, y1 = canvas.yview()
            self._thinking_follow_bottom = float(y1) >= 0.90
        except Exception:  # noqa: BLE001
            pass

    def _thinking_scroll_to_end(self, *, force: bool = False) -> None:
        """Follow the latest card once; never yview_moveto on every token."""
        if not force and not getattr(self, "_thinking_follow_bottom", True):
            return
        if getattr(self, "_thinking_scroll_idle", None) is not None and not force:
            return

        def _go() -> None:
            self._thinking_scroll_idle = None
            if not force and not getattr(self, "_thinking_follow_bottom", True):
                return
            try:
                import time as _time

                now = _time.monotonic()
                last = float(getattr(self, "_thinking_scroll_end_ts", 0) or 0)
                if not force and now - last < 0.70:
                    return
                self._thinking_scroll_end_ts = now
                canvas = self._thinking_canvas()
                if canvas is None:
                    return
                if not force:
                    try:
                        _y0, y1 = canvas.yview()
                        if float(y1) < 0.86:
                            self._thinking_follow_bottom = False
                            return
                        if float(y1) >= 0.995:
                            return
                    except Exception:  # noqa: BLE001
                        pass
                canvas.yview_moveto(1.0)
            except Exception:  # noqa: BLE001
                pass

        if force:
            _go()
            return
        try:
            self._thinking_scroll_idle = self.after(90, _go)
        except Exception:  # noqa: BLE001
            _go()

    def _thinking_update_card(self, idx: int) -> None:
        steps = list(getattr(self, "_thinking_steps", None) or [])
        cards = getattr(self, "_thinking_card_widgets", None) or []
        if idx < 0 or idx >= len(steps) or idx >= len(cards):
            return
        title, current, raw = self._thinking_step_bits(steps[idx], idx)
        card = cards[idx]
        if card.get("title_text") == title and card.get("_raw_cache") == raw and card.get("_cur_cache") == current:
            return
        card["title_text"] = title
        card["_raw_cache"] = raw
        card["_cur_cache"] = current
        try:
            n = idx + 1
            card["toggle"].configure(
                text=f"{'▼' if card.get('open') else '▶'}  {n}. {title}"
            )
            cur_l = card.get("current_lbl")
            if cur_l is not None:
                cur_l.configure(text=current or "(no current text)")
            raw_box = card.get("raw_box")
            if raw_box is not None:
                raw_box.configure(state="normal")
                raw_box.delete("1.0", "end")
                raw_box.insert("1.0", raw or current or title or "")
                raw_box.configure(state="disabled")
                # Do not see("end") — that yanked the parent list on every token.
        except Exception:  # noqa: BLE001
            pass

    def _thinking_add_card(self, idx: int, *, collapse_others: bool = True) -> None:
        lst = getattr(self, "thinking_list", None)
        if lst is None:
            return
        steps = list(getattr(self, "_thinking_steps", None) or [])
        if idx < 0 or idx >= len(steps):
            return
        if not hasattr(self, "_thinking_card_widgets") or self._thinking_card_widgets is None:
            self._thinking_card_widgets = []
        if idx < len(self._thinking_card_widgets):
            self._thinking_update_card(idx)
            return
        from app.ui.themes import UI as _UI, style_chrome_button

        title, current, raw = self._thinking_step_bits(steps[idx], idx)
        wrap = 260
        try:
            wrap = max(200, int(lst.winfo_width() or 280) - 28)
        except Exception:  # noqa: BLE001
            pass
        frame = ctk.CTkFrame(
            lst,
            fg_color=("#eef2ff", "#1a1a2e"),
            corner_radius=8,
            border_width=1,
            border_color=_UI.get("top_border", ("#e5e5e5", "#2a2a2a")),
        )
        frame.pack(fill="x", padx=2, pady=3)
        toggle = ctk.CTkButton(
            frame,
            text=f"▼  {idx + 1}. {title}",
            anchor="w",
            height=28,
            command=lambda i=idx: self._thinking_toggle_card(i),
            **style_chrome_button(),
        )
        toggle.pack(fill="x", padx=4, pady=(4, 2))
        body = ctk.CTkFrame(frame, fg_color="transparent")
        body.pack(fill="x", padx=8, pady=(0, 6))
        ctk.CTkLabel(
            body,
            text="Current",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=_UI.get("muted", ("#6b7280", "#9ca3af")),
            anchor="w",
        ).pack(fill="x")
        current_lbl = ctk.CTkLabel(
            body,
            text=current or "(no current text)",
            font=ctk.CTkFont(size=12),
            text_color=_UI["label"],
            anchor="w",
            justify="left",
            wraplength=wrap,
        )
        current_lbl.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(
            body,
            text="Raw thinking",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=_UI.get("muted", ("#6b7280", "#9ca3af")),
            anchor="w",
        ).pack(fill="x")
        raw_box = ctk.CTkTextbox(
            body,
            height=96,
            font=ctk.CTkFont(family="Consolas", size=11),
            wrap="word",
            activate_scrollbars=True,
        )
        raw_box.pack(fill="x", pady=(0, 2))
        raw_box.insert("1.0", raw or "")
        raw_box.configure(state="disabled")
        card = {
            "frame": frame,
            "toggle": toggle,
            "body": body,
            "current_lbl": current_lbl,
            "raw_box": raw_box,
            "open": True,
            "_packed": True,
            "title_text": title,
            "_raw_cache": raw,
            "_cur_cache": current,
        }
        self._thinking_card_widgets.append(card)
        if collapse_others:
            self._thinking_collapse_except(idx)
        try:
            bind_smooth_text_wheel(
                raw_box,
                on_edge=self._on_thinking_mousewheel,
            )
        except Exception:  # noqa: BLE001
            pass
        try:
            self._thinking_bind_wheel(frame)
        except Exception:  # noqa: BLE001
            pass
        try:
            self._fit_thinking_scroll_inner()
        except Exception:  # noqa: BLE001
            pass
        self._thinking_scroll_to_end(force=False)

    def _thinking_sync_cards(self) -> None:
        lst = getattr(self, "thinking_list", None)
        if lst is None:
            return
        try:
            if not lst.winfo_exists():
                return
        except Exception:  # noqa: BLE001
            return
        steps = list(getattr(self, "_thinking_steps", None) or [])
        cards = getattr(self, "_thinking_card_widgets", None)
        if cards is None:
            self._thinking_card_widgets = []
            cards = self._thinking_card_widgets
        if not steps:
            if cards:
                self._thinking_destroy_cards()
            if not lst.winfo_children():
                from app.ui.themes import UI as _UI

                ctk.CTkLabel(
                    lst,
                    text="No thinking yet. Send a message — each step can expand to show current + raw LLM thinking.",
                    text_color=_UI.get("muted", ("#6b7280", "#9ca3af")),
                    wraplength=240,
                    justify="left",
                    anchor="w",
                ).pack(anchor="w", padx=8, pady=12)
            return
        # Drop empty-state label if present
        if cards and len(cards) > len(steps):
            self._thinking_destroy_cards()
            cards = self._thinking_card_widgets
        for i in range(len(cards), len(steps)):
            self._thinking_add_card(i, collapse_others=True)
        if steps:
            last = len(steps) - 1
            self._thinking_update_card(last)
            # Full rebuild (tab switch) may open last; live paints must not
            # pack_forget/pack every token — that is the Thinking scroll jump.

    # --- Terminal panel operations ---
    def _clear_terminal_panel(self) -> None:
        """Clear the terminal panel display."""
        if hasattr(self, "terminal_box") and self.terminal_box.winfo_exists():
            try:
                self.terminal_box.configure(state="normal")
                self.terminal_box.delete("1.0", "end")
                self.terminal_box.configure(state="disabled")
            except Exception:
                pass
        self._terminal_log_lines = []
        self.set_status("Terminal panel cleared")

    def _copy_terminal_panel(self) -> None:
        """Copy terminal output to clipboard."""
        if not hasattr(self, "terminal_box") or not self.terminal_box.winfo_exists():
            return
        try:
            text = self.terminal_box.get("1.0", "end").strip()
            self.clipboard_clear()
            self.clipboard_append(text)
            self.set_status("Terminal output copied to clipboard")
        except Exception as e:
            messagebox.showerror("Copy terminal", str(e), parent=self)

    def _export_terminal_panel(self) -> None:
        """Export terminal output to a file."""
        if not hasattr(self, "terminal_box") or not self.terminal_box.winfo_exists():
            return
        try:
            text = self.terminal_box.get("1.0", "end").strip()
            if not text:
                self.set_status("No terminal output to export")
                return
            from tkinter import filedialog
            path = filedialog.asksaveasfilename(
                title="Export terminal output",
                defaultextension=".txt",
                filetypes=[("Text", "*.txt"), ("Markdown", "*.md"), ("All", "*.*")],
            )
            if path:
                from pathlib import Path
                Path(path).write_text(text, encoding="utf-8")
                messagebox.showinfo("Export terminal", f"Saved:\n{path}", parent=self)
                self.set_status(f"Terminal exported: {Path(path).name}")
        except Exception as e:
            messagebox.showerror("Export terminal", str(e), parent=self)

    def _refresh_terminal_panel(self) -> None:
        """Refresh terminal panel from stored lines."""
        if not hasattr(self, "terminal_box") or not self.terminal_box.winfo_exists():
            return
        lines = getattr(self, "_terminal_log_lines", [])
        try:
            self.terminal_box.configure(state="normal")
            self.terminal_box.delete("1.0", "end")
            if lines:
                for line in lines:
                    # Apply color tags based on line content
                    tag = "info"
                    lower = line.lower()
                    if lower.startswith("$ ") or "command:" in lower:
                        tag = "cmd"
                    elif "stdout" in lower:
                        tag = "stdout"
                    elif "stderr" in lower:
                        tag = "stderr"
                    elif "exit code" in lower:
                        tag = "exit"
                    elif "cwd:" in lower:
                        tag = "cwd"
                    self.terminal_box.insert("end", line + "\n", tag)
            else:
                self.terminal_box.insert("1.0", "No terminal activity yet…\nRun terminal commands to see output here.")
            self.terminal_box.configure(state="disabled")
            self.terminal_box.see("end")
        except Exception:
            pass

    def _bind_terminal_log(self) -> None:
        """Bind to terminal tool activity for live terminal panel updates."""
        from app.core.services.data.activity_log import add_listener
        import re
        
        # Preserve existing buffer across re-binds
        self._terminal_log_lines = getattr(self, "_terminal_log_lines", [])
        
        def on_line(line: str) -> None:
            def ui() -> None:
                try:
                    if not self.winfo_exists():
                        return
                    box = getattr(self, "terminal_box", None)
                    if box is None or not box.winfo_exists():
                        return
                    # Always buffer terminal-related activity, regardless of active tab
                    # Filter for terminal-related activity (matches activity_log format: [HH:MM:SS][source] message)
                    # Source is in [source] format; check for terminal/stdout/stderr in source bracket
                    source_match = re.search(r'\[(\w+)\]', line)
                    source = source_match.group(1).lower() if source_match else ""
                    if source not in ("terminal", "stdout", "stderr"):
                        return
                    # Also allow lines with explicit command/exit/cwd markers
                    lower = line.lower()
                    if not (source in ("terminal", "stdout", "stderr") or 
                            "$ " in lower or "command:" in lower or "exit=" in lower or "cwd:" in lower):
                        return
                    self._terminal_log_lines.append(line)
                    # Keep last 500 lines
                    if len(self._terminal_log_lines) > 500:
                        self._terminal_log_lines = self._terminal_log_lines[-500:]
                    # Only update UI if Terminal tab is currently visible
                    if getattr(self, "side_panel_mode", None) and self.side_panel_mode.get() == "Terminal":
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
            self._ui_call(ui)
        
        add_listener(on_line)

    # --- Agent track panel operations ---
    def _clear_agent_track(self) -> None:
        """Clear the agent track panel."""
        if hasattr(self, "agent_track_box") and self.agent_track_box.winfo_exists():
            try:
                self.agent_track_box.configure(state="normal")
                self.agent_track_box.delete("1.0", "end")
                self.agent_track_box.configure(state="disabled")
            except Exception:
                pass
        self.set_status("Agent track cleared")

    def _copy_agent_track(self) -> None:
        """Copy agent track to clipboard."""
        if not hasattr(self, "agent_track_box") or not self.agent_track_box.winfo_exists():
            return
        try:
            text = self.agent_track_box.get("1.0", "end").strip()
            self.clipboard_clear()
            self.clipboard_append(text)
            self.set_status("Agent track copied to clipboard")
        except Exception as e:
            messagebox.showerror("Copy agent track", str(e), parent=self)

    # --- Artifacts panel operations ---
    def _clear_artifacts_panel(self) -> None:
        """Clear the artifacts panel."""
        if hasattr(self, "artifacts_frame") and self.artifacts_frame.winfo_exists():
            for w in self.artifacts_frame.winfo_children():
                try:
                    w.destroy()
                except Exception:
                    pass
            ctk.CTkLabel(
                self.artifacts_frame,
                text="Artifacts cleared.\nNew artifacts will appear here.",
                text_color="gray",
            ).pack(anchor="w", padx=6, pady=8)
        self.set_status("Artifacts panel cleared")

    def _refresh_activity_panel(self) -> None:
        """Refresh activity panel from log."""
        if not hasattr(self, "activity_box") or not self.activity_box.winfo_exists():
            return
        from app.core.services.data.activity_log import get_text as _act_get
        try:
            self.activity_box.configure(state="normal")
            self.activity_box.delete("1.0", "end")
            text = _act_get() or "Activity appears here while tools run…"
            self.activity_box.insert("1.0", text + "\n")
            self.activity_box.configure(state="disabled")
            self.activity_box.see("end")
        except Exception:
            pass

    def _bind_activity_log(self) -> None:
        from app.core.services.data.activity_log import add_listener

        def on_line(line: str) -> None:
            def ui() -> None:
                try:
                    if not self.winfo_exists():
                        return
                    box = getattr(self, "activity_box", None)
                    if box is None:
                        return
                    try:
                        if not box.winfo_exists():
                            return
                    except Exception:  # noqa: BLE001
                        return
                    # only append when Activity tab visible
                    if getattr(self, "side_panel_mode", None) and self.side_panel_mode.get() != "Activity":
                        return
                    # Skip heavy Live append when panel is hidden (still logged in memory)
                    if not bool(getattr(self, "_live_panel_visible", False)):
                        return
                    box.insert("end", line + "\n")
                    box.see("end")
                except Exception:  # noqa: BLE001
                    # Widget may be destroyed mid-callback (page switch / app close)
                    pass

            self._ui_call(ui)

        add_listener(on_line)

    def _bind_agent_tracker(self) -> None:
        from app.core.services.data.agent_tracker import add_listener

        def on_change() -> None:
            # Debounce: every LLM thinking step used to full-refresh the side panel → UI freeze
            if not bool(getattr(self, "_live_panel_visible", False)):
                return
            if getattr(self, "side_panel_mode", None):
                mode = self.side_panel_mode.get() or "Activity"
                if mode == "Activity":
                    # Activity tab is append-only via activity_log; skip full refresh
                    return
            aid = getattr(self, "_side_panel_refresh_after", None)
            if aid is not None:
                try:
                    self.after_cancel(aid)
                except Exception:  # noqa: BLE001
                    pass

            def run() -> None:
                self._side_panel_refresh_after = None
                try:
                    if self.winfo_exists():
                        self._refresh_side_panel()
                except Exception:  # noqa: BLE001
                    pass

            try:
                self._side_panel_refresh_after = self.after(400, run)
            except Exception:  # noqa: BLE001
                self._ui_call(run)

        add_listener(on_change)

    def _refresh_side_panel(self) -> None:
        mode = "Activity"
        if getattr(self, "side_panel_mode", None):
            mode = self.side_panel_mode.get() or "Activity"
        if not hasattr(self, "activity_box"):
            return
        # Hide all content panes first
        try:
            self.activity_box.grid_remove()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.agent_track_box.grid_remove()
        except Exception:  # noqa: BLE001
            pass
        try:
            if hasattr(self, "artifacts_frame"):
                self.artifacts_frame.grid_remove()
        except Exception:  # noqa: BLE001
            pass
        try:
            if hasattr(self, "thinking_box"):
                self.thinking_box.grid_remove()
        except Exception:  # noqa: BLE001
            pass
        try:
            if hasattr(self, "thinking_list"):
                self.thinking_list.grid_remove()
        except Exception:  # noqa: BLE001
            pass
        try:
            if hasattr(self, "terminal_box"):
                self.terminal_box.grid_remove()
        except Exception:  # noqa: BLE001
            pass
        try:
            if hasattr(self, "think_toolbar"):
                self.think_toolbar.grid_remove()
        except Exception:  # noqa: BLE001
            pass
        # Show appropriate content and build toolbar
        if mode == "Agents":
            self.agent_track_box.grid(row=2, column=0, sticky="nsew", padx=6, pady=(0, 4))
            self._fill_agent_track_box()
            self._build_panel_toolbar("Agents")
        elif mode == "Artifacts":
            if hasattr(self, "artifacts_frame"):
                self.artifacts_frame.grid(row=2, column=0, sticky="nsew", padx=6, pady=(0, 4))
            self._refresh_artifacts_panel()
            self._build_panel_toolbar("Artifacts")
        elif mode == "Thinking":
            if hasattr(self, "thinking_list"):
                self.thinking_list.grid(row=2, column=0, sticky="nsew", padx=6, pady=(0, 4))
            elif hasattr(self, "thinking_box"):
                self.thinking_box.grid(row=2, column=0, sticky="nsew", padx=6, pady=(0, 4))
            self._refresh_thinking_panel()
            self._build_panel_toolbar("Thinking")
        elif mode == "Terminal":
            if hasattr(self, "terminal_box"):
                self.terminal_box.grid(row=2, column=0, sticky="nsew", padx=6, pady=(0, 4))
            self._refresh_terminal_panel()
            self._build_panel_toolbar("Terminal")
        else:
            self.activity_box.grid(row=2, column=0, sticky="nsew", padx=6, pady=(0, 4))
            self._build_panel_toolbar("Activity")

    def _refresh_thinking_panel(self) -> None:
        """Sync collapsible step cards in the Live → Thinking tab."""
        self._thinking_sync_cards()

    def _refresh_artifacts_panel(self) -> None:
        """Task #12: list files/images/reports/diffs for this chat turn."""
        from app.ui.themes import style_chrome_button, UI as _UI
        from app.services import artifacts as arts

        if not hasattr(self, "artifacts_frame"):
            return
        for w in self.artifacts_frame.winfo_children():
            try:
                w.destroy()
            except Exception:  # noqa: BLE001
                pass
        chat = getattr(self, "_chat_state", None) or {}
        try:
            bundle = arts.collect_artifacts(
                messages=list(chat.get("messages") or []),
                chat_id=str(chat.get("id") or ""),
                pending_images=list(getattr(self, "_pending_images", []) or []),
                pending_videos=list(getattr(self, "_pending_videos", []) or []),
                attachments=list(getattr(self, "_chat_attachments", []) or []),
                this_turn_only=False,
            )
        except Exception as e:  # noqa: BLE001
            ctk.CTkLabel(
                self.artifacts_frame,
                text=f"Artifacts error: {e}",
                text_color=_UI["muted"],
            ).pack(anchor="w", padx=6, pady=8)
            return
        self._last_artifacts_bundle = bundle
        ctk.CTkLabel(
            self.artifacts_frame,
            text=str(bundle.get("summary") or "Artifacts"),
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=_UI["label"],
            anchor="w",
            wraplength=220,
        ).pack(fill="x", padx=4, pady=(4, 6))
        items = list(bundle.get("items") or [])
        if not items:
            ctk.CTkLabel(
                self.artifacts_frame,
                text=(
                    "Nothing yet.\n"
                    "Images, file edits, research reports,\n"
                    "and attachments show up here."
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
            row = ctk.CTkFrame(self.artifacts_frame, fg_color=("gray92", "gray18"), corner_radius=8)
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
                    command=lambda f=fd: self._open_file_diff_viewer(f),
                    **style_chrome_button(primary=True),
                ).pack(side="left", padx=2)
            if path:
                ctk.CTkButton(
                    btns,
                    text="Open",
                    width=50,
                    height=24,
                    command=lambda p=path: self._open_artifact_path(p),
                    **style_chrome_button(),
                ).pack(side="left", padx=2)
                ctk.CTkButton(
                    btns,
                    text="Copy",
                    width=50,
                    height=24,
                    command=lambda p=path: self._copy_artifact_path(p),
                    **style_chrome_button(),
                ).pack(side="left", padx=2)
            if kind == "image" and path:
                ctk.CTkButton(
                    btns,
                    text="View",
                    width=50,
                    height=24,
                    command=lambda p=path: self._open_image_lightbox(p),
                    **style_chrome_button(),
                ).pack(side="left", padx=2)

    def _open_artifact_path(self, path: str) -> None:
        p = (path or "").strip()
        if not p:
            return
        try:
            from app.ui.components.message_box import open_url_or_path
            from app.core.services.data.rag_knowledge import path_to_file_uri

            if p.lower().startswith("file:") or p.lower().startswith("http"):
                open_url_or_path(p)
            else:
                open_url_or_path(path_to_file_uri(p))
            self.set_status(f"Opened {Path(p).name if not p.startswith('http') else p[:40]}", toast=True)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Open artifact", str(e), parent=self)

    def _copy_artifact_path(self, path: str) -> None:
        try:
            self.clipboard_clear()
            self.clipboard_append(path or "")
            self.set_status("Path copied", toast=True)
        except Exception:  # noqa: BLE001
            pass

    def _fill_agent_track_box(self) -> None:
        from app.services import agent_tracker

        if not hasattr(self, "agent_track_box"):
            return
        self.agent_track_box.delete("1.0", "end")
        # Primary view: which agent did what (timeline of steps)
        lines = [agent_tracker.format_who_did_what(50), "", "=== ACTIVE RUN DETAIL ===", ""]
        active = agent_tracker.get_active()
        if active:
            lines.append(f"▶ AGENT: {active.get('agent_name')}")
            lines.append(f"  Role:   {active.get('agent_role')}")
            lines.append(f"  Model:  {active.get('model')}")
            lines.append(f"  Task:   {active.get('task_title')}")
            lines.append(f"  Status: {active.get('status')}")
            lines.append("  Actions this run:")
            for a in (active.get("actions") or [])[-20:]:
                lines.append(f"    · {a.get('action')}")
            lines.append("")
            lines.append("  --- OUTPUT ---")
            lines.append(str(active.get("output") or "(still running…)")[:1500])
        else:
            lines.append("(no agent running right now)")
        lines.append("")
        lines.append("=== RECENT AGENTS ===")
        for r in agent_tracker.list_recent(12):
            name = r.get("agent_name") or "?"
            out = str(r.get("output") or r.get("error") or "").replace("\n", " ")
            lines.append(f"• {name} [{r.get('status')}] {r.get('task_title')}")
            n_act = len(r.get("actions") or [])
            if n_act:
                lines.append(f"  steps: {n_act}")
            lines.append(f"  out:  {out[:160]}{'…' if len(out) > 160 else ''}")
        self.agent_track_box.insert("1.0", "\n".join(lines))

    def _open_image_lightbox(self, path: str) -> None:
        """Grok-style expand image in a popup."""
        win = ctk.CTkToplevel(self)
        win.title(Path(path).name)
        win.geometry("900x700")
        win.transient(self)
        try:
            from PIL import Image  # type: ignore

            im = Image.open(path)
            # fit window
            im.thumbnail((860, 640))
            cimg = ctk.CTkImage(light_image=im, dark_image=im, size=im.size)
            lbl = ctk.CTkLabel(win, image=cimg, text="")
            lbl.image = cimg  # type: ignore[attr-defined]
            lbl.pack(expand=True, padx=12, pady=12)
        except Exception as e:  # noqa: BLE001
            ctk.CTkLabel(win, text=f"Cannot open image:\n{e}\n{path}").pack(padx=20, pady=20)
        ctk.CTkButton(win, text="Close", command=win.destroy).pack(pady=8)

    def _chat_search(self) -> None:
        q = (self.chat_search_var.get() if hasattr(self, "chat_search_var") else "").strip().lower()
        if not q:
            messagebox.showinfo("Search", "Type a search query.", parent=self)
            return
        hits = []
        for i, m in enumerate(self._chat_state.get("messages") or []):
            content = str(m.get("content") or "")
            if q in content.lower() or q in str(m.get("role") or "").lower():
                snippet = content.replace("\n", " ")[:160]
                hits.append(f"#{i + 1} [{m.get('role')}] {snippet}")
        if not hits:
            messagebox.showinfo("Search", f"No matches for “{q}” in this chat.", parent=self)
            return
        win = ctk.CTkToplevel(self)
        win.title(f"Search: {q}")
        win.geometry("640x420")
        win.transient(self)
        box = ctk.CTkTextbox(win, wrap="word")
        box.pack(fill="both", expand=True, padx=10, pady=10)
        box.insert("1.0", f"Found {len(hits)} hit(s) in this chat:\n\n" + "\n\n".join(hits))
        box.configure(state="disabled")

    def _chat_search_all(self) -> None:
        q = (self.chat_search_var.get() if hasattr(self, "chat_search_var") else "").strip().lower()
        if not q:
            messagebox.showinfo("Search", "Type a search query.", parent=self)
            return
        hits = []
        for meta in chat_store.list_chats():
            full = chat_store.load_chat(meta["id"])
            title = full.get("title") or meta["id"][:8]
            for i, m in enumerate(full.get("messages") or []):
                content = str(m.get("content") or "")
                if q in content.lower():
                    hits.append(
                        f"[{title}] #{i + 1} [{m.get('role')}] {content.replace(chr(10), ' ')[:140]}"
                    )
                if len(hits) >= 80:
                    break
            if len(hits) >= 80:
                break
        win = ctk.CTkToplevel(self)
        win.title(f"Search all chats: {q}")
        win.geometry("720x480")
        win.transient(self)
        box = ctk.CTkTextbox(win, wrap="word")
        box.pack(fill="both", expand=True, padx=10, pady=10)
        if not hits:
            box.insert("1.0", f"No matches for “{q}” across chats.")
        else:
            box.insert("1.0", f"Found {len(hits)} hit(s):\n\n" + "\n\n".join(hits))
        box.configure(state="disabled")

    def _page_track(self) -> None:
        """Full agent tracking: active agent, inputs, outputs."""
        from app.services import agent_tracker

        root = ctk.CTkFrame(self.content, fg_color="transparent")
        root.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
        root.grid_columnconfigure(0, weight=1)
        root.grid_columnconfigure(1, weight=1)
        root.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            root, text="Agent track", font=ctk.CTkFont(size=22, weight="bold")
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        ctk.CTkLabel(
            root,
            text="See which agent is active, what it received (input), and what it produced (output).",
            text_color=_HC_MUTED,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 8))

        left = ctk.CTkFrame(root)
        left.grid(row=2, column=0, sticky="nsew", padx=(0, 8))
        left.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(left, text="Active / recent agents", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, sticky="w", padx=10, pady=8
        )
        list_box = ctk.CTkScrollableFrame(left)
        list_box.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)

        right = ctk.CTkFrame(root)
        right.grid(row=2, column=1, sticky="nsew")
        right.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(right, text="Input / Output detail", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, sticky="w", padx=10, pady=8
        )
        detail = ctk.CTkTextbox(right, wrap="word")
        detail.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)

        search_e = ctk.CTkEntry(root, placeholder_text="Search agent runs…")
        search_e.grid(row=3, column=0, sticky="ew", padx=(0, 8), pady=8)

        def show_run(run: dict) -> None:
            detail.delete("1.0", "end")
            detail.insert(
                "1.0",
                f"Status: {run.get('status')}\n"
                f"Agent: {run.get('agent_name')} ({run.get('agent_role')})\n"
                f"Model: {run.get('model')}\n"
                f"Task: {run.get('task_title')}\n"
                f"Task id: {run.get('task_id')}\n"
                f"Goal id: {run.get('goal_id')}\n"
                f"Started: {run.get('started_at')}\n"
                f"Finished: {run.get('finished_at') or '—'}\n"
                f"Error: {run.get('error') or '—'}\n\n"
                f"======== INPUT ========\n{run.get('input') or ''}\n\n"
                f"======== OUTPUT ========\n{run.get('output') or '(none yet)'}\n",
            )

        def render(runs: list | None = None) -> None:
            for w in list_box.winfo_children():
                w.destroy()
            active = agent_tracker.get_active()
            if active:
                ctk.CTkLabel(
                    list_box,
                    text=f"▶ RUNNING: {active.get('agent_name')} — {active.get('task_title')}",
                    text_color=("#1d4ed8", "#93c5fd"),
                    font=ctk.CTkFont(weight="bold"),
                ).pack(fill="x", pady=4)
                ctk.CTkButton(
                    list_box,
                    text="View active I/O",
                    command=lambda: show_run(active),
                ).pack(fill="x", pady=2)
            for r in runs if runs is not None else agent_tracker.list_recent(40):
                label = f"[{r.get('status')}] {r.get('agent_name')} · {r.get('task_title')}"
                ctk.CTkButton(
                    list_box,
                    text=label,
                    anchor="w",
                    fg_color="transparent",
                    command=lambda run=r: show_run(run),
                ).pack(fill="x", pady=1)

        def do_search() -> None:
            q = search_e.get().strip()
            render(agent_tracker.search_runs(q))

        ctk.CTkButton(root, text="Search runs", command=do_search).grid(
            row=3, column=1, sticky="w", pady=8
        )
        ctk.CTkButton(root, text="Refresh", command=lambda: render()).grid(
            row=4, column=0, sticky="w", pady=4
        )
        render()
        active = agent_tracker.get_active()
        if active:
            show_run(active)
        else:
            rec = agent_tracker.list_recent(1)
            if rec:
                show_run(rec[0])

    def _sanitize_chat_attachments(self) -> None:
        """Drop leftover folders / Desktop\\AI clipboard junk from the composer."""
        try:
            from app.core.services.misc.attachments import sanitize_attachment_paths

            self._chat_attachments = sanitize_attachment_paths(
                list(getattr(self, "_chat_attachments", None) or [])
            )
        except Exception:  # noqa: BLE001
            cleaned: list[str] = []
            for p in list(getattr(self, "_chat_attachments", None) or []):
                try:
                    path = Path(p)
                    if path.is_file() and path.name.lower() not in {"ai", "ai working"}:
                        cleaned.append(str(path))
                except Exception:  # noqa: BLE001
                    continue
            self._chat_attachments = cleaned

    def _chat_clear_attachments(self) -> None:
        self._chat_attachments = []
        self._chat_attached_notes = []
        try:
            self._refresh_note_attach_chips()
        except Exception:  # noqa: BLE001
            pass
        if hasattr(self, "chat_attach_label"):
            n_skills = len(discover_skills())
            self.chat_attach_label.configure(
                text=self._attachments_summary() + f"  |  skills discovered: {n_skills}"
            )
        self.set_status("Attachments cleared")

    def _refresh_chat_org_chart_menu(self) -> None:
        """Populate Chat org-chart picker from saved graphs + LLM-create option."""
        try:
            from app.services import workflow_graph as wfg

            graphs = wfg.list_graphs()
            gmap: dict[str, str] = {}
            labels: list[str] = []
            for g in graphs:
                base = str(g.get("name") or g.get("id") or "Org")[:48]
                lab = base
                n = 2
                while lab in gmap:
                    lab = f"{base} ({n})"
                    n += 1
                gmap[lab] = str(g.get("id") or "")
                labels.append(lab)
            self._chat_org_gmap = gmap
            values = [self._LLM_CREATE_ORG_LABEL] + (labels or ["(no charts — open Org chart)"])
            if hasattr(self, "chat_org_chart_menu"):
                self.chat_org_chart_menu.configure(values=values)
            # Restore selection from chat state
            mode = str(self._chat_state.get("org_mode") or getattr(self, "_chat_org_mode", "fixed"))
            gid = str(self._chat_state.get("org_graph_id") or "")
            if mode == "llm_create" or not labels:
                self.chat_org_chart_var.set(self._LLM_CREATE_ORG_LABEL)
            else:
                label = next((lab for lab, i in gmap.items() if i == gid), None)
                if not label:
                    # fall back to active graph
                    active = wfg.get_active_graph()
                    label = next(
                        (lab for lab, i in gmap.items() if i == active.get("id")),
                        labels[0],
                    )
                self.chat_org_chart_var.set(label)
        except Exception:  # noqa: BLE001
            if hasattr(self, "chat_org_chart_var"):
                self.chat_org_chart_var.set(self._LLM_CREATE_ORG_LABEL)

    def _on_chat_org_chart_change(self) -> None:
        self._sync_chat_org_selection_to_state()
        self._on_chat_flags_save()

    def _sync_chat_org_selection_to_state(self) -> None:
        lab = ""
        try:
            lab = (self.chat_org_chart_var.get() or "").strip()
        except Exception:  # noqa: BLE001
            lab = ""
        if lab == getattr(self, "_LLM_CREATE_ORG_LABEL", "") or lab.startswith("✨"):
            self._chat_state["org_mode"] = "llm_create"
            self._chat_state["org_graph_id"] = ""
            self._chat_org_mode = "llm_create"
        else:
            self._chat_state["org_mode"] = "fixed"
            self._chat_org_mode = "fixed"
            self._chat_state["org_graph_id"] = (getattr(self, "_chat_org_gmap", {}) or {}).get(
                lab, ""
            )

    def _on_chat_flags_save(self) -> None:
        self._chat_state["terminal_enabled"] = bool(self.chat_terminal_var.get())
        self._chat_state["skills_enabled"] = bool(self.chat_skills_var.get())
        self._chat_state["mcp_enabled"] = bool(self.chat_mcp_var.get())
        self._chat_state["safety_mode"] = bool(self.chat_safety_var.get())
        if hasattr(self, "chat_laptop_var"):
            self._chat_state["laptop_enabled"] = bool(self.chat_laptop_var.get())
        if hasattr(self, "chat_workflow_var"):
            self._chat_state["use_workflow_graph"] = bool(self.chat_workflow_var.get())
        if hasattr(self, "chat_mode_var"):
            self._chat_state["mode"] = self.chat_mode_var.get() or "action"
        if hasattr(self, "chat_org_chart_var"):
            self._sync_chat_org_selection_to_state()
        chat_svc.save_chat(self._chat_state)
        self._update_composer_status()
        self._refresh_mode_tasks_chips()
        self._refresh_composer_hint()
        org_lab = ""
        try:
            org_lab = self.chat_org_chart_var.get()
        except Exception:  # noqa: BLE001
            pass
        self.set_status(
            f"mode={self._chat_state.get('mode')} term={self._chat_state['terminal_enabled']} "
            f"laptop={self._chat_state.get('laptop_enabled')} "
            f"workflow={self._chat_state.get('use_workflow_graph', True)} "
            f"org={org_lab[:28] or self._chat_state.get('org_mode')} "
            f"skills={self._chat_state['skills_enabled']} mcp={self._chat_state['mcp_enabled']} "
            f"safety={self._chat_state['safety_mode']}"
        )

    def _sync_model_menus(self, select: str | None = None) -> None:
        """Keep compact + comfortable + composer model dropdowns in sync."""
        vals = list(getattr(self, "_chat_model_choices", None) or []) or ["(fetch models)"]
        for attr in ("chat_model_menu", "chat_model_menu_wide", "chat_model_menu_composer"):
            menu = getattr(self, attr, None)
            if menu is not None:
                try:
                    menu.configure(values=vals)
                except Exception:  # noqa: BLE001
                    pass
        pvals = list(getattr(self, "_chat_provider_choices", None) or [])
        if pvals:
            for attr in ("chat_provider_menu", "chat_provider_menu_wide"):
                menu = getattr(self, attr, None)
                if menu is not None:
                    try:
                        menu.configure(values=pvals)
                    except Exception:  # noqa: BLE001
                        pass
        if select and hasattr(self, "chat_model_var"):
            try:
                prev = bool(getattr(self, "_ignore_model_callback", False))
                self._ignore_model_callback = True
                self.chat_model_var.set(select)
                self._ignore_model_callback = prev
            except Exception:  # noqa: BLE001
                self._ignore_model_callback = False

    def _apply_chat_density_layout(self) -> None:
        """Show/hide comfortable bars; compact keeps one top chrome row."""
        compact = getattr(self, "_chat_density", "compact") == "compact"
        llm = getattr(self, "_chat_llm_bar", None)
        modes = getattr(self, "_chat_modes_bar", None)
        if llm is not None:
            if compact:
                llm.grid_remove()
            else:
                llm.grid()
        if modes is not None:
            if compact:
                modes.grid_remove()
            else:
                modes.grid()
        if hasattr(self, "_density_btn"):
            self._density_btn.configure(
                text="Comfort" if compact else "Compact"
            )

    def _chat_toggle_density(self) -> None:
        cur = getattr(self, "_chat_density", "compact")
        nxt = "comfortable" if cur == "compact" else "compact"
        self._chat_density = nxt
        cfg = storage.load_config()
        cfg["chat_density"] = nxt
        cfg["chat_density_user_set"] = True
        storage.save_config(cfg)
        self.cfg = cfg
        self._apply_chat_density_layout()
        if nxt == "compact":
            self.set_status("Compact chrome — more room for replies")
        else:
            self.set_status("Comfortable — full tool bars (less reply space)")

    def _refresh_mode_tasks_chips(self) -> None:
        from app.ui.themes import style_chrome_button

        if hasattr(self, "_mode_chip_btn") and hasattr(self, "chat_mode_var"):
            m = (self.chat_mode_var.get() or "action").lower()
            try:
                if self._is_simple_ui():
                    from app.ui.components.layman_copy import MODE_TOOLS_ON, MODE_PLAN_ONLY

                    self._mode_chip_btn.configure(
                        text=MODE_TOOLS_ON if m == "action" else MODE_PLAN_ONLY,
                        **style_chrome_button(active=(m == "action")),
                    )
                else:
                    self._mode_chip_btn.configure(
                        text="Act" if m == "action" else "Plan",
                        **style_chrome_button(active=(m == "action")),
                    )
            except Exception:  # noqa: BLE001
                pass
        if hasattr(self, "_tasks_chip_btn") and hasattr(self, "chat_company_approval_var"):
            t = (self.chat_company_approval_var.get() or "manual").lower()
            try:
                self._tasks_chip_btn.configure(text=f"T:{t[:3]}")
            except Exception:  # noqa: BLE001
                pass

    def _chat_toggle_compare_mode(self) -> None:
        """P0.2: toggle Compare / multi-model arena (OWUI-style)."""
        if bool(getattr(self, "_compare_mode", False)):
            self._compare_mode = False
            self._persist_compare_prefs()
            self._refresh_compare_chip()
            self.set_status("Compare off — single model chat", toast=True)
            return
        self._chat_open_compare_picker()

    def _refresh_compare_chip(self) -> None:
        btn = getattr(self, "_compare_chip_btn", None)
        if btn is None:
            return
        on = bool(getattr(self, "_compare_mode", False))
        try:
            from app.ui.themes import style_chrome_button

            kwargs = style_chrome_button(active=on)
            # avoid clobbering geometry keys that CTk may reject mid-flight
            for k in ("height", "width"):
                kwargs.pop(k, None)
            btn.configure(text="Compare●" if on else "Compare", **kwargs)
        except Exception:  # noqa: BLE001
            try:
                btn.configure(text="Compare●" if on else "Compare")
            except Exception:  # noqa: BLE001
                pass

    def _persist_compare_prefs(self) -> None:
        try:
            cfg = storage.load_config()
            cfg["compare_mode"] = bool(getattr(self, "_compare_mode", False))
            cfg["compare_models"] = list(getattr(self, "_compare_models", None) or [])[:3]
            cfg["compare_layout"] = str(getattr(self, "_compare_layout", "stacked") or "stacked")
            storage.save_config(cfg)
            self.cfg = cfg
        except Exception:  # noqa: BLE001
            pass

    def _chat_open_compare_picker(self) -> None:
        """Dialog: pick 2–3 models for parallel compare (text-only / no tools)."""
        from app.ui.themes import style_chrome_button, style_option_menu, UI as _UI
        from app.core.services.chat.multimodel import (
            MAX_COMPARE_MODELS,
            MIN_COMPARE_MODELS,
            normalize_compare_models,
        )

        choices = list(getattr(self, "_chat_model_choices", None) or [])
        if not choices:
            choices = ["(fetch models first)"]
        active = ""
        try:
            active = self.chat_model_var.get() if hasattr(self, "chat_model_var") else ""
        except Exception:  # noqa: BLE001
            active = ""
        preset = list(getattr(self, "_compare_models", None) or [])
        if active and active not in preset:
            preset = [active] + [m for m in preset if m != active]
        while len(preset) < MAX_COMPARE_MODELS:
            for c in choices:
                if c not in preset and not str(c).startswith("("):
                    preset.append(c)
                    break
            else:
                preset.append(choices[0])
                break
        preset = preset[:MAX_COMPARE_MODELS]

        win = ctk.CTkToplevel(self)
        win.title("Compare models")
        win.geometry("460x360")
        win.transient(self)
        win.grab_set()
        ctk.CTkLabel(
            win,
            text="Multi-model compare (arena)",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=_UI["label"],
        ).pack(anchor="w", padx=14, pady=(12, 4))
        ctk.CTkLabel(
            win,
            text=(
                f"Pick {MIN_COMPARE_MODELS}–{MAX_COMPARE_MODELS} models. "
                "One prompt → parallel text replies (no tools). "
                "Use “Use this reply” to keep a winner in the main chat."
            ),
            wraplength=420,
            justify="left",
            text_color=_UI["muted"],
        ).pack(anchor="w", padx=14, pady=(0, 8))

        vars_: list = []
        for i in range(MAX_COMPARE_MODELS):
            row = ctk.CTkFrame(win, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=4)
            ctk.CTkLabel(row, text=f"Model {i + 1}", width=70, anchor="w").pack(side="left")
            v = ctk.StringVar(master=win, value=preset[i] if i < len(preset) else choices[0])
            vars_.append(v)
            ctk.CTkOptionMenu(
                row,
                values=choices,
                variable=v,
                width=300,
                **style_option_menu(),
            ).pack(side="left", padx=4)

        layout_var = ctk.StringVar(
            master=win,
            value=str(getattr(self, "_compare_layout", "stacked") or "stacked"),
        )
        lay = ctk.CTkFrame(win, fg_color="transparent")
        lay.pack(fill="x", padx=14, pady=8)
        ctk.CTkLabel(lay, text="Layout", width=70, anchor="w").pack(side="left")
        ctk.CTkOptionMenu(
            lay,
            values=["stacked", "columns"],
            variable=layout_var,
            width=140,
            **style_option_menu(),
        ).pack(side="left", padx=4)

        def apply_on() -> None:
            picked = normalize_compare_models([v.get() for v in vars_])
            if len(picked) < MIN_COMPARE_MODELS:
                self.set_status(
                    f"Need {MIN_COMPARE_MODELS}+ different models", toast=True
                )
                return
            self._compare_models = picked
            self._compare_layout = layout_var.get() or "stacked"
            self._compare_mode = True
            self._persist_compare_prefs()
            self._refresh_compare_chip()
            try:
                win.destroy()
            except Exception:  # noqa: BLE001
                pass
            self.set_status(
                f"Compare on · {', '.join(picked)} · text-only (no tools)",
                toast=True,
            )

        def cancel() -> None:
            try:
                win.destroy()
            except Exception:  # noqa: BLE001
                pass

        btns = ctk.CTkFrame(win, fg_color="transparent")
        btns.pack(fill="x", padx=14, pady=16)
        ctk.CTkButton(
            btns,
            text="Start Compare",
            width=140,
            command=apply_on,
            **style_chrome_button(primary=True),
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            btns, text="Cancel", width=90, command=cancel, **style_chrome_button()
        ).pack(side="left", padx=4)

    def _chat_send_compare(self, *, text: str, hist: list, user_sys: str = "") -> None:
        """Worker path: parallel LLM calls, soft-degrade, no tools."""
        import threading
        from datetime import datetime, timezone

        from app.core.services.chat.multimodel import (
            make_compare_message,
            run_parallel_completions,
            validate_compare_models,
        )
        from app.core.services.llm.providers import resolve_active_llm

        models = list(getattr(self, "_compare_models", None) or [])
        ok, err_msg, cleaned = validate_compare_models(models)
        if not ok:
            self._compare_mode = False
            self._refresh_compare_chip()
            self._chat_busy = False
            self._chat_busy_started = 0.0
            try:
                if hasattr(self, "chat_send_btn"):
                    self.chat_send_btn.configure(state="normal", text="↑")
                if hasattr(self, "chat_stop_btn"):
                    self.chat_stop_btn.configure(state="disabled")
                if hasattr(self, "chat_status"):
                    self.chat_status.configure(text=err_msg)
            except Exception:  # noqa: BLE001
                pass
            self.set_status(err_msg, toast=True)
            self._chat_open_compare_picker()
            return

        if not user_sys:
            try:
                cfg_now = storage.load_config()
                user_sys = (cfg_now.get("system_prompt") or "").strip()
            except Exception:  # noqa: BLE001
                user_sys = ""

        try:
            self._append_thinking_step(
                f"Compare · {len(cleaned)} models in parallel (no tools)…"
            )
        except Exception:  # noqa: BLE001
            pass
        if hasattr(self, "chat_status"):
            try:
                self.chat_status.configure(text=f"Comparing {len(cleaned)} models…")
            except Exception:  # noqa: BLE001
                pass

        prior = [m for m in hist[:-1] if not m.get("_streaming")]

        def worker() -> None:
            err: str | None = None
            compare_msg = None
            try:
                active = resolve_active_llm()
                api_key = str(active.get("api_key") or "")
                base_url = str(active.get("base_url") or "")
                done_n = {"n": 0}

                def on_done(res) -> None:
                    done_n["n"] += 1
                    label = res.model if getattr(res, "ok", False) else f"{res.model} ✗"

                    def _step(n=done_n["n"], lab=label) -> None:
                        try:
                            self._append_thinking_step(f"Compare {n}/{len(cleaned)} · {lab}")
                        except Exception:  # noqa: BLE001
                            pass

                    self._ui_call(_step)

                sys_for_compare = user_sys or ""
                try:
                    from app.core.services.chat.hash_inject import build_hash_inject_block
                    from app.paths import app_root as _ar

                    _blk, _ = build_hash_inject_block(
                        text or "",
                        cwd=getattr(self, "_chat_terminal_cwd", None) or _ar(),
                    )
                    if _blk:
                        sys_for_compare = (sys_for_compare.rstrip() + "\n\n" + _blk).strip()
                except Exception:  # noqa: BLE001
                    pass
                results = run_parallel_completions(
                    models=cleaned,
                    user_text=text or "(empty)",
                    api_key=api_key,
                    base_url=base_url,
                    system_prompt=sys_for_compare,
                    history=prior,
                    timeout=90.0,
                    on_model_done=on_done,
                )
                compare_msg = make_compare_message(results, user_text=text or "")
                if not any(r.ok for r in results):
                    err = "All compared models failed — see panes for details."
            except Exception as e:  # noqa: BLE001
                err = str(e)

            def finish() -> None:
                self._chat_busy = False
                self._chat_cancel = False
                self._chat_paused = False
                self._chat_busy_started = 0.0
                try:
                    if hasattr(self, "chat_send_btn"):
                        self.chat_send_btn.configure(state="normal", text="↑")
                    if hasattr(self, "chat_stop_btn"):
                        self.chat_stop_btn.configure(
                            state="disabled",
                            text="■ Stop",
                            fg_color=("#d1d5db", "#3f3f46"),
                        )
                except Exception:  # noqa: BLE001
                    pass
                messages = [m for m in (hist or []) if not m.get("_streaming")]
                if compare_msg is not None:
                    messages.append(compare_msg)
                if err and compare_msg is None:
                    messages.append(
                        {
                            "role": "error",
                            "content": err,
                            "at": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                self._chat_state["messages"] = messages
                try:
                    chat_svc.save_chat(self._chat_state)
                except Exception:  # noqa: BLE001
                    pass
                try:
                    self._finish_thinking_bubble(ok=not bool(err and compare_msg is None))
                except Exception:  # noqa: BLE001
                    pass
                try:
                    self._chat_render_transcript()
                except Exception:  # noqa: BLE001
                    pass
                ok_n = 0
                if compare_msg:
                    ok_n = sum(
                        1
                        for r in (compare_msg.get("compare_results") or [])
                        if r.get("ok")
                    )
                if hasattr(self, "chat_status"):
                    try:
                        self.chat_status.configure(
                            text=f"Compare ready · {ok_n}/{len(cleaned)} ok"
                        )
                    except Exception:  # noqa: BLE001
                        pass
                self.set_status(
                    f"Compare done · {ok_n}/{len(cleaned)} models replied (text-only)",
                    toast=True,
                )

            self._ui_call(finish)

        threading.Thread(target=worker, daemon=True, name="chat-compare").start()

    def _render_compare_arena(self, parent: Any, msg: dict) -> None:
        """Stacked or column panes for parallel model replies + Use this."""
        from app.ui.themes import style_chrome_button, UI as _UI

        results = list(msg.get("compare_results") or [])
        layout = str(getattr(self, "_compare_layout", "stacked") or "stacked")
        pad = self._chat_side_pad() if hasattr(self, "_chat_side_pad") else 12
        wrap = ctk.CTkFrame(
            parent,
            fg_color=_UI.get("bubble_assistant", ("#f4f4f5", "#1f1f23")),
            corner_radius=12,
            border_width=1,
            border_color=_UI.get("top_border", ("#6b7280", "#4b5563")),
        )
        wrap.pack(fill="x", padx=pad, pady=(6, 10))
        head = ctk.CTkFrame(wrap, fg_color="transparent")
        head.pack(fill="x", padx=10, pady=(8, 4))
        ctk.CTkLabel(
            head,
            text="⚔ Compare · multi-model (no tools)",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=_UI["label"],
            anchor="w",
        ).pack(side="left")
        ctk.CTkLabel(
            head,
            text=f"{sum(1 for r in results if r.get('ok'))}/{len(results)} ok",
            text_color=_UI["muted"],
            anchor="e",
        ).pack(side="right")

        body = ctk.CTkFrame(wrap, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        if layout == "columns" and len(results) > 1:
            for i in range(len(results)):
                body.grid_columnconfigure(i, weight=1)
            for i, res in enumerate(results):
                col = ctk.CTkFrame(body, fg_color="transparent")
                col.grid(row=0, column=i, sticky="nsew", padx=4, pady=2)
                self._render_compare_pane(col, msg, res, idx=i)
        else:
            for i, res in enumerate(results):
                self._render_compare_pane(body, msg, res, idx=i)

    def _render_compare_pane(
        self, parent: Any, msg: dict, res: dict, *, idx: int
    ) -> None:
        from app.ui.themes import style_chrome_button, UI as _UI

        model = str(res.get("model") or f"model-{idx}")
        ok = bool(res.get("ok"))
        pane = ctk.CTkFrame(
            parent,
            fg_color=_UI.get("composer_input", ("#ffffff", "#1a1a1a")),
            corner_radius=10,
            border_width=1,
            border_color=("#16a34a", "#166534") if ok else ("#dc2626", "#7f1d1d"),
        )
        pane.pack(fill="x", pady=4)
        top = ctk.CTkFrame(pane, fg_color="transparent")
        top.pack(fill="x", padx=8, pady=(6, 2))
        status = "✓" if ok else "✗"
        ms = res.get("elapsed_ms")
        meta = f"{status}  {model}"
        if ms:
            meta += f"  ·  {ms} ms"
        ctk.CTkLabel(
            top,
            text=meta,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=_UI["label"],
            anchor="w",
        ).pack(side="left", fill="x", expand=True)
        if ok:
            ctk.CTkButton(
                top,
                text="Use this reply",
                width=110,
                height=26,
                command=lambda m=msg, r=res: self._chat_use_compare_reply(m, r),
                **style_chrome_button(primary=True),
            ).pack(side="right", padx=2)
        body_txt = (
            str(res.get("content") or "")
            if ok
            else f"Error: {res.get('error') or 'failed'}"
        )
        tb = ctk.CTkTextbox(
            pane,
            height=min(220, 40 + min(12, body_txt.count("\n") + 1) * 16),
            wrap="word",
            font=ctk.CTkFont(size=13),
            fg_color="transparent",
            activate_scrollbars=True,
        )
        tb.pack(fill="x", padx=8, pady=(0, 8))
        tb.insert("1.0", body_txt)
        tb.configure(state="disabled")

    def _chat_use_compare_reply(self, compare_msg: dict, result: dict) -> None:
        """Copy winning model answer into the main chat thread."""
        from datetime import datetime, timezone

        from app.core.services.chat.multimodel import pick_winning_content

        content = pick_winning_content(result).strip()
        if not content:
            self.set_status("Empty reply — nothing to use", toast=True)
            return
        model = str(result.get("model") or "")
        hist = list(self._chat_state.get("messages") or [])
        hist.append(
            {
                "role": "assistant",
                "content": content,
                "agent_name": "Chat",
                "model": model,
                "from_compare": True,
                "at": datetime.now(timezone.utc).isoformat(),
            }
        )
        self._chat_state["messages"] = hist
        if model and hasattr(self, "chat_model_var"):
            try:
                self.chat_model_var.set(model)
                self._on_chat_model_change(model)
            except Exception:  # noqa: BLE001
                pass
        try:
            chat_svc.save_chat(self._chat_state)
        except Exception:  # noqa: BLE001
            pass
        try:
            self._chat_render_transcript()
        except Exception:  # noqa: BLE001
            pass
        self.set_status(f"Using reply from {model or 'model'}", toast=True)

    def _chat_cycle_mode_chip(self) -> None:
        """Click mode chip: plan ↔ action."""
        if not hasattr(self, "chat_mode_var"):
            return
        cur = (self.chat_mode_var.get() or "action").lower()
        nxt = "plan" if cur == "action" else "action"
        self.chat_mode_var.set(nxt)
        if hasattr(self, "chat_mode_seg"):
            try:
                self.chat_mode_seg.set(nxt)
            except Exception:  # noqa: BLE001
                pass
        self._on_chat_flags_save()

    def _chat_cycle_risk_tier(self) -> None:
        """Task #4: cycle Read-only → Ask first → Full access."""
        try:
            from app.services.agent_harness.permissions import cycle_risk_tier

            r = cycle_risk_tier()
        except Exception as e:  # noqa: BLE001
            self.set_status(f"Risk tier failed: {e}", toast=True)
            return
        badge = str(r.get("badge") or "✋ Ask")
        hint = str(r.get("hint") or "")
        try:
            if hasattr(self, "_risk_chip_btn"):
                self._risk_chip_btn.configure(text=badge)
        except Exception:  # noqa: BLE001
            pass
        # Keep tool-approval checkbox in sync if present
        try:
            if hasattr(self, "chat_tool_approval_var"):
                self.chat_tool_approval_var.set(bool(r.get("tool_approval_required")))
        except Exception:  # noqa: BLE001
            pass
        self.cfg = storage.load_config()
        self._update_composer_status()
        self.set_status(f"{badge} — {hint}", toast=True)

    def _chat_cycle_tasks_chip(self) -> None:
        """Click tasks chip: manual ↔ auto company approval."""
        if not hasattr(self, "chat_company_approval_var"):
            return
        cur = (self.chat_company_approval_var.get() or "manual").lower()
        nxt = "auto" if cur == "manual" else "manual"
        self.chat_company_approval_var.set(nxt)
        if hasattr(self, "chat_company_approval_seg"):
            try:
                self.chat_company_approval_seg.set(nxt)
            except Exception:  # noqa: BLE001
                pass
        self._on_chat_company_approval_change(nxt)
        self._refresh_mode_tasks_chips()

    def _chat_open_caps_popover(self) -> None:
        """Popover for capability + approval switches (compact chrome)."""
        from app.ui.themes import style_chrome_button, style_switch, UI as _UI

        win = ctk.CTkToplevel(self)
        win.title("Capabilities")
        win.geometry("400x520")
        win.transient(self)
        win.grab_set()
        ctk.CTkLabel(
            win,
            text="Chat capabilities",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=_UI["label"],
        ).pack(anchor="w", padx=14, pady=(12, 4))
        ctk.CTkLabel(
            win,
            text="These switches control what tools the AI may use in Action mode.",
            text_color=_HC_MUTED,
            wraplength=360,
            justify="left",
        ).pack(anchor="w", padx=14, pady=(0, 6))
        body = ctk.CTkScrollableFrame(win)
        body.pack(fill="both", expand=True, padx=12, pady=6)

        caps_help = (
            ("Terminal", self.chat_terminal_var, "Run shell / PowerShell on this PC"),
            ("Skills", self.chat_skills_var, "Load playbooks (docx, review, …)"),
            ("MCP", self.chat_mcp_var, "External tools from data/mcp.json"),
            ("Laptop GUI", self.chat_laptop_var, "Screenshot, click, type, clipboard"),
            (
                "Org pipeline",
                self.chat_workflow_var,
                "ON = multi-agent org run. Pick chart in modes bar (or ✨ LLM creates org for goal)",
            ),
            ("Safety limits", self.chat_safety_var, "Extra blocks on dangerous commands"),
            ("Tool approval", self.chat_tool_approval_var, "Risky tools wait on Approvals"),
            ("Show tool messages", self.chat_show_tools_var, "Expand tool traces in chat"),
        )
        for text, var, hint in caps_help:
            cmd = (
                self._on_chat_tool_approval_toggle
                if text == "Tool approval"
                else (
                    self._on_show_tools_toggle
                    if text == "Show tool messages"
                    else self._on_chat_flags_save
                )
            )
            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x", padx=4, pady=4)
            ctk.CTkSwitch(row, text=text, variable=var, command=cmd, **style_switch()).pack(
                anchor="w"
            )
            ctk.CTkLabel(
                row, text=hint, text_color=_HC_MUTED, font=ctk.CTkFont(size=11), anchor="w"
            ).pack(anchor="w", padx=8)

        bar = ctk.CTkFrame(win, fg_color="transparent")
        bar.pack(fill="x", padx=12, pady=10)
        ctk.CTkButton(
            bar,
            text="Agent…",
            width=90,
            command=lambda: (win.destroy(), self._chat_pick_agent_dialog()),
            **style_chrome_button(),
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            bar,
            text="Mode help",
            width=90,
            command=lambda: (win.destroy(), self._chat_mode_help()),
            **style_chrome_button(),
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            bar,
            text="Done",
            width=90,
            command=lambda: (self._update_composer_status(), win.destroy()),
            **style_chrome_button(primary=True),
        ).pack(side="right", padx=4)

    def _chat_mode_help(self) -> None:
        messagebox.showinfo(
            "Plan vs Action",
            "Action mode: the AI can run tools (terminal, browser, search, files…).\n\n"
            "Plan mode: the AI only writes a plan — tools do not execute.\n\n"
            "Tip: use Plan first for risky work, then switch to Action.\n"
            "Slash: /plan or /action",
            parent=self,
        )

    def _on_chat_company_approval_change(self, value: str) -> None:
        """Chat bar: company task approval manual|auto (same as CEO page)."""
        from app.services import company_store as company

        mode = "auto" if str(value).lower() == "auto" else "manual"
        company.set_approval_mode(mode)
        if hasattr(self, "chat_company_approval_var"):
            self.chat_company_approval_var.set(mode)
        self._update_composer_status()
        self.set_status(
            f"Company tasks: {mode} approval"
            + (" — new tasks run without CEO click" if mode == "auto" else " — wait for Approvals/CEO")
        )

    def _on_chat_tool_approval_toggle(self) -> None:
        """Chat bar: require tool approval for terminal/GUI/pip/MCP."""
        on = bool(self.chat_tool_approval_var.get()) if hasattr(self, "chat_tool_approval_var") else False
        cfg = storage.load_config()
        cfg["tool_approval_required"] = on
        storage.save_config(cfg)
        self.cfg = cfg
        self._update_composer_status()
        self.set_status(
            "Tool approval ON — risky tools wait on Approvals page"
            if on
            else "Tool approval OFF — tools run immediately"
        )

    def _chat_pick_agent_dialog(self) -> None:
        """Pick which agent persona handles this chat."""
        choices = list(getattr(self, "_chat_agent_choices", None) or ["Default assistant"])
        labels = [c.split("|")[0] if "|" in c else c for c in choices]
        win = ctk.CTkToplevel(self)
        win.title("Select agent")
        win.geometry("360x420")
        win.transient(self)
        win.grab_set()
        ctk.CTkLabel(win, text="Agent for this chat", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=12, pady=(12, 6)
        )
        box = ctk.CTkScrollableFrame(win)
        box.pack(fill="both", expand=True, padx=12, pady=6)

        def pick(label: str) -> None:
            self._on_chat_agent_change(label)
            if hasattr(self, "chat_agent_menu"):
                try:
                    self.chat_agent_menu.set(label)
                except Exception:  # noqa: BLE001
                    pass
            self._chat_agent_display = label
            self._update_composer_status()
            self.set_status(f"Agent: {label}")
            win.destroy()

        for lab in labels:
            ctk.CTkButton(box, text=lab, anchor="w", command=lambda l=lab: pick(l)).pack(
                fill="x", pady=2
            )
        ctk.CTkButton(win, text="Cancel", command=win.destroy).pack(pady=8)

    def _chat_run_via_workflow(self) -> None:
        """Run full org pipeline now (same as Send with Org pipeline ON)."""
        if hasattr(self, "chat_workflow_var"):
            self.chat_workflow_var.set(True)
            self._on_chat_flags_save()
        if hasattr(self, "chat_input"):
            text = self.chat_input.get("1.0", "end").strip()
            if not text:
                for m in reversed(self._chat_state.get("messages") or []):
                    if m.get("role") == "user" and m.get("content"):
                        self.chat_input.delete("1.0", "end")
                        self.chat_input.insert("1.0", str(m["content"])[:2000])
                        break
        self._chat_send()

    def _chat_edit_system_prompt(self) -> None:
        """Visible, editable system prompt + library presets (Task #11)."""
        from app.services import prompt_library as plib
        from app.services import project_store
        from app.ui.themes import style_chrome_button

        cfg = storage.load_config()
        proj = None
        try:
            pid = project_store.get_active_project_id()
            proj = project_store.load_project(pid) if pid else None
        except Exception:  # noqa: BLE001
            proj = None
        current = plib.resolve_effective_system_prompt(
            config_prompt=str(cfg.get("system_prompt") or ""),
            project=proj,
            chat=getattr(self, "_chat_state", None),
        )

        win = ctk.CTkToplevel(self)
        win.title("System prompt & library")
        win.geometry("860x640")
        win.transient(self)

        ctk.CTkLabel(
            win,
            text=(
                "Base system prompt for every message (plus live tools catalog). "
                "Pick a library preset, edit freely, optionally bind to the active project."
            ),
            wraplength=820,
            justify="left",
        ).pack(anchor="w", padx=12, pady=8)

        # Preset library row
        presets = plib.list_presets()
        labels = [f"{p.get('name')} ({p.get('id')})" for p in presets]
        id_by_label = {f"{p.get('name')} ({p.get('id')})": str(p.get("id")) for p in presets}
        active_id = plib.get_active_preset_id()
        active_label = next(
            (lb for lb, i in id_by_label.items() if i == active_id),
            labels[0] if labels else "Default operator (default)",
        )
        preset_var = ctk.StringVar(value=active_label)
        prow = ctk.CTkFrame(win, fg_color="transparent")
        prow.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(prow, text="Prompt library").pack(side="left", padx=(0, 8))
        menu = ctk.CTkOptionMenu(prow, variable=preset_var, values=labels or ["default"], width=280)
        menu.pack(side="left", padx=4)

        def apply_preset() -> None:
            pid2 = id_by_label.get(preset_var.get()) or "default"
            body = plib.resolve_prompt_body(pid2)
            box.delete("1.0", "end")
            box.insert("1.0", body)
            plib.set_active_preset_id(pid2)
            self.set_status(f"Preset: {pid2}", toast=True)

        ctk.CTkButton(
            prow, text="Load preset", width=110, command=apply_preset, **style_chrome_button()
        ).pack(side="left", padx=4)

        box = ctk.CTkTextbox(win, wrap="word")
        box.pack(fill="both", expand=True, padx=12, pady=8)
        box.insert("1.0", current)

        def save() -> None:
            text = box.get("1.0", "end").strip()
            cfg2 = storage.load_config()
            cfg2["system_prompt"] = text
            # Keep preset id if body matches a preset, else custom
            pid2 = id_by_label.get(preset_var.get()) or "default"
            cfg2["active_prompt_preset_id"] = pid2
            storage.save_config(cfg2)
            self.cfg = cfg2
            plib.set_active_preset_id(pid2)
            messagebox.showinfo("Saved", "System prompt saved.", parent=win)
            self.set_status("System prompt updated")

        def save_as_preset() -> None:
            name = simpledialog.askstring("Save preset", "Name for this prompt:", parent=win)
            if not name:
                return
            entry = plib.save_user_preset(name=name, body=box.get("1.0", "end").strip())
            plib.set_active_preset_id(str(entry.get("id")))
            messagebox.showinfo("Saved", f"Preset “{entry.get('name')}” saved to library.", parent=win)
            self.set_status(f"Preset saved: {entry.get('name')}", toast=True)

        def bind_project() -> None:
            pid = project_store.get_active_project_id()
            if not pid:
                messagebox.showinfo(
                    "No project",
                    "Select or create a Project first, then bind this prompt to it.",
                    parent=win,
                )
                return
            preset_id = id_by_label.get(preset_var.get()) or ""
            project_store.set_project_prompt(
                pid,
                system_prompt=box.get("1.0", "end").strip(),
                prompt_preset_id=preset_id,
            )
            messagebox.showinfo("Project", "Prompt bound to the active project.", parent=win)
            self.set_status("Project system prompt updated", toast=True)

        def reset() -> None:
            if not messagebox.askyesno(
                "Reset system prompt",
                "Restore the original default system prompt?",
                parent=win,
            ):
                return
            default = get_default_system_prompt()
            box.delete("1.0", "end")
            box.insert("1.0", default)
            cfg2 = storage.load_config()
            cfg2["system_prompt"] = ""  # empty means default
            cfg2["active_prompt_preset_id"] = "default"
            storage.save_config(cfg2)
            self.cfg = cfg2
            plib.set_active_preset_id("default")
            self.set_status("System prompt reset to default")

        def preview_full() -> None:
            # Show that catalog is appended
            from app.core.services.tools.capability_manual import tool_protocol_manual

            mode = self._chat_state.get("mode") or "action"
            extra = tool_protocol_manual(
                mode=mode, safety_mode=bool(self._chat_state.get("safety_mode"))
            )
            p = ctk.CTkToplevel(win)
            p.title("Full prompt preview (base + operator manual sample)")
            p.geometry("800x560")
            t = ctk.CTkTextbox(p, wrap="word")
            t.pack(fill="both", expand=True, padx=8, pady=8)
            t.insert(
                "1.0",
                box.get("1.0", "end").strip()
                + "\n\n---\n[Live catalog of skills/MCP/tools is also appended each Send]\n---\n\n"
                + extra,
            )
            t.configure(state="disabled")

        bar = ctk.CTkFrame(win, fg_color="transparent")
        bar.pack(fill="x", padx=12, pady=10)
        ctk.CTkButton(bar, text="Save", width=100, command=save, **style_chrome_button(primary=True)).pack(
            side="left", padx=4
        )
        ctk.CTkButton(bar, text="Save as library preset", width=160, command=save_as_preset).pack(
            side="left", padx=4
        )
        ctk.CTkButton(bar, text="Bind to project", width=130, command=bind_project).pack(
            side="left", padx=4
        )
        ctk.CTkButton(bar, text="Reset to default", width=130, command=reset).pack(
            side="left", padx=4
        )
        ctk.CTkButton(bar, text="Preview + manual", width=130, command=preview_full).pack(
            side="left", padx=4
        )
        ctk.CTkButton(bar, text="Close", width=80, command=win.destroy).pack(side="right", padx=4)

    def _chat_skills_manager(self) -> None:
        """Per-skill on/off switches."""
        skills = discover_skills()
        enabled = self._chat_state.get("enabled_skill_names")
        # None means all on
        win = ctk.CTkToplevel(self)
        win.title("Skills on/off")
        win.geometry("640x520")
        win.transient(self)
        ctk.CTkLabel(
            win,
            text=f"Skills discovered: {len(skills)}. Uncheck to disable for the LLM.",
            wraplength=600,
        ).pack(anchor="w", padx=12, pady=8)

        scroll = ctk.CTkScrollableFrame(win, width=600, height=400)
        scroll.pack(fill="both", expand=True, padx=12, pady=8)
        vars_map: dict[str, ctk.BooleanVar] = {}
        for s in skills:
            name = s["name"]
            on = enabled is None or name in (enabled or [])
            var = ctk.BooleanVar(value=on)
            vars_map[name] = var
            row = ctk.CTkFrame(scroll, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkCheckBox(row, text=name, variable=var, width=220).pack(side="left")
            ctk.CTkLabel(
                row,
                text=(s.get("description") or s.get("path") or "")[:80],
                text_color=_HC_MUTED,
                anchor="w",
            ).pack(side="left", fill="x", expand=True)

        def all_on() -> None:
            for v in vars_map.values():
                v.set(True)

        def all_off() -> None:
            for v in vars_map.values():
                v.set(False)

        def save() -> None:
            names = [n for n, v in vars_map.items() if v.get()]
            if len(names) == len(skills):
                self._chat_state["enabled_skill_names"] = None  # all
            else:
                self._chat_state["enabled_skill_names"] = names
            chat_svc.save_chat(self._chat_state)
            self.set_status(f"Skills enabled: {len(names)}/{len(skills)}")
            win.destroy()

        btns = ctk.CTkFrame(win, fg_color="transparent")
        btns.pack(fill="x", padx=12, pady=8)
        ctk.CTkButton(btns, text="All on", width=80, command=all_on).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="All off", width=80, command=all_off).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="Save", width=100, command=save).pack(side="right", padx=4)

    def _chat_tools_list(self) -> None:
        from app.core.services.tools.capability_manual import grok_parity_matrix
        from app.core.services.integrations.mcp_client import get_mcp_hub

        skills = discover_skills()
        enabled = self._chat_state.get("enabled_skill_names")
        if enabled is None:
            en_n = len(skills)
        else:
            en_n = len(enabled)
        try:
            tools = get_mcp_hub().list_tools()
        except Exception as e:  # noqa: BLE001
            tools = [{"qualified": f"error: {e}", "error": True}]

        lines = [
            "=== Built-in tools ===",
            "chat, attachments, terminal (<<<TERMINAL>>>), skills (<<<SKILL>>>), mcp (<<<MCP>>>)",
            f"Mode: {self._chat_state.get('mode', 'action')}",
            f"Skills: {en_n}/{len(skills)} enabled (master={self._chat_state.get('skills_enabled')})",
            f"Terminal master={self._chat_state.get('terminal_enabled')}  MCP master={self._chat_state.get('mcp_enabled')}",
            "",
            "=== MCP tools ===",
        ]
        for t in tools[:60]:
            lines.append(f"- {t.get('qualified') or t.get('server')}")
        lines.append("")
        lines.append(grok_parity_matrix())
        messagebox.showinfo("Tools list", "\n".join(lines)[:4000], parent=self)

    def _chat_marketplace(self) -> None:
        from app.core.services.integrations.mcp_marketplace import enable_marketplace_item, list_marketplace

        items = list_marketplace()
        win = ctk.CTkToplevel(self)
        win.title("MCP Marketplace")
        win.geometry("700x520")
        win.transient(self)
        ctk.CTkLabel(
            win,
            text=(
                "Recommended MCP servers (like VS Code extensions / Open WebUI tools).\n"
                "Enable writes into data/mcp.json. Needs Node.js for npx-based servers.\n"
                "Official catalog: https://github.com/modelcontextprotocol/servers"
            ),
            wraplength=660,
            justify="left",
        ).pack(anchor="w", padx=12, pady=8)

        scroll = ctk.CTkScrollableFrame(win, width=660, height=380)
        scroll.pack(fill="both", expand=True, padx=12, pady=8)

        def make_enabler(iid: str):
            def _go() -> None:
                res = enable_marketplace_item(iid)
                if res.get("ok"):
                    messagebox.showinfo(
                        "Installed",
                        f"Added `{iid}` to {res.get('path')}.\n"
                        "Restart chat / next MCP call reloads servers.\n"
                        "Set API tokens in data/mcp.json if required.",
                        parent=win,
                    )
                else:
                    messagebox.showerror("Error", str(res.get("error")), parent=win)

            return _go

        for it in items:
            row = ctk.CTkFrame(scroll)
            row.pack(fill="x", pady=4, padx=4)
            ctk.CTkLabel(
                row,
                text=f"{it['name']}  [{it['id']}]",
                font=ctk.CTkFont(weight="bold"),
                anchor="w",
            ).pack(anchor="w", padx=8, pady=(6, 0))
            ctk.CTkLabel(
                row,
                text=f"{it['description']}\nRequires: {it['requires']}",
                anchor="w",
                justify="left",
                wraplength=520,
            ).pack(anchor="w", padx=8)
            flag = "Installed in config" if it.get("installed") else "Not in config"
            bar = ctk.CTkFrame(row, fg_color="transparent")
            bar.pack(fill="x", padx=8, pady=6)
            ctk.CTkLabel(bar, text=flag, text_color=_HC_MUTED).pack(side="left")
            ctk.CTkButton(bar, text="Enable", width=80, command=make_enabler(it["id"])).pack(
                side="right"
            )

    def _chat_how_it_works(self) -> None:
        from app.core.services.tools.capability_manual import tool_protocol_manual

        mode = (self._chat_state.get("mode") or "action")
        text = tool_protocol_manual(
            mode=mode, safety_mode=bool(self._chat_state.get("safety_mode"))
        )
        win = ctk.CTkToplevel(self)
        win.title("How the LLM knows what to do")
        win.geometry("760x560")
        win.transient(self)
        box = ctk.CTkTextbox(win, wrap="word")
        box.pack(fill="both", expand=True, padx=10, pady=10)
        box.insert(
            "1.0",
            "This exact manual is injected into the model system prompt every message.\n"
            "OpenAI-compatible: Settings base URL + API key + model.\n\n"
            + text,
        )
        box.configure(state="disabled")

    def _chat_pick_cwd(self) -> None:
        """Pick terminal/agent cwd; optional lock to that folder (Task #15)."""
        from app.ui.themes import style_chrome_button, UI as _UI

        d = filedialog.askdirectory(
            title="Working folder for this chat (tools + sandbox)",
            initialdir=self._chat_terminal_cwd or str(app_root()),
        )
        if not d:
            return
        self._chat_terminal_cwd = d
        lock = False
        try:
            if getattr(self, "_chat_state", None) is not None:
                lock = bool(self._chat_state.get("cwd_lock"))
        except Exception:  # noqa: BLE001
            lock = False
        # Ask whether to lock
        if messagebox.askyesno(
            "Lock folder?",
            f"Working folder:\n{d}\n\n"
            "Lock agent tools to this folder only?\n"
            "(Recommended for safer multi-project work.)\n\n"
            "Yes = lock · No = set cwd but allow other roots if sandbox allows",
            parent=self,
        ):
            lock = True
        else:
            lock = False
        try:
            if getattr(self, "_chat_state", None) is not None:
                self._chat_state["terminal_cwd"] = d
                self._chat_state["cwd_lock"] = lock
                chat_svc.save_chat(self._chat_state)
        except Exception:  # noqa: BLE001
            pass
        try:
            from app.services.agent_harness import sandbox as _sbx

            _sbx.set_chat_context(
                chat_id=str((self._chat_state or {}).get("id") or ""),
                cwd=d,
                cwd_lock=lock,
            )
        except Exception:  # noqa: BLE001
            pass
        self._refresh_cwd_label()
        self.set_status(
            f"cwd set{(' + locked' if lock else '')}: {d}",
            toast=True,
        )

    def _refresh_cwd_label(self) -> None:
        if not hasattr(self, "chat_cwd_label"):
            return
        d = str(self._chat_terminal_cwd or "")
        lock = False
        try:
            if getattr(self, "_chat_state", None) is not None:
                d = str(self._chat_state.get("terminal_cwd") or d)
                lock = bool(self._chat_state.get("cwd_lock"))
                self._chat_terminal_cwd = d
        except Exception:  # noqa: BLE001
            pass
        mark = " 🔒 locked" if lock else ""
        try:
            self.chat_cwd_label.configure(text=f"cwd: {d}{mark}")
        except Exception:  # noqa: BLE001
            pass

    def _chat_toggle_cwd_lock(self) -> None:
        """Toggle cwd lock on current chat without changing folder."""
        if not getattr(self, "_chat_state", None):
            return
        cur = bool(self._chat_state.get("cwd_lock"))
        self._chat_state["cwd_lock"] = not cur
        if not self._chat_state.get("terminal_cwd"):
            self._chat_state["terminal_cwd"] = self._chat_terminal_cwd or str(app_root())
        try:
            chat_svc.save_chat(self._chat_state)
        except Exception:  # noqa: BLE001
            pass
        try:
            from app.services.agent_harness import sandbox as _sbx

            _sbx.set_chat_context(
                chat_id=str(self._chat_state.get("id") or ""),
                cwd=str(self._chat_state.get("terminal_cwd") or ""),
                cwd_lock=bool(self._chat_state.get("cwd_lock")),
            )
        except Exception:  # noqa: BLE001
            pass
        self._refresh_cwd_label()
        self.set_status(
            "Folder locked 🔒" if self._chat_state.get("cwd_lock") else "Folder unlocked",
            toast=True,
        )

    def _chat_system_prompt(self) -> str:
        aid = self._chat_state.get("agent_id") or ""
        if aid:
            agent = storage.get_agent(aid)
            if agent:
                parts = [
                    f"You are {agent.get('name') or 'an agent'}.",
                    f"Role: {agent.get('role') or 'Assistant'}",
                    f"Goal: {agent.get('goal') or 'Help the user.'}",
                ]
                if agent.get("backstory"):
                    parts.append(f"Backstory: {agent['backstory']}")
                parts.append("Reply helpfully in chat form.")
                parts.append(
                    "When the user attaches files, use their contents. "
                    "When terminal access is enabled, use TERMINAL blocks to inspect the system."
                )
                return "\n".join(parts)
        return (
            "You are a helpful assistant inside AI Agent Studio. "
            "Answer clearly and concisely unless the user asks for detail. "
            "Use attached file contents when provided. "
            "When terminal access is enabled, use TERMINAL blocks to run commands."
        )

    def _on_chat_agent_change(self, display: str) -> None:
        aid = ""
        for choice in getattr(self, "_chat_agent_choices", []):
            if choice.split("|")[0] == display and "|" in choice:
                aid = choice.split("|")[-1]
                break
        self._chat_state["agent_id"] = aid
        chat_svc.save_chat(self._chat_state)

    def _resolve_provider_id_from_name(self, name: str) -> str:
        name = (name or "").strip()
        pid = (getattr(self, "_provider_name_to_id", {}) or {}).get(name) or ""
        if pid:
            return pid
        low = name.lower()
        if "openrouter" in low:
            return "openrouter"
        if name == "OpenAI" or low == "openai":
            return "openai"
        if "groq" in low:
            return "groq"
        if "ollama" in low:
            return "ollama"
        if "together" in low:
            return "together"
        return low.replace(" ", "") or "openrouter"

    def _pinned_or_active_model(self, active: dict | None = None) -> str:
        from app.core.services.llm.providers import pinned_or_active_model, resolve_active_llm

        try:
            act = active or resolve_active_llm()
        except Exception:  # noqa: BLE001
            act = active or {}
        cfg = self.cfg or storage.load_config()
        return pinned_or_active_model(
            str((act or {}).get("model") or cfg.get("model") or ""),
            base_url=str((act or {}).get("base_url") or cfg.get("api_base_url") or ""),
            provider_id=str((act or {}).get("provider_id") or ""),
            user_pinned=bool(cfg.get("model_user_pinned")),
        )

    def _keep_model_on_list(self, models: list[str]) -> tuple[list[str], str]:
        """Put the pinned/current model first — never jump to catalog models[0]."""
        pinned = self._pinned_or_active_model()
        keep = ""
        try:
            if hasattr(self, "chat_model_var"):
                keep = (self.chat_model_var.get() or "").strip()
        except Exception:  # noqa: BLE001
            keep = ""
        clean = [m for m in models if m and not str(m).startswith("(")]
        sel = ""
        if pinned:
            sel = pinned
        elif keep and keep in clean:
            sel = keep
        elif clean:
            sel = clean[0]
        if sel:
            models = [sel] + [m for m in models if m != sel]
        return models, sel

    def _on_chat_provider_change(self, name: str) -> None:  # noqa: ARG002 — CTk callback
        from app.services import providers as prov

        pid = self._resolve_provider_id_from_name(name)
        prov.set_active(pid)
        p = prov.get_provider(pid) or {}
        models = list(p.get("models_cache") or []) or ["(fetch models)"]
        self._chat_all_models = list(models)
        models, sel = self._keep_model_on_list(models)
        self._chat_model_choices = models[:120]
        self._ignore_model_callback = True
        self._sync_model_menus(select=sel or None)
        if sel and not str(sel).startswith("("):
            prov.set_active(pid, model=sel)
        self.after(400, lambda: setattr(self, "_ignore_model_callback", False))
        if hasattr(self, "chat_model_search_var"):
            self.chat_model_search_var.set("")
        self._update_composer_status()
        try:
            self._refresh_context_chip()
        except Exception:  # noqa: BLE001
            pass
        self.set_status(f"Provider: {name} ({pid})  ·  ↻ models then Search models…")

    def _on_chat_model_change(self, model: str) -> None:
        from app.services import providers as prov
        from app.core.services.llm.providers import NVIDIA_NEMOTRON_550, is_nvidia_integrate

        if getattr(self, "_ignore_model_callback", False):
            return
        if model == "(fetch models)":
            self._chat_fetch_models()
            return
        pid = "openrouter"
        if hasattr(self, "chat_provider_var"):
            pid = self._resolve_provider_id_from_name(self.chat_provider_var.get())
        else:
            active = prov.resolve_active_llm()
            pid = active.get("provider_id") or "openrouter"
        p = prov.get_provider(pid) or {}
        base = str(p.get("base_url") or "")
        cfg = storage.load_config()
        if is_nvidia_integrate(base, pid):
            cfg["model_user_pinned"] = bool(model) and model != NVIDIA_NEMOTRON_550
        cfg["model"] = model
        storage.save_config(cfg)
        self.cfg = cfg
        prov.set_active(pid, model=model)
        self._update_composer_status()
        try:
            self._refresh_context_chip()
        except Exception:  # noqa: BLE001
            pass
        self.set_status(f"Model: {model}")

    def _chat_fetch_models(self) -> None:
        from app.services import providers as prov

        try:
            if hasattr(self, "chat_provider_var"):
                pid = self._resolve_provider_id_from_name(self.chat_provider_var.get())
            else:
                active = prov.resolve_active_llm()
                pid = active.get("provider_id") or "openrouter"
            prov.set_active(pid)
            models = prov.fetch_models(pid, force=True)
            if not models:
                models = ["(no models — add API key in Settings)"]
            # Keep full list for search (not just 80)
            self._chat_all_models = list(models)
            models, sel = self._keep_model_on_list(models)
            self._chat_model_choices = models[:120]
            self._ignore_model_callback = True
            self._sync_model_menus(select=sel or None)
            if sel and not str(sel).startswith("("):
                prov.set_active(pid, model=sel)
            self.after(400, lambda: setattr(self, "_ignore_model_callback", False))
            if hasattr(self, "chat_model_search_var"):
                self.chat_model_search_var.set("")
            self._update_composer_status()
            self.set_status(f"Fetched {len(models)} models for {pid} — use Search models box to filter")
            messagebox.showinfo(
                "Models",
                f"Provider: {pid}\nFetched {len(models)} models.\n\n"
                "Type in “Search models…” to filter, or click Find for a full list.",
                parent=self,
            )
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(
                "Fetch models",
                f"{e}\n\nTip: Settings → Providers → select OpenRouter → add API key.",
                parent=self,
            )

    def _chat_all_model_list(self) -> list[str]:
        full = list(getattr(self, "_chat_all_models", None) or [])
        if full:
            return full
        return list(getattr(self, "_chat_model_choices", None) or [])

    def _chat_filter_models(self) -> None:
        """Filter model dropdown by search box text."""
        q = ""
        if hasattr(self, "chat_model_search_var"):
            q = (self.chat_model_search_var.get() or "").strip().lower()
        all_m = self._chat_all_model_list()
        if not all_m:
            self.set_status("No models loaded — click ↻ models first")
            return
        if not q:
            filtered = all_m[:120]
        else:
            filtered = [m for m in all_m if q in m.lower()]
            if not filtered:
                filtered = [f"(no match for “{q}”)"]
        self._chat_model_choices = filtered[:120]
        sel = None
        if filtered and not str(filtered[0]).startswith("(no match"):
            sel = filtered[0]
        self._sync_model_menus(select=sel)
        if sel:
            self._on_chat_model_change(sel)
        self.set_status(f"Models: {len(filtered)} match “{q or 'all'}”")

    def _chat_filter_models_live(self) -> None:
        # Debounce-ish: only filter when query has 2+ chars or empty
        q = ""
        if hasattr(self, "chat_model_search_var"):
            q = (self.chat_model_search_var.get() or "").strip()
        if len(q) == 1:
            return
        self._chat_filter_models()

    def _chat_open_model_picker(self) -> None:
        """Full searchable model list (better than OptionMenu for 100+ OpenRouter models)."""
        all_m = self._chat_all_model_list()
        if not all_m or (len(all_m) == 1 and str(all_m[0]).startswith("(")):
            messagebox.showinfo(
                "Models",
                "Load models first: select Provider (e.g. OpenRouter) → ↻ models",
                parent=self,
            )
            return
        win = ctk.CTkToplevel(self)
        win.title("Search & select model")
        win.geometry("560x520")
        win.transient(self)
        win.grab_set()
        from app.ui.themes import UI

        ctk.CTkLabel(
            win,
            text="Type to filter · double-click or Select to apply",
            text_color=UI["muted"],
        ).pack(anchor="w", padx=14, pady=(12, 4))
        qvar = ctk.StringVar(value=self.chat_model_search_var.get() if hasattr(self, "chat_model_search_var") else "")
        entry = ctk.CTkEntry(win, textvariable=qvar, placeholder_text="claude, gpt-4o, llama, deepseek…", width=500)
        entry.pack(padx=14, pady=6, fill="x")
        entry.focus_set()
        list_box = ctk.CTkScrollableFrame(win, fg_color=UI["chat_bg"])
        list_box.pack(fill="both", expand=True, padx=14, pady=8)
        state: dict[str, str] = {"sel": self.chat_model_var.get() if hasattr(self, "chat_model_var") else ""}

        def render(_q: str | None = None) -> None:
            for w in list_box.winfo_children():
                w.destroy()
            qq = (qvar.get() or "").strip().lower()
            items = [m for m in all_m if not qq or qq in m.lower()]
            if not items:
                ctk.CTkLabel(list_box, text="No matches", text_color=UI["muted"]).pack(pady=12)
                return
            for m in items[:300]:
                is_sel = m == state["sel"]
                b = ctk.CTkButton(
                    list_box,
                    text=m,
                    anchor="w",
                    height=28,
                    fg_color=UI["sidebar_active"] if is_sel else "transparent",
                    text_color=UI["sidebar_active_text"] if is_sel else UI["label"],
                    hover_color=UI["sidebar_hover"],
                    command=lambda name=m: pick(name),
                )
                b.pack(fill="x", pady=1)
                b.bind("<Double-Button-1>", lambda _e, name=m: apply(name))

        def pick(name: str) -> None:
            state["sel"] = name
            render()

        def apply(name: str | None = None) -> None:
            name = name or state.get("sel") or ""
            qq = (qvar.get() or "").strip().lower()
            matches = [m for m in all_m if not qq or qq in m.lower()]
            # Filtered unique hit wins — Select used to keep the old model (yi-large)
            if matches and name not in matches:
                name = matches[0]
            elif not name and matches:
                name = matches[0]
            if not name or name.startswith("("):
                return
            vals = list(self._chat_model_choices or [])
            if name not in vals:
                vals = [name] + vals
                self._chat_model_choices = vals[:120]
            self._sync_model_menus(select=name)
            self._on_chat_model_change(name)
            if hasattr(self, "chat_model_search_var"):
                self.chat_model_search_var.set("")
            win.destroy()
            self.set_status(f"Model: {name}")

        qvar.trace_add("write", lambda *_a: render())
        entry.bind("<Return>", lambda _e: apply(state.get("sel")))
        bar = ctk.CTkFrame(win, fg_color="transparent")
        bar.pack(fill="x", padx=14, pady=10)
        ctk.CTkButton(bar, text="Select", width=100, command=lambda: apply()).pack(side="left", padx=4)
        ctk.CTkButton(bar, text="Cancel", width=100, command=win.destroy).pack(side="left", padx=4)
        render()

    def _on_chat_switch(self, display: str) -> None:
        for choice in getattr(self, "_chat_switch_choices", []):
            if choice.split("|")[0] == display and "|" in choice:
                cid = choice.split("|")[-1]
                chat_store.set_active_chat_id(cid)
                self._chat_state = self._load_active_chat()
                self.show_page("Chat")
                return

    def _chat_new_session(self) -> None:
        self._open_new_chat(source="new")

    def _open_new_chat(
        self,
        *,
        folder_id: str = "",
        project_id: str | None = None,
        source: str = "new",
    ) -> None:
        """
        Create and open a full Chat session (composer, tools, rail, empty state).
        Used by ＋ New, Ctrl+N, and folder ＋ so folder chats are not half-initialized.
        """
        from app.services import project_store

        try:
            # Clear stuck send state from previous chat
            self._chat_busy = False
            self._chat_cancel = False
            self._chat_paused = False
            self._chat_attachments = []
            self._pending_images = []
            self._pending_videos = []
            self._stream_bubble_label = None
            self._thinking_row = None
            self._thinking_box = None
            self._thinking_steps = []
        except Exception:  # noqa: BLE001
            pass

        fid = str(folder_id or "").strip()
        # Expand target folder so the new chat is visible in the rail
        if fid:
            try:
                fo = chat_store.get_folder(fid)
                if fo and bool(fo.get("collapsed")):
                    chat_store.set_folder_collapsed(fid, False)
            except Exception:  # noqa: BLE001
                pass

        try:
            pid = project_id
            if pid is None:
                pid = project_store.get_active_project_id() or ""
            c = chat_store.new_chat(
                "New chat",
                project_id=str(pid or ""),
                folder_id=fid,
            )
            cid = str(c.get("id") or "")
            if not cid:
                raise RuntimeError("new chat missing id")
            chat_store.set_active_chat_id(cid)
            # Load via chat service (applies mode/tool defaults)
            self._chat_state = chat_svc.load_chat(cid)
            # Ensure folder_id survived defaults merge
            if fid and not str(self._chat_state.get("folder_id") or "").strip():
                self._chat_state["folder_id"] = fid
                try:
                    chat_svc.save_chat(self._chat_state)
                except Exception:  # noqa: BLE001
                    pass
            # Tabs strip
            try:
                tabs = list(getattr(self, "_open_chat_tabs", []) or [])
                tabs = [t for t in tabs if str(t) != cid]
                tabs.insert(0, cid)
                self._open_chat_tabs = tabs[:6]
            except Exception:  # noqa: BLE001
                self._open_chat_tabs = [cid]
            try:
                self._chat_rail_selected = set()
            except Exception:  # noqa: BLE001
                pass

            # Always full Chat page rebuild so composer/tools/empty-state appear
            self.show_page("Chat")

            # Focus composer for typing
            def _focus() -> None:
                try:
                    if hasattr(self, "chat_input") and self.chat_input.winfo_exists():
                        self.chat_input.focus_set()
                        if hasattr(self, "_composer_maybe_placeholder"):
                            self._composer_maybe_placeholder()
                except Exception:  # noqa: BLE001
                    pass

            self.after(80, _focus)

            where = ""
            if fid:
                fo2 = chat_store.get_folder(fid)
                where = f" in “{(fo2 or {}).get('name') or 'folder'}”"
            self.set_status(f"New chat{where}", toast=True)
        except Exception as e:  # noqa: BLE001
            self.set_status(f"New chat failed: {e}")

    def _chat_enter_send(self, event: Any) -> str | None:
        """Enter sends; Shift+Enter newline (ChatGPT-like)."""
        if event.state & 0x0001:  # Shift
            return None
        self._chat_send()
        return "break"

    def _render_message_media(self, bubble: ctk.CTkFrame, m: dict[str, Any]) -> None:
        """Show images and videos inside the chat bubble (not path-only)."""
        import os
        import subprocess
        import webbrowser

        def open_path(p: str) -> None:
            try:
                if str(p).lower().startswith("http://") or str(p).lower().startswith("https://"):
                    webbrowser.open(p)
                    return
                os.startfile(p)  # type: ignore[attr-defined]
            except Exception:
                try:
                    subprocess.Popen(["cmd", "/c", "start", "", p], shell=True)
                except Exception as e:  # noqa: BLE001
                    messagebox.showerror("Open media", str(e), parent=self)

        # Collect images from message + tool screenshot roles
        images = list(m.get("images") or [])
        videos = list(m.get("videos") or [])
        failed_images = list(m.get("failed_images") or [])
        failed_videos = list(m.get("failed_videos") or [])
        # scrape content for leftover media paths if needed
        try:
            from app.core.services.chat.media_chat import extract_media_from_text, stage_many_with_failures
            from app.core.services.chat.chat_store import get_active_chat_id

            imgs2, vids2, cleaned = extract_media_from_text(m.get("content") or "")
            cid = get_active_chat_id() or "default"
            if imgs2 or vids2:
                ok_i, fail_i = stage_many_with_failures(imgs2, cid)
                ok_v, fail_v = stage_many_with_failures(vids2, cid)
                images = list(dict.fromkeys(images + ok_i))
                videos = list(dict.fromkeys(videos + ok_v))
                failed_images = list(dict.fromkeys(failed_images + fail_i))
                failed_videos = list(dict.fromkeys(failed_videos + fail_v))
                # Always strip raw IMAGE/VIDEO tags when re-rendering (never show markers)
                if imgs2 or vids2:
                    m["content"] = cleaned
                    m["images"] = images
                    m["videos"] = videos
                    m["failed_images"] = failed_images
                    m["failed_videos"] = failed_videos
        except Exception:  # noqa: BLE001
            pass

        for ip in images:
            frame = ctk.CTkFrame(bubble, fg_color=("gray90", "gray20"), corner_radius=8)
            frame.pack(fill="x", padx=10, pady=6)
            try:
                from PIL import Image  # type: ignore

                im = Image.open(ip)
                # Grok-style large inline image
                max_w, max_h = 560, 420
                im.thumbnail((max_w, max_h))
                cimg = ctk.CTkImage(light_image=im, dark_image=im, size=im.size)
                lbl = ctk.CTkLabel(frame, image=cimg, text="", cursor="hand2")
                lbl.image = cimg  # type: ignore[attr-defined]
                lbl.pack(padx=8, pady=8)
                lbl.bind("<Button-1>", lambda _e, p=ip: self._open_image_lightbox(p))
            except Exception:
                ctk.CTkLabel(frame, text=f"[image failed to load]\n{ip}", wraplength=480).pack(
                    padx=8, pady=4
                )
            bar = ctk.CTkFrame(frame, fg_color="transparent")
            bar.pack(fill="x", padx=8, pady=(0, 8))
            ctk.CTkLabel(bar, text=Path(ip).name, text_color=_HC_MUTED).pack(side="left")
            ctk.CTkButton(
                bar, text="Expand", width=80, command=lambda p=ip: self._open_image_lightbox(p)
            ).pack(side="right", padx=4)
            ctk.CTkButton(bar, text="Open file", width=90, command=lambda p=ip: open_path(p)).pack(
                side="right", padx=4
            )

        # Remote URLs that could not be downloaded — show open-in-browser cards
        for url in failed_images:
            frame = ctk.CTkFrame(bubble, fg_color=("gray90", "gray20"), corner_radius=8)
            frame.pack(fill="x", padx=10, pady=6)
            ctk.CTkLabel(
                frame,
                text="🖼 Image (download blocked or file missing)",
                font=ctk.CTkFont(weight="bold"),
            ).pack(anchor="w", padx=10, pady=(8, 2))
            ctk.CTkLabel(
                frame, text=url, text_color=_HC_MUTED, wraplength=480, justify="left"
            ).pack(anchor="w", padx=10, pady=2)
            bar = ctk.CTkFrame(frame, fg_color="transparent")
            bar.pack(fill="x", padx=8, pady=8)
            ctk.CTkButton(
                bar, text="Open in browser", width=130, command=lambda u=url: open_path(u)
            ).pack(side="left", padx=4)

        for vp in videos:
            frame = ctk.CTkFrame(bubble, fg_color=("gray90", "gray20"), corner_radius=8)
            frame.pack(fill="x", padx=10, pady=6)
            # thumbnail if possible
            try:
                from app.core.services.chat.media_chat import video_thumbnail

                thumb = video_thumbnail(vp)
                if thumb:
                    from PIL import Image  # type: ignore

                    im = Image.open(thumb)
                    im.thumbnail((480, 320))
                    cimg = ctk.CTkImage(light_image=im, dark_image=im, size=im.size)
                    lbl = ctk.CTkLabel(frame, image=cimg, text="")
                    lbl.image = cimg  # type: ignore[attr-defined]
                    lbl.pack(padx=8, pady=8)
            except Exception:
                pass
            ctk.CTkLabel(
                frame,
                text=f"🎬 {Path(vp).name}",
                font=ctk.CTkFont(weight="bold"),
            ).pack(anchor="w", padx=10)
            ctk.CTkLabel(frame, text=vp, text_color=_HC_MUTED, wraplength=480, justify="left").pack(
                anchor="w", padx=10, pady=2
            )
            bar = ctk.CTkFrame(frame, fg_color="transparent")
            bar.pack(fill="x", padx=8, pady=8)
            ctk.CTkButton(
                bar,
                text="▶ Play video in chat (system player)",
                width=220,
                command=lambda p=vp: open_path(p),
            ).pack(side="left", padx=4)

        for url in failed_videos:
            frame = ctk.CTkFrame(bubble, fg_color=("gray90", "gray20"), corner_radius=8)
            frame.pack(fill="x", padx=10, pady=6)
            ctk.CTkLabel(frame, text="🎬 Video URL (open in browser)", font=ctk.CTkFont(weight="bold")).pack(
                anchor="w", padx=10, pady=(8, 2)
            )
            ctk.CTkLabel(frame, text=url, text_color=_HC_MUTED, wraplength=480, justify="left").pack(
                anchor="w", padx=10, pady=2
            )
            ctk.CTkButton(
                frame, text="Open in browser", width=130, command=lambda u=url: open_path(u)
            ).pack(anchor="w", padx=10, pady=8)

    def _chat_column_width(self) -> int:
        """Actual pixels available for a message (not the whole window)."""
        w = 0
        try:
            if self._chat_scroll_alive():
                w = int(self.chat_scroll.winfo_width() or 0)
                if w < 80:
                    c = self._chat_canvas()
                    if c is not None:
                        w = int(c.winfo_width() or 0)
        except Exception:  # noqa: BLE001
            w = 0
        if w < 80:
            try:
                mid = getattr(self, "_chat_mid", None)
                if mid is not None:
                    live = 340 if bool(getattr(self, "_live_panel_visible", False)) else 0
                    w = int(mid.winfo_width() or 0) - live - 16
            except Exception:  # noqa: BLE001
                w = 0
        return max(280, w - 16)

    def _chat_side_pad(self) -> int:
        return 10

    def _fit_chat_scroll_inner(self) -> None:
        """Stretch CTkScrollableFrame inner width so bubbles don't collapse to 2-letter wrap."""
        try:
            if not self._chat_scroll_alive():
                return
            canvas = self._chat_canvas()
            if canvas is None:
                return
            cw = int(canvas.winfo_width() or 0)
            if cw < 80:
                return
            win_id = getattr(self.chat_scroll, "_create_window_id", None) or getattr(
                self.chat_scroll, "_window_id", None
            )
            if win_id is not None:
                canvas.itemconfigure(win_id, width=cw)
            inner = getattr(self.chat_scroll, "_scrollable_frame", None)
            if inner is None:
                inner = self.chat_scroll
            try:
                inner.configure(width=max(260, cw - 4))
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            pass

    def _thinking_attached_to(self, messages: list[dict[str, Any]], idx: int) -> dict[str, Any] | None:
        if idx < 0 or idx >= len(messages):
            return None
        own = messages[idx].get("_thinking") or messages[idx].get("thinking")
        if isinstance(own, dict) and (own.get("steps") or own.get("content")):
            return own
        for i in range(idx - 1, -1, -1):
            r = str(messages[i].get("role") or "")
            if r == "thinking":
                return messages[i]
            if r in ("user", "assistant"):
                break
        return None

    def _render_in_bubble_thinking(self, parent: Any, think: dict[str, Any]) -> None:
        """Expand/collapse thinking inside this reply (not a side window)."""
        from app.ui.themes import UI as _UI, style_chrome_button

        steps = list(think.get("steps") or [])
        if not steps:
            raw = str(think.get("content") or "").strip()
            steps = [ln.lstrip("• ").strip() for ln in raw.splitlines() if ln.strip()]
        bits = [self._thinking_step_bits(s, i) for i, s in enumerate(steps)]
        bits = [b for b in bits if any(b)]
        if not bits:
            return
        n = len(bits)
        state = {"open": False}
        wrap = ctk.CTkFrame(
            parent,
            fg_color=("#eef2ff", "#1a1a2e"),
            corner_radius=10,
            border_width=0,
        )
        wrap.pack(fill="x", padx=8, pady=(4, 2))
        last_cur = bits[-1][1] or bits[-1][0]
        preview = last_cur if len(last_cur) <= 64 else last_cur[:61] + "…"
        btn = ctk.CTkButton(
            wrap,
            text=f"▶  💭 Thinking · {n} step(s)   {preview}",
            anchor="w",
            height=28,
            **style_chrome_button(),
        )
        btn.pack(fill="x", padx=4, pady=4)
        body = ctk.CTkFrame(wrap, fg_color="transparent")

        def toggle() -> None:
            state["open"] = not state["open"]
            try:
                btn.configure(
                    text=f"{'▼' if state['open'] else '▶'}  💭 Thinking · {n} step(s)"
                    + ("" if state["open"] else f"   {preview}")
                )
                if state["open"]:
                    body.pack(fill="x", padx=8, pady=(0, 8))
                    try:
                        self._bind_wheel_tree(wrap)
                    except Exception:  # noqa: BLE001
                        pass
                else:
                    body.pack_forget()
                self._refresh_chat_scrollregion()
            except Exception:  # noqa: BLE001
                pass

        btn.configure(command=toggle)
        for i, (title, current, raw) in enumerate(bits, 1):
            ctk.CTkLabel(
                body,
                text=f"{i}. {title}",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=_UI.get("label", ("#111", "#eee")),
                anchor="w",
                justify="left",
                wraplength=640,
            ).pack(fill="x", pady=(4, 0))
            show = current or title
            extra = raw if raw and raw not in (current, title) else ""
            ctk.CTkLabel(
                body,
                text=(show + (("\n" + extra[:800]) if extra else "")),
                font=ctk.CTkFont(size=12),
                text_color=_UI.get("muted", ("#6b7280", "#a1a1aa")),
                anchor="w",
                justify="left",
                wraplength=640,
            ).pack(fill="x", pady=(0, 4))
        try:
            self._bind_wheel_tree(wrap)
        except Exception:  # noqa: BLE001
            pass

    def _render_grok_chat_bubble(
        self,
        parent: Any,
        m: dict[str, Any],
        *,
        kind: str,
        content: str,
        full_idx: int,
        thinking: dict[str, Any] | None = None,
    ) -> None:
        """Grok-style message: centered column, soft user pill, flat assistant prose."""
        from app.ui.themes import UI as _UI, style_chrome_button

        bg, fg = _BUBBLE.get(kind, _BUBBLE["assistant"])
        accent = _BUBBLE_ACCENT.get(kind, _BUBBLE_ACCENT["assistant"])
        role = str(m.get("role") or kind)
        side_pad = self._chat_side_pad()
        density = getattr(self, "_chat_density", "compact") or "compact"
        vpad = 8 if density == "compact" else 14

        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=side_pad, pady=vpad)

        is_user = kind == "user"
        anchor = "e" if is_user else "w"

        # Outer flex: avatar + bubble
        line = ctk.CTkFrame(row, fg_color="transparent")
        line.pack(anchor=anchor, fill="x")

        def _avatar(letter: str, color: Any, *, side: str) -> None:
            # Soft circle (Grok uses brand mark — we use G / Y)
            wrap = ctk.CTkFrame(line, fg_color="transparent", width=36, height=36)
            wrap.pack(side=side, padx=(0, 12) if side == "left" else (12, 0), pady=2)
            wrap.pack_propagate(False)
            av = ctk.CTkFrame(
                wrap,
                width=32,
                height=32,
                corner_radius=16,
                fg_color=color,
                border_width=0,
            )
            av.place(relx=0.5, rely=0.5, anchor="center")
            ctk.CTkLabel(
                av,
                text=(letter[:1] or "?").upper(),
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=("#0a0f1a", "#0a0f1a") if kind == "assistant" else ("#ffffff", "#0a0f1a"),
            ).place(relx=0.5, rely=0.5, anchor="center")

        if not is_user:
            letter = "✦" if kind == "assistant" else ("!" if kind == "error" else "i")
            if kind == "assistant":
                letter = "G"
            _avatar(letter, accent, side="left")

        # Constrain bubble width — user pills hug content-ish; assistant fills column
        outer = ctk.CTkFrame(line, fg_color="transparent")
        if is_user:
            outer.pack(side="right", fill="x", expand=True, padx=(80, 0))
        else:
            outer.pack(side="left", fill="x", expand=True, padx=(0, 40))

        # Readable cards — flat-on-canvas + no width made 2-letter wrap
        bubble = ctk.CTkFrame(
            outer,
            fg_color=bg,
            corner_radius=16 if is_user else 14,
            border_width=1,
            border_color=("#93c5fd", "#1e3a8a") if is_user else ("#e5e7eb", "#3f3f46"),
        )
        bubble.pack(anchor=anchor, fill="x")

        if is_user:
            _avatar("Y", accent, side="right")

        agent_who = m.get("agent_name") or m.get("agent") or m.get("source_agent") or ""
        model_who = m.get("model") or ""
        ts = self._format_msg_time(m.get("at") or m.get("timestamp") or "")
        usage_bits = []
        if m.get("prompt_tokens") or m.get("completion_tokens"):
            usage_bits.append(
                f"{m.get('prompt_tokens') or '?'}→{m.get('completion_tokens') or '?'} tok"
            )

        # Meta line — subtle, Grok-style (not heavy bold header bar)
        if kind == "tool":
            label = str(role).upper()
            if agent_who:
                label = f"{label} · {agent_who}"
        elif is_user:
            label = "You"
        elif kind == "system":
            label = "System"
        elif agent_who:
            label = f"{agent_who}" + (f" · {model_who}" if model_who else "")
        else:
            label = "Grok" if kind == "assistant" else "Assistant"
            if model_who and kind == "assistant":
                # Prefer short model tail
                short_m = model_who.split("/")[-1]
                if len(short_m) > 28:
                    short_m = short_m[:26] + "…"
                label = f"Assistant · {short_m}"
        if m.get("_streaming"):
            label = f"{label} · typing…"
        meta_right = "  ·  ".join([x for x in (ts, usage_bits[0] if usage_bits else "") if x])

        head = ctk.CTkFrame(bubble, fg_color="transparent")
        head.pack(fill="x", padx=16 if is_user else 4, pady=(10 if is_user else 2, 0))
        ctk.CTkLabel(
            head,
            text=label,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=("#374151", "#d4d4d8") if kind == "assistant" else fg,
            anchor="w",
        ).pack(side="left")
        if meta_right:
            ctk.CTkLabel(
                head,
                text=meta_right,
                font=ctk.CTkFont(size=11),
                text_color=_UI["muted"],
                anchor="e",
            ).pack(side="right")

        if kind == "assistant" and thinking:
            try:
                self._render_in_bubble_thinking(bubble, thinking)
            except Exception:  # noqa: BLE001
                pass

        col_w = self._chat_column_width()
        wrap = max(240, col_w - 96)
        body_pad_x = 14
        if content:
            long_reply = len(content) > 900 or content.count("\n") > 16
            if kind == "tool" or long_reply:
                self._make_selectable_text(
                    bubble,
                    content,
                    text_color=fg,
                    wrap=wrap,
                    font_size=13 if kind == "tool" else 15,
                    mono=kind == "tool",
                    padx=body_pad_x,
                    pady=6,
                    max_height=self._reply_view_cap(),
                    linkify=True,
                )
            elif kind in ("assistant", "system", "error"):
                self._render_rich_message_body(
                    bubble, content, text_color=fg, wrap=wrap, padx=body_pad_x
                )
            else:
                self._make_selectable_text(
                    bubble,
                    content,
                    text_color=fg,
                    wrap=wrap,
                    font_size=15,
                    padx=body_pad_x,
                    pady=8,
                    linkify=True,
                )

        self._render_message_media(bubble, m)

        # Action strip — very quiet ghost chips (Batch 3: secondary, not primary)
        if kind in ("assistant", "user", "error") and (content or m.get("images")):
            actions = ctk.CTkFrame(bubble, fg_color="transparent")
            actions.pack(fill="x", padx=body_pad_x, pady=(2, 8 if is_user else 4))
            ghost = {
                "fg_color": "transparent",
                "hover_color": ("#f4f4f5", "#1f1f1f"),
                "text_color": ("#64748b", "#71717a"),
                "border_width": 0,
                "corner_radius": 6,
            }
            for lab, w, cmd in (
                ("Copy", 44, lambda t=content: self._copy_text(t)),
            ):
                ctk.CTkButton(
                    actions,
                    text=lab,
                    width=w,
                    height=22,
                    font=ctk.CTkFont(size=11),
                    command=cmd,
                    **ghost,
                ).pack(side="left", padx=(0, 1))
            if kind in ("assistant", "user"):
                ctk.CTkButton(
                    actions,
                    text="Edit",
                    width=40,
                    height=22,
                    font=ctk.CTkFont(size=11),
                    command=lambda i=full_idx: self._chat_edit_message(i),
                    **ghost,
                ).pack(side="left", padx=1)
            if kind == "assistant" and not m.get("_streaming"):
                ctk.CTkButton(
                    actions,
                    text="Reply",
                    width=42,
                    height=22,
                    font=ctk.CTkFont(size=11),
                    command=lambda t=content: self._chat_reply_to(t),
                    **ghost,
                ).pack(side="left", padx=1)
                ctk.CTkButton(
                    actions,
                    text="Again",
                    width=48,
                    height=22,
                    font=ctk.CTkFont(size=11),
                    command=lambda i=full_idx: self._chat_regenerate(i),
                    **ghost,
                ).pack(side="left", padx=1)

    def _chat_bubble_kind(self, role: str) -> str:
        r = (role or "user").lower()
        if r == "user":
            return "user"
        if r == "assistant":
            return "assistant"
        if r in ("system_note", "system"):
            return "system"
        if r in (
            "terminal",
            "skill",
            "mcp",
            "gui",
            "screenshot",
            "clipboard",
            "windows",
            "tool",
            "org",
            "pip",
            "browser",
            "web_search",
            "ocr",
            "self_improve",
        ):
            return "tool"
        if r == "error" or (isinstance(role, str) and "error" in role.lower()):
            return "error"
        return "assistant"

    _TOOL_ROLES = frozenset(
        {
            "terminal",
            "skill",
            "mcp",
            "gui",
            "clipboard",
            "windows",
            "tool",
            "org",
            "pip",
            "system_note",
            "system",
            "browser",
            "web_search",
            "ocr",
            "self_improve",
            "harness",
            "org_agent",
            "web_fetch",
            "web_crawl",
            "web_scrape",
            "web_download",
            "image_gen",
            "deep_research",
        }
    )

    def _tool_trace_summary(self, tool_msgs: list[dict[str, Any]]) -> str:
        counts: dict[str, int] = {}
        edits = 0
        for m in tool_msgs:
            r = str(m.get("role") or "tool").lower()
            counts[r] = counts.get(r, 0) + 1
            if m.get("file_diff") or "```diff" in str(m.get("content") or ""):
                edits += 1
        parts = [f"{n}× {k}" for k, n in sorted(counts.items())]
        base = " · ".join(parts) if parts else f"{len(tool_msgs)} tool step(s)"
        if edits:
            base += f" · {edits} file edit(s)"
        return base

    def _humanize_thinking_step(self, raw: str | dict) -> str:
        """Turn internal emit lines into short user-facing progress.

        Accepts either a string (legacy) or a dict with structured step data.
        """
        # Handle structured data
        if isinstance(raw, dict):
            tool = raw.get("tool")
            status = raw.get("status")
            duration_ms = raw.get("duration_ms")
            detail = raw.get("detail", "")
            msg = raw.get("msg", "")

            if tool and status:
                status_icon = {"start": "⏳", "success": "✓", "error": "✗", "pending": "⏸"}.get(status, "⏳")
                duration_str = f" ({duration_ms}ms)" if duration_ms else ""
                if detail:
                    return f"{status_icon} {tool}: {detail}{duration_str}"
                return f"{status_icon} {tool}{duration_str}"
            elif msg:
                return msg
            return str(raw)

        line = (raw or "").strip()
        if not line:
            return ""
        if line.lstrip().startswith("💭"):
            t = line.lstrip()[1:].strip()
            return t[:200] + ("…" if len(t) > 200 else "")
        # Strip [Agent] / [who] prefixes
        if line.startswith("[") and "] " in line[:48]:
            line = line.split("] ", 1)[-1].strip()
        low = line.lower()
        # Map common internal phrases → clear status
        rules: list[tuple[str, str]] = [
            ("queued message", "Queued — preparing…"),
            ("loading mcp", "Loading tools…"),
            ("building instructions", "Building prompt…"),
            ("writing final answer", "Writing answer…"),
            ("streaming", "Receiving answer…"),
            ("compact instructions", "Retrying with shorter prompt…"),
            ("prompt token", "Prompt too large — compacting…"),
            ("web_search", "Searching the web…"),
            ("searching the web", "Searching the web…"),
            ("opened", "Reading web pages…"),
            ("search done", "Search finished"),
            ("terminal", "Running command…"),
            ("run_terminal", "Running command…"),
            ("browser", "Using browser…"),
            ("screenshot", "Taking screenshot…"),
            ("image_gen", "Generating image…"),
            ("read_file", "Reading a file…"),
            ("write_file", "Writing a file…"),
            ("list_dir", "Listing folder…"),
            ("thinking with", "Model thinking…"),
            ("pass ", "Model working…"),
            ("waiting approval", "Waiting for your approval…"),
            ("org pipeline", "Org agents working…"),
            ("stopped", "Stopped"),
        ]
        for needle, nice in rules:
            if needle in low:
                # Keep a short tail of the original for context (model name, query)
                tail = ""
                if "thinking with" in low and "(" in line:
                    # keep model short name
                    try:
                        mid = line.split("Thinking with", 1)[-1].split("(", 1)[0].strip()
                        if mid and len(mid) < 48:
                            tail = f" ({mid})"
                    except Exception:  # noqa: BLE001
                        tail = ""
                elif "search" in low and ("“" in line or '"' in line or "‘" in line):
                    # keep quoted query snippet
                    for q in ('"', "“", "'"):
                        if q in line:
                            try:
                                part = line.split(q, 2)
                                if len(part) >= 3 and part[1].strip():
                                    qtxt = part[1].strip()[:40]
                                    tail = f" — {qtxt}"
                                    break
                            except Exception:  # noqa: BLE001
                                pass
                return nice + tail
        # Fallback: trim noise, keep readable
        if len(line) > 90:
            line = line[:87] + "…"
        return line

    def _tool_activity_line(self, m: dict[str, Any]) -> str:
        role = str(m.get("role") or "tool")
        body = str(m.get("content") or "")
        cmd = str(m.get("command") or "")
        ok = m.get("ok")
        err = ""
        for ln in body.splitlines():
            low = ln.lower()
            if any(k in ln for k in ("Error", "ImportError", "Traceback", "FAIL", "ModuleNot")):
                err = ln.strip()[:140]
                break
            if "Edited " in ln:
                err = ln.strip()[:140]
                break
        if role == "terminal":
            flag = "ok" if ok is True else ("FAIL" if ok is False or err else "ran")
            return f"⌨  {flag}  ·  {(err or cmd or 'command')[:140]}"
        if role == "harness":
            head = (err or body.splitlines()[0] if body else "file tool")[:140]
            return f"✎  {head}"
        return f"▸  {role}  ·  {(err or body.splitlines()[0] if body else role)[:120]}"

    def _render_chat_activity_lines(self, parent: Any, tool_msgs: list[dict[str, Any]]) -> None:
        """Always-visible short log of what the model just ran (not a raw dump)."""
        from app.ui.themes import UI as _UI

        rows = list(tool_msgs or [])[-8:]
        if not rows:
            return
        box = ctk.CTkFrame(
            parent,
            fg_color=("#f4f4f5", "#18181b"),
            corner_radius=10,
            border_width=1,
            border_color=("#e4e4e7", "#27272a"),
        )
        box.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(
            box,
            text="What the model is doing",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=_UI.get("muted", ("#6b7280", "#a1a1aa")),
            anchor="w",
        ).pack(fill="x", padx=10, pady=(6, 2))
        for m in rows:
            line = self._tool_activity_line(m)
            ctk.CTkLabel(
                box,
                text=line,
                font=ctk.CTkFont(size=13),
                text_color=_UI.get("label", ("#111", "#eee")),
                anchor="w",
                justify="left",
                wraplength=720,
            ).pack(fill="x", padx=10, pady=1)
        ctk.CTkLabel(box, text="", height=4).pack()
        try:
            self._bind_wheel_tree(box)
        except Exception:  # noqa: BLE001
            pass

    def _render_collapsible_thinking(
        self, parent: Any, msg: dict[str, Any], *, expanded: bool = False
    ) -> None:
        """Thinking card — one compact header when collapsed (minimal height)."""
        from app.ui.themes import UI as _UI, style_chrome_button

        steps = list(msg.get("steps") or [])
        if not steps:
            raw = (msg.get("content") or "").strip()
            steps = [ln.lstrip("• ").strip() for ln in raw.splitlines() if ln.strip()]
        # Humanize for display
        nice_steps = [self._humanize_thinking_step(s) or s for s in steps]
        nice_steps = [s for s in nice_steps if s]
        n = len(nice_steps) or len(steps)
        status = str(msg.get("status") or "done")
        # Done/error thinking stays collapsed unless user forced expanded
        if msg.get("collapsed") or (
            status in ("done", "error") and not msg.get("expanded")
        ):
            open0 = False
        else:
            open0 = bool(expanded or msg.get("expanded"))
        state = {"open": open0}

        # Compact outer — no giant side strip stretching height
        card = ctk.CTkFrame(
            parent,
            fg_color=("#eef2ff", "#1a1a2e"),
            corner_radius=10,
            border_width=1,
            border_color=("#c7d2fe", "#312e81"),
        )
        card.pack(fill="x", padx=10, pady=2)

        head = ctk.CTkFrame(card, fg_color="transparent", height=34)
        head.pack(fill="x", padx=6, pady=4)
        head.pack_propagate(False)

        st_word = "done" if status == "done" else ("error" if status == "error" else status)
        title = f"💭 Thought · {n} step(s) · {st_word}"
        toggle_btn = ctk.CTkButton(
            head,
            text=("▼ " if state["open"] else "▶ ") + title,
            anchor="w",
            height=28,
            **style_chrome_button(),
        )
        toggle_btn.pack(side="left", fill="x", expand=True)

        last_raw = nice_steps[-1] if nice_steps else (steps[-1] if steps else "")
        preview = last_raw if len(last_raw) <= 56 else last_raw[:53] + "…"
        prev_lbl = ctk.CTkLabel(
            head,
            text=preview if not state["open"] else "",
            text_color=_UI["muted"],
            font=ctk.CTkFont(size=11),
            anchor="e",
            width=200,
        )
        prev_lbl.pack(side="right", padx=(4, 4))

        detail = ctk.CTkFrame(card, fg_color="transparent")

        def fill_detail() -> None:
            for w in detail.winfo_children():
                try:
                    w.destroy()
                except Exception:  # noqa: BLE001
                    pass
            # Fixed modest height + scrollbar — never eats half the chat
            show = nice_steps[-30:] if nice_steps else steps[-30:]
            tb = ctk.CTkTextbox(
                detail,
                height=min(140, max(72, 18 + min(len(show), 8) * 15)),
                font=ctk.CTkFont(size=12),
                wrap="word",
                fg_color=("#e0e7ff", "#12122a"),
                border_width=0,
                activate_scrollbars=True,
            )
            tb.pack(fill="x", padx=8, pady=(0, 6))
            lines = []
            for i, s in enumerate(show, 1):
                lines.append(f"{i}. {s}")
            tb.insert("1.0", "\n".join(lines) + ("\n" if lines else "(no steps)\n"))
            try:
                tb.configure(state="disabled")
            except Exception:  # noqa: BLE001
                pass
            try:
                tb.see("end")
            except Exception:  # noqa: BLE001
                pass

        def toggle() -> None:
            state["open"] = not state["open"]
            try:
                toggle_btn.configure(text=("▼ " if state["open"] else "▶ ") + title)
            except Exception:  # noqa: BLE001
                pass
            try:
                prev_lbl.configure(text="" if state["open"] else preview)
            except Exception:  # noqa: BLE001
                pass
            if state["open"]:
                fill_detail()
                detail.pack(fill="x", padx=2, pady=(0, 4))
            else:
                try:
                    detail.pack_forget()
                except Exception:  # noqa: BLE001
                    pass

        toggle_btn.configure(command=toggle)
        if state["open"]:
            fill_detail()
            detail.pack(fill="x", padx=2, pady=(0, 4))
        # Wheel over card scrolls chat list
        try:
            self._bind_wheel_tree(card)
        except Exception:  # noqa: BLE001
            pass

    def _render_terminal_tool_step(self, parent: Any, m: dict[str, Any]) -> None:
        """Render a terminal tool step in Cline-like format with command prompt and output."""
        from app.ui.themes import UI as _UI, style_chrome_button

        command = m.get("command", "")
        content = self._display_content_for_message(m)
        exit_code = m.get("exit_code")

        # Parse the formatted content to extract stdout/stderr
        stdout = ""
        stderr = ""
        error = ""
        cwd = ""

        # The content is formatted by format_result_for_llm:
        # ### Terminal result
        # Command: `cmd`
        # Cwd: `cwd`
        # Exit code: X
        # OK: true/false
        # Error: ...
        # Stdout:
        # ```
        # stdout
        # ```
        # Stderr:
        # ```
        # stderr
        # ```
        import re
        cwd_match = re.search(r"Cwd:\s*`([^`]*)`", content)
        if cwd_match:
            cwd = cwd_match.group(1)

        error_match = re.search(r"Error:\s*(.+?)(?:\n|$)", content)
        if error_match:
            error = error_match.group(1).strip()

        stdout_match = re.search(r"Stdout:\n```\n(.*?)\n```", content, re.DOTALL)
        if stdout_match:
            stdout = stdout_match.group(1)

        stderr_match = re.search(r"Stderr:\n```\n(.*?)\n```", content, re.DOTALL)
        if stderr_match:
            stderr = stderr_match.group(1)

        # Create terminal-style block
        block = ctk.CTkFrame(parent, fg_color=("gray92", "gray18"), corner_radius=8)
        block.pack(fill="x", pady=3)

        # Header with role and exit code
        header = ctk.CTkFrame(block, fg_color="transparent")
        header.pack(fill="x", padx=8, pady=(8, 0))
        ctk.CTkLabel(
            header,
            text="TERMINAL",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=_UI["label"],
            anchor="w",
        ).pack(side="left")

        # Exit code badge
        if exit_code is not None:
            ec_color = ("#059669", "#34d399") if exit_code == 0 else ("#dc2626", "#ef4444")
            ec_frame = ctk.CTkFrame(header, fg_color=ec_color, corner_radius=4)
            ec_frame.pack(side="right", padx=4)
            ctk.CTkLabel(
                ec_frame,
                text=f"  exit {exit_code}  ",
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color="#ffffff",
            ).pack(padx=6, pady=2)

        # Command display - like a terminal prompt
        if command:
            cmd_frame = ctk.CTkFrame(block, fg_color=("gray85", "gray22"), corner_radius=6)
            cmd_frame.pack(fill="x", padx=8, pady=(6, 2))
            # Terminal prompt style
            prompt_text = f"$ {command}"
            ctk.CTkLabel(
                cmd_frame,
                text=prompt_text,
                font=ctk.CTkFont(family="Consolas", size=11),
                text_color=("#1f2937", "#e5e7eb"),
                anchor="w",
                justify="left",
            ).pack(anchor="w", padx=10, pady=6)

        # CWD if available
        if cwd:
            cwd_frame = ctk.CTkFrame(block, fg_color="transparent")
            cwd_frame.pack(fill="x", padx=8, pady=(0, 4))
            ctk.CTkLabel(
                cwd_frame,
                text=f"📁 {cwd}",
                font=ctk.CTkFont(size=10),
                text_color=_UI["muted"],
                anchor="w",
            ).pack(anchor="w")

        # Error if any
        if error:
            err_frame = ctk.CTkFrame(block, fg_color=("#fef2f2", "#7f1d1d"), corner_radius=6)
            err_frame.pack(fill="x", padx=8, pady=(2, 4))
            ctk.CTkLabel(
                err_frame,
                text=f"⚠ Error: {error}",
                font=ctk.CTkFont(size=11),
                text_color=("#dc2626", "#fca5a5"),
                anchor="w",
                justify="left",
                wraplength=600,
            ).pack(anchor="w", padx=10, pady=6)

        # Stdout
        if stdout:
            out_frame = ctk.CTkFrame(block, fg_color=("gray88", "gray20"), corner_radius=6)
            out_frame.pack(fill="x", padx=8, pady=(2, 2))
            # Use textbox for selectable output
            tb = ctk.CTkTextbox(
                out_frame,
                font=ctk.CTkFont(family="Consolas", size=11),
                fg_color=("gray88", "gray20"),
                border_width=0,
                wrap="word",
                height=min(200, max(60, len(stdout.splitlines()) * 22)),
            )
            tb.pack(fill="x", padx=6, pady=6)
            tb.insert("1.0", stdout)
            tb.configure(state="disabled")

        # Stderr
        if stderr:
            err_frame = ctk.CTkFrame(block, fg_color=("#fef2f2", "#7f1d1d"), corner_radius=6)
            err_frame.pack(fill="x", padx=8, pady=(2, 8))
            tb = ctk.CTkTextbox(
                err_frame,
                font=ctk.CTkFont(family="Consolas", size=11),
                fg_color=("#fef2f2", "#7f1d1d"),
                border_width=0,
                wrap="word",
                height=min(200, max(60, len(stderr.splitlines()) * 22)),
            )
            tb.pack(fill="x", padx=6, pady=6)
            tb.insert("1.0", stderr)
            tb.configure(state="disabled")

    def _render_collapsible_tool_trace(
        self, parent: Any, tool_msgs: list[dict[str, Any]], *, expanded: bool = False
    ) -> None:
        """Compact tool-trace card with expand/collapse (keeps main chat clean)."""
        from app.ui.themes import UI as _UI, style_chrome_button

        state = {"open": bool(expanded)}
        card = ctk.CTkFrame(parent, fg_color=_BUBBLE["tool"][0][0], corner_radius=12)
        card.pack(fill="x", padx=10, pady=4)
        # left accent strip simulation
        strip = ctk.CTkFrame(card, width=4, fg_color=("#059669", "#34d399"), corner_radius=2)
        strip.pack(side="left", fill="y", padx=(0, 0), pady=0)

        body_wrap = ctk.CTkFrame(card, fg_color="transparent")
        body_wrap.pack(side="left", fill="both", expand=True)

        summary = self._tool_trace_summary(tool_msgs)
        head = ctk.CTkFrame(body_wrap, fg_color="transparent")
        head.pack(fill="x", padx=8, pady=6)
        toggle_btn = ctk.CTkButton(
            head,
            text=("▼ " if state["open"] else "▶ ") + f"Tools · {summary}",
            anchor="w",
            height=28,
            **style_chrome_button(),
        )
        toggle_btn.pack(side="left", fill="x", expand=True)

        detail = ctk.CTkFrame(body_wrap, fg_color="transparent")
        if state["open"]:
            detail.pack(fill="x", padx=8, pady=(0, 8))

        def fill_detail() -> None:
            for w in detail.winfo_children():
                w.destroy()
            for m in tool_msgs:
                role = str(m.get("role") or "tool")
                # Special handling for terminal messages - render in Cline-like format
                if role == "terminal":
                    self._render_terminal_tool_step(detail, m)
                else:
                    content = self._display_content_for_message(m)
                    if len(content) > 1200:
                        content = content[:1200] + "\n…"
                    block = ctk.CTkFrame(detail, fg_color=("gray92", "gray18"), corner_radius=8)
                    block.pack(fill="x", pady=3)
                    row = ctk.CTkFrame(block, fg_color="transparent")
                    row.pack(fill="x", padx=6, pady=(6, 0))
                    ctk.CTkLabel(
                        row,
                        text=role.upper(),
                        font=ctk.CTkFont(size=11, weight="bold"),
                        text_color=_UI["label"],
                        anchor="w",
                    ).pack(side="left")
                    fd = m.get("file_diff") if isinstance(m.get("file_diff"), dict) else None
                    if not fd and ("```diff" in str(m.get("content") or "") or "--- a/" in str(m.get("content") or "")):
                        try:
                            from app.core.services.tools.file_diff import extract_diff_from_text

                            dtxt = extract_diff_from_text(str(m.get("content") or ""))
                            if dtxt:
                                fd = {"diff": dtxt, "path": "", "summary": "File change"}
                        except Exception:  # noqa: BLE001
                            fd = None
                    if fd and (fd.get("diff") or fd.get("summary")):
                        ctk.CTkButton(
                            row,
                            text="📄 View diff",
                            width=100,
                            height=26,
                            command=lambda f=fd: self._open_file_diff_viewer(f),
                            **style_chrome_button(primary=True),
                        ).pack(side="right", padx=4)
                    if content.strip():
                        ctk.CTkLabel(
                            block,
                            text=content.strip(),
                            justify="left",
                            anchor="w",
                            wraplength=640,
                            text_color=_UI["muted"],
                            font=ctk.CTkFont(size=12),
                        ).pack(anchor="w", padx=8, pady=(2, 6))
                    if m.get("images"):
                        self._render_message_media(block, m)

        def toggle() -> None:
            state["open"] = not state["open"]
            toggle_btn.configure(
                text=("▼ " if state["open"] else "▶ ") + f"Tools · {summary}"
            )
            if state["open"]:
                fill_detail()
                detail.pack(fill="x", padx=8, pady=(0, 8))
            else:
                detail.pack_forget()
            try:
                self._bind_wheel_tree(card)
            except Exception:  # noqa: BLE001
                pass

        toggle_btn.configure(command=toggle)
        if state["open"]:
            fill_detail()

    def _open_file_diff_viewer(self, file_diff: dict[str, Any] | None) -> None:
        """Task #8: popup unified diff with +/- color tags."""
        from app.ui.themes import style_chrome_button, UI as _UI

        fd = file_diff or {}
        diff_text = str(fd.get("diff") or "")
        path = str(fd.get("path") or "")
        summary = str(fd.get("summary") or "File change")
        if not diff_text and fd.get("content"):
            try:
                from app.core.services.tools.file_diff import extract_diff_from_text

                diff_text = extract_diff_from_text(str(fd.get("content") or ""))
            except Exception:  # noqa: BLE001
                diff_text = str(fd.get("content") or "")
        if not diff_text:
            messagebox.showinfo("Diff", "No diff available for this step.", parent=self)
            return
        win = ctk.CTkToplevel(self)
        win.title(f"Diff — {Path(path).name if path else 'file edit'}")
        win.geometry("760x520")
        win.minsize(480, 320)
        try:
            win.transient(self)
            win.resizable(True, True)
        except Exception:  # noqa: BLE001
            pass
        head = ctk.CTkFrame(win, fg_color="transparent")
        head.pack(fill="x", padx=12, pady=(12, 4))
        ctk.CTkLabel(
            head,
            text=summary,
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=_UI["label"],
            anchor="w",
        ).pack(fill="x")
        if path:
            ctk.CTkLabel(
                head,
                text=path,
                text_color=_UI["muted"],
                font=ctk.CTkFont(size=11),
                anchor="w",
            ).pack(fill="x", pady=(2, 0))
        tb = ctk.CTkTextbox(win, font=ctk.CTkFont(family="Consolas", size=12), wrap="none")
        tb.pack(fill="both", expand=True, padx=12, pady=8)
        tb.insert("1.0", diff_text if diff_text.endswith("\n") else diff_text + "\n")
        # Color +/- lines
        try:
            tw = tb._textbox  # type: ignore[attr-defined]
            tw.tag_configure("add", foreground="#16a34a")
            tw.tag_configure("del", foreground="#dc2626")
            tw.tag_configure("hunk", foreground="#2563eb")
            tw.tag_configure("meta", foreground="#6b7280")
            for i, line in enumerate(diff_text.splitlines(), 1):
                start = f"{i}.0"
                end = f"{i}.end"
                if line.startswith("+++") or line.startswith("---"):
                    tw.tag_add("meta", start, end)
                elif line.startswith("@@"):
                    tw.tag_add("hunk", start, end)
                elif line.startswith("+"):
                    tw.tag_add("add", start, end)
                elif line.startswith("-"):
                    tw.tag_add("del", start, end)
        except Exception:  # noqa: BLE001
            pass
        try:
            tb.configure(state="disabled")
        except Exception:  # noqa: BLE001
            pass
        bar = ctk.CTkFrame(win, fg_color="transparent")
        bar.pack(fill="x", padx=12, pady=(0, 12))

        def copy_diff() -> None:
            try:
                self.clipboard_clear()
                self.clipboard_append(diff_text)
                self.set_status("Diff copied", toast=True)
            except Exception:  # noqa: BLE001
                pass

        def open_file() -> None:
            if not path:
                return
            try:
                from app.ui.components.message_box import open_url_or_path
                from app.core.services.data.rag_knowledge import path_to_file_uri

                open_url_or_path(path_to_file_uri(path))
            except Exception as e:  # noqa: BLE001
                messagebox.showerror("Open file", str(e), parent=win)

        ctk.CTkButton(bar, text="Copy diff", width=100, command=copy_diff, **style_chrome_button()).pack(
            side="left", padx=4
        )
        if path:
            ctk.CTkButton(
                bar, text="Open file", width=100, command=open_file, **style_chrome_button()
            ).pack(side="left", padx=4)
        ctk.CTkButton(bar, text="Close", width=90, command=win.destroy, **style_chrome_button(primary=True)).pack(
            side="right", padx=4
        )

    def _render_file_edit_chips(self, parent: Any, tool_msgs: list[dict[str, Any]]) -> None:
        """Always-visible chips for file edits even when tool trace is hidden (Task #8)."""
        from app.ui.themes import style_chrome_button, UI as _UI

        edits: list[dict[str, Any]] = []
        for m in tool_msgs:
            fd = m.get("file_diff")
            if isinstance(fd, dict) and (fd.get("diff") or fd.get("summary")):
                edits.append(fd)
        if not edits:
            return
        wrap = ctk.CTkFrame(parent, fg_color=("#ecfdf5", "#052e16"), corner_radius=10)
        wrap.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(
            wrap,
            text=f"📄 {len(edits)} file change(s) this turn",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=_UI["label"],
            anchor="w",
        ).pack(fill="x", padx=10, pady=(8, 2))
        row = ctk.CTkFrame(wrap, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=(0, 8))
        for fd in edits[:8]:
            label = str(fd.get("summary") or Path(str(fd.get("path") or "file")).name)
            if len(label) > 42:
                label = label[:39] + "…"
            ctk.CTkButton(
                row,
                text=label,
                width=min(220, 40 + len(label) * 7),
                height=28,
                command=lambda f=fd: self._open_file_diff_viewer(f),
                **style_chrome_button(primary=True),
            ).pack(side="left", padx=3, pady=2)

    def _on_show_tools_toggle(self) -> None:
        self._chat_show_tools = bool(self.chat_show_tools_var.get())
        self._chat_render_transcript()

    def _chat_stored_count(self) -> int:
        try:
            return len((self._chat_state or {}).get("messages") or [])
        except Exception:  # noqa: BLE001
            return 0

    def _chat_load_older_messages(self) -> None:
        """Paint more stored messages above the current tail."""
        total = self._chat_stored_count()
        cur = int(getattr(self, "_chat_history_window", 80) or 80)
        nxt = min(max(total, 80), cur + 120)
        if nxt <= cur and cur >= total:
            self.set_status("Already showing the full chat", toast=True)
            return
        self._chat_history_window = nxt
        self._chat_user_pinned_bottom = False
        self._chat_render_transcript()
        try:
            self.after(40, self._chat_scroll_to_start)
        except Exception:  # noqa: BLE001
            pass
        self.set_status(f"Showing last {self._chat_history_window} of {total} messages", toast=True)

    def _chat_show_all_messages(self) -> None:
        self._chat_show_from_start()

    def _chat_show_from_start(self) -> None:
        """Paint from the first stored message and jump to the top."""
        total = max(self._chat_stored_count(), 1)
        self._chat_history_window = total
        self._chat_user_pinned_bottom = False
        self._chat_render_transcript()
        try:
            self.after(40, self._chat_scroll_to_start)
            self.after(160, self._chat_scroll_to_start)
        except Exception:  # noqa: BLE001
            pass
        self.set_status(f"Full chat from the start ({total} messages)", toast=True)

    def _chat_scroll_to_start(self) -> None:
        try:
            c = self._chat_canvas()
            if c is None:
                return
            c.yview_moveto(0.0)
            self._chat_user_pinned_bottom = False
            self._update_jump_latest_fab()
        except Exception:  # noqa: BLE001
            pass

    def _chat_maybe_load_older_on_scroll(self) -> None:
        if bool(getattr(self, "_chat_busy", False)):
            return
        try:
            import time as _time

            now = _time.monotonic()
            last = float(getattr(self, "_chat_load_older_ts", 0) or 0)
            if now - last < 0.8:
                return
            c = self._chat_canvas()
            if c is None:
                return
            y0, _y1 = c.yview()
            if float(y0) > 0.02:
                return
            total = self._chat_stored_count()
            win = int(getattr(self, "_chat_history_window", 80) or 80)
            if win >= total:
                return
            self._chat_load_older_ts = now
            self._chat_load_older_messages()
        except Exception:  # noqa: BLE001
            pass

    def _chat_scroll_alive(self) -> bool:
        try:
            w = getattr(self, "chat_scroll", None)
            return w is not None and bool(w.winfo_exists())
        except Exception:  # noqa: BLE001
            return False

    def _ensure_chat_scroll(self) -> bool:
        """Recreate the message list if Restore/show_page destroyed it."""
        if self._chat_scroll_alive():
            return True
        mid = getattr(self, "_chat_mid", None)
        try:
            if mid is None or not bool(mid.winfo_exists()):
                return False
        except Exception:  # noqa: BLE001
            return False
        try:
            from app.ui.themes import UI as _UI

            self.chat_scroll = ctk.CTkScrollableFrame(
                mid,
                fg_color=_UI.get("chat_bg", ("#ffffff", "#111111")),
                corner_radius=0,
            )
            self.chat_scroll.grid(row=0, column=0, sticky="nsew")
            self.chat_scroll.grid_columnconfigure(0, weight=1)
            return True
        except Exception:  # noqa: BLE001
            return False

    def _chat_canvas(self) -> Any | None:
        try:
            if self._chat_scroll_alive():
                return self.chat_scroll._parent_canvas  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            return None
        return None

    def _chat_near_bottom(self, threshold: float = 0.12) -> bool:
        """True if user is near the bottom (follow stream / pin)."""
        canvas = self._chat_canvas()
        if canvas is None:
            return True
        try:
            _y0, y1 = canvas.yview()
            return float(y1) >= (1.0 - threshold)
        except Exception:  # noqa: BLE001
            return True

    def _refresh_chat_scrollregion(self) -> None:
        """Resize the chat canvas after expand/collapse — do not yank to the bottom."""
        try:
            canvas = self._chat_canvas()
            if canvas is None:
                return
            canvas.update_idletasks()
            bb = canvas.bbox("all")
            if bb:
                canvas.configure(scrollregion=bb)
        except Exception:  # noqa: BLE001
            pass

    def _chat_scroll_units(self, steps: int) -> None:
        """Scroll chat by steps (negative = up). Updates pin-to-bottom flag."""
        canvas = self._chat_canvas()
        if canvas is None or steps == 0:
            return
        try:
            canvas.yview_scroll(int(steps), "units")
            self._chat_user_pinned_bottom = self._chat_near_bottom()
            self._update_jump_latest_fab()
        except Exception:  # noqa: BLE001
            pass

    def _on_chat_mousewheel(self, event: Any) -> str | None:
        """
        Scroll the message list when the pointer is over chat.

        Long reply textboxes handle the wheel themselves (smooth inner scroll)
        and call this when they hit the top or bottom.
        """
        # Shift = allow nested textbox to scroll its own content
        try:
            if int(getattr(event, "state", 0) or 0) & 0x0001:
                return None
        except Exception:  # noqa: BLE001
            pass
        canvas = self._chat_canvas()
        if canvas is None:
            return None
        try:
            delta = int(getattr(event, "delta", 0) or 0)
            if delta:
                # Windows mouse: ±120 per notch; trackpads send smaller deltas
                # +50% vs old (/30 → ~4 units): /20 → ~6 units per notch
                steps = int(round(-delta / 20.0))
                if steps == 0:
                    steps = -1 if delta > 0 else 1
                # Cap so a huge trackpad fling doesn't jump the whole chat (+50%)
                steps = max(-18, min(18, steps))
                self._chat_scroll_units(steps)
            elif getattr(event, "num", None) == 4:  # Linux up
                self._chat_scroll_units(-6)
            elif getattr(event, "num", None) == 5:
                self._chat_scroll_units(6)
            try:
                self._chat_maybe_load_older_on_scroll()
            except Exception:  # noqa: BLE001
                pass
            return "break"
        except Exception:  # noqa: BLE001
            return None

    def _bind_wheel_tree(self, widget: Any) -> None:
        """Bind wheel on widget + descendants (replace, do not stack handlers)."""
        # Long reply textboxes own the wheel (smooth inner scroll) until they hit an edge
        if bool(getattr(widget, "_own_smooth_scroll", False)):
            return
        try:
            if isinstance(widget, ctk.CTkTextbox) and bool(
                getattr(widget, "_own_smooth_scroll", False)
            ):
                return
        except Exception:  # noqa: BLE001
            pass
        try:
            # Replace previous handlers so re-renders don't multiply scroll speed
            widget.bind("<MouseWheel>", self._on_chat_mousewheel)
            widget.bind("<Button-4>", self._on_chat_mousewheel)
            widget.bind("<Button-5>", self._on_chat_mousewheel)
        except Exception:  # noqa: BLE001
            pass
        try:
            for child in widget.winfo_children():
                self._bind_wheel_tree(child)
        except Exception:  # noqa: BLE001
            pass

    def _widget_under_chat_list(self, widget: Any) -> bool:
        """True if widget is in the message list (not composer / Live)."""
        try:
            live = getattr(self, "_chat_live_frame", None)
            inp = getattr(self, "chat_input", None)
            w = widget
            for _ in range(24):
                if w is None:
                    return False
                if inp is not None and w is inp:
                    return False
                if live is not None and w is live:
                    return False
                if w is getattr(self, "chat_scroll", None):
                    return True
                w = getattr(w, "master", None)
        except Exception:  # noqa: BLE001
            return False
        return False

    def _on_global_chat_wheel(self, event: Any) -> str | None:
        if getattr(self, "_current_page", "") != "Chat":
            return None
        if not self._widget_under_chat_list(getattr(event, "widget", None)):
            return None
        return self._on_chat_mousewheel(event)

    def _bind_chat_mousewheel(self) -> None:
        """Wheel / keys scroll the message list when chat is active."""
        if not hasattr(self, "chat_scroll"):
            return
        if not hasattr(self, "_chat_user_pinned_bottom"):
            self._chat_user_pinned_bottom = True
        self._bind_wheel_tree(self.chat_scroll)
        if not getattr(self, "_chat_global_wheel_bound", False):
            try:
                self.bind_all("<MouseWheel>", self._on_global_chat_wheel, add="+")
                self.bind_all("<Button-4>", self._on_global_chat_wheel, add="+")
                self.bind_all("<Button-5>", self._on_global_chat_wheel, add="+")
                self._chat_global_wheel_bound = True
            except Exception:  # noqa: BLE001
                pass
        canvas = self._chat_canvas()
        if canvas is not None:
            try:
                canvas.bind("<MouseWheel>", self._on_chat_mousewheel)
                canvas.bind("<Button-4>", self._on_chat_mousewheel)
                canvas.bind("<Button-5>", self._on_chat_mousewheel)
                canvas.bind(
                    "<ButtonRelease-1>",
                    lambda _e: (
                        setattr(self, "_chat_user_pinned_bottom", self._chat_near_bottom()),
                        self._update_jump_latest_fab(),
                    ),
                )
                # B1-Motion on scrollbar/canvas: track pin state while dragging
                canvas.bind(
                    "<B1-Motion>",
                    lambda _e: setattr(
                        self, "_chat_user_pinned_bottom", self._chat_near_bottom()
                    ),
                )
            except Exception:  # noqa: BLE001
                pass
        # Keyboard navigation when chat has focus
        try:
            mid = getattr(self, "_chat_mid", None)
            if mid is not None:
                mid.bind("<Prior>", lambda _e: (self._chat_scroll_units(-30), "break"))
                mid.bind("<Next>", lambda _e: (self._chat_scroll_units(30), "break"))
                mid.bind(
                    "<Home>",
                    lambda _e: (
                        self._chat_canvas() and self._chat_canvas().yview_moveto(0),  # type: ignore[union-attr]
                        setattr(self, "_chat_user_pinned_bottom", False),
                        self._update_jump_latest_fab(),
                        "break",
                    ),
                )
                mid.bind(
                    "<End>",
                    lambda _e: (self._chat_scroll_to_end(force=True), "break"),
                )
        except Exception:  # noqa: BLE001
            pass

    def _update_jump_latest_fab(self) -> None:
        """Show/hide ↓ Latest when user has scrolled up."""
        try:
            mid = getattr(self, "_chat_mid", None)
            if mid is None or not mid.winfo_exists():
                return
            old = getattr(self, "_jump_latest_btn", None)
            at_bottom = self._chat_near_bottom()
            pinned = bool(getattr(self, "_chat_user_pinned_bottom", True))
            if at_bottom or pinned:
                if old is not None:
                    try:
                        old.destroy()
                    except Exception:  # noqa: BLE001
                        pass
                    self._jump_latest_btn = None
                return
            if old is not None:
                try:
                    if old.winfo_exists():
                        return
                except Exception:  # noqa: BLE001
                    pass
            from app.ui.themes import style_chrome_button

            # Place on scroll canvas only (not whole mid) so rail / half-screen stay free
            host = getattr(self, "chat_scroll", None) or mid
            self._jump_latest_btn = ctk.CTkButton(
                host,
                text="↓ Latest",
                width=100,
                height=30,
                corner_radius=15,
                command=lambda: self._chat_scroll_to_end(force=True),
                **style_chrome_button(primary=True),
            )
            self._jump_latest_btn.place(relx=0.5, rely=0.97, anchor="s")
        except Exception:  # noqa: BLE001
            pass

    def _reply_view_cap(self) -> int:
        """Grow replies with the list. The chat canvas scrolls — not an inner box."""
        return 12000

    def _estimate_text_height(self, text: str, wrap: int, font_size: int = 14) -> int:
        """Natural pixel height for wrapped message body (no window cap)."""
        # Conservative chars/line — under-estimating clips the last lines
        cpl = max(18, int(wrap / max(7.2, font_size * 0.68)))
        lines = 0
        for ln in (text or "").split("\n"):
            lines += max(1, (len(ln) + cpl - 1) // cpl) if ln else 1
        return max(52, 24 + lines * (font_size + 10))

    def _sync_textbox_height(
        self,
        tb: Any,
        *,
        font_size: int = 15,
        max_height: int | None = None,
    ) -> bool:
        """Grow the box to the real wrapped line count so the last line is not cut."""
        try:
            tw = tb._textbox
        except Exception:  # noqa: BLE001
            return False
        try:
            tb.update_idletasks()
        except Exception:  # noqa: BLE001
            pass
        display = 0
        try:
            cnt = tw.count("1.0", "end-1c", "displaylines")
            if isinstance(cnt, (tuple, list)):
                display = int(cnt[0] or 0)
            elif cnt:
                display = int(cnt)
        except Exception:  # noqa: BLE001
            display = 0
        if display <= 0:
            try:
                display = int(float(str(tw.index("end-1c")).split(".")[0]))
            except Exception:  # noqa: BLE001
                display = 3
        extra = 0
        try:
            bb = tw.bbox("end-1c")
            if bb:
                extra = 8
        except Exception:  # noqa: BLE001
            extra = 8
        h = 22 + int(display) * (int(font_size) + 9) + extra
        cap = min(int(max_height or 1400), self._reply_view_cap())
        overflow = h > cap + 8
        try:
            tb.configure(height=cap if overflow else max(52, h))
        except Exception:  # noqa: BLE001
            pass
        return overflow

    def _linkify_and_lock_textbox(self, tb: ctk.CTkTextbox, *, linkify: bool = True) -> None:
        """
        Make a CTkTextbox selectable/copyable but not editable.
        Optionally tag http(s) URLs so they open in the default browser on click.
        """
        import re
        import webbrowser

        try:
            tw = tb._textbox  # underlying tk.Text
        except Exception:  # noqa: BLE001
            return

        if linkify:
            try:
                tw.tag_configure("hyper", foreground="#2563eb", underline=True)
            except Exception:  # noqa: BLE001
                try:
                    tw.tag_configure("hyper", foreground="blue", underline=True)
                except Exception:  # noqa: BLE001
                    pass

            content = tw.get("1.0", "end-1c")
            # Trim trailing punctuation often glued to URLs in prose
            url_re = re.compile(r"https?://[^\s<>\"'\]\)]+")
            url_map: dict[str, str] = {}
            n = 0
            for m in url_re.finditer(content):
                raw = m.group(0)
                url = raw.rstrip(".,;:)]}>\"'")
                if len(url) < 10:
                    continue
                tag = f"hyper_{n}"
                n += 1
                start = f"1.0+{m.start()}c"
                end = f"1.0+{m.start() + len(url)}c"
                try:
                    tw.tag_add(tag, start, end)
                    tw.tag_add("hyper", start, end)
                    url_map[tag] = url
                except Exception:  # noqa: BLE001
                    continue

            def on_click(event: Any) -> str | None:
                try:
                    idx = tw.index(f"@{event.x},{event.y}")
                    for tag in tw.tag_names(idx):
                        if tag in url_map:
                            webbrowser.open(url_map[tag])
                            self.set_status(f"Opened link: {url_map[tag][:60]}")
                            return "break"
                except Exception:  # noqa: BLE001
                    pass
                return None

            def on_motion(event: Any) -> None:
                try:
                    idx = tw.index(f"@{event.x},{event.y}")
                    if any(t in url_map for t in tw.tag_names(idx)):
                        tw.configure(cursor="hand2")
                    else:
                        tw.configure(cursor="xterm")
                except Exception:  # noqa: BLE001
                    pass

            try:
                tw.tag_bind("hyper", "<Button-1>", on_click)
                tw.bind("<Motion>", on_motion, add="+")
            except Exception:  # noqa: BLE001
                pass

        def block_edit(event: Any) -> str | None:
            # Allow navigation + copy/select-all; block typing
            if event.state & 0x4:  # Control
                if event.keysym.lower() in ("c", "a", "insert"):
                    return None
            if event.keysym in (
                "Left",
                "Right",
                "Up",
                "Down",
                "Home",
                "End",
                "Prior",
                "Next",
                "Shift_L",
                "Shift_R",
                "Control_L",
                "Control_R",
                "Alt_L",
                "Alt_R",
            ):
                return None
            return "break"

        try:
            tw.bind("<Key>", block_edit)
            tw.bind("<<Paste>>", lambda _e: "break")
            tw.bind("<<Cut>>", lambda _e: "break")
            # Double-click still selects words; Ctrl+A selects all
            tw.bind("<Control-a>", lambda e: (tw.tag_add("sel", "1.0", "end-1c"), "break"))
            tw.bind("<Control-A>", lambda e: (tw.tag_add("sel", "1.0", "end-1c"), "break"))
        except Exception:  # noqa: BLE001
            pass

    def _make_selectable_text(
        self,
        parent: Any,
        text: str,
        *,
        text_color: Any,
        wrap: int = 680,
        font_size: int = 14,
        bold: bool = False,
        mono: bool = False,
        padx: int = 4,
        pady: int = 2,
        linkify: bool = True,
        max_height: int = 1400,
    ) -> ctk.CTkTextbox:
        """Selectable, copyable message text (not a CTkLabel — those block selection)."""
        natural = self._estimate_text_height(text or "", wrap, font_size)
        cap = min(int(max_height or 1400), self._reply_view_cap())
        overflow = natural > cap + 12
        h = cap if overflow else natural
        family = "Consolas" if mono else None
        kwargs: dict[str, Any] = {
            "height": h,
            "font": ctk.CTkFont(
                size=font_size,
                weight="bold" if bold else "normal",
                **({"family": family} if family else {}),
            ),
            "text_color": text_color,
            "fg_color": "transparent",
            "border_width": 0,
            "wrap": "word" if not mono else "none",
            "activate_scrollbars": overflow,
        }
        try:
            kwargs["width"] = max(240, int(wrap or 320))
        except Exception:  # noqa: BLE001
            kwargs["width"] = 320
        tb = ctk.CTkTextbox(parent, **kwargs)
        tb.pack(fill="x", padx=padx, pady=pady)
        tb.insert("1.0", text or "")
        overflow = self._sync_textbox_height(
            tb, font_size=font_size, max_height=max_height or cap
        ) or overflow
        try:
            if overflow:
                tb.configure(activate_scrollbars=True)
        except Exception:  # noqa: BLE001
            pass
        self._linkify_and_lock_textbox(tb, linkify=linkify)
        try:
            tb.bind("<MouseWheel>", self._on_chat_mousewheel)
            tb.bind("<Button-4>", self._on_chat_mousewheel)
            tb.bind("<Button-5>", self._on_chat_mousewheel)
            inner = getattr(tb, "_textbox", None)
            if inner is not None:
                inner.bind("<MouseWheel>", self._on_chat_mousewheel)
                inner.bind("<Button-4>", self._on_chat_mousewheel)
                inner.bind("<Button-5>", self._on_chat_mousewheel)
        except Exception:  # noqa: BLE001
            pass
        return tb

    def _render_rich_message_body(
        self,
        bubble: Any,
        content: str,
        *,
        text_color: Any,
        padx: int = 14,
        wrap: int = 720,
    ) -> None:
        """Render assistant text: selectable + clickable links + light markdown."""
        from app.ui.components.markdown_lite import parse_markdown_lite
        from app.ui.themes import UI as _UI

        segs = parse_markdown_lite(content)
        if not segs:
            return
        # Single plain para → one selectable text box
        if len(segs) == 1 and segs[0].get("type") == "para":
            self._make_selectable_text(
                bubble,
                segs[0]["text"],
                text_color=text_color,
                wrap=wrap,
                font_size=15,
                padx=padx,
                pady=8,
            )
            return
        body = ctk.CTkFrame(bubble, fg_color="transparent")
        body.pack(fill="x", padx=padx, pady=(4, 6))
        for seg in segs:
            t = seg.get("type")
            txt = seg.get("text") or ""
            if t == "heading":
                lvl = int(seg.get("level") or 2)
                size = 17 if lvl == 1 else (15 if lvl == 2 else 14)
                self._make_selectable_text(
                    body,
                    txt,
                    text_color=text_color,
                    wrap=wrap,
                    font_size=size,
                    bold=True,
                    padx=4,
                    pady=(6, 2),
                )
            elif t == "code":
                lang = seg.get("lang") or ""
                frame = ctk.CTkFrame(body, fg_color=("#0f172a", "#0b1220"), corner_radius=10)
                frame.pack(fill="x", padx=2, pady=4)
                if lang:
                    ctk.CTkLabel(
                        frame,
                        text=lang,
                        font=ctk.CTkFont(size=10),
                        text_color=("#94a3b8", "#94a3b8"),
                        anchor="w",
                    ).pack(anchor="w", padx=10, pady=(6, 0))
                lines = max(1, txt.count("\n") + 1)
                h = min(320, max(48, 18 + lines * 15))
                tb = ctk.CTkTextbox(
                    frame,
                    height=h,
                    font=ctk.CTkFont(family="Consolas", size=12),
                    fg_color="transparent",
                    text_color=("#e2e8f0", "#e2e8f0"),
                    wrap="none",
                    activate_scrollbars=True,
                )
                tb.pack(fill="x", padx=6, pady=(2, 8))
                tb.insert("1.0", txt)
                # Selectable code (not disabled — disabled blocks selection on some platforms)
                self._linkify_and_lock_textbox(tb, linkify=True)
            elif t == "bullet":
                indent = int(seg.get("indent") or 0)
                pad_l = 12 + indent * 16
                self._make_selectable_text(
                    body,
                    txt,
                    text_color=text_color,
                    wrap=wrap - pad_l,
                    font_size=14,
                    padx=(pad_l, 4),
                    pady=1,
                )
            elif t == "table":
                rows = seg.get("rows") or []
                if not rows:
                    continue
                # Flatten table to selectable text (labels can't select cells well)
                lines = []
                for ri, row_cells in enumerate(rows[:30]):
                    lines.append(" | ".join(str(c) for c in row_cells))
                    if ri == 0:
                        lines.append(" | ".join("---" for _ in row_cells))
                self._make_selectable_text(
                    body,
                    "\n".join(lines),
                    text_color=text_color,
                    wrap=wrap,
                    font_size=12,
                    mono=True,
                    padx=4,
                    pady=4,
                )
            else:
                self._make_selectable_text(
                    body,
                    txt,
                    text_color=text_color,
                    wrap=wrap,
                    font_size=14,
                    padx=4,
                    pady=2,
                )

    def _display_content_for_message(self, m: dict[str, Any]) -> str:
        """Clean content for chat bubbles — strip tool blocks / raw tags users shouldn't see."""
        import re

        content = str(m.get("content") or "")
        role_l = (m.get("role") or "").lower()
        # Old chats may still store Cloudflare HTML error dumps — clean for display
        if role_l == "error" or content.strip().startswith("[Error]") or (
            "HTTP 524" in content and "<" in content
        ):
            try:
                from app.core.services.llm.llm import format_llm_error_message

                return format_llm_error_message(content.replace("[Error]", "", 1).strip())
            except Exception:  # noqa: BLE001
                pass
        # Universal strip (<<<TOOL>>> + <tool_call> etc.) — answers must not show tool code
        try:
            from app.core.services.chat.chat import strip_tool_blocks_for_display

            if role_l == "assistant" or m.get("_strip_tools_ui"):
                content = strip_tool_blocks_for_display(content)
        except Exception:  # noqa: BLE001
            pass
        # Strip residual media markers (already rendered as images)
        content = re.sub(
            r"<<<(?:SHOW_)?IMAGE>>>.*?<<<END_(?:SHOW_)?IMAGE>>>",
            "",
            content,
            flags=re.I | re.S,
        )
        content = re.sub(
            r"<<<(?:SHOW_)?VIDEO>>>.*?<<<END_(?:SHOW_)?VIDEO>>>",
            "",
            content,
            flags=re.I | re.S,
        )
        # Hide internal tool instruction blocks from assistant text if any leaked
        for tag in (
            "TERMINAL",
            "SKILL",
            "MCP",
            "BROWSER",
            "KNOWLEDGE",
            "SELF_IMPROVE",
            "BACKUP",
            "ROLLBACK",
            "IMAGE_GEN",
            "ORG",
            "PIP",
            "GUI",
            "SCREENSHOT",
            "CLIPBOARD",
            "WINDOWS",
            "WEB_SEARCH",
            "WEB_FETCH",
            "WEB_CRAWL",
            "WEB_SCRAPE",
            "WEB_DOWNLOAD",
            "DEEP_RESEARCH",
            "OCR",
            "PATCH_REVIEW",
            "WRITE_FILE",
            "READ_FILE",
            "SEARCH_REPLACE",
            "LIST_DIR",
            "GREP",
        ):
            content = re.sub(
                rf"<<<{tag}>>>.*?<<<END_{tag}>>>",
                "",
                content,
                flags=re.I | re.S,
            )
        content = re.sub(
            r"<<<(?:SET_GOAL|END_SET_GOAL|FINDING|END_FINDING|"
            r"RESOLVE_FINDING|END_RESOLVE_FINDING|REOPEN_FINDING|END_REOPEN_FINDING)>>>",
            "",
            content,
            flags=re.I,
        )
        content = re.sub(r"\n{3,}", "\n\n", content).strip()
        raw = str(m.get("content") or "")
        dump = False
        try:
            from app.core.services.chat.chat import looks_like_tool_dump, strip_tool_blocks_for_display

            dump = looks_like_tool_dump(raw)
            content = strip_tool_blocks_for_display(content)
        except Exception:  # noqa: BLE001
            pass
        leftover_dump = False
        try:
            from app.core.services.chat.chat import looks_like_file_dump_for_ui

            leftover_dump = looks_like_file_dump_for_ui(raw) or "<<<" in (content or "")
        except Exception:  # noqa: BLE001
            leftover_dump = bool(
                dump
                or "<<<" in (content or "")
                or "@'" in raw
                or '@"' in raw
                or "$content" in raw
            )
        if leftover_dump:
            prose = re.sub(r"\s+", " ", content).strip()
            if len(prose) > 180:
                prose = prose[:180].rstrip() + "…"
            if not prose or dump:
                prose = (
                    str(getattr(self, "_now_doing_text", "") or "").strip()
                    or "Working with tools."
                )
            return prose + "\n\n_(Details are in Live → Thinking / Terminal.)_"
        # Keep the full answer in the bubble; long replies scroll inside
        _max = 20000
        if len(content) > _max:
            content = content[:_max].rstrip() + "\n\n…(very long — rest is in Live / copy)"
        return content

    def _paint_chat_render_fallback(self, exc: BaseException) -> None:
        """Never leave a white hole — paint last turns even if the scroll died."""
        parent = None
        if self._ensure_chat_scroll():
            parent = self.chat_scroll
        else:
            mid = getattr(self, "_chat_mid", None)
            try:
                if mid is not None and bool(mid.winfo_exists()):
                    parent = mid
            except Exception:  # noqa: BLE001
                parent = None
        if parent is None:
            return
        try:
            for child in list(parent.winfo_children()):
                try:
                    child.destroy()
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            pass
        try:
            import traceback
            from pathlib import Path as _P

            err = f"Chat render failed:\n{exc}\n{traceback.format_exc()[-700:]}"
            (_P(data_dir()) / "_chat_render_debug.txt").write_text(err, encoding="utf-8")
        except Exception:  # noqa: BLE001
            err = f"Chat render failed: {exc}"
        try:
            ctk.CTkLabel(
                parent,
                text="Could not draw the full chat. Last messages:",
                anchor="w",
                justify="left",
            ).pack(anchor="w", padx=16, pady=(16, 6))
        except Exception:  # noqa: BLE001
            pass
        import re

        msgs = list((getattr(self, "_chat_state", None) or {}).get("messages") or [])
        shown = 0
        for m in reversed(msgs):
            role = str(m.get("role") or "")
            if role not in ("user", "assistant"):
                continue
            text = re.sub(r"\s+", " ", str(m.get("content") or "")).strip()
            if not text:
                continue
            if len(text) > 400:
                text = text[:400].rstrip() + "…"
            try:
                ctk.CTkLabel(
                    parent,
                    text=f"{role}: {text}",
                    anchor="w",
                    justify="left",
                    wraplength=560,
                ).pack(anchor="w", padx=16, pady=4)
            except Exception:  # noqa: BLE001
                break
            shown += 1
            if shown >= 6:
                break
        try:
            ctk.CTkLabel(
                parent,
                text=err[:500],
                anchor="w",
                justify="left",
                wraplength=560,
            ).pack(anchor="w", padx=16, pady=10)
        except Exception:  # noqa: BLE001
            pass

    def _chat_render_transcript(self) -> None:
        gen = int(getattr(self, "_chat_page_gen", 0) or 0)
        if not self._ensure_chat_scroll():
            return
        try:
            self._chat_render_transcript_body()
        except Exception as e:  # noqa: BLE001
            if int(getattr(self, "_chat_page_gen", 0) or 0) != gen:
                return
            try:
                self._paint_chat_render_fallback(e)
            except Exception:  # noqa: BLE001
                pass

    def _chat_render_transcript_body(self) -> None:
        paint_gen = int(getattr(self, "_chat_page_gen", 0) or 0)
        if not (self._chat_state or {}).get("messages"):
            try:
                self._chat_state = self._load_active_chat()
            except Exception:  # noqa: BLE001
                pass
        # Grok: only auto-jump to bottom if user was already following the latest messages
        stick_bottom = bool(getattr(self, "_chat_user_pinned_bottom", True)) or self._chat_near_bottom()
        saved_yview: tuple[float, float] | None = None
        if not stick_bottom:
            try:
                c0 = self._chat_canvas()
                if c0 is not None:
                    saved_yview = c0.yview()  # type: ignore[assignment]
            except Exception:  # noqa: BLE001
                saved_yview = None

        busy = bool(getattr(self, "_chat_busy", False))
        # Never mutate the stored history here. Paint a growing tail so "From start"
        # can reach message 1 (hard-coded last-80 used to hide the inception).
        stored = list(self._chat_state.get("messages") or [])
        total_stored = len(stored)
        if busy:
            tail_n = 36
        else:
            tail_n = int(getattr(self, "_chat_history_window", 80) or 80)
            tail_n = max(20, min(max(total_stored, 20), tail_n))
        all_messages = stored[-tail_n:] if total_stored > tail_n else list(stored)
        older_stored = max(0, total_stored - len(all_messages))
        if not busy and tail_n <= 160:
            try:
                from app.core.services.chat.media_chat import enrich_message_with_media
                from app.core.services.chat.chat_store import get_active_chat_id

                cid = get_active_chat_id() or "default"
                fixed = []
                for m in all_messages:
                    mm = dict(m)
                    content_u = str(mm.get("content") or "").upper()
                    if mm.get("role") in ("assistant", "user", "screenshot") and (
                        "<<<IMAGE>>>" in content_u
                        or "<<<VIDEO>>>" in content_u
                        or "![" in str(mm.get("content") or "")
                    ):
                        mm = enrich_message_with_media(mm, chat_id=cid)
                    fixed.append(mm)
                all_messages = fixed
            except Exception:  # noqa: BLE001
                pass
            try:
                from app.core.services.chat.chat import finalize_history_for_display

                all_messages = finalize_history_for_display(all_messages)
            except Exception:  # noqa: BLE001
                pass

        show_tools = bool(getattr(self, "_chat_show_tools", False))
        tool_roles = set(self._TOOL_ROLES)

        # Build display sequence BEFORE wiping the canvas.
        display_items: list[tuple[str, Any]] = []
        pending_tools: list[dict[str, Any]] = []

        def flush_tools() -> None:
            nonlocal pending_tools
            if pending_tools:
                has_edit = any(
                    isinstance(m.get("file_diff"), dict) and m.get("file_diff")
                    for m in pending_tools
                )
                if has_edit:
                    display_items.append(("file_edits", list(pending_tools)))
                if show_tools:
                    display_items.append(("trace", list(pending_tools)))
                else:
                    display_items.append(("activity", list(pending_tools)))
                pending_tools = []

        def _is_hidden_asst(msg: dict[str, Any]) -> bool:
            if msg.get("_hide_ui") or msg.get("_tool_round") or msg.get("_tool_intent_only"):
                return True
            return False

        for m in all_messages:
            role = (m.get("role") or "").lower()
            if role == "assistant" and _is_hidden_asst(m):
                continue
            is_tool = role in tool_roles and not m.get("images")
            if role in tool_roles and m.get("images"):
                flush_tools()
                display_items.append(("message", m))
            elif is_tool or role in ("org_agent", "harness"):
                pending_tools.append(m)
            elif role == "error":
                flush_tools()
                display_items.append(("message", m))
            elif role == "thinking":
                # Folded into the next assistant bubble (not a separate window)
                continue
            else:
                flush_tools()
                display_items.append(("message", m))
        flush_tools()
        if not display_items:
            # Hidden tool-round tails used to leave a white hole (no empty-state either)
            for m in reversed(all_messages):
                role = (m.get("role") or "")
                if role in ("user", "assistant") and not (
                    m.get("_hide_ui") or m.get("_tool_round") or m.get("_tool_intent_only")
                ):
                    display_items.append(("message", m))
                    if sum(1 for x in display_items if x[0] == "message") >= 8:
                        break
            display_items.reverse()
        if not display_items:
            for m in reversed(stored[-24:] if stored else []):
                if (m.get("role") or "") in ("user", "assistant"):
                    mm = dict(m)
                    mm.pop("_hide_ui", None)
                    mm.pop("_tool_round", None)
                    display_items.append(("message", mm))
                    if len(display_items) >= 6:
                        break
            display_items.reverse()

        if int(getattr(self, "_chat_page_gen", 0) or 0) != paint_gen:
            return
        if not self._ensure_chat_scroll():
            return
        try:
            for child in list(self.chat_scroll.winfo_children()):
                try:
                    child.destroy()
                except Exception:  # noqa: BLE001
                    pass
        except Exception as exc:  # noqa: BLE001
            if not self._ensure_chat_scroll():
                raise exc
        self._stream_bubble_label = None

        if not all_messages:
            # Grok empty state (from live Chrome): wordmark + “What's on your mind?” + chips
            from app.ui.themes import style_chrome_button, UI as _UI
            from app.ui.components.layman_copy import (
                STATUS_STARTER,
                EMPTY_CHAT_TITLE,
                EMPTY_CHAT_WORDMARK,
            )

            # Grok empty state: wordmark + question + suggestion chips (centered)
            pad = self._chat_side_pad()
            empty = ctk.CTkFrame(self.chat_scroll, fg_color="transparent")
            empty.pack(fill="both", expand=True, padx=pad, pady=32)
            ctk.CTkLabel(
                empty,
                text=EMPTY_CHAT_WORDMARK,
                font=ctk.CTkFont(size=36, weight="bold"),
                text_color=_UI["label"],
            ).pack(anchor="center", pady=(56, 6))
            ctk.CTkLabel(
                empty,
                text=EMPTY_CHAT_TITLE,
                font=ctk.CTkFont(size=22),
                text_color=_UI["muted"],
            ).pack(anchor="center", pady=(0, 28))
            try:
                from app.core.services.llm.providers import has_active_api_key

                key_ok = has_active_api_key()
            except Exception:  # noqa: BLE001
                key_ok = bool((storage.load_config().get("api_key") or "").strip())
            if not key_ok:
                ctk.CTkButton(
                    empty,
                    text="Connect AI account first",
                    width=220,
                    height=38,
                    corner_radius=19,
                    command=self._show_onboarding_wizard,
                    **style_chrome_button(primary=True),
                ).pack(anchor="center", pady=10)

            def use_starter(s: str) -> None:
                if hasattr(self, "chat_input"):
                    from app.ui.themes import UI as _UIp

                    self._composer_is_placeholder = False
                    self.chat_input.delete("1.0", "end")
                    self.chat_input.insert("1.0", s)
                    try:
                        self.chat_input.configure(
                            text_color=_UIp.get("composer_text", _UIp["label"])
                        )
                    except Exception:  # noqa: BLE001
                        pass
                    self.chat_input.focus_set()
                    self.set_status(STATUS_STARTER, toast=True)

            starter_list = (
                "What can you do on this PC?",
                "Search the web for today’s AI news",
                "List files on my Desktop",
                "Make an image of a cute orange cat",
            )
            # 2×2 chip grid (Grok / ChatGPT suggestion style)
            starters = ctk.CTkFrame(empty, fg_color="transparent")
            starters.pack(anchor="center", pady=8)
            for i, s in enumerate(starter_list):
                r, c = divmod(i, 2)
                cell = ctk.CTkFrame(starters, fg_color="transparent")
                cell.grid(row=r, column=c, padx=6, pady=6, sticky="ew")
                ctk.CTkButton(
                    cell,
                    text=s[:48] + ("…" if len(s) > 48 else ""),
                    height=40,
                    width=260,
                    corner_radius=20,
                    border_width=1,
                    border_color=_UI.get("composer_border", ("#e5e5e5", "#2a2a2a")),
                    # CTk 6.x: use string "transparent", not ("transparent","transparent")
                    # — tuple form crashes empty-chat render (new chat / folder +)
                    fg_color="transparent",
                    hover_color=("#f4f4f5", "#1f1f1f"),
                    text_color=_UI["label"],
                    anchor="w",
                    command=lambda t=s: use_starter(t),
                ).pack(fill="x")
            return

        visible_items = display_items

        if older_stored or (not busy and total_stored > 80):
            from app.ui.themes import style_chrome_button, UI as _UI

            load_bar = ctk.CTkFrame(self.chat_scroll, fg_color="transparent")
            load_bar.pack(fill="x", padx=16, pady=(10, 6))
            if older_stored:
                label = (
                    f"Showing last {len(all_messages)} of {total_stored} messages "
                    f"({older_stored} older)"
                )
            else:
                label = f"Showing all {total_stored} messages from the start"
            ctk.CTkLabel(
                load_bar,
                text=label,
                text_color=_UI["muted"],
                font=ctk.CTkFont(size=12),
            ).pack(side="left", padx=6)
            if older_stored:
                ctk.CTkButton(
                    load_bar,
                    text="Load older (+120)",
                    width=140,
                    height=28,
                    command=self._chat_load_older_messages,
                    **style_chrome_button(primary=True),
                ).pack(side="left", padx=4)
            ctk.CTkButton(
                load_bar,
                text="From start",
                width=96,
                height=28,
                command=self._chat_show_from_start,
                **style_chrome_button(primary=bool(older_stored)),
            ).pack(side="left", padx=4)

        for item_kind, payload in visible_items:
            if item_kind == "file_edits":
                try:
                    self._render_file_edit_chips(self.chat_scroll, list(payload or []))
                except Exception:  # noqa: BLE001
                    pass
                continue
            if item_kind == "activity":
                try:
                    self._render_chat_activity_lines(self.chat_scroll, list(payload or []))
                except Exception:  # noqa: BLE001
                    pass
                continue
            if item_kind == "trace":
                # Only when "Show tools" is on (default OFF → Grok clean chat)
                if not show_tools:
                    continue
                tool_msgs = payload
                self._render_collapsible_tool_trace(
                    self.chat_scroll, tool_msgs, expanded=True
                )
                continue

            m = payload
            try:
                full_idx = all_messages.index(m)
            except ValueError:
                full_idx = 0
            role = m.get("role") or "user"
            # Hidden intermediate tool-call assistants / sticky echoes / tool rounds
            if m.get("_hide_ui") or m.get("_tool_intent_only") or m.get("_tool_round"):
                continue
            if str(role).lower() == "thinking":
                continue
            content = self._display_content_for_message(m)
            kind = self._chat_bubble_kind(str(role))
            # Skip intermediate tool-round assistants if finalize flags were missed
            if kind == "assistant":
                try:
                    from app.core.services.chat.chat import (
                        has_tool_call_markup,
                        is_tool_intent_only_assistant,
                        strip_tool_blocks_for_display,
                    )

                    later_final = any(
                        (
                            x.get("role") == "assistant"
                            and not x.get("_hide_ui")
                            and not x.get("_tool_round")
                            and not x.get("_tool_intent_only")
                            and x is not m
                        )
                        for x in all_messages[full_idx + 1 :]
                    )
                    # Any assistant that still has tool markup + a later final → hide
                    if later_final and (
                        is_tool_intent_only_assistant(str(m.get("content") or ""))
                        or has_tool_call_markup(str(m.get("content") or ""))
                    ):
                        continue
                    # Never paint raw <<<TOOL>>> blocks in the answer bubble
                    if has_tool_call_markup(str(m.get("content") or "")) or m.get(
                        "_strip_tools_ui"
                    ):
                        content = strip_tool_blocks_for_display(
                            str(m.get("content") or "")
                        ) or content
                except Exception:  # noqa: BLE001
                    pass
            # Org agent details only when tools are shown
            if str(role).lower() == "org_agent":
                if show_tools:
                    self._render_collapsible_tool_trace(
                        self.chat_scroll,
                        [m],
                        expanded=False,
                    )
                continue
            # Empty after strip → skip (was tool-only noise)
            think = None
            if kind == "assistant":
                think = self._thinking_attached_to(all_messages, full_idx)
            if kind == "assistant" and not (content or "").strip() and not m.get("images") and not think and not m.get("compare"):
                continue
            if m.get("compare") and m.get("compare_results"):
                try:
                    self._render_compare_arena(self.chat_scroll, m)
                except Exception:  # noqa: BLE001
                    pass
                continue
            self._render_grok_chat_bubble(
                self.chat_scroll,
                m,
                kind=kind,
                content=content,
                full_idx=full_idx,
                thinking=think,
            )

        # Bottom spacer so last bubble isn't flush against the edge
        try:
            spacer = ctk.CTkFrame(self.chat_scroll, fg_color="transparent", height=28)
            spacer.pack(fill="x")
            spacer.pack_propagate(False)
        except Exception:  # noqa: BLE001
            pass

        # Re-bind wheel (replace handlers — nested textboxes no longer trap scroll)
        try:
            self._bind_wheel_tree(self.chat_scroll)
        except Exception:  # noqa: BLE001
            pass
        try:
            self._fit_chat_scroll_inner()
            self.after(40, self._fit_chat_scroll_inner)
        except Exception:  # noqa: BLE001
            pass

        if stick_bottom:
            self._chat_scroll_to_end(force=True)
            # One follow after layout — a burst of after()s made the list jump forever
            self.after(60, lambda: self._chat_scroll_to_end(force=True))
        elif saved_yview is not None:
            # Restore approximate position after re-render
            def _restore() -> None:
                try:
                    c = self._chat_canvas()
                    if c is None or not saved_yview:
                        return
                    self.chat_scroll.update_idletasks()
                    bb = c.bbox("all")
                    if bb:
                        c.configure(scrollregion=bb)
                    c.yview_moveto(float(saved_yview[0]))
                    self._update_jump_latest_fab()
                except Exception:  # noqa: BLE001
                    pass

            self.after(20, _restore)
            self.after(100, _restore)
        else:
            self._update_jump_latest_fab()
        # Task #12: keep Artifacts tab current after re-render
        try:
            if (
                getattr(self, "side_panel_mode", None)
                and self.side_panel_mode.get() == "Artifacts"
                and getattr(self, "_live_panel_visible", False)
            ):
                self._refresh_artifacts_panel()
        except Exception:  # noqa: BLE001
            pass

    def _format_msg_time(self, iso: str) -> str:
        if not iso:
            return ""
        try:
            # show local-ish short time from ISO
            s = str(iso)
            if "T" in s:
                date_part, time_part = s.split("T", 1)
                time_part = time_part.replace("Z", "").split("+")[0][:8]
                # if today-ish just time; always show date+time short
                return f"{date_part[5:]} {time_part}"
            return s[:16]
        except Exception:  # noqa: BLE001
            return str(iso)[:16]

    def _chat_scroll_to_end(self, force: bool = False) -> None:
        """
        Scroll to latest message (Grok: follow stream only when pinned to bottom).
        force=True after send / full re-render of a new turn.
        During live streaming, avoid double update_idletasks (main freeze source).
        """
        if not force and not getattr(self, "_chat_user_pinned_bottom", True):
            return
        try:
            import time as _time

            now = _time.monotonic()
            last = float(getattr(self, "_chat_scroll_end_ts", 0) or 0)
            # Busy follow: at most ~4 Hz so the list is not stuck jumping
            if not force and now - last < 0.25:
                return
            self._chat_scroll_end_ts = now
            if not hasattr(self, "chat_scroll") or not self.chat_scroll.winfo_exists():
                return
            canvas = self._chat_canvas()
            if canvas is None:
                return
            if not force:
                try:
                    _y0, y1 = canvas.yview()
                    if float(y1) >= 0.995:
                        return
                except Exception:  # noqa: BLE001
                    pass
            light = bool(getattr(self, "_chat_busy", False)) and not force
            if light:
                # Cheap follow: no forced full geometry recalc (keeps UI responsive)
                try:
                    canvas.yview_moveto(1.0)
                except Exception:  # noqa: BLE001
                    pass
                return
            # Full layout pass only when force (send / final render)
            self.chat_scroll.update_idletasks()
            canvas.update_idletasks()
            try:
                bbox = canvas.bbox("all")
                if bbox:
                    canvas.configure(scrollregion=bbox)
            except Exception:  # noqa: BLE001
                pass
            canvas.yview_moveto(1.0)
            self._chat_user_pinned_bottom = True
            self._update_jump_latest_fab()
        except Exception:  # noqa: BLE001
            pass

    def _ensure_stream_bubble(self, agent_label: str) -> None:
        """Grok-style live typing: flat assistant column, avatar, no heavy card."""
        from app.ui.themes import UI as _UI

        self._stream_bubble_label = None
        if not hasattr(self, "chat_scroll") or not self.chat_scroll.winfo_exists():
            return
        bg, fg = _BUBBLE.get("assistant", _BUBBLE["assistant"])
        accent = _BUBBLE_ACCENT["assistant"]
        side_pad = self._chat_side_pad()
        row = ctk.CTkFrame(self.chat_scroll, fg_color="transparent")
        row.pack(fill="x", padx=side_pad, pady=8)
        line = ctk.CTkFrame(row, fg_color="transparent")
        line.pack(anchor="w", fill="x")
        av_wrap = ctk.CTkFrame(line, width=40, height=40, fg_color="transparent")
        av_wrap.pack(side="left", padx=(0, 10))
        av_wrap.pack_propagate(False)
        av = ctk.CTkFrame(av_wrap, width=36, height=36, corner_radius=18, fg_color=accent)
        av.place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(
            av,
            text="G",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=("#0a0f1a", "#0a0f1a"),
        ).place(relx=0.5, rely=0.5, anchor="center")
        bubble = ctk.CTkFrame(line, fg_color=bg, corner_radius=0, border_width=0)
        bubble.pack(side="left", fill="x", expand=True, padx=(0, 48))
        ctk.CTkLabel(
            bubble,
            text=f"{agent_label or 'Assistant'}  ·  writing…",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=_UI["muted"],
            anchor="w",
        ).pack(fill="x", padx=4, pady=(2, 0))
        # Tall enough stream area so you can read the reply while it types
        try:
            stream_h = max(160, min(520, int(self.winfo_height() or 800) // 3))
        except Exception:  # noqa: BLE001
            stream_h = 200
        tb = ctk.CTkTextbox(
            bubble,
            height=stream_h,
            font=ctk.CTkFont(size=15),
            text_color=fg,
            fg_color=bg,
            border_width=0,
            wrap="word",
            activate_scrollbars=True,
        )
        tb.pack(fill="both", expand=True, padx=4, pady=(6, 10))
        self._linkify_and_lock_textbox(tb, linkify=False)
        try:
            bind_smooth_text_wheel(tb, on_edge=self._on_chat_mousewheel)
        except Exception:  # noqa: BLE001
            pass
        self._stream_bubble_label = tb
        self._stream_bubble_row = row
        try:
            self._append_thinking_step("✍ Writing final answer (streaming)…")
        except Exception:  # noqa: BLE001
            pass
        self._bind_wheel_tree(row)
        self._chat_user_pinned_bottom = True
        self._chat_scroll_to_end(force=True)

    def _copy_text(self, text: str) -> None:
        try:
            self.clipboard_clear()
            self.clipboard_append(text or "")
            self.set_status("Copied to clipboard")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Copy", str(e), parent=self)

    def _chat_edit_message(self, index: int) -> None:
        msgs = list(self._chat_state.get("messages") or [])
        if index < 0 or index >= len(msgs):
            return
        m = msgs[index]
        old = str(m.get("content") or "")
        win = ctk.CTkToplevel(self)
        win.title("Edit message")
        win.geometry("640x400")
        win.transient(self)
        box = ctk.CTkTextbox(win, wrap="word")
        box.pack(fill="both", expand=True, padx=12, pady=12)
        box.insert("1.0", old)

        def save() -> None:
            new = box.get("1.0", "end").strip()
            msgs[index]["content"] = new
            msgs[index]["edited"] = True
            msgs[index]["at"] = msgs[index].get("at") or ""
            self._chat_state["messages"] = msgs
            chat_svc.save_chat(self._chat_state)
            win.destroy()
            self._chat_render_transcript()
            self.set_status("Message edited")

        ctk.CTkButton(win, text="Save edit", command=save).pack(pady=8)

    def _chat_reply_to(self, snippet: str) -> None:
        if not hasattr(self, "chat_input"):
            return
        quote = (snippet or "").strip().replace("\n", " ")
        if len(quote) > 200:
            quote = quote[:200] + "…"
        prefix = f'> Re: "{quote}"\n\n'
        if getattr(self, "_composer_is_placeholder", False):
            cur = ""
        else:
            cur = self.chat_input.get("1.0", "end").strip()
        self._composer_set_text(prefix + cur)
        self.chat_input.focus_set()
        self.set_status("Reply quote inserted")

    def _chat_regenerate(self, index: int) -> None:
        """Re-send from the last user message before this assistant turn."""
        if self._chat_busy:
            return
        msgs = list(self._chat_state.get("messages") or [])
        if index < 0 or index >= len(msgs):
            return
        # find preceding user message
        user_text = ""
        cut = index
        for i in range(index - 1, -1, -1):
            if msgs[i].get("role") == "user":
                user_text = str(msgs[i].get("content") or "")
                cut = i
                break
        if not user_text:
            messagebox.showinfo("Regenerate", "No prior user message found.", parent=self)
            return
        # drop this assistant and everything after the user message stay, remove after cut+1
        self._chat_state["messages"] = msgs[: cut + 1]
        chat_svc.save_chat(self._chat_state)
        if hasattr(self, "chat_input"):
            self._composer_set_text(user_text)
        # remove the last user from history so send re-adds it
        self._chat_state["messages"] = msgs[:cut]
        chat_svc.save_chat(self._chat_state)
        self._chat_render_transcript()
        self._chat_send()

    def _chat_rename(self) -> None:
        cid = self._chat_state.get("id") or chat_store.get_active_chat_id()
        if not cid:
            return
        cur = self._chat_state.get("title") or "Chat"
        name = simpledialog.askstring("Rename chat", "Chat name:", initialvalue=cur, parent=self)
        if name is None:
            return
        name = name.strip() or cur
        chat_store.rename_chat(cid, name)
        self._chat_state = chat_svc.load_chat(cid)
        if hasattr(self, "chat_title_label"):
            pin = "📌 " if self._chat_state.get("pinned") else ""
            self.chat_title_label.configure(text=f"{pin}{name}")
        self.set_status(f"Renamed chat → {name}")
        # refresh switcher labels if on chat page
        if self._current_page == "Chat":
            self.show_page("Chat")

    def _refresh_context_chip(self) -> None:
        """Update the Context chip on the cycle bar (and Comfort bar if present)."""
        try:
            from app.core.services.llm.model_params import get_model_params
            from app.core.services.llm.model_limits import get_model_limits

            p = get_model_params()
            lim = get_model_limits(refresh=False)
            ctx = int(p.get("context_window") or 0)
            mx = int(lim.get("context_length") or 0)
            mt = int(p.get("max_tokens") or 0)
            ov = ""
            try:
                if (self._chat_state or {}).get("use_context_override"):
                    ov = " · edited"
            except Exception:  # noqa: BLE001
                ov = ""
            text = f"ctx {ctx:,}" + (f"/{mx:,}" if mx else "") + f" · resp={mt or 'auto'}{ov}"
        except Exception:  # noqa: BLE001
            text = "ctx ?"
        for attr in ("_ctx_chip_lbl", "_ctx_chip_lbl_modes"):
            lbl = getattr(self, attr, None)
            try:
                if lbl is not None and bool(lbl.winfo_exists()):
                    lbl.configure(text=text)
            except Exception:  # noqa: BLE001
                pass

    def _chat_context_window_dialog(self) -> None:
        """Always-visible Context editor: window size + the prompt the model will see."""
        from app.core.services.llm.model_params import get_model_params, save_model_params
        from app.core.services.llm.model_limits import get_model_limits
        from app.core.services.chat.context_edit import (
            format_api_context,
            parse_api_context,
            preview_chat_context,
        )
        from app.core.services.misc.default_prompts import get_default_system_prompt
        from app.ui.themes import UI as _UI, style_chrome_button, style_textbox

        p = get_model_params()
        win = ctk.CTkToplevel(self)
        win.title("Context window & content")
        win.geometry("920x720")
        win.transient(self)
        try:
            win.lift()
            win.focus_force()
        except Exception:  # noqa: BLE001
            pass
        form = ctk.CTkFrame(win)
        form.pack(fill="both", expand=True, padx=16, pady=16)

        info = ctk.CTkLabel(
            form,
            text="Fetching model limits…",
            text_color=_UI["muted"],
            wraplength=860,
            justify="left",
            anchor="w",
        )
        info.pack(anchor="w", padx=4, pady=(0, 8))

        lim_state: dict[str, Any] = {"lim": None}

        def load_limits(force: bool = False) -> None:
            try:
                lim = get_model_limits(refresh=force)
                lim_state["lim"] = lim
                info.configure(
                    text=(
                        f"Model: {lim.get('model') or '?'}\n"
                        f"Max context (provider/heuristic): {int(lim.get('context_length') or 0):,} tokens\n"
                        f"Max response completion: {int(lim.get('max_completion_tokens') or 0):,} tokens\n"
                        f"Source: {lim.get('source')}\n"
                        f"Recommended context ≤ {int(lim.get('recommended_context') or 0):,} · "
                        f"response ≤ {int(lim.get('recommended_max_tokens') or 0):,}"
                    )
                )
            except Exception as e:  # noqa: BLE001
                info.configure(text=f"Could not fetch model limits: {e}")

        # Fetch async so dialog opens fast
        def bg_fetch() -> None:
            load_limits(force=True)
            try:
                self.after(0, lambda: None)
            except Exception:  # noqa: BLE001
                pass

        threading.Thread(target=bg_fetch, daemon=True).start()
        load_limits(force=False)

        fields_frame = ctk.CTkFrame(form, fg_color="transparent")
        fields_frame.pack(fill="x", pady=8)
        ctx_var = ctk.StringVar(value=str(int(p.get("context_window") or 128000)))
        res_var = ctk.StringVar(value=str(int(p.get("context_reserve_reply") or 8000)))
        max_tok_var = ctk.StringVar(value=str(int(p.get("max_tokens") or 0)))

        def row(label: str, var: ctk.StringVar, r: int) -> None:
            ctk.CTkLabel(fields_frame, text=label, text_color=_UI["label"]).grid(
                row=r, column=0, sticky="w", padx=4, pady=6
            )
            ctk.CTkEntry(fields_frame, textvariable=var, width=160).grid(
                row=r, column=1, sticky="w", padx=4, pady=6
            )

        row("Context window (tokens)", ctx_var, 0)
        row("Reserve for reply", res_var, 1)
        row("Max response tokens (0 = provider default)", max_tok_var, 2)

        ctk.CTkLabel(
            form,
            text=(
                "Context window = how many tokens the model can take. "
                "The box below is the actual prompt (### system / ### user / ### assistant). "
                "Edit it, then Save content. Tick “Use edited context on next send” to send this instead of auto-built history."
            ),
            text_color=_UI["muted"],
            wraplength=860,
            justify="left",
        ).pack(anchor="w", padx=4, pady=(2, 6))

        use_ov = ctk.BooleanVar(
            value=bool((self._chat_state or {}).get("use_context_override"))
        )
        llm_sum = ctk.BooleanVar(value=bool(storage.load_config().get("agent_context_llm_summary", False)))
        ctk.CTkCheckBox(
            form,
            text="Use edited context on next send",
            variable=use_ov,
        ).pack(anchor="w", padx=4, pady=(0, 2))
        ctk.CTkCheckBox(
            form,
            text="Auto-compact: LLM-polish the rolling summary (extractive compact is always on)",
            variable=llm_sum,
        ).pack(anchor="w", padx=4, pady=(0, 4))
        compact_lbl = ctk.CTkLabel(
            form,
            text="Auto-compact is always on at send: older turns become a rolling summary when the prompt exceeds min(your window, model max). That avoids a silent hard truncate.",
            text_color=_UI["muted"],
            wraplength=860,
            justify="left",
        )
        compact_lbl.pack(anchor="w", padx=4, pady=(0, 4))

        body = ctk.CTkTextbox(form, wrap="word", height=340, **style_textbox())
        body.pack(fill="both", expand=True, padx=2, pady=4)

        def _sys_for_preview() -> str:
            try:
                sys_p = str((self._chat_state or {}).get("system_prompt") or "").strip()
            except Exception:  # noqa: BLE001
                sys_p = ""
            return sys_p or get_default_system_prompt()

        def reload_body() -> None:
            try:
                st = self._chat_state or {}
                if st.get("context_override_text") and st.get("use_context_override"):
                    txt = str(st.get("context_override_text") or "")
                else:
                    msgs = preview_chat_context(
                        list(st.get("messages") or []),
                        system_prompt=_sys_for_preview(),
                    )
                    txt = format_api_context(msgs)
                body.delete("1.0", "end")
                body.insert("1.0", txt or "(empty context)")
            except Exception as e:  # noqa: BLE001
                body.delete("1.0", "end")
                body.insert("1.0", f"(could not load context: {e})")

        reload_body()

        def compact_now() -> None:
            try:
                from app.core.services.llm.model_params import trim_messages_to_context
                from app.core.services.chat.chat_store import get_active_chat_id

                msgs = preview_chat_context(
                    list((self._chat_state or {}).get("messages") or []),
                    system_prompt=_sys_for_preview(),
                )
                cid = get_active_chat_id() or ""
                packed = trim_messages_to_context(msgs, chat_id=cid, update_summary=True)
                body.delete("1.0", "end")
                body.insert("1.0", format_api_context(packed))
                use_ov.set(True)
                compact_lbl.configure(
                    text=f"Compacted now: {len(msgs)} → {len(packed)} messages. "
                    "Tick is on — Save all to use this on the next send."
                )
            except Exception as e:  # noqa: BLE001
                compact_lbl.configure(text=f"Compact failed: {e}")

        btns = ctk.CTkFrame(form, fg_color="transparent")
        btns.pack(fill="x", pady=8)

        def save() -> None:
            try:
                raw = {
                    "context_window": int(float(ctx_var.get())),
                    "context_reserve_reply": int(float(res_var.get())),
                    "max_tokens": int(float(max_tok_var.get())),
                }
            except ValueError:
                messagebox.showerror("Context", "Invalid number", parent=win)
                return
            lim = lim_state.get("lim") or get_model_limits()
            mx = int(lim.get("context_length") or 0)
            if mx and raw["context_window"] > mx:
                if not messagebox.askyesno(
                    "Above model max",
                    f"Context {raw['context_window']:,} exceeds model max {mx:,}.\n"
                    "Save anyway? (API may reject oversized prompts)",
                    parent=win,
                ):
                    return
            mo = int(lim.get("max_completion_tokens") or 0)
            if mo and raw["max_tokens"] > mo:
                if not messagebox.askyesno(
                    "Above model max",
                    f"Max tokens {raw['max_tokens']:,} exceeds model max {mo:,}. Save anyway?",
                    parent=win,
                ):
                    return
            cur = get_model_params()
            cur.update(raw)
            save_model_params(cur)
            try:
                cfg = storage.load_config()
                cfg["context_window_locked"] = True
                cfg["agent_context_llm_summary"] = bool(llm_sum.get())
                storage.save_config(cfg)
            except Exception:  # noqa: BLE001
                pass
            txt = ""
            try:
                txt = body.get("1.0", "end-1c")
            except Exception:  # noqa: BLE001
                txt = ""
            parsed = parse_api_context(txt)
            if getattr(self, "_chat_state", None) is None:
                self._chat_state = {}
            self._chat_state["context_override_text"] = txt
            self._chat_state["context_override_messages"] = parsed
            self._chat_state["use_context_override"] = bool(use_ov.get())
            try:
                chat_svc.save_chat(self._chat_state)
            except Exception:  # noqa: BLE001
                pass
            self._refresh_context_chip()
            win.destroy()
            extra = " · using edited content" if use_ov.get() else ""
            self.set_status(
                f"Context {raw['context_window']:,} · reserve {raw['context_reserve_reply']:,} · "
                f"max_tokens {raw['max_tokens']}{extra}",
                toast=True,
            )

        def use_model_max_ctx() -> None:
            lim = lim_state.get("lim") or get_model_limits(refresh=True)
            lim_state["lim"] = lim
            load_limits(force=False)
            res = int(float(res_var.get() or 8000))
            ctx = max(4000, int(lim["context_length"]) - res)
            ctx_var.set(str(ctx))

        def use_model_max_resp() -> None:
            lim = lim_state.get("lim") or get_model_limits(refresh=True)
            lim_state["lim"] = lim
            max_tok_var.set(str(int(lim["max_completion_tokens"])))

        def refresh_model() -> None:
            info.configure(text="Refreshing model metadata…")
            def work() -> None:
                try:
                    lim = get_model_limits(refresh=True)
                    lim_state["lim"] = lim

                    def ui() -> None:
                        load_limits(force=False)
                        self._refresh_context_chip()

                    self.after(0, ui)
                except Exception as e:  # noqa: BLE001
                    self.after(0, lambda: info.configure(text=str(e)))

            threading.Thread(target=work, daemon=True).start()

        ctk.CTkButton(
            btns, text="Use model max context", width=160, command=use_model_max_ctx, **style_chrome_button()
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            btns, text="Use model max response", width=170, command=use_model_max_resp, **style_chrome_button()
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            btns, text="Refresh model info", width=130, command=refresh_model, **style_chrome_button()
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            btns, text="Reload from chat", width=130, command=reload_body, **style_chrome_button()
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            btns, text="Compact now", width=120, command=compact_now, **style_chrome_button(primary=True)
        ).pack(side="left", padx=4)

        bot = ctk.CTkFrame(form, fg_color="transparent")
        bot.pack(fill="x", pady=(8, 0))
        ctk.CTkButton(bot, text="Save all", width=110, command=save, **style_chrome_button(primary=True)).pack(
            side="right", padx=4
        )
        ctk.CTkButton(bot, text="Close", width=90, command=win.destroy, **style_chrome_button()).pack(
            side="right", padx=4
        )

    def _chat_model_params_dialog(self) -> None:
        # Full params + opens context dialog reference
        from app.core.services.llm.model_params import get_model_params, save_model_params
        from app.core.services.llm.model_limits import get_model_limits

        p = get_model_params()
        win = ctk.CTkToplevel(self)
        win.title("Model parameters & context window")
        win.geometry("520x520")
        win.transient(self)
        form = ctk.CTkFrame(win)
        form.pack(fill="both", expand=True, padx=16, pady=16)
        try:
            lim = get_model_limits(refresh=False)
            lim_txt = lim.get("label") or ""
        except Exception:  # noqa: BLE001
            lim_txt = ""
        ctk.CTkLabel(
            form,
            text=lim_txt or "Model limits: open Context… to fetch",
            text_color=_HC_MUTED,
            wraplength=460,
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=6, pady=(0, 8))
        fields = [
            ("temperature", "Temperature (0–2)"),
            ("top_p", "Top P"),
            ("max_tokens", "Max response tokens (0=default)"),
            ("context_window", "Context window (tokens)"),
            ("context_reserve_reply", "Reserve for reply"),
            ("presence_penalty", "Presence penalty"),
            ("frequency_penalty", "Frequency penalty"),
        ]
        entries: dict[str, ctk.CTkEntry] = {}
        for i, (key, label) in enumerate(fields):
            ctk.CTkLabel(form, text=label).grid(row=i + 1, column=0, sticky="w", padx=6, pady=6)
            e = ctk.CTkEntry(form, width=140)
            e.insert(0, str(p.get(key, "")))
            e.grid(row=i + 1, column=1, sticky="w", padx=6, pady=6)
            entries[key] = e

        def save() -> None:
            raw = {}
            for k, e in entries.items():
                v = e.get().strip()
                try:
                    if k in ("max_tokens", "context_window", "context_reserve_reply"):
                        raw[k] = int(float(v))
                    else:
                        raw[k] = float(v)
                except ValueError:
                    messagebox.showerror("Params", f"Invalid number for {k}", parent=win)
                    return
            save_model_params(raw)
            try:
                self._refresh_context_chip()
            except Exception:  # noqa: BLE001
                pass
            win.destroy()
            self.set_status(
                f"Params saved · temp={raw.get('temperature')} · ctx={raw.get('context_window')}"
            )

        ctk.CTkLabel(
            form,
            text="Tip: use Chat → Context… for model-max buttons and live limit fetch.",
            text_color=_HC_MUTED,
            wraplength=440,
        ).grid(row=len(fields) + 1, column=0, columnspan=2, sticky="w", padx=6, pady=8)
        bf = ctk.CTkFrame(form, fg_color="transparent")
        bf.grid(row=len(fields) + 2, column=0, columnspan=2, sticky="ew", pady=10)
        ctk.CTkButton(bf, text="Context…", width=100, command=lambda: (win.destroy(), self._chat_context_window_dialog())).pack(
            side="left", padx=4
        )
        ctk.CTkButton(bf, text="Save", width=100, command=save).pack(side="right", padx=4)

    def _chat_clear(self) -> None:
        if self._chat_busy:
            return
        if not messagebox.askyesno("Clear chat", "Clear the conversation history?"):
            return
        self._chat_state = chat_svc.clear_chat()
        self._chat_attachments = []
        if hasattr(self, "chat_attach_label"):
            self.chat_attach_label.configure(text=self._attachments_summary())
        self._chat_render_transcript()
        self.set_status("Chat cleared.")

    def _chat_toggle_pause(self) -> None:
        """Task #9: pause/resume long chat agent runs between tool/LLM passes."""
        if not self._chat_busy:
            return
        self._chat_paused = not bool(getattr(self, "_chat_paused", False))
        paused = bool(self._chat_paused)
        try:
            if hasattr(self, "chat_pause_btn"):
                self.chat_pause_btn.configure(
                    text="▶ Resume" if paused else "⏸ Pause",
                )
        except Exception:  # noqa: BLE001
            pass
        if paused:
            self.set_status("Paused — finishes current step, then waits. Resume to continue.", toast=True)
            if hasattr(self, "chat_status"):
                try:
                    self.chat_status.configure(text="⏸ Paused — press Resume")
                except Exception:  # noqa: BLE001
                    pass
        else:
            self.set_status("Resumed", toast=True)

    def _chat_force_unlock(self, *, reason: str = "unlocked") -> None:
        """Clear stuck busy state so the user can send again (worker may be dead/hung)."""
        self._chat_busy = False
        self._chat_cancel = False
        self._chat_paused = False
        self._chat_busy_started = 0.0
        self._stream_bubble_label = None
        try:
            from app.core.services.data.agent_tracker import abandon_stale_runs

            abandon_stale_runs(max_age_sec=0)  # mark active chat runs failed
        except Exception:  # noqa: BLE001
            pass
        try:
            if hasattr(self, "chat_send_btn"):
                from app.ui.components.layman_copy import send_label as _sl

                self.chat_send_btn.configure(
                    state="normal", text=_sl(simple=self._is_simple_ui())
                )
            if hasattr(self, "chat_stop_btn"):
                from app.ui.components.layman_copy import STOP_LABEL as _st

                self.chat_stop_btn.configure(
                    state="disabled",
                    text=_st,
                    fg_color=("#d1d5db", "#3f3f46"),
                )
            if hasattr(self, "chat_pause_btn"):
                self.chat_pause_btn.configure(state="disabled", text="⏸ Pause")
            if hasattr(self, "chat_status"):
                self.chat_status.configure(text="Ready — you can send again")
        except Exception:  # noqa: BLE001
            pass
        try:
            self._finish_thinking_bubble(ok=False)
        except Exception:  # noqa: BLE001
            pass
        self.set_status(f"Chat {reason} — send is available again", toast=True)

    def _chat_stop(self) -> None:
        """Stop LLM thinking / tool loop for the current send (+ kill terminal)."""
        import time as _time

        # Not busy → still allow force-unlock if buttons look stuck
        if not self._chat_busy:
            try:
                # Re-enable send if somehow disabled while not busy
                if hasattr(self, "chat_send_btn"):
                    st = str(self.chat_send_btn.cget("state") or "")
                    if st == "disabled":
                        self._chat_force_unlock(reason="recovered")
                        return
            except Exception:  # noqa: BLE001
                pass
            return

        # Second Stop within 2s = force unlock immediately (hung worker)
        now = _time.monotonic()
        last = float(getattr(self, "_chat_stop_click_ts", 0) or 0)
        self._chat_stop_click_ts = now
        if last and (now - last) < 2.0:
            self._chat_force_unlock(reason="force-stopped")
            return

        self._chat_cancel = True
        self._chat_paused = False  # stop wins over pause
        try:
            from app.core.services.system.terminal_tool import kill_active_terminal

            if kill_active_terminal():
                self.set_status("Stopping… (killed terminal). Click Stop again to force unlock.")
            else:
                self.set_status("Stopping… Click Stop again if it stays stuck.")
        except Exception:  # noqa: BLE001
            self.set_status("Stopping…")
        if hasattr(self, "chat_status"):
            try:
                self.chat_status.configure(text="Stopping… (Stop again = force unlock)")
            except Exception:  # noqa: BLE001
                pass
        if hasattr(self, "chat_stop_btn"):
            try:
                self.chat_stop_btn.configure(state="normal", text="■ Force")
            except Exception:  # noqa: BLE001
                pass
        if hasattr(self, "chat_pause_btn"):
            try:
                self.chat_pause_btn.configure(state="disabled", text="⏸ Pause")
            except Exception:  # noqa: BLE001
                pass

        # If worker never finishes finish(), unlock after 1.5s anyway
        def _auto_unlock() -> None:
            if bool(getattr(self, "_chat_busy", False)):
                self._chat_force_unlock(reason="auto-unlocked after Stop")

        try:
            self.after(1500, _auto_unlock)
        except Exception:  # noqa: BLE001
            pass

    def _composer_hint_text(self, mode: str | None = None) -> str:
        from app.ui.components.layman_copy import composer_hint

        m = (mode or (self.chat_mode_var.get() if hasattr(self, "chat_mode_var") else "action") or "action").lower()
        return composer_hint(simple=self._is_simple_ui(), mode=m)

    def _refresh_composer_hint(self) -> None:
        if hasattr(self, "_composer_hint"):
            try:
                self._composer_hint.configure(text=self._composer_hint_text())
            except Exception:  # noqa: BLE001
                pass

    def _chat_on_input_key(self) -> None:
        """Lightweight slash hint + draft autosave while typing."""
        if not hasattr(self, "chat_input"):
            return
        try:
            if getattr(self, "_composer_is_placeholder", False):
                return
            t = self.chat_input.get("1.0", "end")
            # draft (keep trailing space for typing comfort)
            if getattr(self, "_chat_state", None) is not None:
                self._chat_state["draft"] = t.rstrip("\n")
            if t.strip().startswith("/") and " " not in t.strip():
                self.set_status("Slash: /plan /action /image /search /stop /caps /live /new")
            # P0.3 lightweight `#` autocomplete hint (knowledge titles)
            elif "#" in t:
                try:
                    from app.core.services.chat.hash_inject import (
                        parse_hash_tokens,
                        suggest_hash_completions,
                    )

                    tail = t.rsplit("#", 1)[-1]
                    partial = ""
                    if not t.rstrip().endswith("#"):
                        partial = (tail.split()[0] if tail.split() else "").rstrip(".,;:!?")
                    sug = suggest_hash_completions(partial, limit=5)
                    if sug:
                        labels = ", ".join(s.get("label") or "" for s in sug[:4])
                        self.set_status(f"Hash inject: {labels}")
                    elif parse_hash_tokens(t):
                        self.set_status("Hash inject: will pull #tokens into this turn on Send")
                except Exception:  # noqa: BLE001
                    pass
            # Throttled token meter refresh (Task #3)
            import time

            now = time.monotonic()
            last = float(getattr(self, "_composer_budget_ts", 0) or 0)
            if now - last > 0.35:
                self._composer_budget_ts = now
                self._update_composer_status()
        except Exception:  # noqa: BLE001
            pass

    def _try_handle_slash_command(self, text: str) -> bool:
        """Return True if text was a slash command (handled, do not send to LLM)."""
        raw = (text or "").strip()
        if not raw.startswith("/"):
            return False
        # only pure slash commands (first line)
        first = raw.splitlines()[0].strip()
        parts = first.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""
        rest = "\n".join(raw.splitlines()[1:]).strip()
        if rest and cmd not in ("/image", "/search", "/img"):
            # multi-line starting with / — treat as normal message unless known single-line cmds
            return False

        if cmd in ("/plan",):
            self.chat_mode_var.set("plan")
            self._on_chat_flags_save()
            self._refresh_composer_hint()
            self.set_status("Mode → plan")
            return True
        if cmd in ("/action", "/act"):
            self.chat_mode_var.set("action")
            self._on_chat_flags_save()
            self._refresh_composer_hint()
            self.set_status("Mode → action")
            return True
        if cmd in ("/stop", "/unlock"):
            if bool(getattr(self, "_chat_busy", False)):
                self._chat_stop()
            else:
                self._chat_force_unlock(reason="unlocked via /stop")
            return True
        if cmd in ("/image", "/img", "/gen"):
            prompt = arg or rest
            if prompt:
                # put prompt into gen dialog flow via direct generate if possible
                self._composer_set_text(f"Generate an image: {prompt}")
                # Prefer native IMAGE_GEN path via normal send in action mode
                if hasattr(self, "chat_mode_var"):
                    self.chat_mode_var.set("action")
                    self._on_chat_flags_save()
                return False  # fall through to send as message with image intent
            self._chat_image_gen_dialog()
            return True
        if cmd in ("/search", "/web"):
            if arg:
                self._composer_set_text(f"Search the web for: {arg}")
                return False
            self._chat_web_search_dialog()
            return True
        if cmd in ("/caps", "/capabilities"):
            self._chat_open_caps_popover()
            return True
        if cmd in ("/live",):
            self._chat_toggle_live_panel()
            return True
        if cmd in ("/new",):
            self._shortcut_new_chat()
            return True
        if cmd in ("/help", "/?"):
            self._show_shortcuts_help()
            return True
        if cmd in ("/compact", "/comfort"):
            self._chat_toggle_density()
            return True
        # unknown slash — let LLM see it
        return False

    def _chat_open_plus_menu(self) -> None:
        from app.ui.themes import style_chrome_button

        win = ctk.CTkToplevel(self)
        win.title("Add")
        win.geometry("280x320")
        win.transient(self)
        win.grab_set()
        ctk.CTkLabel(win, text="Add to chat", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=12, pady=(12, 6)
        )
        items = [
            ("📎 Attach file", self._chat_attach),
            ("🖼 Attach image", getattr(self, "_chat_attach_image", self._chat_attach)),
            ("📝 Attach note", self._chat_attach_note_dialog),
            ("🎨 Generate image", self._chat_image_gen_dialog),
            ("🔍 Web search", self._chat_web_search_dialog),
            ("👁 OCR", getattr(self, "_chat_ocr_dialog", lambda: None)),
            ("⌨ Command palette (Ctrl+K)", self._open_command_palette),
        ]
        for label, cmd in items:
            ctk.CTkButton(
                win,
                text=label,
                anchor="w",
                command=lambda c=cmd: (win.destroy(), c()),
                **style_chrome_button(),
            ).pack(fill="x", padx=12, pady=3)
        ctk.CTkButton(win, text="Close", command=win.destroy).pack(pady=10)

    def _open_command_palette(self) -> None:
        """Ctrl+K: jump to pages and common actions."""
        from app.ui.themes import style_chrome_button, style_entry

        win = ctk.CTkToplevel(self)
        win.title("Command palette")
        win.geometry("480x520")
        win.transient(self)
        win.grab_set()
        ctk.CTkLabel(win, text="Commands (Ctrl+K)", font=ctk.CTkFont(size=15, weight="bold")).pack(
            anchor="w", padx=12, pady=(12, 4)
        )
        qvar = ctk.StringVar(value="")
        entry = ctk.CTkEntry(win, textvariable=qvar, placeholder_text="Filter…", width=440, **style_entry())
        entry.pack(padx=12, pady=6)
        entry.focus_set()
        box = ctk.CTkScrollableFrame(win, height=380)
        box.pack(fill="both", expand=True, padx=12, pady=6)

        actions: list[tuple[str, Callable[[], None]]] = []
        for name in NAV_ITEMS:
            actions.append((f"Go to {name}", lambda n=name: self.show_page(n)))
        actions.extend(
            [
                ("Mode → Action", lambda: (self.chat_mode_var.set("action"), self._on_chat_flags_save()) if hasattr(self, "chat_mode_var") else None),
                ("Mode → Plan", lambda: (self.chat_mode_var.set("plan"), self._on_chat_flags_save()) if hasattr(self, "chat_mode_var") else None),
                ("Toggle density", self._chat_toggle_density),
                ("One-screen view", lambda: self._set_one_screen(True)),
                ("Exit one-screen", lambda: self._set_one_screen(False)),
                ("Hide / show menu", self._toggle_app_menu),
                ("Hide / show CPU bar", self._toggle_sysmon_bar),
                ("Caps / capabilities", self._chat_open_caps_popover),
                ("Generate image", self._chat_image_gen_dialog),
                ("Web search", self._chat_web_search_dialog),
                ("New chat", self._shortcut_new_chat),
                ("Toggle Live panel", self._chat_toggle_live_panel),
                ("Approvals", lambda: self.show_page("Approvals")),
                ("Settings", lambda: self.show_page("Settings")),
                ("Shortcuts help", self._show_shortcuts_help),
            ]
        )

        def run_action(fn: Callable[[], None]) -> None:
            win.destroy()
            try:
                if fn:
                    fn()
            except Exception as e:  # noqa: BLE001
                self.set_status(f"Command failed: {e}")

        def render(*_a: Any) -> None:
            for w in box.winfo_children():
                w.destroy()
            q = (qvar.get() or "").strip().lower()
            shown = 0
            for label, fn in actions:
                if q and q not in label.lower():
                    continue
                ctk.CTkButton(
                    box,
                    text=label,
                    anchor="w",
                    command=lambda f=fn: run_action(f),
                    **style_chrome_button(),
                ).pack(fill="x", pady=2)
                shown += 1
                if shown >= 40:
                    break
            if not shown:
                ctk.CTkLabel(box, text="No matches").pack(anchor="w", padx=8, pady=8)

        qvar.trace_add("write", lambda *_: render())
        entry.bind("<Return>", lambda _e: None)
        render()

    def _chat_show_live_panel(self) -> None:
        """Ensure Live activity panel is visible (Grok-style side thinking)."""
        if getattr(self, "_live_panel_visible", False):
            return
        try:
            self._chat_toggle_live_panel()
        except Exception:  # noqa: BLE001
            pass

    def _ensure_thinking_bubble(self) -> None:
        """
        Live thinking strip — compact one-line by default (collapsed).
        Expand shows a small fixed-height step list (does not eat the chat).
        """
        if getattr(self, "_thinking_row", None) is not None:
            try:
                if self._thinking_row.winfo_exists():
                    return
            except Exception:  # noqa: BLE001
                pass
        if not hasattr(self, "chat_scroll") or not self.chat_scroll.winfo_exists():
            return
        from app.ui.themes import UI as _UI, style_chrome_button

        self._thinking_steps = list(getattr(self, "_thinking_steps", None) or [])
        # Start collapsed so the answer area stays large; status line still updates live
        self._thinking_live_open = False

        side_pad = self._chat_side_pad()
        row = ctk.CTkFrame(self.chat_scroll, fg_color="transparent")
        row.pack(fill="x", padx=side_pad, pady=(2, 4))

        card = ctk.CTkFrame(
            row,
            fg_color=("#eef2ff", "#1e1b4b"),
            corner_radius=10,
            border_width=1,
            border_color=("#c7d2fe", "#4338ca"),
            height=36,
        )
        card.pack(anchor="w", fill="x", padx=(4, 48))
        card.pack_propagate(False)
        self._thinking_card = card

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="both", expand=True, padx=6, pady=3)

        self._thinking_toggle_btn = ctk.CTkButton(
            head,
            text="▶ 💭 Working…",
            anchor="w",
            height=28,
            command=self._toggle_live_thinking,
            **style_chrome_button(),
        )
        self._thinking_toggle_btn.pack(side="left", fill="x", expand=True)
        self._thinking_status_lbl = ctk.CTkLabel(
            head,
            text="starting…",
            font=ctk.CTkFont(size=11),
            text_color=_UI["muted"],
            anchor="e",
            width=220,
        )
        self._thinking_status_lbl.pack(side="right", padx=(4, 2))

        # Detail is NOT packed until user expands (keeps height ~36px)
        self._thinking_detail = ctk.CTkFrame(row, fg_color="transparent")
        box = ctk.CTkTextbox(
            self._thinking_detail,
            height=100,  # fixed modest height when open
            font=ctk.CTkFont(size=12),
            wrap="word",
            fg_color=("#e0e7ff", "#12122a"),
            border_width=0,
            activate_scrollbars=True,
        )
        box.pack(fill="x", padx=(8, 48), pady=(0, 4))
        try:
            box.insert("1.0", "1. Starting…\n")
            box.configure(state="disabled")
        except Exception:  # noqa: BLE001
            pass

        self._thinking_row = row
        self._thinking_box = box
        self._bind_wheel_tree(row)

    def _toggle_live_thinking(self) -> None:
        open_now = not bool(getattr(self, "_thinking_live_open", False))
        self._thinking_live_open = open_now
        n = len(getattr(self, "_thinking_steps", []) or [])
        btn = getattr(self, "_thinking_toggle_btn", None)
        detail = getattr(self, "_thinking_detail", None)
        card = getattr(self, "_thinking_card", None)
        st = getattr(self, "_thinking_status_lbl", None)
        steps = list(getattr(self, "_thinking_steps", []) or [])
        last = self._humanize_thinking_step(steps[-1]) if steps else "…"

        if btn is not None:
            label = (
                f"{'▼' if open_now else '▶'} 💭 "
                f"{'Live' if bool(getattr(self, '_chat_busy', False)) else 'Thought'} "
                f"· {n} step(s)"
            )
            try:
                btn.configure(text=label)
            except Exception:  # noqa: BLE001
                pass
        if card is not None:
            try:
                if open_now:
                    card.configure(height=36)
                    card.pack_propagate(False)
                else:
                    card.configure(height=36)
                    card.pack_propagate(False)
            except Exception:  # noqa: BLE001
                pass
        if detail is not None:
            try:
                if open_now:
                    detail.pack(fill="x", after=card if card is not None else None)
                    # refresh list body
                    self._paint_thinking_ui(steps[-1] if steps else last, force_body=True)
                else:
                    detail.pack_forget()
            except Exception:  # noqa: BLE001
                try:
                    if open_now:
                        detail.pack(fill="x")
                    else:
                        detail.pack_forget()
                except Exception:  # noqa: BLE001
                    pass
        if st is not None:
            try:
                short = last if len(last) <= 48 else last[:45] + "…"
                st.configure(text=short)
            except Exception:  # noqa: BLE001
                pass

    def _append_thinking_step(self, msg: str | dict) -> None:
        """Append one live thinking line; always update one-line status; throttle list paint.
        
        Accepts either a string (legacy) or a dict with structured step data:
        {"msg": str, "source": str, "detail": str, "tool": str, "status": str, "duration_ms": int, "at": str}
        """
        if not self.winfo_exists():
            return
        
        # Handle structured data from chat.py emit()
        if isinstance(msg, dict):
            step_data = msg
            line = step_data.get("msg", "")
            source = step_data.get("source", "agent")
            detail = step_data.get("detail", "")
            tool = step_data.get("tool")
            status = step_data.get("status")
            duration_ms = step_data.get("duration_ms")
            
            # Build display text from structured data
            if tool and status:
                status_icon = {"start": "⏳", "success": "✓", "error": "✗", "pending": "⏸"}.get(status, "⏳")
                duration_str = f" ({duration_ms}ms)" if duration_ms else ""
                if detail:
                    line = f"{status_icon} {tool}: {detail}{duration_str}"
                else:
                    line = f"{status_icon} {tool}{duration_str}"
            elif line:
                line = line
            else:
                line = str(step_data)
        else:
            line = (msg or "").strip()
        
        if not line:
            return
        try:
            self._set_now_doing(self._humanize_thinking_step(line) or line, idle=False)
        except Exception:  # noqa: BLE001
            try:
                self._set_now_doing(line, idle=False)
            except Exception:  # noqa: BLE001
                pass
        # Parse timestamp from activity log format: [HH:MM:SS][source] message
        timestamp = ""
        if isinstance(msg, str) and line.startswith("[") and "] " in line[:40]:
            # Extract timestamp from [HH:MM:SS][source] prefix
            import re
            match = re.match(r"\[(\d{2}:\d{2}:\d{2})\]\[[^\]]+\]\s*(.*)", line)
            if match:
                timestamp = match.group(1)
                # Convert 24-hour to 12-hour AM/PM format
                try:
                    from datetime import datetime
                    dt = datetime.strptime(timestamp, "%H:%M:%S")
                    timestamp = dt.strftime("%I:%M:%S %p").lstrip("0")
                except Exception:
                    pass
                line = match.group(2)
            else:
                # Fallback: just strip the first [xxx] [yyy] prefix
                line = line.split("] ", 1)[-1]
        
        import time as _time

        now = _time.monotonic()
        last = float(getattr(self, "_thinking_ui_last", 0) or 0)
        steps = getattr(self, "_thinking_steps", None)
        if steps is None:
            self._thinking_steps = []
            steps = self._thinking_steps

        src = ""
        if isinstance(msg, dict):
            src = str(msg.get("source") or "")
        is_thought = src == "thinking" or line.lstrip().startswith("💭")
        raw_bit = line[1:].strip() if line.lstrip().startswith("💭") else line
        if is_thought:
            # Don't treat "Thinking with model…" as model prose
            low = raw_bit.lower()
            if low.startswith("thinking with") or "pass " in low[:40]:
                is_thought = False

        if is_thought:
            if steps and isinstance(steps[-1], dict) and steps[-1].get("kind") == "thought":
                prev = str(steps[-1].get("raw") or "")
                merged = (prev + ("\n" if prev else "") + raw_bit)[-12000:]
                steps[-1]["raw"] = merged
                steps[-1]["current"] = raw_bit[-500:]
                steps[-1]["text"] = steps[-1]["current"]
                try:
                    if getattr(self, "side_panel_mode", None) and self.side_panel_mode.get() == "Thinking":
                        self._thinking_update_card(len(steps) - 1)
                        self._thinking_set_open(len(steps) - 1, True)
                except Exception:  # noqa: BLE001
                    pass
                return
            step_entry = {
                "kind": "thought",
                "title": "LLM thinking",
                "time": timestamp,
                "text": raw_bit[-500:],
                "current": raw_bit[-500:],
                "raw": raw_bit[-12000:],
                "source": "thinking",
            }
            steps.append(step_entry)
            try:
                if getattr(self, "side_panel_mode", None) and self.side_panel_mode.get() == "Thinking":
                    self._thinking_add_card(len(steps) - 1, collapse_others=True)
            except Exception:  # noqa: BLE001
                pass
        else:
            if steps and isinstance(steps[-1], dict) and steps[-1].get("text") == line:
                return
            if steps and isinstance(steps[-1], str) and steps[-1] == line:
                return
            nice = self._humanize_thinking_step(line) or line[:80]
            step_entry = {
                "kind": "phase",
                "title": nice,
                "time": timestamp,
                "text": line,
                "current": nice,
                "raw": line,
                "source": src or "agent",
            }
            if isinstance(msg, dict):
                step_entry["tool"] = tool
                step_entry["status"] = status
                step_entry["duration_ms"] = duration_ms
                step_entry["detail"] = detail
            steps.append(step_entry)
            try:
                if getattr(self, "side_panel_mode", None) and self.side_panel_mode.get() == "Thinking":
                    self._thinking_add_card(len(steps) - 1, collapse_others=True)
            except Exception:  # noqa: BLE001
                pass
        # Always refresh compact status quickly; full list is throttled
        if now - last < 0.15 and len(steps) > 1:
            self._thinking_ui_pending = line
            if not getattr(self, "_thinking_flush_scheduled", False):
                self._thinking_flush_scheduled = True
                try:
                    self.after(160, self._flush_thinking_ui)
                except Exception:  # noqa: BLE001
                    self._thinking_flush_scheduled = False
            # Still poke the one-line label immediately (cheap)
            try:
                self._ensure_thinking_bubble()
                nice = self._humanize_thinking_step(line)
                st = getattr(self, "_thinking_status_lbl", None)
                if st is not None:
                    short = nice if len(nice) <= 48 else nice[:45] + "…"
                    st.configure(text=short)
                n = len(steps)
                btn = getattr(self, "_thinking_toggle_btn", None)
                if btn is not None and not bool(getattr(self, "_thinking_live_open", False)):
                    btn.configure(text=f"▶ 💭 Working · {n} step(s)")
                if hasattr(self, "chat_status"):
                    self.chat_status.configure(text=f"💭 {nice[:88]}")
            except Exception:  # noqa: BLE001
                pass
            return
        self._thinking_ui_last = now
        self._thinking_ui_pending = None
        self._paint_thinking_ui(line)

    def _flush_thinking_ui(self) -> None:
        self._thinking_flush_scheduled = False
        pending = getattr(self, "_thinking_ui_pending", None)
        self._thinking_ui_pending = None
        if pending:
            import time as _time

            self._thinking_ui_last = _time.monotonic()
            self._paint_thinking_ui(str(pending))

    def _paint_thinking_ui(self, line: str, *, force_body: bool = False) -> None:
        """Update compact header always; step list only when expanded."""
        try:
            self._ensure_thinking_bubble()
            steps = list(getattr(self, "_thinking_steps", None) or [])
            n = len(steps)
            # Get the text from the step entry (handle both old string format and new dict format)
            def get_step_text(step):
                if isinstance(step, dict):
                    return step.get("text", "")
                return step
            
            nice = self._humanize_thinking_step(line) if line else (
                self._humanize_thinking_step(get_step_text(steps[-1])) if steps else "…"
            )
            open_now = bool(getattr(self, "_thinking_live_open", False))

            btn = getattr(self, "_thinking_toggle_btn", None)
            if btn is not None:
                try:
                    btn.configure(
                        text=(
                            f"{'▼' if open_now else '▶'} 💭 "
                            f"{'Working' if bool(getattr(self, '_chat_busy', False)) else 'Thought'} "
                            f"· {n} step(s)"
                        )
                    )
                except Exception:  # noqa: BLE001
                    pass

            st = getattr(self, "_thinking_status_lbl", None)
            if st is not None:
                short = nice if len(nice) <= 48 else nice[:45] + "…"
                try:
                    st.configure(text=short)
                except Exception:  # noqa: BLE001
                    pass

            if hasattr(self, "chat_status"):
                try:
                    self.chat_status.configure(text=f"💭 {nice[:88]}")
                except Exception:  # noqa: BLE001
                    pass

            # Expanded body only
            if open_now or force_body:
                box = getattr(self, "_thinking_box", None)
                if box is not None and box.winfo_exists():
                    lines = []
                    for i, s in enumerate(steps, 1):
                        title, current, raw = self._thinking_step_bits(s, i - 1)
                        step_time = s.get("time", "") if isinstance(s, dict) else ""
                        prefix = f"[{step_time}] " if step_time else ""
                        body = current or title or raw
                        lines.append(f"{i}. {prefix}{body}")
                        if raw and raw not in (current, title):
                            lines.append(f"    {raw[:400]}")
                    text = "\n".join(lines) + ("\n" if lines else "")
                    try:
                        box.configure(state="normal")
                        box.delete("1.0", "end")
                        box.insert("1.0", text)
                        box.configure(state="disabled")
                        box.see("end")
                    except Exception:  # noqa: BLE001
                        pass
            # Live Thinking tab: update the last card only (no full rebuild/scroll)
            try:
                if getattr(self, "side_panel_mode", None) and self.side_panel_mode.get() == "Thinking":
                    cards = getattr(self, "_thinking_card_widgets", None) or []
                    if len(cards) < n:
                        self._thinking_sync_cards()
                    elif n:
                        self._thinking_update_card(n - 1)
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            pass

    def _snapshot_thinking_message(self, *, ok: bool = True) -> dict[str, Any] | None:
        """Build a durable chat message so thinking is not lost after re-render."""
        steps = list(getattr(self, "_thinking_steps", None) or [])
        if not steps:
            return None
        from datetime import datetime, timezone

        status = "done" if ok else "error"
        # Handle both old string format and new dict format
        def get_step_text(step):
            if isinstance(step, dict):
                return step.get("text", "")
            return step
        
        nice = [self._humanize_thinking_step(get_step_text(s)) or get_step_text(s) for s in steps]
        return {
            "role": "thinking",
            "content": "\n".join(f"• {s}" for s in nice if s),
            "steps": list(steps),
            "status": status,
            "collapsed": True,
            "at": datetime.now(timezone.utc).isoformat(),
        }

    def _finish_thinking_bubble(self, *, ok: bool = True) -> None:
        """Collapse live card tightly; snapshot injected into history by finish()."""
        steps = list(getattr(self, "_thinking_steps", None) or [])
        self._thinking_steps_final = steps
        try:
            n = len(steps)
            def get_step_text(step):
                if isinstance(step, dict):
                    return step.get("text", "")
                return step
            last = self._humanize_thinking_step(get_step_text(steps[-1])) if steps else ""
            st = getattr(self, "_thinking_status_lbl", None)
            if st is not None:
                try:
                    if st.winfo_exists():
                        tail = (last[:40] + "…") if len(last) > 40 else last
                        st.configure(
                            text=(("done ✓" if ok else "error") + (f" · {tail}" if tail else f" · {n}"))
                        )
                except Exception:  # noqa: BLE001
                    pass
            btn = getattr(self, "_thinking_toggle_btn", None)
            if btn is not None:
                try:
                    btn.configure(
                        text=f"▶ 💭 Thought · {n} step(s) · {'done' if ok else 'error'}"
                    )
                except Exception:  # noqa: BLE001
                    pass
            self._thinking_live_open = False
            detail = getattr(self, "_thinking_detail", None)
            if detail is not None:
                try:
                    detail.pack_forget()
                except Exception:  # noqa: BLE001
                    pass
            card = getattr(self, "_thinking_card", None)
            if card is not None:
                try:
                    card.configure(height=36)
                    card.pack_propagate(False)
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            pass
        # Clear live refs — history card replaces this on transcript render
        self._thinking_row = None
        self._thinking_box = None
        self._thinking_status_lbl = None
        self._thinking_toggle_btn = None
        self._thinking_detail = None
        self._thinking_card = None

    def _chat_send(self) -> None:
        import time as _time

        if self._chat_busy:
            # If stuck busy > 45s with no progress, auto-unlock on next Send click
            started = float(getattr(self, "_chat_busy_started", 0) or 0)
            stuck = started > 0 and (_time.monotonic() - started) > 45.0
            if stuck:
                self._chat_force_unlock(reason="auto-cleared stuck busy")
                # fall through and send
            else:
                try:
                    if hasattr(self, "chat_status"):
                        self.chat_status.configure(
                            text="Still working… ■ Stop once, or twice to force unlock"
                        )
                    self.set_status(
                        "Chat is busy — press ■ Stop (twice if stuck), then send.",
                        toast=True,
                    )
                except Exception:  # noqa: BLE001
                    pass
                return
        if not hasattr(self, "chat_input"):
            return
        # Don't send the Grok-style placeholder as a message
        if getattr(self, "_composer_is_placeholder", False):
            text = ""
        else:
            text = self.chat_input.get("1.0", "end").strip()
        self._sanitize_chat_attachments()
        attachments = list(self._chat_attachments)
        attached_notes = list(getattr(self, "_chat_attached_notes", None) or [])
        if not text and not attachments and not attached_notes:
            self.chat_status.configure(text="Empty message")
            return

        # Slash commands (do not hit LLM when fully handled)
        if text.startswith("/") and self._try_handle_slash_command(text):
            self.chat_input.delete("1.0", "end")
            self._composer_is_placeholder = False
            self._composer_maybe_placeholder()
            self._refresh_composer_hint()
            return
        # /image with prompt rewrote input — re-read
        text = self.chat_input.get("1.0", "end").strip()
        if getattr(self, "_composer_is_placeholder", False):
            text = ""

        try:
            from app.core.services.chat.task_watch import is_auto_continue_text

            if text and not is_auto_continue_text(text):
                self._auto_continue_count = 0
        except Exception:  # noqa: BLE001
            pass

        self._chat_busy = True
        self._chat_busy_started = _time.monotonic()
        self._chat_cancel = False
        self._chat_paused = False
        self.chat_send_btn.configure(state="disabled", text="…")
        if hasattr(self, "chat_stop_btn"):
            self.chat_stop_btn.configure(
                state="normal",
                text="■ Stop",
                fg_color=("#dc2626", "#7f1d1d"),
            )
        if hasattr(self, "chat_pause_btn"):
            try:
                self.chat_pause_btn.configure(state="normal", text="⏸ Pause")
            except Exception:  # noqa: BLE001
                pass
        self.chat_status.configure(text="Thinking…")
        try:
            self._refresh_task_llm_chips()
        except Exception:  # noqa: BLE001
            pass
        self.chat_input.delete("1.0", "end")
        self._composer_is_placeholder = False
        if getattr(self, "_chat_state", None) is not None:
            self._chat_state["draft"] = ""
        # New send: pin to bottom like Grok when you submit
        self._chat_user_pinned_bottom = True
        # Live / Thinking / Terminal is the monitor — always open on send so dumps
        # never have to live in the answer bubble.
        try:
            self._ensure_live_monitor_open(tab="Thinking")
        except Exception:  # noqa: BLE001
            pass

        # Optimistic display (full content built after send on success path)
        display = text or ("(notes)" if attached_notes else "(attachments only)")
        if attachments:
            display += "\n[attachments: " + ", ".join(Path(p).name for p in attachments) + "]"
        if attached_notes:
            try:
                from app.core.services.chat import notes_store as _ns
                _ntitles = []
                for _nid in attached_notes:
                    _n = _ns.get_note(_nid)
                    _ntitles.append((_n or {}).get("title") or _nid[:8])
                display += "\n[notes: " + ", ".join(_ntitles) + "]"
            except Exception:  # noqa: BLE001
                display += "\n[notes: " + ", ".join(attached_notes) + "]"
        images = list(getattr(self, "_pending_images", []) or [])
        videos = list(getattr(self, "_pending_videos", []) or [])
        # Stage into chat_media for stable in-chat display
        try:
            from app.core.services.chat.media_chat import stage_many
            from app.core.services.chat.chat_store import get_active_chat_id

            cid = get_active_chat_id() or "default"
            images = stage_many(images, cid)
            videos = stage_many(videos, cid)
        except Exception:  # noqa: BLE001
            pass
        hist = list(self._chat_state.get("messages") or [])
        from datetime import datetime, timezone

        hist.append(
            {
                "role": "user",
                "content": display,
                "images": images,
                "videos": videos,
                "attachments": list(attachments),
                "at": datetime.now(timezone.utc).isoformat(),
            }
        )
        self._chat_state["messages"] = hist
        self._pending_images = []
        self._pending_videos = []
        # Crash-safe: persist user turn immediately so a hung worker still leaves a trail
        try:
            chat_svc.save_chat(self._chat_state)
        except Exception:  # noqa: BLE001
            pass
        self.set_status("Thinking…")
        try:
            self._ensure_live_monitor_open(tab="Thinking")
        except Exception:  # noqa: BLE001
            pass
        try:
            self._thinking_row = None
            self._thinking_box = None
            self._ensure_thinking_bubble()
            self._append_thinking_step("Queued message — preparing tools & model…")
        except Exception:  # noqa: BLE001
            pass
        self._chat_render_transcript()

        # P0.2: Compare / multi-model path (no tools)
        if bool(getattr(self, "_compare_mode", False)):
            self._chat_send_compare(text=text, hist=hist, user_sys="")
            return

        prior = hist[:-1]
        terminal_on = bool(getattr(self, "chat_terminal_var", None) and self.chat_terminal_var.get())
        skills_on = bool(getattr(self, "chat_skills_var", None) and self.chat_skills_var.get())
        mcp_on = bool(getattr(self, "chat_mcp_var", None) and self.chat_mcp_var.get())
        safety_on = bool(getattr(self, "chat_safety_var", None) and self.chat_safety_var.get())
        laptop_on = bool(getattr(self, "chat_laptop_var", None) and self.chat_laptop_var.get())
        workflow_on = bool(
            getattr(self, "chat_workflow_var", None) and self.chat_workflow_var.get()
        )
        mode = "action"
        if hasattr(self, "chat_mode_var"):
            mode = self.chat_mode_var.get() or "action"
        enabled_names = self._chat_state.get("enabled_skill_names")
        # Prefer per-chat cwd (Task #15)
        try:
            if getattr(self, "_chat_state", None) and self._chat_state.get("terminal_cwd"):
                self._chat_terminal_cwd = str(self._chat_state.get("terminal_cwd"))
        except Exception:  # noqa: BLE001
            pass
        cwd = self._chat_terminal_cwd
        cfg_now = storage.load_config()
        # Task #11: prompt library + project/chat overrides
        try:
            from app.services import prompt_library as plib
            from app.services import project_store as _ps

            _pid = _ps.get_active_project_id()
            _proj = _ps.load_project(_pid) if _pid else None
            user_sys = plib.resolve_effective_system_prompt(
                config_prompt=str(cfg_now.get("system_prompt") or ""),
                project=_proj,
                chat=getattr(self, "_chat_state", None),
            )
        except Exception:  # noqa: BLE001
            user_sys = (cfg_now.get("system_prompt") or "").strip() or get_default_system_prompt()
        # Optional agent persona layered on top of user system prompt
        persona = self._chat_system_prompt()
        if persona and "Default" not in (self.chat_agent_menu.get() if hasattr(self, "chat_agent_menu") else "Default"):
            user_sys = user_sys.rstrip() + "\n\n## Active agent persona\n" + persona
        # Inject memory (does not block; chat remains interactive)
        try:
            from app.services import project_store

            user_sys = user_sys.rstrip() + "\n\n" + memory_prompt_block(
                project_id=project_store.get_active_project_id()
            )
        except Exception:  # noqa: BLE001
            pass
        # Clear pending attachments after queueing send
        self._chat_attachments = []
        if hasattr(self, "chat_attach_label"):
            n_skills = len(discover_skills())
            self.chat_attach_label.configure(
                text=self._attachments_summary()
                + f"  |  skills discovered: {n_skills}  |  mode={mode}"
            )

        # Capture Tk widget values on main thread (never read menus from worker)
        agent_label = "Chat"
        try:
            if hasattr(self, "chat_agent_menu"):
                agent_label = self.chat_agent_menu.get() or "Chat"
        except Exception:  # noqa: BLE001
            agent_label = "Chat"

        def worker() -> None:
            from app.services import agent_tracker
            from app.core.services.llm.providers import resolve_active_llm

            err: str | None = None
            new_hist = hist
            try:
                active = resolve_active_llm()
            except Exception:  # noqa: BLE001
                active = {"model": "?", "provider_name": "chat"}
            run_id = agent_tracker.start_run(
                agent_name=str(agent_label),
                agent_role="interactive",
                model=str(active.get("model") or ""),
                task_title="Chat message",
                input_text=text or "(attachments)",
                source="chat",
            )
            stream_buf: list[str] = []
            stream_state = {"last_ui": 0.0, "started": False, "height_tick": 0}

            def on_stream_delta(delta: str) -> None:
                """Update one live bubble in place — no full transcript rebuild (no flicker)."""
                import time as _time

                if self._chat_cancel:
                    return
                stream_buf.append(delta)
                piece = "".join(stream_buf)
                now = _time.time()
                # Throttle paint: ~5/sec keeps window responsive during long streams
                if now - float(stream_state["last_ui"]) < 0.2 and stream_state["started"]:
                    return
                stream_state["last_ui"] = now
                stream_state["height_tick"] = int(stream_state.get("height_tick") or 0) + 1
                tick = int(stream_state["height_tick"])

                def ui_stream() -> None:
                    if not self.winfo_exists() or self._chat_cancel:
                        return
                    if hasattr(self, "chat_status"):
                        try:
                            self.chat_status.configure(
                                text=f"Typing live… {len(piece)} chars  ·  ■ Stop to cancel"
                            )
                        except Exception:  # noqa: BLE001
                            pass
                    try:
                        # Keep state in sync for final save, but avoid destroy/rebuild
                        msgs = list(self._chat_state.get("messages") or [])
                        while msgs and msgs[-1].get("_streaming"):
                            msgs.pop()
                        msgs.append(
                            {
                                "role": "assistant",
                                "content": piece,
                                "agent_name": str(agent_label),
                                "_streaming": True,
                            }
                        )
                        self._chat_state["messages"] = msgs

                        if self._current_page != "Chat" or not hasattr(self, "chat_scroll"):
                            return
                        # Create streaming bubble once, then only update its label
                        if not stream_state["started"] or not getattr(
                            self, "_stream_bubble_label", None
                        ):
                            self._ensure_stream_bubble(agent_label)
                            stream_state["started"] = True
                        lbl = getattr(self, "_stream_bubble_label", None)
                        if lbl is not None:
                            try:
                                dump = False
                                try:
                                    from app.core.services.chat.chat import looks_like_tool_dump

                                    dump = looks_like_tool_dump(piece)
                                except Exception:  # noqa: BLE001
                                    dump = False
                                if dump:
                                    now = str(getattr(self, "_now_doing_text", "") or "").strip()
                                    show = (
                                        f"{now or 'Working with tools…'}\n"
                                        "Watch Live → Thinking / Terminal (not this bubble)."
                                    )
                                    try:
                                        tbx = getattr(self, "terminal_box", None)
                                        if tbx is not None and tbx.winfo_exists():
                                            tail = piece[-4000:] if len(piece) > 4000 else piece
                                            tbx.configure(state="normal")
                                            tbx.delete("1.0", "end")
                                            tbx.insert("1.0", tail)
                                            tbx.see("end")
                                    except Exception:  # noqa: BLE001
                                        pass
                                else:
                                    show = piece if len(piece) < 20000 else piece[:20000] + "\n…"
                                # Support CTkTextbox (selectable) or legacy CTkLabel
                                if hasattr(lbl, "delete") and hasattr(lbl, "insert"):
                                    # Keep stream box height stable — resizing every tick
                                    # reflows the list and looks like a scroll loop
                                    if tick == 1:
                                        try:
                                            lbl.configure(height=self._reply_view_cap())
                                        except Exception:  # noqa: BLE001
                                            pass
                                    lbl.delete("1.0", "end")
                                    lbl.insert("1.0", show)
                                    try:
                                        lbl.see("end")
                                    except Exception:  # noqa: BLE001
                                        pass
                                else:
                                    lbl.configure(text=show)
                            except Exception:  # noqa: BLE001
                                pass
                            if tick <= 1 or tick % 16 == 0:
                                self._chat_scroll_to_end(force=False)
                    except Exception:  # noqa: BLE001
                        pass

                self._ui_call(ui_stream)

            try:
                cid = str(self._chat_state.get("id") or chat_store.get_active_chat_id() or "")

                def progress_cb(m: str) -> None:
                    msg = m
                    self._ui_call(lambda: self._append_thinking_step(msg))

                # ── Org pipeline switch ON: full multi-agent org flow ──
                if workflow_on:
                    from app.services import project_store
                    from app.core.services.company.org_pipeline import (
                        format_pipeline_for_chat,
                        run_org_pipeline,
                    )

                    # Resolve which org chart to use (fixed vs LLM-create)
                    self._sync_chat_org_selection_to_state()
                    org_mode = str(self._chat_state.get("org_mode") or "fixed")
                    org_gid = str(self._chat_state.get("org_graph_id") or "")
                    graph_for_run = None

                    if org_mode == "llm_create":
                        progress_cb(
                            "✨ LLM designing organisation chart for this goal…"
                        )
                        from app.core.services.company.org_ai import generate_org_chart, summarize_graph_tree

                        gen = generate_org_chart(
                            text or "(attachments only)",
                            make_active=False,
                            link_agents=True,
                        )
                        if not gen.get("ok"):
                            err = f"AI org create failed: {gen.get('error')}"
                            agent_tracker.finish_run(run_id, error=err, status="failed")
                            graph_for_run = None
                        else:
                            graph_for_run = gen.get("graph")
                            org_gid = str(gen.get("graph_id") or "")
                            self._chat_state["org_graph_id"] = org_gid
                            try:
                                progress_cb(
                                    f"Org chart created: {gen.get('graph_name')} "
                                    f"({gen.get('node_count')} nodes)"
                                )
                                for ln in summarize_graph_tree(graph_for_run).splitlines()[:16]:
                                    progress_cb(ln)
                            except Exception:  # noqa: BLE001
                                pass
                    else:
                        progress_cb(
                            f"Org pipeline ON — chart fixed"
                            + (f" id={org_gid[:8]}…" if org_gid else " (active chart)")
                        )

                    if err:
                        pipe = None
                    else:
                        progress_cb(
                            "Each org agent will run, then CEO evaluates & answers"
                        )
                        pipe = run_org_pipeline(
                            text or "(attachments only)",
                            project_id=project_store.get_active_project_id(),
                            on_progress=progress_cb,
                            should_stop=lambda: bool(self._chat_cancel),
                            force_auto_approve=True,
                            graph_id=org_gid if not graph_for_run else None,
                            graph=graph_for_run,
                        )
                    if err:
                        pass
                    elif pipe and pipe.get("cancelled"):
                        err = "Org pipeline stopped by user"
                        agent_tracker.finish_run(run_id, error=err, status="failed")
                    elif pipe and not pipe.get("ok") and not (pipe.get("final_text") or "").strip():
                        err = str(pipe.get("error") or "Org pipeline failed")
                        agent_tracker.finish_run(run_id, error=err, status="failed")
                    elif pipe:
                        # hist already includes optimistic user message
                        base = [m for m in list(hist) if not m.get("_streaming")]
                        pipe_msgs = format_pipeline_for_chat(pipe)
                        new_hist = base + pipe_msgs
                        reply = pipe.get("final_text") or ""
                        for msg in new_hist:
                            msg.pop("_streaming", None)
                        status = "stopped" if self._chat_cancel else "done"
                        agent_tracker.finish_run(
                            run_id,
                            output=reply or "",
                            status=status,
                        )
                        self._last_org_pipeline = pipe
                        # Mirror into Teams-style channel so Team page shows the same run
                        try:
                            from app.services import team_channel as tc
                            from app.services import workflow_graph as wfg

                            g = wfg.resolve_graph(
                                graph_id=str(pipe.get("graph_id") or "") or None
                            )
                            ch = tc.new_channel(
                                text or "(goal)",
                                title=(text or "Org pipeline")[:60],
                                org_graph_id=str(pipe.get("graph_id") or g.get("id") or ""),
                                org_name=str(pipe.get("graph_name") or g.get("name") or ""),
                                mode="pipeline",
                                graph=g,
                            )
                            for a in pipe.get("agent_results") or []:
                                tc.append_message(
                                    ch,
                                    role="agent",
                                    agent_name=str(a.get("agent_name") or "Agent"),
                                    agent_role=str(a.get("agent_role") or ""),
                                    org_node_id=str(a.get("org_node_id") or ""),
                                    content=str(a.get("result") or "(empty)"),
                                )
                            if reply:
                                tc.append_message(
                                    ch,
                                    role="ceo",
                                    agent_name="CEO",
                                    agent_role="ceo",
                                    content=f"**FINAL ANSWER**\n\n{reply}",
                                )
                                tc.set_final(ch, reply)
                            progress_cb(
                                f"Also saved to Team channel — open sidebar Team to review feed"
                            )
                        except Exception:  # noqa: BLE001
                            pass
                else:
                    do_stream = bool(storage.load_config().get("stream_replies", True))
                    new_hist, reply = chat_svc.send_user_message(
                        text,
                        history=prior,
                        system_prompt=user_sys,
                        attachment_paths=attachments,
                        attached_note_ids=note_ids_for_send,
                        mode=mode,
                        terminal_enabled=terminal_on,
                        skills_enabled=skills_on,
                        mcp_enabled=mcp_on,
                        laptop_enabled=laptop_on,
                        safety_mode=safety_on,
                        use_workflow_graph=False,  # soft org prompt only when pipeline OFF
                        enabled_skill_names=enabled_names,
                        terminal_cwd=cwd,
                        agent_name=str(agent_label),
                        chat_id_hint=cid,
                        stream=do_stream,
                        on_stream=on_stream_delta if do_stream else None,
                        should_stop=lambda: bool(self._chat_cancel),
                        is_paused=lambda: bool(getattr(self, "_chat_paused", False)),
                        ask_large_file=self._ask_large_file,
                        ask_large_output=self._ask_large_output,
                        on_progress=progress_cb,
                    )
                    # Tag assistant messages with which agent produced them
                    model_name = str(active.get("model") or "")
                    for msg in new_hist:
                        if msg.get("role") == "assistant" and not msg.get("agent_name"):
                            msg["agent_name"] = str(agent_label)
                            msg["model"] = msg.get("model") or model_name
                        msg.pop("_streaming", None)
                    status = "stopped" if self._chat_cancel else "done"
                    agent_tracker.finish_run(run_id, output=reply or "", status=status)
            except LLMError as e:
                from app.core.services.llm.llm import format_llm_error_message

                err = format_llm_error_message(e)
                agent_tracker.finish_run(run_id, error=err, status="failed")
            except Exception as e:  # noqa: BLE001
                from app.core.services.llm.llm import format_llm_error_message

                err = format_llm_error_message(f"Unexpected error: {e}")
                agent_tracker.finish_run(run_id, error=err, status="failed")

            def finish() -> None:
                # Always clear busy first — even if window is gone or later UI fails
                self._chat_busy = False
                self._chat_cancel = False
                self._chat_paused = False
                self._chat_busy_started = 0.0
                self._stream_bubble_label = None
                try:
                    last = ""
                    steps = list(getattr(self, "_thinking_steps", None) or [])
                    if steps:
                        s = steps[-1]
                        last = s.get("current") or s.get("title") or s.get("text") if isinstance(s, dict) else str(s)
                    self._set_now_doing(str(last or ("error" if err else "reply received")), idle=True)
                except Exception:  # noqa: BLE001
                    pass
                try:
                    if not self.winfo_exists():
                        return
                except Exception:  # noqa: BLE001
                    return
                thinking_msg = None
                try:
                    thinking_msg = self._snapshot_thinking_message(ok=not bool(err))
                    self._finish_thinking_bubble(ok=not bool(err))
                except Exception:  # noqa: BLE001
                    thinking_msg = None

                def _inject_thinking(messages: list) -> list:
                    """Keep thinking in chat history (collapsed) — never drop on final reply."""
                    if not thinking_msg:
                        return messages
                    # Org pipeline already embeds a thinking card — avoid duplicate
                    if any(
                        (m.get("role") == "thinking" and m.get("pipeline") == "org")
                        or m.get("org_pipeline")
                        for m in messages
                    ):
                        return messages
                    out = list(messages)
                    for i in range(len(out) - 1, -1, -1):
                        if (out[i].get("role") or "") == "user":
                            out.insert(i + 1, thinking_msg)
                            return out
                    out.insert(0, thinking_msg)
                    return out

                try:
                    if hasattr(self, "chat_send_btn"):
                        from app.ui.components.layman_copy import send_label as _sl, STOP_LABEL as _st

                        self.chat_send_btn.configure(
                            state="normal", text=_sl(simple=self._is_simple_ui())
                        )
                    if hasattr(self, "chat_stop_btn"):
                        from app.ui.components.layman_copy import STOP_LABEL as _st2

                        self.chat_stop_btn.configure(
                            state="disabled",
                            text=_st2,
                            fg_color=("#d1d5db", "#3f3f46"),
                        )
                    if hasattr(self, "chat_pause_btn"):
                        self.chat_pause_btn.configure(state="disabled", text="⏸ Pause")
                except Exception:  # noqa: BLE001
                    pass
                if err:
                    from datetime import datetime, timezone

                    from app.core.services.llm.llm import format_llm_error_message

                    friendly = format_llm_error_message(err)
                    messages = list(self._chat_state.get("messages") or [])
                    # remove streaming stub
                    messages = [m for m in messages if not m.get("_streaming")]
                    messages = _inject_thinking(messages)
                    # role=error → red error bubble (never dump Cloudflare HTML)
                    messages.append(
                        {
                            "role": "error",
                            "content": friendly,
                            "at": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                    self._chat_state["messages"] = messages
                    try:
                        chat_svc.save_chat(self._chat_state)
                    except Exception:  # noqa: BLE001
                        pass
                    if hasattr(self, "chat_status"):
                        try:
                            n = len((thinking_msg or {}).get("steps") or [])
                            self.chat_status.configure(
                                text=f"Error · thinking saved ({n} steps, collapsed)"
                            )
                        except Exception:  # noqa: BLE001
                            pass
                    # Short status — full text is in the error bubble
                    short = friendly.splitlines()[0][:90] if friendly else "Chat error"
                    self.set_status(short)
                    try:
                        from app.core.services.chat.task_watch import (
                            MIN_ERROR_RETRY_SEC,
                            is_retryable_llm_error,
                        )

                        import time as _time

                        if is_retryable_llm_error(friendly):
                            # Start backoff from this error so we do not immediately re-fire
                            self._auto_continue_last_ts = _time.monotonic()
                            if bool(getattr(self, "_task_cycle_running", False)):
                                wait_ms = int(MIN_ERROR_RETRY_SEC * 1000)
                                self.set_status(
                                    f"{short} — cycle retries in {int(MIN_ERROR_RETRY_SEC)}s",
                                    toast=True,
                                )
                                self.after(wait_ms, self._maybe_auto_continue_task)
                    except Exception:  # noqa: BLE001
                        pass
                else:
                    # Prefer worker history (includes tools); strip streaming stubs
                    cleaned = [m for m in (new_hist or []) if not m.get("_streaming")]
                    cleaned = _inject_thinking(cleaned)
                    if thinking_msg:
                        for _i in range(len(cleaned) - 1, -1, -1):
                            if (cleaned[_i].get("role") or "") == "assistant":
                                cleaned[_i]["_thinking"] = thinking_msg
                                break
                    self._chat_state["messages"] = cleaned
                    self._auto_error_retries = 0
                    self._auto_error_gave_up = False
                    try:
                        from app.core.services.chat.task_watch import apply_inferred_goal

                        cid = str((self._chat_state or {}).get("id") or "")
                        disk = chat_svc.load_chat(cid) if cid else {}
                        if disk and not (self._chat_state or {}).get("current_goal_user_pin"):
                            if disk.get("current_goal"):
                                self._chat_state["current_goal"] = disk.get("current_goal")
                                self._chat_state["current_goal_source"] = (
                                    disk.get("current_goal_source") or "conversation"
                                )
                        apply_inferred_goal(self._chat_state, cleaned)
                    except Exception:  # noqa: BLE001
                        pass
                    try:
                        chat_svc.save_chat(self._chat_state)
                    except Exception:  # noqa: BLE001
                        pass
                    if hasattr(self, "chat_status"):
                        try:
                            n = len((thinking_msg or {}).get("steps") or [])
                            self.chat_status.configure(
                                text=f"Ready · 💭 {n} thinking step(s) kept (collapsed — click to open)"
                                if n
                                else "Ready"
                            )
                        except Exception:  # noqa: BLE001
                            pass
                    try:
                        from app.core.services.data.usage_meter import format_status_line

                        pipe = getattr(self, "_last_org_pipeline", None)
                        if pipe:
                            n_ag = len(pipe.get("agent_results") or [])
                            ae = (pipe.get("agent_evaluation") or {}).get("ok")
                            fe = (pipe.get("final_evaluation") or {}).get("ok")
                            self.set_status(
                                f"Org pipeline done · {n_ag} agents · "
                                f"agent_eval={'pass' if ae else 'issues'} · "
                                f"final_eval={'pass' if fe else 'review'} · "
                                f"{format_status_line()}"
                            )
                            self._last_org_pipeline = None
                        else:
                            self.set_status(f"Reply received.  {format_status_line()}")
                    except Exception:  # noqa: BLE001
                        self.set_status("Reply received.")
                    try:
                        self._voice_maybe_auto_speak(str(reply or ""))
                    except Exception:  # noqa: BLE001
                        pass
                if self._current_page == "Chat":
                    try:
                        self._chat_render_transcript()
                        self._refresh_side_panel()
                    except Exception:  # noqa: BLE001
                        pass
                try:
                    self._refresh_context_chip()
                except Exception:  # noqa: BLE001
                    pass
                try:
                    self._refresh_task_llm_chips()
                    if bool(getattr(self, "_task_cycle_running", False)):
                        self.after(1800, self._maybe_auto_continue_task)
                except Exception:  # noqa: BLE001
                    pass

            # Always hop to main thread via queue (never after() from worker)
            try:
                self._ui_call(finish)
            except Exception:  # noqa: BLE001
                # Last resort: clear busy even if queue failed
                self._chat_busy = False
                self._chat_cancel = False

        def worker_safe() -> None:
            try:
                worker()
            except Exception as e:  # noqa: BLE001
                # Worker crashed without scheduling finish
                try:
                    from app.core.services.llm.llm import format_llm_error_message

                    err_s = format_llm_error_message(f"Unexpected error: {e}")
                except Exception:  # noqa: BLE001
                    err_s = str(e)

                def fail_ui() -> None:
                    self._chat_force_unlock(reason="recovered from crash")
                    try:
                        from datetime import datetime, timezone

                        msgs = list((self._chat_state or {}).get("messages") or [])
                        msgs = [m for m in msgs if not m.get("_streaming")]
                        msgs.append(
                            {
                                "role": "error",
                                "content": err_s,
                                "at": datetime.now(timezone.utc).isoformat(),
                            }
                        )
                        self._chat_state["messages"] = msgs
                        if self._current_page == "Chat":
                            self._chat_render_transcript()
                    except Exception:  # noqa: BLE001
                        pass

                try:
                    self._ui_call(fail_ui)
                except Exception:  # noqa: BLE001
                    self._chat_busy = False

        threading.Thread(target=worker_safe, daemon=True).start()
        # Watchdog: if still busy after 6 minutes, unlock (hung browser/LLM)
        def _watchdog() -> None:
            if not bool(getattr(self, "_chat_busy", False)):
                return
            started = float(getattr(self, "_chat_busy_started", 0) or 0)
            import time as _t

            if started and (_t.monotonic() - started) >= 360:
                self._chat_force_unlock(reason="timed out (6 min)")

        try:
            self.after(360_000, _watchdog)
        except Exception:  # noqa: BLE001
            pass

    def _refresh_chat_tabs_bar(self) -> None:
        if not hasattr(self, "_chat_tabs_bar"):
            return
        from app.ui.themes import UI as _UI, style_chrome_button

        for w in self._chat_tabs_bar.winfo_children():
            w.destroy()
        active = chat_store.get_active_chat_id()
        tabs = list(getattr(self, "_open_chat_tabs", []) or [])
        if active and active not in tabs:
            tabs.insert(0, active)
        tabs = tabs[:5]
        self._open_chat_tabs = tabs
        index_by_id = {}
        try:
            index_by_id = {str(c.get("id")): c for c in (chat_store.list_chats() or [])}
        except Exception:  # noqa: BLE001
            index_by_id = {}
        for cid in tabs:
            try:
                c = index_by_id.get(str(cid)) or {}
                title = (c.get("title") or cid[:6])[:12]
                if c.get("pinned"):
                    title = "📌" + title
            except Exception:  # noqa: BLE001
                title = cid[:6]
            is_active = cid == active
            # Pill-style tab (Batch 2) — active vs idle easier to see
            cell = ctk.CTkFrame(
                self._chat_tabs_bar,
                fg_color=_UI["tab_active_bg"] if is_active else _UI["tab_idle_bg"],
                corner_radius=14,
                border_width=0,
            )
            cell.pack(side="left", padx=3, pady=2)
            ctk.CTkButton(
                cell,
                text=title,
                width=88,
                height=24,
                corner_radius=12,
                fg_color="transparent",
                hover_color=_UI["sidebar_hover"],
                text_color=_UI["tab_active_text"] if is_active else _UI["tab_idle_text"],
                font=ctk.CTkFont(size=12, weight="bold" if is_active else "normal"),
                command=lambda i=cid: self._open_chat_tab(i),
            ).pack(side="left", padx=(4, 0), pady=2)
            ctk.CTkButton(
                cell,
                text="×",
                width=22,
                height=24,
                corner_radius=10,
                fg_color="transparent",
                hover_color=_UI["sidebar_hover"],
                text_color=_UI["muted"],
                command=lambda i=cid: self._close_chat_tab(i),
            ).pack(side="left", padx=(0, 4), pady=2)
        ctk.CTkButton(
            self._chat_tabs_bar,
            text="+",
            width=30,
            height=28,
            corner_radius=14,
            command=self._chat_new_tab,
            **style_chrome_button(primary=True),
        ).pack(side="left", padx=4)

    def _open_chat_tab(self, cid: str) -> None:
        chat_store.set_active_chat_id(cid)
        tabs = list(getattr(self, "_open_chat_tabs", []) or [])
        if cid not in tabs:
            tabs.insert(0, cid)
        self._open_chat_tabs = tabs[:8]
        self._chat_state = chat_svc.load_chat(cid)
        self.show_page("Chat")

    def _close_chat_tab(self, cid: str) -> None:
        tabs = [t for t in (getattr(self, "_open_chat_tabs", []) or []) if t != cid]
        self._open_chat_tabs = tabs
        if chat_store.get_active_chat_id() == cid and tabs:
            self._open_chat_tab(tabs[0])
        elif not tabs:
            c = chat_store.new_chat("New chat")
            self._open_chat_tab(c["id"])
        else:
            self._refresh_chat_tabs_bar()

    def _chat_new_tab(self) -> None:
        c = chat_store.new_chat("New chat")
        self._open_chat_tab(c["id"])

    def _chat_voice_continuous(self) -> None:
        """Toggle continuous voice conversation (Settings mic mode = toggle)."""
        try:
            from app.core.services.ai import voice_settings as _vs
            from app.core.services.ai.stt_service import (
                continuous_running,
                start_continuous,
                stop_continuous,
                stt_capability,
            )
        except Exception as e:  # noqa: BLE001
            messagebox.showinfo("Voice", f"Mic / STT unavailable: {e}", parent=self)
            return

        if continuous_running():
            stop_continuous()
            self.set_status("Continuous voice OFF")
            try:
                self._voice_refresh_composer_buttons()
            except Exception:  # noqa: BLE001
                pass
            return

        if not _vs.mic_enabled():
            messagebox.showinfo(
                "Voice",
                "Mic input is disabled in Settings → Voice.",
                parent=self,
            )
            return

        cap = stt_capability()
        if not cap.get("available"):
            messagebox.showinfo(
                "Voice",
                (cap.get("detail") or "STT unavailable")
                + ("\n" + (cap.get("hint") or "")).rstrip(),
                parent=self,
            )
            self.set_status(f"STT unavailable: {(cap.get('detail') or '')[:80]}")
            return

        lang = _vs.voice_language()

        def on_utt(result: dict) -> None:
            if result.get("degraded") and not result.get("ok"):
                err = str(result.get("error") or "STT unavailable")

                def err_ui() -> None:
                    if not self.winfo_exists():
                        return
                    messagebox.showinfo("Voice", err, parent=self)
                    self.set_status(f"Voice: {err[:80]}")
                    try:
                        self._voice_refresh_composer_buttons()
                    except Exception:  # noqa: BLE001
                        pass

                try:
                    self.after(0, err_ui)
                except Exception:  # noqa: BLE001
                    pass
                return

            text = str(result.get("text") or "").strip()
            if not text:
                return

            def ui() -> None:
                if not self.winfo_exists():
                    return
                if hasattr(self, "chat_input"):
                    try:
                        if getattr(self, "_composer_is_placeholder", False):
                            self._composer_set_text(text)
                        else:
                            self._composer_set_text(text)
                    except Exception:  # noqa: BLE001
                        self.chat_input.delete("1.0", "end")
                        self.chat_input.insert("1.0", text)
                if not self._chat_busy:
                    self._chat_send()
                else:
                    self.set_status(f"Voice (queued): {text[:50]}")

            try:
                self.after(0, ui)
            except Exception:  # noqa: BLE001
                pass

        start_continuous(
            on_utt,
            language=lang,
            on_status=lambda m: self.after(0, lambda: self.set_status(m) if self.winfo_exists() else None),
        )
        self.set_status("Continuous voice ON — speak freely; click 🎤 again to stop")
        try:
            self._voice_refresh_composer_buttons()
        except Exception:  # noqa: BLE001
            pass

    def _chat_web_search_dialog(self) -> None:
        q = simpledialog.askstring("Web search", "Search the web:", parent=self)
        if not q:
            return
        self.set_status(f"Searching: {q}")

        def worker() -> None:
            from app.core.services.web.web_search import web_search

            res = web_search(q, max_results=6)

            def ui() -> None:
                if res.get("ok"):
                    lines = [
                        f"Search: {q}",
                        f"Provider: {res.get('provider') or '?'}  ·  Backends: {', '.join(res.get('backends') or [])}",
                    ]
                    if res.get("note"):
                        lines.append(str(res.get("note"))[:400])
                    if res.get("answer"):
                        lines.append("")
                        lines.append("Engine summary: " + str(res.get("answer"))[:500])
                    if res.get("wiki_only"):
                        lines.append(
                            "Note: mostly encyclopedia results — add a Search API key in "
                            "Settings → Web search for broader results."
                        )
                    lines.append("")
                    for i, r in enumerate(res.get("results") or [], 1):
                        src = r.get("source") or ""
                        lines.append(f"{i}. [{src}] {r.get('title')}")
                        lines.append(f"   {r.get('url')}")
                        if r.get("snippet"):
                            lines.append(f"   {r.get('snippet')[:200]}")
                        lines.append("")
                    for p in res.get("pages") or []:
                        if not p.get("ok"):
                            lines.append(f"Page fail: {p.get('url')} — {p.get('error')}")
                            continue
                        lines.append(f"### Read: {p.get('title') or p.get('url')}")
                        lines.append((p.get("text") or "")[:1500])
                        lines.append("")
                    body = "\n".join(lines)
                    hist = list(self._chat_state.get("messages") or [])
                    hist.append({"role": "assistant", "content": body, "agent_name": "WebSearch"})
                    self._chat_state["messages"] = hist
                    chat_svc.save_chat(self._chat_state)
                    if self._current_page == "Chat":
                        self._chat_render_transcript()
                    self.set_status(f"Search done: {res.get('count')} results", toast=True)
                else:
                    msg = str(res.get("error") or "Search failed")
                    if res.get("hint"):
                        msg += "\n\n" + str(res.get("hint"))
                    messagebox.showerror("Search", msg, parent=self)
                    self.set_status(f"Search failed: {res.get('error')}", toast=True)

            self.after(0, ui)

        threading.Thread(target=worker, daemon=True).start()

    def _chat_browse_dialog(self) -> None:
        """GUI entry for portable browser: open URL, screenshot, or extract text."""
        from app.ui.themes import style_chrome_button, style_entry, UI as _UI

        win = ctk.CTkToplevel(self)
        win.title("Browse URL")
        win.geometry("480x280")
        win.transient(self)
        win.grab_set()
        ctk.CTkLabel(
            win,
            text="Open a page with the built-in browser (portable Chromium)",
            font=ctk.CTkFont(weight="bold"),
            text_color=_UI["label"],
        ).pack(anchor="w", padx=14, pady=(14, 6))
        ctk.CTkLabel(
            win,
            text="Results appear in chat (screenshot / text). Requires Launch.bat browser setup once.",
            text_color=_HC_MUTED,
            wraplength=440,
            justify="left",
        ).pack(anchor="w", padx=14, pady=(0, 8))
        url_var = ctk.StringVar(value="https://example.com")
        ctk.CTkEntry(win, textvariable=url_var, width=440, **style_entry()).pack(padx=14, pady=4)
        action_var = ctk.StringVar(value="screenshot")
        ctk.CTkOptionMenu(
            win, variable=action_var, values=["screenshot", "text", "goto", "html"], width=160
        ).pack(anchor="w", padx=14, pady=6)

        def run() -> None:
            url = (url_var.get() or "").strip()
            if not url:
                return
            act = action_var.get() or "screenshot"
            win.destroy()
            self.set_status(f"Browser: {act} {url[:40]}…", toast=True)

            def worker() -> None:
                try:
                    from app.core.services.web.browser_tool import run_browser

                    res = run_browser(action=act, url=url)
                except Exception as e:  # noqa: BLE001
                    res = {"ok": False, "error": str(e)}

                def ui() -> None:
                    hist = list(self._chat_state.get("messages") or [])
                    content = f"### Browser ({act})\nURL: {url}\n\n```json\n{res}\n```"
                    imgs = []
                    if isinstance(res, dict) and res.get("path"):
                        p = str(res.get("path"))
                        if p.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                            imgs.append(p)
                    hist.append(
                        {
                            "role": "screenshot" if imgs else "assistant",
                            "content": content,
                            "agent_name": "Browser",
                            "images": imgs,
                        }
                    )
                    self._chat_state["messages"] = hist
                    chat_svc.save_chat(self._chat_state)
                    if self._current_page == "Chat":
                        self._chat_render_transcript()
                    ok = bool(isinstance(res, dict) and res.get("ok", True) and not res.get("error"))
                    self.set_status(
                        "Browser done" if ok else f"Browser: {res.get('error') if isinstance(res, dict) else res}",
                        toast=True,
                    )

                self.after(0, ui)

            threading.Thread(target=worker, daemon=True).start()

        ctk.CTkButton(win, text="Run", width=100, command=run, **style_chrome_button(primary=True)).pack(
            pady=12
        )

    def _chat_ocr_dialog(self) -> None:
        path = filedialog.askopenfilename(
            title="OCR image",
            filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.bmp;*.webp"), ("All", "*.*")],
        )
        if not path:
            return
        self.set_status("Running OCR…")

        def worker() -> None:
            from app.core.services.web.ocr_service import ocr_image

            res = ocr_image(path)

            def ui() -> None:
                if res.get("ok"):
                    hist = list(self._chat_state.get("messages") or [])
                    hist.append(
                        {
                            "role": "assistant",
                            "content": f"OCR ({res.get('engine')}):\n\n{res.get('text')}",
                            "agent_name": "OCR",
                            "images": [path],
                        }
                    )
                    self._chat_state["messages"] = hist
                    chat_svc.save_chat(self._chat_state)
                    if self._current_page == "Chat":
                        self._chat_render_transcript()
                    self.set_status("OCR done")
                else:
                    messagebox.showerror("OCR", str(res.get("error")), parent=self)

            self.after(0, ui)

        threading.Thread(target=worker, daemon=True).start()

    def _voice_refresh_composer_buttons(self) -> None:
        """Enable/disable mic & speak controls from Settings + capability (never raises)."""
        try:
            from app.core.services.ai import voice_settings as _vs
            from app.core.services.ai.stt_service import continuous_running, stt_capability
            from app.core.services.ai.tts_service import tts_capability
        except Exception:  # noqa: BLE001
            return
        try:
            mic_on = bool(_vs.mic_enabled())
            tts_on = bool(_vs.tts_enabled())
            stt = stt_capability()
            tts = tts_capability()
            mic_ok = mic_on and bool(stt.get("available"))
            tts_ok = tts_on and bool(tts.get("available"))
            if hasattr(self, "chat_mic_btn"):
                try:
                    self.chat_mic_btn.configure(state="normal" if mic_on else "disabled")
                    tip = chat_control_help("mic")
                    if not mic_on:
                        tip = "Mic disabled in Settings → Voice"
                    elif not stt.get("available"):
                        tip = f"Mic unavailable: {stt.get('detail') or 'no STT engine'}"
                    elif _vs.mic_mode() == "toggle":
                        tip = (
                            "Continuous voice ON — click to stop"
                            if continuous_running()
                            else "Toggle continuous voice listen (Settings: mic mode = toggle)"
                        )
                    self._tooltip(self.chat_mic_btn, tip)
                except Exception:  # noqa: BLE001
                    pass
            if hasattr(self, "chat_speak_btn"):
                try:
                    self.chat_speak_btn.configure(state="normal" if tts_on else "disabled")
                    tip = chat_control_help("speak")
                    if not tts_on:
                        tip = "TTS disabled in Settings → Voice"
                    elif not tts.get("available"):
                        tip = f"TTS unavailable: {tts.get('detail') or 'no engine'}"
                    self._tooltip(self.chat_speak_btn, tip)
                except Exception:  # noqa: BLE001
                    pass
            # Silence unused when engines missing — buttons stay clickable to show reason
            _ = mic_ok, tts_ok
        except Exception:  # noqa: BLE001
            pass

    def _voice_maybe_auto_speak(self, reply: str) -> None:
        """Optional auto read-aloud of assistant replies (Settings). Soft-degrades."""
        try:
            from app.core.services.ai import voice_settings as _vs
            from app.core.services.ai.tts_service import speak_text, tts_capability
        except Exception:  # noqa: BLE001
            return
        try:
            if not _vs.tts_enabled() or not _vs.auto_read_aloud():
                return
            if not (reply or "").strip():
                return
            cap = tts_capability()
            if not cap.get("available"):
                self.set_status(f"Auto-speak skipped: {(cap.get('detail') or 'TTS unavailable')[:80]}")
                return
            speak_text(reply, async_play=True)
            self.set_status("Auto-speaking assistant reply…")
        except Exception:  # noqa: BLE001
            pass

    def _chat_mic(self) -> None:
        """Speech-to-text into the chat input (Ctrl+M). Respects Settings → Voice."""
        try:
            from app.core.services.ai import voice_settings as _vs
            from app.core.services.ai.stt_service import continuous_running, listen_async, stt_capability
        except Exception as e:  # noqa: BLE001
            messagebox.showinfo("Mic / STT", f"Mic unavailable: {e}", parent=self)
            return

        if not _vs.mic_enabled():
            messagebox.showinfo(
                "Mic / STT",
                "Mic input is disabled in Settings → Voice. Enable “Mic input in chat” to use 🎤.",
                parent=self,
            )
            return

        # Toggle mode → continuous conversation
        if _vs.mic_mode() == "toggle":
            self._chat_voice_continuous()
            return

        if continuous_running():
            from app.core.services.ai.stt_service import stop_continuous

            stop_continuous()
            self.set_status("Continuous voice OFF")
            try:
                self._voice_refresh_composer_buttons()
            except Exception:  # noqa: BLE001
                pass
            return

        if getattr(self, "_mic_busy", False):
            self.set_status("Mic already listening…")
            return

        cap = stt_capability()
        if not cap.get("available"):
            messagebox.showinfo(
                "Mic / STT",
                (cap.get("detail") or "STT unavailable")
                + ("\n" + (cap.get("hint") or "")).rstrip(),
                parent=self,
            )
            self.set_status(f"Mic unavailable: {(cap.get('detail') or '')[:80]}")
            return

        self._mic_busy = True
        self.set_status("🎤 Listening… speak now")
        if hasattr(self, "chat_status"):
            try:
                self.chat_status.configure(text="Listening…")
            except Exception:  # noqa: BLE001
                pass

        lang = _vs.voice_language()

        def done(result: dict) -> None:
            def ui() -> None:
                self._mic_busy = False
                if not self.winfo_exists():
                    return
                if result.get("ok") and result.get("text"):
                    text = str(result["text"]).strip()
                    if hasattr(self, "chat_input"):
                        if getattr(self, "_composer_is_placeholder", False):
                            self._composer_set_text(text)
                        else:
                            cur = self.chat_input.get("1.0", "end").strip()
                            if cur:
                                self._composer_set_text(" " + text, append=True)
                            else:
                                self._composer_set_text(text)
                    self.set_status(f"Mic OK ({result.get('engine')}): {text[:60]}")
                    if hasattr(self, "chat_status"):
                        self.chat_status.configure(text="Ready")
                else:
                    err = result.get("error") or "No speech"
                    hint = result.get("hint") or ""
                    msg = err + (f"\n{hint}" if hint else "")
                    messagebox.showinfo("Mic / STT", msg, parent=self)
                    self.set_status(f"Mic: {err[:80]}")
                    if hasattr(self, "chat_status"):
                        self.chat_status.configure(text="Ready")

            try:
                self.after(0, ui)
            except Exception:  # noqa: BLE001
                self._mic_busy = False

        listen_async(
            done,
            language=lang,
            on_status=lambda m: self.after(0, lambda: self.set_status(m) if self.winfo_exists() else None),
        )

    def _chat_toggle_pin(self) -> None:
        cid = self._chat_state.get("id") or chat_store.get_active_chat_id()
        if not cid:
            return
        c = chat_store.toggle_pin(cid)
        self._chat_state = chat_svc.load_chat(cid)
        pin = "📌 pinned" if c.get("pinned") else "unpinned"
        if hasattr(self, "chat_title_label"):
            mark = "📌 " if c.get("pinned") else ""
            self.chat_title_label.configure(text=f"{mark}{c.get('title') or 'Chat'}")
        self.set_status(f"Chat {pin}")

    def _chat_branch(self) -> None:
        cid = self._chat_state.get("id") or chat_store.get_active_chat_id()
        c = chat_store.branch_chat(cid)
        self._chat_state = chat_svc.load_chat(c["id"])
        self.show_page("Chat")
        self.set_status(f"Branched chat → {c.get('title')}")

    def _chat_save_to_project(self) -> None:
        from app.services import project_outputs, project_store

        pid = project_store.get_active_project_id()
        if not pid:
            messagebox.showinfo(
                "Save to project",
                "Select or create an active project in Projects tab first.",
                parent=self,
            )
            return
        msgs = list(self._chat_state.get("messages") or [])
        if not msgs:
            messagebox.showinfo("Save to project", "No messages to save.", parent=self)
            return
        res = project_outputs.save_chat_exchange_to_project(
            msgs,
            title=str(self._chat_state.get("title") or "chat"),
            project_id=pid,
            agent_name="Chat",
        )
        if res.get("ok"):
            messagebox.showinfo("Saved", f"Wrote:\n{res.get('path')}", parent=self)
            self.set_status(f"Saved to project: {res.get('name')}")
        else:
            messagebox.showerror("Save failed", str(res.get("error")), parent=self)

    def _chat_image_gen_dialog(self) -> None:
        prompt = simpledialog.askstring(
            "Generate image",
            "Describe the image to generate:",
            parent=self,
        )
        if not prompt:
            return
        self.set_status("Generating image…")

        def worker() -> None:
            err = None
            paths: list[str] = []
            try:
                from app.core.services.ai.image_gen import generate_image, ImageGenError
                from app.core.services.chat.chat_store import get_active_chat_id

                res = generate_image(prompt, chat_id=get_active_chat_id() or "default")
                paths = list(res.get("paths") or [])
            except Exception as e:  # noqa: BLE001
                err = str(e)

            def finish() -> None:
                if err:
                    messagebox.showerror("Image gen", err, parent=self)
                    self.set_status(f"Image gen failed: {err[:80]}")
                    return
                hist = list(self._chat_state.get("messages") or [])
                hist.append(
                    {
                        "role": "assistant",
                        "content": f"Generated image:\n{prompt}",
                        "images": paths,
                        "agent_name": "ImageGen",
                    }
                )
                self._chat_state["messages"] = hist
                chat_svc.save_chat(self._chat_state)
                if self._current_page == "Chat":
                    self._chat_render_transcript()
                self.set_status(f"Image generated ({len(paths)} file(s))")

            self.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    def _page_patches(self) -> None:
        from app.services import patch_review

        root = ctk.CTkFrame(self.content, fg_color="transparent")
        root.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
        root.grid_columnconfigure(0, weight=1)
        root.grid_columnconfigure(1, weight=2)
        root.grid_rowconfigure(2, weight=1)

        self._page_header(
            root,
            "Patch review",
            "LLM-proposed code changes wait here. Review the diff, then Apply (backed up) or Reject.",
            columnspan=2,
            actions=[("Refresh", lambda: self.show_page("Patches"))],
        )

        left = ctk.CTkScrollableFrame(root)
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        right = ctk.CTkTextbox(root, wrap="none", font=ctk.CTkFont(family="Consolas", size=12))
        right.grid(row=1, column=1, sticky="nsew")
        root.grid_rowconfigure(1, weight=1)

        state: dict[str, str] = {"id": ""}

        def show(p: dict) -> None:
            state["id"] = p.get("id") or ""
            right.delete("1.0", "end")
            right.insert(
                "1.0",
                f"Path: {p.get('path')}\nNote: {p.get('note')}\nStatus: {p.get('status')}\n\n"
                f"======== DIFF ========\n{p.get('diff') or ''}\n",
            )

        def refresh() -> None:
            for w in left.winfo_children():
                w.destroy()
            pending = patch_review.list_pending()
            if not pending:
                ctk.CTkLabel(left, text="No pending patches").pack(anchor="w", padx=6, pady=8)
            for p in pending:
                row = ctk.CTkFrame(left)
                row.pack(fill="x", pady=4, padx=4)
                ctk.CTkLabel(
                    row,
                    text=f"{p.get('path')}\n{(p.get('note') or '')[:80]}",
                    anchor="w",
                    justify="left",
                    wraplength=260,
                ).pack(anchor="w", padx=6, pady=4)
                bar = ctk.CTkFrame(row, fg_color="transparent")
                bar.pack(fill="x", padx=4, pady=4)
                ctk.CTkButton(bar, text="View", width=60, command=lambda i=p: show(i)).pack(
                    side="left", padx=2
                )
                ctk.CTkButton(
                    bar,
                    text="Apply",
                    width=70,
                    command=lambda i=p["id"]: (
                        messagebox.showinfo("Apply", str(patch_review.apply_patch(i)), parent=self),
                        refresh(),
                    ),
                ).pack(side="left", padx=2)
                ctk.CTkButton(
                    bar,
                    text="Reject",
                    width=70,
                    fg_color="#a33",
                    command=lambda i=p["id"]: (patch_review.reject_patch(i), refresh()),
                ).pack(side="left", padx=2)

        ctk.CTkButton(root, text="Refresh list", command=refresh).grid(row=2, column=0, sticky="w", pady=8)
        refresh()

    def _page_schedule(self) -> None:
        from app.services import scheduler_service as sched
        from app.ui.themes import style_chrome_button

        root = ctk.CTkFrame(self.content, fg_color="transparent")
        root.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(2, weight=1)

        self._page_header(
            root,
            "Scheduled agents",
            "Recurring company tasks. Sticky Add bar stays fixed; schedule list scrolls below.",
            actions=[("Work board", lambda: self.show_page("Work"))],
        )

        # Sticky add bar (always visible — not inside the list scroll)
        form = ctk.CTkFrame(
            root,
            fg_color=_THEME_UI.get("top_bg", ("#f3f4f6", "#161a22")),
            corner_radius=10,
            border_width=1,
            border_color=_THEME_UI.get("top_border", ("#6b7280", "#4b5563")),
        )
        form.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        title_e = ctk.CTkEntry(form, placeholder_text="Title", width=180)
        title_e.pack(side="left", padx=(10, 4), pady=10)
        mins_e = ctk.CTkEntry(form, placeholder_text="Minutes", width=70)
        mins_e.insert(0, "60")
        mins_e.pack(side="left", padx=4, pady=10)
        prompt_e = ctk.CTkEntry(form, placeholder_text="Task prompt / description", width=280)
        prompt_e.pack(side="left", padx=4, pady=10, fill="x", expand=True)

        list_f = ctk.CTkScrollableFrame(root, fg_color="transparent")
        list_f.grid(row=2, column=0, sticky="nsew", pady=0)

        def refresh() -> None:
            for w in list_f.winfo_children():
                w.destroy()
            items = sched.load_schedules()
            if not items:
                ctk.CTkLabel(
                    list_f,
                    text="No schedules yet. Fill the bar above and click Add schedule.",
                    text_color=_HC_MUTED,
                ).pack(padx=12, pady=20)
                return
            for s in items:
                row = ctk.CTkFrame(list_f)
                row.pack(fill="x", pady=3)
                en = "ON" if s.get("enabled") else "OFF"
                ctk.CTkLabel(
                    row,
                    text=(
                        f"[{en}] every {s.get('interval_minutes')}m · {s.get('title')}\n"
                        f"runs={s.get('run_count')} last={str(s.get('last_run') or '—')[:19]}\n"
                        f"{(s.get('prompt') or '')[:120]}"
                    ),
                    anchor="w",
                    justify="left",
                    wraplength=700,
                ).pack(side="left", fill="x", expand=True, padx=8, pady=6)
                ctk.CTkButton(
                    row,
                    text="Toggle",
                    width=70,
                    command=lambda i=s["id"], e=not s.get("enabled"): (
                        sched.set_enabled(i, e),
                        refresh(),
                    ),
                ).pack(side="right", padx=4)
                ctk.CTkButton(
                    row,
                    text="Delete",
                    width=70,
                    fg_color="#a33",
                    command=lambda i=s["id"]: (sched.delete_schedule(i), refresh()),
                ).pack(side="right", padx=4)

        def add() -> None:
            try:
                mins = int(mins_e.get().strip() or "60")
            except ValueError:
                mins = 60
            sched.add_schedule(
                title=title_e.get().strip() or "Scheduled",
                prompt=prompt_e.get().strip() or title_e.get().strip(),
                interval_minutes=mins,
            )
            sched.start()
            title_e.delete(0, "end")
            prompt_e.delete(0, "end")
            refresh()
            self.set_status("Schedule added", toast=True)

        ctk.CTkButton(
            form,
            text="💾  Add schedule",
            width=140,
            height=34,
            command=add,
            **style_chrome_button(primary=True),
        ).pack(side="left", padx=6, pady=10)
        ctk.CTkButton(
            form,
            text="Run due now",
            width=110,
            height=34,
            command=lambda: (sched.tick(), refresh()),
        ).pack(side="left", padx=4, pady=10)
        self._page_save_handler = add
        refresh()

    def _page_knowledge(self) -> None:
        from app.services import rag_knowledge as rag
        from app.services import file_watcher, local_embeddings

        root = ctk.CTkFrame(self.content, fg_color="transparent")
        root.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(2, weight=1)

        try:
            health = rag.knowledge_health()
            hsub = (
                f"{health.get('documents', 0)} docs · {health.get('chunks', 0)} chunks · "
                f"{health.get('watches', 0)} watches"
            )
        except Exception:  # noqa: BLE001
            hsub = "Index PDFs/MD/code · hybrid BM25+embeddings+RRF · optional folder auto-watch."
        self._page_header(
            root,
            "Local Knowledge (RAG)",
            hsub,
            actions=[("Refresh", lambda: self.show_page("Knowledge"))],
        )

        bar = ctk.CTkFrame(root)
        bar.grid(row=1, column=0, sticky="ew", pady=4)

        def do_index_file() -> None:
            path = filedialog.askopenfilename(
                title="Index document",
                filetypes=[
                    ("Documents", "*.pdf;*.md;*.txt;*.py;*.json;*.csv"),
                    ("All", "*.*"),
                ],
            )
            if not path:
                return
            r = rag.index_file(path)
            if r.get("ok"):
                local_embeddings.index_embeddings_for_all()
                messagebox.showinfo(
                    "Indexed", f"{r.get('title')}\n{r.get('chunks')} chunks", parent=self
                )
                refresh()
            else:
                messagebox.showerror("Index failed", str(r.get("error")), parent=self)

        def do_index_folder() -> None:
            path = filedialog.askdirectory(title="Index folder")
            if not path:
                return
            r = rag.index_folder(path)
            local_embeddings.index_embeddings_for_all()
            messagebox.showinfo(
                "Folder index",
                f"Indexed {r.get('indexed')} files · errors {r.get('errors')}",
                parent=self,
            )
            refresh()

        def do_watch() -> None:
            path = filedialog.askdirectory(title="Watch folder (auto-index)")
            if not path:
                return
            r = file_watcher.add_watch(path)
            messagebox.showinfo("Watch", str(r), parent=self)
            refresh_watch()

        def do_search() -> None:
            q = search_e.get().strip()
            if not q:
                return
            hits = local_embeddings.hybrid_search(q, limit=12)
            if not hits:
                hits = rag.search(q, limit=12)
            result_box.delete("1.0", "end")
            if not hits:
                result_box.insert("1.0", "No matches.")
                return
            lines = []
            for i, h in enumerate(hits, 1):
                sc = h.get("emb_score")
                lines.append(f"[{i}] {h.get('title')} — {h.get('path')}" + (f" score={sc}" if sc is not None else ""))
                lines.append((h.get("content") or "")[:500])
                lines.append("")
            result_box.insert("1.0", "\n".join(lines))

        ctk.CTkButton(bar, text="Index file…", command=do_index_file).pack(side="left", padx=4, pady=6)
        ctk.CTkButton(bar, text="Index folder…", command=do_index_folder).pack(
            side="left", padx=4, pady=6
        )
        ctk.CTkButton(bar, text="Watch folder…", command=do_watch).pack(side="left", padx=4, pady=6)
        ctk.CTkButton(
            bar,
            text="Rebuild embeddings",
            width=140,
            command=lambda: (
                messagebox.showinfo("Embeddings", str(local_embeddings.index_embeddings_for_all()), parent=self)
            ),
        ).pack(side="left", padx=4)
        search_e = ctk.CTkEntry(bar, placeholder_text="Search knowledge…", width=240)
        search_e.pack(side="left", padx=8, pady=6)
        ctk.CTkButton(bar, text="Search", width=80, command=do_search).pack(side="left", padx=2)
        ctk.CTkButton(
            bar,
            text="Clear all",
            width=80,
            fg_color="#a33",
            command=lambda: (rag.clear_all(), refresh()),
        ).pack(side="left", padx=8)

        body = ctk.CTkFrame(root)
        body.grid(row=2, column=0, sticky="nsew", pady=8)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(body, text="Indexed documents", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, sticky="w", padx=6
        )
        ctk.CTkLabel(body, text="Search results", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=1, sticky="w", padx=6
        )
        docs_box = ctk.CTkScrollableFrame(body)
        docs_box.grid(row=1, column=0, sticky="nsew", padx=6, pady=4)
        result_box = ctk.CTkTextbox(body, wrap="word")
        result_box.grid(row=1, column=1, sticky="nsew", padx=6, pady=4)

        watch_lbl = ctk.CTkLabel(root, text="", text_color=_HC_MUTED, anchor="w", justify="left")
        watch_lbl.grid(row=4, column=0, sticky="w", pady=4)

        def refresh_watch() -> None:
            ws = file_watcher.load_watches()
            if not ws:
                watch_lbl.configure(text="Watches: (none) — use Watch folder… for auto-index")
            else:
                lines = [f"Watches ({'running' if file_watcher.is_running() else 'idle'}):"]
                for w in ws:
                    lines.append(f"  · {w.get('path')}  indexed+={w.get('indexed')}  last={w.get('last_scan') or '—'}")
                watch_lbl.configure(text="\n".join(lines))

        def refresh() -> None:
            for w in docs_box.winfo_children():
                w.destroy()
            docs = rag.list_documents()
            if not docs:
                ctk.CTkLabel(docs_box, text="No documents yet. Index a file or folder.").pack(
                    anchor="w", padx=6, pady=8
                )
            for d in docs:
                row = ctk.CTkFrame(docs_box)
                row.pack(fill="x", pady=3)
                ctk.CTkLabel(
                    row,
                    text=f"{d.get('title')}  ·  {d.get('chunk_count')} chunks\n{d.get('path')}",
                    anchor="w",
                    justify="left",
                    wraplength=340,
                ).pack(side="left", fill="x", expand=True, padx=4)
                ctk.CTkButton(
                    row,
                    text="Delete",
                    width=60,
                    command=lambda i=d["id"]: (rag.delete_document(i), refresh()),
                ).pack(side="right", padx=4)
            refresh_watch()

        refresh()

    def _page_approvals(self) -> None:
        from app.services import tool_approvals
        from app.services import company_store as company

        root = ctk.CTkFrame(self.content, fg_color="transparent")
        root.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
        root.grid_columnconfigure(0, weight=1)
        root.grid_columnconfigure(1, weight=1)
        root.grid_rowconfigure(1, weight=1)

        self._page_header(
            root,
            "Approvals queue",
            "Tool actions (when Safety / tool approval is on) + company task approvals. Chat stays free.",
            columnspan=2,
            actions=[
                ("Refresh", lambda: self.show_page("Approvals")),
                ("Work", lambda: self.show_page("Work")),
            ],
        )

        left = ctk.CTkScrollableFrame(root)
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        right = ctk.CTkScrollableFrame(root)
        right.grid(row=1, column=1, sticky="nsew", padx=(8, 0))

        cfg = storage.load_config()
        top = ctk.CTkFrame(root)
        top.grid(row=2, column=0, columnspan=2, sticky="ew", pady=8)
        req_var = ctk.BooleanVar(value=bool(cfg.get("tool_approval_required")))

        def toggle_req() -> None:
            c = storage.load_config()
            c["tool_approval_required"] = bool(req_var.get())
            storage.save_config(c)
            self.set_status(
                "Tool approval ON — risky tools wait here"
                if req_var.get()
                else "Tool approval OFF — tools run immediately"
            )

        ctk.CTkSwitch(
            top, text="Require tool approval (terminal/GUI/pip/MCP)", variable=req_var, command=toggle_req
        ).pack(side="left", padx=8)
        ctk.CTkButton(
            top, text="Approve all tools", width=120, command=lambda: (tool_approvals.approve_all_pending(), refresh())
        ).pack(side="left", padx=8)
        ctk.CTkButton(top, text="Refresh", width=80, command=lambda: refresh()).pack(side="left", padx=4)

        def refresh() -> None:
            for w in left.winfo_children():
                w.destroy()
            for w in right.winfo_children():
                w.destroy()
            ctk.CTkLabel(left, text="Tool approvals", font=ctk.CTkFont(weight="bold")).pack(
                anchor="w", padx=6, pady=4
            )
            pending = tool_approvals.list_pending()
            if not pending:
                ctk.CTkLabel(left, text="No pending tool approvals").pack(anchor="w", padx=8, pady=6)
            for ap in pending:
                row = ctk.CTkFrame(left)
                row.pack(fill="x", pady=4, padx=4)
                ctk.CTkLabel(
                    row,
                    text=f"[{ap.get('tool')}] {ap.get('summary')}",
                    wraplength=340,
                    justify="left",
                    anchor="w",
                ).pack(anchor="w", padx=6, pady=4)
                bar = ctk.CTkFrame(row, fg_color="transparent")
                bar.pack(fill="x", padx=6, pady=4)
                ctk.CTkButton(
                    bar,
                    text="Approve",
                    width=80,
                    command=lambda i=ap["id"]: (tool_approvals.approve(i), refresh()),
                ).pack(side="left", padx=2)
                ctk.CTkButton(
                    bar,
                    text="Reject",
                    width=80,
                    fg_color="#a33",
                    command=lambda i=ap["id"]: (tool_approvals.reject(i), refresh()),
                ).pack(side="left", padx=2)

            ctk.CTkLabel(right, text="Company task approvals", font=ctk.CTkFont(weight="bold")).pack(
                anchor="w", padx=6, pady=4
            )
            for ap in company.list_approvals(status="pending"):
                row = ctk.CTkFrame(right)
                row.pack(fill="x", pady=4, padx=4)
                ctk.CTkLabel(
                    row,
                    text=(ap.get("summary") or "")[:220],
                    wraplength=340,
                    justify="left",
                    anchor="w",
                ).pack(anchor="w", padx=6, pady=4)
                bar = ctk.CTkFrame(row, fg_color="transparent")
                bar.pack(fill="x", padx=6, pady=4)
                ctk.CTkButton(
                    bar,
                    text="Approve",
                    width=80,
                    command=lambda i=ap["id"]: (
                        get_orchestrator().approve(i),
                        refresh(),
                    ),
                ).pack(side="left", padx=2)
                ctk.CTkButton(
                    bar,
                    text="Reject",
                    width=80,
                    fg_color="#a33",
                    command=lambda i=ap["id"]: (
                        get_orchestrator().reject(i),
                        refresh(),
                    ),
                ).pack(side="left", padx=2)
            if not company.list_approvals(status="pending"):
                ctk.CTkLabel(right, text="No pending company approvals").pack(anchor="w", padx=8, pady=6)

            ctk.CTkLabel(left, text="Recent tool decisions", text_color=_HC_MUTED).pack(
                anchor="w", padx=6, pady=(12, 4)
            )
            for ap in tool_approvals.list_all(12):
                if ap.get("status") == "pending":
                    continue
                ctk.CTkLabel(
                    left,
                    text=f"{ap.get('status')}: [{ap.get('tool')}] {str(ap.get('summary') or '')[:80]}",
                    text_color=_HC_MUTED,
                    anchor="w",
                    wraplength=340,
                ).pack(anchor="w", padx=8, pady=1)

        refresh()

    def _page_usage(self) -> None:
        from app.core.services.data.usage_meter import get_summary, reset_usage, format_status_line
        from app.core.services.tools.tool_budget import (
            get_budgets,
            set_budgets,
            DEFAULT_BUDGETS,
            get_parallel_caps,
            set_parallel_caps,
        )

        root = ctk.CTkFrame(self.content, fg_color="transparent")
        root.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(1, weight=1)

        self._page_header(
            root,
            "Usage & budgets",
            format_status_line() + "  ·  Estimates only (varies by provider pricing)",
            actions=[("Refresh", lambda: self.show_page("Usage"))],
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

        # Task #14: parallel agent caps
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
            self.set_status("Budgets + parallel caps saved", toast=True)
            messagebox.showinfo(
                "Budgets",
                "Saved tool budgets and parallel agent caps for future runs.",
                parent=self,
            )

        bar = ctk.CTkFrame(body, fg_color="transparent")
        bar.pack(fill="x", pady=8)
        ctk.CTkButton(bar, text="Save budgets", command=save_b).pack(side="left", padx=4)
        ctk.CTkButton(
            bar,
            text="Reset usage counters",
            fg_color="#a33",
            command=lambda: (reset_usage(), self.show_page("Usage")),
        ).pack(side="left", padx=4)
        ctk.CTkButton(bar, text="Refresh", command=lambda: self.show_page("Usage")).pack(
            side="left", padx=4
        )

    def _page_agents(self) -> None:
        from app.ui.themes import style_chrome_button
        from app.ui.components.page_layout import attach_save_bar_to_form_panel, make_list_form_page

        layout = make_list_form_page(self.content, list_width=260)
        self._page_form_layout = layout  # for Ctrl+S
        self._page_save_handler = self._agent_save

        self._page_header(
            layout.header_parent,
            "Agents",
            "Scroll the form if needed. Save stays on the bar below — never off-screen. Empty LLM fields = Settings default.",
            columnspan=1,
            actions=[("New Agent", self._agent_new)],
        )

        # Left list header
        assert layout.list_panel is not None and layout.list_scroll is not None
        ctk.CTkButton(
            layout.list_panel,
            text="New Agent",
            command=self._agent_new,
            **style_chrome_button(primary=True),
        ).grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        self.agent_list = layout.list_scroll

        form = layout.form_scroll
        assert form is not None
        form.grid_columnconfigure(1, weight=1)

        self.agent_id_var = ctk.StringVar(value="")
        self.agent_name = ctk.CTkEntry(form, placeholder_text="Name")
        self.agent_role = ctk.CTkEntry(form, placeholder_text="Role")
        self.agent_goal = ctk.CTkEntry(form, placeholder_text="Goal")
        self.agent_backstory = ctk.CTkTextbox(form, height=70)
        self.agent_llm_model = ctk.CTkEntry(
            form, placeholder_text="e.g. gpt-4o-mini or grok-2 (empty=Settings)"
        )
        self.agent_llm_base = ctk.CTkEntry(
            form, placeholder_text="https://api.openai.com/v1 (empty=Settings)"
        )
        self.agent_llm_key = ctk.CTkEntry(
            form,
            placeholder_text="API key for this agent only (empty=Settings)",
            show="*",
        )
        self.agent_system_prompt = ctk.CTkTextbox(form, height=100)
        self.agent_error = ctk.CTkLabel(form, text="", text_color="tomato")

        labels = [
            "Name *",
            "Role *",
            "Goal *",
            "Backstory",
            "LLM model",
            "LLM base URL",
            "LLM API key",
            "System prompt",
        ]
        widgets = [
            self.agent_name,
            self.agent_role,
            self.agent_goal,
            self.agent_backstory,
            self.agent_llm_model,
            self.agent_llm_base,
            self.agent_llm_key,
            self.agent_system_prompt,
        ]
        for i, (lab, w) in enumerate(zip(labels, widgets)):
            ctk.CTkLabel(form, text=lab).grid(row=i, column=0, sticky="nw", padx=10, pady=6)
            w.grid(row=i, column=1, sticky="ew", padx=10, pady=6)

        self.agent_error.grid(row=8, column=0, columnspan=2, sticky="w", padx=10, pady=(4, 12))

        self._agent_save_bar = attach_save_bar_to_form_panel(
            layout,
            save_label="💾  Save agent",
            on_save=self._agent_save,
            secondary=[
                (
                    "Delete",
                    self._agent_delete,
                    {"fg_color": "#a33", "hover_color": "#7f1d1d", "width": 90},
                ),
            ],
            hint="Edit fields above, then Save (Ctrl+S)",
        )

        def _mark_dirty(*_a: Any) -> None:
            try:
                self._agent_save_bar.mark_dirty(True)
            except Exception:  # noqa: BLE001
                pass

        for w in (
            self.agent_name,
            self.agent_role,
            self.agent_goal,
            self.agent_llm_model,
            self.agent_llm_base,
            self.agent_llm_key,
        ):
            try:
                w.bind("<KeyRelease>", _mark_dirty)
            except Exception:  # noqa: BLE001
                pass
        for tb in (self.agent_backstory, self.agent_system_prompt):
            try:
                tb.bind("<KeyRelease>", _mark_dirty)
            except Exception:  # noqa: BLE001
                pass

        self._refresh_agent_list()
        if not storage.list_agents():
            ctk.CTkLabel(self.agent_list, text="No agents yet.\nClick New Agent.").pack(
                padx=8, pady=16
            )

    def _refresh_agent_list(self) -> None:
        for w in self.agent_list.winfo_children():
            w.destroy()
        for a in storage.list_agents():
            model = a.get("llm_model") or "default-LLM"
            label = f"{a.get('name') or a.get('role') or a.get('id', '')[:8]}  [{model}]"
            ctk.CTkButton(
                self.agent_list,
                text=label,
                anchor="w",
                fg_color="transparent",
                command=lambda i=a["id"]: self._agent_select(i),
            ).pack(fill="x", pady=2)

    def _agent_new(self) -> None:
        self._selected_agent_id = None
        self.agent_id_var.set("")
        self.agent_name.delete(0, "end")
        self.agent_role.delete(0, "end")
        self.agent_goal.delete(0, "end")
        self.agent_backstory.delete("1.0", "end")
        self.agent_llm_model.delete(0, "end")
        self.agent_llm_base.delete(0, "end")
        self.agent_llm_key.delete(0, "end")
        self.agent_system_prompt.delete("1.0", "end")
        self.agent_error.configure(text="")

    def _agent_select(self, agent_id: str) -> None:
        a = storage.get_agent(agent_id)
        if not a:
            return
        self._selected_agent_id = agent_id
        self.agent_id_var.set(agent_id)
        self.agent_name.delete(0, "end")
        self.agent_name.insert(0, a.get("name") or "")
        self.agent_role.delete(0, "end")
        self.agent_role.insert(0, a.get("role") or "")
        self.agent_goal.delete(0, "end")
        self.agent_goal.insert(0, a.get("goal") or "")
        self.agent_backstory.delete("1.0", "end")
        self.agent_backstory.insert("1.0", a.get("backstory") or "")
        self.agent_llm_model.delete(0, "end")
        self.agent_llm_model.insert(0, a.get("llm_model") or "")
        self.agent_llm_base.delete(0, "end")
        self.agent_llm_base.insert(0, a.get("llm_base_url") or "")
        self.agent_llm_key.delete(0, "end")
        self.agent_llm_key.insert(0, a.get("llm_api_key") or "")
        self.agent_system_prompt.delete("1.0", "end")
        self.agent_system_prompt.insert("1.0", a.get("system_prompt") or "")
        self.agent_error.configure(text="")

    def _agent_save(self) -> None:
        name = self.agent_name.get().strip()
        role = self.agent_role.get().strip()
        goal = self.agent_goal.get().strip()
        if not name:
            self.agent_error.configure(text="Name is required.")
            return
        if not role or not goal:
            self.agent_error.configure(text="Role and Goal are required.")
            return
        agent: dict[str, Any] = {
            "id": self._selected_agent_id or "",
            "name": name,
            "role": role,
            "goal": goal,
            "backstory": self.agent_backstory.get("1.0", "end").strip(),
            "llm_model": self.agent_llm_model.get().strip(),
            "llm_base_url": self.agent_llm_base.get().strip(),
            "llm_api_key": self.agent_llm_key.get().strip(),
            "system_prompt": self.agent_system_prompt.get("1.0", "end").strip(),
        }
        saved = storage.save_agent(agent)
        self._selected_agent_id = saved["id"]
        llm = storage.resolve_agent_llm(saved)
        msg = f"Saved. Effective model: {llm['model']}"
        self.agent_error.configure(text=msg)
        try:
            if getattr(self, "_agent_save_bar", None):
                self._agent_save_bar.mark_saved(f"✓ Saved · {llm['model']}")
        except Exception:  # noqa: BLE001
            pass
        self._refresh_agent_list()
        self.set_status(f"Agent saved: {name} → {llm['model']}", toast=True)

    def _agent_delete(self) -> None:
        if not self._selected_agent_id:
            self.agent_error.configure(text="Select an agent first.")
            try:
                if getattr(self, "_agent_save_bar", None):
                    self._agent_save_bar.mark_error("Select an agent first")
            except Exception:  # noqa: BLE001
                pass
            return
        if not messagebox.askyesno("Delete agent", "Delete this agent?"):
            return
        storage.delete_agent(self._selected_agent_id)
        self._agent_new()
        self._refresh_agent_list()
        try:
            if getattr(self, "_agent_save_bar", None):
                self._agent_save_bar.set_status("Agent deleted", kind="muted")
        except Exception:  # noqa: BLE001
            pass
        self.set_status("Agent deleted.")

    def _page_tasks(self) -> None:
        from app.ui.themes import style_chrome_button
        from app.ui.components.page_layout import attach_save_bar_to_form_panel, make_list_form_page

        layout = make_list_form_page(self.content, list_width=260)
        self._page_form_layout = layout
        self._page_save_handler = self._task_save

        self._page_header(
            layout.header_parent,
            "Tasks",
            "Assign work items to agents for multi-task Runs. Save bar stays visible under the form.",
            columnspan=1,
            actions=[("New Task", self._task_new)],
        )

        assert layout.list_panel is not None and layout.list_scroll is not None
        ctk.CTkButton(
            layout.list_panel,
            text="New Task",
            command=self._task_new,
            **style_chrome_button(primary=True),
        ).grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        self.task_list = layout.list_scroll

        form = layout.form_scroll
        assert form is not None
        form.grid_columnconfigure(1, weight=1)

        self.task_name = ctk.CTkEntry(form, placeholder_text="Task name")
        self.task_desc = ctk.CTkTextbox(form, height=100)
        self.task_expected = ctk.CTkEntry(form, placeholder_text="Expected output")
        agents = storage.list_agents()
        agent_labels = ["(none)"] + [
            f"{a.get('name') or a.get('role')}|{a['id']}" for a in agents
        ]
        self._agent_choices = agent_labels
        self.task_agent = ctk.CTkOptionMenu(
            form, values=[x.split("|")[0] for x in agent_labels]
        )
        self.task_error = ctk.CTkLabel(form, text="", text_color="tomato")

        rows = [
            ("Name", self.task_name),
            ("Description", self.task_desc),
            ("Expected output", self.task_expected),
            ("Assign agent", self.task_agent),
        ]
        for i, (lab, w) in enumerate(rows):
            ctk.CTkLabel(form, text=lab).grid(row=i, column=0, sticky="nw", padx=10, pady=8)
            w.grid(row=i, column=1, sticky="ew", padx=10, pady=8)

        self.task_error.grid(row=4, column=0, columnspan=2, sticky="w", padx=10, pady=(4, 12))

        self._task_save_bar = attach_save_bar_to_form_panel(
            layout,
            save_label="💾  Save task",
            on_save=self._task_save,
            secondary=[
                (
                    "Delete",
                    self._task_delete,
                    {"fg_color": "#a33", "hover_color": "#7f1d1d", "width": 90},
                ),
            ],
            hint="Edit fields above, then Save (Ctrl+S)",
        )

        self._refresh_task_list()
        if not storage.list_tasks():
            ctk.CTkLabel(self.task_list, text="No tasks yet.\nClick New Task.").pack(
                padx=8, pady=16
            )

    def _refresh_task_list(self) -> None:
        for w in self.task_list.winfo_children():
            w.destroy()
        for t in storage.list_tasks():
            label = t.get("name") or (t.get("description") or "")[:40] or t.get("id", "")[:8]
            ctk.CTkButton(
                self.task_list,
                text=label,
                anchor="w",
                fg_color="transparent",
                command=lambda i=t["id"]: self._task_select(i),
            ).pack(fill="x", pady=2)

    def _task_new(self) -> None:
        self._selected_task_id = None
        self.task_name.delete(0, "end")
        self.task_desc.delete("1.0", "end")
        self.task_expected.delete(0, "end")
        self.task_agent.set("(none)")
        self.task_error.configure(text="")

    def _task_select(self, task_id: str) -> None:
        t = next((x for x in storage.list_tasks() if x.get("id") == task_id), None)
        if not t:
            return
        self._selected_task_id = task_id
        self.task_name.delete(0, "end")
        self.task_name.insert(0, t.get("name") or "")
        self.task_desc.delete("1.0", "end")
        self.task_desc.insert("1.0", t.get("description") or "")
        self.task_expected.delete(0, "end")
        self.task_expected.insert(0, t.get("expected_output") or "")
        aid = t.get("agent_id") or ""
        label = "(none)"
        for choice in self._agent_choices:
            if "|" in choice and choice.split("|")[-1] == aid:
                label = choice.split("|")[0]
                break
        self.task_agent.set(label)
        self.task_error.configure(text="")

    def _resolve_agent_id(self) -> str:
        selected = self.task_agent.get()
        for choice in self._agent_choices:
            if choice.startswith(selected + "|") or choice.split("|")[0] == selected:
                if "|" in choice:
                    return choice.split("|")[-1]
        return ""

    def _task_save(self) -> None:
        name = self.task_name.get().strip()
        desc = self.task_desc.get("1.0", "end").strip()
        if not name and not desc:
            self.task_error.configure(text="Name or description required.")
            return
        task: dict[str, Any] = {
            "id": self._selected_task_id or "",
            "name": name or desc[:40],
            "description": desc,
            "expected_output": self.task_expected.get().strip(),
            "agent_id": self._resolve_agent_id(),
        }
        saved = storage.save_task(task)
        self._selected_task_id = saved["id"]
        self.task_error.configure(text="Saved.")
        try:
            if getattr(self, "_task_save_bar", None):
                self._task_save_bar.mark_saved("✓ Task saved")
        except Exception:  # noqa: BLE001
            pass
        self._refresh_task_list()
        self.set_status("Task saved", toast=True)

    def _task_delete(self) -> None:
        if not self._selected_task_id:
            self.task_error.configure(text="Select a task first.")
            return
        if not messagebox.askyesno("Delete task", "Delete this task?"):
            return
        storage.delete_task(self._selected_task_id)
        self._task_new()
        self._refresh_task_list()
        try:
            if getattr(self, "_task_save_bar", None):
                self._task_save_bar.set_status("Task deleted", kind="muted")
        except Exception:  # noqa: BLE001
            pass

    def _page_runs(self) -> None:
        root = ctk.CTkFrame(self.content, fg_color="transparent")
        root.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
        root.grid_columnconfigure(1, weight=1)
        root.grid_rowconfigure(1, weight=1)

        self._page_header(
            root,
            "Runs",
            "Sequential multi-task runs (mock or LLM).",
            columnspan=2,
        )

        left = ctk.CTkFrame(root)
        left.grid(row=1, column=0, sticky="nsw", padx=(0, 12))
        ctk.CTkButton(left, text="Start Run (mock)", command=lambda: self._start_run(False)).pack(
            fill="x", padx=8, pady=(8, 4)
        )
        ctk.CTkButton(
            left,
            text="Start Run (LLM)",
            command=lambda: self._start_run(True),
        ).pack(fill="x", padx=8, pady=(4, 8))
        ctk.CTkLabel(
            left,
            text="LLM needs API key\nin Settings",
            font=ctk.CTkFont(size=11),
            text_color=_HC_MUTED,
        ).pack(padx=8, pady=(0, 8))
        self.run_list = ctk.CTkScrollableFrame(left, width=240, height=420)
        self.run_list.pack(fill="both", expand=True, padx=8, pady=8)

        right = ctk.CTkFrame(root)
        right.grid(row=1, column=1, sticky="nsew")
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)
        self.run_status_label = ctk.CTkLabel(right, text="Select a run or start a new one.")
        self.run_status_label.grid(row=0, column=0, sticky="w", padx=10, pady=8)
        self.run_log = ctk.CTkTextbox(right)
        self.run_log.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

        self._refresh_run_list()
        if not storage.list_runs():
            ctk.CTkLabel(self.run_list, text="No runs yet.").pack(padx=8, pady=16)

    def _refresh_run_list(self) -> None:
        for w in self.run_list.winfo_children():
            w.destroy()
        for r in storage.list_runs():
            label = f"{r.get('status', '?')} · {str(r.get('id', ''))[:8]}"
            ctk.CTkButton(
                self.run_list,
                text=label,
                anchor="w",
                fg_color="transparent",
                command=lambda i=r["id"]: self._run_select(i),
            ).pack(fill="x", pady=2)

    def _run_select(self, run_id: str) -> None:
        r = storage.get_run(run_id)
        if not r:
            return
        self._selected_run_id = run_id
        self.run_status_label.configure(text=f"Status: {r.get('status')}  |  id={run_id}")
        self.run_log.delete("1.0", "end")
        for m in r.get("messages") or []:
            self.run_log.insert("end", f"[{m.get('role')}] {m.get('content')}\n")

    def _start_run(self, use_llm: bool = False) -> None:
        self.run_log.delete("1.0", "end")
        mode = "llm" if use_llm else "mock"
        self.run_status_label.configure(text=f"Status: running ({mode})…")

        def on_line(line: str) -> None:
            self.run_log.insert("end", line + "\n")
            self.run_log.see("end")
            self.update_idletasks()

        run = run_pipeline(use_llm=use_llm, on_line=on_line)
        self.run_status_label.configure(
            text=f"Status: {run.get('status')}  |  mode={run.get('mode', mode)}  |  id={run.get('id')}"
        )
        self._refresh_run_list()
        self.set_status(f"Run finished: {run.get('status')} ({run.get('mode', mode)})")

    def _settings_test_search(self) -> None:
        """Phase 2: one-click internet/search health check."""
        self.set_status("Testing internet / search…")

        def worker() -> None:
            try:
                from app.core.services.web.web_search import connectivity_check

                res = connectivity_check()
                sample = res.get("web_search_sample") or {}
                news = res.get("web_search_news") or {}
                ok = bool(sample.get("ok") or news.get("ok"))
                lines = []
                for name in ("wikipedia", "ddg_html", "ddg_api", "brave", "google_news"):
                    c = res.get(name) or {}
                    if not isinstance(c, dict):
                        continue
                    if c.get("ok"):
                        flag = " · CAPTCHA" if c.get("challenge") else ""
                        lines.append(f"• {name}: ok ({c.get('bytes')} bytes){flag}")
                    else:
                        lines.append(f"• {name}: FAIL {c.get('error')}")
                lines.append(
                    f"• sample search: {sample.get('count')} via {sample.get('backends')}"
                )
                lines.append(
                    f"• news search: {news.get('count')} via {news.get('backends')}"
                )
                if sample.get("warnings") or news.get("warnings"):
                    w = list(sample.get("warnings") or []) + list(news.get("warnings") or [])
                    lines.append("warnings: " + "; ".join(w)[:300])
                msg = ("Search OK\n" if ok else "Search weak/failed\n") + "\n".join(lines)
            except Exception as e:  # noqa: BLE001
                ok = False
                msg = f"Connectivity test error: {e}"

            def ui() -> None:
                if ok:
                    messagebox.showinfo("Internet / search", msg, parent=self)
                    self.set_status(msg, toast=True)
                else:
                    messagebox.showerror("Internet / search", msg, parent=self)
                    self.set_status(msg, toast=True)

            self.after(0, ui)

        threading.Thread(target=worker, daemon=True).start()

    def _page_settings(self) -> None:
        from app.services import providers as prov
        from app.ui.themes import style_chrome_button
        from app.core.services.web.web_search import SEARCH_PROVIDERS, search_status

        outer = ctk.CTkFrame(self.content, fg_color="transparent")
        outer.grid(row=0, column=0, sticky="nsew", padx=16, pady=12)
        outer.grid_columnconfigure(0, weight=1)
        outer.grid_rowconfigure(2, weight=1)

        self._page_header(
            outer,
            "Settings",
            "Scroll for all options. Use the green Save buttons — they stay easy to find.",
            actions=[
                ("Setup wizard", self._show_onboarding_wizard),
                ("Test search", self._settings_test_search),
            ],
        )

        # Sticky save bar (always visible above the scroll area)
        save_bar = ctk.CTkFrame(outer, fg_color=("gray90", "gray20"), corner_radius=8)
        save_bar.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        save_status = ctk.CTkLabel(
            save_bar,
            text="Change options below, then click Save all settings.",
            text_color=_HC_MUTED,
        )
        save_status.pack(side="left", padx=12, pady=10)

        # Scrollable body — fixes “no save button” when content was cut off
        frame = ctk.CTkScrollableFrame(outer, fg_color="transparent")
        frame.grid(row=2, column=0, sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)

        # Section: Version & updates (Task #10)
        from app.core.services.misc.version_check import (
            install_summary,
            should_auto_check,
            set_auto_check,
            set_update_check_url,
        )

        ctk.CTkLabel(
            frame,
            text="Version & updates",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=_HC_LABEL,
        ).grid(row=0, column=0, sticky="w", pady=(4, 2))
        upd_box = ctk.CTkFrame(frame)
        upd_box.grid(row=1, column=0, sticky="ew", pady=4)
        try:
            _inst = install_summary()
        except Exception:  # noqa: BLE001
            _inst = {"version": __version__, "mode_label": "?", "app_root": ""}
        ctk.CTkLabel(
            upd_box,
            text=(
                f"Current: v{_inst.get('version')} · {_inst.get('mode_label')}\n"
                f"Always shown in the window title and bottom status bar."
            ),
            text_color=_HC_MUTED,
            justify="left",
            anchor="w",
        ).pack(anchor="w", padx=10, pady=(8, 4))
        auto_upd_var = ctk.BooleanVar(value=should_auto_check())
        ctk.CTkSwitch(
            upd_box,
            text="Check for updates when app starts (quiet toast if newer)",
            variable=auto_upd_var,
            command=lambda: set_auto_check(bool(auto_upd_var.get())),
        ).pack(anchor="w", padx=10, pady=4)
        url_row = ctk.CTkFrame(upd_box, fg_color="transparent")
        url_row.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(url_row, text="Optional update JSON URL", text_color=_HC_LABEL).pack(
            side="left", padx=(0, 6)
        )
        upd_url_var = ctk.StringVar(value=str(self.cfg.get("update_check_url") or ""))
        ctk.CTkEntry(url_row, textvariable=upd_url_var, width=360).pack(side="left", padx=4)
        ctk.CTkButton(
            url_row,
            text="Save URL",
            width=90,
            command=lambda: (
                set_update_check_url(upd_url_var.get()),
                self.cfg.update({"update_check_url": upd_url_var.get().strip()}),
                self.set_status("Update URL saved", toast=True),
            ),
            **style_chrome_button(),
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            upd_box,
            text="Check for updates now",
            width=180,
            command=self._run_update_check_dialog,
            **style_chrome_button(primary=True),
        ).pack(anchor="w", padx=10, pady=(4, 10))

        # Task #13: global hotkeys
        try:
            from app.services import global_hotkeys as ghk

            hk_box = ctk.CTkFrame(upd_box, fg_color="transparent")
            hk_box.pack(fill="x", padx=10, pady=(0, 10))
            hk_var = ctk.BooleanVar(value=ghk.hotkeys_enabled())

            def _toggle_hk() -> None:
                on = bool(hk_var.get())
                ghk.set_hotkeys_enabled(on)
                if on:
                    ghk.set_listener(
                        lambda ev: self.after(
                            0,
                            lambda: self._ask_about_clipboard(
                                str(ev.get("text") or ""),
                                source=str(ev.get("label") or ""),
                            )
                            if ev.get("type") == "ask_clipboard"
                            else None,
                        )
                    )
                    ghk.start()
                    self.set_status("Global hotkeys on (Ctrl+Shift+G)", toast=True)
                else:
                    ghk.stop()
                    self.set_status("Global hotkeys off", toast=True)

            ctk.CTkSwitch(
                hk_box,
                text="Global hotkey: Ctrl+Shift+G ask about clipboard (Windows)",
                variable=hk_var,
                command=_toggle_hk,
            ).pack(anchor="w")
            ctk.CTkLabel(
                hk_box,
                text="Works even when another app is focused. Copy text → Ctrl+Shift+G → Chat fills.",
                text_color=_HC_MUTED,
                font=ctk.CTkFont(size=11),
            ).pack(anchor="w", pady=(2, 0))
        except Exception:  # noqa: BLE001
            pass

        # PENDING #19: system tray
        try:
            from app.services import system_tray as tray_svc

            tray_box = ctk.CTkFrame(upd_box, fg_color="transparent")
            tray_box.pack(fill="x", padx=10, pady=(0, 10))
            ctk.CTkLabel(
                tray_box,
                text="System tray (run in background)",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=_HC_LABEL,
            ).pack(anchor="w", pady=(4, 2))
            if not tray_svc.is_supported():
                ctk.CTkLabel(
                    tray_box,
                    text="Tray unavailable — install pystray (in requirements.txt) and restart via Launch.bat.",
                    text_color=_HC_MUTED,
                    font=ctk.CTkFont(size=11),
                ).pack(anchor="w")
            else:
                tray_on_var = ctk.BooleanVar(value=tray_svc.tray_enabled())
                close_tray_var = ctk.BooleanVar(value=tray_svc.close_to_tray())
                min_tray_var = ctk.BooleanVar(value=tray_svc.minimize_to_tray())
                start_min_var = ctk.BooleanVar(value=tray_svc.start_minimized())

                def _toggle_tray() -> None:
                    on = bool(tray_on_var.get())
                    tray_svc.set_tray_enabled(on)
                    self.cfg["system_tray_enabled"] = on
                    if on:
                        self._setup_system_tray()
                        self.set_status("System tray enabled", toast=True)
                    else:
                        try:
                            tray_svc.stop()
                        except Exception:  # noqa: BLE001
                            pass
                        self.set_status("System tray disabled — close will quit", toast=True)

                def _toggle_close_tray() -> None:
                    on = bool(close_tray_var.get())
                    tray_svc.set_close_to_tray(on)
                    self.cfg["close_to_tray"] = on

                def _toggle_min_tray() -> None:
                    on = bool(min_tray_var.get())
                    tray_svc.set_minimize_to_tray(on)
                    self.cfg["minimize_to_tray"] = on

                def _toggle_start_min() -> None:
                    on = bool(start_min_var.get())
                    tray_svc.set_start_minimized(on)
                    self.cfg["start_minimized"] = on
                    self.set_status(
                        "Start minimized on" if on else "Start minimized off",
                        toast=True,
                    )

                ctk.CTkSwitch(
                    tray_box,
                    text="Enable system tray icon",
                    variable=tray_on_var,
                    command=_toggle_tray,
                ).pack(anchor="w", pady=2)
                ctk.CTkSwitch(
                    tray_box,
                    text="Close (✕) hides to tray instead of quitting",
                    variable=close_tray_var,
                    command=_toggle_close_tray,
                ).pack(anchor="w", pady=2)
                ctk.CTkSwitch(
                    tray_box,
                    text="Minimize button hides to tray",
                    variable=min_tray_var,
                    command=_toggle_min_tray,
                ).pack(anchor="w", pady=2)
                ctk.CTkSwitch(
                    tray_box,
                    text="Start minimized (open in tray)",
                    variable=start_min_var,
                    command=_toggle_start_min,
                ).pack(anchor="w", pady=2)
                ctk.CTkLabel(
                    tray_box,
                    text="Tray menu: Show · Hide · Quit. Agents keep running while hidden.",
                    text_color=_HC_MUTED,
                    font=ctk.CTkFont(size=11),
                ).pack(anchor="w", pady=(2, 0))
        except Exception:  # noqa: BLE001
            pass

        # Section: Appearance
        ctk.CTkLabel(
            frame,
            text="Appearance",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=_HC_LABEL,
        ).grid(row=2, column=0, sticky="w", pady=(8, 2))
        top = ctk.CTkFrame(frame)
        top.grid(row=3, column=0, sticky="ew", pady=4)
        from app.ui.themes import theme_names

        ctk.CTkLabel(top, text="UI colour theme", text_color=_HC_LABEL).pack(side="left", padx=8)
        self.ui_theme_var = ctk.StringVar(value=self.cfg.get("ui_theme") or "Dark Blue")
        ctk.CTkOptionMenu(
            top,
            variable=self.ui_theme_var,
            values=theme_names(),
            command=self._on_ui_theme_change,
            width=160,
        ).pack(side="left", padx=4)
        ctk.CTkLabel(
            top,
            text="Pick a colour scheme (Dark Blue, Ocean, Forest, Daylight…)",
            text_color=_HC_MUTED,
        ).pack(side="left", padx=8)
        ctk.CTkLabel(top, text=f"Data: {data_dir()}", text_color=_HC_MUTED, wraplength=320).pack(
            side="left", padx=12
        )

        ctk.CTkLabel(
            frame,
            text="Chat & safety",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=_HC_LABEL,
        ).grid(row=4, column=0, sticky="w", pady=(8, 2))
        opts = ctk.CTkFrame(frame)
        opts.grid(row=5, column=0, sticky="ew", pady=6)
        cfg = self.cfg
        stream_var = ctk.BooleanVar(master=opts, value=bool(cfg.get("stream_replies", True)))
        auto_proj_var = ctk.BooleanVar(master=opts, value=bool(cfg.get("auto_save_results_to_project")))
        tool_ap_var = ctk.BooleanVar(master=opts, value=bool(cfg.get("tool_approval_required")))
        native_tools_var = ctk.BooleanVar(
            master=opts, value=bool(cfg.get("prefer_native_openai_tools", True))
        )
        hybrid_rag_var = ctk.BooleanVar(
            master=opts, value=bool(cfg.get("hybrid_rag_enabled", True))
        )
        dens_cur = str(cfg.get("chat_density") or "compact").lower()
        if dens_cur not in ("compact", "comfortable"):
            dens_cur = "compact"
        dens_var = ctk.StringVar(master=opts, value=dens_cur)
        try:
            scale_cur = float(cfg.get("ui_scale") or 1.0)
        except Exception:  # noqa: BLE001
            scale_cur = 1.0
        scale_var = ctk.StringVar(master=opts, value=f"{scale_cur:.2f}")
        si_review_var = ctk.BooleanVar(master=opts, value=bool(cfg.get("self_improve_require_review", True)))
        from app.core.services.tools.capabilities import IMAGE_PRESETS, format_capability_matrix

        preset_labels = [p["label"] for p in IMAGE_PRESETS]
        preset_id_by_label = {p["label"]: p["id"] for p in IMAGE_PRESETS}
        cur_preset = str(cfg.get("image_preset") or "openai-dalle3")
        cur_label = next((p["label"] for p in IMAGE_PRESETS if p["id"] == cur_preset), preset_labels[0])
        img_preset_var = ctk.StringVar(master=opts, value=cur_label)

        ctk.CTkSwitch(opts, text="Stream replies", variable=stream_var).pack(
            side="left", padx=8, pady=6
        )
        ctk.CTkSwitch(
            opts, text="Auto-save results → project", variable=auto_proj_var
        ).pack(side="left", padx=8, pady=6)
        ctk.CTkSwitch(
            opts, text="Require tool approval", variable=tool_ap_var
        ).pack(side="left", padx=8, pady=6)
        ctk.CTkSwitch(
            opts,
            text="Prefer native OpenAI tool calls",
            variable=native_tools_var,
        ).pack(side="left", padx=8, pady=6)
        ctk.CTkSwitch(
            opts,
            text="Hybrid RAG (BM25 + embeddings)",
            variable=hybrid_rag_var,
        ).pack(side="left", padx=8, pady=6)
        ctk.CTkLabel(opts, text="Chat density").pack(side="left", padx=(12, 4))
        ctk.CTkOptionMenu(
            opts,
            variable=dens_var,
            values=["compact", "comfortable"],
            width=120,
        ).pack(side="left", padx=4)
        ctk.CTkLabel(opts, text="UI scale").pack(side="left", padx=(12, 4))
        ctk.CTkOptionMenu(
            opts,
            variable=scale_var,
            values=["0.90", "1.00", "1.10", "1.20", "1.25"],
            width=80,
        ).pack(side="left", padx=4)
        ctk.CTkButton(opts, text="Setup wizard", width=100, command=self._show_onboarding_wizard).pack(
            side="left", padx=8
        )
        ctk.CTkSwitch(
            opts,
            text="Self-improve → Patches review",
            variable=si_review_var,
        ).pack(side="left", padx=8, pady=6)


        # PENDING #16: Tool call audit log (Settings)
        try:
            from app.core.services.data import audit_log as _audit_ui

            audit_strip = ctk.CTkFrame(opts, fg_color="transparent")
            audit_strip.pack(fill="x", padx=8, pady=(8, 6))
            ctk.CTkLabel(
                audit_strip,
                text="Tool call audit log",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=_HC_LABEL,
            ).pack(anchor="w")
            _asum = _audit_ui.status_summary()
            audit_count_lbl = ctk.CTkLabel(
                audit_strip,
                text=(
                    f"Persisted tool calls: {_asum.get('count', 0)} · "
                    f"data/tool_audit.json (secrets redacted)"
                ),
                text_color=_HC_MUTED,
                font=ctk.CTkFont(size=11),
            )
            audit_count_lbl.pack(anchor="w", pady=(0, 4))

            def _refresh_audit_count() -> None:
                try:
                    s = _audit_ui.status_summary()
                    audit_count_lbl.configure(
                        text=(
                            f"Persisted tool calls: {s.get('count', 0)} · "
                            f"data/tool_audit.json (secrets redacted)"
                        )
                    )
                except Exception:  # noqa: BLE001
                    pass

            def _export_audit_json() -> None:
                try:
                    out = self._export_tool_audit(fmt="json")
                    if out:
                        _refresh_audit_count()
                except Exception as e:  # noqa: BLE001
                    messagebox.showerror("Audit export", str(e), parent=self)

            def _export_audit_csv() -> None:
                try:
                    out = self._export_tool_audit(fmt="csv")
                    if out:
                        _refresh_audit_count()
                except Exception as e:  # noqa: BLE001
                    messagebox.showerror("Audit export", str(e), parent=self)

            def _clear_audit() -> None:
                if not messagebox.askyesno(
                    "Clear audit log",
                    "Delete all persisted tool-call audit entries?",
                    parent=self,
                ):
                    return
                try:
                    n = _audit_ui.clear()
                    _refresh_audit_count()
                    self.set_status(f"Cleared {n} audit entries", toast=True)
                except Exception as e:  # noqa: BLE001
                    messagebox.showerror("Clear audit", str(e), parent=self)

            def _rotate_audit() -> None:
                try:
                    removed = _audit_ui.rotate(keep=1000)
                    _refresh_audit_count()
                    self.set_status(f"Rotated audit log (removed {removed})", toast=True)
                except Exception as e:  # noqa: BLE001
                    messagebox.showerror("Rotate audit", str(e), parent=self)

            brow = ctk.CTkFrame(audit_strip, fg_color="transparent")
            brow.pack(fill="x", pady=2)
            ctk.CTkButton(
                brow, text="Export JSON", width=110, command=_export_audit_json, **style_chrome_button()
            ).pack(side="left", padx=4)
            ctk.CTkButton(
                brow, text="Export CSV", width=110, command=_export_audit_csv, **style_chrome_button()
            ).pack(side="left", padx=4)
            ctk.CTkButton(brow, text="Clear", width=80, command=_clear_audit).pack(side="left", padx=4)
            ctk.CTkButton(
                brow, text="Rotate (keep 1000)", width=140, command=_rotate_audit
            ).pack(side="left", padx=4)
        except Exception:  # noqa: BLE001
            pass

        # PENDING #18: Voice in/out (soft-degrade if deps missing)
        voice_mic_var = None
        voice_tts_var = None
        voice_auto_var = None
        voice_mode_var = None
        voice_lang_var = None
        try:
            from app.core.services.ai import voice_settings as _vs
            from app.core.services.ai.stt_service import stt_capability as _stt_cap
            from app.core.services.ai.tts_service import tts_capability as _tts_cap
            
            _vs.ensure_defaults(cfg)
            ctk.CTkLabel(
                frame,
                text="Voice (mic in / read-aloud out)",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color=_HC_LABEL,
            ).grid(row=6, column=0, sticky="w", pady=(8, 2))
            voice_box = ctk.CTkFrame(frame)
            voice_box.grid(row=7, column=0, sticky="ew", pady=6)
            voice_mic_var = ctk.BooleanVar(master=voice_box, value=bool(cfg.get("voice_mic_enabled", True)))
            voice_tts_var = ctk.BooleanVar(master=voice_box, value=bool(cfg.get("voice_tts_enabled", True)))
            voice_auto_var = ctk.BooleanVar(master=voice_box, value=bool(cfg.get("voice_auto_read_aloud", False)))
            _mode_cur = str(cfg.get("voice_mic_mode") or "push_to_talk")
            if _mode_cur not in ("push_to_talk", "toggle"):
                _mode_cur = "push_to_talk"
            voice_mode_var = ctk.StringVar(master=voice_box, value=_mode_cur)
            voice_lang_var = ctk.StringVar(master=voice_box, value=str(cfg.get("voice_language") or "en-US"))
            row_v1 = ctk.CTkFrame(voice_box, fg_color="transparent")
            row_v1.pack(fill="x", padx=8, pady=4)
            ctk.CTkSwitch(row_v1, text="Mic input in chat", variable=voice_mic_var).pack(side="left", padx=4)
            ctk.CTkSwitch(row_v1, text="TTS / Speak button", variable=voice_tts_var).pack(side="left", padx=8)
            ctk.CTkSwitch(
                row_v1, text="Auto read-aloud assistant replies", variable=voice_auto_var
            ).pack(side="left", padx=8)
            row_v2 = ctk.CTkFrame(voice_box, fg_color="transparent")
            row_v2.pack(fill="x", padx=8, pady=4)
            ctk.CTkLabel(row_v2, text="Mic mode", text_color=_HC_LABEL).pack(side="left", padx=(4, 6))
            ctk.CTkOptionMenu(
                row_v2,
                variable=voice_mode_var,
                values=["push_to_talk", "toggle"],
                width=140,
            ).pack(side="left", padx=4)
            ctk.CTkLabel(
                row_v2,
                text="push_to_talk = click 🎤 once · toggle = continuous listen",
                text_color=_HC_MUTED,
                font=ctk.CTkFont(size=11),
            ).pack(side="left", padx=8)
            ctk.CTkLabel(row_v2, text="Language", text_color=_HC_LABEL).pack(side="left", padx=(12, 4))
            ctk.CTkEntry(row_v2, textvariable=voice_lang_var, width=90).pack(side="left", padx=4)
            _stt = _stt_cap()
            _tts = _tts_cap()
            _stt_line = (
                f"STT: {'ready' if _stt.get('available') else 'unavailable'} — {_stt.get('detail') or ''}"
            )
            _tts_line = (
                f"TTS: {'ready' if _tts.get('available') else 'unavailable'} — {_tts.get('detail') or ''}"
            )
            ctk.CTkLabel(
                voice_box,
                text=_stt_line[:160] + "\n" + _tts_line[:160],
                text_color=_HC_MUTED,
                justify="left",
                anchor="w",
                font=ctk.CTkFont(size=11),
            ).pack(anchor="w", padx=12, pady=(2, 8))
            
        except Exception as _voice_ui_err:  # noqa: BLE001
            try:
                ctk.CTkLabel(
                    frame,
                    text="Voice (mic in / read-aloud out)",
                    font=ctk.CTkFont(size=14, weight="bold"),
                    text_color=_HC_LABEL,
                ).grid(row=6, column=0, sticky="w", pady=(8, 2))
                ctk.CTkLabel(
                    frame,
                    text=f"Voice settings unavailable: {_voice_ui_err}",
                    text_color=_HC_MUTED,
                    wraplength=720,
                    justify="left",
                ).grid(row=7, column=0, sticky="w", pady=4, padx=8)
            except Exception:  # noqa: BLE001
                pass

        # Image presets + capability matrix
        ctk.CTkLabel(
            frame,
            text="Image generation",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=_HC_LABEL,
        ).grid(row=8, column=0, sticky="w", pady=(8, 2))
        img_row = ctk.CTkFrame(frame)
        img_row.grid(row=9, column=0, sticky="ew", pady=6)
        ctk.CTkLabel(img_row, text="Image preset", text_color=_HC_LABEL).pack(side="left", padx=8)
        ctk.CTkOptionMenu(
            img_row,
            variable=img_preset_var,
            values=preset_labels,
            width=220,
        ).pack(side="left", padx=4)

        ctk.CTkLabel(img_row, text="Image model:", text_color=_HC_LABEL).pack(side="left", padx=(12, 4))
        img_model_e = ctk.CTkEntry(img_row, width=140, placeholder_text="dall-e-3")
        img_model_e.insert(0, str(cfg.get("image_model") or "dall-e-3"))
        img_model_e.pack(side="left", padx=4)

        def test_image_gen() -> None:
            save_all_settings()
            prompt = simpledialog.askstring("Test image gen", "Prompt:", initialvalue="a red cube on white", parent=self)
            if not prompt:
                return
            try:
                from app.core.services.ai.image_gen import generate_image

                res = generate_image(prompt, size="512x512", chat_id="settings_test")
                messagebox.showinfo(
                    "Image gen OK",
                    f"Model: {res.get('model')}\nFiles:\n" + "\n".join(res.get("paths") or []),
                    parent=self,
                )
            except Exception as e:  # noqa: BLE001
                messagebox.showerror("Image gen failed", str(e), parent=self)

        ctk.CTkButton(img_row, text="Test image gen", width=120, command=test_image_gen).pack(side="left", padx=8)
        ctk.CTkButton(img_row, text="Usage & budgets", width=120, command=lambda: self.show_page("Usage")).pack(
            side="left", padx=4
        )
        ctk.CTkButton(img_row, text="Shortcuts (F1)", width=110, command=self._show_shortcuts_help).pack(
            side="left", padx=4
        )

        # ── Web search (ChatGPT/Grok-style research) ──
        ctk.CTkLabel(
            frame,
            text="Web search (internet research)",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=_HC_LABEL,
        ).grid(row=10, column=0, sticky="w", pady=(10, 2))
        search_box = ctk.CTkFrame(frame)
        search_box.grid(row=11, column=0, sticky="ew", pady=4)
        search_box.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            search_box,
            text="Like ChatGPT/Grok: paste a free Search API key, then click Save all settings (top bar).",
            text_color=_HC_MUTED,
            wraplength=720,
            justify="left",
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=8, pady=(6, 4))

        prov_ids = [p[0] for p in SEARCH_PROVIDERS]
        prov_labels = [p[1] for p in SEARCH_PROVIDERS]
        label_by_id = {a: b for a, b in SEARCH_PROVIDERS}
        id_by_label = {b: a for a, b in SEARCH_PROVIDERS}
        cur_sp = str(cfg.get("search_provider") or "auto")
        if cur_sp not in prov_ids:
            cur_sp = "auto"
        search_prov_var = ctk.StringVar(master=search_box, value=label_by_id.get(cur_sp, prov_labels[0]))
        search_key_e = ctk.CTkEntry(
            search_box, width=320, placeholder_text="Search API key (Tavily / Brave / SerpAPI / Bing)", show="*"
        )
        if cfg.get("search_api_key"):
            search_key_e.insert(0, str(cfg.get("search_api_key")))
        auto_fetch_var = ctk.BooleanVar(master=search_box, value=bool(cfg.get("search_auto_fetch", True)))
        try:
            fetch_n = int(cfg.get("search_fetch_count") or 5)
        except Exception:  # noqa: BLE001
            fetch_n = 5
        fetch_n = max(3, min(8, fetch_n))  # high volume default
        fetch_count_var = ctk.StringVar(master=search_box, value=str(fetch_n))
        # Adult search permanently ON — vars kept only for legacy reads; UI is locked
        adult_mode_var = ctk.BooleanVar(master=search_box, value=True)
        safe_search_var = ctk.StringVar(master=search_box, value="off")

        ctk.CTkLabel(search_box, text="Engine", text_color=_HC_LABEL).grid(
            row=1, column=0, sticky="w", padx=8, pady=4
        )
        ctk.CTkOptionMenu(
            search_box, variable=search_prov_var, values=prov_labels, width=280
        ).grid(row=1, column=1, sticky="w", padx=4, pady=4)
        ctk.CTkLabel(search_box, text="API key", text_color=_HC_LABEL).grid(
            row=2, column=0, sticky="w", padx=8, pady=4
        )
        search_key_e.grid(row=2, column=1, sticky="ew", padx=4, pady=4)

        def save_all_settings() -> None:
            """One Save for chat/safety/image + web search."""
            self.cfg["stream_replies"] = bool(stream_var.get())
            self.cfg["auto_save_results_to_project"] = bool(auto_proj_var.get())
            self.cfg["tool_approval_required"] = bool(tool_ap_var.get())
            self.cfg["prefer_native_openai_tools"] = bool(native_tools_var.get())
            try:
                self.cfg["hybrid_rag_enabled"] = bool(hybrid_rag_var.get())
            except Exception:  # noqa: BLE001
                self.cfg["hybrid_rag_enabled"] = True
            self.cfg["self_improve_require_review"] = bool(si_review_var.get())
            # Voice (#18)
            try:
                if voice_mic_var is not None:
                    self.cfg["voice_mic_enabled"] = bool(voice_mic_var.get())
                if voice_tts_var is not None:
                    self.cfg["voice_tts_enabled"] = bool(voice_tts_var.get())
                if voice_auto_var is not None:
                    self.cfg["voice_auto_read_aloud"] = bool(voice_auto_var.get())
                if voice_mode_var is not None:
                    _vm = str(voice_mode_var.get() or "push_to_talk")
                    self.cfg["voice_mic_mode"] = _vm if _vm in ("push_to_talk", "toggle") else "push_to_talk"
                if voice_lang_var is not None:
                    self.cfg["voice_language"] = (voice_lang_var.get() or "en-US").strip() or "en-US"
            except Exception:  # noqa: BLE001
                pass
            self.cfg["chat_density"] = dens_var.get() if dens_var.get() in ("compact", "comfortable") else "compact"
            self.cfg["image_preset"] = preset_id_by_label.get(img_preset_var.get(), "custom")
            try:
                sc = float(scale_var.get())
            except Exception:  # noqa: BLE001
                sc = 1.0
            sc = max(0.9, min(1.25, sc))
            self.cfg["ui_scale"] = sc
            pid = self.cfg["image_preset"]
            preset_model = next((p.get("model") for p in IMAGE_PRESETS if p["id"] == pid), "")
            typed = img_model_e.get().strip()
            if pid != "custom" and preset_model:
                self.cfg["image_model"] = preset_model
                try:
                    img_model_e.delete(0, "end")
                    img_model_e.insert(0, preset_model)
                except Exception:  # noqa: BLE001
                    pass
            else:
                self.cfg["image_model"] = typed or "dall-e-3"
            # Web search
            self.cfg["search_provider"] = id_by_label.get(search_prov_var.get(), "auto")
            self.cfg["search_api_key"] = search_key_e.get().strip()
            self.cfg["search_auto_fetch"] = bool(auto_fetch_var.get())
            try:
                n = int(fetch_count_var.get())
            except Exception:  # noqa: BLE001
                n = 3
            self.cfg["search_fetch_count"] = max(0, min(8, n))
            self.cfg["search_default_max"] = 25
            self.cfg["search_min_domains"] = 18
            self.cfg["search_auto_fetch"] = True
            # Adult search ALWAYS ON — cannot be disabled from Settings
            self.cfg["search_safe_search"] = "off"
            self.cfg["search_adult_mode"] = True
            try:
                adult_mode_var.set(True)
                safe_search_var.set("off")
            except Exception:  # noqa: BLE001
                pass
            # Browser session
            try:
                self.cfg["browser_headed"] = bool(browser_headed_var.get())
                self.cfg["browser_persistent"] = bool(browser_persist_var.get())
            except Exception:  # noqa: BLE001
                pass
            storage.save_config(self.cfg)
            self._chat_density = self.cfg["chat_density"]
            try:
                self._voice_refresh_composer_buttons()
            except Exception:  # noqa: BLE001
                pass
            try:
                ctk.set_widget_scaling(sc)
                ctk.set_window_scaling(sc)
            except Exception:  # noqa: BLE001
                pass
            st = search_status()
            key_note = "search API key set" if st.get("has_api_key") else "free search backends"
            headed = "headed" if self.cfg.get("browser_headed") else "headless"
            msg = f"Settings saved · {st.get('provider')} · {key_note} · browser {headed}"
            try:
                save_status.configure(text="✓ " + msg, text_color=_HC_LABEL)
            except Exception:  # noqa: BLE001
                pass
            self.set_status(msg, toast=True)

        # Browser vars must exist before first Save (defined here, used in save_all_settings)
        browser_headed_var = ctk.BooleanVar(master=frame, value=bool(cfg.get("browser_headed", False)))
        browser_persist_var = ctk.BooleanVar(master=frame, value=bool(cfg.get("browser_persistent", True)))

        # Wire sticky bar + entry Enter
        ctk.CTkButton(
            save_bar,
            text="💾  Save all settings",
            width=180,
            height=34,
            command=save_all_settings,
            **style_chrome_button(primary=True),
        ).pack(side="right", padx=12, pady=8)
        ctk.CTkButton(
            save_bar,
            text="Test search",
            width=110,
            height=34,
            command=self._settings_test_search,
            **style_chrome_button(),
        ).pack(side="right", padx=4, pady=8)
        try:
            search_key_e.bind("<Return>", lambda _e: save_all_settings())
        except Exception:  # noqa: BLE001
            pass

        ctk.CTkSwitch(
            search_box,
            text="Auto-open top pages (read full text)",
            variable=auto_fetch_var,
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=8, pady=4)
        ctk.CTkLabel(search_box, text="Pages to open", text_color=_HC_LABEL).grid(
            row=3, column=2, sticky="e", padx=4
        )
        ctk.CTkOptionMenu(
            search_box,
            variable=fetch_count_var,
            values=["3", "4", "5", "6", "7", "8"],
            width=60,
        ).grid(row=3, column=3, sticky="w", padx=4)
        ctk.CTkLabel(
            search_box,
            text="🔞 Adult search (18+): ALWAYS ON  ·  Safe Search: permanently OFF  ·  locked",
            text_color=_HC_LABEL,
        ).grid(row=4, column=0, columnspan=4, sticky="w", padx=8, pady=4)
        ctk.CTkLabel(
            search_box,
            text=(
                "Open discovery (any domain) · Telegram / Instagram / Discord / X · "
                "up to 40 hits · LLM gets full titles/URLs/invites · CSAM hard-blocked"
            ),
            text_color=_HC_MUTED,
        ).grid(row=5, column=0, columnspan=4, sticky="w", padx=8, pady=(0, 6))
        btn_row = ctk.CTkFrame(search_box, fg_color="transparent")
        btn_row.grid(row=6, column=0, columnspan=4, sticky="ew", padx=8, pady=(8, 10))
        ctk.CTkButton(
            btn_row,
            text="💾  Save all settings",
            width=180,
            height=36,
            command=save_all_settings,
            **style_chrome_button(primary=True),
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            btn_row,
            text="Test search",
            width=110,
            height=36,
            command=self._settings_test_search,
            **style_chrome_button(),
        ).pack(side="left", padx=4)
        ctk.CTkLabel(
            btn_row,
            text="Free keys: tavily.com · brave.com/search/api · serpapi.com",
            text_color=_HC_MUTED,
        ).pack(side="left", padx=10)

        # Browser (full internet session)
        ctk.CTkLabel(
            frame,
            text="Browser (full internet / live Chromium)",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=_HC_LABEL,
        ).grid(row=9, column=0, sticky="w", pady=(12, 2))
        br_box = ctk.CTkFrame(frame)
        br_box.grid(row=10, column=0, sticky="ew", pady=4)
        ctk.CTkLabel(
            br_box,
            text="Persistent session keeps cookies so multi-step browsing works. "
            "Headed = visible Chrome window (for CAPTCHAs / logins).",
            text_color=_HC_MUTED,
            wraplength=720,
            justify="left",
        ).pack(anchor="w", padx=8, pady=(6, 4))
        ctk.CTkSwitch(br_box, text="Browser headed (show window)", variable=browser_headed_var).pack(
            side="left", padx=8, pady=8
        )
        ctk.CTkSwitch(br_box, text="Persistent profile (cookies)", variable=browser_persist_var).pack(
            side="left", padx=8, pady=8
        )

        # Agent harness (Grok-style tools — GUI kept)
        ctk.CTkLabel(
            frame,
            text="Agent harness (Grok-style tools)",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=_HC_LABEL,
        ).grid(row=11, column=0, sticky="w", pady=(12, 2))
        ah_box = ctk.CTkFrame(frame)
        ah_box.grid(row=12, column=0, sticky="ew", pady=4)
        harness_on_var = ctk.BooleanVar(master=ah_box, value=bool(cfg.get("agent_harness_enabled", True)))
        sandbox_on_var = ctk.BooleanVar(master=ah_box, value=bool(cfg.get("agent_sandbox_enabled", False)))
        hooks_on_var = ctk.BooleanVar(master=ah_box, value=bool(cfg.get("agent_hooks_enabled", True)))
        perm_mode = str(cfg.get("agent_permission_mode") or "auto")
        if perm_mode in ("always-approve", "yolo", "bypass"):
            perm_mode = "always_approve"
        if perm_mode not in ("auto", "ask", "always_approve", "plan"):
            perm_mode = "auto"
        perm_var = ctk.StringVar(master=ah_box, value=perm_mode)
        sand_prof = str(cfg.get("agent_sandbox_profile") or "workspace")
        if sand_prof not in ("workspace", "strict", "read_only", "off"):
            sand_prof = "workspace"
        sand_prof_var = ctk.StringVar(master=ah_box, value=sand_prof)
        ctk.CTkLabel(
            ah_box,
            text=(
                "File read/write/patch · grep · list_dir · subagents · git · bg shell · "
                "plan.md · AGENTS.md · hooks · todos. Headless: python studio_agent.py -p \"…\""
            ),
            text_color=_HC_MUTED,
            wraplength=720,
            justify="left",
        ).pack(anchor="w", padx=8, pady=(6, 4))
        ah_row = ctk.CTkFrame(ah_box, fg_color="transparent")
        ah_row.pack(fill="x", padx=8, pady=4)
        ctk.CTkSwitch(ah_row, text="Harness enabled", variable=harness_on_var).pack(side="left", padx=6)
        ctk.CTkSwitch(ah_row, text="Sandbox", variable=sandbox_on_var).pack(side="left", padx=6)
        ctk.CTkSwitch(ah_row, text="Hooks", variable=hooks_on_var).pack(side="left", padx=6)
        ah_row2 = ctk.CTkFrame(ah_box, fg_color="transparent")
        ah_row2.pack(fill="x", padx=8, pady=(0, 8))
        ctk.CTkLabel(ah_row2, text="Permission mode", text_color=_HC_LABEL).pack(side="left", padx=(6, 4))
        ctk.CTkOptionMenu(
            ah_row2,
            variable=perm_var,
            values=["auto", "ask", "always_approve", "plan"],
            width=140,
        ).pack(side="left", padx=4)
        ctk.CTkLabel(ah_row2, text="Sandbox profile", text_color=_HC_LABEL).pack(side="left", padx=(12, 4))
        ctk.CTkOptionMenu(
            ah_row2,
            variable=sand_prof_var,
            values=["workspace", "strict", "read_only", "off"],
            width=120,
        ).pack(side="left", padx=4)
        # Task #4: simple risk tiers (maps to permission + sandbox + tool approval)
        try:
            from app.services.agent_harness.permissions import get_risk_tier, set_risk_tier, risk_tier_hint

            _rt0 = get_risk_tier()
        except Exception:  # noqa: BLE001
            _rt0 = "ask"

            def risk_tier_hint(_t=None):  # type: ignore
                return ""

            def set_risk_tier(t):  # type: ignore
                return {"tier": t}

        risk_tier_var = ctk.StringVar(master=ah_box, value=_rt0)
        ah_row3 = ctk.CTkFrame(ah_box, fg_color="transparent")
        ah_row3.pack(fill="x", padx=8, pady=(0, 8))
        ctk.CTkLabel(ah_row3, text="PC risk tier", text_color=_HC_LABEL).pack(side="left", padx=(6, 4))
        risk_hint_lbl = ctk.CTkLabel(
            ah_row3,
            text=risk_tier_hint(_rt0),
            text_color=_HC_MUTED,
            wraplength=420,
            anchor="w",
        )

        def _on_risk_tier_ui(v: str) -> None:
            try:
                r = set_risk_tier(v)
                risk_hint_lbl.configure(text=str(r.get("hint") or risk_tier_hint(v)))
                # Reflect mapped expert controls
                mode = str(r.get("mode") or "")
                if mode in ("auto", "ask", "always_approve", "plan"):
                    perm_var.set(mode)
                sand_on = bool(r.get("sandbox_enabled"))
                sandbox_on_var.set(sand_on)
                sp = str(r.get("sandbox_profile") or "")
                if sp in ("workspace", "strict", "read_only", "off"):
                    sand_prof_var.set(sp)
            except Exception:  # noqa: BLE001
                pass

        ctk.CTkOptionMenu(
            ah_row3,
            variable=risk_tier_var,
            values=["read_only", "ask", "full"],
            width=120,
            command=_on_risk_tier_ui,
        ).pack(side="left", padx=4)
        risk_hint_lbl.pack(side="left", padx=10)

        # Deep research / crawl limits
        ctk.CTkLabel(
            frame,
            text="Deep research & crawl limits",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=_HC_LABEL,
        ).grid(row=13, column=0, sticky="w", pady=(12, 2))
        res_box = ctk.CTkFrame(frame)
        res_box.grid(row=14, column=0, sticky="ew", pady=4)
        ctk.CTkLabel(
            res_box,
            text="Caps runaway crawls. Model uses DEEP_RESEARCH / WEB_CRAWL / WEB_SCRAPE / WEB_DOWNLOAD.",
            text_color=_HC_MUTED,
            wraplength=720,
            justify="left",
        ).pack(anchor="w", padx=8, pady=(6, 4))
        res_row = ctk.CTkFrame(res_box, fg_color="transparent")
        res_row.pack(fill="x", padx=8, pady=6)

        def _iv(key: str, default: int) -> str:
            try:
                return str(int(cfg.get(key, default)))
            except Exception:  # noqa: BLE001
                return str(default)

        research_sources_var = ctk.StringVar(master=res_box, value=_iv("research_max_sources", 8))
        research_follow_var = ctk.StringVar(master=res_box, value=_iv("research_follow_links", 4))
        crawl_pages_var = ctk.StringVar(master=res_box, value=_iv("research_crawl_max_pages", 12))
        crawl_depth_var = ctk.StringVar(master=res_box, value=_iv("research_crawl_max_depth", 2))
        for lab, var, vals in (
            ("Sources", research_sources_var, ["4", "6", "8", "10", "12", "16"]),
            ("Follow links", research_follow_var, ["0", "2", "4", "6", "8"]),
            ("Crawl pages", crawl_pages_var, ["5", "8", "12", "20", "30"]),
            ("Crawl depth", crawl_depth_var, ["1", "2", "3"]),
        ):
            ctk.CTkLabel(res_row, text=lab, text_color=_HC_LABEL).pack(side="left", padx=(8, 2))
            ctk.CTkOptionMenu(res_row, variable=var, values=vals, width=70).pack(side="left", padx=2)

        # Extend save_all to persist research limits
        _save_prev2 = save_all_settings

        def save_all_settings() -> None:  # type: ignore[no-redef]
            try:
                self.cfg["research_max_sources"] = int(research_sources_var.get())
                self.cfg["research_follow_links"] = int(research_follow_var.get())
                self.cfg["research_crawl_max_pages"] = int(crawl_pages_var.get())
                self.cfg["research_crawl_max_depth"] = int(crawl_depth_var.get())
            except Exception:  # noqa: BLE001
                pass
            try:
                self.cfg["agent_harness_enabled"] = bool(harness_on_var.get())
                self.cfg["agent_sandbox_enabled"] = bool(sandbox_on_var.get())
                self.cfg["agent_hooks_enabled"] = bool(hooks_on_var.get())
                self.cfg["agent_permission_mode"] = perm_var.get() or "auto"
                self.cfg["agent_sandbox_profile"] = sand_prof_var.get() or "workspace"
                # Prefer explicit risk tier (maps permissions); then re-sync expert fields
                try:
                    from app.services.agent_harness.permissions import set_risk_tier

                    set_risk_tier(risk_tier_var.get() or "ask")
                    self.cfg = storage.load_config()
                    # Re-apply expert toggles the user may have changed after tier
                    self.cfg["agent_harness_enabled"] = bool(harness_on_var.get())
                    self.cfg["agent_sandbox_enabled"] = bool(sandbox_on_var.get())
                    self.cfg["agent_hooks_enabled"] = bool(hooks_on_var.get())
                    self.cfg["agent_permission_mode"] = perm_var.get() or "auto"
                    self.cfg["agent_sandbox_profile"] = sand_prof_var.get() or "workspace"
                    self.cfg["agent_risk_tier"] = risk_tier_var.get() or "ask"
                except Exception:  # noqa: BLE001
                    self.cfg["agent_risk_tier"] = risk_tier_var.get() or "ask"
            except Exception:  # noqa: BLE001
                pass
            _save_prev2()

        for bar in (save_bar, btn_row, res_row):
            try:
                for child in bar.winfo_children():
                    try:
                        if "Save all" in str(child.cget("text")):
                            child.configure(command=save_all_settings)
                    except Exception:  # noqa: BLE001
                        pass
            except Exception:  # noqa: BLE001
                pass
        # sticky bar buttons
        for child in save_bar.winfo_children():
            try:
                if "Save all" in str(child.cget("text")):
                    child.configure(command=save_all_settings)
            except Exception:  # noqa: BLE001
                pass
        for child in btn_row.winfo_children():
            try:
                if "Save all" in str(child.cget("text")):
                    child.configure(command=save_all_settings)
            except Exception:  # noqa: BLE001
                pass

        ctk.CTkLabel(
            frame,
            text="Provider capabilities (honest)",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=_HC_LABEL,
        ).grid(row=13, column=0, sticky="w", pady=(8, 2))
        cap_box = ctk.CTkTextbox(frame, height=100, font=ctk.CTkFont(family="Consolas", size=11))
        try:
            cap_box.grid(row=14, column=0, sticky="ew", pady=4)
            cap_box.insert("1.0", format_capability_matrix())
            cap_box.configure(state="disabled")
        except Exception:  # noqa: BLE001
            pass

        # Task #1: Direct Grok (xAI) — preferred over OpenRouter
        grok_bar = ctk.CTkFrame(frame, fg_color=("#dbeafe", "#1e293b"), corner_radius=10)
        grok_bar.grid(row=15, column=0, sticky="ew", pady=(10, 6))
        ctk.CTkLabel(
            grok_bar,
            text="Use Grok directly (xAI) — no CLI, no OpenRouter credits required",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=_HC_LABEL,
            anchor="w",
        ).pack(fill="x", padx=12, pady=(10, 2))
        ctk.CTkLabel(
            grok_bar,
            text="Get an API key at console.x.ai · paste below on provider “xAI Grok” · or use the button",
            text_color=_HC_MUTED,
            anchor="w",
            font=ctk.CTkFont(size=11),
        ).pack(fill="x", padx=12, pady=(0, 6))
        gb = ctk.CTkFrame(grok_bar, fg_color="transparent")
        gb.pack(fill="x", padx=10, pady=(0, 10))
        ctk.CTkButton(
            gb,
            text="✦ Connect Grok (xAI key)",
            width=200,
            height=32,
            command=self._use_grok_as_agent,
            **style_chrome_button(primary=True),
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            gb,
            text="Test active model",
            width=140,
            height=32,
            command=self._test_active_llm_connection,
            **style_chrome_button(),
        ).pack(side="left", padx=4)

        ctk.CTkLabel(
            frame,
            text="LLM providers & keys — xAI Grok, OpenRouter, OpenAI, Offline · Ollama (local)…",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=_HC_LABEL,
        ).grid(row=16, column=0, sticky="w", pady=(8, 4))

        body = ctk.CTkFrame(frame)
        body.grid(row=17, column=0, sticky="ew", pady=(0, 8))
        body.grid_columnconfigure(1, weight=1)

        # Bottom save (after scrolling to providers)
        bottom_save = ctk.CTkFrame(frame, fg_color="transparent")
        bottom_save.grid(row=18, column=0, sticky="ew", pady=(12, 20))
        ctk.CTkButton(
            bottom_save,
            text="💾  Save all settings",
            width=200,
            height=40,
            command=save_all_settings,
            **style_chrome_button(primary=True),
        ).pack(side="left", padx=4)
        ctk.CTkLabel(
            bottom_save,
            text="Also saves Web search + browser + chat options",
            text_color=_HC_MUTED,
        ).pack(side="left", padx=10)

        plist = ctk.CTkScrollableFrame(body, width=200)
        plist.grid(row=0, column=0, rowspan=3, sticky="nsw", padx=8, pady=8)

        form = ctk.CTkFrame(body)
        form.grid(row=0, column=1, sticky="nsew", padx=8, pady=8)
        form.grid_columnconfigure(1, weight=1)

        state: dict[str, Any] = {"provider_id": prov.resolve_active_llm().get("provider_id") or "openrouter"}

        name_e = ctk.CTkEntry(form, placeholder_text="Provider name")
        base_e = ctk.CTkEntry(form, placeholder_text="Base URL (Offline Ollama: http://127.0.0.1:11434/v1)")
        key_e = ctk.CTkEntry(form, placeholder_text="Paste API key", show="*")
        key_label_e = ctk.CTkEntry(form, placeholder_text="Key label e.g. personal")
        msg = ctk.CTkLabel(form, text="", text_color=_HC_MUTED, wraplength=420, justify="left")
        models_box = ctk.CTkTextbox(form, height=120)

        def load_provider(pid: str) -> None:
            state["provider_id"] = pid
            # PENDING #17: keep Offline · Ollama label migrated
            if pid == "ollama":
                try:
                    from app.core.services.llm.ollama_local import ensure_offline_label

                    ensure_offline_label()
                except Exception:  # noqa: BLE001
                    pass
            p = prov.get_provider(pid) or {}
            name_e.delete(0, "end")
            name_e.insert(0, p.get("name") or "")
            base_e.delete(0, "end")
            base_e.insert(0, p.get("base_url") or "")
            models_box.delete("1.0", "end")
            cache = p.get("models_cache") or []
            models_box.insert("1.0", "\n".join(cache[:80]) if cache else "(no models cached — click Fetch models)")
            keys = p.get("keys") or []
            hint = (
                f"Keys stored: {len(keys)}  |  "
                + ", ".join(f"{k.get('label')}({k.get('id')})" for k in keys[:6])
            )
            if pid == "ollama":
                try:
                    from app.core.services.llm.ollama_local import health, OFFLINE_LABEL

                    h = health(p.get("base_url") or "")
                    if h.get("running"):
                        hint = (
                            f"● {OFFLINE_LABEL} running · {len(h.get('model_names') or [])} local model(s). "
                            "Key may be “ollama”. Not a cloud API."
                        )
                        if h.get("model_names"):
                            models_box.delete("1.0", "end")
                            models_box.insert("1.0", "\n".join(h["model_names"][:80]))
                    else:
                        tip = " → ".join(str(a) for a in (h.get("next_actions") or [])[:3])
                        hint = f"○ {OFFLINE_LABEL} not running. Next: {tip}"
                except Exception:  # noqa: BLE001
                    hint = "Offline · Ollama (local) — check http://127.0.0.1:11434"
            msg.configure(text=hint)
            refresh_plist()

        def refresh_plist() -> None:
            for w in plist.winfo_children():
                w.destroy()

            # ── "New Provider" button at top of sidebar ───────────────────────
            new_btn = ctk.CTkButton(
                plist,
                text="➕  New Provider",
                font=ctk.CTkFont(weight="bold"),
                height=30,
                fg_color=(("#dbeafe", "#1e3a5f")),
                hover=True,
                command=lambda: self._show_create_provider_dialog(plist),
            )
            new_btn.pack(fill="x", pady=(4, 6))

            active = prov.resolve_active_llm()
            for p in prov.list_providers():
                star = "★ " if p.get("id") == active.get("provider_id") else ""
                ctk.CTkButton(
                    plist,
                    text=f"{star}{p.get('name')}",
                    anchor="w",
                    fg_color="transparent",
                    command=lambda i=p["id"]: load_provider(i),
                ).pack(fill="x", pady=2)

        def save_provider() -> None:
            p = prov.upsert_provider(
                provider_id=state.get("provider_id") or "",
                name=name_e.get().strip(),
                base_url=base_e.get().strip(),
            )
            state["provider_id"] = p["id"]
            msg.configure(text=f"Provider saved: {p.get('name')}")
            refresh_plist()

        def add_key() -> None:
            key = key_e.get().strip()
            if not key:
                msg.configure(text="Paste a key first")
                return
            try:
                entry = prov.add_key(
                    state["provider_id"],
                    key,
                    label=key_label_e.get().strip() or "default",
                )
                key_e.delete(0, "end")
                prov.set_active(state["provider_id"], key_id=entry["id"])
                load_provider(state["provider_id"])
                msg.configure(text=f"Key added: {entry.get('label')}")
            except Exception as e:  # noqa: BLE001
                msg.configure(text=str(e))

        def fetch_models() -> None:
            try:
                models = prov.fetch_models(state["provider_id"], force=True)
                models_box.delete("1.0", "end")
                models_box.insert("1.0", "\n".join(models[:120]))
                msg.configure(text=f"Fetched {len(models)} models")
                # set first as active if none
                active = prov.resolve_active_llm()
                if models and not active.get("model"):
                    prov.set_active(state["provider_id"], model=models[0])
            except Exception as e:  # noqa: BLE001
                msg.configure(text=f"Fetch failed: {e}")

        def set_active_provider() -> None:
            prov.set_active(state["provider_id"])
            # also sync model from first line if user typed in legacy
            msg.configure(text=f"Active provider: {state['provider_id']}")
            refresh_plist()

        ctk.CTkLabel(form, text="Provider name").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        name_e.grid(row=0, column=1, sticky="ew", padx=8, pady=4)
        ctk.CTkLabel(form, text="Base URL").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        base_e.grid(row=1, column=1, sticky="ew", padx=8, pady=4)
        ctk.CTkLabel(form, text="Add API key").grid(row=2, column=0, sticky="w", padx=8, pady=4)
        key_e.grid(row=2, column=1, sticky="ew", padx=8, pady=4)
        ctk.CTkLabel(form, text="Key label").grid(row=3, column=0, sticky="w", padx=8, pady=4)
        key_label_e.grid(row=3, column=1, sticky="ew", padx=8, pady=4)
        msg.grid(row=4, column=0, columnspan=2, sticky="w", padx=8, pady=4)
        ctk.CTkLabel(form, text="Models cache (fetched)").grid(
            row=5, column=0, columnspan=2, sticky="w", padx=8
        )
        models_box.grid(row=6, column=0, columnspan=2, sticky="nsew", padx=8, pady=4)
        form.grid_rowconfigure(6, weight=1)

        btns = ctk.CTkFrame(form, fg_color="transparent")
        btns.grid(row=7, column=0, columnspan=2, sticky="ew", padx=8, pady=8)
        ctk.CTkButton(btns, text="Save provider", command=save_provider).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="Add key", command=add_key).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="Fetch models", command=fetch_models).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="Set active provider", command=set_active_provider).pack(
            side="left", padx=4
        )
        ctk.CTkButton(
            btns,
            text="Test connection",
            command=self._test_active_llm_connection,
            **style_chrome_button(primary=True),
        ).pack(side="left", padx=4)

        self.settings_msg = msg
        refresh_plist()
        # Prefer opening xAI Grok first for new users connecting Grok
        try:
            load_provider("xai" if prov.get_provider("xai") else state["provider_id"])
        except Exception:  # noqa: BLE001
            load_provider(state["provider_id"])
        # Ctrl+S on Settings saves all form fields
        self._page_save_handler = save_all_settings

    def _on_theme_change(self, value: str) -> None:
        ctk.set_appearance_mode("Dark" if value == "dark" else "Light")
        self.cfg["theme"] = value
        storage.save_config(self.cfg)

    def _on_ui_theme_change(self, name: str) -> None:
        from app.ui.themes import apply_theme

        apply_theme(name)
        self.cfg["ui_theme"] = name
        self.cfg["theme"] = "dark" if "Dark" in name or name in ("Midnight", "Ocean", "Forest") else "light"
        storage.save_config(self.cfg)
        self.set_status(f"Theme: {name} (reopen page for full refresh)")
        # soft refresh current page
        self.show_page(self._current_page or "Chat")

    def _save_settings(self) -> None:
        # kept for compatibility; provider UI saves via providers module
        self.cfg = storage.load_config()
        self.set_status("Settings / providers updated")

    def _maybe_check_updates_on_start(self) -> None:
        """Task #10: soft version check on launch (never blocks UI)."""
        try:
            from app.core.services.misc.version_check import should_auto_check, check_for_updates

            if not should_auto_check():
                return
        except Exception:  # noqa: BLE001
            return

        def work() -> None:
            try:
                r = check_for_updates()
            except Exception:  # noqa: BLE001
                return

            def ui() -> None:
                try:
                    if not self.winfo_exists():
                        return
                    st = r.get("status")
                    if st == "update_available":
                        self.set_status(
                            f"Update available: v{r.get('latest')} (you have v{r.get('current')}) — see About",
                            toast=True,
                        )
                    elif st == "up_to_date":
                        # Quiet — only put version in status, no toast spam
                        pass
                except Exception:  # noqa: BLE001
                    pass

            try:
                self.after(0, ui)
            except Exception:  # noqa: BLE001
                pass

        threading.Thread(target=work, daemon=True).start()

    def _run_update_check_dialog(self) -> None:
        """Manual Check for updates (About / Settings)."""
        from app.core.services.misc.version_check import check_for_updates

        self.set_status("Checking version…")
        try:
            r = check_for_updates(force_remote=True)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Updates", str(e), parent=self)
            return
        title = {
            "update_available": "Update available",
            "up_to_date": "You're up to date",
            "unknown": "Version info",
            "error": "Update check",
        }.get(str(r.get("status") or ""), "Version")
        messagebox.showinfo(title, str(r.get("message") or r), parent=self)
        self.set_status(
            f"Version v{r.get('current')} · {r.get('status')}",
            toast=True,
        )

    def _page_about(self) -> None:
        from app.ui.themes import style_card, style_chrome_button, UI as _UI
        from app.core.services.misc.version_check import install_summary, check_for_updates

        frame = ctk.CTkFrame(self.content, fg_color="transparent")
        frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        frame.grid_columnconfigure(0, weight=1)

        self._page_header(
            frame,
            "About",
            f"{APP_NAME} v{__version__} — portable multi-agent studio",
            actions=[
                ("Check updates", self._run_update_check_dialog),
                ("Docs", lambda: self.set_status("See docs/ folder next to the app", toast=True)),
            ],
        )
        try:
            info = install_summary()
        except Exception:  # noqa: BLE001
            info = {
                "version": __version__,
                "mode_label": "unknown",
                "app_root": "",
                "data_dir": "",
                "launch": "Launch.bat",
                "python": "",
            }

        card = ctk.CTkFrame(frame, **style_card())
        card.grid(row=1, column=0, sticky="ew", pady=8)
        ctk.CTkLabel(
            card,
            justify="left",
            text_color=_UI["label"],
            font=ctk.CTkFont(size=16, weight="bold"),
            text=f"{APP_NAME}  v{info.get('version') or __version__}",
        ).pack(anchor="w", padx=16, pady=(16, 4))
        ctk.CTkLabel(
            card,
            justify="left",
            text_color=_UI["muted"],
            text=(
                f"Install mode: {info.get('mode_label')}\n"
                f"Start with: {info.get('launch')}\n"
                f"App folder:\n  {info.get('app_root')}\n"
                f"Your data (chats, keys):\n  {info.get('data_dir')}\n"
                f"Python: {info.get('python') or 'bundled'}\n\n"
                "Chat · multi-chat · memory · projects · Team · tools · Knowledge RAG\n"
                "Ctrl+K palette · Ctrl+\\ focus · F1 shortcuts · License: MIT (original code)"
            ),
        ).pack(anchor="w", padx=16, pady=(0, 8))

        upd = ctk.CTkFrame(frame, **style_card())
        upd.grid(row=2, column=0, sticky="ew", pady=8)
        ctk.CTkLabel(
            upd,
            text="Updates",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=_UI["label"],
        ).pack(anchor="w", padx=16, pady=(12, 4))
        status_lbl = ctk.CTkLabel(
            upd,
            text="Click Check for updates to compare this build with VERSION / optional URL.",
            text_color=_UI["muted"],
            justify="left",
            wraplength=640,
            anchor="w",
        )
        status_lbl.pack(anchor="w", padx=16, pady=(0, 8))

        def do_check() -> None:
            status_lbl.configure(text="Checking…")
            try:
                r = check_for_updates(force_remote=True)
                status_lbl.configure(text=str(r.get("message") or ""))
                self.set_status(f"v{r.get('current')} · {r.get('status')}", toast=True)
            except Exception as e:  # noqa: BLE001
                status_lbl.configure(text=str(e))

        bar = ctk.CTkFrame(upd, fg_color="transparent")
        bar.pack(fill="x", padx=12, pady=(0, 12))
        ctk.CTkButton(
            bar,
            text="Check for updates",
            width=160,
            command=do_check,
            **style_chrome_button(primary=True),
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            bar,
            text="Open app folder",
            width=140,
            command=lambda: self._open_path_in_os(str(info.get("app_root") or "")),
            **style_chrome_button(),
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            bar,
            text="Open data folder",
            width=140,
            command=lambda: self._open_path_in_os(str(info.get("data_dir") or "")),
            **style_chrome_button(),
        ).pack(side="left", padx=4)

    def _open_path_in_os(self, path: str) -> None:
        if not path:
            return
        try:
            from app.ui.components.message_box import open_url_or_path
            from app.core.services.data.rag_knowledge import path_to_file_uri

            open_url_or_path(path_to_file_uri(path))
            self.set_status(f"Opened {path}", toast=True)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Open folder", str(e), parent=self)

    def _maybe_offer_crash_restore(self) -> None:
        """If previous run did not close cleanly, offer to open last chat."""
        cid = getattr(self, "_crash_restore_chat_id", None)
        if not cid:
            return
        if not messagebox.askyesno(
            "Restore session",
            "The previous session may have closed unexpectedly.\n\n"
            f"Open last active chat again?\n({str(cid)[:12]}…)",
            parent=self,
        ):
            self._crash_restore_chat_id = None
            return
        try:
            chat_store.set_active_chat_id(cid)
            self._chat_state = chat_svc.load_chat(cid)
            self.show_page("Chat")
            # Re-paint only — a second/third full show_page destroyed chat_scroll mid-render
            self.after(250, self._chat_render_transcript)
            self.set_status("Restored previous chat after unclean exit")
        except Exception as e:  # noqa: BLE001
            self.set_status(f"Restore failed: {e}")
        self._crash_restore_chat_id = None

    def _setup_system_tray(self) -> None:
        """PENDING #19 — system tray Show/Hide/Quit; soft-degrades if pystray missing."""
        try:
            from app.services import system_tray as tray

            if not tray.should_use_tray():
                return

            def _show() -> None:
                try:
                    self.after(0, self._show_from_tray)
                except Exception:  # noqa: BLE001
                    pass

            def _hide() -> None:
                try:
                    self.after(0, self._hide_to_tray)
                except Exception:  # noqa: BLE001
                    pass

            def _quit() -> None:
                try:
                    self.after(0, self._quit_from_tray)
                except Exception:  # noqa: BLE001
                    pass

            tray.set_callbacks(show=_show, hide=_hide, quit_app=_quit)
            if tray.start():
                try:
                    self.bind("<Unmap>", self._on_unmap_minimize, add="+")
                except Exception:  # noqa: BLE001
                    pass
                try:
                    self.set_status("System tray ready — close/minimize can run in background", toast=False)
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            pass

    def _hide_to_tray(self) -> None:
        """Withdraw main window; keep running in background via tray."""
        try:
            from app.services import system_tray as tray

            if not tray.should_use_tray():
                return
            if not tray.start():
                return
        except Exception:  # noqa: BLE001
            return
        self._hidden_in_tray = True
        try:
            # Persist geometry before hide
            try:
                st = str(self.state() or "")
                if st != "zoomed" and st != "iconic":
                    cfg = storage.load_config()
                    cfg["window_geometry"] = self.geometry()
                    storage.save_config(cfg)
                    if isinstance(getattr(self, "cfg", None), dict):
                        self.cfg["window_geometry"] = cfg["window_geometry"]
            except Exception:  # noqa: BLE001
                pass
            self.withdraw()
            try:
                self.set_status("Running in tray — right-click tray icon → Show / Quit", toast=True)
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            self._hidden_in_tray = False

    def _show_from_tray(self) -> None:
        """Restore main window from tray."""
        self._hidden_in_tray = False
        try:
            self.deiconify()
            try:
                self.state("normal")
            except Exception:  # noqa: BLE001
                pass
            self.lift()
            self.focus_force()
            try:
                self.attributes("-topmost", True)
                self.after(200, lambda: self.attributes("-topmost", False))
            except Exception:  # noqa: BLE001
                pass
            try:
                self.set_status("Restored from tray", toast=True)
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            pass

    def _quit_from_tray(self) -> None:
        """Fully exit (tray Quit)."""
        self._tray_quitting = True
        self._hidden_in_tray = False
        self._on_close()

    def _on_unmap_minimize(self, event=None) -> None:  # noqa: ANN001
        """OS minimize → tray when enabled (PENDING #19)."""
        try:
            if event is not None and getattr(event, "widget", None) is not self:
                return
        except Exception:  # noqa: BLE001
            pass
        if getattr(self, "_tray_quitting", False) or getattr(self, "_hidden_in_tray", False):
            return
        try:
            from app.services import system_tray as tray

            if not tray.should_use_tray() or not tray.minimize_to_tray():
                return
            st = str(self.state() or "")
            if st == "iconic":
                # Defer so Tk finishes iconify before we withdraw
                self.after(50, self._hide_to_tray)
        except Exception:  # noqa: BLE001
            pass

    def _on_close(self) -> None:
        # PENDING #19: X button → tray (background) unless Quit or tray disabled
        if not getattr(self, "_tray_quitting", False):
            try:
                from app.services import system_tray as tray

                if tray.should_use_tray() and tray.close_to_tray():
                    self._hide_to_tray()
                    return
            except Exception:  # noqa: BLE001
                pass
        try:
            if getattr(self, "_chat_state", None):
                chat_svc.save_chat(self._chat_state)
        except Exception:  # noqa: BLE001
            pass
        try:
            cfg = storage.load_config()
            cfg["session_unclean"] = False
            cfg["session_active_chat"] = ""
            # Remember size + maximized state for next launch (OS title bar)
            try:
                try:
                    is_max = str(self.state()) == "zoomed"
                except Exception:  # noqa: BLE001
                    is_max = bool(getattr(self, "_win_maximized", False))
                cfg["window_maximized"] = is_max
                self._win_maximized = is_max
                if not is_max:
                    try:
                        if str(self.state()) != "withdrawn":
                            cfg["window_geometry"] = self.geometry()
                    except Exception:  # noqa: BLE001
                        cfg["window_geometry"] = self.geometry()
            except Exception:  # noqa: BLE001
                pass
            storage.save_config(cfg)
        except Exception:  # noqa: BLE001
            pass
        try:
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
        # Stop system monitor
        try:
            self._sysmon_running = False
        except Exception:  # noqa: BLE001
            pass
        self.destroy()


def run_app(splash: Any = None) -> None:
    # Apply theme BEFORE the first CTk window exists — avoids Windows titlebar
    # withdraw/redraw flash that happens when appearance mode changes after map.
    try:
        cfg = storage.load_config()
        from app.ui.themes import apply_theme

        apply_theme(cfg.get("ui_theme") or "Readable Dark")
        AppWindow._theme_preapplied = True  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        try:
            ctk.set_appearance_mode("Dark")
            ctk.set_default_color_theme("blue")
            AppWindow._theme_preapplied = True  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            AppWindow._theme_preapplied = False  # type: ignore[attr-defined]
    if splash is not None:
        try:
            splash.stage("Building main window…", 85)
        except Exception:  # noqa: BLE001
            pass
    app = AppWindow()
    # Ensure the window is mapped and rendered before we hide the splash.
    try:
        app.update_idletasks()
        # PENDING #19: optional start minimized → tray
        _start_min = False
        try:
            from app.services import system_tray as _tray

            _start_min = bool(_tray.should_use_tray() and _tray.start_minimized())
        except Exception:  # noqa: BLE001
            _start_min = False
        if _start_min:
            app._hidden_in_tray = True
            try:
                app.withdraw()
            except Exception:  # noqa: BLE001
                pass
            try:
                _tray.start()
            except Exception:  # noqa: BLE001
                pass
        else:
            app.deiconify()
        app.after(50, lambda: None)  # let the event loop process a frame
    except Exception:  # noqa: BLE001
        pass
    if splash is not None:
        try:
            # Hide splash first so the user sees the main window immediately.
            splash.window.withdraw()
            # Schedule splash close after a short delay to ensure the main window is fully ready.
            app.after(100, lambda: splash.finish() if splash else None)
        except Exception:  # noqa: BLE001
            pass
    app.mainloop()
