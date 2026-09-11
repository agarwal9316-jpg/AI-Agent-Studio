"""
Smooth mousewheel/trackpad scrolling for CustomTkinter scrollable frames.

Why (Phase 1 -- user-friendly GUI, "proper smooth scroll"):
  - CustomTkinter's CTkScrollableFrame only scrolls when the cursor is directly
    over its inner canvas, and child widgets (buttons, labels, nested frames)
    swallow <MouseWheel> events. That makes content feel dead when the pointer
    is over a child -- a common "jerky / can't scroll" complaint.
  - This helper binds a uniform, consistent wheel step across the frame and all
    of its descendants so one notch always scrolls the same smooth amount
    regardless of which widget the cursor is over.

Design:
  - Uses the same "+50% wheel" spirit as the chat wheel (v1.23.5): a fixed,
    comfortable delta per notch instead of the tiny default CTk step.
  - Cross-platform trackpad support: Windows (±120/notch), Mac (small deltas
    with momentum), Linux (Button-4/5), high-precision trackpads (small deltas).
  - Smooth animated scrolling with configurable easing for natural feel.
  - Momentum/inertia scrolling for trackpad flings.
  - Lets native multi-line Text widgets scroll themselves (chat input, logs).
  - Registers a guard so bindings detach if the scrollable frame is destroyed.
"""

from __future__ import annotations

import math
import platform
import sys
import time
from typing import Any, Callable

import customtkinter as ctk


def _walk(widget: Any):
    """Yield a widget and all of its descendants (breadth-first)."""
    yield widget
    try:
        for child in widget.winfo_children():
            yield from _walk(child)
    except Exception:  # noqa: BLE001
        return


def _can_scroll(canvas: Any) -> bool:
    try:
        bbox = canvas.bbox("all")
        return bool(bbox and bbox[3] > canvas.winfo_height())
    except Exception:  # noqa: BLE001
        return True


def _can_scroll_x(canvas: Any) -> bool:
    try:
        bbox = canvas.bbox("all")
        return bool(bbox and bbox[2] > canvas.winfo_width())
    except Exception:  # noqa: BLE001
        return True


class SmoothScroller:
    """High-quality animated scroller with momentum support."""

    def __init__(
        self,
        canvas: Any,
        *,
        step: int = 60,
        animate: bool = True,
        momentum: bool = True,
        horizontal: bool = False,
    ):
        self.canvas = canvas
        self.step = step
        self.animate = animate
        self.momentum = momentum
        self.horizontal = horizontal

        # Animation state
        self._anim_id: int | None = None
        self._target_pos: float = 0.0
        self._current_pos: float = 0.0
        self._velocity: float = 0.0
        self._last_time: float = 0.0
        self._last_delta: float = 0.0
        self._is_animating: bool = False

        # Platform detection
        self._is_mac = sys.platform == "darwin"
        self._is_windows = sys.platform == "win32"
        self._is_linux = sys.platform.startswith("linux")

    def _get_scroll_pos(self) -> float:
        """Get current scroll position (0.0 to 1.0)."""
        try:
            if self.horizontal:
                return self.canvas.xview()[0]
            return self.canvas.yview()[0]
        except Exception:  # noqa: BLE001
            return 0.0

    def _alive(self) -> bool:
        try:
            c = self.canvas
            return c is not None and bool(c.winfo_exists())
        except Exception:  # noqa: BLE001
            return False

    def _set_scroll_pos(self, pos: float) -> None:
        """Set scroll position (clamped to 0.0-1.0)."""
        if not self._alive():
            self.stop()
            return
        try:
            pos = max(0.0, min(1.0, pos))
            if self.horizontal:
                self.canvas.xview_moveto(pos)
            else:
                self.canvas.yview_moveto(pos)
        except Exception:  # noqa: BLE001
            self.stop()

    def _scroll_by_units(self, units: int) -> None:
        """Scroll by discrete units (for non-animated fallback)."""
        try:
            if self.horizontal:
                self.canvas.xview_scroll(units, "units")
            else:
                self.canvas.yview_scroll(units, "units")
        except Exception:  # noqa: BLE001
            pass

    def _animate_step(self) -> None:
        """Single animation frame using spring physics."""
        if not self._is_animating:
            return
        if not self._alive():
            self.stop()
            return

        now = time.perf_counter()
        dt = now - self._last_time
        self._last_time = now

        if dt <= 0 or dt > 0.1:  # Clamp dt
            dt = 1 / 60

        # Spring animation towards target
        if self.momentum and abs(self._velocity) > 0.01:
            # Apply friction
            friction = 0.95
            self._velocity *= friction

            # Update position
            self._current_pos += self._velocity * dt * 100

            # Clamp and bounce
            if self._current_pos <= 0:
                self._current_pos = 0
                self._velocity = 0
            elif self._current_pos >= 1:
                self._current_pos = 1
                self._velocity = 0
        else:
            # Spring towards target
            stiffness = 15.0
            damping = 0.8
            displacement = self._target_pos - self._current_pos
            spring_force = displacement * stiffness
            self._velocity = (self._velocity + spring_force * dt) * damping
            self._current_pos += self._velocity * dt * 100

            # Check if settled
            if abs(self._current_pos - self._target_pos) < 0.001 and abs(self._velocity) < 0.01:
                self._current_pos = self._target_pos
                self._velocity = 0
                self._is_animating = False

        self._set_scroll_pos(self._current_pos)

        if self._is_animating:
            self._anim_id = self.canvas.after(16, self._animate_step)  # ~60fps

    def _start_animation(self) -> None:
        """Start the animation loop."""
        if self._is_animating:
            return
        self._is_animating = True
        self._last_time = time.perf_counter()
        self._current_pos = self._get_scroll_pos()
        self._animate_step()

    def scroll_by_delta(self, delta: float, is_fling: bool = False) -> None:
        """Scroll by a delta amount (normalized)."""
        if not self.animate:
            # Direct scroll without animation
            units = int(delta * (self.step / 30.0))
            if units == 0:
                units = 1 if delta > 0 else -1
            self._scroll_by_units(-units)
            return

        # Calculate target position
        current = self._get_scroll_pos()
        # Normalize delta to scroll fraction (1.0 = full viewport)
        viewport_fraction = 0.15  # Scroll ~15% of viewport per "notch"
        scroll_amount = delta * viewport_fraction

        if is_fling:
            # For flings, add momentum
            self._velocity = scroll_amount * 50.0  # Scale for momentum
            self._target_pos = current - scroll_amount
        else:
            # Normal scroll with spring
            self._target_pos = max(0.0, min(1.0, current - scroll_amount))
            self._velocity = 0.0

        self._start_animation()

    def stop(self) -> None:
        """Stop any ongoing animation."""
        self._is_animating = False
        if self._anim_id is not None:
            try:
                self.canvas.after_cancel(self._anim_id)
            except Exception:  # noqa: BLE001
                pass
            self._anim_id = None


