"""OWUI-inspired message queue while streaming (P1.4).

While the assistant is generating / streaming / tool-running, composer Send
enqueues the follow-up instead of blocking. On turn idle, dequeue FIFO and
auto-send the next item.

Stop behavior (documented choice):
  STOP_CLEARS_QUEUE = False
  ■ Stop cancels the active run but **keeps** the queue. User clears queue
  explicitly (× on a chip or Clear queue). After the run becomes idle,
  the next queued item auto-sends.

Ideas from Open WebUI `chatRequestQueues` / QueuedMessageItem — clean Studio
reimplementation (no GPL blobs). Studio uses true FIFO one-at-a-time (not
OWUI's combine-all-prompts-into-one).
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any

# Documented product choice — Stop cancels run, does not wipe queue.
STOP_CLEARS_QUEUE = False

# Soft cap so a runaway loop cannot grow forever
MAX_QUEUE_PER_CHAT = 50

_lock = threading.RLock()
# chat_id -> list of queue items (FIFO)
_queues: dict[str, list[dict[str, Any]]] = {}


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _norm_chat_id(chat_id: str | None) -> str:
    return str(chat_id or "").strip() or "default"


def enqueue(
    chat_id: str | None,
    text: str,
    *,
    attachments: list[str] | None = None,
    notes: list[str] | None = None,
    images: list[str] | None = None,
    videos: list[str] | None = None,
    source: str = "composer",
) -> dict[str, Any] | None:
    """Append a follow-up to the chat's FIFO queue. Returns the item or None if empty/capped."""
    body = (text or "").strip()
    atts = [str(p) for p in (attachments or []) if p]
    note_ids = [str(n) for n in (notes or []) if n]
    imgs = [str(p) for p in (images or []) if p]
    vids = [str(p) for p in (videos or []) if p]
    if not body and not atts and not note_ids and not imgs and not vids:
        return None
    cid = _norm_chat_id(chat_id)
    item = {
        "id": _new_id(),
        "text": body,
        "attachments": atts,
        "notes": note_ids,
        "images": imgs,
        "videos": vids,
        "source": str(source or "composer"),
        "created_at": time.time(),
    }
    with _lock:
        q = _queues.setdefault(cid, [])
        if len(q) >= MAX_QUEUE_PER_CHAT:
            return None
        q.append(item)
        return dict(item)


def list_queued(chat_id: str | None) -> list[dict[str, Any]]:
    """Return a shallow copy of the FIFO list for this chat."""
    cid = _norm_chat_id(chat_id)
    with _lock:
        return [dict(x) for x in (_queues.get(cid) or [])]


def peek(chat_id: str | None) -> dict[str, Any] | None:
    with _lock:
        q = _queues.get(_norm_chat_id(chat_id)) or []
        return dict(q[0]) if q else None


def count(chat_id: str | None) -> int:
    with _lock:
        return len(_queues.get(_norm_chat_id(chat_id)) or [])


def dequeue(chat_id: str | None) -> dict[str, Any] | None:
    """Pop and return the next FIFO item, or None if empty."""
    cid = _norm_chat_id(chat_id)
    with _lock:
        q = _queues.get(cid) or []
        if not q:
            return None
        item = q.pop(0)
        if not q:
            _queues.pop(cid, None)
        return dict(item)


def remove(chat_id: str | None, item_id: str) -> bool:
    """Remove one queued item by id. Returns True if found."""
    cid = _norm_chat_id(chat_id)
    iid = str(item_id or "")
    if not iid:
        return False
    with _lock:
        q = _queues.get(cid) or []
        for i, it in enumerate(q):
            if it.get("id") == iid:
                q.pop(i)
                if not q:
                    _queues.pop(cid, None)
                return True
        return False


def clear(chat_id: str | None) -> int:
    """Clear all queued items for a chat. Returns how many were removed."""
    cid = _norm_chat_id(chat_id)
    with _lock:
        q = _queues.pop(cid, None) or []
        return len(q)


def clear_all() -> None:
    """Reset every chat queue (tests / shutdown)."""
    with _lock:
        _queues.clear()


def reorder(chat_id: str | None, ordered_ids: list[str]) -> bool:
    """Optional: reorder queue to match ordered_ids (unknown ids dropped to end)."""
    cid = _norm_chat_id(chat_id)
    with _lock:
        q = list(_queues.get(cid) or [])
        if not q:
            return False
        by_id = {str(it.get("id")): it for it in q}
        seen: set[str] = set()
        new_q: list[dict[str, Any]] = []
        for oid in ordered_ids or []:
            oid = str(oid)
            if oid in by_id and oid not in seen:
                new_q.append(by_id[oid])
                seen.add(oid)
        for it in q:
            iid = str(it.get("id"))
            if iid not in seen:
                new_q.append(it)
        _queues[cid] = new_q
        return True


def preview_label(item: dict[str, Any], *, max_len: int = 40) -> str:
    """Short chip label for UI."""
    t = str((item or {}).get("text") or "").strip().replace("\n", " ")
    if t:
        return (t[: max_len - 1] + "…") if len(t) > max_len else t
    n_att = len((item or {}).get("attachments") or [])
    n_notes = len((item or {}).get("notes") or [])
    bits = []
    if n_notes:
        bits.append(f"{n_notes} note(s)")
    if n_att:
        bits.append(f"{n_att} file(s)")
    return ", ".join(bits) if bits else "(empty)"


def should_clear_queue_on_stop() -> bool:
    """Product policy accessor — Stop keeps the queue unless this returns True."""
    return bool(STOP_CLEARS_QUEUE)
