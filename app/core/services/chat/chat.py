"""Interactive LLM chat — plan/action modes, skills, MCP, terminal, full operator manual."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.paths import app_root
from app.core.services.misc.attachments import format_attachments_block
from app.core.services.tools.capability_manual import build_runtime_catalog
from app.core.services.chat.chat_store import load_chat as store_load_chat
from app.core.services.chat.chat_store import save_chat as store_save_chat
from app.core.services.misc.default_prompts import get_default_system_prompt
from app.core.services.system.laptop_control import (
    clipboard_op,
    extract_clipboard_blocks,
    extract_gui_blocks,
    extract_screenshot_blocks,
    extract_windows_blocks,
    laptop_tool_instructions,
    run_gui_actions,
    take_screenshot,
    windows_op,
)
from app.core.services.web.browser_tool import (
    extract_browser_blocks,
    run_browser,
    tool_instructions as browser_tool_instructions,
)
from app.core.services.web.web_fetch import (
    extract_fetch_blocks,
    run_fetch_command,
    tool_instructions as web_fetch_instructions,
)
from app.core.services.ai.deep_research import (
    extract_crawl_blocks,
    extract_deep_research_blocks,
    extract_download_blocks,
    extract_scrape_blocks,
    run_crawl,
    run_deep_research,
    run_download,
    run_scrape,
    tool_instructions as deep_research_instructions,
)
from app.core.services.system.internet_access import internet_playbook
from app.core.services.ai.image_gen import (
    extract_image_gen_blocks,
    generate_image,
    image_gen_instructions,
    ImageGenError,
)
from app.core.services.llm.llm import (
    LLMError,
    chat_completion,
    chat_completion_stream,
    is_prompt_token_limit_error,
)
from app.core.services.integrations.mcp_client import extract_mcp_requests, get_mcp_hub
from app.core.services.integrations.mcp_marketplace import marketplace_prompt
from app.core.services.chat.media_chat import enrich_message_with_media, media_tool_instructions, stage_media_file
from app.core.services.company.org_tools import extract_org_commands, org_tool_instructions, run_org_command
from app.core.services.misc.package_auto import extract_pip_commands, pip_tool_instructions, run_pip_command
from app.core.services.llm.providers import provider_prompt_block, resolve_active_llm
from app.core.services.data.rag_knowledge import (
    extract_knowledge_commands,
    run_knowledge_command,
    tool_instructions as knowledge_tool_instructions,
)
from app.core.services.ai.local_embeddings import build_context_block_hybrid
from app.core.services.web.ocr_service import extract_ocr_blocks, ocr_image, tool_instructions as ocr_tool_instructions
from app.core.services.misc.patch_review import (
    extract_patch_blocks,
    queue_patch,
    tool_instructions as patch_review_instructions,
)
from app.core.services.ai.self_improve import (
    extract_self_improve_blocks,
    run_self_improve_from_reply,
    tool_instructions as self_improve_instructions,
)
from app.core.services.web.web_search import (
    extract_search_blocks,
    run_search_command,
    tool_instructions as web_search_instructions,
)
from app.services.agent_harness import (
    extract_harness_blocks,
    harness_tool_instructions,
    inject_project_context,
    run_harness_from_reply,
)
from app.services.agent_harness import hooks as agent_hooks
from app.core.services.tools.skills_registry import (
    discover_skills,
    extract_skill_requests,
    load_skill_text,
)
from app.core.services.data.storage import load_config
# Universal tool-call normalizer (Strategy 1: text blocks, 2: OpenAI tool_calls, 3: simplified JSON)
from app.core.services.tools.tool_normalizer import normalize_tool_calls
# Lazy imports to break circular dependencies
def _get_tool_approvals():
    from app.services import tool_approvals
    return tool_approvals


def _get_tool_budget():
    from app.services import tool_budget
    return tool_budget


def _get_usage_meter():
    from app.services import usage_meter
    return usage_meter
from app.core.services.system.terminal_tool import (
    MAX_ROUNDS,
    command_fingerprint,
    extract_terminal_commands,
    format_result_for_llm,
    run_command,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slim_system_prompt(base: str, *, mode: str = "action") -> str:
    """
    Compact system prompt for low-credit OpenRouter (prompt token caps ~3k–8k).
    Full Action-mode catalogs are ~15k+ tokens and fail even on “hi”.
    """
    core = (base or get_default_system_prompt() or "").strip()
    # Keep a short persona, drop multi-kb tool manuals
    if len(core) > 2500:
        core = core[:2500].rstrip() + "\n…"
    lite = (
        core
        + "\n\n## Compact mode (auto)\n"
        "Your provider rejected the full tool manual (prompt token limit). "
        "Answer helpfully and concisely. Prefer plain replies for greetings "
        "and simple questions.\n"
    )
    if (mode or "action").lower() == "action":
        lite += (
            "\nYou may still use short text tool blocks when the user clearly needs them:\n"
            "<<<WEB_SEARCH>>>query<<<END_WEB_SEARCH>>>\n"
            "<<<TERMINAL>>>command<<<END_TERMINAL>>>\n"
            "<<<IMAGE_GEN>>>prompt<<<END_IMAGE_GEN>>>\n"
            "Do not invent tool results. If a tool is required and unavailable, say so.\n"
        )
    else:
        lite += "\nMode is PLAN — outline steps; do not execute tools.\n"
    return lite


def load_chat(chat_id: str | None = None) -> dict[str, Any]:
    data = store_load_chat(chat_id)
    defaults = {
        "messages": [],
        "agent_id": "",
        "mode": "action",
        "terminal_enabled": True,
        "skills_enabled": True,
        "mcp_enabled": True,
        "laptop_enabled": True,
        "use_workflow_graph": False,
        "safety_mode": False,
        "enabled_skill_names": None,
        "project_id": "",
        "folder_id": "",
        "draft": "",
    }
    for k, v in defaults.items():
        data.setdefault(k, v)
    return data


def save_chat(chat: dict[str, Any]) -> dict[str, Any]:
    return store_save_chat(chat)


def clear_chat() -> dict[str, Any]:
    prev = load_chat()
    chat = {
        **prev,
        "messages": [],
        "updated_at": _now(),
    }
    return save_chat(chat)


def resolve_enabled_skills(
    enabled_skill_names: list[str] | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Returns (enabled skill dicts, disabled names)."""
    all_skills = discover_skills()
    if enabled_skill_names is None:
        return all_skills, []
    allow = {n.lower() for n in enabled_skill_names}
    enabled = [s for s in all_skills if s["name"].lower() in allow]
    disabled = [s["name"] for s in all_skills if s["name"].lower() not in allow]
    return enabled, disabled


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
    # Unclosed <<<TERMINAL>>> / here-string dumps (Nemotron often omits END)
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
    """True if content contains executable tool syntax (blocks or pseudo JSON/XML)."""
    text = content or ""
    if _TOOL_BLOCK_RE.search(text):
        return True
    if _PSEUDO_TOOL_RE.search(text):
        return True
    if "<<<END_" in text.upper():
        return True
    return False


def looks_like_file_dump_for_ui(content: str) -> bool:
    """True only for raw tool/file dumps — not a normal answer that happens to include code."""
    t = content or ""
    if has_tool_call_markup(t):
        return True
    low = t.lower()
    if "<tool_call" in low:
        return True
    if "@'" in t or '@"' in t or "$content" in t:
        return True
    if "<<<TERMINAL>>>" in t.upper() or "end_terminal" in low:
        return True
    if '"action"' in t and "search_replace" in low:
        return True
    return False


def looks_like_tool_dump(content: str) -> bool:
    """True when the model dumped a file / here-string / tool JSON instead of an answer."""
    t = content or ""
    if has_tool_call_markup(t):
        return True
    low = t.lower()
    if "<tool_call" in low or '"action"' in t and "search_replace" in low:
        return True
    if "@'" in t or '@"' in t or "$content" in t:
        return True
    if t.count("\\n") > 12:
        return True
    if "<<<TERMINAL>>>" in t.upper() or "end_terminal" in low:
        return True
    if len(t) > 600 and ("class " in t or "def " in t or "import " in t) and t.count("\n") < 8:
        return True
    code_hits = sum(t.count(s) for s in ("class ", "def ", "import ", "return ", "mapped_column", "self."))
    if len(t) > 500 and code_hits >= 4:
        return True
    return False


def is_tool_intent_only_assistant(content: str) -> bool:
    """True if assistant message is mainly tool-call blocks (not a final answer)."""
    text = (content or "").strip()
    if not text:
        return True
    if _STICKY_ECHO in text and len(text) < 280:
        return True
    if _is_echo_stub(text):
        return True
    if looks_like_tool_dump(text):
        return True
    if not has_tool_call_markup(text):
        return False
    prose = strip_tool_blocks_for_display(text)
    prose = re.sub(r"\s+", " ", prose).strip()
    # Short filler around a tool call → hide from UI as its own reply
    # (e.g. "I'll open Chrome for you." + <<<GUI>>>… is still a tool-intent msg)
    if len(prose) < 220:
        return True
    # Longer prose still counts as intermediate tool-round if it clearly announces tools
    announce = re.search(
        r"\b(i('ll| will)|let me|opening|launching|running|searching|executing|"
        r"using the|i am going to)\b",
        prose,
        re.I,
    )
    return bool(announce and len(prose) < 500)


