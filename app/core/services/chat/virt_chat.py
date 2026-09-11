"""Virtualized long chat history — sliding window math (roadmap 1.27.97).

Keeps a bounded painted range over stored messages so very long chats stay
smooth. Soft-degrades for short chats (paint everything, no Load chrome).

Stream tokens already update one live bubble in place (app_window); this
module only owns window start/end math so the UI never needs to rebuild the
full transcript on every tick.
"""

from __future__ import annotations

from typing import Any

# Align with docs/FEATURES.md: Last 50 · Load older (+40)
DEFAULT_WINDOW = 50
LOAD_STEP = 40
# Hard cap of painted message rows (sliding — older drops newer and vice versa)
MAX_WINDOW = 200
# While streaming / tools busy: paint a light tail only
BUSY_WINDOW = 36


def soft_degrade(total: int, *, default_window: int = DEFAULT_WINDOW) -> bool:
    """True when the chat is short enough that virtualization is a no-op."""
    t = max(0, int(total or 0))
    return t <= max(1, int(default_window or DEFAULT_WINDOW))


def clamp_window(
    start: int,
    end: int,
    total: int,
    *,
    max_window: int = MAX_WINDOW,
) -> tuple[int, int]:
    """Clamp [start, end) into [0, total] and enforce max_window width."""
    t = max(0, int(total or 0))
    if t == 0:
        return 0, 0
    mw = max(1, int(max_window or MAX_WINDOW))
    s = max(0, min(t, int(start or 0)))
    e = max(0, min(t, int(end or 0)))
    if e < s:
        e = s
    if e - s > mw:
        # Prefer keeping the end anchored (newer side) when over-wide
        s = e - mw
    if e - s > mw:
        e = s + mw
    if e > t:
        e = t
        s = max(0, e - mw)
    if s < 0:
        s = 0
    return s, e


def jump_latest(
    total: int,
    *,
    window: int = DEFAULT_WINDOW,
    max_window: int = MAX_WINDOW,
) -> tuple[int, int]:
    """End-aligned window (default view / ↓ Latest)."""
    t = max(0, int(total or 0))
    if t == 0:
        return 0, 0
    if soft_degrade(t):
        return 0, t
    w = max(1, min(int(window or DEFAULT_WINDOW), int(max_window or MAX_WINDOW)))
    w = min(w, t)
    return t - w, t


def show_from_start(
    total: int,
    *,
    max_window: int = MAX_WINDOW,
) -> tuple[int, int]:
    """Start-aligned window (From start) — capped, not full O(n) paint."""
    t = max(0, int(total or 0))
    if t == 0:
        return 0, 0
    if soft_degrade(t):
        return 0, t
    mw = max(1, int(max_window or MAX_WINDOW))
    return 0, min(t, mw)


def busy_tail(
    total: int,
    *,
    busy_window: int = BUSY_WINDOW,
) -> tuple[int, int]:
    """Light tail while streaming — does not mutate persisted virt state."""
    t = max(0, int(total or 0))
    if t == 0:
        return 0, 0
    w = max(1, int(busy_window or BUSY_WINDOW))
    w = min(w, t)
    return t - w, t


def load_older(
    start: int,
    end: int,
    total: int,
    *,
    step: int = LOAD_STEP,
    max_window: int = MAX_WINDOW,
) -> tuple[int, int, bool]:
    """
    Reveal `step` older messages above the current window.

    If the window would exceed max_window, slide: drop the same count from the
    newer side so paint cost stays bounded.
    Returns (start, end, changed).
    """
    t = max(0, int(total or 0))
    s, e = clamp_window(start, end, t, max_window=max_window)
    if t == 0 or s <= 0:
        return s, e, False
    st = max(1, int(step or LOAD_STEP))
    mw = max(1, int(max_window or MAX_WINDOW))
    new_s = max(0, s - st)
    grown = s - new_s
    new_e = e
    if (new_e - new_s) > mw:
        new_e = new_s + mw
    new_s, new_e = clamp_window(new_s, new_e, t, max_window=mw)
    changed = (new_s, new_e) != (s, e)
    return new_s, new_e, changed


def load_newer(
    start: int,
    end: int,
    total: int,
    *,
    step: int = LOAD_STEP,
    max_window: int = MAX_WINDOW,
) -> tuple[int, int, bool]:
    """Reveal `step` newer messages below the current window (slide if needed)."""
    t = max(0, int(total or 0))
    s, e = clamp_window(start, end, t, max_window=max_window)
    if t == 0 or e >= t:
        return s, e, False
    st = max(1, int(step or LOAD_STEP))
    mw = max(1, int(max_window or MAX_WINDOW))
    new_e = min(t, e + st)
    grown = new_e - e
    new_s = s
    if (new_e - new_s) > mw:
        new_s = new_e - mw
    new_s, new_e = clamp_window(new_s, new_e, t, max_window=mw)
    changed = (new_s, new_e) != (s, e)
    return new_s, new_e, changed


def older_count(start: int) -> int:
    return max(0, int(start or 0))


def newer_count(end: int, total: int) -> int:
    return max(0, int(total or 0) - int(end or 0))


def window_size(start: int, end: int) -> int:
    return max(0, int(end or 0) - int(start or 0))


def needs_load_chrome(
    start: int,
    end: int,
    total: int,
    *,
    default_window: int = DEFAULT_WINDOW,
) -> bool:
    """Show Load older / newer bar only when virtualization is active."""
    t = max(0, int(total or 0))
    if soft_degrade(t, default_window=default_window):
        return False
    return older_count(start) > 0 or newer_count(end, t) > 0 or t > int(default_window or DEFAULT_WINDOW)


def slice_messages(messages: list[Any], start: int, end: int) -> list[Any]:
    """Safe slice of stored messages for the painted window."""
    if not messages:
        return []
    t = len(messages)
    s, e = clamp_window(start, end, t)
    return list(messages[s:e])


def ensure_window(
    start: int | None,
    end: int | None,
    total: int,
    *,
    default_window: int = DEFAULT_WINDOW,
    max_window: int = MAX_WINDOW,
) -> tuple[int, int]:
    """Initialize or clamp a window; None → jump_latest."""
    t = max(0, int(total or 0))
    if start is None or end is None:
        return jump_latest(t, window=default_window, max_window=max_window)
    return clamp_window(int(start), int(end), t, max_window=max_window)


def status_label(start: int, end: int, total: int) -> str:
    """Human status for the load bar / toast."""
    t = max(0, int(total or 0))
    s, e = clamp_window(start, end, t)
    if t == 0:
        return "No messages"
    if soft_degrade(t):
        return f"Showing all {t} messages"
    older = older_count(s)
    newer = newer_count(e, t)
    base = f"Showing {s + 1}–{e} of {t}"
    bits = []
    if older:
        bits.append(f"{older} older")
    if newer:
        bits.append(f"{newer} newer")
    if bits:
        return f"{base} ({', '.join(bits)})"
    return base
