"""Collect files / images / reports produced this chat turn (Task #12)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.paths import data_dir

_PATH_RE = re.compile(
    r"(?P<p>(?:[A-Za-z]:\\|\\\\|/)[^\s`\"'<>|]{3,240}\.(?:"
    r"png|jpe?g|gif|webp|bmp|svg|mp4|webm|pdf|md|txt|json|csv|py|html|zip"
    r"))",
    re.I,
)
_FILE_URI_RE = re.compile(r"file:///[^\s)\]>`\"']+", re.I)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _kind_for_path(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"):
        return "image"
    if ext in (".mp4", ".webm", ".mkv", ".avi", ".mov"):
        return "video"
    if ext in (".md", ".txt", ".pdf", ".html"):
        return "report"
    if ext in (".py", ".js", ".ts", ".json", ".csv", ".yaml", ".yml"):
        return "code"
    return "file"


def _item(
    *,
    kind: str,
    title: str,
    path: str = "",
    meta: str = "",
    source: str = "",
    openable: bool = True,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "title": title or kind,
        "path": path or "",
        "meta": meta or "",
        "source": source or "",
        "openable": openable and bool(path),
        "at": _now(),
        **(extra or {}),
    }


def collect_from_messages(
    messages: list[dict[str, Any]] | None,
    *,
    limit_msgs: int = 40,
) -> list[dict[str, Any]]:
    """Scan recent chat messages for media, diffs, and file paths."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    msgs = list(messages or [])[-max(1, int(limit_msgs)) :]
    for m in msgs:
        role = str(m.get("role") or "")
        # Images on message
        for ip in m.get("images") or []:
            p = str(ip)
            if p and p not in seen:
                seen.add(p)
                out.append(
                    _item(
                        kind="image",
                        title=Path(p).name,
                        path=p,
                        meta=f"from {role or 'message'}",
                        source="chat",
                    )
                )
        # Structured file edits
        fd = m.get("file_diff")
        if isinstance(fd, dict) and (fd.get("path") or fd.get("diff")):
            p = str(fd.get("path") or "")
            key = f"diff:{p}:{str(fd.get('summary') or '')[:40]}"
            if key not in seen:
                seen.add(key)
                out.append(
                    _item(
                        kind="diff",
                        title=str(fd.get("summary") or Path(p).name or "File edit"),
                        path=p,
                        meta="file edit",
                        source="harness",
                        openable=bool(p),
                        extra={"diff": fd.get("diff") or "", "file_diff": fd},
                    )
                )
        content = str(m.get("content") or "")
        # file:// links
        for muri in _FILE_URI_RE.finditer(content):
            uri = muri.group(0).rstrip(".,;:)]}>\"'")
            key = f"uri:{uri}"
            if key not in seen:
                seen.add(key)
                out.append(
                    _item(
                        kind="link",
                        title=uri.split("/")[-1] or uri,
                        path=uri,
                        meta="citation / link",
                        source=role or "chat",
                    )
                )
        # Absolute paths in content
        for mp in _PATH_RE.finditer(content):
            p = mp.group("p").rstrip(".,;:)]}>\"'")
            if p in seen:
                continue
            # skip noise
            if len(p) < 6:
                continue
            seen.add(p)
            kind = _kind_for_path(p)
            out.append(
                _item(
                    kind=kind,
                    title=Path(p).name,
                    path=p,
                    meta=f"mentioned in {role or 'message'}",
                    source=role or "chat",
                )
            )
    return out


def collect_recent_edits(limit: int = 15, *, chat_id: str = "") -> list[dict[str, Any]]:
    try:
        from app.core.services.tools.file_diff import list_recent_edits

        edits = list_recent_edits(limit=limit, chat_id=chat_id)
    except Exception:  # noqa: BLE001
        return []
    out = []
    for e in edits:
        out.append(
            _item(
                kind="diff",
                title=str(e.get("summary") or Path(str(e.get("path") or "")).name or "Edit"),
                path=str(e.get("path") or ""),
                meta=str(e.get("action") or "edit"),
                source="file_edit_log",
                extra={"diff": e.get("diff") or "", "file_diff": e},
            )
        )
    return out


