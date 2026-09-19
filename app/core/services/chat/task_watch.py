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
    r"^\s*(done|stop|that'?s all|task complete|mark(?:ed)? done|cancel task)\s*[.!?]?\s*$",
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
        if (m.get("role") or "").lower() == "user":
            return m
    return None


def last_assistant_message(messages: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    for m in reversed(messages or []):
        if (m.get("role") or "").lower() == "assistant":
            return m
    return None


def classify_task_from_messages(messages: list[dict[str, Any]] | None) -> str:
    """Heuristic task state from recent chat turns."""
    msgs = messages or []
    if not msgs:
        return TASK_NONE
    last_u = last_user_message(msgs)
    text_u = _plain(last_u)
    if text_u and _USER_MARK_DONE.match(text_u):
        return TASK_ACHIEVED
    if text_u and _USER_REOPEN.search(text_u):
        return TASK_OPEN
    # Any non-junk user message implies an open task unless clearly closed
    if text_u and not _JUNK_USER.match(text_u) and not is_auto_continue_text(text_u):
        return TASK_OPEN
    # Auto-continues mean task still open
    if text_u and is_auto_continue_text(text_u):
        return TASK_OPEN
    return TASK_NONE


def user_marked_task_done(text: str) -> bool:
    return bool(_USER_MARK_DONE.match((text or "").strip()))


def user_reopened_task(text: str) -> bool:
    return bool(_USER_REOPEN.search((text or "").strip()))


def status_label(task: str, llm: str) -> str:
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
