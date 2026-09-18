"""Status bar helpers and non-blocking toast.

Extracted from AppWindow to shrink the god class.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

import customtkinter as ctk

from app.paths import data_dir
from app.ui.components.tooltip import add_tooltip
from app.ui.themes import UI as _UI
from app.version import __version__


def build_status_text(
    *,
    task_status: str = "none",
    llm_phase: str = "idle",
) -> str:
    """Compose the default status-bar line (Ready + data + HW + version)."""
    bg = ""
    usage = ""
    hw = ""
    try:
        from app.core.services.chat.orchestrator import get_orchestrator

        bg = f"  |  BG: {get_orchestrator().status}"
    except Exception:
        pass
    try:
        from app.core.services.data.usage_meter import format_status_line

        usage = f"  |  {format_status_line()}"
    except Exception:
        pass
    try:
        from app.core.services.system.ops_monitor import hardware_snapshot

        snap = hardware_snapshot()
        cpu = snap.get("cpu_percent")
        ram = snap.get("ram") or {}
        gpu = (snap.get("gpu") or [{}])[0] if snap.get("gpu") else {}
        if cpu is not None:
            hw = (
                f"  |  CPU {cpu}%  ·  RAM {ram.get('used_gb', 0):.1f}/"
                f"{ram.get('total_gb', 0):.1f} GB ({ram.get('percent', '?')}%)  ·  "
                f"GPU {gpu.get('util_percent', '—')}%"
            )
    except Exception:
        pass

    task_llm = ""
    try:
        from app.core.services.chat.task_watch import llm_chip_label, task_chip_label

        task_llm = (
            f"{task_chip_label(task_status)}  |  "
            f"{llm_chip_label(llm_phase)}  |  "
        )
    except Exception:
        task_llm = ""

    return f"{task_llm}Ready  |  data: {data_dir()}{bg}{usage}{hw}  |  v{__version__}"


def ensure_version_in_message(msg: str) -> str:
    """Always keep version visible in the status line."""
    try:
        ver = f"v{__version__}"
        if ver not in (msg or ""):
            return f"{msg}  |  {ver}"
    except Exception:
        pass
    return msg


def toast_kind_from_text(text: str) -> str:
    low = (text or "").lower()
    if any(x in low for x in ("fail", "error", "denied")):
        return "err"
    if any(x in low for x in ("ok", "done", "saved", "ready", "complete")):
        return "ok"
    if "approval" in low or "warn" in low:
        return "warn"
    return "info"


class ToastHost:
    """Non-blocking toast shown in the top-right of a parent window."""

    def __init__(self, parent: ctk.CTkBaseClass, after: Callable[[int, Callable], Any]) -> None:
        self._parent = parent
        self._after = after
        self._toast_win: Optional[ctk.CTkFrame] = None

    def show(self, message: str, *, kind: str = "info", ms: int = 3200) -> None:
        try:
            old = self._toast_win
            if old is not None:
                try:
                    old.destroy()
                except Exception:
                    pass

            colors = {
                "info": _UI["accent_soft"],
                "ok": (("#d1fae5", "#064e3b")),
                "warn": (("#fef3c7", "#78350f")),
                "err": (("#fee2e2", "#7f1d1d")),
            }
            fg = colors.get(kind, colors["info"])
            fr = ctk.CTkFrame(
                self._parent,
                fg_color=fg,
                corner_radius=12,
                border_width=1,
                border_color=_UI["top_border"],
            )
            self._toast_win = fr
            ctk.CTkLabel(
                fr,
                text=(message or "")[:120],
                text_color=_UI["label"],
                font=ctk.CTkFont(size=12),
                wraplength=360,
                justify="left",
            ).pack(padx=14, pady=10)
            fr.place(relx=0.98, rely=0.06, anchor="ne")
            self._after(ms, lambda: self._destroy(fr))
        except Exception:
            pass

    def _destroy(self, fr: Any) -> None:
        try:
            if self._toast_win is fr:
                self._toast_win = None
            fr.destroy()
        except Exception:
            pass


def attach_tooltip(widget: Any, text: str) -> None:
    """Attach a hover tooltip (safe no-op on failure)."""
    try:
        add_tooltip(widget, text)
    except Exception:
        pass