def _normalize_delta(event: Any, is_mac: bool, is_windows: bool) -> tuple[float, bool]:
    """
    Normalize wheel delta across platforms.

    Returns:
        (normalized_delta, is_fling)
        - normalized_delta: ~1.0 per "notch" equivalent
        - is_fling: True if this looks like a trackpad fling (high velocity)
    """
    try:
        # Linux scroll events (Button-4/Button-5)
        if getattr(event, "num", None) in (4, 5):
            return (1.0 if event.num == 4 else -1.0, False)

        # Windows/macOS MouseWheel events
        delta = getattr(event, "delta", None)
        if delta is None:
            return (0.0, False)

        # Detect high-precision trackpad (small deltas, high frequency)
        # Trackpads often send deltas of ±1-10 instead of ±120
        abs_delta = abs(delta)

        if is_mac:
            # Mac trackpad: very small deltas (±1-3 for normal, ±4-50 for flings)
            # Trackpad flings have larger initial delta but still < mouse wheel
            if abs_delta <= 3:
                # High-precision trackpad: treat as continuous scroll
                return (delta / 3.0, abs_delta > 2)
            elif abs_delta <= 50:
                # Trackpad fling or fast scroll: more aggressive, with momentum
                return (delta / 10.0, True)
            else:
                # Standard mouse wheel
                return (delta / 120.0, False)

        elif is_windows:
            # Windows: standard mouse ±120, precision trackpad ±1-50
            # High-precision trackpads (Surface, Dell, etc.) send small deltas
            if abs_delta < 50:
                # High-precision trackpad or touchpad
                return (delta / 10.0, abs_delta > 30)  # Fling if > 30
            else:
                # Standard mouse wheel
                return (delta / 120.0, False)

        else:
            # Linux/other: assume standard
            return (delta / 120.0, False)

    except Exception:  # noqa: BLE001
        return (0.0, False)


