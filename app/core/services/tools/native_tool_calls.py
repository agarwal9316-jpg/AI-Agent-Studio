"""Native OpenAI tool_calls ↔ Studio dual-path (role:tool round-trip).

Adapted conceptually from Open WebUI middleware (tool_calls drain / sanitize pairs),
but reimplemented for Studio's CustomTkinter chat loop + text-block harness.

Path A — <<<BLOCK>>> text tools (always work)
Path B — OpenAI tools schemas → tool_calls → execute → role:tool → continue
Path C — JSON / <tool_call> in content → normalizer → text blocks

When prefer_native is ON and the provider supports tools, Studio sends `tools`
schemas, keeps structured tool_calls on the assistant message, appends
role:tool results with tool_call_id, and continues until a final answer.
Execution still goes through the existing text-block / harness extractors
(conversion is lossless for known tools). Soft-degrade: provider rejects tools
→ llm.py retries text-only.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from app.core.services.data.storage import load_config, save_config

# Config key — default ON (OpenAI-compatible providers support function calling)
PREFER_NATIVE_KEY = "prefer_native_openai_tools"

# Providers known to accept OpenAI-style tools / tool_calls
_NATIVE_TOOL_PROVIDERS = frozenset(
    {
        "openai",
        "openrouter",
        "xai",
        "grok",
        "groq",
        "together",
        "anthropic",  # via OpenAI-compatible gateway if used
        "azure",
        "ollama",  # modern Ollama supports tools
        "nvidia",
        "deepseek",
        "mistral",
        "fireworks",
        "custom",  # optimistic — soft-degrade on reject
    }
)

# Map OpenAI function name → Studio hist roles typically produced
_FN_TO_HIST_ROLES: dict[str, tuple[str, ...]] = {
    "run_terminal": ("terminal",),
    "terminal": ("terminal",),
    "execute_command": ("terminal",),
    "shell": ("terminal",),
    "web_search": ("web_search", "search"),
    "search": ("web_search", "search"),
    "web_fetch": ("web_fetch",),
    "deep_research": ("deep_research",),
    "browser": ("browser",),
    "open_url": ("browser",),
    "image_gen": ("image_gen", "image"),
    "generate_image": ("image_gen", "image"),
    "screenshot": ("screenshot",),
    "gui": ("gui",),
    "clipboard": ("clipboard",),
    "windows": ("windows",),
    "skill": ("skill",),
    "mcp": ("mcp",),
    "openapi": ("openapi", "mcp"),
    "pip_install": ("pip",),
    "knowledge": ("knowledge",),
    "ocr": ("ocr",),
    "read_file": ("harness",),
    "write_file": ("harness",),
    "search_replace": ("harness",),
    "list_dir": ("harness",),
    "grep": ("harness",),
    "git_status": ("harness",),
    "git_diff": ("harness",),
    "git_commit": ("harness",),
    "spawn_subagent": ("harness",),
    "bg_shell": ("harness",),
    "todo_write": ("harness",),
    "plan_write": ("harness",),
    "ask_user": ("harness",),
    "backup": ("org",),
    "rollback": ("org",),
    "org_command": ("org",),
    "patch_review": ("patch",),
    "self_improve": ("self_improve",),
}

_TOOLISH_ROLES = frozenset(
    {
        "terminal",
        "tool",
        "skill",
        "mcp",
        "openapi",
        "gui",
        "clipboard",
        "windows",
        "org",
        "pip",
        "browser",
        "web_search",
        "search",
        "ocr",
        "self_improve",
        "harness",
        "screenshot",
        "org_agent",
        "web_fetch",
        "deep_research",
        "crawl",
        "scrape",
        "download",
        "knowledge",
        "image_gen",
        "image",
        "patch",
    }
)


def prefer_native_openai_tools(cfg: dict[str, Any] | None = None) -> bool:
    """Settings toggle: Prefer native OpenAI tool calls (default ON)."""
    try:
        c = cfg if isinstance(cfg, dict) else load_config()
        if PREFER_NATIVE_KEY not in c:
            return True
        return bool(c.get(PREFER_NATIVE_KEY))
    except Exception:  # noqa: BLE001
        return True


def set_prefer_native_openai_tools(on: bool) -> None:
    cfg = load_config()
    cfg[PREFER_NATIVE_KEY] = bool(on)
    save_config(cfg)


def provider_supports_native_tools(
    provider_id: str = "",
    *,
    base_url: str = "",
    model: str = "",
) -> bool:
    """Heuristic: does this provider likely accept OpenAI `tools`?"""
    pid = (provider_id or "").lower().strip()
    base = (base_url or "").lower()
    _ = model  # reserved for future model-level denylist
    if pid in _NATIVE_TOOL_PROVIDERS:
        return True
    for hint in (
        "openai.com",
        "openrouter.ai",
        "api.x.ai",
        "groq.com",
        "together.xyz",
        "anthropic.com",
        "deepseek.com",
        "mistral.ai",
        "fireworks.ai",
        "nvidia.com",
        "11434",  # local ollama
    ):
        if hint in base:
            return True
    # Unknown custom OpenAI-compatible endpoint — try (soft-degrade on reject)
    return True


def should_send_native_tools(
    *,
    mode: str = "action",
    cfg: dict[str, Any] | None = None,
    provider_id: str = "",
    base_url: str = "",
    model: str = "",
) -> bool:
    """Whether Action mode should attach OpenAI tools schemas this turn."""
    if (mode or "").lower() != "action":
        return False
    if not prefer_native_openai_tools(cfg):
        return False
    return provider_supports_native_tools(provider_id, base_url=base_url, model=model)


def ensure_tool_call_ids(tool_calls: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Normalize OpenAI tool_calls: ensure id/type/function shape."""
    out: list[dict[str, Any]] = []
    if not tool_calls:
        return out
    for i, tc in enumerate(tool_calls):
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
        name = str(fn.get("name") or "").strip()
        if not name:
            continue
        args = fn.get("arguments")
        if isinstance(args, (dict, list)):
            args_str = json.dumps(args, ensure_ascii=False)
        else:
            args_str = str(args if args is not None else "")
        tid = str(tc.get("id") or "").strip() or f"call_{uuid.uuid4().hex[:24]}"
        out.append(
            {
                "id": tid,
                "type": str(tc.get("type") or "function"),
                "index": int(tc.get("index") if tc.get("index") is not None else i),
                "function": {"name": name, "arguments": args_str},
            }
        )
    return out


