"""Multiple chat sessions management."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.paths import chat_index_path, chats_dir, current_chat_path
from app.core.services.data.storage import _read_json, _write_json, load_config, save_config


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_chat(title: str = "New chat") -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "title": title,
        "messages": [],
        "agent_id": "",
        "mode": "action",
        "terminal_enabled": True,
        "skills_enabled": True,
        "mcp_enabled": True,
        "laptop_enabled": True,
        "safety_mode": False,
        "enabled_skill_names": None,
        "project_id": "",
        "folder_id": "",
        "pinned": False,
        "parent_chat_id": "",
        "created_at": _now(),
        "updated_at": _now(),
    }


def _default_folder(name: str = "New folder") -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "name": (name or "New folder").strip()[:64] or "New folder",
        "collapsed": False,
        "list_order": 0,
        "created_at": _now(),
        "updated_at": _now(),
    }


def _ensure_index_shape(idx: dict[str, Any]) -> dict[str, Any]:
    """Migrate older indexes: folders list + folder_id on chat meta."""
    if not isinstance(idx, dict):
        return {"active_id": "", "chats": [], "folders": []}
    idx.setdefault("folders", [])
    if not isinstance(idx["folders"], list):
        idx["folders"] = []
    for c in idx.get("chats") or []:
        if isinstance(c, dict):
            c.setdefault("folder_id", "")
    return idx


def _load_index() -> dict[str, Any]:
    idx = _read_json(chat_index_path(), None)
    if isinstance(idx, dict) and "chats" in idx:
        return _ensure_index_shape(idx)
    # migrate legacy current.json
    legacy = _read_json(current_chat_path(), None)
    chats: list[dict[str, Any]] = []
    active = ""
    if isinstance(legacy, dict):
        c = _default_chat(legacy.get("title") or "Main chat")
        c.update({k: legacy[k] for k in legacy if k != "id"})
        c["id"] = legacy.get("id") or c["id"]
        _write_json(chats_dir() / f"{c['id']}.json", c)
        chats.append(
            {
                "id": c["id"],
                "title": c["title"],
                "updated_at": c["updated_at"],
                "folder_id": "",
            }
        )
        active = c["id"]
    else:
        c = _default_chat("Main chat")
        _write_json(chats_dir() / f"{c['id']}.json", c)
        chats.append(
            {
                "id": c["id"],
                "title": c["title"],
                "updated_at": c["updated_at"],
                "folder_id": "",
            }
        )
        active = c["id"]
    idx = {"active_id": active, "chats": chats, "folders": []}
    _write_json(chat_index_path(), idx)
    cfg = load_config()
    cfg["active_chat_id"] = active
    save_config(cfg)
    return _ensure_index_shape(idx)


def _save_index(idx: dict[str, Any]) -> None:
    _write_json(chat_index_path(), _ensure_index_shape(idx))


def list_chats() -> list[dict[str, Any]]:
    idx = _load_index()
    return list(idx.get("chats") or [])


# ---------------------------------------------------------------------------
# Folders (organize chats in the left rail)
# ---------------------------------------------------------------------------


def list_folders() -> list[dict[str, Any]]:
    idx = _load_index()
    folders = list(idx.get("folders") or [])
    return sorted(
        folders,
        key=lambda f: (
            int(f.get("list_order") if f.get("list_order") is not None else 10_000),
            str(f.get("name") or "").lower(),
        ),
    )


def get_folder(folder_id: str) -> dict[str, Any] | None:
    fid = str(folder_id or "").strip()
    if not fid:
        return None
    for f in list_folders():
        if str(f.get("id")) == fid:
            return f
    return None


def create_folder(name: str = "New folder") -> dict[str, Any]:
    idx = _load_index()
    folders = list(idx.get("folders") or [])
    f = _default_folder(name)
    f["list_order"] = len(folders)
    folders.append(f)
    idx["folders"] = folders
    _save_index(idx)
    return f


def rename_folder(folder_id: str, name: str) -> dict[str, Any] | None:
    idx = _load_index()
    fid = str(folder_id or "").strip()
    label = (name or "").strip()[:64] or "Folder"
    for f in idx.get("folders") or []:
        if str(f.get("id")) == fid:
            f["name"] = label
            f["updated_at"] = _now()
            _save_index(idx)
            return f
    return None


def set_folder_collapsed(folder_id: str, collapsed: bool) -> None:
    idx = _load_index()
    fid = str(folder_id or "").strip()
    for f in idx.get("folders") or []:
        if str(f.get("id")) == fid:
            f["collapsed"] = bool(collapsed)
            _save_index(idx)
            return


def toggle_folder_collapsed(folder_id: str) -> bool:
    """Returns new collapsed state."""
    idx = _load_index()
    fid = str(folder_id or "").strip()
    for f in idx.get("folders") or []:
        if str(f.get("id")) == fid:
            f["collapsed"] = not bool(f.get("collapsed"))
            _save_index(idx)
            return bool(f["collapsed"])
    return False


def delete_folder(folder_id: str, *, move_chats_to: str = "") -> bool:
    """
    Remove folder. Chats in it move to move_chats_to (default "" = uncategorized).
    """
    fid = str(folder_id or "").strip()
    if not fid:
        return False
    idx = _load_index()
    before = list(idx.get("folders") or [])
    idx["folders"] = [f for f in before if str(f.get("id")) != fid]
    if len(idx["folders"]) == len(before):
        return False
    dest = str(move_chats_to or "").strip()
    # Validate dest exists (or empty)
    if dest and not any(str(f.get("id")) == dest for f in idx["folders"]):
        dest = ""
    affected: list[str] = []
    for c in idx.get("chats") or []:
        if str(c.get("folder_id") or "") == fid:
            c["folder_id"] = dest
            cid = str(c.get("id") or "")
            if cid:
                affected.append(cid)
    # Sync chat JSON files
    for cid in affected:
        data = try_load_chat(cid)
        if data is not None:
            data["folder_id"] = dest
            data["updated_at"] = _now()
            _write_json(chat_path(data["id"]), data)
    _save_index(idx)
    return True


def move_chat_to_folder(chat_id: str, folder_id: str = "") -> dict[str, Any]:
    """Assign chat to a folder (empty folder_id = uncategorized / root)."""
    cid = str(chat_id or "").strip()
    fid = str(folder_id or "").strip()
    if fid and get_folder(fid) is None:
        fid = ""
    c = load_chat(cid)
    c["folder_id"] = fid
    return save_chat(c)


def move_chats_to_folder(chat_ids: list[str], folder_id: str = "") -> int:
    """Bulk move. Returns count moved."""
    n = 0
    for cid in chat_ids or []:
        cid = str(cid or "").strip()
        if not cid:
            continue
        try:
            move_chat_to_folder(cid, folder_id)
            n += 1
        except Exception:  # noqa: BLE001
            continue
    return n


def delete_chats(chat_ids: list[str]) -> int:
    """Bulk delete. Returns count removed."""
    n = 0
    for cid in list(chat_ids or []):
        cid = str(cid or "").strip()
        if not cid:
            continue
        try:
            if delete_chat(cid):
                n += 1
        except Exception:  # noqa: BLE001
            continue
    return n


def list_chats_in_folder(folder_id: str = "") -> list[dict[str, Any]]:
    """folder_id '' = chats not in any folder."""
    fid = str(folder_id or "").strip()
    out = []
    for c in list_chats():
        cf = str(c.get("folder_id") or "").strip()
        if cf == fid:
            out.append(c)
    return out


def get_active_chat_id() -> str:
    cfg = load_config()
    aid = cfg.get("active_chat_id") or ""
    idx = _load_index()
    if aid and any(c["id"] == aid for c in idx.get("chats") or []):
        return aid
    return idx.get("active_id") or ""


def set_active_chat_id(chat_id: str) -> None:
    idx = _load_index()
    idx["active_id"] = chat_id
    _save_index(idx)
    cfg = load_config()
    cfg["active_chat_id"] = chat_id
    save_config(cfg)


def chat_path(chat_id: str) -> Path:
    return chats_dir() / f"{chat_id}.json"


def load_chat(chat_id: str | None = None) -> dict[str, Any]:
    cid = chat_id or get_active_chat_id()
    path = chat_path(cid)
    data = _read_json(path, None)
    if isinstance(data, dict) and data.get("id"):
        return data
    # fallback create
    c = _default_chat()
    c["id"] = cid or c["id"]
    save_chat(c)
    return c


def _title_from_messages(messages: list[Any] | None) -> str:
    for m in messages or []:
        if not isinstance(m, dict):
            continue
        if m.get("role") == "user" and m.get("content"):
            t = str(m["content"]).strip().split("\n")[0][:48]
            if t:
                return t
    return ""


def _is_default_title(title: str | None) -> bool:
    return (title or "").strip().lower() in ("", "new chat", "main chat", "chat")


def try_load_chat(chat_id: str) -> dict[str, Any] | None:
    """Load chat JSON without creating a new file if missing."""
    if not chat_id:
        return None
    data = _read_json(chat_path(chat_id), None)
    if isinstance(data, dict) and data.get("id"):
        return data
    return None


def save_chat(chat: dict[str, Any]) -> dict[str, Any]:
    if not chat.get("id"):
        chat["id"] = str(uuid.uuid4())
    chat["updated_at"] = _now()
    chat.setdefault("pinned", False)
    chat.setdefault("parent_chat_id", "")
    chat.setdefault("folder_id", "")
    # Drop stale folder refs
    fid = str(chat.get("folder_id") or "").strip()
    if fid:
        idx_chk = _load_index()
        if not any(str(f.get("id")) == fid for f in (idx_chk.get("folders") or [])):
            fid = ""
            chat["folder_id"] = ""
    msgs = chat.get("messages") or []
    # Auto-title empty/default titles from first user message
    if _is_default_title(chat.get("title")):
        derived = _title_from_messages(msgs)
        chat["title"] = derived or (chat.get("title") or "New chat") or "New chat"
    msg_count = len(msgs)
    _write_json(chat_path(chat["id"]), chat)
    idx = _load_index()
    found = False
    for c in idx.get("chats") or []:
        if c["id"] == chat["id"]:
            c["title"] = chat["title"]
            c["updated_at"] = chat["updated_at"]
            c["pinned"] = bool(chat.get("pinned"))
            c["parent_chat_id"] = chat.get("parent_chat_id") or ""
            c["folder_id"] = str(chat.get("folder_id") or "")
            c["message_count"] = msg_count
            found = True
            break
    if not found:
        idx.setdefault("chats", []).insert(
            0,
            {
                "id": chat["id"],
                "title": chat["title"],
                "updated_at": chat["updated_at"],
                "pinned": bool(chat.get("pinned")),
                "parent_chat_id": chat.get("parent_chat_id") or "",
                "folder_id": str(chat.get("folder_id") or ""),
                "message_count": msg_count,
            },
        )
    # Pinned first, then manual list_order (lower = higher), then newest
    idx["chats"] = _sort_chat_index(idx.get("chats") or [])
    _save_index(idx)
    return chat


def _sort_chat_index(chats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pinned first, then list_order ascending, then updated_at descending."""
    return sorted(
        chats,
        key=lambda x: (
            0 if x.get("pinned") else 1,
            int(x.get("list_order") if x.get("list_order") is not None else 10_000),
            # Descending updated_at: invert by prefixing with reverse key via sort later
            # Use negative rank of ISO string (lexicographic reverse)
            tuple(-ord(c) for c in str(x.get("updated_at") or "0")[:24]),
        ),
    )


