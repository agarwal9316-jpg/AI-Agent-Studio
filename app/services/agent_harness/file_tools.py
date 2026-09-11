"""Surgical file tools: read, write, search_replace, list_dir, grep."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.services.agent_harness.sandbox import check_path_access


def read_file(
    path: str,
    *,
    offset: int = 1,
    limit: int | None = 500,
) -> dict[str, Any]:
    chk = check_path_access(path, write=False)
    if not chk.get("ok"):
        return {"ok": False, "error": chk.get("error"), "path": path}
    p = Path(chk["path"])
    if not p.is_file():
        return {"ok": False, "error": f"Not a file: {p}", "path": str(p)}
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return {"ok": False, "error": str(e), "path": str(p)}
    lines = text.splitlines()
    start = max(0, int(offset or 1) - 1)
    if limit is None or int(limit) <= 0:
        chunk = lines[start:]
    else:
        chunk = lines[start : start + int(limit)]
    numbered = "\n".join(f"{start + i + 1}|{ln}" for i, ln in enumerate(chunk))
    return {
        "ok": True,
        "path": str(p),
        "total_lines": len(lines),
        "offset": start + 1,
        "returned_lines": len(chunk),
        "content": numbered,
    }


def write_file(path: str, content: str, *, create_dirs: bool = True) -> dict[str, Any]:
    chk = check_path_access(path, write=True)
    if not chk.get("ok"):
        return {"ok": False, "error": chk.get("error"), "path": path}
    p = Path(chk["path"])
    old = ""
    if p.is_file():
        try:
            old = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            old = ""
    new = content if content is not None else ""
    try:
        if create_dirs:
            p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(new, encoding="utf-8", newline="\n")
        from app.core.services.tools.file_diff import summarize_edit, record_edit

        edit = summarize_edit(path=str(p), old=old, new=new, action="write")
        try:
            record_edit(edit)
        except Exception:  # noqa: BLE001
            pass
        return {
            "ok": True,
            "path": str(p),
            "bytes": p.stat().st_size,
            "diff": edit.get("diff") or "",
            "diff_summary": edit.get("summary") or "",
            "diff_stats": edit.get("stats") or {},
            "is_new": bool(edit.get("is_new")),
        }
    except OSError as e:
        return {"ok": False, "error": str(e), "path": str(p)}


def search_replace(
    path: str,
    old_string: str,
    new_string: str,
    *,
    replace_all: bool = False,
) -> dict[str, Any]:
    chk = check_path_access(path, write=True)
    if not chk.get("ok"):
        return {"ok": False, "error": chk.get("error"), "path": path}
    p = Path(chk["path"])
    if not p.is_file():
        return {"ok": False, "error": f"Not a file: {p}", "path": str(p)}
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return {"ok": False, "error": str(e), "path": str(p)}
    if not old_string:
        return {"ok": False, "error": "old_string empty", "path": str(p)}
    count = text.count(old_string)
    if count == 0:
        return {
            "ok": False,
            "error": "old_string not found (exact match required)",
            "path": str(p),
            "hint": "Re-read the file; match whitespace exactly",
        }
    if count > 1 and not replace_all:
        return {
            "ok": False,
            "error": f"old_string found {count} times; set replace_all=true or add context",
            "path": str(p),
            "matches": count,
        }
    if replace_all:
        new_text = text.replace(old_string, new_string)
        n = count
    else:
        new_text = text.replace(old_string, new_string, 1)
        n = 1
    try:
        p.write_text(new_text, encoding="utf-8", newline="\n")
    except OSError as e:
        return {"ok": False, "error": str(e), "path": str(p)}
    from app.core.services.tools.file_diff import summarize_edit, record_edit

    edit = summarize_edit(path=str(p), old=text, new=new_text, action="search_replace")
    try:
        record_edit(edit)
    except Exception:  # noqa: BLE001
        pass
    return {
        "ok": True,
        "path": str(p),
        "replacements": n,
        "diff": edit.get("diff") or "",
        "diff_summary": edit.get("summary") or "",
        "diff_stats": edit.get("stats") or {},
    }


def delete_file(path: str) -> dict[str, Any]:
    chk = check_path_access(path, write=True)
    if not chk.get("ok"):
        return {"ok": False, "error": chk.get("error"), "path": path}
    p = Path(chk["path"])
    if not p.exists():
        return {"ok": False, "error": "Path does not exist", "path": str(p)}
    try:
        if p.is_dir():
            return {"ok": False, "error": "Refusing to delete directories via delete_file", "path": str(p)}
        old = ""
        try:
            old = p.read_text(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            old = ""
        p.unlink()
        from app.core.services.tools.file_diff import summarize_edit, record_edit

        edit = summarize_edit(path=str(p), old=old, new="", action="delete")
        try:
            record_edit(edit)
        except Exception:  # noqa: BLE001
            pass
        return {
            "ok": True,
            "path": str(p),
            "deleted": True,
            "diff": edit.get("diff") or "",
            "diff_summary": edit.get("summary") or "",
            "diff_stats": edit.get("stats") or {},
        }
    except OSError as e:
        return {"ok": False, "error": str(e), "path": str(p)}


def list_dir(path: str = ".", *, max_entries: int = 200) -> dict[str, Any]:
    chk = check_path_access(path or ".", write=False)
    if not chk.get("ok"):
        return {"ok": False, "error": chk.get("error"), "path": path}
    p = Path(chk["path"])
    if not p.is_dir():
        return {"ok": False, "error": f"Not a directory: {p}", "path": str(p)}
    entries: list[dict[str, Any]] = []
    try:
        kids = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
    except OSError as e:
        return {"ok": False, "error": str(e), "path": str(p)}
    for child in kids[: max(1, int(max_entries))]:
        try:
            st = child.stat()
            entries.append(
                {
                    "name": child.name,
                    "type": "dir" if child.is_dir() else "file",
                    "size": st.st_size if child.is_file() else None,
                }
            )
        except OSError:
            entries.append({"name": child.name, "type": "?", "size": None})
    return {
        "ok": True,
        "path": str(p),
        "count": len(entries),
        "truncated": len(kids) > len(entries),
        "entries": entries,
    }


def grep(
    pattern: str,
    path: str = ".",
    *,
    glob: str = "*",
    max_matches: int = 80,
    case_insensitive: bool = False,
) -> dict[str, Any]:
    chk = check_path_access(path or ".", write=False)
    if not chk.get("ok"):
        return {"ok": False, "error": chk.get("error"), "path": path}
    root = Path(chk["path"])
    try:
        flags = re.I if case_insensitive else 0
        rx = re.compile(pattern, flags)
    except re.error as e:
        return {"ok": False, "error": f"bad regex: {e}"}

    matches: list[dict[str, Any]] = []
    files_scanned = 0
    skip_dirs = {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "dist",
        "build",
        ".tox",
        "browsers",
    }
    try:
        if root.is_file():
            candidates = [root]
        else:
            candidates = [f for f in root.rglob(glob or "*") if f.is_file()]
    except OSError as e:
        return {"ok": False, "error": str(e), "path": str(root)}

    for f in candidates:
        if any(part in skip_dirs for part in f.parts):
            continue
        if f.suffix.lower() in (
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".webp",
            ".exe",
            ".dll",
            ".bin",
            ".pyc",
            ".zip",
            ".7z",
            ".mp4",
            ".pdf",
        ):
            continue
        files_scanned += 1
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if rx.search(line):
                matches.append(
                    {
                        "path": str(f),
                        "line": i,
                        "text": line[:400],
                    }
                )
                if len(matches) >= max(1, int(max_matches)):
                    return {
                        "ok": True,
                        "pattern": pattern,
                        "path": str(root),
                        "files_scanned": files_scanned,
                        "match_count": len(matches),
                        "truncated": True,
                        "matches": matches,
                    }
    return {
        "ok": True,
        "pattern": pattern,
        "path": str(root),
        "files_scanned": files_scanned,
        "match_count": len(matches),
        "truncated": False,
        "matches": matches,
    }
