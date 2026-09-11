"""
Safe self-improvement of the app source with automatic backups + rollback.

Never edits without a restore point. On failure, restores from the last backup.
"""

from __future__ import annotations

import json
import re
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.paths import app_root, data_dir

SELF_IMPROVE_RE = re.compile(
    r"<<<SELF_IMPROVE>>>\s*(.*?)\s*<<<END_SELF_IMPROVE>>>",
    re.DOTALL | re.IGNORECASE,
)
BACKUP_RE = re.compile(
    r"<<<BACKUP>>>\s*(.*?)\s*<<<END_BACKUP>>>",
    re.DOTALL | re.IGNORECASE,
)
ROLLBACK_RE = re.compile(
    r"<<<ROLLBACK>>>\s*(.*?)\s*<<<END_ROLLBACK>>>",
    re.DOTALL | re.IGNORECASE,
)

# Paths the agent may touch (relative to app_root)
ALLOWED_PREFIXES = (
    "app/",
    "app\\",
    "docs/",
    "docs\\",
    "requirements.txt",
    "README.md",
    "FEATURES.md",
    "Launch.bat",
    "Launch.ps1",
)

# Never touch these even if under app/
FORBIDDEN_PARTS = (
    "data/",
    "data\\",
    ".venv/",
    ".venv\\",
    "__pycache__",
    ".git/",
)


def backups_dir() -> Path:
    d = data_dir() / "backups" / "self_improve"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _now_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def list_backups(limit: int = 30) -> list[dict[str, Any]]:
    out = []
    for p in sorted(backups_dir().glob("*.zip"), reverse=True)[:limit]:
        meta_path = p.with_suffix(".json")
        meta = {}
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                pass
        out.append(
            {
                "id": p.stem,
                "path": str(p.resolve()),
                "size": p.stat().st_size,
                "created": meta.get("created") or p.stem,
                "note": meta.get("note") or "",
                "files": meta.get("files") or [],
            }
        )
    return out


def _is_allowed_rel(rel: str) -> bool:
    rel = rel.replace("\\", "/").lstrip("./")
    if any(f in rel or rel.startswith(f.rstrip("/")) for f in ("data", ".venv", "__pycache__", ".git")):
        return False
    for part in FORBIDDEN_PARTS:
        if part.replace("\\", "/") in rel:
            return False
    for pref in ALLOWED_PREFIXES:
        p = pref.replace("\\", "/")
        if rel == p.rstrip("/") or rel.startswith(p):
            return True
    return False


def resolve_target(path_str: str) -> tuple[Path | None, str]:
    """Return (absolute path under app_root, relative) or (None, error)."""
    s = (path_str or "").strip().strip('"').strip("'")
    if not s:
        return None, "Empty path"
    root = app_root().resolve()
    p = Path(s)
    if not p.is_absolute():
        p = (root / s).resolve()
    else:
        p = p.resolve()
    try:
        rel = str(p.relative_to(root)).replace("\\", "/")
    except ValueError:
        return None, f"Path outside app root: {p}"
    if not _is_allowed_rel(rel):
        return None, f"Path not allowed for self-improve: {rel}"
    return p, rel


