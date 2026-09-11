"""Redact secrets from logs, exports, and displayed tool output."""

from __future__ import annotations

import re
from typing import Any

# API keys, bearer tokens, common secret patterns
_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}\b"),
    re.compile(r"\bsk-or-v1-[A-Za-z0-9_\-]{8,}\b"),
    re.compile(r"\bsk-proj-[A-Za-z0-9_\-]{8,}\b"),
    re.compile(r"(?i)(api[_-]?key|token|secret|password|authorization)\s*[:=]\s*['\"]?([^\s'\"]{8,})"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*"),
    re.compile(r"(?i)x-api-key\s*[:=]\s*\S+"),
]


def redact_text(text: str) -> str:
    if not text:
        return text
    out = str(text)
    for pat in _PATTERNS:
        if pat.groups:
            out = pat.sub(lambda m: f"{m.group(1)}=***REDACTED***" if m.lastindex and m.lastindex >= 1 else "***REDACTED***", out)
        else:
            out = pat.sub("***REDACTED***", out)
    return out


def redact_obj(obj: Any) -> Any:
    if isinstance(obj, str):
        return redact_text(obj)
    if isinstance(obj, dict):
        return {k: redact_obj(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_obj(x) for x in obj]
    return obj
