"""
Persistent worker attachments + text extraction for non-vision models.

IMAGE → OCR / image-to-text → TEXT → LLM (when model has no vision).
Never silently pretends a text-only model understood an image.
"""

from __future__ import annotations

import mimetypes
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.paths import data_dir
from app.core.services.data.storage import _read_json, _write_json, get_agent, save_agent


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def worker_attachments_dir(agent_id: str = "") -> Path:
    d = data_dir() / "worker_attachments"
    if agent_id:
        d = d / str(agent_id)[:32]
    d.mkdir(parents=True, exist_ok=True)
    return d


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"}
TEXT_EXTS = {
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".py",
    ".js",
    ".ts",
    ".html",
    ".css",
    ".xml",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".log",
    ".rst",
}
DOC_EXTS = {".pdf", ".docx", ".xlsx", ".xls"}


def _guess_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in TEXT_EXTS:
        return "text"
    if ext == ".pdf":
        return "pdf"
    if ext in {".docx"}:
        return "docx"
    if ext in {".xlsx", ".xls"}:
        return "spreadsheet"
    if ext in {".py", ".js", ".ts", ".go", ".rs", ".java", ".c", ".cpp"}:
        return "code"
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "file"


def model_has_vision(model_id: str, provider_id: str = "") -> bool:
    """Best-effort vision capability detection (honest, conservative)."""
    mid = (model_id or "").lower()
    # Known vision markers
    vision_markers = (
        "vision",
        "gpt-4o",
        "gpt-4-turbo",
        "gpt-4.1",
        "claude-3",
        "claude-4",
        "gemini",
        "llava",
        "pixtral",
        "qwen-vl",
        "qwen2-vl",
        "qwen2.5-vl",
        "grok-2-vision",
        "grok-vision",
        "o4-mini",
        "o3",
    )
    no_vision = (
        "coder",
        "code",
        "deepseek-chat",
        "deepseek-r1",
        "text-embedding",
        "tts",
        "whisper",
        "moderation",
    )
    if any(x in mid for x in no_vision) and "vl" not in mid and "vision" not in mid:
        # code models usually text-only unless explicitly VL
        if "vl" not in mid and "vision" not in mid and "4o" not in mid:
            if any(x in mid for x in ("coder", "code-", "codestral")):
                return False
    if any(x in mid for x in vision_markers):
        return True
    # Provider defaults
    try:
        from app.core.services.tools.capabilities import capabilities_for_provider

        caps = capabilities_for_provider(provider_id)
        v = caps.get("vision")
        if v is True:
            return True
        if v is False:
            return False
        # limited/unknown — only trust explicit model markers
    except Exception:  # noqa: BLE001
        pass
    return False


def model_capability_flags(
    model_id: str,
    provider_id: str = "",
) -> dict[str, bool]:
    """Display flags for worker config UI."""
    mid = (model_id or "").lower()
    pid = (provider_id or "").lower()
    text = True
    vision = model_has_vision(model_id, provider_id)
    tools = True
    if any(x in mid for x in ("embed", "tts", "whisper", "moderation", "dall-e", "flux", "image")):
        tools = False
        text = "embed" not in mid and "dall-e" not in mid and "flux" not in mid
    reasoning = any(
        x in mid
        for x in ("o1", "o3", "o4", "r1", "reason", "thinking", "qwq", "deepseek-r")
    )
    structured = tools  # OpenAI-compatible structured often available with tools
    audio = any(x in mid for x in ("audio", "whisper", "tts", "realtime"))
    embeddings = "embed" in mid
    try:
        from app.core.services.tools.capabilities import capabilities_for_provider

        caps = capabilities_for_provider(pid)
        if caps.get("chat") is False:
            text = False
    except Exception:  # noqa: BLE001
        pass
    return {
        "text": bool(text),
        "vision": bool(vision),
        "tool_calling": bool(tools),
        "structured_output": bool(structured),
        "reasoning": bool(reasoning),
        "audio": bool(audio),
        "embeddings": bool(embeddings),
    }


def format_capabilities_line(flags: dict[str, bool]) -> str:
    order = (
        ("text", "Text"),
        ("vision", "Vision"),
        ("tool_calling", "Tool Calling"),
        ("structured_output", "Structured Output"),
        ("reasoning", "Reasoning"),
        ("audio", "Audio"),
        ("embeddings", "Embeddings"),
    )
    parts = []
    for key, label in order:
        ok = flags.get(key)
        parts.append(f"{'✓' if ok else '✗'} {label}")
    return "  ".join(parts)


