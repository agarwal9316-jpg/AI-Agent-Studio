"""
Detect unverified success claims in assistant text when tools did not succeed.
"""

from __future__ import annotations

import re
from typing import Any

_SUCCESS_CLAIMS = re.compile(
    r"("
    r"\bsuccessfully (created|saved|wrote|generated|installed|deleted|updated|fixed)\b|"
    r"\b(file|image|screenshot|patch) (has been |was )?(created|saved|generated|written|applied)\b|"
    r"\bsaved as\s+[`']?[\w.\-\\/]+|"
    r"\bI('ve| have) (created|saved|generated|written|fixed|wrote)\b|"
    r"\bI (created|saved|generated|wrote|fixed)\b|"
    r"\b(the )?(image|file|screenshot) was (created|saved|generated|written)\b|"
    r"\bdone\.?\s*$|"
    r"\ball set\b"
    r")",
    re.I | re.M,
)

_TOOL_OK_HINTS = re.compile(
    r"\b(ok|success|exit_code[\"']?\s*:\s*0|generated image ✓|auto-generated image)\b",
    re.I,
)


def looks_like_success_claim(text: str) -> bool:
    return bool(_SUCCESS_CLAIMS.search(text or ""))


def tool_messages_indicate_success(tool_msgs: list[dict[str, Any]]) -> bool:
    if not tool_msgs:
        return False
    for m in tool_msgs:
        role = (m.get("role") or "").lower()
        if role == "error":
            continue
        content = str(m.get("content") or "")
        if m.get("images"):
            return True
        if _TOOL_OK_HINTS.search(content):
            return True
        if role in ("screenshot",) and "fail" not in content.lower():
            return True
    # any non-error tool message counts as "something ran"
    return any((m.get("role") or "").lower() != "error" for m in tool_msgs)


def verification_note(
    assistant_text: str,
    *,
    tool_msgs: list[dict[str, Any]],
    used_tool: bool,
) -> str | None:
    """
    Return a system_note content string if the assistant claimed success
    without evidence, else None.
    """
    if not looks_like_success_claim(assistant_text):
        return None
    if used_tool and tool_messages_indicate_success(tool_msgs):
        return None
    if used_tool:
        # tools ran but no clear success / only errors
        errs = [m for m in tool_msgs if (m.get("role") or "").lower() == "error"]
        if errs:
            return (
                "### Unverified claim\n"
                "The assistant described success, but tool results include **errors**. "
                "Treat the claim as unconfirmed until fixed."
            )
        return None
    return (
        "### Unverified claim\n"
        "The assistant described completing work, but **no tools reported success** "
        "in this turn (no terminal/image/file tool evidence). "
        "Do not trust file/image claims until a tool succeeds."
    )
