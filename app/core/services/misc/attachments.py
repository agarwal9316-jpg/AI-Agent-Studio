"""Read user-selected files for chat — no hard skip by default; large files ask the user."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

# Soft threshold only — triggers user choice, not auto-deny
LARGE_FILE_BYTES = 400_000  # ~400 KB prompt to choose

# Choice values returned by ask_large_file callback
CHOICE_FULL = "full"
CHOICE_HEAD = "head"
CHOICE_TAIL = "tail"
CHOICE_BOTH = "both"  # head + tail
CHOICE_SKIP = "skip"
CHOICE_PATH_ONLY = "path_only"

HEAD_CHARS = 80_000
TAIL_CHARS = 80_000


def describe_attachment(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    return {
        "path": str(p.resolve()) if p.exists() else str(p),
        "name": p.name,
        "size": p.stat().st_size if p.is_file() else 0,
    }


def _decode_bytes(raw: bytes) -> tuple[str, str]:
    for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace"), "latin-1-replace"


def load_attachment_text(
    path: str | Path,
    *,
    mode: str = CHOICE_FULL,
    ask_large: Callable[[str, int], str] | None = None,
) -> dict[str, Any]:
    """
    Load one file.
    mode: full|head|tail|both|skip|path_only
    If file is large and ask_large is provided, user decides mode.
    """
    p = Path(path)
    info: dict[str, Any] = {
        "name": p.name,
        "path": str(p.resolve()) if p.exists() else str(p),
        "ok": False,
        "kind": "missing",
        "text": "",
        "note": "",
        "mode": mode,
    }
    if not p.is_file():
        info["note"] = "File not found"
        return info

    size = p.stat().st_size
    info["size"] = size

    chosen = mode
    if size > LARGE_FILE_BYTES and ask_large is not None:
        try:
            chosen = ask_large(str(p), size) or CHOICE_FULL
        except Exception:  # noqa: BLE001
            chosen = CHOICE_FULL
        info["mode"] = chosen

    if chosen == CHOICE_SKIP:
        info["kind"] = "skipped"
        info["note"] = "Skipped by user choice"
        info["ok"] = True
        return info

    if chosen == CHOICE_PATH_ONLY:
        info["kind"] = "path_only"
        info["note"] = f"Path only (user choice). Size={size} bytes."
        info["ok"] = True
        return info

    # No default size refusal — always read (may use a lot of RAM for huge files if FULL)
    try:
        raw = p.read_bytes()
    except OSError as e:
        info["note"] = str(e)
        return info

    # binary heuristic only for note, still try decode
    if b"\x00" in raw[:8192] and chosen == CHOICE_FULL:
        info["kind"] = "binary"
        info["note"] = (
            f"Binary-like file ({size} bytes). Decoded with latin-1 fallback. "
            "User can re-attach with path_only if preferred."
        )

    text, enc = _decode_bytes(raw)
    info["encoding"] = enc

    if chosen == CHOICE_HEAD:
        text = text[:HEAD_CHARS]
        info["note"] = (info.get("note") or "") + f" Included first {HEAD_CHARS} chars."
    elif chosen == CHOICE_TAIL:
        text = text[-TAIL_CHARS:] if len(text) > TAIL_CHARS else text
        info["note"] = (info.get("note") or "") + f" Included last {TAIL_CHARS} chars."
    elif chosen == CHOICE_BOTH:
        if len(text) > HEAD_CHARS + TAIL_CHARS:
            text = (
                text[:HEAD_CHARS]
                + "\n\n...[middle omitted by user choice]...\n\n"
                + text[-TAIL_CHARS:]
            )
            info["note"] = (info.get("note") or "") + " Head+tail included."
    # FULL: entire file, no truncation

    info["kind"] = info.get("kind") or "text"
    info["text"] = text
    info["ok"] = True
    return info


def is_stray_attachment(path: str | Path) -> bool:
    """True for dirs, missing paths, or clipboard leftovers like Desktop\\AI."""
    try:
        p = Path(path)
        if not str(path or "").strip():
            return True
        if not p.exists() or p.is_dir():
            return True
        if p.name.lower() in {"ai", "ai working"}:
            return True
    except Exception:  # noqa: BLE001
        return True
    return False


def sanitize_attachment_paths(paths: list[str] | None) -> list[str]:
    out: list[str] = []
    for raw in paths or []:
        if is_stray_attachment(raw):
            continue
        try:
            out.append(str(Path(raw)))
        except Exception:  # noqa: BLE001
            continue
    return out


def format_attachments_block(
    paths: list[str],
    *,
    ask_large: Callable[[str, int], str] | None = None,
    per_file_modes: dict[str, str] | None = None,
) -> str:
    """Build attachment section. No file-count hard cap by default."""
    paths = sanitize_attachment_paths(paths)
    if not paths:
        return ""

    parts: list[str] = ["\n\n---\n### Attached files\n"]
    modes = per_file_modes or {}

    for i, path in enumerate(paths, start=1):
        mode = modes.get(path, CHOICE_FULL)
        loaded = load_attachment_text(path, mode=mode, ask_large=ask_large)
        header = f"\n#### Attachment {i}: `{loaded['name']}`\nPath: `{loaded['path']}`\n"
        if loaded.get("size") is not None:
            header += f"Size: {loaded.get('size')} bytes | mode: {loaded.get('mode')}\n"
        parts.append(header)
        if loaded.get("note"):
            parts.append(str(loaded["note"]) + "\n")
        body = loaded.get("text") or ""
        if body:
            parts.append(f"```\n{body}\n```\n")

    return "".join(parts)
