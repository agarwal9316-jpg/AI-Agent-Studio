"""Workspace Channels — shared timeline for user + AI models (P1.2).

Ideas from Open WebUI channels (timeline, @model mentions, pins, thread replies)
reimplemented cleanly for Studio CustomTkinter — no GPL blobs.

Separate from Org **Team** goal channels (`team_channel` / `data/team_channels/`).
Storage: index + one JSON file per channel under ``data/channels/``.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.paths import channels_dir
from app.core.services.data.storage import _read_json, _write_json

MAX_CHANNEL_MESSAGES = 2_000
MAX_NAME_LEN = 80
MAX_CONTENT_LEN = 32_000

# @model mentions: @slug (letters, digits, . _ / : -) — Studio-simple, not OWUI XML tags
_MENTION_RE = re.compile(r"(?<!\w)@([A-Za-z0-9][A-Za-z0-9._/:+\-]{0,120})")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_id(cid: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "", (cid or "").strip())[:80]


def _index_path() -> Path:
    return channels_dir() / "index.json"


def _channel_path(channel_id: str) -> Path:
    sid = _safe_id(channel_id)
    if not sid:
        raise ValueError("invalid channel id")
    return channels_dir() / f"{sid}.json"


def _load_index() -> dict[str, Any]:
    data = _read_json(_index_path(), None)
    if isinstance(data, dict) and isinstance(data.get("channels"), list):
        return data
    return {"channels": [], "active_id": ""}


def _save_index(idx: dict[str, Any]) -> None:
    _write_json(_index_path(), idx)


def _normalize_message(m: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(m.get("id") or ""),
        "role": str(m.get("role") or "user"),
        "author": str(m.get("author") or ""),
        "model_id": str(m.get("model_id") or ""),
        "content": str(m.get("content") or ""),
        "at": str(m.get("at") or ""),
        "reply_to": m.get("reply_to") or None,
        "parent_id": m.get("parent_id") or None,
        "pinned": bool(m.get("pinned")),
        "mentions": list(m.get("mentions") or []),
        "meta": dict(m.get("meta") or {}) if isinstance(m.get("meta"), dict) else {},
    }


def _normalize_channel(ch: dict[str, Any]) -> dict[str, Any]:
    msgs = [_normalize_message(m) for m in (ch.get("messages") or []) if isinstance(m, dict)]
    return {
        "id": str(ch.get("id") or ""),
        "name": str(ch.get("name") or "channel").strip() or "channel",
        "description": str(ch.get("description") or ""),
        "created_at": str(ch.get("created_at") or ""),
        "updated_at": str(ch.get("updated_at") or ""),
        "messages": msgs,
        "message_count": len(msgs),
    }


def _summary(ch: dict[str, Any]) -> dict[str, Any]:
    msgs = ch.get("messages") or []
    last = msgs[-1] if msgs else None
    preview = ""
    if isinstance(last, dict):
        preview = re.sub(r"\s+", " ", str(last.get("content") or "").strip())[:100]
    return {
        "id": ch["id"],
        "name": ch.get("name") or "channel",
        "description": (ch.get("description") or "")[:200],
        "created_at": ch.get("created_at"),
        "updated_at": ch.get("updated_at"),
        "message_count": len(msgs),
        "last_preview": preview,
    }


def _upsert_index(ch: dict[str, Any], *, set_active: bool = True) -> None:
    idx = _load_index()
    summary = _summary(ch)
    channels = [c for c in (idx.get("channels") or []) if c.get("id") != ch["id"]]
    channels.insert(0, summary)
    channels.sort(key=lambda c: str(c.get("updated_at") or ""), reverse=True)
    idx["channels"] = channels[:200]
    if set_active:
        idx["active_id"] = ch["id"]
    _save_index(idx)


def list_channels(*, query: str = "") -> list[dict[str, Any]]:
    """Channel summaries newest-first; optional name/description filter."""
    idx = _load_index()
    items = list(idx.get("channels") or [])
    # Prefer live files if index empty / stale
    if not items:
        for p in channels_dir().glob("*.json"):
            if p.name in ("index.json",) or p.name.endswith(".tmp"):
                continue
            data = _read_json(p, None)
            if isinstance(data, dict) and data.get("id"):
                items.append(_summary(_normalize_channel(data)))
        items.sort(key=lambda c: str(c.get("updated_at") or ""), reverse=True)
    q = (query or "").strip().lower()
    if not q:
        return items
    words = [w for w in re.split(r"\s+", q) if w]
    out: list[dict[str, Any]] = []
    for c in items:
        hay = f"{c.get('name', '')}\n{c.get('description', '')}\n{c.get('last_preview', '')}".lower()
        if all(w in hay for w in words):
            out.append(c)
    return out


def get_active_channel_id() -> str:
    return str(_load_index().get("active_id") or "")


def set_active_channel_id(channel_id: str) -> None:
    idx = _load_index()
    idx["active_id"] = channel_id or ""
    _save_index(idx)


def get_channel(channel_id: str) -> dict[str, Any] | None:
    try:
        path = _channel_path(channel_id)
    except ValueError:
        return None
    data = _read_json(path, None)
    if isinstance(data, dict) and data.get("id"):
        return _normalize_channel(data)
    return None


def save_channel(ch: dict[str, Any], *, set_active: bool = True) -> dict[str, Any]:
    if not ch.get("id"):
        ch["id"] = str(uuid.uuid4())
    ch["updated_at"] = _now()
    if not ch.get("created_at"):
        ch["created_at"] = ch["updated_at"]
    # trim message history soft-cap
    msgs = list(ch.get("messages") or [])
    if len(msgs) > MAX_CHANNEL_MESSAGES:
        ch["messages"] = msgs[-MAX_CHANNEL_MESSAGES:]
    norm = _normalize_channel(ch)
    _write_json(_channel_path(norm["id"]), norm)
    _upsert_index(norm, set_active=set_active)
    return norm


def create_channel(*, name: str = "general", description: str = "") -> dict[str, Any]:
    nm = (name or "general").strip() or "general"
    nm = nm[:MAX_NAME_LEN]
    now = _now()
    ch: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "name": nm,
        "description": (description or "").strip()[:500],
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }
    append_message(
        ch,
        role="system",
        author="System",
        content=f"Channel “{nm}” opened. Post as you, or @mention / pick a model to reply.",
        save=False,
    )
    return save_channel(ch)


def rename_channel(channel_id: str, name: str, *, description: str | None = None) -> dict[str, Any] | None:
    ch = get_channel(channel_id)
    if not ch:
        return None
    nm = (name or "").strip()
    if nm:
        ch["name"] = nm[:MAX_NAME_LEN]
    if description is not None:
        ch["description"] = (description or "").strip()[:500]
    return save_channel(ch)


def delete_channel(channel_id: str) -> bool:
    try:
        path = _channel_path(channel_id)
    except ValueError:
        return False
    existed = path.exists()
    try:
        path.unlink(missing_ok=True)  # type: ignore[call-arg]
    except TypeError:
        if path.exists():
            path.unlink()
    except OSError:
        return False
    idx = _load_index()
    idx["channels"] = [c for c in (idx.get("channels") or []) if c.get("id") != channel_id]
    if idx.get("active_id") == channel_id:
        idx["active_id"] = idx["channels"][0]["id"] if idx["channels"] else ""
    _save_index(idx)
    return existed


def append_message(
    ch: dict[str, Any],
    *,
    role: str,
    content: str,
    author: str = "",
    model_id: str = "",
    reply_to: str | None = None,
    parent_id: str | None = None,
    pinned: bool = False,
    mentions: list[str] | None = None,
    meta: dict[str, Any] | None = None,
    save: bool = True,
) -> dict[str, Any]:
    body = (content or "")[:MAX_CONTENT_LEN]
    msg = {
        "id": str(uuid.uuid4())[:12],
        "role": role if role in ("user", "model", "system") else "user",
        "author": author or (role.title() if role else "User"),
        "model_id": model_id or "",
        "content": body,
        "at": _now(),
        "reply_to": reply_to or None,
        "parent_id": parent_id or None,
        "pinned": bool(pinned),
        "mentions": list(mentions or []),
        "meta": dict(meta or {}),
    }
    ch.setdefault("messages", []).append(msg)
    if save:
        save_channel(ch)
    return msg


def post_user_message(
    channel_id: str,
    content: str,
    *,
    reply_to: str | None = None,
    parent_id: str | None = None,
    author: str = "You",
) -> dict[str, Any] | None:
    """Post a user message. Always works without an API key."""
    text = (content or "").strip()
    if not text:
        return None
    ch = get_channel(channel_id)
    if not ch:
        return None
    # Validate reply/parent belong to this channel (soft: ignore bad refs)
    ids = {m["id"] for m in ch.get("messages") or []}
    if reply_to and reply_to not in ids:
        reply_to = None
    if parent_id and parent_id not in ids:
        parent_id = None
    mentions = extract_model_mentions(text)
    msg = append_message(
        ch,
        role="user",
        author=author or "You",
        content=text,
        reply_to=reply_to,
        parent_id=parent_id,
        mentions=mentions,
        save=True,
    )
    return {"channel": get_channel(channel_id), "message": msg}


def extract_model_mentions(text: str) -> list[str]:
    """Extract @slug mentions from free text (deduped, order preserved)."""
    seen: set[str] = set()
    out: list[str] = []
    for m in _MENTION_RE.findall(text or ""):
        mid = m.strip()
        if not mid or mid.lower() in seen:
            continue
        # skip common non-model words
        if mid.lower() in ("you", "channel", "everyone", "here", "all"):
            continue
        seen.add(mid.lower())
        out.append(mid)
    return out


def replace_mentions_for_prompt(text: str) -> str:
    """Humanize @mentions for the model prompt (keep readable slug)."""
    return _MENTION_RE.sub(r"\1", text or "")


def toggle_pin(channel_id: str, message_id: str) -> dict[str, Any] | None:
    """Soft pin / unpin a message. Returns updated message or None."""
    ch = get_channel(channel_id)
    if not ch:
        return None
    hit = None
    for m in ch.get("messages") or []:
        if m.get("id") == message_id:
            m["pinned"] = not bool(m.get("pinned"))
            hit = m
            break
    if not hit:
        return None
    save_channel(ch)
    return _normalize_message(hit)


def list_pinned(channel_id: str) -> list[dict[str, Any]]:
    ch = get_channel(channel_id)
    if not ch:
        return []
    return [m for m in ch.get("messages") or [] if m.get("pinned")]


def list_thread(channel_id: str, parent_id: str) -> list[dict[str, Any]]:
    """Parent message + replies whose parent_id matches (soft threads)."""
    ch = get_channel(channel_id)
    if not ch:
        return []
    msgs = ch.get("messages") or []
    parent = next((m for m in msgs if m.get("id") == parent_id), None)
    if not parent:
        return []
    replies = [m for m in msgs if m.get("parent_id") == parent_id]
    return [parent] + replies


def build_channel_prompt_messages(
    ch: dict[str, Any],
    *,
    model_id: str,
    max_msgs: int = 40,
    parent_id: str | None = None,
) -> list[dict[str, str]]:
    """Build a short conversational prompt for a model reply into the channel."""
    system = (
        f"You are {model_id}, participating in a shared Studio channel "
        f"“{ch.get('name') or 'channel'}”. Be concise and conversational. "
        "Reply as yourself in the timeline — no tool calls, no roleplay as other users."
    )
    if ch.get("description"):
        system += f"\nChannel topic: {ch['description']}"

    msgs: list[dict[str, str]] = [{"role": "system", "content": system}]

    history_src: list[dict[str, Any]]
    if parent_id:
        history_src = list_thread(ch["id"], parent_id) if ch.get("id") else []
        if not history_src:
            history_src = list(ch.get("messages") or [])[-max_msgs:]
    else:
        # Prefer top-level + recent; include pinned lightly
        all_m = list(ch.get("messages") or [])
        pinned = [m for m in all_m if m.get("pinned") and m.get("role") != "system"]
        recent = all_m[-max_msgs:]
        seen: set[str] = set()
        history_src = []
        for m in pinned[-5:] + recent:
            mid = m.get("id")
            if mid in seen:
                continue
            seen.add(str(mid))
            history_src.append(m)

    for m in history_src:
        role = m.get("role") or "user"
        if role == "system":
            continue
        content = replace_mentions_for_prompt(str(m.get("content") or ""))
        who = m.get("author") or role
        if role == "model":
            msgs.append({"role": "assistant", "content": f"{who}: {content}"})
        else:
            msgs.append({"role": "user", "content": f"{who}: {content}"})
    return msgs


def resolve_model_for_ask(model_id: str = "") -> dict[str, Any]:
    """Resolve LLM settings for a channel ask. Soft fields; may lack api_key."""
    try:
        from app.core.services.llm.providers import resolve_active_llm
        from app.core.services.data.storage import load_config
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "note": f"LLM unavailable: {e}", "api_key": "", "model": model_id}

    try:
        active = resolve_active_llm()
    except Exception:  # noqa: BLE001
        cfg = load_config()
        active = {
            "api_key": cfg.get("api_key") or "",
            "base_url": cfg.get("api_base_url") or "https://api.openai.com/v1",
            "model": cfg.get("model") or "gpt-4o-mini",
        }

    mid = (model_id or "").strip() or str(active.get("model") or "gpt-4o-mini")
    return {
        "ok": True,
        "api_key": (active.get("api_key") or "").strip(),
        "base_url": str(active.get("base_url") or "https://api.openai.com/v1"),
        "model": mid,
        "provider_id": active.get("provider_id") or "",
    }


def list_model_choices() -> list[str]:
    """Best-effort model id list for the channel picker."""
    out: list[str] = []
    seen: set[str] = set()
    try:
        from app.core.services.llm.providers import resolve_active_llm, list_providers

        active = resolve_active_llm()
        am = str(active.get("model") or "").strip()
        if am:
            out.append(am)
            seen.add(am.lower())
        for p in list_providers() or []:
            for m in p.get("models_cache") or []:
                mid = str(m or "").strip()
                if not mid or mid.startswith("(") or mid.lower() in seen:
                    continue
                seen.add(mid.lower())
                out.append(mid)
                if len(out) >= 80:
                    return out
    except Exception:  # noqa: BLE001
        pass
    if not out:
        out = ["gpt-4o-mini"]
    return out


def ask_model_reply(
    channel_id: str,
    *,
    model_id: str = "",
    user_text: str = "",
    reply_to: str | None = None,
    parent_id: str | None = None,
    post_user: bool = True,
    chat_completion_fn: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Ask a model to reply into the channel.

    Soft-degrades without API key: user message still posts when ``post_user``
    and ``user_text`` are set; model reply is skipped with a clear note.
    """
    ch = get_channel(channel_id)
    if not ch:
        return {"ok": False, "note": "Channel not found", "message": None, "user_message": None}

    posted_user = None
    text = (user_text or "").strip()
    mentions_from_text = extract_model_mentions(text) if text else []

    # Prefer explicit model_id, else first @mention, else active model
    mid = (model_id or "").strip()
    if not mid and mentions_from_text:
        mid = mentions_from_text[0]

    if post_user and text:
        res = post_user_message(
            channel_id,
            text,
            reply_to=reply_to,
            parent_id=parent_id,
        )
        if res:
            posted_user = res.get("message")
            ch = res.get("channel") or get_channel(channel_id)
            # thread under the new user message when asking from composer
            if parent_id is None and posted_user:
                # keep timeline flat by default; reply_to already set if provided
                pass

    resolved = resolve_model_for_ask(mid)
    mid = str(resolved.get("model") or mid or "gpt-4o-mini")
    api_key = str(resolved.get("api_key") or "")

    if not api_key:
        note = "No API key — model reply soft-degraded (user post kept; add a key in Settings → Providers)"
        # Leave a system soft-notice so the timeline shows what happened
        if ch:
            append_message(
                ch,
                role="system",
                author="System",
                content=note,
                save=True,
            )
        return {
            "ok": False,
            "note": note,
            "message": None,
            "user_message": posted_user,
            "model_id": mid,
        }

    fn = chat_completion_fn
    if fn is None:
        from app.core.services.llm.llm import chat_completion as fn  # type: ignore

    # Refresh channel after possible user post
    ch = get_channel(channel_id) or ch
    prompt_parent = parent_id
    if not prompt_parent and reply_to:
        prompt_parent = reply_to
    messages = build_channel_prompt_messages(ch, model_id=mid, parent_id=prompt_parent)
    if text and not post_user:
        # Asking without re-posting — append the ask as the latest user turn
        messages.append(
            {
                "role": "user",
                "content": f"You: {replace_mentions_for_prompt(text)}",
            }
        )

    try:
        out = fn(
            api_key=api_key,
            messages=messages,
            model=mid,
            base_url=str(resolved.get("base_url") or "https://api.openai.com/v1"),
            timeout=90.0,
            temperature=0.6,
            max_tokens=2048,
        )
        if isinstance(out, tuple):
            reply = str(out[0] or "").strip()
        else:
            reply = str(out or "").strip()
        if not reply:
            return {
                "ok": False,
                "note": "Empty model reply (soft-degrade)",
                "message": None,
                "user_message": posted_user,
                "model_id": mid,
            }
        # Prefer threading under the user message just posted
        thread_parent = parent_id
        thread_reply_to = reply_to
        if posted_user and not thread_parent:
            thread_reply_to = posted_user.get("id")
        msg = append_message(
            ch,
            role="model",
            author=mid,
            model_id=mid,
            content=reply,
            reply_to=thread_reply_to,
            parent_id=thread_parent,
            meta={"model_id": mid},
            save=True,
        )
        return {
            "ok": True,
            "note": f"Replied as {mid}",
            "message": msg,
            "user_message": posted_user,
            "model_id": mid,
        }
    except Exception as e:  # noqa: BLE001
        note = f"Model reply failed (soft-degrade): {e}"
        ch2 = get_channel(channel_id)
        if ch2:
            append_message(ch2, role="system", author="System", content=note, save=True)
        return {
            "ok": False,
            "note": note,
            "message": None,
            "user_message": posted_user,
            "model_id": mid,
        }


def preview_text(text: str, *, limit: int = 100) -> str:
    body = re.sub(r"\s+", " ", (text or "").strip())
    if len(body) <= limit:
        return body
    return body[: limit - 1] + "…"
