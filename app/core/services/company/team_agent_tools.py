"""Tool-using agent runner for Team / org pipeline.

Why this exists
---------------
Chat Action mode runs a multi-round loop: model emits <<<TERMINAL>>> / <<<WEB_SEARCH>>>
blocks → app executes them → results go back to the model.

Team coordinate mode and org pipeline used a *single* chat_completion with no
execution loop, so agents only *talked* about tools and never used the terminal.

This module gives Team the same capability (compact: terminal + web search + fetch).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

from app.paths import app_root
from app.core.services.llm.llm import LLMError, chat_completion
from app.core.services.llm.providers import resolve_active_llm
from app.core.services.data.storage import load_config, resolve_agent_llm, get_agent
from app.core.services.system.terminal_tool import (
    extract_terminal_commands,
    format_result_for_llm,
    run_command,
)
from app.core.services.tools.tool_normalizer import normalize_tool_calls

ProgressCb = Callable[[str], None]

# Cap rounds so a runaway agent cannot hang forever
_DEFAULT_MAX_TOOL_ROUNDS = 6

_WEB_SEARCH_RE = re.compile(
    r"<<<WEB_SEARCH>>>\s*(.*?)\s*<<<END_WEB_SEARCH>>>",
    re.DOTALL | re.I,
)
_WEB_FETCH_RE = re.compile(
    r"<<<WEB_FETCH>>>\s*(.*?)\s*<<<END_WEB_FETCH>>>",
    re.DOTALL | re.I,
)


def _prog(cb: ProgressCb | None, msg: str) -> None:
    if cb:
        try:
            cb(msg)
        except Exception:  # noqa: BLE001
            pass


def _team_tool_system(
    *,
    name: str,
    role: str,
    department: str,
    goal: str,
) -> str:
    return f"""You are {name}, role={role}, department={department}.
You are part of a multi-AI Team working on a shared goal on the user's Windows PC.

## Goal
{goal}

## CRITICAL — you have REAL tools (they actually run)
Do NOT only describe what you would do. Use tool blocks when needed.

### Terminal (PowerShell on this PC)
<<<TERMINAL>>>
command here
<<<END_TERMINAL>>>

Examples: curl, Invoke-WebRequest, dir, python scripts, etc.

### Web search
<<<WEB_SEARCH>>>
your search query
<<<END_WEB_SEARCH>>>

### Fetch a URL
<<<WEB_FETCH>>>
https://example.com/page
<<<END_WEB_FETCH>>>