def extract_text_from_file(path: Path, *, max_chars: int = 80000) -> dict[str, Any]:
    """Extract plain text from common file types."""
    p = Path(path)
    if not p.is_file():
        return {"ok": False, "error": f"File not found: {path}", "text": "", "status": "missing"}
    ext = p.suffix.lower()
    try:
        if ext in TEXT_EXTS or ext in {".py", ".js", ".ts", ".go", ".rs", ".java", ".c", ".cpp", ".cs"}:
            raw = p.read_text(encoding="utf-8", errors="replace")
            return {
                "ok": True,
                "text": raw[:max_chars],
                "status": "extracted",
                "chars": min(len(raw), max_chars),
                "engine": "plain",
            }
        if ext in IMAGE_EXTS:
            from app.core.services.web.ocr_service import ocr_image

            res = ocr_image(p)
            if not res.get("ok"):
                return {
                    "ok": False,
                    "error": res.get("error") or "OCR failed",
                    "text": "",
                    "status": "ocr_failed",
                    "engine": res.get("engine") or "",
                }
            text = str(res.get("text") or "")
            return {
                "ok": True,
                "text": text[:max_chars],
                "status": "ocr_extracted",
                "chars": min(len(text), max_chars),
                "engine": res.get("engine") or "ocr",
                "path": res.get("path") or str(p),
            }
        if ext == ".pdf":
            try:
                # lightweight: try pypdf if available
                from pypdf import PdfReader  # type: ignore

                reader = PdfReader(str(p))
                chunks = []
                for page in reader.pages[:40]:
                    chunks.append(page.extract_text() or "")
                text = "\n".join(chunks)
                return {
                    "ok": bool(text.strip()),
                    "text": text[:max_chars],
                    "status": "extracted" if text.strip() else "empty",
                    "chars": min(len(text), max_chars),
                    "engine": "pypdf",
                }
            except Exception as e:  # noqa: BLE001
                return {
                    "ok": False,
                    "error": f"PDF extract failed: {e}",
                    "text": "",
                    "status": "extract_failed",
                }
        if ext == ".docx":
            try:
                import zipfile
                import re

                with zipfile.ZipFile(p) as z:
                    xml = z.read("word/document.xml").decode("utf-8", errors="replace")
                text = re.sub(r"<[^>]+>", " ", xml)
                text = re.sub(r"\s+", " ", text).strip()
                return {
                    "ok": bool(text),
                    "text": text[:max_chars],
                    "status": "extracted",
                    "chars": min(len(text), max_chars),
                    "engine": "docx_xml",
                }
            except Exception as e:  # noqa: BLE001
                return {
                    "ok": False,
                    "error": f"DOCX extract failed: {e}",
                    "text": "",
                    "status": "extract_failed",
                }
        # fallback: try utf-8
        raw = p.read_text(encoding="utf-8", errors="replace")
        if raw.strip():
            return {
                "ok": True,
                "text": raw[:max_chars],
                "status": "extracted",
                "chars": min(len(raw), max_chars),
                "engine": "fallback_text",
            }
        return {
            "ok": False,
            "error": f"Unsupported or empty file type: {ext or 'unknown'}",
            "text": "",
            "status": "unsupported",
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "text": "", "status": "error"}


def add_attachment_to_agent(
    agent_id: str,
    source_path: str | Path,
    *,
    copy_file: bool = True,
) -> dict[str, Any]:
    """Copy (optional) and register a persistent attachment on an agent profile."""
    ag = get_agent(agent_id)
    if not ag:
        raise ValueError("Agent not found")
    src = Path(source_path).expanduser()
    if not src.is_file():
        raise ValueError(f"File not found: {src}")
    dest = src
    if copy_file:
        dest_dir = worker_attachments_dir(agent_id)
        dest = dest_dir / f"{uuid.uuid4().hex[:10]}_{src.name}"
        shutil.copy2(src, dest)
    entry = {
        "id": str(uuid.uuid4())[:12],
        "name": src.name,
        "path": str(dest.resolve()),
        "source": str(src.resolve()),
        "type": _guess_type(src),
        "size": int(src.stat().st_size),
        "status": "pending",
        "chars": 0,
        "engine": "",
        "error": "",
        "added_at": _now(),
    }
    atts = list(ag.get("attachments") or [])
    atts.append(entry)
    ag["attachments"] = atts
    save_agent(ag)
    return entry


def remove_attachment(agent_id: str, attachment_id: str) -> bool:
    ag = get_agent(agent_id)
    if not ag:
        return False
    atts = list(ag.get("attachments") or [])
    new = [a for a in atts if str(a.get("id")) != str(attachment_id)]
    if len(new) == len(atts):
        return False
    ag["attachments"] = new
    save_agent(ag)
    return True