def tool_calls_to_text_blocks(tool_calls: list[dict[str, Any]] | None) -> str:
    """Convert native tool_calls → <<<BLOCK>>> form for harness execution."""
    if not tool_calls:
        return ""
    try:
        from app.core.services.llm.llm import _convert_tool_calls_to_text_blocks

        return _convert_tool_calls_to_text_blocks(ensure_tool_call_ids(tool_calls)) or ""
    except Exception:  # noqa: BLE001
        return ""


def make_tool_result_message(
    *,
    tool_call_id: str,
    name: str,
    content: str,
    at: str = "",
    agent_name: str = "",
    **extra: Any,
) -> dict[str, Any]:
    """OpenAI-compatible role:tool message for the next LLM turn."""
    m: dict[str, Any] = {
        "role": "tool",
        "tool_call_id": str(tool_call_id or ""),
        "name": str(name or ""),
        "content": str(content or ""),
        "_native_tool_result": True,
    }
    if at:
        m["at"] = at
    if agent_name:
        m["agent_name"] = agent_name
    m.update(extra)
    return m


def _toolish_after_assistant(
    hist: list[dict[str, Any]],
    asst_index: int,
) -> list[dict[str, Any]]:
    """Collect Studio tool-role messages after an assistant (UI path)."""
    out: list[dict[str, Any]] = []
    for m in hist[asst_index + 1 :]:
        role = str(m.get("role") or "").lower()
        if role == "assistant":
            break
        if role == "user":
            break
        if m.get("_native_tool_result"):
            continue  # already a native result
        if role in _TOOLISH_ROLES or (
            role
            and role
            not in (
                "thinking",
                "system",
                "system_note",
                "error",
                "attachment",
            )
        ):
            out.append(m)
    return out


