"""Task achieved vs open, plus LLM idle/working — used to auto-continue."""

from __future__ import annotations

import re
from typing import Any

TASK_NONE = "none"
TASK_OPEN = "open"
TASK_ACHIEVED = "achieved"
TASK_BLOCKED = "blocked"

LLM_IDLE = "idle"
LLM_WORKING = "working"
LLM_PAUSED = "paused"
LLM_ERROR = "error"

AUTO_PREFIX = "[auto]"
MAX_AUTO_CONTINUES = 30
MIN_AUTO_GAP_SEC = 8.0
MIN_ERROR_RETRY_SEC = 15.0
MAX_ERROR_RETRIES = 8

_JUNK_USER = re.compile(
    r"^(hi+|hello|hey|ok|okay|thanks|thank you|\?+|what\??|continue\.?)\s*$",
    re.I,
)
_USER_MARK_DONE = re.compile(
    r"^\s*(done|stop|that'?s all|task complete|mark(?:ed)? done|cancel task)\s*[.!]?\s*$",
    re.I,
)
_USER_REOPEN = re.compile(
    r"^\s*(not done|still broken|keep going|reopen task|task is (?:not |still )?open)\b",
    re.I,
)


def is_auto_continue_text(text: str) -> bool:
    t = (text or "").lstrip()
    return t.startswith(AUTO_PREFIX)


def auto_continue_text(goal: str = "", ledger: dict | None = None) -> str:
    g = re.sub(r"\s+", " ", (goal or "").strip())
    rules = (
        "Use the Findings list. Do not rediscover a listed error. "
        "Then ONE new action (not the same dir/read as last time). "
        "Quote every Windows path that has spaces. "
        "Use <<<READ_FILE>>> for source, not type/Get-Content. "
        "After a launch, emit <<<WINDOWS>>> or SCREENSHOT and only claim done if the GUI window is visible. "
        "Emit <<<SET_GOAL>>>…<<<END_SET_GOAL>>> if the goal changed. "
        "Emit <<<FINDING>>>one line<<<END_FINDING>>> for any new fact."
    )
    extra = ""
    if ledger:
        try:
            from app.core.services.chat.task_ledger import format_for_prompt, last_error_text

            err = last_error_text(ledger)
            if err:
                extra += f"\nLast error (do not rediscover): {err}"
            block = format_for_prompt(ledger, max_items=8)
            if block:
                extra += "\n" + block
        except Exception:  # noqa: BLE001
            extra = ""
    if g:
        return f"{AUTO_PREFIX} Live goal is still open: {g}\nContinue THAT goal. {rules}{extra}"
    return (
        f"{AUTO_PREFIX} Task is still open and the model went idle. "
        f"Continue the user's task now. {rules}{extra}"
    )


def _plain(msg: dict[str, Any] | None) -> str:
    if not msg:
        return ""
    return str(msg.get("content") or "").strip()


