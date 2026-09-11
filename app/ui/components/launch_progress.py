"""Lightweight launch / splash screen with a progress bar.

Shown from the very start of ``app.main`` so the user can see the app is
actually launching (the main ``AppWindow`` can take a while to build all its
pages). The splash is a small, always-on-top, centered ``customtkinter``
window. The caller advances it between setup stages and must ``close()`` it once
the real main window is ready.

Threading note: Tk is not thread-safe, so the splash is driven from the main
thread only. Advancing it between stages is enough: during the (blocking)
``AppWindow`` construction it simply keeps its last rendered frame on screen,
then we close it right before ``mainloop()`` starts.
"""

from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from app.version import APP_NAME, __version__

# Colors tuned to the app's "Readable Dark"-ish look without importing themes
# (themes import is heavy and we want the splash first).
_BG = "#101418"
_FG = "#e8eaed"
_ACCENT = "#3b82f6"
_MUTED = "#9aa3ad"


def _on_close_clear() -> None:
    """Default close hook — override to avoid triggering app shutdown."""


class LaunchProgress:
    """A small always-on-top splash window with a labelled progress bar.

    Usage::

        splash = LaunchProgress()
        splash.stage("Loading configuration…", 15)
        ...
        splash.stage("Building interface…", 80)
        app = AppWindow()
        splash.finish()   # sets 100% and closes
        app.mainloop()

    If the ``on_close`` callback is provided it is invoked when the user clicks
    the window's close button (letting the app decide whether to abort).
    """

    def __init__(self, on_close: Callable[[], None] | None = None) -> None:
        self._on_close = on_close
        self._closed = False

        self.window = ctk.CTk()
        self.window.title(f"{APP_NAME} — launching")
        self.window.configure(fg_color=_BG)
        self.window.resizable(False, False)
        # Remove minimise/maximise chrome; keep it a focused, simple splash.
        self.window.overrideredirect(False)
        try:
            self.window.attributes("-topmost", True)
        except Exception:  # noqa: BLE001 — non-fatal on some platforms
            pass

        self._stage_label = ctk.CTkLabel(
            self.window,
            text="Starting…",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=_FG,
        )
        self._stage_label.pack(padx=28, pady=(22, 4), anchor="w")

        self._sub_label = ctk.CTkLabel(
            self.window,
            text=f"{APP_NAME}  v{__version__}",
            font=ctk.CTkFont(size=11),
            text_color=_MUTED,
        )
        self._sub_label.pack(padx=28, pady=(0, 14), anchor="w")

        self._bar = ctk.CTkProgressBar(
            self.window,
            width=360,
            height=12,
            progress_color=_ACCENT,
            fg_color="#22282f",
        )
        self._bar.pack(padx=28, pady=(0, 6))
        self._bar.set(0.0)

        self._pct_label = ctk.CTkLabel(
            self.window,
            text="0%",
            font=ctk.CTkFont(size=10),
            text_color=_MUTED,
        )
        self._pct_label.pack(padx=28, pady=(0, 18), anchor="e")

        if on_close is not None:
            self.window.protocol("WM_DELETE_WINDOW", self._user_close)

        # Centre on the primary display.
        self.window.update_idletasks()
        try:
            self.window.after_idle(self._centre)
        except Exception:  # noqa: BLE001
            pass

    def _centre(self) -> None:
        self.window.update_idletasks()
        try:
            w = self.window.winfo_reqwidth()
            h = self.window.winfo_reqheight()
            x = (self.window.winfo_screenwidth() - w) // 2
            y = (self.window.winfo_screenheight() - h) // 2
            self.window.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:  # noqa: BLE001
            pass
        self._flush()

    def _user_close(self) -> None:
        self.window.withdraw()
        cb = self._on_close
        if cb is not None:
            try:
                cb()
            except Exception:  # noqa: BLE001
                pass

    def _flush(self) -> None:
        """Pump the Tk event loop so the splash actually repaints."""
        try:
            self.window.update()
        except Exception:  # noqa: BLE001
            pass

    def stage(self, message: str, value: float) -> None:
        """Update the stage label and the 0-100 progress value."""
        if self._closed:
            return
        try:
            self._stage_label.configure(text=message)
            value = max(0.0, min(100.0, value))
            self._bar.set(value / 100.0)
            self._pct_label.configure(text=f"{int(round(value))}%")
            self._flush()
        except Exception:  # noqa: BLE001
            pass

    def finish(self) -> None:
        """Fill the bar to 100% and close the splash window."""
        self.stage("Ready", 100)
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.window.destroy()
        except Exception:  # noqa: BLE001
            pass