def reorder_chat(chat_id: str, target_index: int) -> list[dict[str, Any]]:
    """
    Move chat to target_index in the index list (0 = top after pins logic).
    Reassigns list_order so order persists across save_chat re-sorts.
    """
    idx = _load_index()
    chats = list(idx.get("chats") or [])
    item = next((c for c in chats if c.get("id") == chat_id), None)
    if not item:
        return chats
    rest = [c for c in chats if c.get("id") != chat_id]
    ti = max(0, min(len(rest), int(target_index)))
    rest.insert(ti, item)
    for i, c in enumerate(rest):
        c["list_order"] = i
    idx["chats"] = _sort_chat_index(rest)
    # After sort, re-stamp list_order to match visual order
    for i, c in enumerate(idx["chats"]):
        c["list_order"] = i
    _save_index(idx)
    return list(idx["chats"])


def pin_chat(chat_id: str, pinned: bool = True) -> dict[str, Any]:
    c = load_chat(chat_id)
    c["pinned"] = bool(pinned)
    return save_chat(c)


def toggle_pin(chat_id: str) -> dict[str, Any]:
    c = load_chat(chat_id)
    c["pinned"] = not bool(c.get("pinned"))
    return save_chat(c)


def branch_chat(chat_id: str | None = None, *, title: str = "") -> dict[str, Any]:
    """
    Fork a chat: copy messages into a new chat (branch).
    Original remains unchanged; new chat is activated.
    """
    src = load_chat(chat_id)
    branch_title = (title or "").strip() or f"Branch of {src.get('title') or 'chat'}"
    c = _default_chat(branch_title[:80])
    c["messages"] = list(src.get("messages") or [])
    c["agent_id"] = src.get("agent_id") or ""
    c["mode"] = src.get("mode") or "action"
    c["terminal_enabled"] = bool(src.get("terminal_enabled", True))
    c["skills_enabled"] = bool(src.get("skills_enabled", True))
    c["mcp_enabled"] = bool(src.get("mcp_enabled", True))
    c["laptop_enabled"] = bool(src.get("laptop_enabled", True))
    c["safety_mode"] = bool(src.get("safety_mode", False))
    c["enabled_skill_names"] = src.get("enabled_skill_names")
    c["project_id"] = src.get("project_id") or ""
    c["parent_chat_id"] = src.get("id") or ""
    c["folder_id"] = str(src.get("folder_id") or "")
    c["pinned"] = False
    save_chat(c)
    set_active_chat_id(c["id"])
    return c


