"""Lightweight markdown → render segments for CustomTkinter chat bubbles.

Supports: fenced code, headings, nested bullets, tables, **bold** stripped for CTk.
No HTML execution.
"""

from __future__ import annotations

import re
from typing import Any


def parse_markdown_lite(text: str) -> list[dict[str, Any]]:
    """
    Parse text into segments:
      heading | code | bullet | table | para
    bullet has indent level (0-based).
    table has rows: list[list[str]]
    """
    text = (text or "").replace("\r\n", "\n")
    if not text.strip():
        return []

    segments: list[dict[str, Any]] = []
    fence = chr(96) * 3  # ```
    fence_re = re.compile(
        rf"({re.escape(fence)}([\w+-]*)\r?\n([\s\S]*?){re.escape(fence)})"
    )
    parts: list[str] = []
    last = 0
    for m in fence_re.finditer(text):
        if m.start() > last:
            parts.append(text[last : m.start()])
        parts.append(m.group(0))
        last = m.end()
    if last < len(text):
        parts.append(text[last:])
    if not parts:
        parts = [text]

    for part in parts:
        if not part:
            continue
        m = re.match(
            rf"{re.escape(fence)}([\w+-]*)\r?\n([\s\S]*?){re.escape(fence)}\s*$",
            part,
        )
        if m:
            segments.append(
                {
                    "type": "code",
                    "lang": m.group(1) or "",
                    "text": m.group(2).rstrip("\n"),
                }
            )
            continue
        for block in re.split(r"\n{2,}", part):
            block = block.strip("\n")
            if not block.strip():
                continue
            lines = block.split("\n")
            # Table: | a | b | and separator |---|
            if _looks_like_table(lines):
                rows = _parse_table(lines)
                if rows:
                    segments.append({"type": "table", "rows": rows})
                    continue
            # All bullet lines (including nested)?
            if all(
                re.match(r"^\s*([-*•]|\d+\.)\s+", ln) or not ln.strip()
                for ln in lines
                if ln.strip()
            ):
                for ln in lines:
                    if not ln.strip():
                        continue
                    indent, body = _bullet_indent(ln)
                    segments.append(
                        {
                            "type": "bullet",
                            "text": _inline_clean(body),
                            "indent": indent,
                        }
                    )
                continue
            # Single heading line
            hm = re.match(r"^(#{1,3})\s+(.+)$", lines[0].strip())
            if hm and len(lines) == 1:
                segments.append(
                    {
                        "type": "heading",
                        "level": len(hm.group(1)),
                        "text": _inline_clean(hm.group(2)),
                    }
                )
                continue
            # Mixed block line-by-line
            cleaned_lines: list[str] = []
            for ln in lines:
                hm2 = re.match(r"^(#{1,3})\s+(.+)$", ln.strip())
                if hm2:
                    if cleaned_lines:
                        segments.append(
                            {"type": "para", "text": _inline_clean("\n".join(cleaned_lines))}
                        )
                        cleaned_lines = []
                    segments.append(
                        {
                            "type": "heading",
                            "level": len(hm2.group(1)),
                            "text": _inline_clean(hm2.group(2)),
                        }
                    )
                elif re.match(r"^\s*([-*•]|\d+\.)\s+", ln):
                    if cleaned_lines:
                        segments.append(
                            {"type": "para", "text": _inline_clean("\n".join(cleaned_lines))}
                        )
                        cleaned_lines = []
                    indent, body = _bullet_indent(ln)
                    segments.append(
                        {
                            "type": "bullet",
                            "text": _inline_clean(body),
                            "indent": indent,
                        }
                    )
                else:
                    cleaned_lines.append(ln)
            if cleaned_lines:
                segments.append({"type": "para", "text": _inline_clean("\n".join(cleaned_lines))})
    return segments or [{"type": "para", "text": _inline_clean(text)}]


def _bullet_indent(line: str) -> tuple[int, str]:
    """Return (indent_level, text with bullet)."""
    m = re.match(r"^(\s*)([-*•]|\d+\.)\s+(.*)$", line)
    if not m:
        return 0, line.strip()
    spaces = len(m.group(1).expandtabs(2).replace("\t", "  "))
    level = min(4, spaces // 2)
    return level, "• " + m.group(3).strip()


def _looks_like_table(lines: list[str]) -> bool:
    if len(lines) < 2:
        return False
    pipe_lines = [ln for ln in lines if ln.strip().startswith("|") and ln.strip().endswith("|")]
    if len(pipe_lines) < 2:
        # also allow without trailing |
        pipe_lines = [ln for ln in lines if ln.count("|") >= 2]
    if len(pipe_lines) < 2:
        return False
    # separator row with ---
    for ln in lines[1:3]:
        if re.match(r"^\s*\|?[\s:\-|]+\|?\s*$", ln) and "-" in ln:
            return True
    return False


def _parse_table(lines: list[str]) -> list[list[str]]:
    rows: list[list[str]] = []
    for ln in lines:
        if re.match(r"^\s*\|?[\s:\-|]+\|?\s*$", ln) and "-" in ln:
            continue  # skip alignment row
        if ln.count("|") < 1:
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if cells:
            rows.append([_inline_clean(c) for c in cells])
    return rows


def _inline_clean(s: str) -> str:
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"__(.+?)__", r"\1", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", s)
    return s