def last_user_message(messages: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    for m in reversed(messages or []):
        if (m.get("role") or "") == "user":
            return m
    return None


def last_assistant_message(messages: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    for m in reversed(messages or []):
        role = (m.get("role") or "")
        if role == "assistant" and not (
            m.get("_hide_ui") or m.get("_tool_round") or m.get("_streaming")
        ):
            return m
    return None


def has_user_goal(messages: list[dict[str, Any]] | None) -> bool:
    for m in messages or []:
        if (m.get("role") or "") != "user":
            continue
        t = _plain(m)
        if not t or is_auto_continue_text(t) or _JUNK_USER.match(t):
            continue
        if t.lower().startswith("continue.") and len(t) < 20:
            continue
        if len(t) >= 12:
            return True
    return False


def _assistant_unfinished(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    try:
        from app.core.services.chat.chat import (
            _is_echo_stub,
            _looks_unfinished_work,
            looks_like_tool_dump,
        )
    except Exception:  # noqa: BLE001
        return len(t) < 8
    if _is_echo_stub(t) or looks_like_tool_dump(t):
        return True
    if _looks_unfinished_work(t):
        return True
    if t.startswith("<<<") and ">>>" in t[:80]:
        return True
    return False


def infer_task_status(
    messages: list[dict[str, Any]] | None,
    *,
    user_pin: str | None = None,
    auto_count: int = 0,
) -> str:
    """User pin wins. Otherwise: no goal → none; 8 idle loops → blocked; else open."""
    pin = (user_pin or "").strip().lower()
    if pin in (TASK_ACHIEVED, TASK_OPEN, TASK_BLOCKED):
        return pin
    last_u = _plain(last_user_message(messages))
    if last_u and _USER_MARK_DONE.match(last_u):
        return TASK_ACHIEVED
    if last_u and _USER_REOPEN.search(last_u):
        return TASK_OPEN
    if not has_user_goal(messages):
        return TASK_NONE
    if auto_count >= MAX_AUTO_CONTINUES:
        return TASK_BLOCKED
    return TASK_OPEN


def _clip_goal(text: str, n: int = 220) -> str:
    return _sanitize_goal(text, n) or re.sub(r"\s+", " ", (text or "").strip())[:n]


_SET_GOAL_RE = re.compile(
    r"<<<SET_GOAL>>>\s*(?:goal\s*:\s*)?(.*?)\s*(?:<<<END_SET_GOAL>>>|$)",
    re.I | re.S,
)
_ACTION_GOAL_RE = re.compile(
    r'\{\s*"action"\s*:\s*"set_goal"\s*,\s*"goal"\s*:\s*"((?:\\.|[^"\\])*)"',
    re.I | re.S,
)
# "## My Goal: …" / "Current goal: …" / mid-sentence "your original goal was: …"
_DECLARE_GOAL_RE = re.compile(
    r"(?:#{1,4}\s+)?"
    r"\*{0,2}\s*"
    r"(?:(?:your|the|my)\s+)?"
    r"(?:current\s+|live\s+|original\s+)?"
    r"goal(?:\s+was)?"
    r"\s*[:\-–*]+\s*"
    r"\*{0,2}\s*"
    r"([^\n]{8,280})",
    re.I,
)
_ASK_ABOUT_GOAL_RE = re.compile(
    r"\b(what should be your goal|what is (?:the |your )?goal|based on chat history)\b",
    re.I,
)
_BAD_GOAL_RE = re.compile(
    r"working with tools|watch live|details omitted|ask anything|empty message|"
    r"none yet|one short (?:concrete )?objective|one short sentence|"
    r"the live objective|the real current objective",
    re.I,
)
_META_GOAL_ONLY_RE = re.compile(
    r"^(update|set|change|edit|show|tell) (the |your |my )?goal\b.*$",
    re.I,
)


def _sanitize_goal(text: str, n: int = 220) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    t = t.strip("*\"'`“” ")
    t = re.sub(r"^(?:current |live |my |the )?(?:goal|task)\s*[:\-–]\s*", "", t, flags=re.I)
    if len(t) < 8:
        return ""
    if _BAD_GOAL_RE.search(t) or _META_GOAL_ONLY_RE.match(t) or _ASK_ABOUT_GOAL_RE.search(t):
        return ""
    if t.lower().startswith("continue") and len(t) < 24:
        return ""
    if len(t) <= n:
        return t
    return t[: n - 1] + "…"


def extract_explicit_goal(text: str) -> str:
    """Goal the model set via <<<SET_GOAL>>> or {\"action\":\"set_goal\"}."""
    raw = text or ""
    m = _SET_GOAL_RE.search(raw)
    if m:
        g = _sanitize_goal(m.group(1), 280)
        if g:
            return g
    m = _ACTION_GOAL_RE.search(raw)
    if m:
        g = _sanitize_goal(m.group(1).replace('\\"', '"'), 280)
        if g:
            return g
    return ""


def extract_declared_goal(text: str) -> str:
    """Goal the model stated in prose (Current goal: … / ## My Goal: …)."""
    t = (text or "").strip()
    if not t:
        return ""
    # Tool-only dumps have no usable prose; mixed replies still can.
    scan = t
    if looks_like_file_dumpish(t) and "goal" not in t.lower():
        return ""
    if t.startswith("<<<") and "goal" not in t.lower()[:200]:
        return ""
    best = ""
    for m in _DECLARE_GOAL_RE.finditer(scan):
        g = _sanitize_goal(m.group(1), 280)
        if g:
            best = g
    return best


def looks_like_file_dumpish(text: str) -> bool:
    t = text or ""
    return "<<<" in t[:40] or "$content" in t[:80] or len(t) > 4000


def current_goal_text(
    messages: list[dict[str, Any]] | None,
    *,
    override: str | None = None,
    user_pin: bool = False,
) -> str:
    """LLM-set / declared goal, then latest real user ask. Pinned override wins."""
    ov = _sanitize_goal(override or "")
    if user_pin and ov:
        return ov
    last_user = ""
    first_user = ""
    last_llm = ""
    for m in messages or []:
        role = (m.get("role") or "")
        t = _plain(m)
        if not t:
            continue
        tagged = _sanitize_goal(str(m.get("_llm_goal") or ""))
        if tagged:
            last_llm = tagged
        g = extract_explicit_goal(t)
        if g:
            last_llm = g
            continue
        if role == "assistant" and not (
            m.get("_hide_ui") or m.get("_tool_round")
        ):
            d = extract_declared_goal(t)
            if d:
                last_llm = d
        if role != "user":
            continue
        if is_auto_continue_text(t) or _JUNK_USER.match(t):
            continue
        if t.lower().startswith("continue"):
            continue
        if _ASK_ABOUT_GOAL_RE.search(t) or _META_GOAL_ONLY_RE.match(t.strip()):
            continue
        if _sanitize_goal(t) == "":
            continue
        if len(t) < 12:
            continue
        if not first_user:
            first_user = t
        last_user = t
    if last_llm:
        return _sanitize_goal(last_llm)
    if ov:
        return ov
    return _sanitize_goal(last_user or first_user)


def apply_inferred_goal(
    chat: dict[str, Any] | None,
    messages: list[dict[str, Any]] | None,
    latest_reply: str = "",
) -> str:
    """Write current_goal onto the chat dict unless the user pinned it."""
    if not isinstance(chat, dict):
        return ""
    if chat.get("current_goal_user_pin"):
        return _sanitize_goal(str(chat.get("current_goal") or ""))
    set_g = extract_explicit_goal(latest_reply) if latest_reply else ""
    declared = extract_declared_goal(latest_reply) if latest_reply else ""
    inferred = set_g or declared or current_goal_text(
        messages,
        override=str(chat.get("current_goal") or ""),
    )
    inferred = _sanitize_goal(inferred)
    if inferred and inferred != str(chat.get("current_goal") or ""):
        chat["current_goal"] = inferred
        chat["current_goal_source"] = "llm" if (set_g or declared) else (
            str(chat.get("current_goal_source") or "") or "conversation"
        )
    elif not inferred:
        # Drop junk that was previously persisted ("update the goal")
        prev = str(chat.get("current_goal") or "")
        if prev and not _sanitize_goal(prev):
            chat["current_goal"] = ""
    return inferred or _sanitize_goal(str(chat.get("current_goal") or ""))


def goal_banner_status(task: str, llm: str) -> str:
    if task == TASK_ACHIEVED:
        return "DONE"
    if task == TASK_BLOCKED:
        return "BLOCKED"
    if llm == LLM_ERROR:
        return "ERROR"
    if llm == LLM_WORKING:
        return "WORKING"
    if llm == LLM_PAUSED:
        return "PAUSED"
    if task == TASK_OPEN:
        return "PENDING"
    return "NONE"


def infer_llm_status(*, busy: bool, paused: bool = False, last_error: bool = False) -> str:
    if busy and paused:
        return LLM_PAUSED
    if busy:
        return LLM_WORKING
    if last_error:
        return LLM_ERROR
    return LLM_IDLE


_RETRYABLE_ERR_RE = re.compile(
    r"(HTTP\s*5\d\d|HTTP\s*429|HTTP\s*524|"
    r"internal server error|overloaded|temporar(?:y|ily)|"
    r"timed? ?out|timeout|unavailable|connection (?:reset|refused|aborted|error)|"
    r"rate limit|too many requests|bad gateway|service unavailable|gateway timeout)",
    re.I,
)
_FATAL_ERR_RE = re.compile(
    r"HTTP\s*40[013]|invalid api key|unauthorized|forbidden|incorrect api key",
    re.I,
)


def is_retryable_llm_error(text: str) -> bool:
    """True for transient provider failures (500/502/503/429/timeout)."""
    t = (text or "").strip()
    if not t:
        return False
    if _FATAL_ERR_RE.search(t):
        return False
    return bool(_RETRYABLE_ERR_RE.search(t))


def should_auto_continue(
    *,
    task: str,
    llm: str,
    user_typing: bool = False,
    hold: bool = False,
    auto_count: int = 0,
    seconds_since_last_auto: float = 999.0,
    page_is_chat: bool = True,
    cycle_running: bool = False,
    retryable_error: bool = False,
    error_retries: int = 0,
) -> bool:
    if not cycle_running:
        return False
    if not page_is_chat:
        return False
    if task != TASK_OPEN:
        return False
    if user_typing or hold:
        return False
    if auto_count >= MAX_AUTO_CONTINUES:
        return False
    if llm == LLM_ERROR:
        if not retryable_error:
            return False
        if error_retries >= MAX_ERROR_RETRIES:
            return False
        if seconds_since_last_auto < MIN_ERROR_RETRY_SEC:
            return False
        return True
    if llm != LLM_IDLE:
        return False
    if seconds_since_last_auto < MIN_AUTO_GAP_SEC:
        return False
    return True


def task_chip_label(task: str) -> str:
    return {
        TASK_NONE: "Task · none",
        TASK_OPEN: "Task · open",
        TASK_ACHIEVED: "Task · achieved",
        TASK_BLOCKED: "Task · blocked",
    }.get(task, f"Task · {task}")


def llm_chip_label(llm: str) -> str:
    return {
        LLM_IDLE: "LLM · idle",
        LLM_WORKING: "LLM · working",
        LLM_PAUSED: "LLM · paused",
        LLM_ERROR: "LLM · error",
    }.get(llm, f"LLM · {llm}")
