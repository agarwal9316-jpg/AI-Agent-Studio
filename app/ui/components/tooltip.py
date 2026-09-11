"""
Theme-aware hover tooltips for CustomTkinter widgets.

Purpose (Phase 1 -- user-friendly GUI): "mouse hover gives every detail."
Every control can carry a short, plain-English explanation that appears as a
small, high-contrast popup near the cursor when the user hovers (no click needed).

Design notes:
  - Uses the app's `themes.UI` token palette so tooltips stay readable in both
    light and dark mode (never low-contrast defaults).
  - Small hover delay (~450ms) so passing the cursor over a control does not
    flash a tooltip; it appears only when the user intentionally rests on it.
  - Binds <Enter>/<Leave>/<Motion>; auto-destroys the tooltip on leave or when
    the source widget is destroyed.
  - Safe: every internal call is try/except wrapped so a tooltip can never crash
    the app (matches the codebase's `# noqa: BLE001` defensive style).
"""

from __future__ import annotations

from typing import Any, Callable

import customtkinter as ctk

from app.ui.themes import UI as _UI

# Tooltip popup colors from the UI palette (light, dark) tuples.
_FG = _UI.get("menu_drop_fg", ("#ffffff", "#111827"))
_TEXT = _UI.get("menu_drop_text", _UI.get("label", ("#0a0f1a", "#f9fafb")))
_BORDER = _UI.get("top_border", ("#d1d5db", "#374151"))


class Tooltip:
    """A small, theme-aware hover popup attached to a widget.

    The tooltip tracks the pointer on <Motion> so it stays beside the cursor,
    appears after `delay_ms` of rest, and is removed on <Leave> or destroy.
    """

    def __init__(
        self,
        widget: Any,
        text: str | Callable[[], str],
        *,
        delay_ms: int = 450,
        wrap: int = 340,
        font_size: int = 12,
        max_chars: int = 380,
    ) -> None:
        self.widget = widget
        self._text = text
        self._delay_ms = delay_ms
        self._wrap = wrap
        self._font_size = font_size
        self._max_chars = max_chars
        self._after: str | None = None
        self._tooltip: ctk.CTkFrame | None = None
        self._widget_destroy_guard: str | None = None

        try:
            self._bind()
        except Exception:  # noqa: BLE001
            pass

    # -- public API -------------------------------------------------------
    def text(self) -> str:
        """Resolve tooltip text (supports dynamic callables)."""
        raw = self._text() if callable(self._text) else self._text
        return (raw or "").strip()[: self._max_chars]

    def hide(self) -> None:
        self._cancel_schedule()
        self._destroy_tooltip()

    def destroy(self) -> None:
        self.hide()
        try:
            self._unbind()
        except Exception:  # noqa: BLE001
            pass
# -- binding ----------------------------------------------------------
    def _bind(self) -> None:
        try:
            w = self.widget

            def _on_enter(_ev: Any = None) -> str | None:
                return self._schedule_show()

            def _on_leave(_ev: Any = None) -> str | None:
                self.hide()
                return None

            def _on_motion(_ev: Any = None) -> str | None:
                # Nudge position on movement so the popup tracks the pointer.
                if self._tooltip is not None and self._tooltip.winfo_exists():
                    self._position(_ev)
                return None

            w.bind("<Enter>", _on_enter, add="+")
            w.bind("<Leave>", _on_leave, add="+")
            w.bind("<Motion>", _on_motion, add="+")

            # Clean up if the owning widget is destroyed.
            self._widget_destroy_guard = w.bind("<Destroy>", lambda _e: self.hide(), add="+")
        except Exception:  # noqa: BLE001
            pass

    def _unbind(self) -> None:
        try:
            for seq in ("<Enter>", "<Leave>", "<Motion>"):
                try:
                    self.widget.unbind(seq)
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            pass

    # -- scheduling -------------------------------------------------------
    def _schedule_show(self) -> str | None:
        self._cancel_schedule()
        try:
            self._after = self.widget.after(self._delay_ms, self._show)
        except Exception:  # noqa: BLE001
            pass
        return None

    def _cancel_schedule(self) -> None:
        try:
            if self._after:
                self.widget.after_cancel(self._after)
        except Exception:  # noqa: BLE001
            pass
        self._after = None

    # -- show / position ---------------------------------------------------
    def _show(self) -> None:
        self._after = None
        text = self.text()
        if not text:
            return
        try:
            self._destroy_tooltip()
            fr = ctk.CTkFrame(
                self.widget,
                fg_color=_FG,
                corner_radius=8,
                border_width=1,
                border_color=_BORDER,
            )
            ctk.CTkLabel(
                fr,
                text=text,
                text_color=_TEXT,
                font=ctk.CTkFont(size=self._font_size),
                wraplength=self._wrap,
                justify="left",
                anchor="w",
            ).pack(padx=10, pady=8)
            self._tooltip = fr
            fr.lift()
            self._position(None)
        except Exception:  # noqa: BLE001
            pass

    def _position(self, _ev: Any = None) -> None:
        fr = self._tooltip
        if fr is None:
            return
        try:
            # Keep the tooltip near the top-right of the source widget so it
            # never hides the control under the pointer.
            x = self.widget.winfo_rootx() + self.widget.winfo_width()
            y = self.widget.winfo_rooty() - 8
            fr.place(
                x=max(4, x + 4),
                y=max(4, y - fr.winfo_reqheight() - 6),
            )
        except Exception:  # noqa: BLE001
            pass

    def _destroy_tooltip(self) -> None:
        if self._tooltip is not None:
            try:
                self._tooltip.destroy()
            except Exception:  # noqa: BLE001
                pass
            self._tooltip = None


def add_tooltip(
    widget: Any,
    text: str | Callable[[], str],
    *,
    delay_ms: int = 450,
    wrap: int = 340,
    font_size: int = 12,
) -> Tooltip | None:
    """Add a hover tooltip to a widget. Returns the Tooltip (or None on failure).

    Safe no-op if widget/theme missing -- never breaks the UI.
    """
    if widget is None:
        return None
    try:
        return Tooltip(
            widget,
            text,
            delay_ms=delay_ms,
            wrap=wrap,
            font_size=font_size,
        )
    except Exception:  # noqa: BLE001
        return None