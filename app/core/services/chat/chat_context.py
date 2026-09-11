"""
Max LLM context use: rolling summaries, sticky memory, smart keep set.

Goals:
  • Use as much of the model context window as possible
  • Never silently lose goals/decisions when history is trimmed
  • Keep a single leading system message (provider-safe)
  • Do not break existing chat / tool setup
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.paths import chats_dir, data_dir
from app.core.services.data.storage import load_config
from app.core.services.data.usage_meter import estimate_tokens_from_text


# ── paths ───────────────────────────────────────────────────────────────────


def _summary_path(chat_id: str) -> Path:
    d = data_dir() / "chat_summaries"
    d.mkdir(parents=True, exist_ok=True)
    cid = (chat_id or "default").replace("/", "_").replace("\\", "_")[:80]
    return d / f"{cid}.json"


def load_summary(chat_id: str) -> dict[str, Any]:
    p = _summary_path(chat_id)
    if not p.exists():
        return {"chat_id": chat_id, "summary": "", "updated_at": "", "drops": 0}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:  # noqa: BLE001
        pass
    return {"chat_id": chat_id, "summary": "", "updated_at": "", "drops": 0}


def save_summary(chat_id: str, summary: str, *, drops: int = 0) -> dict[str, Any]:
    prev = load_summary(chat_id)
    data = {
        "chat_id": chat_id,
        "summary": (summary or "").strip()[:12000],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "drops": int(prev.get("drops") or 0) + int(drops or 0),
    }
    _summary_path(chat_id).write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


# ── extractive + optional LLM compress ───────────────────────────────────────


def _clip(text: str, n: int = 280) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    if len(t) <= n:
        return t
    return t[: n - 1] + "…"


def extractive_summary_from_messages(messages: list[dict[str, str]], *, max_bullets: int = 24) -> str:
    """Fast, offline summary of dropped turns (no API call)."""
    bullets: list[str] = []
    paths: set[str] = set()
    for m in messages:
        role = (m.get("role") or "user").lower()
        content = (m.get("content") or "").strip()
        if not content:
            continue
        # capture file-like paths
        for p in re.findall(r"[A-Za-z0-9_./\\-]+\.(?:py|ts|tsx|js|md|json|toml|yml|yaml|ps1|bat)", content):
            if len(p) < 120:
                paths.add(p)
        if role == "user":
            # skip pure tool dumps that are huge
            if content.startswith("[") and "]\n" in content[:40]:
                head = content.split("\n", 1)[0]
                bullets.append(f"tool-result {head[:80]}")
            else:
                bullets.append(f"user: {_clip(content, 220)}")
        elif role == "assistant":
            # keep decisions / plans, skip pure tool-block spam
            if "<<<" in content and len(content) < 400:
                bullets.append(f"assistant-tools: {_clip(content, 160)}")
            else:
                # first non-empty paragraph
                para = content.split("\n\n")[0]
                bullets.append(f"assistant: {_clip(para, 220)}")
        if len(bullets) >= max_bullets:
            break
    lines = ["### Compressed earlier conversation"]
    if paths:
        lines.append("Files mentioned: " + ", ".join(sorted(paths)[:20]))
    for b in bullets[:max_bullets]:
        lines.append(f"- {b}")
    return "\n".join(lines)


def merge_summaries(old: str, new_chunk: str, *, max_chars: int = 8000) -> str:
    old = (old or "").strip()
    new_chunk = (new_chunk or "").strip()
    if not old:
        return new_chunk[:max_chars]
    if not new_chunk:
        return old[:max_chars]
    merged = (
        old
        + "\n\n### Later (compressed)\n"
        + new_chunk.replace("### Compressed earlier conversation\n", "")
    )
    if len(merged) <= max_chars:
        return merged
    # keep head (goals) + tail (recent compressed)
    head = merged[: max_chars // 3]
    tail = merged[-(max_chars - len(head) - 40) :]
    return head + "\n\n…(summary compacted)…\n\n" + tail


def llm_compact_summary(text: str) -> str | None:
    """Optional LLM compression (off by default — extractive is fast and always on)."""
    cfg = load_config()
    # Default False: never block the main chat turn on a second LLM call
    if not cfg.get("agent_context_llm_summary", False):
        return None
    blob = (text or "").strip()
    if len(blob) < 1200:
        return None
    try:
        from app.core.services.llm.llm import chat_completion
        from app.core.services.llm.providers import resolve_active_llm

        active = resolve_active_llm()
        api_key = (active.get("api_key") or cfg.get("api_key") or "").strip()
        if not api_key:
            return None
        model = (active.get("model") or cfg.get("model") or "gpt-4o-mini").strip()
        base_url = (
            active.get("base_url") or cfg.get("api_base_url") or "https://api.openai.com/v1"
        ).strip()
        prompt = (
            "Compress the following chat excerpts into a durable memory for a coding agent. "
            "Keep: user goals, decisions, constraints, file paths, tool outcomes, open tasks. "
            "Drop chit-chat and repeated tool dumps. Use short bullet points. Max 600 words.\n\n"
            + blob[:14000]
        )
        out = chat_completion(
            api_key=api_key,
            messages=[
                {
                    "role": "system",
                    "content": "You write compact conversation memory. No preamble.",
                },
                {"role": "user", "content": prompt},
            ],
            model=model,
            base_url=base_url,
            timeout=25.0,
        )
        if isinstance(out, str) and out.strip():
            return "### Conversation memory (LLM compressed)\n" + out.strip()[:6000]
    except Exception:  # noqa: BLE001
        return None
    return None


def update_rolling_summary(chat_id: str, dropped_messages: list[dict[str, str]]) -> str:
    if not dropped_messages or not chat_id:
        return load_summary(chat_id).get("summary") or ""
    # Always extractive first (instant), optional LLM polish only if enabled
    extractive = extractive_summary_from_messages(dropped_messages)
    prev = load_summary(chat_id).get("summary") or ""
    merged = merge_summaries(prev, extractive)
    save_summary(chat_id, merged, drops=len(dropped_messages))
    # Optional second-pass LLM (never required for correctness)
    try:
        polished = llm_compact_summary(merged)
        if polished:
            save_summary(chat_id, polished, drops=0)
            return polished
    except Exception:  # noqa: BLE001
        pass
    return merged


# ── sticky context for the model ─────────────────────────────────────────────


def first_user_goal(history: list[dict[str, Any]]) -> str:
    for m in history or []:
        if (m.get("role") or "") == "user":
            t = (m.get("content") or "").strip()
            if t and not t.startswith("[Context") and not t.startswith("[Conversation"):
                return _clip(t, 600)
    return ""


def memory_block(limit: int = 30) -> str:
    try:
        from app.core.services.chat.memory_store import memory_prompt_block

        return memory_prompt_block(limit=limit)
    except Exception:  # noqa: BLE001
        return ""


def sticky_context_messages(
    *,
    chat_id: str = "",
    history: list[dict[str, Any]] | None = None,
    summary_override: str | None = None,
) -> list[dict[str, str]]:
    """
    High-priority user messages injected after system, before live history.
    Survive better than middle-of-chat noise.
    """
    cfg = load_config()
    if cfg.get("agent_context_sticky", True) is False:
        return []

    parts: list[str] = []
    parts.append(
        "## Context strategy\n"
        "The Findings list below is task memory. Do not rediscover listed errors. "
        "The live transcript is only the last turns — the list is what you already know."
    )

    try:
        from app.core.services.chat.task_ledger import (
            backfill_from_history,
            format_for_prompt,
            load_ledger,
            save_ledger,
        )

        led = load_ledger(None, chat_id)
        if not (led.get("findings") or []) and history:
            led = backfill_from_history(history, led)
            if chat_id and led.get("findings"):
                save_ledger({"id": chat_id}, led)
        block = format_for_prompt(led)
        if block:
            parts.append(block)
    except Exception:  # noqa: BLE001
        pass

    goal = first_user_goal(history or [])
    if goal:
        parts.append(f"## Original user goal (keep pursuing)\n{goal}")

    mem = memory_block(limit=int(cfg.get("agent_memory_inject_limit") or 30))
    if mem and "no stored memories" not in mem.lower():
        parts.append(mem)

    summary = summary_override
    if summary is None and chat_id:
        summary = load_summary(chat_id).get("summary") or ""
    junk = "tool omitted" in (summary or "").lower() or "prior turn was tool" in (summary or "").lower()
    if summary and summary.strip() and not junk:
        parts.append(
            "## Rolling conversation summary (older turns compressed — treat as true)\n"
            + summary.strip()[:2500]
        )

    try:
        from app.services.agent_harness.agent_todo import format_for_prompt

        td = format_for_prompt(chat_id)
        if td:
            parts.append(td)
    except Exception:  # noqa: BLE001
        pass

    try:
        from app.services.agent_harness.plan_mode import read_plan

        pl = read_plan(chat_id)
        if pl.get("ok") and pl.get("content"):
            parts.append("## Active plan.md (excerpt)\n" + (pl.get("content") or "")[:2500])
    except Exception:  # noqa: BLE001
        pass

    body = "\n\n".join(parts).strip()
    if not body:
        return []
    # IMPORTANT: only a user note — never a fake assistant turn.
    # A canned assistant "Understood..." was being mirrored as a visible chat reply
    # (models copy the last assistant message, and users saw multiple replies).
    return [
        {
            "role": "user",
            "content": (
                "[Internal sticky context — not a user question; do not reply to this alone. "
                "Use it only to answer the next real user message.]\n\n" + body
            ),
        },
    ]


def auto_capture_memory_from_reply(reply: str, *, source: str = "chat") -> int:
    """Optionally extract durable facts into Memory page."""
    cfg = load_config()
    if not cfg.get("agent_auto_memory", True):
        return 0
    text = (reply or "").strip()
    if len(text) < 120:
        return 0
    # Look for decision-like lines
    patterns = [
        r"(?i)^(?:decision|decided|we will|always|never|constraint|note)[:\-\s]+(.+)$",
        r"(?i)^(?:important|remember|preference)[:\-\s]+(.+)$",
    ]
    captured = 0
    try:
        from app.core.services.chat.memory_store import add_item, list_items

        existing = " ".join(i.get("content") or "" for i in list_items()[:50]).lower()
        for line in text.splitlines():
            line = line.strip().lstrip("#*- ").strip()
            if len(line) < 20 or len(line) > 240:
                continue
            for pat in patterns:
                m = re.match(pat, line)
                if not m:
                    continue
                fact = m.group(1).strip() if m.lastindex else line
                if fact.lower() in existing:
                    continue
                add_item(fact, tags=["auto", "chat"], source=source)
                existing += " " + fact.lower()
                captured += 1
                if captured >= 3:
                    return captured
    except Exception:  # noqa: BLE001
        return captured
    return captured


def recommended_context_window() -> int:
    """Push toward max model capability (user can still override lower)."""
    cfg = load_config()
    # Explicit override wins
    try:
        if cfg.get("context_window_force"):
            return max(8000, int(cfg["context_window_force"]))
    except Exception:  # noqa: BLE001
        pass
    # Prefer model_params / top-level if user set high
    try:
        cur = int((cfg.get("model_params") or {}).get("context_window") or cfg.get("context_window") or 0)
    except Exception:  # noqa: BLE001
        cur = 0
    # Default max-capability budget
    target = int(cfg.get("context_window_max") or 128000)
    if cur < 32000:
        return max(cur if cur >= 8000 else 0, min(target, 128000)) or 128000
    return max(cur, 32000)


def ensure_max_context_config() -> dict[str, Any]:
    """Raise stored context window toward max if still on old low defaults."""
    from app.core.services.data.storage import save_config
    from app.core.services.llm.model_params import get_model_params, save_model_params

    cfg = load_config()
    p = get_model_params()
    changed = False
    # Upgrade legacy 12k / low values to max-capability default
    try:
        cw = int(p.get("context_window") or 0)
    except Exception:  # noqa: BLE001
        cw = 0
    if cw and cw < 32000 and not cfg.get("context_window_locked"):
        p["context_window"] = int(cfg.get("context_window_max") or 128000)
        changed = True
    try:
        res = int(p.get("context_reserve_reply") or 0)
    except Exception:  # noqa: BLE001
        res = 0
    if res and res < 4000 and not cfg.get("context_window_locked"):
        p["context_reserve_reply"] = 8000
        changed = True
    if changed:
        save_model_params(p)
        cfg = load_config()
        cfg["agent_context_sticky"] = cfg.get("agent_context_sticky", True)
        cfg["agent_context_llm_summary"] = cfg.get("agent_context_llm_summary", False)
        cfg["agent_auto_memory"] = cfg.get("agent_auto_memory", True)
        cfg["context_window_max"] = cfg.get("context_window_max", 128000)
        save_config(cfg)
    return get_model_params()