def apply_smooth_scroll(
    scrollable: ctk.CTkScrollableFrame,
    *,
    step: int = 60,
    animate: bool = True,
    momentum: bool = True,
    horizontal: bool = False,
) -> SmoothScroller | None:
    """
    Attach a smooth, consistent mousewheel/trackpad scroller over a scrollable frame.

    Args:
        scrollable: CTkScrollableFrame with _parent_canvas and _parent_scrollbar
        step: Base scroll step size (for non-animated fallback)
        animate: Enable smooth animated scrolling
        momentum: Enable momentum/inertia scrolling for trackpad flings
        horizontal: Enable horizontal scrolling (for Shift+wheel or 2-finger horizontal)

    Returns:
        SmoothScroller instance for advanced control, or None if failed.
    """
    if scrollable is None:
        return None
    try:
        canvas = getattr(scrollable, "_parent_canvas", None)
        if canvas is None:
            return None
    except Exception:  # noqa: BLE001
        return None

    scroller = SmoothScroller(canvas, step=step, animate=animate, momentum=momentum, horizontal=horizontal)

    is_mac = sys.platform == "darwin"
    is_windows = sys.platform == "win32"

    def _on_wheel(event: Any) -> str | None:
        # Let multi-line text inputs scroll natively
        try:
            w = getattr(event, "widget", None)
            if w is not None and isinstance(w, ctk.CTkTextbox):
                return None
        except Exception:  # noqa: BLE001
            return None

        # Check for horizontal scroll modifiers
        try:
            state = int(getattr(event, "state", 0) or 0)
            shift_pressed = bool(state & 0x0001)  # Shift key
            ctrl_pressed = bool(state & 0x0004)   # Ctrl/Command key
        except Exception:  # noqa: BLE001
            shift_pressed = False
            ctrl_pressed = False

        # Determine scroll direction
        is_horizontal_scroll = horizontal and (shift_pressed or ctrl_pressed)

        # Check if canvas can scroll in the requested direction
        if is_horizontal_scroll:
            if not _can_scroll_x(canvas):
                return "break"
        else:
            if not _can_scroll(canvas):
                return "break"

        # Normalize delta
        delta, is_fling = _normalize_delta(event, is_mac, is_windows)

        if delta == 0:
            return None

        # For horizontal scroll, we'd need a separate horizontal scroller
        # For now, just handle vertical
        if not is_horizontal_scroll:
            scroller.scroll_by_delta(delta, is_fling=is_fling)
        else:
            # Horizontal scroll fallback (direct, no animation for simplicity)
            try:
                units = int(delta * (step / 30.0))
                if units == 0:
                    units = 1 if delta > 0 else -1
                canvas.xview_scroll(-units, "units")
            except Exception:  # noqa: BLE001
                pass

        return "break"

    # Bind to scrollable frame and all descendants
    try:
        for t in _walk(scrollable):
            try:
                t.bind("<MouseWheel>", _on_wheel, add="+")
            except Exception:  # noqa: BLE001
                pass
            for seq in ("<Button-4>", "<Button-5>"):
                try:
                    t.bind(seq, _on_wheel, add="+")
                except Exception:  # noqa: BLE001
                    pass

        # Store reference for cleanup
        setattr(scrollable, "_smooth_scroller", scroller)
        setattr(scrollable, "_smooth_wheel_handler", _on_wheel)

    except Exception:  # noqa: BLE001
        pass

    return scroller


def bind_smooth_text_wheel(
    textbox: Any,
    *,
    on_edge: Callable[[Any], str | None] | None = None,
    step: int = 40,
) -> SmoothScroller | None:
    """
    Smooth-scroll a CTkTextbox / tk.Text when the pointer is over it.
    At the top or bottom, call on_edge so the parent chat list can keep moving.
    """
    if textbox is None:
        return None
    try:
        inner = getattr(textbox, "_textbox", textbox)
    except Exception:  # noqa: BLE001
        inner = textbox
    if inner is None:
        return None

    scroller = SmoothScroller(inner, step=step, animate=True, momentum=True)
    is_mac = sys.platform == "darwin"
    is_windows = sys.platform == "win32"

    def _can_move(delta: float) -> bool:
        try:
            first, last = inner.yview()
            first_f = float(first)
            last_f = float(last)
        except Exception:  # noqa: BLE001
            return False
        # Positive delta = wheel up = earlier text
        if delta > 0:
            return first_f > 0.002
        return last_f < 0.998

    def _on_wheel(event: Any) -> str | None:
        delta, is_fling = _normalize_delta(event, is_mac, is_windows)
        if delta == 0:
            num = getattr(event, "num", None)
            if num == 4:
                delta = 1.0
            elif num == 5:
                delta = -1.0
        if delta == 0:
            return None
        if not _can_move(delta):
            if on_edge is not None:
                return on_edge(event)
            return None
        scroller.scroll_by_delta(delta, is_fling=is_fling)
        return "break"

    for w in (textbox, inner):
        try:
            w.bind("<MouseWheel>", _on_wheel)
            w.bind("<Button-4>", _on_wheel)
            w.bind("<Button-5>", _on_wheel)
        except Exception:  # noqa: BLE001
            pass
    try:
        setattr(textbox, "_own_smooth_scroll", True)
        setattr(textbox, "_smooth_scroller", scroller)
        setattr(inner, "_own_smooth_scroll", True)
    except Exception:  # noqa: BLE001
        pass
    return scroller


def remove_smooth_scroll(scrollable: ctk.CTkScrollableFrame) -> None:
    """Remove smooth scroll bindings from a scrollable frame and its descendants."""
    try:
        handler = getattr(scrollable, "_smooth_wheel_handler", None)
        scroller = getattr(scrollable, "_smooth_scroller", None)

        if scroller:
            scroller.stop()

        if handler:
            for t in _walk(scrollable):
                try:
                    t.unbind("<MouseWheel>", handler)
                except Exception:  # noqa: BLE001
                    pass
                for seq in ("<Button-4>", "<Button-5>"):
                    try:
                        t.unbind(seq, handler)
                    except Exception:  # noqa: BLE001
                        pass

        # Clean up attributes
        if hasattr(scrollable, "_smooth_scroller"):
            delattr(scrollable, "_smooth_scroller")
        if hasattr(scrollable, "_smooth_wheel_handler"):
            delattr(scrollable, "_smooth_wheel_handler")

    except Exception:  # noqa: BLE001
        pass