def create_backup(note: str = "", files: list[str] | None = None) -> dict[str, Any]:
    """
    Snapshot app source (or listed files) into a zip under data/backups/self_improve/.
    """
    root = app_root()
    bid = f"backup_{_now_slug()}"
    zip_path = backups_dir() / f"{bid}.zip"
    collected: list[str] = []

    def add_file(zf: zipfile.ZipFile, abs_path: Path, rel: str) -> None:
        if abs_path.is_file():
            zf.write(abs_path, rel)
            collected.append(rel)

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if files:
            for f in files:
                abs_p, rel_or_err = resolve_target(f)
                if abs_p and abs_p.is_file():
                    add_file(zf, abs_p, rel_or_err)
        else:
            # full safe snapshot of app package + key root files
            app_pkg = root / "app"
            if app_pkg.is_dir():
                for p in app_pkg.rglob("*"):
                    if not p.is_file():
                        continue
                    if "__pycache__" in p.parts or p.suffix == ".pyc":
                        continue
                    rel = str(p.relative_to(root)).replace("\\", "/")
                    if _is_allowed_rel(rel):
                        add_file(zf, p, rel)
            for name in ("requirements.txt", "README.md", "FEATURES.md", "Launch.bat", "Launch.ps1"):
                p = root / name
                if p.is_file():
                    add_file(zf, p, name)

    meta = {
        "id": bid,
        "created": datetime.now(timezone.utc).isoformat(),
        "note": note or "auto",
        "files": collected,
        "count": len(collected),
    }
    (backups_dir() / f"{bid}.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )
    return {"ok": True, "id": bid, "path": str(zip_path), "files": len(collected), "note": note}


def rollback(backup_id: str = "") -> dict[str, Any]:
    """Restore from a backup zip (latest if id empty)."""
    backs = list_backups(50)
    if not backs:
        return {"ok": False, "error": "No backups available"}
    target = None
    if backup_id:
        for b in backs:
            if b["id"] == backup_id or backup_id in b["id"]:
                target = b
                break
        if not target:
            return {"ok": False, "error": f"Backup not found: {backup_id}"}
    else:
        target = backs[0]

    zip_path = Path(target["path"])
    if not zip_path.is_file():
        return {"ok": False, "error": f"Missing zip: {zip_path}"}

    # Safety backup of current state before rollback
    pre = create_backup(note=f"pre-rollback-before-{target['id']}")
    root = app_root()
    restored = []
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for name in zf.namelist():
                if name.endswith("/"):
                    continue
                rel = name.replace("\\", "/")
                if not _is_allowed_rel(rel):
                    continue
                dest = root / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(name) as src, dest.open("wb") as out:
                    shutil.copyfileobj(src, out)
                restored.append(rel)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "pre_backup": pre.get("id")}

    return {
        "ok": True,
        "restored_from": target["id"],
        "files": restored,
        "count": len(restored),
        "pre_rollback_backup": pre.get("id"),
    }


def apply_patch(
    *,
    path: str,
    content: str,
    mode: str = "write",
    note: str = "",
    create_backup_first: bool = True,
) -> dict[str, Any]:
    """
    Write or append to an allowed file after backup.
    mode: write | append
    On exception after write attempt, auto-rollback that file from the backup just made.
    """
    abs_p, rel_or_err = resolve_target(path)
    if abs_p is None:
        return {"ok": False, "error": rel_or_err}

    backup_info = None
    if create_backup_first:
        backup_info = create_backup(
            note=note or f"before edit {rel_or_err}",
            files=[rel_or_err] if abs_p.is_file() else None,
        )
        # if file is new, still snapshot parent tree lightly
        if not abs_p.is_file() and not backup_info.get("files"):
            backup_info = create_backup(note=note or f"before create {rel_or_err}")

    old_bytes = abs_p.read_bytes() if abs_p.is_file() else None
    try:
        abs_p.parent.mkdir(parents=True, exist_ok=True)
        text = content if content is not None else ""
        if mode == "append" and abs_p.is_file():
            abs_p.write_text(abs_p.read_text(encoding="utf-8", errors="replace") + text, encoding="utf-8")
        else:
            abs_p.write_text(text, encoding="utf-8")
        # basic sanity: if .py, try compile
        if abs_p.suffix == ".py":
            src = abs_p.read_text(encoding="utf-8")
            compile(src, str(abs_p), "exec")
        return {
            "ok": True,
            "path": str(abs_p),
            "rel": rel_or_err,
            "mode": mode,
            "backup_id": (backup_info or {}).get("id"),
            "bytes": abs_p.stat().st_size,
        }
    except Exception as e:  # noqa: BLE001
        # restore file from memory first, then backup
        try:
            if old_bytes is not None:
                abs_p.write_bytes(old_bytes)
            elif abs_p.is_file():
                abs_p.unlink()
        except Exception:  # noqa: BLE001
            if backup_info and backup_info.get("id"):
                rollback(backup_info["id"])
        return {
            "ok": False,
            "error": f"Edit failed, restored previous content: {e}",
            "backup_id": (backup_info or {}).get("id"),
            "path": rel_or_err,
        }