def collect_project_outputs(limit: int = 12) -> list[dict[str, Any]]:
    try:
        from app.services import project_outputs, project_store

        pid = project_store.get_active_project_id()
        items = project_outputs.list_outputs(pid, limit=limit)
    except Exception:  # noqa: BLE001
        return []
    out = []
    for it in items:
        if isinstance(it, dict):
            p = str(it.get("path") or "")
            title = str(it.get("title") or it.get("name") or Path(p).name)
        else:
            p = str(it)
            title = Path(p).name
        if not p:
            continue
        out.append(
            _item(
                kind="report",
                title=title,
                path=p,
                meta="project output",
                source="project",
            )
        )
    return out


def collect_research_packs(limit: int = 8) -> list[dict[str, Any]]:
    d = data_dir() / "research"
    if not d.is_dir():
        return []
    files = sorted(d.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    return [
        _item(
            kind="report",
            title=f.name,
            path=str(f),
            meta="research pack",
            source="research",
        )
        for f in files
    ]


def collect_artifacts(
    *,
    messages: list[dict[str, Any]] | None = None,
    chat_id: str = "",
    pending_images: list[str] | None = None,
    pending_videos: list[str] | None = None,
    attachments: list[str] | None = None,
    this_turn_only: bool = False,
) -> dict[str, Any]:
    """
    Build a categorized artifact list for the UI.
    this_turn_only: only last user→assistant segment (approx last 12 msgs).
    """
    msgs = list(messages or [])
    if this_turn_only and msgs:
        # from last user message
        start = 0
        for i in range(len(msgs) - 1, -1, -1):
            if str(msgs[i].get("role") or "") == "user":
                start = i
                break
        msgs = msgs[start:]

    items: list[dict[str, Any]] = []
    items.extend(collect_from_messages(msgs))
    for p in pending_images or []:
        items.append(_item(kind="image", title=Path(p).name, path=p, meta="pending", source="attach"))
    for p in pending_videos or []:
        items.append(_item(kind="video", title=Path(p).name, path=p, meta="pending", source="attach"))
    for p in attachments or []:
        items.append(
            _item(kind=_kind_for_path(p), title=Path(p).name, path=p, meta="attachment", source="attach")
        )
    if not this_turn_only:
        items.extend(collect_recent_edits(12, chat_id=chat_id))
        items.extend(collect_project_outputs(10))
        items.extend(collect_research_packs(6))

    # Dedupe by path+kind
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for it in items:
        key = f"{it.get('kind')}|{it.get('path')}|{it.get('title')}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(it)

    by_kind: dict[str, int] = {}
    for it in unique:
        k = str(it.get("kind") or "file")
        by_kind[k] = by_kind.get(k, 0) + 1

    return {
        "ok": True,
        "count": len(unique),
        "by_kind": by_kind,
        "items": unique[:80],
        "summary": _format_summary(by_kind, len(unique)),
    }


def _format_summary(by_kind: dict[str, int], total: int) -> str:
    if not total:
        return "No artifacts yet this turn."
    parts = [f"{n}× {k}" for k, n in sorted(by_kind.items())]
    return f"{total} artifact(s): " + " · ".join(parts)


def format_artifacts_text(bundle: dict[str, Any]) -> str:
    lines = [str(bundle.get("summary") or "Artifacts"), ""]
    icons = {
        "image": "🖼",
        "video": "🎬",
        "diff": "📄",
        "report": "📑",
        "code": "💻",
        "file": "📎",
        "link": "🔗",
    }
    for it in bundle.get("items") or []:
        ic = icons.get(str(it.get("kind")), "•")
        title = it.get("title") or "?"
        path = it.get("path") or ""
        meta = it.get("meta") or ""
        lines.append(f"{ic} [{it.get('kind')}] {title}")
        if meta:
            lines.append(f"    {meta}")
        if path:
            lines.append(f"    {path}")
        lines.append("")
    if not bundle.get("items"):
        lines.append("(empty — generate an image, edit a file, or save a report)")
    return "\n".join(lines).rstrip() + "\n"