Rules:
1. When you need live facts, links, or verification → USE tools first, then answer.
2. After tool results return, write a clear RESULT for teammates and the user.
3. Never invent “I checked and it works” without tool output in the conversation.
4. Prefer short terminal commands. Avoid destructive system changes.
5. When done, write the final useful answer for this turn (no more tools needed).
6. Do NOT return empty messages.
"""


def _extract_web_queries(text: str) -> list[str]:
    out: list[str] = []
    for m in _WEB_SEARCH_RE.finditer(text or ""):
        q = (m.group(1) or "").strip()
        # allow "query: foo" wrapper
        if q.lower().startswith("query:"):
            q = q[6:].strip()
        if q:
            out.append(q)
    return out


def _extract_fetch_urls(text: str) -> list[str]:
    out: list[str] = []
    for m in _WEB_FETCH_RE.finditer(text or ""):
        u = (m.group(1) or "").strip()
        if u.lower().startswith("url:"):
            u = u[4:].strip()
        # first line only if multi-line body
        u = u.splitlines()[0].strip() if u else ""
        if u.startswith("http"):
            out.append(u)
    return out


def _has_tool_blocks(text: str) -> bool:
    t = text or ""
    return bool(
        extract_terminal_commands(t)
        or _extract_web_queries(t)
        or _extract_fetch_urls(t)
        or "<<<TERMINAL>>>" in t.upper()
        or "<<<WEB_SEARCH>>>" in t.upper()
        or "<<<WEB_FETCH>>>" in t.upper()
    )


def strip_tool_blocks(text: str) -> str:
    """Remove executed/raw tool markup so the feed shows human answer text."""
    t = text or ""
    # Closed blocks (non-greedy, DOTALL)
    for name in (
        "TERMINAL",
        "WEB_SEARCH",
        "WEB_FETCH",
        "DEEP_RESEARCH",
        "BROWSER",
        "PIP",
    ):
        t = re.sub(
            rf"<<<{name}>>>\s*.*?\s*<<<END_{name}>>>",
            f"[{name.lower()} ran]",
            t,
            flags=re.DOTALL | re.IGNORECASE,
        )
    # Unclosed / broken blocks: drop from <<<NAME>>> to next <<< or end
    t = re.sub(
        r"<<<([A-Z][A-Z0-9_]*)>>>[\s\S]*?(?=<<<|\Z)",
        r"[\1 ran]",
        t,
        flags=re.IGNORECASE,
    )
    # Collapse noisy placeholders
    t = re.sub(r"(?:\[(?:terminal|web_search|web_fetch) ran\]\s*){2,}", "[tools ran]\n", t, flags=re.I)
    return t.strip()


def _run_web_search(query: str) -> str:
    try:
        from app.core.services.web.web_search import search_web

        res = search_web(query, max_results=8)
        if isinstance(res, dict):
            # prefer markdown report if present
            md = res.get("markdown") or res.get("report") or ""
            if md:
                return str(md)[:12000]
            hits = res.get("hits") or res.get("results") or []
            lines = [f"### Web search: {query}"]
            for h in hits[:10]:
                if isinstance(h, dict):
                    lines.append(
                        f"- {h.get('title') or ''} | {h.get('url') or h.get('link') or ''}\n"
                        f"  {(h.get('snippet') or h.get('body') or '')[:200]}"
                    )
                else:
                    lines.append(f"- {h}")
            return "\n".join(lines) if len(lines) > 1 else f"(no hits for {query})"
        return str(res)[:8000]
    except Exception as e:  # noqa: BLE001
        return f"Web search error: {e}"


def _run_web_fetch(url: str) -> str:
    try:
        from app.core.services.web.web_fetch import fetch_url

        res = fetch_url(url)
        if isinstance(res, dict):
            text = res.get("text") or res.get("content") or res.get("markdown") or ""
            title = res.get("title") or ""
            return f"### Fetch {url}\nTitle: {title}\n\n{str(text)[:10000]}"
        return str(res)[:10000]
    except Exception as e:  # noqa: BLE001
        # fallback curl via terminal is caller's choice; keep error clear
        return f"Web fetch error: {e}"


def run_tool_agent(
    *,
    user_brief: str,
    agent_name: str = "Agent",
    agent_role: str = "specialist",
    department: str = "Team",
    goal: str = "",
    agent_id: str = "",
    transcript: str = "",
    max_tool_rounds: int = _DEFAULT_MAX_TOOL_ROUNDS,
    on_progress: ProgressCb | None = None,
    should_stop: Callable[[], bool] | None = None,
    terminal_cwd: str | Path | None = None,
    enable_terminal: bool = True,
    enable_web: bool = True,
) -> dict[str, Any]:
    """
    Multi-round agent with terminal + web tools.

    Returns {ok, text, tool_log, rounds, error?}
    """
    active = resolve_active_llm()
    cfg = load_config()
    key = (active.get("api_key") or cfg.get("api_key") or "").strip()
    model = (active.get("model") or cfg.get("model") or "gpt-4o-mini").strip()
    base = (
        active.get("base_url") or cfg.get("api_base_url") or "https://api.openai.com/v1"
    ).strip()
    if agent_id:
        ag = get_agent(agent_id)
        if ag:
            llm = resolve_agent_llm(ag)
            key = (llm.get("api_key") or key).strip()
            model = (llm.get("model") or model).strip()
            base = (llm.get("base_url") or base).strip()
    if not key:
        return {"ok": False, "text": "", "error": "No API key", "tool_log": [], "rounds": 0}

    cwd = str(terminal_cwd or app_root())
    system = _team_tool_system(
        name=agent_name,
        role=agent_role,
        department=department,
        goal=goal or user_brief,
    )
    user = user_brief
    if transcript:
        user = f"## Team channel so far\n{transcript[:12000]}\n\n## Your assignment\n{user_brief}"

    messages: list[dict[str, str]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    tool_log: list[str] = []
    last_text = ""
    rounds_done = 0

    # Optional OpenAI tools schemas (dual path)
    tools = None
    try:
        from app.core.services.tools.tool_schemas import studio_openai_tools

        tools = [
            t
            for t in studio_openai_tools(include_harness=False)
            if (t.get("function") or {}).get("name")
            in ("run_terminal", "terminal", "web_search", "web_fetch")
        ]
    except Exception:  # noqa: BLE001
        tools = None

    for round_i in range(1, max(1, max_tool_rounds) + 1):
        if should_stop and should_stop():
            return {
                "ok": bool(last_text),
                "text": last_text or "(stopped)",
                "tool_log": tool_log,
                "rounds": rounds_done,
                "cancelled": True,
            }
        rounds_done = round_i
        _prog(on_progress, f"{agent_name}: thinking (tool round {round_i}/{max_tool_rounds})…")
        try:
            raw = chat_completion(
                api_key=key,
                messages=messages,
                model=model,
                base_url=base,
                timeout=180.0,
                temperature=0.3,
                max_tokens=2500,
                tools=tools if tools else None,
                normalize_tools=True,
            )
        except LLMError as e:
            # retry without tools schema if rejected
            if tools and "tool" in str(e).lower():
                tools = None
                try:
                    raw = chat_completion(
                        api_key=key,
                        messages=messages,
                        model=model,
                        base_url=base,
                        timeout=180.0,
                        temperature=0.3,
                        max_tokens=2500,
                        tools=None,
                        normalize_tools=True,
                    )
                except LLMError as e2:
                    return {
                        "ok": False,
                        "text": last_text,
                        "error": str(e2),
                        "tool_log": tool_log,
                        "rounds": rounds_done,
                    }
            else:
                return {
                    "ok": False,
                    "text": last_text,
                    "error": str(e),
                    "tool_log": tool_log,
                    "rounds": rounds_done,
                }

        text = normalize_tool_calls(str(raw or "")) or str(raw or "")
        last_text = text.strip()
        messages.append({"role": "assistant", "content": text})

        if not last_text:
            messages.append(
                {
                    "role": "user",
                    "content": "Your reply was empty. Use tools if needed, then write a non-empty RESULT.",
                }
            )
            continue

        # Execute tools
        observations: list[str] = []
        used = False

        if enable_terminal:
            for cmd in extract_terminal_commands(text):
                used = True
                _prog(on_progress, f"{agent_name}: TERMINAL → {cmd[:80]}")
                tool_log.append(f"TERMINAL: {cmd[:200]}")
                try:
                    result = run_command(cmd, cwd=cwd, safety_mode=False)
                    observations.append(format_result_for_llm(result))
                except Exception as e:  # noqa: BLE001
                    observations.append(f"Terminal error: {e}")

        if enable_web:
            for q in _extract_web_queries(text):
                used = True
                _prog(on_progress, f"{agent_name}: WEB_SEARCH → {q[:80]}")
                tool_log.append(f"WEB_SEARCH: {q[:200]}")
                observations.append(_run_web_search(q))
            for url in _extract_fetch_urls(text):
                used = True
                _prog(on_progress, f"{agent_name}: WEB_FETCH → {url[:80]}")
                tool_log.append(f"WEB_FETCH: {url[:200]}")
                observations.append(_run_web_fetch(url))

        if not used:
            # No tool blocks — this is the final answer for this agent turn
            break

        # Feed tool results back
        obs_blob = "\n\n---\n\n".join(observations)[:14000]
        # On last allowed round after tools: demand pure final text (no more tools)
        if round_i >= max_tool_rounds:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "## Tool results (real — use them)\n"
                        f"{obs_blob}\n\n"
                        "Write your FINAL RESULT for the team NOW. "
                        "Do NOT emit any <<<TERMINAL>>> / <<<WEB_*>>> blocks. "
                        "Plain text only, non-empty."
                    ),
                }
            )
            try:
                raw_f = chat_completion(
                    api_key=key,
                    messages=messages,
                    model=model,
                    base_url=base,
                    timeout=120.0,
                    temperature=0.3,
                    max_tokens=2000,
                    tools=None,
                    normalize_tools=False,
                )
                last_text = strip_tool_blocks(str(raw_f or "").strip()) or last_text
            except LLMError:
                pass
            break

        messages.append(
            {
                "role": "user",
                "content": (
                    "## Tool results (real — use them)\n"
                    f"{obs_blob}\n\n"
                    "Using these results, continue. If you need more tools, emit more blocks. "
                    "Otherwise write your final RESULT for the team (no empty message, no raw tool blocks)."
                ),
            }
        )

    # Always strip raw tool markup from what we show/post
    display = strip_tool_blocks(last_text)
    if not display.strip() and tool_log:
        display = (
            "Tools ran but model did not write a summary.\n\n### Tools used\n"
            + "\n".join(f"- {x}" for x in tool_log[:20])
        )
    return {
        "ok": bool(display.strip()),
        "text": display.strip() or "(no output)",
        "tool_log": tool_log,
        "rounds": rounds_done,
        "tools_used": len(tool_log),
    }