def extract_self_improve_blocks(text: str) -> list[dict[str, str]]:
    """
    Block format:
    <<<SELF_IMPROVE>>>
    path: app/services/foo.py
    mode: write
    note: add feature
    ---
    file content here
    <<<END_SELF_IMPROVE>>>
    """
    out = []
    for m in SELF_IMPROVE_RE.finditer(text or ""):
        body = (m.group(1) or "").strip()
        if "---" in body:
            header, content = body.split("---", 1)
        else:
            lines = body.splitlines()
            header = "\n".join(lines[:5])
            content = "\n".join(lines[5:])
        meta: dict[str, str] = {"path": "", "mode": "write", "note": "", "content": content.strip("\n")}
        for line in header.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                k, v = k.strip().lower(), v.strip()
                if k in ("path", "file", "target"):
                    meta["path"] = v
                elif k == "mode":
                    meta["mode"] = v if v in ("write", "append") else "write"
                elif k == "note":
                    meta["note"] = v
        if meta["path"]:
            out.append(meta)
        elif body:
            # Malformed block (e.g. title:/files: without path:) — keep a stub so chat can warn
            meta["path"] = ""
            meta["note"] = (meta.get("note") or "") + " [invalid: need path: app/...]"
            meta["_invalid"] = "1"
            out.append(meta)
    return out


def extract_backup_notes(text: str) -> list[str]:
    return [(m.group(1) or "").strip() or "manual" for m in BACKUP_RE.finditer(text or "")]


def extract_rollback_ids(text: str) -> list[str]:
    return [(m.group(1) or "").strip() for m in ROLLBACK_RE.finditer(text or "")]


def run_self_improve_from_reply(reply: str) -> list[dict[str, Any]]:
    results = []
    for note in extract_backup_notes(reply):
        results.append({"kind": "backup", **create_backup(note=note)})
    for rid in extract_rollback_ids(reply):
        results.append({"kind": "rollback", **rollback(rid)})
    for patch in extract_self_improve_blocks(reply):
        if patch.get("_invalid") or not (patch.get("path") or "").strip():
            results.append(
                {
                    "kind": "patch",
                    "ok": False,
                    "error": "SELF_IMPROVE missing path: app/... (see tool instructions)",
                }
            )
            continue
        results.append(
            {
                "kind": "patch",
                **apply_patch(
                    path=patch["path"],
                    content=patch.get("content") or "",
                    mode=patch.get("mode") or "write",
                    note=patch.get("note") or "",
                ),
            }
        )
    return results


def tool_instructions() -> str:
    return """
## Self-improve this app (safe, with backup)

**Default:** SELF_IMPROVE blocks are **queued on the Patches page** for user Apply/Reject
(not written immediately). Prefer PATCH_REVIEW for the same flow.

You may still create BACKUP / ROLLBACK. Direct write only if the user enables
“Allow direct self-improve” in Settings.

### Create backup only
<<<BACKUP>>>
reason: before adding feature X
<<<END_BACKUP>>>

### Propose a source edit (review queue)
<<<SELF_IMPROVE>>>
path: app/services/example.py
mode: write
note: what you changed
---
# full new file content
<<<END_SELF_IMPROVE>>>

### Or explicit patch review
<<<PATCH_REVIEW>>>
path: app/services/example.py
mode: write
note: what you changed
---
# full new file content
<<<END_PATCH_REVIEW>>>

### Rollback to a backup id (or empty = latest)
<<<ROLLBACK>>>
backup_20260725_120000
<<<END_ROLLBACK>>>

Rules:
- Prefer small, focused edits. Always set a clear note.
- Never touch `data/`, `.venv/`, or paths outside the app.
- After apply + UI changes, tell the user to restart via Launch.bat.
- If unsure, create BACKUP first and describe the plan without editing.
""".strip()