def new_chat(
    title: str = "New chat",
    project_id: str = "",
    folder_id: str = "",
) -> dict[str, Any]:
    c = _default_chat(title)
    if project_id:
        c["project_id"] = project_id
    fid = str(folder_id or "").strip()
    if fid and get_folder(fid) is not None:
        c["folder_id"] = fid
    save_chat(c)
    set_active_chat_id(c["id"])
    return c


def delete_chat(chat_id: str) -> bool:
    """
    Delete chat file + index entry.
    Does not recreate the deleted id. Ensures at least one chat exists.
    Returns True if the id was removed from the index (or file deleted).
    """
    chat_id = str(chat_id or "").strip()
    if not chat_id:
        return False
    path = chat_path(chat_id)
    file_gone = False
    if path.exists():
        try:
            path.unlink()
            file_gone = True
        except OSError:
            # Still drop from index so UI does not keep a ghost entry
            file_gone = False
    idx = _load_index()
    before = list(idx.get("chats") or [])
    idx["chats"] = [c for c in before if str(c.get("id")) != chat_id]
    removed = len(idx["chats"]) < len(before) or file_gone
    # Update active id in the same write — do NOT call set_active_chat_id()
    # here (it reloads index from disk and can re-introduce the deleted row).
    active = str(idx.get("active_id") or "")
    if active == chat_id or not any(str(c.get("id")) == active for c in idx["chats"]):
        idx["active_id"] = str(idx["chats"][0]["id"]) if idx["chats"] else ""
    _save_index(idx)
    cfg = load_config()
    cfg["active_chat_id"] = idx.get("active_id") or ""
    save_config(cfg)
    if not idx["chats"]:
        new_chat("Main chat")
    return removed


