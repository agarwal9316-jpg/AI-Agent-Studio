"""P1.4 — Message queue while streaming.

FIFO enqueue/dequeue, remove/clear, Stop keeps queue, soft-cap.
No GPL OWUI blobs — Studio reimplementation.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.services.chat import msg_queue as mq  # noqa: E402


def setup_function(_fn=None):
    mq.clear_all()


def teardown_function(_fn=None):
    mq.clear_all()


def test_fifo_enqueue_dequeue():
    mq.clear_all()
    a = mq.enqueue("c1", "first")
    b = mq.enqueue("c1", "second")
    c = mq.enqueue("c1", "third")
    assert a and b and c
    assert mq.count("c1") == 3
    assert mq.peek("c1")["text"] == "first"
    assert mq.dequeue("c1")["text"] == "first"
    assert mq.dequeue("c1")["text"] == "second"
    assert mq.dequeue("c1")["text"] == "third"
    assert mq.dequeue("c1") is None
    assert mq.count("c1") == 0
    print("✓ FIFO enqueue/dequeue")


def test_per_chat_isolation():
    mq.clear_all()
    mq.enqueue("chat-a", "A1")
    mq.enqueue("chat-b", "B1")
    mq.enqueue("chat-a", "A2")
    assert [x["text"] for x in mq.list_queued("chat-a")] == ["A1", "A2"]
    assert [x["text"] for x in mq.list_queued("chat-b")] == ["B1"]
    mq.dequeue("chat-a")
    assert mq.peek("chat-a")["text"] == "A2"
    assert mq.peek("chat-b")["text"] == "B1"
    print("✓ per-chat isolation")


def test_remove_and_clear():
    mq.clear_all()
    a = mq.enqueue("c", "keep-me")
    b = mq.enqueue("c", "drop-me")
    c = mq.enqueue("c", "also-keep")
    assert mq.remove("c", b["id"]) is True
    assert mq.remove("c", "missing") is False
    assert [x["text"] for x in mq.list_queued("c")] == ["keep-me", "also-keep"]
    n = mq.clear("c")
    assert n == 2
    assert mq.list_queued("c") == []
    assert a and c
    print("✓ remove + clear")


def test_empty_rejected_and_soft_cap():
    mq.clear_all()
    assert mq.enqueue("c", "   ") is None
    assert mq.enqueue("c", "", attachments=[]) is None
    assert mq.enqueue("c", "", notes=["nid1"]) is not None
    # soft-cap
    mq.clear("c")
    for i in range(mq.MAX_QUEUE_PER_CHAT):
        assert mq.enqueue("c", f"m{i}") is not None
    assert mq.enqueue("c", "overflow") is None
    assert mq.count("c") == mq.MAX_QUEUE_PER_CHAT
    print("✓ empty reject + soft-cap")


def test_stop_keeps_queue_policy():
    """Documented choice: Stop cancels run but keeps queue."""
    mq.clear_all()
    assert mq.STOP_CLEARS_QUEUE is False
    assert mq.should_clear_queue_on_stop() is False
    mq.enqueue("c", "still here after stop")
    # Simulate Stop path: do NOT clear unless policy says so
    if mq.should_clear_queue_on_stop():
        mq.clear("c")
    assert mq.count("c") == 1
    assert mq.peek("c")["text"] == "still here after stop"
    print("✓ Stop keeps queue (policy)")


def test_reorder_optional():
    mq.clear_all()
    a = mq.enqueue("c", "a")
    b = mq.enqueue("c", "b")
    c = mq.enqueue("c", "c")
    assert mq.reorder("c", [c["id"], a["id"], b["id"]]) is True
    assert [x["text"] for x in mq.list_queued("c")] == ["c", "a", "b"]
    print("✓ optional reorder")


def test_preview_label():
    assert "hello" in mq.preview_label({"text": "hello world"})
    long = mq.preview_label({"text": "x" * 80}, max_len=20)
    assert len(long) <= 20 and long.endswith("…")
    assert "note" in mq.preview_label({"text": "", "notes": ["n1"]}).lower()
    print("✓ preview_label")


def test_attachments_roundtrip():
    mq.clear_all()
    it = mq.enqueue(
        "c",
        "with files",
        attachments=["/tmp/a.txt"],
        notes=["note-1"],
        images=["/tmp/i.png"],
        source="voice",
    )
    assert it["attachments"] == ["/tmp/a.txt"]
    assert it["notes"] == ["note-1"]
    assert it["images"] == ["/tmp/i.png"]
    assert it["source"] == "voice"
    got = mq.dequeue("c")
    assert got["text"] == "with files"
    assert got["attachments"] == ["/tmp/a.txt"]
    print("✓ attachments roundtrip")


if __name__ == "__main__":
    test_fifo_enqueue_dequeue()
    test_per_chat_isolation()
    test_remove_and_clear()
    test_empty_rejected_and_soft_cap()
    test_stop_keeps_queue_policy()
    test_reorder_optional()
    test_preview_label()
    test_attachments_roundtrip()
    print("\nAll P1.4 msgqueue tests passed.")
