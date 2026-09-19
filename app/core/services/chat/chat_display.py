"""Chat history display helpers — strip tool markup, hide tool-intent bubbles.

Extracted from chat.py so UI components can import without loading the full
send/stream pipeline.
"""
from __future__ import annotations

import re
from typing import Any

_TOOL_BLOCK_RE = re.compile(r"<<<[A-Z][A-Z0-9_]*>>>", re.I)
_STICKY_ECHO = "Understood. I will use the sticky context"
# Also detect XML / JSON tool pseudo-calls as "tool intent"
_PSEUDO_TOOL_RE = re.compile(
    r"(<\s*tool_call\b)|(\"name\"\s*:\s*\"run_terminal\")|"
    r"(\{\s*\"terminal\"\s*:)|(\{\s*\"web_search\"\s*:)|"
    r"(\"action\"\s*:\s*\"search_replace\")",
    re.I,
)
_UNFINISHED_TALK_RE = re.compile(
    r"\b("
    r"let me|"
    r"i(?:'ll| will) (?:now )?(?:add|fix|edit|write|check|open|run|continue|create)|"
    r"next i(?:'ll| will)|"
    r"working on it|"
    r"one moment|"
    r"hang on"
    r")\b",
    re.I,
)


_ECHO_STUB_RE = re.compile(
    r"^\[(?:tool work done|omitted tool dump)\b",
    re.I,
)


def _is_echo_stub(text: str) -> bool:
    """True when the model copied our context-shrink placeholder as the answer."""
    t = (text or "").strip()
    if not t:
        return False
    if _ECHO_STUB_RE.match(t):
        return True
    low = t.lower()
    return "details omitted from context" in low and len(t) < 220


def _looks_unfinished_work(text: str) -> bool:
    """True when the model announced the next step but emitted no tool."""
    t = (text or "").strip()
    if not t or len(t) > 6000:
        return False
    if _is_echo_stub(t):
        return True
    if "<<<" in t and ">>>" in t:
        return False
    if _PSEUDO_TOOL_RE.search(t):
        return False
    return bool(_UNFINISHED_TALK_RE.search(t))


def strip_tool_blocks_for_display(content: str) -> str:
    """Remove tool blocks / pseudo tool markup; leave human prose."""
    text = content or ""
    text = re.sub(
        r"<<<[A-Z][A-Z0-9_]*>>>.*?<<<END_[A-Z0-9_]+>>>",
        "",
        text,
        flags=re.I | re.S,
    )
    text = re.sub(r"<<<[A-Z][A-Z0-9_]*>>>[\s\S]*$", "", text, flags=re.I)
    text = re.sub(r"\$\w+\s*=\s*@['\"][\s\S]*", "", text)
    text = re.sub(
        r"<\s*tool_call\b[^>]*>.*?<\s*/\s*tool_call\s*>",
        "",
        text,
        flags=re.I | re.S,
    )
    text = re.sub(r"<\s*tool_call\b[^>]*>[\s\S]*", "", text, flags=re.I)
    text = re.sub(r"<\s*/\s*tool_call\s*>", "", text, flags=re.I)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def has_tool_call_markup(content: str) -> bool:
    t = content or ""
    if _TOOL_BLOCK_RE.search(t):
        return True
    if _PSEUDO_TOOL_RE.search(t):
        return True
    return False


def looks_like_file_dump_for_ui(content: str) -> bool:
    t = (content or "").strip()
    if len(t) < 400:
        return False
    if has_tool_call_markup(t):
        return True
    if t.count("\n") > 40 and len(t) > 2000:
        return True
    return False


def looks_like_tool_dump(content: str) -> bool:
    t = (content or "").strip()
    if not t:
        return False
    if has_tool_call_markup(t):
        return True
    if _is_echo_stub(t):
        return True
    if looks_like_file_dump_for_ui(t):
        return True
    return False


def is_tool_intent_only_assistant(content: str) -> bool:
    text = content or ""
    if looks_like_tool_dump(text):
        return True
    if not has_tool_call_markup(text):
        return False
    prose = strip_tool_blocks_for_display(text)
    prose = re.sub(r"\s+", " ", prose).strip()
    return len(prose) < 80


def finalize_history_for_display(hist: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mark tool-intent assistant rows as hidden for the chat UI."""
    if not hist:
        return []
    n = len(hist)
    hide_indices: set[int] = set()
    i = 0
    while i < n:
        j = i + 1
        asst_idxs: list[int] = []
        tool_after_asst = False
        while j < n:
            role = (hist[j].get("role") or "").lower()
            if role == "user":
                break
            if role == "assistant":
                asst_idxs.append(j)
            elif role == "tool":
                tool_after_asst = True
            j += 1
        if len(asst_idxs) == 1 and tool_after_asst:
            only = asst_idxs[0]
            if is_tool_intent_only_assistant(str(hist[only].get("content") or "")):
                prose = strip_tool_blocks_for_display(str(hist[only].get("content") or ""))
                prose = re.sub(r"\s+", " ", prose).strip()
                if len(prose) < 40:
                    hide_indices.add(only)
        i = j if j > i else i + 1

    out: list[dict[str, Any]] = []
    for idx, m in enumerate(hist):
        mm = dict(m)
        if mm.get("role") == "assistant":
            content = mm.get("content") or ""
            if _STICKY_ECHO in content and len(content) < 280:
                continue
            if idx in hide_indices or mm.get("_tool_round") or mm.get("_hide_ui"):
                mm["_hide_ui"] = True
                mm["_tool_intent_only"] = True
                mm["_tool_round"] = True
            elif is_tool_intent_only_assistant(content):
                later_final = any(
                    (
                        hist[k].get("role") == "assistant"
                        and not hist[k].get("_streaming")
                        and k not in hide_indices
                        and k > idx
                        and not is_tool_intent_only_assistant(
                            str(hist[k].get("content") or "")
                        )
                    )
                    for k in range(idx + 1, n)
                )
                later_any_asst = any(
                    (
                        hist[k].get("role") == "assistant"
                        and not hist[k].get("_streaming")
                        and k not in hide_indices
                        and k > idx
                    )
                    for k in range(idx + 1, n)
                )
                if later_final or later_any_asst:
                    mm["_hide_ui"] = True
                    mm["_tool_intent_only"] = True
                    mm["_tool_round"] = True
            if not mm.get("_hide_ui") and has_tool_call_markup(content):
                mm["_strip_tools_ui"] = True
        out.append(mm)
    return out