def is_empty_stub(meta: dict[str, Any] | None = None, chat_id: str = "") -> bool:
    """True if chat has no messages and a default title (empty New/Main chat)."""
    cid = str(chat_id or (meta or {}).get("id") or "").strip()
    title = str((meta or {}).get("title") or "")
    msg_count = (meta or {}).get("message_count")
    if msg_count is None and cid:
        data = try_load_chat(cid)
        if data is None:
            return True
        msg_count = len(data.get("messages") or [])
        if not title:
            title = str(data.get("title") or "")
    if int(msg_count or 0) > 0:
        return False
    return _is_default_title(title)


def prune_empty_stub_chats(*, keep_active: bool = True, keep_extra: int = 0) -> int:
    """
    Remove truly empty New/Main chat stubs from disk + index.
    Keeps the active chat (if keep_active) and up to keep_extra other empty stubs.
    Chats with messages are never removed. Returns number deleted.
    """
    idx = _load_index()
    active = str(idx.get("active_id") or "")
    empty_ids: list[str] = []
    for meta in list(idx.get("chats") or []):
        cid = str(meta.get("id") or "")
        if not cid:
            continue
        if is_empty_stub(meta, cid):
            empty_ids.append(cid)
    keep: set[str] = set()
    if keep_active and active and active in empty_ids:
        keep.add(active)
    for cid in empty_ids:
        if cid in keep:
            continue
        if keep_extra > 0:
            keep.add(cid)
            keep_extra -= 1
            continue
    removed = 0
    for cid in empty_ids:
        if cid in keep:
            continue
        if delete_chat(cid):
            removed += 1
    return removed