def process_attachments_for_llm(
    attachments: list[dict[str, Any]] | None,
    *,
    model_id: str = "",
    provider_id: str = "",
) -> dict[str, Any]:
    """
    Build attachment text for LLM.

    For images when model lacks vision: OCR → text.
    Returns {text, items, vision_capable, warnings}.
    """
    vision = model_has_vision(model_id, provider_id)
    items: list[dict[str, Any]] = []
    parts: list[str] = []
    warnings: list[str] = []

    for a in attachments or []:
        if not isinstance(a, dict):
            continue
        path = Path(str(a.get("path") or a.get("source") or ""))
        name = a.get("name") or path.name or "file"
        ftype = a.get("type") or _guess_type(path) if path.suffix else "file"
        row = dict(a)
        row["name"] = name
        row["type"] = ftype

        if ftype == "image" and vision:
            row["status"] = "vision_passthrough"
            row["processing"] = "Image → vision model (raw image path noted; text extract optional)"
            # Still extract OCR as secondary context when cheap
            extracted = extract_text_from_file(path)
            if extracted.get("ok") and extracted.get("text"):
                row["status"] = "vision_plus_ocr"
                row["chars"] = extracted.get("chars") or 0
                row["engine"] = extracted.get("engine") or ""
                parts.append(
                    f"### Attachment (image, vision model): {name}\n"
                    f"(OCR secondary extract, {row['chars']} chars)\n"
                    f"{extracted['text'][:20000]}"
                )
            else:
                parts.append(
                    f"### Attachment (image, vision model): {name}\n"
                    f"Path: {path}\n"
                    "(Model is vision-capable; image path recorded. "
                    "OCR secondary extract unavailable.)"
                )
                warnings.append(f"{name}: vision model — no OCR secondary text")
        elif ftype == "image" and not vision:
            extracted = extract_text_from_file(path)
            row["status"] = extracted.get("status") or "ocr_failed"
            row["chars"] = extracted.get("chars") or 0
            row["engine"] = extracted.get("engine") or ""
            row["error"] = extracted.get("error") or ""
            row["processing"] = "Image → OCR / Image-to-Text → Text → LLM"
            if extracted.get("ok") and extracted.get("text"):
                parts.append(
                    f"### Attachment (image → OCR for text-only model): {name}\n"
                    f"Processing: Image → OCR ({row['engine']}) → {row['chars']} characters\n"
                    f"{extracted['text'][:20000]}"
                )
            else:
                msg = extracted.get("error") or "cannot extract text"
                parts.append(
                    f"### Attachment (image, text-only model): {name}\n"
                    f"⚠ Cannot process for this worker: {msg}\n"
                    "Model is not vision-capable and OCR failed."
                )
                warnings.append(f"{name}: {msg}")
        else:
            extracted = extract_text_from_file(path)
            row["status"] = extracted.get("status") or "error"
            row["chars"] = extracted.get("chars") or 0
            row["engine"] = extracted.get("engine") or ""
            row["error"] = extracted.get("error") or ""
            row["processing"] = "File → text extract → LLM"
            if extracted.get("ok") and extracted.get("text"):
                parts.append(
                    f"### Attachment ({ftype}): {name}\n"
                    f"Extracted {row['chars']} characters via {row['engine']}\n"
                    f"{extracted['text'][:20000]}"
                )
            else:
                parts.append(
                    f"### Attachment ({ftype}): {name}\n"
                    f"⚠ Cannot process: {extracted.get('error') or 'unknown'}"
                )
                warnings.append(f"{name}: {extracted.get('error') or 'failed'}")
        items.append(row)

    return {
        "text": "\n\n".join(parts),
        "items": items,
        "vision_capable": vision,
        "warnings": warnings,
        "attachment_count": len(items),
    }


def sync_attachment_status_to_agent(agent_id: str, items: list[dict[str, Any]]) -> None:
    """Write back processing status onto agent attachment records."""
    ag = get_agent(agent_id)
    if not ag:
        return
    by_id = {str(i.get("id")): i for i in items if i.get("id")}
    atts = list(ag.get("attachments") or [])
    for a in atts:
        aid = str(a.get("id") or "")
        if aid in by_id:
            src = by_id[aid]
            a["status"] = src.get("status") or a.get("status")
            a["chars"] = src.get("chars") or 0
            a["engine"] = src.get("engine") or ""
            a["error"] = src.get("error") or ""
            a["processing"] = src.get("processing") or ""
    ag["attachments"] = atts
    save_agent(ag)
