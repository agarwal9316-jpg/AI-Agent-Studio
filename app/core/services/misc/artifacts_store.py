"""Persistent artifacts store — durable personal library for turn outputs (P2.2).

Ideas from Open WebUI file uploads + local storage provider (metadata + blob
under a data dir, list/get/delete by id) reimplemented cleanly for Studio
CustomTkinter — no GPL blobs, no multi-user DB.

Storage layout::

    data/artifacts/
      index.json              # { items: [...], updated_at }
      blobs/<id>/<filename>   # copied file bytes

Metadata fields: id, chat_id, title, path (relative under artifacts_dir),
mime, kind, size, source_path, created_at, tags.
"""

from __future__ import annotations

import mimetypes
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.paths import artifacts_dir
from app.core.services.data.storage import _read_json, _write_json

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._\- ]+")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_id(aid: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "", (aid or "").strip())[:80]


def _safe_filename(name: str) -> str:
    base = Path(name or "artifact.bin").name.strip() or "artifact.bin"
    base = _SAFE_NAME_RE.sub("_", base).strip("._") or "artifact.bin"
    if len(base) > 180:
        stem = Path(base).stem[:140]
        suf = Path(base).suffix[:20]
        base = stem + suf
    return base


def _index_path() -> Path:
    return artifacts_dir() / "index.json"


def _blobs_dir() -> Path:
    d = artifacts_dir() / "blobs"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return d


def _guess_mime(path: Path, *, fallback: str = "application/octet-stream") -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime or fallback


def _kind_from_mime_or_path(mime: str, path: str) -> str:
    m = (mime or "").lower()
    ext = Path(path or "").suffix.lower()
    if m.startswith("image/") or ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"):
        return "image"
    if m.startswith("video/") or ext in (".mp4", ".webm", ".mkv", ".avi", ".mov"):
        return "video"
    if m.startswith("text/") or ext in (".md", ".txt", ".html", ".pdf"):
        return "report" if ext in (".md", ".txt", ".html", ".pdf") else "file"
    if ext in (".py", ".js", ".ts", ".json", ".csv", ".yaml", ".yml", ".diff", ".patch"):
        return "code"
    return "file"


def _normalize(item: dict[str, Any]) -> dict[str, Any]:
    tags = item.get("tags") or []
    if not isinstance(tags, list):
        tags = []
    tags = [str(t).strip() for t in tags if str(t).strip()]
    return {
        "id": str(item.get("id") or ""),
        "chat_id": str(item.get("chat_id") or ""),
        "title": str(item.get("title") or "Untitled").strip() or "Untitled",
        "path": str(item.get("path") or ""),
        "mime": str(item.get("mime") or "application/octet-stream"),
        "kind": str(item.get("kind") or "file"),
        "size": int(item.get("size") or 0),
        "source_path": str(item.get("source_path") or ""),
        "created_at": str(item.get("created_at") or ""),
        "tags": tags,
    }


def _load_index() -> dict[str, Any]:
    """Load index; soft-degrade to empty on disk/JSON errors."""
    try:
        data = _read_json(_index_path(), {"items": [], "updated_at": ""})
    except Exception:  # noqa: BLE001
        return {"items": [], "updated_at": "", "error": "read_failed"}
    if not isinstance(data, dict):
        return {"items": [], "updated_at": ""}
    items = data.get("items")
    if not isinstance(items, list):
        items = []
    return {"items": items, "updated_at": str(data.get("updated_at") or "")}