def repair_chat_titles() -> int:
    """
    Backfill titles for chats still named New/Main chat that already have messages.
    Updates index. Returns number of titles fixed.
    """
    fixed = 0
    idx = _load_index()
    changed = False
    for meta in list(idx.get("chats") or []):
        cid = str(meta.get("id") or "")
        if not cid:
            continue
        data = try_load_chat(cid)
        if data is None:
            continue
        msgs = data.get("messages") or []
        msg_count = len(msgs)
        meta["message_count"] = msg_count
        if msg_count and _is_default_title(data.get("title")):
            derived = _title_from_messages(msgs)
            if derived:
                data["title"] = derived
                data["updated_at"] = data.get("updated_at") or _now()
                _write_json(chat_path(cid), data)
                meta["title"] = derived
                fixed += 1
                changed = True
        elif data.get("title") and meta.get("title") != data.get("title"):
            meta["title"] = data["title"]
            changed = True
    if changed or fixed:
        idx["chats"] = _sort_chat_index(idx.get("chats") or [])
        _save_index(idx)
    return fixed


def rename_chat(chat_id: str, title: str) -> None:
    c = load_chat(chat_id)
    c["title"] = title.strip() or c.get("title") or "Chat"
    save_chat(c)


def move_chat_to_project(chat_id: str, project_id: str) -> dict[str, Any]:
    """Assign / move a chat into a project (empty project_id = ungrouped)."""
    c = load_chat(chat_id)
    c["project_id"] = project_id or ""
    return save_chat(c)


def list_chats_for_project(project_id: str = "") -> list[dict[str, Any]]:
    """If project_id set, only chats in that project; else all (with project_id field)."""
    out = []
    for meta in list_chats():
        full = load_chat(meta["id"])
        entry = {
            **meta,
            "project_id": full.get("project_id") or "",
            "message_count": len(full.get("messages") or []),
        }
        if project_id and entry["project_id"] != project_id:
            continue
        out.append(entry)
    return out


def list_ungrouped_chats() -> list[dict[str, Any]]:
    return [c for c in list_chats_for_project("") if not c.get("project_id")]