def append_native_tool_results(
    hist: list[dict[str, Any]],
    *,
    asst_index: int,
    tool_calls: list[dict[str, Any]] | None,
    at: str = "",
    agent_name: str = "",
) -> list[dict[str, Any]]:
    """
    After text-block execution, append role:tool messages paired to tool_calls.

    Matching: prefer hist role mapped from function name; else assign in order.
    Marks paired UI messages with `_native_paired` so build_api_messages can skip
    re-injecting them as fake user turns.
    Returns the new role:tool messages appended.
    """
    tcs = ensure_tool_call_ids(tool_calls)
    if not tcs or asst_index < 0 or asst_index >= len(hist):
        return []

    ui_tools = _toolish_after_assistant(hist, asst_index)
    used: set[int] = set()
    appended: list[dict[str, Any]] = []

    for tc in tcs:
        fn = str((tc.get("function") or {}).get("name") or "")
        preferred = _FN_TO_HIST_ROLES.get(fn.lower(), ())
        pick_i = -1
        for i, um in enumerate(ui_tools):
            if i in used:
                continue
            role = str(um.get("role") or "").lower()
            if preferred and role in preferred:
                pick_i = i
                break
        if pick_i < 0:
            for i, _um in enumerate(ui_tools):
                if i not in used:
                    pick_i = i
                    break
        if pick_i >= 0:
            used.add(pick_i)
            um = ui_tools[pick_i]
            content = str(um.get("content") or "")
            um["_native_paired"] = True
            um["_paired_tool_call_id"] = tc["id"]
        else:
            content = f'Error: no Studio result for tool "{fn}"'

        msg = make_tool_result_message(
            tool_call_id=tc["id"],
            name=fn,
            content=content[:50000],
            at=at,
            agent_name=agent_name,
        )
        hist.append(msg)
        appended.append(msg)

    # Mark assistant as native tool round (keep for API even if hidden in UI)
    asst = hist[asst_index]
    if isinstance(asst, dict):
        asst["tool_calls"] = tcs
        asst["_native_tools"] = True

    return appended


def sanitize_native_tool_pairs(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Drop orphan tool_calls / role:tool messages so the provider never sees
    incomplete pairs (adapted from Open WebUI sanitize_tool_pairs).
    """
    tool_result_ids = {
        m.get("tool_call_id")
        for m in messages
        if m.get("role") == "tool" and m.get("tool_call_id")
    }
    tool_call_ids = {
        tc.get("id")
        for m in messages
        for tc in (m.get("tool_calls") or [])
        if m.get("role") == "assistant" and isinstance(tc, dict) and tc.get("id")
    }

    sanitized: list[dict[str, Any]] = []
    for message in messages:
        if message.get("role") == "assistant" and message.get("tool_calls"):
            kept = [
                tc
                for tc in (message.get("tool_calls") or [])
                if isinstance(tc, dict) and tc.get("id") in tool_result_ids
            ]
            if kept:
                sanitized.append({**message, "tool_calls": kept})
            else:
                clean = dict(message)
                clean.pop("tool_calls", None)
                if clean.get("content"):
                    sanitized.append(clean)
        elif message.get("role") != "tool" or message.get("tool_call_id") in tool_call_ids:
            sanitized.append(message)
    return sanitized


def api_message_from_history_item(m: dict[str, Any]) -> dict[str, Any] | None:
    """
    Convert one Studio hist message to an OpenAI API message when it participates
    in the native tool path. Returns None if the caller should use the legacy path.
    """
    role = str(m.get("role") or "").lower()

    if role == "assistant" and m.get("tool_calls"):
        tcs = ensure_tool_call_ids(list(m.get("tool_calls") or []))
        if not tcs:
            return None
        # Prefer prose-only content for API when we also have structured calls
        content = m.get("content")
        if content is None:
            content = ""
        # Strip huge converted blocks if marked; keep short status text
        text = str(content)
        return {
            "role": "assistant",
            "content": text if text.strip() else None,
            "tool_calls": tcs,
        }

    if role == "tool" and m.get("tool_call_id") and (
        m.get("_native_tool_result") or m.get("name") is not None
    ):
        out: dict[str, Any] = {
            "role": "tool",
            "tool_call_id": str(m.get("tool_call_id")),
            "content": str(m.get("content") or ""),
        }
        name = str(m.get("name") or "").strip()
        if name:
            out["name"] = name
        return out

    return None


def dual_path_native_hint() -> str:
    """Extra system-prompt note when native path is preferred."""
    return """
## Native OpenAI tool calls (preferred when available)
The API may return structured `tool_calls`. Studio executes them and replies with
`role:tool` results (tool_call_id). You may also emit <<<BLOCK>>> text tools —
both paths work. Prefer native function calls when the tools schemas are present;
fall back to text blocks if unsure.
""".strip()