def _save_index(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Persist index. Returns {ok, note?} — soft-degrades on OSError."""
    payload = {"items": items, "updated_at": _now()}
    try:
        _write_json(_index_path(), payload)
        return {"ok": True, "note": ""}
    except OSError as e:
        return {"ok": False, "note": f"Disk error saving artifacts index: {e}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "note": f"Could not save artifacts index: {e}"}


def resolve_path(item: dict[str, Any]) -> Path | None:
    """Absolute path to stored blob (or None if missing)."""
    rel = str(item.get("path") or "").strip()
    if not rel:
        return None
    p = Path(rel)
    if not p.is_absolute():
        p = artifacts_dir() / rel
    try:
        if p.is_file():
            return p
    except OSError:
        return None
    return None


def list_artifacts(
    *,
    query: str = "",
    chat_id: str = "",
    tag: str = "",
) -> list[dict[str, Any]]:
    """List saved artifacts newest-first. Never raises."""
    try:
        idx = _load_index()
        items = [_normalize(i) for i in idx.get("items") or [] if isinstance(i, dict) and i.get("id")]
    except Exception:  # noqa: BLE001
        return []
    cid = (chat_id or "").strip()
    if cid:
        items = [i for i in items if i.get("chat_id") == cid]
    t = (tag or "").strip().lower()
    if t:
        items = [i for i in items if t in [x.lower() for x in (i.get("tags") or [])]]
    items.sort(key=lambda n: n.get("created_at") or "", reverse=True)
    q = (query or "").strip().lower()
    if not q:
        return items
    words = [w for w in re.split(r"\s+", q) if w]
    out: list[dict[str, Any]] = []
    for n in items:
        hay = (
            f"{n.get('title', '')}\n{n.get('mime', '')}\n{n.get('kind', '')}\n"
            f"{n.get('source_path', '')}\n{' '.join(n.get('tags') or [])}\n{n.get('chat_id', '')}"
        ).lower()
        if all(w in hay for w in words):
            out.append(n)
    return out


def search_artifacts(query: str) -> list[dict[str, Any]]:
    return list_artifacts(query=query)


def get_artifact(artifact_id: str) -> dict[str, Any] | None:
    sid = _safe_id(artifact_id)
    if not sid:
        return None
    try:
        for it in list_artifacts():
            if it.get("id") == sid or _safe_id(str(it.get("id") or "")) == sid:
                # prefer exact match from index (list already normalized)
                if it.get("id") == artifact_id or it.get("id") == sid:
                    return it
        # fallback exact scan
        idx = _load_index()
        for raw in idx.get("items") or []:
            if isinstance(raw, dict) and str(raw.get("id") or "") == artifact_id:
                return _normalize(raw)
    except Exception:  # noqa: BLE001
        return None
    return None


def save_artifact(
    source: str | Path | None = None,
    *,
    title: str = "",
    chat_id: str = "",
    tags: list[str] | None = None,
    mime: str = "",
    kind: str = "",
    content: bytes | str | None = None,
    filename: str = "",
) -> dict[str, Any]:
    """Copy a file (or write content) into the store. Soft-degrades on disk errors.

    Returns ``{ok, artifact?, note}``.
    """
    aid = str(uuid.uuid4())
    src_path = Path(source) if source else None
    raw: bytes
    display_name = filename or (src_path.name if src_path else "") or "artifact.bin"

    try:
        if content is not None:
            raw = content.encode("utf-8") if isinstance(content, str) else bytes(content)
        elif src_path is not None:
            if not src_path.is_file():
                return {"ok": False, "artifact": None, "note": f"Source not found: {src_path}"}
            raw = src_path.read_bytes()
            display_name = filename or src_path.name
        else:
            return {"ok": False, "artifact": None, "note": "No source path or content"}
    except OSError as e:
        return {"ok": False, "artifact": None, "note": f"Disk error reading source: {e}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "artifact": None, "note": f"Could not read source: {e}"}

    safe_name = _safe_filename(display_name)
    rel = f"blobs/{aid}/{safe_name}"
    dest_dir = _blobs_dir() / aid
    dest = dest_dir / safe_name
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
    except OSError as e:
        return {"ok": False, "artifact": None, "note": f"Disk error writing artifact: {e}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "artifact": None, "note": f"Could not write artifact: {e}"}

    guessed = mime or _guess_mime(dest)
    k = kind or _kind_from_mime_or_path(guessed, safe_name)
    item = _normalize(
        {
            "id": aid,
            "chat_id": chat_id or "",
            "title": (title or Path(safe_name).stem or "Untitled").strip() or "Untitled",
            "path": rel,
            "mime": guessed,
            "kind": k,
            "size": len(raw),
            "source_path": str(src_path) if src_path else "",
            "created_at": _now(),
            "tags": list(tags or []),
        }
    )

    try:
        idx = _load_index()
        items = [i for i in (idx.get("items") or []) if isinstance(i, dict)]
        items.append(item)
        saved = _save_index(items)
        if not saved.get("ok"):
            # best-effort cleanup of orphan blob
            try:
                shutil.rmtree(dest_dir, ignore_errors=True)
            except Exception:  # noqa: BLE001
                pass
            return {"ok": False, "artifact": None, "note": saved.get("note") or "Index save failed"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "artifact": None, "note": f"Index update soft-degrade: {e}"}

    return {"ok": True, "artifact": item, "note": "Saved"}


def save_from_turn_item(
    turn_item: dict[str, Any] | None,
    *,
    chat_id: str = "",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Persist an ephemeral Live→Artifacts item into the durable store."""
    it = turn_item if isinstance(turn_item, dict) else {}
    path = str(it.get("path") or "").strip()
    title = str(it.get("title") or "").strip()
    kind = str(it.get("kind") or "").strip()
    extra_tags = list(tags or [])
    src_tag = str(it.get("source") or "").strip()
    if src_tag and src_tag not in extra_tags:
        extra_tags.append(src_tag)
    if kind and kind not in extra_tags:
        extra_tags.append(kind)

    # Diff / text-only: store payload as a text file
    if kind == "diff" or (not path and (it.get("diff") or it.get("file_diff"))):
        fd = it.get("file_diff") if isinstance(it.get("file_diff"), dict) else {}
        body = str(it.get("diff") or fd.get("diff") or "")
        if not body and path:
            try:
                body = Path(path).read_text(encoding="utf-8", errors="replace")
            except OSError:
                body = f"(diff path: {path})"
        fname = _safe_filename((title or Path(path).name or "edit") + ".diff")
        return save_artifact(
            None,
            title=title or fname,
            chat_id=chat_id or "",
            tags=extra_tags,
            mime="text/x-diff",
            kind="diff",
            content=body or f"# {title}\npath: {path}\n",
            filename=fname,
        )

    if not path:
        # link or empty — soft-degrade
        return {
            "ok": False,
            "artifact": None,
            "note": "Nothing to save (no file path on this artifact)",
        }

    # Skip file:// and http links for blob copy — store a small pointer note
    low = path.lower()
    if low.startswith("http://") or low.startswith("https://") or low.startswith("file:"):
        fname = _safe_filename((title or "link") + ".txt")
        return save_artifact(
            None,
            title=title or path[:80],
            chat_id=chat_id or "",
            tags=extra_tags + ["link"],
            mime="text/plain",
            kind="link",
            content=f"{path}\n",
            filename=fname,
        )

    src = Path(path)
    return save_artifact(
        src,
        title=title or src.name,
        chat_id=chat_id or "",
        tags=extra_tags,
        kind=kind,
        filename=src.name,
    )


def delete_artifact(artifact_id: str) -> dict[str, Any]:
    """Remove metadata + blob. Soft-degrades; returns {ok, note}."""
    art = get_artifact(artifact_id)
    if not art:
        return {"ok": False, "note": "Artifact not found"}
    aid = art["id"]
    try:
        idx = _load_index()
        items = [
            i
            for i in (idx.get("items") or [])
            if isinstance(i, dict) and str(i.get("id") or "") != aid
        ]
        saved = _save_index(items)
        if not saved.get("ok"):
            return {"ok": False, "note": saved.get("note") or "Index save failed"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "note": f"Index update soft-degrade: {e}"}

    # Remove blob directory
    try:
        blob_dir = _blobs_dir() / aid
        if blob_dir.is_dir():
            shutil.rmtree(blob_dir, ignore_errors=True)
    except OSError as e:
        return {"ok": True, "note": f"Removed from index; blob cleanup soft-degrade: {e}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": True, "note": f"Removed from index; blob cleanup note: {e}"}
    return {"ok": True, "note": "Deleted"}


def export_artifact(artifact_id: str, dest: str | Path) -> dict[str, Any]:
    """Copy stored blob to dest path. Soft-degrades on disk errors."""
    art = get_artifact(artifact_id)
    if not art:
        return {"ok": False, "note": "Artifact not found", "path": ""}
    src = resolve_path(art)
    if src is None:
        return {"ok": False, "note": "Stored file missing on disk", "path": ""}
    dest_p = Path(dest)
    try:
        dest_p.parent.mkdir(parents=True, exist_ok=True)
        if dest_p.is_dir():
            dest_p = dest_p / src.name
        shutil.copy2(src, dest_p)
        return {"ok": True, "note": "Exported", "path": str(dest_p)}
    except OSError as e:
        return {"ok": False, "note": f"Disk error exporting: {e}", "path": ""}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "note": f"Export soft-degrade: {e}", "path": ""}


