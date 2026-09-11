"""Roadmap — Virtualized long chat history (1.27.97).

Window math / load older-newer / soft-degrade / jump latest — unit-tested.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.version import __version__  # noqa: E402
from app.core.services.chat import virt_chat as vc  # noqa: E402


def test_version():
    assert __version__ == "1.27.97", __version__
    print("✓ version 1.27.97")


def test_soft_degrade_short_chat():
    assert vc.soft_degrade(0) is True
    assert vc.soft_degrade(1) is True
    assert vc.soft_degrade(vc.DEFAULT_WINDOW) is True
    assert vc.soft_degrade(vc.DEFAULT_WINDOW + 1) is False
    start, end = vc.jump_latest(30)
    assert (start, end) == (0, 30)
    start, end = vc.show_from_start(30)
    assert (start, end) == (0, 30)
    assert vc.needs_load_chrome(0, 30, 30) is False
    print("✓ soft-degrade short chat (no behavior change)")


def test_jump_latest_end_aligned():
    start, end = vc.jump_latest(500)
    assert end == 500
    assert start == 500 - vc.DEFAULT_WINDOW
    assert vc.window_size(start, end) == vc.DEFAULT_WINDOW
    assert vc.older_count(start) == 450
    assert vc.newer_count(end, 500) == 0
    print("✓ jump_latest end-aligned")


def test_load_older_grows_then_slides():
    # Start at latest window
    s, e = vc.jump_latest(500)
    s2, e2, changed = vc.load_older(s, e, 500, step=40)
    assert changed is True
    assert s2 == s - 40
    assert e2 == e  # still room under MAX — grows upward
    assert vc.window_size(s2, e2) == vc.DEFAULT_WINDOW + 40

    # Keep loading until at max, then must slide (drop newer)
    s, e = s2, e2
    while vc.window_size(s, e) < vc.MAX_WINDOW and s > 0:
        s, e, _ = vc.load_older(s, e, 500, step=40)
    assert vc.window_size(s, e) <= vc.MAX_WINDOW
    before = (s, e)
    s3, e3, changed = vc.load_older(s, e, 500, step=40)
    assert changed is True
    assert s3 < before[0]
    assert e3 < before[1]  # slid: dropped newer side
    assert vc.window_size(s3, e3) == vc.MAX_WINDOW
    print("✓ load_older grows then slides at MAX_WINDOW")


def test_load_older_at_start_noop():
    s, e, changed = vc.load_older(0, 50, 500)
    assert changed is False
    assert (s, e) == (0, 50)
    print("✓ load_older at start is noop")


def test_load_newer_slides_toward_end():
    # Window parked in the middle (from start, then not at end)
    s, e = vc.show_from_start(500)  # 0..MAX
    assert s == 0
    assert e == vc.MAX_WINDOW
    s2, e2, changed = vc.load_newer(s, e, 500, step=40)
    assert changed is True
    assert e2 == e + 40
    assert s2 == s + 40  # slid — dropped older
    assert vc.window_size(s2, e2) == vc.MAX_WINDOW
    assert vc.older_count(s2) == 40
    assert vc.newer_count(e2, 500) == 500 - e2
    print("✓ load_newer slides toward end")


def test_load_newer_at_end_noop():
    s, e = vc.jump_latest(200)
    s2, e2, changed = vc.load_newer(s, e, 200)
    assert changed is False
    assert (s2, e2) == (s, e)
    print("✓ load_newer at end is noop")


def test_show_from_start_capped():
    s, e = vc.show_from_start(10_000)
    assert s == 0
    assert e == vc.MAX_WINDOW
    assert vc.needs_load_chrome(s, e, 10_000) is True
    print("✓ show_from_start capped at MAX_WINDOW")


def test_busy_tail():
    s, e = vc.busy_tail(500)
    assert e == 500
    assert s == 500 - vc.BUSY_WINDOW
    s0, e0 = vc.busy_tail(10)
    assert (s0, e0) == (0, 10)
    print("✓ busy_tail light window")


def test_clamp_and_ensure():
    assert vc.clamp_window(-10, 999, 100) == (0, 100)
    s, e = vc.clamp_window(-5, 300, 100, max_window=50)
    assert 0 <= s <= e <= 100
    assert e - s <= 50
    s, e = vc.ensure_window(None, None, 400)
    assert (s, e) == vc.jump_latest(400)
    s, e = vc.ensure_window(10, 60, 400)
    assert (s, e) == (10, 60)
    print("✓ clamp_window + ensure_window")


def test_slice_and_status():
    msgs = [{"i": i} for i in range(100)]
    s, e = vc.jump_latest(100)
    out = vc.slice_messages(msgs, s, e)
    assert len(out) == vc.DEFAULT_WINDOW
    assert out[0]["i"] == s
    assert out[-1]["i"] == e - 1
    label = vc.status_label(s, e, 100)
    assert "of 100" in label
    assert "older" in label
    print("✓ slice_messages + status_label")


def test_constants_match_features_copy():
    # FEATURES: Last 50 · Load older (+40) · sliding max
    assert vc.DEFAULT_WINDOW == 50
    assert vc.LOAD_STEP == 40
    assert vc.MAX_WINDOW == 200
    assert vc.BUSY_WINDOW == 36
    print("✓ constants match FEATURES (50 / +40 / max 200)")


if __name__ == "__main__":
    test_version()
    test_soft_degrade_short_chat()
    test_jump_latest_end_aligned()
    test_load_older_grows_then_slides()
    test_load_older_at_start_noop()
    test_load_newer_slides_toward_end()
    test_load_newer_at_end_noop()
    test_show_from_start_capped()
    test_busy_tail()
    test_clamp_and_ensure()
    test_slice_and_status()
    test_constants_match_features_copy()
    print("\nAll virt_chat tests passed.")