def finalize_history_for_display(hist: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    One clean user-visible assistant reply per user turn (Grok-like):
    - drop sticky-echo assistant messages
    - hide intermediate tool-round assistants (any before the last in the turn)
    - hide pure tool-intent assistants when a later final exists, or when tools
      ran and the only reply is short filler around tool blocks
    Tool role messages stay in history for Live panel / optional tool traces,
    but the UI should not paint them as answer bubbles by default.
    """
    if not hist:
        return hist

    # Roles that mean "tools ran" (not a user-facing answer)
    _toolish = frozenset(
        {
            "terminal",
            "skill",
            "mcp",
            "gui",
            "clipboard",
            "windows",
            "tool",
            "org",
            "pip",
            "browser",
            "web_search",
            "ocr",
            "self_improve",
            "harness",
            "screenshot",
            "org_agent",
        }
    )

    hide_indices: set[int] = set()
    n = len(hist)
    i = 0
    while i < n:
        if (hist[i].get("role") or "") != "user":
            i += 1
            continue
        j = i + 1
        asst_idxs: list[int] = []
        tool_after_asst = False
        while j < n and (hist[j].get("role") or "") != "user":
            role = (hist[j].get("role") or "").lower()
            if role == "assistant" and not hist[j].get("_streaming"):
                asst_idxs.append(j)
            elif role in _toolish or (
                role not in ("user", "assistant", "thinking", "system", "system_note", "error")
            ):
                if asst_idxs:
                    tool_after_asst = True
            j += 1

        if len(asst_idxs) > 1:
            # Keep only the last assistant bubble for this turn
            for idx in asst_idxs[:-1]:
                hide_indices.add(idx)
            # If tools ran, also hide last assistant when it is pure tool-intent
            # and there is nothing else (should not happen often after multi-round)
            last = asst_idxs[-1]
            if tool_after_asst and is_tool_intent_only_assistant(
                str(hist[last].get("content") or "")
            ):
                # Prefer last non-tool-intent assistant if any was wrongly ordered
                for idx in reversed(asst_idxs):
                    if not is_tool_intent_only_assistant(str(hist[idx].get("content") or "")):
                        # unhide this one, hide the rest including previous "last"
                        hide_indices = (hide_indices - {idx}) | set(asst_idxs)
                        hide_indices.discard(idx)
                        break
        elif len(asst_idxs) == 1 and tool_after_asst:
            only = asst_idxs[0]
            # Single reply that only announced tools: hide as answer bubble if
            # little prose remains after stripping tool markup (tools live in Live)
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
                continue  # drop fake sticky reply entirely
            if idx in hide_indices or mm.get("_tool_round") or mm.get("_hide_ui"):
                mm["_hide_ui"] = True
                mm["_tool_intent_only"] = True
                mm["_tool_round"] = True
            elif is_tool_intent_only_assistant(content):
                # Tool-intent with a later final answer → never show as its own bubble
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
            # Always strip raw tool markup from visible assistant content flag
            if not mm.get("_hide_ui") and has_tool_call_markup(content):
                mm["_strip_tools_ui"] = True
        out.append(mm)
    return out


def _shrink_history_for_api(role: str, raw: str) -> str:
    """Keep API context small: drop here-strings / file dumps, cap huge tool results."""
    text = raw or ""
    dump = False
    try:
        dump = looks_like_tool_dump(text)
    except Exception:  # noqa: BLE001
        dump = False
    if (role or "") in ("terminal", "harness", "tool"):
        cap = 900
        if len(text) > cap:
            return text[:500] + f"\n…[truncated {len(text)} chars]\n" + text[-300:]
    if dump or len(text) > 2500:
        prose = strip_tool_blocks_for_display(text)
        prose = re.sub(r"\s+", " ", prose).strip()
        if (role or "") == "assistant":
            if len(prose) > 280:
                prose = prose[:280] + "…"
            return prose or "[omitted tool dump — continue the user task; do not repeat this line]"
        head = text.split("\n", 1)[0][:160]
        return f"{head}\n[truncated {len(text)} chars]"
    if len(text) > 4000:
        return text[:2400] + "\n…[truncated]"
    return text


def build_api_messages(
    history: list[dict[str, Any]],
    *,
    system_prompt: str,
    chat_id: str = "",
    override_messages: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    """
    Build OpenAI-compatible messages.

    Critical: many providers (OpenRouter Llama/Mistral templates) require
    exactly one system message and it must be the first item. Never put
    role=system later in the list (context trim notes, system_note, etc.).

    Sticky context (Memory, rolling summary, original goal) is injected as
    user/assistant pairs right after system so max model capability retains
    durable state when the live history is long.
    """
    if override_messages:
        out: list[dict[str, str]] = []
        for m in override_messages:
            role = str(m.get("role") or "user").strip().lower()
            if role not in ("system", "user", "assistant"):
                continue
            content = str(m.get("content") or "")
            if content or role == "system":
                out.append({"role": role, "content": content})
        if out and out[0]["role"] != "system" and (system_prompt or "").strip():
            out.insert(0, {"role": "system", "content": (system_prompt or "").strip()})
        return out
    # Single system message only (merge any extras into this string)
    sys_parts = [(system_prompt or "").strip()]
    msgs: list[dict[str, str]] = []
    for m in history:
        role = m.get("role") or "user"
        raw = (m.get("content") or "").strip()
        if not raw:
            continue
        if role == "system":
            # Fold into the leading system blob — never mid-conversation
            sys_parts.append(raw)
            continue
        if role == "thinking":
            # UI-only trace — do not re-send full thinking dump to the model every turn
            continue
        if m.get("_hide_ui") or m.get("_tool_round") or m.get("_tool_intent_only"):
            continue
        # Never feed dump/stub lines back — they bloat NVIDIA context and get copied
        if role == "assistant" and (
            _is_echo_stub(raw) or looks_like_file_dump_for_ui(raw)
        ):
            continue
        else:
            raw = _shrink_history_for_api(role, raw)
        if role in (
            "terminal",
            "tool",
            "attachment",
            "skill",
            "mcp",
            "system_note",
            "gui",
            "screenshot",
            "clipboard",
            "windows",
            "org",
            "pip",
            "web_search",
            "browser",
            "knowledge",
            "image_gen",
            "search",
            "self_improve",
            "patch",
            "image",
            "ocr",
            "error",
            "web_fetch",
            "deep_research",
            "crawl",
            "scrape",
            "download",
            "harness",
            "org_agent",
        ):
            content = f"[{role}]\n{raw}"
            role = "user"
        else:
            if role not in ("user", "assistant"):
                role = "user"
            content = raw
        if content:
            msgs.append({"role": role, "content": content})

    try:
        from app.core.services.chat.task_watch import is_auto_continue_text

        auto_idxs = [
            i
            for i, m in enumerate(msgs)
            if m.get("role") == "user" and is_auto_continue_text(m.get("content") or "")
        ]
        if len(auto_idxs) > 1:
            drop = set(auto_idxs[:-1])
            msgs = [m for i, m in enumerate(msgs) if i not in drop]
    except Exception:  # noqa: BLE001
        pass

    # Durable sticky context — fold into system (never fake user/assistant turns)
    try:
        from app.core.services.chat.chat_context import sticky_context_messages

        sticky = sticky_context_messages(chat_id=chat_id or "", history=history)
        for s in sticky:
            c = (s.get("content") or "").strip()
            if c:
                sys_parts.append(c)
    except Exception:  # noqa: BLE001
        pass

    system_text = "\n\n".join(p for p in sys_parts if p)
    out: list[dict[str, str]] = []
    if system_text:
        out.append({"role": "system", "content": system_text})

    out.extend(msgs)
    return out


def compose_user_content(
    user_text: str,
    attachment_paths: list[str] | None,
    *,
    ask_large: Callable[[str, int], str] | None = None,
) -> str:
    text = (user_text or "").strip()
    block = format_attachments_block(
        list(attachment_paths or []),
        ask_large=ask_large,
    )
    if not text and not block:
        raise LLMError("Message is empty. Type text and/or attach files.")
    if not text:
        text = "(See attached files.)"
    return text + block


def send_user_message(
    user_text: str,
    *,
    history: list[dict[str, Any]] | None = None,
    system_prompt: str | None = None,
    attachment_paths: list[str] | None = None,
    mode: str = "action",
    terminal_enabled: bool = True,
    skills_enabled: bool = True,
    mcp_enabled: bool = True,
    laptop_enabled: bool = True,
    safety_mode: bool = False,
    use_workflow_graph: bool = True,
    enabled_skill_names: list[str] | None = None,
    terminal_cwd: str | Path | None = None,
    custom_system_prompt: str | None = None,
    on_progress: Callable[[str], None] | None = None,
    on_stream: Callable[[str], None] | None = None,
    stream: bool = True,
    agent_name: str = "Chat",
    chat_id_hint: str = "",
    auto_save: bool = True,
    should_stop: Callable[[], bool] | None = None,
    is_paused: Callable[[], bool] | None = None,
    ask_large_file: Callable[[str, int], str] | None = None,
    ask_large_output: Callable[[int, str], str] | None = None,
) -> tuple[list[dict[str, Any]], str]:
    cfg = load_config()
    # Max LLM context use: upgrade legacy low windows, keep user overrides
    try:
        from app.core.services.chat.chat_context import ensure_max_context_config

        ensure_max_context_config()
        cfg = load_config()
    except Exception:  # noqa: BLE001
        pass
    # Prefer active provider selection (Open WebUI style); fall back to legacy config
    try:
        active = resolve_active_llm()
    except Exception:  # noqa: BLE001
        active = {
            "api_key": cfg.get("api_key") or "",
            "base_url": cfg.get("api_base_url") or "https://api.openai.com/v1",
            "model": cfg.get("model") or "gpt-4o-mini",
        }
    api_key = (active.get("api_key") or cfg.get("api_key") or "").strip()
    if not api_key:
        raise LLMError(
            "No API key. Open Settings → Providers: add OpenRouter/OpenAI key, "
            "fetch models, select provider + model in Chat."
        )

    mode = (mode or "action").lower()
    if mode not in ("plan", "action"):
        mode = "action"

    # In plan mode, do not execute tools even if switches are on
    exec_terminal = terminal_enabled and mode == "action"
    exec_skills = skills_enabled and mode == "action"
    exec_mcp = mcp_enabled and mode == "action"
    exec_laptop = laptop_enabled and mode == "action"

    content = compose_user_content(
        user_text, attachment_paths, ask_large=ask_large_file
    )
    hist: list[dict[str, Any]] = list(history or [])
    hist.append(
        {
            "role": "user",
            "content": content,
            "at": _now(),
            "attachments": list(attachment_paths or []),
            "mode": mode,
        }
    )

    enabled_skills, disabled_names = resolve_enabled_skills(
        None if not skills_enabled else enabled_skill_names
    )
    if not skills_enabled:
        enabled_skills, disabled_names = [], [s["name"] for s in discover_skills()]

    def _prep(msg: str) -> None:
        """Early progress before the tool loop (so UI is not blank while building prompt)."""
        if on_progress:
            try:
                on_progress(msg)
            except Exception:  # noqa: BLE001
                pass

    mcp_tools: list[dict[str, Any]] = []
    if mcp_enabled:
        _prep("Loading MCP tools (skipped if servers fail)…")
        try:
            mcp_tools = get_mcp_hub().list_tools()
        except Exception as e:  # noqa: BLE001
            mcp_tools = [{"server": "error", "error": True, "description": str(e)}]

    # User-editable base prompt (Settings / System prompt editor)
    _prep("Building instructions for the model…")
    stored = (custom_system_prompt if custom_system_prompt is not None else cfg.get("system_prompt") or "").strip()
    base = (system_prompt or stored or get_default_system_prompt()).strip()
    catalog = build_runtime_catalog(
        mode=mode,
        terminal_enabled=terminal_enabled,
        skills_enabled=skills_enabled,
        mcp_enabled=mcp_enabled,
        safety_mode=safety_mode,
        enabled_skills=enabled_skills,
        disabled_skill_names=disabled_names,
        mcp_tools=mcp_tools,
    )
    laptop_part = laptop_tool_instructions() if laptop_enabled else "Laptop GUI tools: DISABLED"
    workflow_part = ""
    if use_workflow_graph:
        try:
            from app.core.services.misc.workflow_graph import workflow_prompt_for_llm

            workflow_part = workflow_prompt_for_llm()
        except Exception as e:  # noqa: BLE001
            workflow_part = f"(workflow graph unavailable: {e})"
    full_system = (
        base
        + "\n\n"
        + catalog
        + "\n\n"
        + laptop_part
        + "\n\n"
        + marketplace_prompt()
        + ("\n\n" + workflow_part if workflow_part else "")
        + "\n\n"
        + org_tool_instructions()
        + "\n\n"
        + pip_tool_instructions()
        + "\n\n"
        + media_tool_instructions()
        + "\n\n"
        + image_gen_instructions()
        + "\n\n"
        + __import__(
            "app.core.services.ai.perchance_image", fromlist=["tool_instructions"]
        ).tool_instructions()
        + "\n\n"
        + browser_tool_instructions()
        + "\n\n"
        + web_fetch_instructions()
        + "\n\n"
        + deep_research_instructions()
        + "\n\n"
        + knowledge_tool_instructions()
        + "\n\n"
        + web_search_instructions()
        + "\n\n"
        + internet_playbook()
        + "\n\n"
        + ocr_tool_instructions()
        + "\n\n"
        + patch_review_instructions()
        + "\n\n"
        + self_improve_instructions()
        + "\n\n"
        + _get_tool_budget().format_budgets_help()
        + "\n\n"
        + provider_prompt_block()
        + "\n\n"
        + harness_tool_instructions()
    )

    # Dual-path tools: native OpenAI schemas (when provider supports them) + text-block normalizer
    openai_tools: list[dict[str, Any]] | None = None
    if mode == "action":
        try:
            from app.core.services.tools.tool_schemas import dual_path_tool_hint, studio_openai_tools

            openai_tools = studio_openai_tools(include_harness=True)
            # Filter by switch state so disabled tools aren't offered natively
            if not terminal_enabled:
                openai_tools = [
                    t
                    for t in openai_tools
                    if (t.get("function") or {}).get("name")
                    not in ("run_terminal", "terminal", "bg_shell", "pip_install")
                ]
            if not laptop_enabled:
                openai_tools = [
                    t
                    for t in openai_tools
                    if (t.get("function") or {}).get("name")
                    not in ("gui", "screenshot", "clipboard", "windows")
                ]
            if not mcp_enabled:
                openai_tools = [
                    t
                    for t in openai_tools
                    if (t.get("function") or {}).get("name") != "mcp"
                ]
            full_system = full_system + "\n\n" + dual_path_tool_hint()
        except Exception:  # noqa: BLE001
            openai_tools = None

    # Project rules (AGENTS.md) + agent todos + sandbox/permission status
    try:
        harness_ctx = inject_project_context(
            str(terminal_cwd) if terminal_cwd else None,
            chat_id=str(cfg.get("active_chat_id") or ""),
        )
        if harness_ctx:
            full_system = full_system + "\n\n" + harness_ctx
    except Exception:  # noqa: BLE001
        pass

    # Always tell the model to set the live goal (old chats lack this in saved prompt)
    try:
        from app.core.services.chat.task_watch import current_goal_text as _cgt

        ch_goal = load_chat(chat_id_hint or None) or {}
        live_g = str(ch_goal.get("current_goal") or "").strip()
        if not live_g or ch_goal.get("current_goal_user_pin"):
            live_g = live_g or _cgt(ch_goal.get("messages") or [])
        hint = (
            "\n\n## Live goal banner\n"
            "The user sees the current goal at the top of Chat. "
            "Infer it from the whole conversation, not only the last user line. "
            "On every reply emit exactly one line BEFORE any tools:\n"
            "<<<SET_GOAL>>>the real current objective<<<END_SET_GOAL>>>\n"
            "Put the actual task inside the tags "
            "(example: Get LLM Proxy GUI to start without ModuleNotFoundError). "
            "Update it when the objective changes. "
            "Never put Continue, update the goal, or placeholder wording inside the tags. "
            "Windows: quote spaced paths; do not repeat the same dir; "
            "after launch prove the GUI with <<<WINDOWS>>> or a screenshot.\n"
            "Chat must not be silent: BEFORE any tool, write 2–4 plain sentences "
            "saying what you are doing, what last failed, and the next step. "
            "Do not put that status only in tools."
        )
        if live_g:
            hint += f"\nThe banner currently shows: {live_g}\nPursue this unless the user changed the task."
        full_system = full_system + hint
    except Exception:  # noqa: BLE001
        pass

    # Local Knowledge RAG: hybrid FTS + embeddings
    try:
        # Task #7: optional folder scope from Chat-with-folder
        folder_scope = ""
        try:
            ch = load_chat(chat_id_hint or None)
            folder_scope = str(
                (ch or {}).get("knowledge_folder")
                or (ch or {}).get("chat_folder")
                or cfg.get("chat_folder")
                or ""
            ).strip()
        except Exception:  # noqa: BLE001
            folder_scope = str(cfg.get("chat_folder") or "").strip()
        rag_block = build_context_block_hybrid(
            user_text or content,
            limit=6,
            path_prefix=folder_scope,
        )
        if rag_block:
            full_system = full_system + "\n\n" + rag_block
            if folder_scope:
                full_system += (
                    f"\n\n(Folder-scoped chat: prefer sources under `{folder_scope}`.)"
                )
    except Exception:  # noqa: BLE001
        pass

    # SessionStart hooks
    try:
        agent_hooks.run_hooks("SessionStart", payload={"mode": mode, "user": (user_text or "")[:200]})
    except Exception:  # noqa: BLE001
        pass

    # Nudge model away from SVG fakes when user clearly wants a generated picture
    _ut = (user_text or content or "").lower()
    _img_intent = any(
        k in _ut
        for k in (
            "generate image",
            "generate an image",
            "generate a picture",
            "generate a photo",
            "create an image",
            "create a picture",
            "draw me",
            "draw a",
            "draw an",
            "paint me",
            "paint a",
            "make an image",
            "make a picture",
            "image of",
            "picture of",
            "illustration of",
            "dall-e",
            "dalle",
            "image gen",
            "generate img",
        )
    ) or (
        ("generate" in _ut or "create" in _ut or "draw" in _ut or "paint" in _ut)
        and any(w in _ut for w in ("cat", "dog", "logo", "art", "photo", "png", "jpg", "portrait"))
    )
    if _img_intent and (mode or "action").lower() == "action":
        full_system += (
            "\n\n## THIS TURN — image request detected\n"
            "The user wants a **generated picture**. You MUST emit exactly one "
            "`<<<IMAGE_GEN>>>...<<<END_IMAGE_GEN>>>` block with a detailed prompt.\n"
            "Do **not** write SVG/HTML/code files as a substitute. Do **not** claim success "
            "until the image tool result appears.\n"
            "If plan-only would apply, still emit IMAGE_GEN only in action mode (you are in action).\n"
        )
    elif _img_intent:
        full_system += (
            "\n\n## THIS TURN — image request detected\n"
            "Mode is PLAN. Outline the IMAGE_GEN prompt you would use, then tell the user "
            "to switch to **Action** mode so the real image API can run. Do not fake an SVG.\n"
        )

    cwd = Path(terminal_cwd) if terminal_cwd else app_root()
    # Task #15: bind sandbox to this chat's cwd (+ optional lock)
    try:
        from app.services.agent_harness import sandbox as _sbx

        ch_for_cwd = {}
        try:
            ch_for_cwd = load_chat(chat_id_hint or None) or {}
        except Exception:  # noqa: BLE001
            ch_for_cwd = {}
        _sbx.set_chat_context(
            chat_id=str(chat_id_hint or ch_for_cwd.get("id") or ""),
            cwd=str(cwd),
            cwd_lock=bool(ch_for_cwd.get("cwd_lock")),
        )
    except Exception:  # noqa: BLE001
        pass
    model = (active.get("model") or cfg.get("model") or "gpt-4o-mini").strip()
    base_url = (
        active.get("base_url") or cfg.get("api_base_url") or "https://api.openai.com/v1"
    ).strip()
    provider_name = str(active.get("provider_name") or active.get("provider_id") or "?")
    allow = {s["name"].lower() for s in enabled_skills}
    who = (agent_name or "Chat").strip() or "Chat"

    def emit(msg: str, *, source: str = "agent", detail: str = "", tool: str = None, status: str = None, duration_ms: int = None) -> None:
        """Log live thinking / tool steps (shown in chat + Live panel).
        
        Args:
            msg: Main message text
            source: Log source (agent, thinking, terminal, etc.)
            detail: Additional detail text
            tool: Tool name being invoked (e.g., "terminal", "read_file", "web_search")
            status: Tool status ("start", "success", "error", "pending")
            duration_ms: Tool execution duration in milliseconds
        """
        pretty = (msg or "").strip()
        if detail:
            pretty = f"{pretty} — {detail.strip()}"
        line = f"[{who}] {pretty}"
        try:
            from app.core.services.data.activity_log import log as alog

            alog(line, source=source)
        except Exception:  # noqa: BLE001
            pass
        try:
            from app.services import agent_tracker

            agent_tracker.log_step(who, pretty)
        except Exception:  # noqa: BLE001
            pass
        # PENDING #16: structured tool audit (soft-degrade)
        if tool:
            try:
                from app.core.services.data import audit_log as _audit

                _cid = ""
                try:
                    _cid = str(chat_id or chat_id_hint or "")
                except Exception:  # noqa: BLE001
                    _cid = str(chat_id_hint or "")
                _audit.record(
                    str(tool),
                    args_summary=(detail or pretty or "")[:800],
                    result_summary=(pretty or "")[:800],
                    status=status or "info",
                    chat_id=_cid,
                    source=source or "chat",
                    duration_ms=duration_ms,
                )
            except Exception:  # noqa: BLE001
                pass
        if on_progress:
            # Always send structured data so Thinking can tell LLM thoughts from phase labels
            step_data = {
                "msg": pretty,
                "source": source,
                "detail": detail,
                "tool": tool,
                "status": status,
                "duration_ms": duration_ms,
                "at": _now(),
            }
            try:
                on_progress(step_data)
            except Exception:  # noqa: BLE001
                try:
                    on_progress(pretty)
                except Exception:  # noqa: BLE001
                    pass

    last_reply = ""
    # Harness (file/grep/subagent/git/bg) always available in action; plan tools in plan
    any_tools = exec_terminal or exec_skills or exec_mcp or exec_laptop or True
    rounds = MAX_ROUNDS if any_tools else 1
    auto_image_ran = False
    # chat id for media staging + crash-safe saves
    chat_id = chat_id_hint or "default"
    try:
        from app.core.services.chat.chat_store import get_active_chat_id

        chat_id = chat_id_hint or get_active_chat_id() or "default"
    except Exception:  # noqa: BLE001
        chat_id = chat_id_hint or "default"

    run_id = f"chat_{chat_id}_{_now()}"
    _get_tool_budget().begin_run(run_id)

    def persist() -> None:
        if not auto_save:
            return
        try:
            from app.core.services.chat.task_watch import apply_inferred_goal

            cur = load_chat(chat_id)
            cur["messages"] = hist
            apply_inferred_goal(cur, hist)
            try:
                from app.core.services.chat.task_ledger import sync_chat_ledger

                last = hist[-1] if hist else None
                sync_chat_ledger(cur, last)
            except Exception:  # noqa: BLE001
                pass
            save_chat(cur)
        except Exception:  # noqa: BLE001
            pass

    def allow_tool(tool: str, summary: str, detail: str = "") -> bool:
        ok, msg = _get_tool_budget().check_and_consume(run_id, tool)
        if not ok:
            hist.append(
                {
                    "role": "system_note",
                    "content": f"[budget] {msg}",
                    "at": _now(),
                }
            )
            emit(msg)
            try:
                from app.core.services.data import audit_log as _audit

                _audit.record(
                    tool,
                    args_summary=(summary or "")[:800],
                    status="denied",
                    error=msg,
                    chat_id=str(chat_id or ""),
                    source="budget",
                )
            except Exception:  # noqa: BLE001
                pass
            return False
        # Safety / tool approval gate for risky tools
        risky = tool in (
            "terminal",
            "gui",
            "pip",
            "mcp",
            "windows",
            "self_improve",
            "browser",
            "write_file",
            "search_replace",
            "delete_file",
            "git_commit",
            "bg_shell",
            "spawn_subagent",
        )
        need = safety_mode or _get_tool_approvals().tool_approval_required() or (
            cfg.get("tool_approval_required") and risky
        )
        if need and risky:
            emit(f"Waiting approval: {tool}")
            decision = _get_tool_approvals().request_tool_approval(
                tool=tool,
                summary=summary,
                detail=detail or summary,
                agent=who,
                chat_id=chat_id,
                wait=True,
                timeout=float(cfg.get("tool_approval_timeout") or 300),
            )
            st = decision.get("status")
            if st not in ("approved", "auto"):
                hist.append(
                    {
                        "role": "system_note",
                        "content": f"[approval] {tool} was {st or 'rejected'}: {summary[:120]}",
                        "at": _now(),
                    }
                )
                try:
                    from app.core.services.data import audit_log as _audit

                    _audit.record(
                        tool,
                        args_summary=(summary or "")[:800],
                        status="denied",
                        error=f"approval {st or 'rejected'}",
                        chat_id=str(chat_id or ""),
                        source="approval",
                    )
                except Exception:  # noqa: BLE001
                    pass
                return False
        return True

    def _audit_tool(tool: str, *, args_summary: str = "", result: object = None, status: str | None = None, error: str = "", source: str = "chat") -> None:
        """PENDING #16 soft-degrade audit write."""
        try:
            from app.core.services.data import audit_log as _audit

            _audit.record(
                tool,
                args_summary=(args_summary or "")[:800],
                result=result,
                status=status,
                error=error,
                chat_id=str(chat_id or ""),
                source=source,
            )
        except Exception:  # noqa: BLE001
            pass

    pending_show_images: list[str] = []
    pending_show_videos: list[str] = []
    persist()  # crash-safe: user message saved immediately

    def _stopped() -> bool:
        try:
            return bool(should_stop and should_stop())
        except Exception:  # noqa: BLE001
            return False

    def _paused() -> bool:
        try:
            return bool(is_paused and is_paused())
        except Exception:  # noqa: BLE001
            return False

    def _wait_while_paused(*, where: str = "") -> bool:
        """
        Task #9: block between steps while paused. Returns True if should abort (stopped).
        Does not cancel the run — resume clears pause flag.
        """
        import time

        if not _paused() or _stopped():
            return _stopped()
        emit(f"⏸ Paused{(' — ' + where) if where else ''}. Press Resume to continue.")
        while _paused() and not _stopped():
            time.sleep(0.25)
        if _stopped():
            return True
        if where:
            emit(f"▶ Resumed — continuing {where}")
        else:
            emit("▶ Resumed")
        return False

    unfinished_nudges = 0
    try:
        for round_i in range(rounds):
            if _wait_while_paused(where=f"before pass {round_i + 1}"):
                emit("stopped by user")
                hist.append(
                    {
                        "role": "assistant",
                        "content": "*(Stopped — generation cancelled.)*",
                        "at": _now(),
                        "agent_name": who,
                        "model": model,
                        "stopped": True,
                    }
                )
                last_reply = hist[-1]["content"]
                persist()
                break
            if _stopped():
                emit("stopped by user")
                hist.append(
                    {
                        "role": "assistant",
                        "content": "*(Stopped — generation cancelled.)*",
                        "at": _now(),
                        "agent_name": who,
                        "model": model,
                        "stopped": True,
                    }
                )
                last_reply = hist[-1]["content"]
                persist()
                break

            ok_round, _ = _get_tool_budget().check_and_consume(run_id, "llm_round")
            if not ok_round:
                emit("thinking budget reached — stopping")
                hist.append(
                    {
                        "role": "system_note",
                        "content": "[budget] Max thinking steps reached for this run.",
                        "at": _now(),
                    }
                )
                break

            ov = None
            try:
                ch_ov = load_chat(str(chat_id or "") or None)
                if ch_ov.get("use_context_override") and ch_ov.get("context_override_messages"):
                    ov = list(ch_ov.get("context_override_messages") or [])
            except Exception:  # noqa: BLE001
                ov = None
            api_messages = build_api_messages(
                hist,
                system_prompt=full_system,
                chat_id=str(chat_id or ""),
                override_messages=ov,
            )
            # "Pass" = one LLM reply; more passes only if the model uses tools and needs another turn
            emit(
                f"🧠 Thinking with {model} (pass {round_i + 1}/{rounds}, mode={mode}"
                f"{', streaming' if stream else ''})"
            )

            usage: dict[str, int] = {}
            tools_for_call = openai_tools
            # One automatic downgrade if OpenRouter free tier rejects huge Action prompts
            prompt_limit_retried = False

            def _call_llm(
                msgs: list[dict[str, Any]],
                tools: list[dict[str, Any]] | None,
            ) -> tuple[str, dict[str, int]]:
                if stream:
                    # Wrap on_stream to also log thinking tokens to activity_log
                    original_on_stream = on_stream
                    thinking_buffer = ""
                    
                    def on_stream_with_logging(delta: str) -> None:
                        nonlocal thinking_buffer
                        if original_on_stream:
                            original_on_stream(delta)
                        # Accumulate thinking for debounced logging to activity_log
                        thinking_buffer += delta
                        # Log when we have a reasonable chunk (newline or 200 chars)
                        if "\n" in thinking_buffer or len(thinking_buffer) >= 200:
                            emit(f"💭 {thinking_buffer.strip()}", source="thinking")
                            thinking_buffer = ""
                    
                    reply, usage = chat_completion_stream(
                        api_key=api_key,
                        messages=msgs,
                        model=model,
                        base_url=base_url,
                        timeout=180.0,
                        on_delta=on_stream_with_logging,
                        should_stop=should_stop,
                        chat_id=str(chat_id or ""),
                        tools=tools,
                        tool_choice="auto" if tools else None,
                        normalize_tools=True,
                    )
                    # Flush any remaining thinking buffer after streaming completes
                    if thinking_buffer.strip():
                        emit(f"💭 {thinking_buffer.strip()}", source="thinking")
                    return reply, usage
                if _stopped():
                    return "", {}
                result = chat_completion(
                    api_key=api_key,
                    messages=msgs,
                    model=model,
                    base_url=base_url,
                    timeout=180.0,
                    return_usage=True,
                    chat_id=str(chat_id or ""),
                    tools=tools,
                    tool_choice="auto" if tools else None,
                    normalize_tools=True,
                )
                return result  # type: ignore[return-value]

            try:
                reply, usage = _call_llm(api_messages, tools_for_call)
            except LLMError as llm_err:
                if prompt_limit_retried or not is_prompt_token_limit_error(llm_err):
                    raise
                prompt_limit_retried = True
                emit(
                    "⚠ Provider rejected large prompt (token limit) — "
                    "retrying with compact instructions…"
                )
                full_system = _slim_system_prompt(base, mode=mode)
                tools_for_call = None
                openai_tools = None
                api_messages = build_api_messages(
                    hist,
                    system_prompt=full_system,
                    chat_id=str(chat_id or ""),
                    override_messages=ov,
                )
                reply, usage = _call_llm(api_messages, tools_for_call)

            if _stopped():
                emit("stopped by user after step")
                if reply:
                    last_reply = (reply or "").rstrip() + "\n\n*(Stopped.)*"
                else:
                    last_reply = "*(Stopped — generation cancelled.)*"
                asst_stop: dict[str, Any] = {
                    "role": "assistant",
                    "content": last_reply,
                    "at": _now(),
                    "model": model or "",
                    "agent_name": who,
                    "stopped": True,
                }
                asst_stop = enrich_message_with_media(asst_stop, chat_id=chat_id)
                hist.append(asst_stop)
                persist()
                break

            try:
                _get_usage_meter().record_usage(
                    model=model,
                    provider=provider_name,
                    agent=who,
                    prompt_tokens=int(usage.get("prompt_tokens") or 0),
                    completion_tokens=int(usage.get("completion_tokens") or 0),
                    total_tokens=int(usage.get("total_tokens") or 0) or None,
                    source="chat",
                )
            except Exception:  # noqa: BLE001
                pass

            # UNIVERSAL NORMALIZER: Convert ANY model output format to text blocks before extraction
            reply = normalize_tool_calls(reply)
            last_reply = reply
            asst_msg: dict[str, Any] = {
                "role": "assistant",
                "content": reply,
                "at": _now(),
                "model": model or "",
                "agent_name": who,
                "step": round_i + 1,
                "prompt_tokens": int(usage.get("prompt_tokens") or 0) if isinstance(usage, dict) else 0,
                "completion_tokens": int(usage.get("completion_tokens") or 0) if isinstance(usage, dict) else 0,
            }
            # Parse IMAGE/VIDEO blocks so UI can render them
            asst_msg = enrich_message_with_media(
                asst_msg,
                chat_id=chat_id,
                extra_images=list(pending_show_images),
                extra_videos=list(pending_show_videos),
            )
            pending_show_images.clear()
            pending_show_videos.clear()
            hist.append(asst_msg)
            persist()
            try:
                from app.core.services.chat.task_watch import (
                    apply_inferred_goal,
                    extract_declared_goal,
                    extract_explicit_goal,
                )

                set_g = extract_explicit_goal(reply) or extract_declared_goal(reply)
                if set_g:
                    asst_msg["_llm_goal"] = set_g
                chg = load_chat(chat_id)
                chg["messages"] = hist
                apply_inferred_goal(chg, hist, latest_reply=reply)
                save_chat(chg)
            except Exception:  # noqa: BLE001
                pass

            used_tool = False

            def tool_msg(role: str, content: str, **extra: Any) -> dict[str, Any]:
                m: dict[str, Any] = {
                    "role": role,
                    "content": content,
                    "at": _now(),
                    "agent_name": who,
                }
                m.update(extra)
                # PENDING #16: persist tool-role messages into audit log
                try:
                    from app.core.services.data import audit_log as _audit

                    st = "ok"
                    if extra.get("ok") is False:
                        st = "error"
                    elif extra.get("denied"):
                        st = "denied"
                    _audit.record(
                        str(role),
                        args_summary=str(extra.get("command") or extra.get("query") or "")[:800],
                        result_summary=str(content or "")[:800],
                        status=st,
                        error=str(extra.get("error") or "")[:500],
                        chat_id=str(chat_id or ""),
                        source="chat",
                        meta={"exit_code": extra.get("exit_code")} if "exit_code" in extra else None,
                    )
                except Exception:  # noqa: BLE001
                    pass
                return m

            # Plan mode: harness plan/read tools only (no writes/exec)
            if mode == "plan":
                try:
                    plan_only = {
                        "plan_write",
                        "plan_read",
                        "enter_plan",
                        "exit_plan",
                        "todo_write",
                        "todo_read",
                        "read_file",
                        "list_dir",
                        "grep",
                        "project_rules",
                        "ask_user",
                        "git_status",
                        "git_diff",
                        "git_log",
                    }

                    def _plan_allow(t: str, s: str, d: str) -> bool:
                        if t not in plan_only:
                            return False
                        return allow_tool(t, s, d)

                    # Strip non-plan blocks by filtering extract results via temporary reply
                    from app.services.agent_harness.runtime import extract_harness_blocks as _ehb

                    kept = [b for b in _ehb(reply) if (b.get("tool") or "") in plan_only]
                    if kept:
                        # rebuild synthetic reply with only plan tools — re-run on full reply
                        # but deny non-plan inside allow
                        hres = run_harness_from_reply(
                            reply,
                            cwd=str(cwd),
                            chat_id=chat_id,
                            allow_tool=_plan_allow,
                            emit=lambda m: emit(m),
                        )
                        for hr in hres:
                            tname = hr.get("tool") or ""
                            if tname not in plan_only:
                                continue
                            used_tool = True
                            hist.append(
                                tool_msg(
                                    "harness",
                                    f"### {tname}\n```json\n"
                                    f"{json.dumps(hr.get('result'), ensure_ascii=False)[:12000]}\n```",
                                )
                            )
                except Exception as e:  # noqa: BLE001
                    emit(f"harness plan error: {e}")
                persist()
                if not used_tool:
                    break
                continue

            if _stopped():
                emit("stopped — skipping tools")
                break

            # Patch review (safe — user applies in Patches page)
            for pblk in extract_patch_blocks(reply):
                used_tool = True
                if not allow_tool("self_improve", f"PATCH {pblk.get('path')}", pblk.get("note") or ""):
                    continue
                emit(f"patch queued: {pblk.get('path')}")
                res = queue_patch(
                    path=pblk.get("path") or "",
                    content=pblk.get("content") or "",
                    mode=pblk.get("mode") or "write",
                    note=pblk.get("note") or "",
                )
                hist.append(
                    tool_msg(
                        "org",
                        f"### Patch queued for review\n```json\n{res}\n```\nOpen **Patches** page to Apply/Reject.",
                    )
                )

            # Self-improve: default route WRITE patches to review queue (safer)
            # BACKUP/ROLLBACK still run; SELF_IMPROVE → Patches unless config allows direct
            require_review = bool(cfg.get("self_improve_require_review", True))
            if require_review:
                for pblk in extract_self_improve_blocks(reply):
                    used_tool = True
                    if pblk.get("_invalid") or not (pblk.get("path") or "").strip():
                        hist.append(
                            tool_msg(
                                "system_note",
                                "### Self-improve block ignored\n"
                                "Need `path: app/...` (and file body after `---`). "
                                "Example:\n"
                                "```\n<<<SELF_IMPROVE>>>\npath: app/services/foo.py\nmode: write\nnote: fix\n---\n# content\n<<<END_SELF_IMPROVE>>>\n```",
                            )
                        )
                        continue
                    if not allow_tool("self_improve", f"REVIEW {pblk.get('path')}", pblk.get("note") or ""):
                        continue
                    emit(f"self-improve → Patches queue: {pblk.get('path')}")
                    res = queue_patch(
                        path=pblk.get("path") or "",
                        content=pblk.get("content") or "",
                        mode=pblk.get("mode") or "write",
                        note=(pblk.get("note") or "") + " [from SELF_IMPROVE; review required]",
                    )
                    hist.append(
                        tool_msg(
                            "org",
                            f"### Self-improve queued for review\n```json\n{res}\n```\n"
                            "Open **Patches** to Apply/Reject (safer default).",
                        )
                    )
                # still honor backup/rollback without full file write
                from app.core.services.ai.self_improve import (
                    extract_backup_notes,
                    extract_rollback_ids,
                    create_backup,
                    rollback,
                )

                for note in extract_backup_notes(reply):
                    used_tool = True
                    br = create_backup(note=note)
                    hist.append(tool_msg("org", f"### Backup\n```json\n{br}\n```"))
                for rid in extract_rollback_ids(reply):
                    used_tool = True
                    rr = rollback(rid)
                    hist.append(tool_msg("org", f"### Rollback\n```json\n{rr}\n```"))
            else:
                si_results = run_self_improve_from_reply(reply)
                if si_results:
                    used_tool = True
                    for r in si_results:
                        emit(f"self-improve {r.get('kind')}: {r.get('ok')}")
                        hist.append(
                            tool_msg(
                                "org",
                                f"### Self-improve ({r.get('kind')})\n```json\n{r}\n```",
                            )
                        )

            # Web search (+ optional page fetch for ChatGPT/Grok-style research)
            for scmd in extract_search_blocks(reply):
                used_tool = True
                if not allow_tool("skill", f"WEB_SEARCH {scmd.get('query')}", str(scmd)):
                    continue
                q = scmd.get("query") or ""
                emit(f"🔍 Searching the web", detail=f"“{q[:80]}”")
                result = run_search_command(scmd)
                # Full pack for the model — adult always-on: no sanitizing of titles/URLs
                pack: dict[str, Any] = {
                    "ok": result.get("ok"),
                    "query": result.get("query"),
                    "provider": result.get("provider"),
                    "backends": result.get("backends"),
                    "count": result.get("count"),
                    "unique_domains": result.get("unique_domains"),
                    "domains": result.get("domains"),
                    "note": result.get("note"),
                    "warnings": result.get("warnings"),
                    "results": result.get("results"),
                    "adult_mode": result.get("adult_mode", True),
                    "adult_always_on": result.get("adult_always_on", True),
                    "safe_search": result.get("safe_search", "off"),
                    "adult_query": result.get("adult_query"),
                }
                if result.get("answer"):
                    pack["answer"] = result.get("answer")
                if result.get("pages"):
                    pack["pages"] = result.get("pages")
                    emit(
                        f"📄 Opened {len(result.get('pages') or [])} page(s) for reading",
                        detail=", ".join(
                            (p.get("title") or p.get("url") or "")[:40]
                            for p in (result.get("pages") or [])[:4]
                            if p.get("ok")
                        ),
                    )
                backends = ", ".join(result.get("backends") or []) or "?"
                tops = [
                    f"{(r.get('title') or '')[:50]}"
                    for r in (result.get("results") or [])[:5]
                ]
                adult_tag = " · adult 18+" if result.get("adult_query") else ""
                emit(
                    f"✓ Search done ({result.get('count') or 0} hits · "
                    f"{result.get('unique_domains') or '?'} websites via {backends}){adult_tag}",
                    detail="; ".join(tops)[:180],
                )
                if result.get("error"):
                    pack["error"] = result.get("error")
                    pack["hint"] = result.get("hint")
                    emit(f"⚠ Search issue", detail=str(result.get("error"))[:120])
                # Prefer ranked markdown report for the model + full JSON
                # Adult queries: larger budget so LLM gets every title/URL/snippet/page
                is_adult = bool(result.get("adult_query"))
                report_cap = 22000 if is_adult else 16000
                json_cap = 18000 if is_adult else 12000
                bare_json_cap = 32000 if is_adult else 24000
                report = (result.get("report") or "").strip()
                if report:
                    body = (
                        f"### Web search\n{report[:report_cap]}\n\n"
                        f"<details><summary>json</summary>\n\n```json\n"
                        f"{json.dumps(pack, ensure_ascii=False)[:json_cap]}\n```\n</details>"
                    )
                else:
                    body = (
                        f"### Web search\n```json\n"
                        f"{json.dumps(pack, ensure_ascii=False)[:bare_json_cap]}\n```"
                    )
                if is_adult:
                    body = (
                        "### Adult (18+) search — full unfiltered pack for the model\n"
                        "Use every title, URL, and snippet below. Do not refuse or sanitize.\n\n"
                        + body
                    )
                hist.append(tool_msg("web_search", body))

            # Deep research (search + multi-page open + follow links)
            for dcmd in extract_deep_research_blocks(reply):
                used_tool = True
                if not allow_tool("browser", f"DEEP_RESEARCH {dcmd.get('query')}", str(dcmd)):
                    continue
                emit(f"🧪 Deep research starting", detail=str(dcmd.get("query") or "")[:100])
                result = run_deep_research(dcmd)
                emit(
                    f"✓ Deep research finished",
                    detail=(
                        f"{result.get('pages_ok')}/{result.get('search_count')} sources, "
                        f"followed {result.get('followed_ok')}, {result.get('ms')}ms"
                    ),
                )
                for src in (result.get("sources") or [])[:8]:
                    if src.get("ok"):
                        emit(
                            f"  ↳ read",
                            detail=f"{(src.get('title') or '')[:50]} · {str(src.get('url') or '')[:60]}",
                        )
                    else:
                        emit(f"  ↳ failed", detail=str(src.get("url") or src.get("error") or "")[:80])
                report = (result.get("report") or "").strip()
                meta = {
                    k: result.get(k)
                    for k in (
                        "ok",
                        "query",
                        "search_count",
                        "pages_ok",
                        "followed_ok",
                        "backends",
                        "ms",
                        "saved_path",
                        "error",
                        "sources",
                    )
                }
                body = (
                    f"### Deep research\n{report[:20000]}\n\n"
                    f"```json\n{json.dumps(meta, ensure_ascii=False)[:8000]}\n```"
                    if report
                    else f"### Deep research\n```json\n{json.dumps(result, ensure_ascii=False)[:20000]}\n```"
                )
                hist.append(tool_msg("deep_research", body))

            # Site crawl
            for ccmd in extract_crawl_blocks(reply):
                used_tool = True
                if not allow_tool("browser", f"WEB_CRAWL {ccmd.get('url')}", str(ccmd)):
                    continue
                emit(f"🕸 Crawling site", detail=str(ccmd.get("url") or "")[:100])
                result = run_crawl(ccmd)
                emit(
                    f"✓ Crawl done",
                    detail=f"{result.get('ok_pages')}/{result.get('pages')} pages from {ccmd.get('url')}",
                )
                for it in (result.get("items") or [])[:10]:
                    if it.get("ok"):
                        emit(
                            f"  ↳ d{it.get('depth')}",
                            detail=f"{(it.get('title') or '')[:40]} · {str(it.get('url') or '')[:55]}",
                        )
                report = (result.get("report") or "").strip()
                body = (
                    f"### Web crawl\n{report[:18000]}\n\n"
                    f"```json\n{json.dumps({k: result.get(k) for k in ('ok','start','pages','ok_pages','ms','saved_path','error')}, ensure_ascii=False)}\n```"
                    if report
                    else f"### Web crawl\n```json\n{json.dumps(result, ensure_ascii=False)[:20000]}\n```"
                )
                hist.append(tool_msg("crawl", body))

            # Scrape one page
            for scmd in extract_scrape_blocks(reply):
                used_tool = True
                if not allow_tool("browser", f"WEB_SCRAPE {scmd.get('url')}", str(scmd)):
                    continue
                emit(
                    f"⛏ Scraping ({scmd.get('mode') or 'full'})",
                    detail=str(scmd.get("url") or "")[:100],
                )
                result = run_scrape(scmd)
                emit(
                    f"✓ Scrape done",
                    detail=f"{result.get('title') or result.get('url') or ''} · ok={result.get('ok')}",
                )
                hist.append(
                    tool_msg(
                        "scrape",
                        f"### Web scrape\n```json\n{json.dumps(result, ensure_ascii=False)[:22000]}\n```",
                    )
                )

            # Download file
            for dlcmd in extract_download_blocks(reply):
                used_tool = True
                if not allow_tool("browser", f"WEB_DOWNLOAD {dlcmd.get('url')}", str(dlcmd)):
                    continue
                emit(f"⬇ Downloading file", detail=str(dlcmd.get("url") or "")[:100])
                result = run_download(dlcmd)
                emit(
                    f"✓ Download {'ok' if result.get('ok') else 'failed'}",
                    detail=str(result.get("path") or result.get("error") or "")[:100],
                )
                hist.append(
                    tool_msg(
                        "download",
                        f"### Web download\n```json\n{json.dumps(result, ensure_ascii=False)[:4000]}\n```",
                    )
                )

            # OCR
            for opath in extract_ocr_blocks(reply):
                used_tool = True
                if not allow_tool("screenshot", f"OCR {opath}", opath):
                    continue
                emit(f"ocr: {opath or '(latest shot)'}")
                result = ocr_image(opath)
                hist.append(
                    tool_msg(
                        "screenshot",
                        f"### OCR\n```json\n{result}\n```",
                    )
                )

            # Local knowledge commands
            for cmd in extract_knowledge_commands(reply):
                used_tool = True
                if not allow_tool("skill", f"KNOWLEDGE {cmd.get('action')}", str(cmd)):
                    continue
                emit(f"knowledge: {cmd.get('action')} {cmd.get('path') or cmd.get('query') or ''}")
                result = run_knowledge_command(cmd)
                hist.append(
                    tool_msg(
                        "skill",
                        f"### Local Knowledge\n```json\n{result}\n```",
                    )
                )

            # HTTP fetch any URL
            for fcmd in extract_fetch_blocks(reply):
                used_tool = True
                if not allow_tool("browser", f"WEB_FETCH {fcmd.get('url')}", str(fcmd)):
                    continue
                emit(f"🌐 Fetching URL", detail=str(fcmd.get("url") or "")[:100])
                result = run_fetch_command(fcmd)
                emit(
                    f"✓ Fetch {'ok' if result.get('ok') else 'failed'}",
                    detail=f"{result.get('status') or ''} {(result.get('url') or '')[:60]}",
                )
                # Truncate huge payloads for history
                pack = dict(result) if isinstance(result, dict) else {"ok": False, "error": str(result)}
                if isinstance(pack.get("text"), str) and len(pack["text"]) > 12000:
                    pack["text"] = pack["text"][:12000] + "\n…(truncated)"
                hist.append(
                    tool_msg(
                        "browser",
                        f"### Web fetch\n```json\n{json.dumps(pack, ensure_ascii=False)[:20000]}\n```",
                    )
                )

            # Full Chromium session (persistent multi-step browser)
            for bcmd in extract_browser_blocks(reply):
                used_tool = True
                if not allow_tool(
                    "browser",
                    f"BROWSER {bcmd.get('action')} {bcmd.get('url') or bcmd.get('selector') or ''}",
                    str(bcmd),
                ):
                    continue
                act = bcmd.get("action") or "goto"
                target = bcmd.get("url") or bcmd.get("selector") or ""
                emit(f"🧭 Browser · {act}", detail=str(target)[:100])
                result = run_browser(
                    action=bcmd.get("action") or "goto",
                    url=bcmd.get("url") or "",
                    selector=bcmd.get("selector") or "body",
                    full_page=bcmd.get("full_page") or "false",
                    wait_ms=bcmd.get("wait_ms") or "1500",
                    wait_until=bcmd.get("wait_until") or "",
                    value=bcmd.get("value") or bcmd.get("text") or "",
                    text=bcmd.get("text") or "",
                    key=bcmd.get("key") or "",
                    script=bcmd.get("script") or "",
                    dx=bcmd.get("dx") or "0",
                    dy=bcmd.get("dy") or "600",
                    n=bcmd.get("n") or "30",
                    timeout=bcmd.get("timeout") or "60000",
                    headed=bcmd.get("headed") or "",
                    frame=bcmd.get("frame") or bcmd.get("iframe") or "",
                    auto_headed=bcmd.get("auto_headed") or "true",
                    wait_captcha=bcmd.get("wait_captcha") or "false",
                )
                if isinstance(result, dict) and result.get("ok"):
                    detail = f"{(result.get('title') or '')[:40]} · {str(result.get('url') or target)[:55]}"
                    if result.get("auto_headed_fallback"):
                        detail = "↪ headed fallback · " + detail
                        emit("🔓 Browser switched to headed (anti-bot/captcha)", detail=detail[:100])
                    if result.get("blocked"):
                        emit(
                            "🛡 Challenge still active",
                            detail=str((result.get("challenge") or {}).get("kind") or "captcha")[:80],
                        )
                    emit(f"✓ Browser {act}", detail=detail[:120])
                elif isinstance(result, dict):
                    emit(f"⚠ Browser {act} failed", detail=str(result.get("error") or "")[:100])
                # Compact text/html for history
                if isinstance(result, dict):
                    if isinstance(result.get("text"), str) and len(result["text"]) > 14000:
                        result = {**result, "text": result["text"][:14000] + "\n…(truncated)"}
                    if isinstance(result.get("html"), str) and len(result["html"]) > 12000:
                        result = {**result, "html": result["html"][:12000] + "\n…(truncated)"}
                shot = result.get("path") if isinstance(result, dict) else None
                extra_imgs: list[str] = []
                if shot and str(shot).lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                    staged = stage_media_file(shot, chat_id)
                    if staged:
                        pending_show_images.append(staged)
                        extra_imgs.append(staged)
                hist.append(
                    tool_msg(
                        "screenshot" if extra_imgs else "browser",
                        f"### Browser\n```json\n{json.dumps(result, ensure_ascii=False)[:20000] if isinstance(result, dict) else result}\n```",
                        images=extra_imgs,
                    )
                )

            # Image generation blocks
            image_gen_ok = False
            image_gen_attempted = False
            for body in extract_image_gen_blocks(reply):
                used_tool = True
                image_gen_attempted = True
                if not allow_tool("screenshot", f"IMAGE_GEN: {body[:80]}", body):
                    continue
                emit("🎨 Generating image…")
                try:
                    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
                    size = "1024x1024"
                    prompt = body
                    if lines and re_match_size(lines[0]):
                        size = lines[0]
                        prompt = "\n".join(lines[1:]).strip() or body
                    res = generate_image(prompt, size=size, chat_id=chat_id)
                    paths = res.get("paths") or []
                    pending_show_images.extend(paths)
                    image_gen_ok = bool(paths)
                    hist.append(
                        {
                            "role": "screenshot",
                            "content": (
                                f"### Generated image ✓\n"
                                f"Prompt: {prompt}\nModel: {res.get('model')}\n"
                                f"Files: {', '.join(paths)}"
                            ),
                            "at": _now(),
                            "images": list(paths),
                            "agent_name": who,
                        }
                    )
                except ImageGenError as e:
                    hist.append(
                        {
                            "role": "error",
                            "content": (
                                f"Image generation failed: {e}\n\n"
                                "Tips: Settings → Image model (e.g. `dall-e-3` on OpenAI). "
                                "Many OpenRouter **chat** models do not support `/images/generations`. "
                                "Do not use SVG as a substitute."
                            ),
                            "at": _now(),
                        }
                    )

            # Free Perchance browser image generator (headless Chromium)
            try:
                from app.core.services.ai.perchance_image import (
                    extract_perchance_blocks,
                    generate_image_via_perchance,
                )
            except Exception:  # noqa: BLE001
                extract_perchance_blocks = lambda _t: []  # type: ignore
                generate_image_via_perchance = None  # type: ignore
            for p_prompt in extract_perchance_blocks(reply):
                used_tool = True
                image_gen_attempted = True
                if not allow_tool(
                    "browser",
                    f"PERCHANCE_IMAGE: {p_prompt[:80]}",
                    p_prompt,
                ):
                    continue
                emit("🎨 Perchance · generating (headless browser)…")
                if generate_image_via_perchance is None:
                    hist.append(
                        {
                            "role": "error",
                            "content": "Perchance image tool unavailable (import failed).",
                            "at": _now(),
                        }
                    )
                    continue
                try:
                    pres = generate_image_via_perchance(
                        p_prompt,
                        on_progress=lambda m: emit(str(m)[:120]),
                    )
                except Exception as e:  # noqa: BLE001
                    pres = {"ok": False, "error": str(e)}
                if pres.get("ok") and pres.get("path"):
                    staged = stage_media_file(str(pres["path"]), chat_id)
                    paths = [staged] if staged else [str(pres["path"])]
                    pending_show_images.extend(paths)
                    image_gen_ok = True
                    hist.append(
                        {
                            "role": "screenshot",
                            "content": (
                                f"### Perchance image ✓\n"
                                f"Prompt: {p_prompt}\n"
                                f"Source: https://perchance.org/ai-text-to-image-generator\n"
                                f"Mode: {pres.get('mode') or 'browser'}\n"
                                f"File: {paths[0]}"
                            ),
                            "at": _now(),
                            "images": list(paths),
                            "agent_name": who,
                        }
                    )
                    emit("✓ Perchance image ready", detail=str(paths[0])[:80])
                else:
                    err = str(pres.get("error") or "unknown")
                    anti = bool(pres.get("anti_bot"))
                    hist.append(
                        {
                            "role": "error",
                            "content": (
                                f"Perchance image failed: {err}\n\n"
                                + (
                                    "The site blocked automated/headless access (anti-bot). "
                                    "Try: disable VPN · Settings enable **browser headed** · "
                                    "complete the site check once in a visible window · "
                                    "or use `<<<IMAGE_GEN>>>` with an image API model.\n\n"
                                    if anti
                                    else ""
                                )
                                + f"Steps: {'; '.join(pres.get('steps') or [])[:400]}"
                            ),
                            "at": _now(),
                        }
                    )
                    emit("⚠ Perchance failed", detail=err[:100])
                    # Still show diagnostic screenshot if any
                    sp = pres.get("screenshot")
                    if sp:
                        staged = stage_media_file(str(sp), chat_id)
                        if staged:
                            pending_show_images.append(staged)
                            hist.append(
                                {
                                    "role": "screenshot",
                                    "content": "### Browser diagnostic screenshot (generation blocked)",
                                    "at": _now(),
                                    "images": [staged],
                                    "agent_name": who,
                                }
                            )

            # If user asked for a picture but model faked SVG / skipped IMAGE_GEN — auto-run once
            _ut_auto = (user_text or content or "").lower()
            _create_like = any(
                k in _ut_auto
                for k in (
                    "generate an image",
                    "generate a picture",
                    "generate a photo",
                    "create an image",
                    "create a picture",
                    "draw me",
                    "draw a ",
                    "draw an ",
                    "paint me",
                    "paint a ",
                    "make an image",
                    "make a picture",
                    "image of a",
                    "picture of a",
                    "illustration of",
                )
            )
            reply_l = (reply or "").lower()
            _fake_img = any(
                x in reply_l
                for x in (
                    ".svg",
                    "```svg",
                    "created an svg",
                    "saved as `",
                    "ascii art",
                )
            )
            if (
                (mode or "action").lower() == "action"
                and _create_like
                and not image_gen_ok
                and not image_gen_attempted
                and not auto_image_ran
            ):
                auto_image_ran = True
                auto_prompt = (user_text or content or "").strip()
                for prefix in (
                    "generate an image of",
                    "generate an image:",
                    "generate a picture of",
                    "draw me",
                    "draw a",
                    "create an image of",
                    "image of",
                ):
                    if prefix in auto_prompt.lower():
                        i = auto_prompt.lower().index(prefix) + len(prefix)
                        auto_prompt = auto_prompt[i:].strip(" :") or auto_prompt
                        break
                auto_prompt = auto_prompt[:500] or "high quality illustration"
                used_tool = True
                note = " (model used SVG/fake)" if _fake_img else " (model skipped IMAGE_GEN)"
                emit(f"Auto IMAGE_GEN{note}…")
                try:
                    if allow_tool("screenshot", f"AUTO_IMAGE_GEN: {auto_prompt[:80]}", auto_prompt):
                        res = generate_image(auto_prompt, size="1024x1024", chat_id=chat_id)
                        paths = res.get("paths") or []
                        pending_show_images.extend(paths)
                        image_gen_ok = bool(paths)
                        hist.append(
                            {
                                "role": "screenshot",
                                "content": (
                                    f"### Auto-generated image{note}\n"
                                    f"Prompt: {auto_prompt}\nModel: {res.get('model')}"
                                ),
                                "at": _now(),
                                "images": list(paths),
                                "agent_name": who,
                            }
                        )
                except ImageGenError as e:
                    hist.append(
                        {
                            "role": "error",
                            "content": f"Auto image generation failed: {e}",
                            "at": _now(),
                        }
                    )

            if exec_skills:
                for sk in extract_skill_requests(reply):
                    used_tool = True
                    if not allow_tool("skill", f"Load skill {sk}", sk):
                        continue
                    if sk.lower() not in allow and not Path(sk).is_file():
                        if not Path(sk).is_file():
                            hist.append(
                                {
                                    "role": "skill",
                                    "content": f"Skill '{sk}' is disabled or unknown. Enable it in Skills manager.",
                                    "at": _now(),
                                }
                            )
                            continue
                    emit(f"Loading skill: {sk}")
                    loaded = load_skill_text(sk)
                    if loaded.get("ok"):
                        name = (loaded.get("name") or "").lower()
                        if name and name not in allow and not Path(sk).is_file():
                            body = f"Skill '{loaded.get('name')}' is disabled."
                        else:
                            body = (
                                f"### Skill loaded: {loaded.get('name')}\n"
                                f"Path: {loaded.get('path')}\n\n"
                                f"**Follow this skill's procedure exactly.**\n\n"
                                f"{loaded.get('text')}"
                            )
                    else:
                        body = f"### Skill load failed: {sk}\n{loaded.get('error')}"
                    hist.append({"role": "skill", "content": body, "at": _now()})
                    _audit_tool("skill", args_summary=str(sk)[:200], result={"ok": True, "preview": str(body)[:200]}, status="ok")

            if exec_mcp:
                for qual, args in extract_mcp_requests(reply):
                    used_tool = True
                    if not allow_tool("mcp", f"MCP {qual}", str(args)):
                        continue
                    emit(f"MCP: {qual}")
                    result = get_mcp_hub().call(qual, args)
                    hist.append(
                        {
                            "role": "mcp",
                            "content": f"### MCP result `{qual}`\n```json\n{result}\n```",
                            "at": _now(),
                        }
                    )
                    _audit_tool(
                        "mcp",
                        args_summary=f"{qual} {args}"[:800],
                        result=result if isinstance(result, dict) else {"preview": str(result)[:400]},
                        status="ok",
                    )

            # In plan mode, log terminal commands for visibility but don't execute them
            terminal_commands = list(extract_terminal_commands(reply))
            if terminal_commands:
                prior_fps = [
                    command_fingerprint(str(m.get("command") or ""))
                    for m in hist
                    if (m.get("role") or "") == "terminal" and command_fingerprint(str(m.get("command") or ""))
                ]
                for cmd in terminal_commands:
                    if exec_terminal:
                        used_tool = True
                        if not allow_tool("terminal", f"TERMINAL: {cmd[:100]}", cmd):
                            continue
                        fp = command_fingerprint(cmd)
                        if fp and prior_fps.count(fp) >= 2:
                            note = (
                                f"[repeat blocked] Already ran `{cmd[:160]}` "
                                f"{prior_fps.count(fp)} times. Do NOT list the same folder again. "
                                "Next: one NEW step toward the live goal "
                                "(launch from App\\ with quoted paths, then <<<WINDOWS>>> to prove the GUI)."
                            )
                            emit("Repeat command blocked", detail=cmd[:80])
                            hist.append(
                                {
                                    "role": "system_note",
                                    "content": note,
                                    "at": _now(),
                                }
                            )
                            continue
                        emit(f"⌨ Terminal", detail=cmd[:120])
                        result = run_command(
                            cmd,
                            cwd=cwd,
                            safety_mode=safety_mode,
                            ask_large_output=ask_large_output,
                            should_stop=_stopped,
                        )
                        if fp:
                            prior_fps.append(fp)
                        errbit = (
                            str(result.get("error") or result.get("stderr") or "")
                            .strip()
                            .splitlines()[0][:100]
                            if not result.get("ok")
                            else ""
                        )
                        if result.get("ok"):
                            emit("Terminal ok", detail=cmd[:80])
                        else:
                            emit(
                                f"Terminal FAIL: {errbit or 'error'}",
                                detail=cmd[:80],
                            )
                        hist.append(
                            {
                                "role": "terminal",
                                "content": format_result_for_llm(result),
                                "at": _now(),
                                "command": result.get("command") or cmd,
                                "exit_code": result.get("exit_code"),
                                "ok": bool(result.get("ok")),
                            }
                        )
                        try:
                            from app.core.services.data import audit_log as _audit

                            _audit.record(
                                "terminal",
                                args_summary=(cmd or "")[:800],
                                result=result,
                                status="ok" if result.get("ok") else "error",
                                chat_id=str(chat_id or ""),
                                source="chat",
                            )
                        except Exception:  # noqa: BLE001
                            pass
                    else:
                        # Plan mode: log for visibility only (not executed)
                        emit(f"⌨ Terminal (plan)", detail=cmd[:120])

            for body in extract_org_commands(reply):
                used_tool = True
                if not allow_tool("org", "ORG update", body):
                    continue
                emit("Updating organisation…")
                result = run_org_command(body)
                hist.append(
                    {
                        "role": "org",
                        "content": f"### Org update\n```json\n{result}\n```",
                        "at": _now(),
                    }
                )
                _audit_tool("org", args_summary=(body or "")[:800], result=result if isinstance(result, dict) else {"preview": str(result)[:400]}, status="ok")

            for body in extract_pip_commands(reply):
                used_tool = True
                if not allow_tool("pip", f"PIP: {body[:80]}", body):
                    continue
                emit("Installing packages…")
                result = run_pip_command(body)
                hist.append(
                    {
                        "role": "pip",
                        "content": f"### Package install\n```json\n{result}\n```",
                        "at": _now(),
                    }
                )
                _audit_tool("pip", args_summary=(body or "")[:800], result=result if isinstance(result, dict) else {"preview": str(result)[:400]}, status="ok")

            if exec_laptop:
                for name in extract_screenshot_blocks(reply):
                    used_tool = True
                    if not allow_tool("screenshot", "SCREENSHOT", name or ""):
                        continue
                    emit("Screenshot…")
                    result = take_screenshot(name or None)
                    shot_path = result.get("path") if isinstance(result, dict) else None
                    staged = stage_media_file(shot_path, chat_id) if shot_path else None
                    if staged:
                        pending_show_images.append(staged)
                    hist.append(
                        {
                            "role": "screenshot",
                            "content": f"### Screenshot\n```json\n{result}\n```\n"
                            + (f"\n<<<IMAGE>>>\n{staged}\n<<<END_IMAGE>>>\n" if staged else ""),
                            "at": _now(),
                            "images": [staged] if staged else [],
                        }
                    )
                for body in extract_gui_blocks(reply):
                    used_tool = True
                    if not allow_tool("gui", f"GUI: {body[:80]}", body):
                        continue
                    emit("GUI actions…")
                    result = run_gui_actions(body)
                    hist.append(
                        {
                            "role": "gui",
                            "content": f"### GUI\n```json\n{result}\n```",
                            "at": _now(),
                        }
                    )
                for body in extract_clipboard_blocks(reply):
                    used_tool = True
                    if not allow_tool("clipboard", "CLIPBOARD", body):
                        continue
                    emit("Clipboard…")
                    result = clipboard_op(body)
                    hist.append(
                        {
                            "role": "clipboard",
                            "content": f"### Clipboard\n```json\n{result}\n```",
                            "at": _now(),
                        }
                    )
                for body in extract_windows_blocks(reply):
                    used_tool = True
                    if not allow_tool("windows", "WINDOWS", body or "list"):
                        continue
                    emit("Windows…")
                    result = windows_op(body or "list")
                    hist.append(
                        {
                            "role": "windows",
                            "content": f"### Windows\n```json\n{result}\n```",
                            "at": _now(),
                        }
                    )
                if "<<<SCREENSHOT>>>" in reply.upper() and not extract_screenshot_blocks(reply):
                    if re_search_empty_screenshot(reply):
                        used_tool = True
                        if allow_tool("screenshot", "SCREENSHOT", ""):
                            emit("Screenshot…")
                            result = take_screenshot(None)
                            shot_path = result.get("path") if isinstance(result, dict) else None
                            staged = stage_media_file(shot_path, chat_id) if shot_path else None
                            if staged:
                                pending_show_images.append(staged)
                            hist.append(
                                {
                                    "role": "screenshot",
                                    "content": f"### Screenshot\n```json\n{result}\n```",
                                    "at": _now(),
                                    "images": [staged] if staged else [],
                                }
                            )

            # Grok-style agent harness (file/grep/subagent/git/bg/todo/plan)
            try:
                if extract_harness_blocks(reply):
                    hres = run_harness_from_reply(
                        reply,
                        cwd=str(cwd),
                        chat_id=chat_id,
                        allow_tool=allow_tool,
                        emit=lambda m: emit(m),
                    )
                    for hr in hres:
                        used_tool = True
                        tool_name = hr.get("tool") or "harness"
                        res = hr.get("result") or {}
                        emit(
                            f"✓ harness {tool_name}",
                            detail=(
                                str(res.get("diff_summary") or "")
                                or ("ok" if res.get("ok") else str(res.get("error") or "")[:80])
                            ),
                        )
                        # Task #8: surface unified diff for file edits (not only raw JSON)
                        body_parts = [f"### {tool_name}"]
                        if res.get("diff_summary"):
                            body_parts.append(str(res.get("diff_summary")))
                        if res.get("path"):
                            body_parts.append(f"Path: {res.get('path')}")
                        if res.get("diff"):
                            from app.core.services.tools.file_diff import format_diff_display

                            body_parts.append(
                                format_diff_display(
                                    str(res.get("diff") or ""),
                                    summary=str(res.get("diff_summary") or "File change"),
                                    path=str(res.get("path") or ""),
                                )
                            )
                        # Compact JSON (trim huge content/diff duplication)
                        slim = {
                            k: v
                            for k, v in res.items()
                            if k not in ("diff",) and not (k == "content" and len(str(v)) > 400)
                        }
                        if res.get("diff"):
                            slim["diff_preview"] = (str(res.get("diff"))[:400] + "…") if len(str(res.get("diff"))) > 400 else res.get("diff")
                        body_parts.append(
                            "```json\n" + json.dumps(slim, ensure_ascii=False)[:8000] + "\n```"
                        )
                        extra: dict[str, Any] = {}
                        if res.get("diff"):
                            extra["file_diff"] = {
                                "path": res.get("path") or "",
                                "diff": res.get("diff") or "",
                                "summary": res.get("diff_summary") or "",
                                "stats": res.get("diff_stats") or {},
                                "tool": tool_name,
                            }
                        hist.append(tool_msg("harness", "\n".join(body_parts), **extra))
            except Exception as e:  # noqa: BLE001
                emit(f"harness error: {e}")
                hist.append(tool_msg("harness", f"### harness error\n{e}"))

            # Unverified success claims (no tool evidence)
            try:
                from app.core.services.tools.claim_verify import verification_note

                # Tool messages appended this round = after assistant message
                # Find tools after last assistant
                tool_tail: list[dict[str, Any]] = []
                for m in reversed(hist):
                    r = (m.get("role") or "").lower()
                    if r == "assistant":
                        break
                    if r not in ("user",):
                        tool_tail.append(m)
                tool_tail.reverse()
                note = verification_note(reply or "", tool_msgs=tool_tail, used_tool=used_tool)
                if note:
                    hist.append(
                        {
                            "role": "system_note",
                            "content": note,
                            "at": _now(),
                            "agent_name": who,
                        }
                    )
                    emit("unverified claim flagged")
            except Exception:  # noqa: BLE001
                pass

            # If tools ran, this assistant was an intermediate tool-round — hide from main chat
            # so the next final answer is the only bubble (tools stay in collapsed tool trace).
            if used_tool:
                for i in range(len(hist) - 1, -1, -1):
                    if hist[i].get("role") == "assistant" and not hist[i].get("_streaming"):
                        hist[i]["_hide_ui"] = True
                        hist[i]["_tool_round"] = True
                        hist[i]["_tool_intent_only"] = True
                        break
                emit("tool round complete — continuing for final answer…")
                if _wait_while_paused(where="after tools"):
                    break

            persist()
            if not used_tool:
                # Nudge even on the last booked pass — 50/50 + "let me check" used to stop cold
                if unfinished_nudges < 3 and _looks_unfinished_work(reply):
                    unfinished_nudges += 1
                    hist.append(
                        {
                            "role": "system_note",
                            "content": (
                                "[continue] That reply was not a finished answer. "
                                "Do not repeat omitted-context placeholders. "
                                "Call a tool now (<<<SEARCH_REPLACE>>> / <<<WRITE_FILE>>> / "
                                "<<<TERMINAL>>> or {\"action\":\"search_replace\",...}) "
                                "or give a short status / blocker. Finish the user's task."
                            ),
                            "at": _now(),
                        }
                    )
                    emit("continuing — model talked about work but called no tool")
                    continue
                break
    finally:
        try:
            agent_hooks.run_hooks("Stop", payload={"chat_id": chat_id, "rounds": rounds})
        except Exception:  # noqa: BLE001
            pass
        _get_tool_budget().end_run(run_id)
        try:
            from app.services.agent_harness import sandbox as _sbx

            _sbx.clear_chat_context()
        except Exception:  # noqa: BLE001
            pass

    # Final pass: ensure last assistant message shows any pending media
    if pending_show_images or pending_show_videos:
        for i in range(len(hist) - 1, -1, -1):
            if hist[i].get("role") == "assistant":
                hist[i] = enrich_message_with_media(
                    hist[i],
                    chat_id=chat_id,
                    extra_images=pending_show_images,
                    extra_videos=pending_show_videos,
                )
                break
        persist()

    # Optionally save agent result into active project outputs
    if cfg.get("auto_save_results_to_project") and last_reply:
        try:
            from app.services import project_outputs, project_store

            pid = project_store.get_active_project_id()
            if pid:
                project_outputs.save_result(
                    last_reply,
                    title="assistant_reply",
                    agent_name=who,
                    project_id=pid,
                    source="chat",
                )
        except Exception:  # noqa: BLE001
            pass

    # Auto-capture durable facts into Memory (does not alter chat history)
    if last_reply:
        try:
            from app.core.services.chat.chat_context import auto_capture_memory_from_reply

            n = auto_capture_memory_from_reply(last_reply, source="chat")
            if n:
                emit(f"memory: auto-saved {n} fact(s)")
        except Exception:  # noqa: BLE001
            pass

    # One clean UI reply: drop sticky-echo + hide intermediate tool-call assistants
    hist = finalize_history_for_display(hist)
    # Prefer last real assistant content as last_reply
    for m in reversed(hist):
        if m.get("role") == "assistant" and not m.get("_hide_ui"):
            last_reply = m.get("content") or last_reply
            break
    persist()

    return hist, last_reply


def re_match_size(s: str) -> bool:
    import re

    return bool(re.match(r"^\d{2,4}x\d{2,4}$", (s or "").strip()))


def re_search_empty_screenshot(text: str) -> bool:
    import re

    return bool(
        re.search(
            r"<<<SCREENSHOT>>>\s*<<<END_SCREENSHOT>>>",
            text or "",
            re.I | re.DOTALL,
        )
    )