def update_tags(artifact_id: str, tags: list[str]) -> dict[str, Any]:
    art = get_artifact(artifact_id)
    if not art:
        return {"ok": False, "artifact": None, "note": "Artifact not found"}
    try:
        idx = _load_index()
        items: list[dict[str, Any]] = []
        updated = None
        for raw in idx.get("items") or []:
            if not isinstance(raw, dict):
                continue
            if str(raw.get("id") or "") == art["id"]:
                raw = dict(raw)
                raw["tags"] = [str(t).strip() for t in tags if str(t).strip()]
                updated = _normalize(raw)
                items.append(updated)
            else:
                items.append(raw)
        saved = _save_index(items)
        if not saved.get("ok"):
            return {"ok": False, "artifact": None, "note": saved.get("note") or "Save failed"}
        return {"ok": True, "artifact": updated, "note": "Updated"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "artifact": None, "note": f"Update soft-degrade: {e}"}


def store_status() -> dict[str, Any]:
    """Capability / health probe for UI. Never raises."""
    try:
        root = artifacts_dir()
        writable = False
        try:
            root.mkdir(parents=True, exist_ok=True)
            probe = root / f".write_probe_{uuid.uuid4().hex[:8]}"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            writable = True
        except OSError as e:
            return {
                "ok": False,
                "writable": False,
                "count": 0,
                "root": str(root),
                "note": f"Disk not writable: {e}",
            }
        items = list_artifacts()
        return {
            "ok": True,
            "writable": writable,
            "count": len(items),
            "root": str(root),
            "note": "",
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "writable": False, "count": 0, "root": "", "note": str(e)}
