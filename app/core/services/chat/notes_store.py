"""Notes workspace — persist, search, attach-to-chat, optional AI rewrite (P1.1).

Ideas from Open WebUI notes (title + markdown body, attach into chat context)
reimplemented cleanly for Studio CustomTkinter — no GPL blobs.

Storage: one JSON file per note under ``data/notes/<id>.json``.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.paths import notes_dir
from app.core.services.data.storage import _read_json, _write_json

DEFAULT_MAX_CHARS_PER_NOTE = 24_000
DEFAULT_MAX_TOTAL_ATTACH = 60_000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_id(note_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "", (note_id or "").strip())[:80]


def _note_path(note_id: str) -> Path:
    sid = _safe_id(note_id)
    if not sid:
        raise ValueError("invalid note id")
    return notes_dir() / f"{sid}.json"


def _normalize(note: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(note.get("id") or ""),
        "title": str(note.get("title") or "Untitled").strip() or "Untitled",
        "body": str(note.get("body") or ""),
        "created_at": str(note.get("created_at") or ""),
        "updated_at": str(note.get("updated_at") or ""),
    }


def list_notes(*, query: str = "") -> list[dict[str, Any]]:
    """List notes newest-first; optional case-insensitive title/body search."""
    items: list[dict[str, Any]] = []
    root = notes_dir()
    for p in root.glob("*.json"):
        if p.name.endswith(".tmp"):
            continue
        data = _read_json(p, None)
        if isinstance(data, dict) and data.get("id"):
            items.append(_normalize(data))
    items.sort(key=lambda n: n.get("updated_at") or "", reverse=True)
    q = (query or "").strip().lower()
    if not q:
        return items
    words = [w for w in re.split(r"\s+", q) if w]
    out: list[dict[str, Any]] = []
    for n in items:
        hay = f"{n.get('title', '')}\n{n.get('body', '')}".lower()
        # AND semantics across words (OWUI-like)
        if all(w in hay for w in words):
            out.append(n)
    return out


def get_note(note_id: str) -> dict[str, Any] | None:
    try:
        path = _note_path(note_id)
    except ValueError:
        return None
    data = _read_json(path, None)
    if isinstance(data, dict) and data.get("id"):
        return _normalize(data)
    return None


def create_note(*, title: str = "Untitled", body: str = "") -> dict[str, Any]:
    nid = str(uuid.uuid4())
    now = _now()
    note = {
        "id": nid,
        "title": (title or "Untitled").strip() or "Untitled",
        "body": body or "",
        "created_at": now,
        "updated_at": now,
    }
    _write_json(_note_path(nid), note)
    return _normalize(note)


def update_note(
    note_id: str,
    *,
    title: str | None = None,
    body: str | None = None,
) -> dict[str, Any] | None:
    note = get_note(note_id)
    if not note:
        return None
    if title is not None:
        note["title"] = (title or "").strip() or "Untitled"
    if body is not None:
        note["body"] = body
    note["updated_at"] = _now()
    _write_json(_note_path(note["id"]), note)
    return _normalize(note)


def delete_note(note_id: str) -> bool:
    try:
        path = _note_path(note_id)
    except ValueError:
        return False
    if not path.exists():
        return False
    try:
        path.unlink()
        return True
    except OSError:
        return False


def search_notes(query: str) -> list[dict[str, Any]]:
    return list_notes(query=query)


def preview_text(note: dict[str, Any], *, limit: int = 120) -> str:
    body = re.sub(r"\s+", " ", (note.get("body") or "").strip())
    if len(body) <= limit:
        return body
    return body[: limit - 1] + "…"


def build_attach_context_block(
    note_ids: list[str] | None,
    *,
    max_chars_per: int = DEFAULT_MAX_CHARS_PER_NOTE,
    max_total: int = DEFAULT_MAX_TOTAL_ATTACH,
) -> tuple[str, list[dict[str, Any]]]:
    """Build a system-context block for attached notes (full-context inject).

    Soft-degrades missing ids with a clear note; never raises.
    Returns (block_text, resolution_list).
    """
    ids = [str(i).strip() for i in (note_ids or []) if str(i).strip()]
    if not ids:
        return "", []

    # de-dupe preserve order
    seen: set[str] = set()
    ordered: list[str] = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            ordered.append(i)

    results: list[dict[str, Any]] = []
    parts: list[str] = []
    total = 0
    for nid in ordered:
        note = get_note(nid)
        if not note:
            results.append(
                {
                    "id": nid,
                    "ok": False,
                    "title": "",
                    "note": "Note not found (soft-degrade)",
                }
            )
            parts.append(f"### Note `{nid}`\n_(unresolved — note missing)_")
            continue
        title = note.get("title") or "Untitled"
        body = note.get("body") or ""
        truncated = False
        if len(body) > max_chars_per:
            body = body[:max_chars_per] + "\n…[truncated]"
            truncated = True
        chunk = f"### Note: {title}\n(id: {note['id']})\n\n{body}"
        if total + len(chunk) > max_total and parts:
            results.append(
                {
                    "id": note["id"],
                    "ok": True,
                    "title": title,
                    "truncated": True,
                    "note": "Skipped — attach budget exhausted",
                }
            )
            parts.append(
                f"### Note: {title}\n_(skipped — context budget; detach others or shorten)_"
            )
            continue
        total += len(chunk)
        results.append(
            {
                "id": note["id"],
                "ok": True,
                "title": title,
                "truncated": truncated,
                "chars": len(body),
            }
        )
        parts.append(chunk)

    header = (
        "## Attached notes (full context for this turn)\n"
        "The user attached the following note(s). Treat them as primary context "
        "for the request. Prefer facts from these notes when answering.\n"
    )
    block = header + "\n\n".join(parts)
    return block, results


def rewrite_text(
    selected: str,
    *,
    instruction: str = "Rewrite clearly and concisely. Keep meaning. Return only the rewritten text.",
    chat_completion_fn: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Optional AI rewrite of selected note text. Soft-degrades if no API key.

    Returns ``{ok, text, note}``. On soft-degrade, ``ok=False`` and original text
    is echoed in ``text`` so the UI can leave selection unchanged.
    """
    text = (selected or "").strip()
    if not text:
        return {"ok": False, "text": "", "note": "Nothing selected to rewrite"}

    try:
        from app.core.services.data.storage import load_config
        from app.core.services.llm.providers import resolve_active_llm
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "text": text, "note": f"LLM unavailable: {e}"}

    try:
        active = resolve_active_llm()
    except Exception:  # noqa: BLE001
        cfg = load_config()
        active = {
            "api_key": cfg.get("api_key") or "",
            "base_url": cfg.get("api_base_url") or "https://api.openai.com/v1",
            "model": cfg.get("model") or "gpt-4o-mini",
        }

    api_key = (active.get("api_key") or "").strip()
    if not api_key:
        return {
            "ok": False,
            "text": text,
            "note": "No API key — rewrite soft-degraded (add a key in Settings → Providers)",
        }

    fn = chat_completion_fn
    if fn is None:
        from app.core.services.llm.llm import chat_completion as fn  # type: ignore

    messages = [
        {
            "role": "system",
            "content": (
                "You are a careful writing assistant. Follow the user instruction. "
                "Return only the rewritten text — no preamble, no quotes wrapper."
            ),
        },
        {
            "role": "user",
            "content": f"Instruction: {instruction.strip()}\n\nText:\n{text}",
        },
    ]
    try:
        out = fn(
            api_key=api_key,
            messages=messages,
            model=str(active.get("model") or "gpt-4o-mini"),
            base_url=str(active.get("base_url") or "https://api.openai.com/v1"),
            timeout=45.0,
            temperature=0.4,
            max_tokens=min(4000, max(256, len(text) // 2 + 400)),
        )
        if isinstance(out, tuple):
            rewritten = str(out[0] or "").strip()
        else:
            rewritten = str(out or "").strip()
        if not rewritten:
            return {"ok": False, "text": text, "note": "Empty rewrite from model"}
        return {"ok": True, "text": rewritten, "note": "Rewritten"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "text": text, "note": f"Rewrite failed (soft-degrade): {e}"}
