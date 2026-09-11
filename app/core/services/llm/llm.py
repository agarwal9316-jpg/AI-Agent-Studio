"""OpenAI-compatible chat completions via stdlib (no extra deps). Supports streaming."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any, Callable

from app.core.services.llm.model_params import build_api_body_extras, trim_messages_to_context


class LLMError(Exception):
    """Raised when the LLM call fails."""


# Cloudflare / gateway codes that often succeed on one automatic retry
_TRANSIENT_HTTP = frozenset({408, 425, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524})


def _strip_html_noise(text: str) -> str:
    """Remove HTML/script so Cloudflare error pages never land in chat bubbles."""
    t = text or ""
    if "<" not in t:
        return t.strip()
    t = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", t)
    t = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", t)
    t = re.sub(r"(?is)<!--.*?-->", " ", t)
    t = re.sub(r"(?is)<[^>]+>", " ", t)
    t = re.sub(r"&nbsp;|&amp;|&lt;|&gt;|&quot;", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def format_llm_http_error(code: int, body: str = "") -> str:
    """Human-readable HTTP error (no HTML dump). Used for chat bubbles + status."""
    raw = (body or "")[:4000]
    cleaned = _strip_html_noise(raw)
    # Drop classic Cloudflare chrome leftovers
    for junk in (
        "DOCTYPE html",
        "no-js ie6",
        "oldie",
        "Attention Required",
        "cloudflare",
        "cf-error",
        "Enable JavaScript",
    ):
        if junk.lower() in cleaned.lower() and len(cleaned) < 80:
            cleaned = ""
            break
    if cleaned and (
        "DOCTYPE" in cleaned.upper()
        or cleaned.lower().startswith("html")
        or "ie6 oldie" in cleaned.lower()
    ):
        cleaned = ""

    friendly = {
        524: (
            "The AI provider timed out (HTTP 524 — Cloudflare).\n\n"
            "The model took too long to answer (common after long tool use or a busy model). "
            "Studio already retries once automatically.\n\n"
            "What to try: send again in a few seconds · pick a faster model · "
            "or shorter questions after tool runs."
        ),
        502: (
            "The AI provider gateway is temporarily unavailable (HTTP 502).\n\n"
            "Wait a few seconds and try again."
        ),
        503: (
            "The AI provider is overloaded (HTTP 503).\n\n"
            "Wait a moment and send again, or switch model/provider."
        ),
        504: (
            "The AI provider gateway timed out (HTTP 504).\n\n"
            "Try again, or use a smaller/faster model."
        ),
        520: "The AI provider returned an unknown gateway error (520). Try again shortly.",
        521: "The AI provider origin is down (521). Try again later or another provider.",
        522: "The AI provider connection timed out (522). Check network and retry.",
        523: "The AI provider origin is unreachable (523). Try again later.",
        429: (
            "Rate limited (HTTP 429).\n\n"
            "Wait a bit, or switch model / API key / provider in Settings."
        ),
        402: (
            "Payment / credits required (HTTP 402).\n\n"
            "If you are on OpenRouter: add credits at openrouter.ai/settings/credits,\n"
            "or switch to direct Grok — Home → ✦ Use Grok as my AI and paste an xAI key\n"
            "from https://console.x.ai (no OpenRouter needed)."
        ),
        401: "API key rejected (HTTP 401). Open Settings → Providers and check your key.",
        403: "Access denied (HTTP 403). Check API key permissions and model access.",
        400: "Bad request (HTTP 400). The model or message format may be unsupported.",
        404: "Not found (HTTP 404). Check the model name and API base URL.",
        408: "Request timed out (HTTP 408). Try again with a shorter prompt or faster model.",
    }
    # OpenRouter free/low balance often rejects large Action-mode system prompts
    # ("Prompt tokens limit exceeded: 16898 > 3655") — not a dead API key.
    clow = cleaned.lower()
    if int(code or 0) == 402 and (
        "prompt tokens limit" in clow
        or "prompt token" in clow
        or "tokens limit exceeded" in clow
    ):
        # Prefer the numbers from the provider when present
        mlim = re.search(
            r"prompt tokens limit exceeded:\s*(\d+)\s*>\s*(\d+)",
            cleaned,
            re.I,
        )
        sizes = ""
        if mlim:
            sizes = f" (this request ~{mlim.group(1)} tokens, your limit ~{mlim.group(2)})"
        return (
            f"Prompt too large for your OpenRouter plan{sizes}.\n\n"
            "Action mode ships a big tool manual (~15k+ tokens). Free/low-credit "
            "OpenRouter accounts only allow a few thousand prompt tokens, so even "
            "a short “hi” can fail before the model answers.\n\n"
            "What to try:\n"
            "• Studio auto-retries once with a compact prompt — send again if needed\n"
            "• Add credits: https://openrouter.ai/settings/credits\n"
            "• Or switch to direct Grok: Home → ✦ Use Grok as my AI (console.x.ai key)\n"
            "• Or turn off some tool switches (Terminal / Skills / MCP / Laptop) for light chat"
        )

    base = friendly.get(int(code) if code else 0)
    if base:
        if cleaned and len(cleaned) > 12:
            return f"{base}\n\n(Detail: {cleaned[:160]})"
        return base
    if cleaned:
        return f"HTTP {code}: {cleaned[:220]}"
    return f"HTTP {code}: request failed"


def is_prompt_token_limit_error(err: str | BaseException) -> bool:
    """True when provider rejected the request for oversized prompt (OpenRouter 402)."""
    text = str(err or "").lower()
    if not text:
        return False
    if "prompt too large for your openrouter plan" in text:
        return True
    if "prompt tokens limit" in text or "tokens limit exceeded" in text:
        return True
    if "402" in text and "prompt token" in text:
        return True
    return False


def _apply_safe_max_tokens(
    body: dict[str, Any],
    *,
    base_url: str,
    max_tokens: int | None = None,
) -> None:
    """
    OpenRouter bills against max_tokens. Unset max on some Grok models defaults to
    65k completion → HTTP 402 for low balances. Cap sensibly.
    """
    if max_tokens is not None and max_tokens > 0:
        body["max_tokens"] = int(max_tokens)
        return
    if "max_tokens" in body and int(body.get("max_tokens") or 0) > 0:
        # Cap absurd values from config/model_limits
        if int(body["max_tokens"]) > 8192:
            body["max_tokens"] = 8192
        return
    base = (base_url or "").lower()
    if "openrouter.ai" in base:
        # OpenRouter reserves credits for max_tokens up-front. Keep low so
        # nearly-empty balances still work (user can raise in Settings).
        body["max_tokens"] = 512
    elif "api.x.ai" in base:
        body["max_tokens"] = 2048


def format_llm_error_message(err: str | BaseException) -> str:
    """Normalize any LLMError / raw string for UI (strips HTML, maps 524, etc.)."""
    text = str(err or "").strip()
    if not text:
        return "Something went wrong talking to the AI. Please try again."
    # Already friendly?
    if "timed out (HTTP 524" in text or "provider timed out" in text.lower():
        return text if "<" not in text else _strip_html_noise(text)
    m = re.search(r"HTTP\s+(\d{3})\s*:\s*(.*)", text, re.I | re.S)
    if m:
        code = int(m.group(1))
        body = m.group(2) or ""
        return format_llm_http_error(code, body)
    if "<html" in text.lower() or "<!doctype" in text.lower():
        cleaned = _strip_html_noise(text)
        if re.search(r"\b524\b", text):
            return format_llm_http_error(524, cleaned)
        return cleaned[:300] or "The AI provider returned an error page. Please try again."
    # Cap huge dumps
    if len(text) > 500:
        return text[:480] + "…"
    return text


def _headers(api_key: str, base_url: str) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {(api_key or '').strip()}",
    }
    if "openrouter.ai" in (base_url or ""):
        headers["HTTP-Referer"] = "https://ai-agent-studio.local"
        headers["X-Title"] = "AI Agent Studio"
    return headers


# ---------------------------------------------------------------------------
# JSON tool_calls → text blocks converter
# ---------------------------------------------------------------------------

"""
Maps OpenAI-style tool_call function names to (block_name, key_map) tuples.
  block_name  — the <<<TOOL_NAME>>> / <<<END_TOOLNAME>>> wrapper
  key_map     — dict mapping JSON arg keys to text-block key labels
"""
_TOOL_NAME_MAP = {
    # Terminal / shell
    "run_terminal": ("TERMINAL", {"command": ""}),
    "terminal": ("TERMINAL", {"command": ""}),
    "execute_command": ("TERMINAL", {"command": ""}),
    "shell": ("TERMINAL", {"command": ""}),
    # Search
    "web_search": ("WEB_SEARCH", {"query": "", "q": ""}),
    "search": ("WEB_SEARCH", {"query": "", "q": ""}),
    "bing_search": ("WEB_SEARCH", {"query": "", "q": ""}),
    "brave_search": ("WEB_SEARCH", {"query": "", "q": ""}),
    # File operations (harness)
    "read_file": ("READ_FILE", {"path": "path", "offset": "offset", "limit": "limit"}),
    "write_file": ("WRITE_FILE", {"path": "path", "content": "content"}),
    "search_replace": ("SEARCH_REPLACE", {
        "path": "path", "old_string": "old", "new_string": "new",
        "replace_all": "replace_all",
    }),
    "list_dir": ("LIST_DIR", {"path": "path"}),
    "grep": ("GREP", {"pattern": "pattern", "path": "path", "glob": "glob"}),
    # Git (harness)
    "git_status": ("GIT_STATUS", {}),
    "git_diff": ("GIT_DIFF", {"staged": "staged"}),
    "git_commit": ("GIT_COMMIT", {"message": "message"}),
    # Browser
    "browser": ("BROWSER", {"action": "action", "url": "url"}),
    "open_url": ("BROWSER", {"action": "action", "url": "url"}),
    # Image generation
    "image_gen": ("IMAGE_GEN", {"size": "", "prompt": ""}),
    "generate_image": ("IMAGE_GEN", {"size": "", "prompt": ""}),
    "dall_e_3": ("IMAGE_GEN", {"size": "", "prompt": ""}),
    # MCP
    "mcp": ("MCP", {"server": "server", "tool_name": "tool_name", "arguments": "arguments"}),
    # Screenshot / GUI / Clipboard
    "screenshot": ("SCREENSHOT", {"name": ""}),
    "gui": ("GUI", {"actions": ""}),
    "clipboard": ("CLIPBOARD", {"action": ""}),
    "windows": ("WINDOWS", {"action": ""}),
    # Knowledge / RAG
    "knowledge": ("KNOWLEDGE", {"action": "action", "query": "query"}),
    # OCR
    "ocr": ("OCR", {"image_path": ""}),
    # Skills
    "skill": ("SKILL", {"name": ""}),
    # Web fetch
    "web_fetch": ("WEB_FETCH", {"url": "url"}),
    # Deep research
    "deep_research": ("DEEP_RESEARCH", {"query": "query"}),
    # Patch review
    "patch_review": ("PATCH_REVIEW", {"path": "path", "mode": "mode", "note": "note"}),
    # Self-improve
    "self_improve": ("SELF_IMPROVE", {"path": "path", "mode": "mode", "note": "note"}),
    # Backup / rollback
    "backup": ("BACKUP", {"reason": ""}),
    "rollback": ("ROLLBACK", {"backup_id": ""}),
    # Org commands
    "org_command": ("ORG_COMMAND", {}),
    # Pip install
    "pip_install": ("PIP_INSTALL", {"packages": ""}),
}

# Additional known block names that are NOT in _TOOL_NAME_MAP (for fallback)
_KNOWN_BLOCKS = {
    "TERMINAL", "WEB_SEARCH", "READ_FILE", "WRITE_FILE", "SEARCH_REPLACE",
    "LIST_DIR", "GREP", "GIT_STATUS", "GIT_DIFF", "GIT_COMMIT",
    "BROWSER", "IMAGE_GEN", "MCP", "SCREENSHOT", "GUI", "CLIPBOARD",
    "WINDOWS", "KNOWLEDGE", "OCR", "SKILL", "WEB_FETCH", "DEEP_RESEARCH",
    "CRAWL", "SCRAPE", "DOWNLOAD", "PATCH_REVIEW", "SELF_IMPROVE",
    "BACKUP", "ROLLBACK", "IMAGE", "VIDEO", "ORG_COMMAND", "PIP_INSTALL",
    "AGENTS", "TODO_WRITE", "PLAN_WRITE", "ENTER_PLAN", "EXIT_PLAN",
    "SPAWN_SUBAGENT", "GET_SUBAGENT", "PARALLEL_AGENTS", "BG_SHELL", "BG_STATUS", "BG_KILL",
    "ASK_USER", "PROJECT_RULES", "SANDBOX_STATUS", "PERMISSION_STATUS",
}


def _json_to_text_block(func_name: str, arguments_str: str) -> str | None:
    """
    Convert a single OpenAI tool_call (func_name + JSON args) to text block format.
    Returns the text block string, or None if conversion failed.
    """
    # 1) Look up known mapping
    entry = _TOOL_NAME_MAP.get(func_name.lower())
    if entry:
        block_name, key_map = entry
        try:
            args = json.loads(arguments_str)
        except (json.JSONDecodeError, TypeError):
            args = {}

        return _build_text_block(block_name, args, key_map)

    # 2) Fallback: heuristic — try to guess block name from function name
    fn_upper = func_name.upper().replace(" ", "_").replace("-", "_")
    if fn_upper in _KNOWN_BLOCKS:
        try:
            args = json.loads(arguments_str)
        except (json.JSONDecodeError, TypeError):
            args = {}
        # Heuristic key map: use JSON keys directly as text-block keys
        return _build_text_block(fn_upper, args, {k: k for k in args})

    # 3) Last resort: emit raw JSON inside a generic block
    return f"<<<RAW_TOOL>>>\ntool: {func_name}\nargs: {arguments_str[:500]}\n<<<END_RAW_TOOL>>>"


def _build_text_block(block_name: str, args: dict[str, Any], key_map: dict[str, str]) -> str:
    """
    Build a text block string from parsed JSON args.

    key_map maps:  JSON_key → text-block_key_label
    If text-block label is empty string, use the JSON key as-is (lowercased).

    TERMINAL / WEB_SEARCH special-case: emit raw body (no key prefix) so
    extract_terminal_commands / extract_search_blocks run the real command/query.
    """
    # TERMINAL: prefer raw command string
    if block_name == "TERMINAL":
        for k in ("command", "cmd", "text", "shell"):
            if k in args and str(args[k]).strip():
                return f"<<<TERMINAL>>>\n{str(args[k]).strip()}\n<<<END_TERMINAL>>>"
        # Single arbitrary value
        if len(args) == 1:
            only = next(iter(args.values()))
            if str(only).strip():
                return f"<<<TERMINAL>>>\n{str(only).strip()}\n<<<END_TERMINAL>>>"

    # WEB_SEARCH: raw query when only query-like keys present
    if block_name == "WEB_SEARCH":
        for k in ("query", "q", "search"):
            if k in args and str(args[k]).strip() and len(args) <= 2:
                # allow query + max
                q = str(args[k]).strip()
                extra = []
                for ek in ("max", "limit", "fetch", "deep"):
                    if ek in args:
                        extra.append(f"{ek}: {args[ek]}")
                body = q if not extra else q + "\n" + "\n".join(extra)
                return f"<<<WEB_SEARCH>>>\n{body}\n<<<END_WEB_SEARCH>>>"

    lines: list[str] = []
    for json_key, value in args.items():
        # Find corresponding text-block key from key_map
        tb_key = key_map.get(json_key)
        if tb_key is None or tb_key == "":
            # Use the JSON key itself (lowercased) as the label
            tb_key = json_key.lower()

        # Format value
        if isinstance(value, (dict, list)):
            formatted_value = json.dumps(value, ensure_ascii=False)
        else:
            formatted_value = str(value)

        lines.append(f"{tb_key}: {formatted_value}")

    body = "\n".join(lines).strip()
    return f"<<<{block_name}>>>\n{body}\n<<<END_{block_name}>>>"


def _convert_tool_calls_to_text_blocks(tool_calls: list[dict[str, Any]]) -> str:
    """
    Convert a list of OpenAI-style tool_calls into text block format.
    Returns concatenated text blocks that will be injected into the reply.
    """
    parts: list[str] = []
    for tc in tool_calls:
        func = (tc.get("function") or {}).get("name", "")
        args_str = (tc.get("function") or {}).get("arguments", "") or ""
        block = _json_to_text_block(func, args_str)
        if block:
            parts.append(block)

    # Add a note for any tool_calls that couldn't be converted
    unconverted = []
    for tc in tool_calls:
        func = (tc.get("function") or {}).get("name", "")
        args_str = (tc.get("function") or {}).get("arguments", "") or ""
        block = _json_to_text_block(func, args_str)
        if not block:
            unconverted.append(f"*(unconvertible tool_call: {func})*")

    return "\n\n".join(parts) + ("\n\n" + "\n\n".join(unconverted) if unconverted else "")


def ensure_executable_tool_format(
    content: str,
    tool_calls: list[dict[str, Any]] | None = None,
) -> str:
    """
    Dual-path merge: native API tool_calls + any JSON/XML in content → text blocks.

    Called at the end of every chat_completion(_stream) so all callers
    (chat, subagent, orchestrator) get executable format without extra wiring.
    """
    text = (content or "").strip()
    if tool_calls and isinstance(tool_calls, list):
        converted = _convert_tool_calls_to_text_blocks(tool_calls)
        if converted:
            text = (text + "\n\n" if text else "") + converted
    try:
        from app.core.services.tools.tool_normalizer import normalize_tool_calls

        text = normalize_tool_calls(text) or text
    except Exception:  # noqa: BLE001
        pass
    return text


def _tools_rejected(detail: str) -> bool:
    """Heuristic: provider rejected the tools / tool_choice fields."""
    d = (detail or "").lower()
    keys = (
        "tool",
        "function",
        "tools is not supported",
        "tool_choice",
        "does not support",
        "unknown field",
        "unexpected keyword",
        "invalid parameter",
        "extra inputs are not permitted",
    )
    return any(k in d for k in keys)


# ---------------------------------------------------------------------------
# Message content extraction (Qwen / local / multi-part)
# ---------------------------------------------------------------------------

def _extract_assistant_text(message: dict[str, Any] | None) -> str:
    """Pull visible assistant text from varied provider message shapes."""
    if not isinstance(message, dict):
        return ""
    raw = message.get("content")
    if raw is None:
        raw = ""
    # OpenAI multi-part: [{"type":"text","text":"..."}]
    if isinstance(raw, list):
        parts: list[str] = []
        for p in raw:
            if isinstance(p, str):
                parts.append(p)
            elif isinstance(p, dict):
                t = p.get("text") or p.get("content") or ""
                if isinstance(t, str) and t.strip():
                    parts.append(t)
        return "\n".join(parts).strip()
    return str(raw or "").strip()


def _extract_reasoning_fallback(message: dict[str, Any] | None) -> str:
    """
    Some models (Qwen3, uncensored local builds) spend the token budget on
    reasoning and leave content empty. Recover usable text from common fields.
    """
    if not isinstance(message, dict):
        return ""
    for key in (
        "reasoning_content",
        "reasoning",
        "thinking",
        "model_extra",
    ):
        val = message.get(key)
        if isinstance(val, dict):
            val = val.get("content") or val.get("text") or ""
        text = str(val or "").strip()
        if text:
            # Prefer last non-empty paragraph as the "answer"
            paras = [p.strip() for p in text.split("\n\n") if p.strip()]
            if paras:
                # If very long reasoning, keep last ~2 paragraphs
                return "\n\n".join(paras[-2:])[:8000]
    return ""


# ---------------------------------------------------------------------------
# Main API functions
# ---------------------------------------------------------------------------

def chat_completion(
    *,
    api_key: str,
    messages: list[dict[str, str]],
    model: str = "gpt-4o-mini",
    base_url: str = "https://api.openai.com/v1",
    timeout: float = 60.0,
    return_usage: bool = False,
    temperature: float | None = None,
    max_tokens: int | None = None,
    chat_id: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    normalize_tools: bool = True,
    _tools_retry: bool = True,
    _transient_retry: bool = True,
) -> str | tuple[str, dict[str, int]]:
    """Call POST {base_url}/chat/completions. Returns assistant content (or content+usage).

    Dual path:
      - Optional OpenAI `tools` / `tool_calls` → converted to text blocks
      - JSON / <tool_call> in content → normalized to text blocks
    If the provider rejects `tools`, retries once without them (text-only path).
    Transient gateway errors (524/502/503/…) retry once automatically.
    """
    key = (api_key or "").strip()
    if not key:
        raise LLMError("No API key configured. Open Settings / Providers and add a key.")

    url = base_url.rstrip("/") + "/chat/completions"
    msgs = trim_messages_to_context(messages, chat_id=chat_id)
    body: dict[str, Any] = {
        "model": model,
        "messages": msgs,
    }
    body.update(build_api_body_extras())
    if temperature is not None:
        body["temperature"] = temperature
    _apply_safe_max_tokens(body, base_url=base_url, max_tokens=max_tokens)
    if tools:
        body["tools"] = tools
        body["tool_choice"] = tool_choice if tool_choice is not None else "auto"

    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers=_headers(key, base_url),
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:2000]
        # Provider doesn't support tools → retry text-only (still normalizes content JSON)
        if tools and _tools_retry and e.code in (400, 404, 422) and _tools_rejected(detail):
            return chat_completion(
                api_key=key,
                messages=messages,
                model=model,
                base_url=base_url,
                timeout=timeout,
                return_usage=return_usage,
                temperature=temperature,
                max_tokens=max_tokens,
                chat_id=chat_id,
                tools=None,
                tool_choice=None,
                normalize_tools=normalize_tools,
                _tools_retry=False,
                _transient_retry=_transient_retry,
            )
        # Cloudflare 524 / gateway blips — one automatic retry
        if _transient_retry and int(e.code) in _TRANSIENT_HTTP:
            import time

            time.sleep(1.6 if int(e.code) in (524, 504, 408) else 1.0)
            return chat_completion(
                api_key=key,
                messages=messages,
                model=model,
                base_url=base_url,
                timeout=timeout,
                return_usage=return_usage,
                temperature=temperature,
                max_tokens=max_tokens,
                chat_id=chat_id,
                tools=tools,
                tool_choice=tool_choice,
                normalize_tools=normalize_tools,
                _tools_retry=_tools_retry,
                _transient_retry=False,
            )
        raise LLMError(format_llm_http_error(int(e.code), detail)) from e
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", None) or str(e)
        rlow = str(reason).lower()
        # socket.timeout often arrives as URLError(reason=timeout(...))
        if "timed out" in rlow or "timeout" in rlow:
            if _transient_retry:
                import time

                time.sleep(1.5)
                # Bump timeout on retry for long org-design completions
                return chat_completion(
                    api_key=key,
                    messages=messages,
                    model=model,
                    base_url=base_url,
                    timeout=max(float(timeout) * 1.5, float(timeout) + 60.0),
                    return_usage=return_usage,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    chat_id=chat_id,
                    tools=tools,
                    tool_choice=tool_choice,
                    normalize_tools=normalize_tools,
                    _tools_retry=_tools_retry,
                    _transient_retry=False,
                )
            raise LLMError(
                f"Request timed out after {timeout:.0f}s contacting {base_url.rstrip('/')}. "
                "Try a faster model, smaller seat count, or check the network."
            ) from e
        raise LLMError(f"Network error: {reason}") from e
    except TimeoutError as e:
        if _transient_retry:
            import time

            time.sleep(1.2)
            return chat_completion(
                api_key=key,
                messages=messages,
                model=model,
                base_url=base_url,
                timeout=max(float(timeout) * 1.5, float(timeout) + 60.0),
                return_usage=return_usage,
                temperature=temperature,
                max_tokens=max_tokens,
                chat_id=chat_id,
                tools=tools,
                tool_choice=tool_choice,
                normalize_tools=normalize_tools,
                _tools_retry=_tools_retry,
                _transient_retry=False,
            )
        base_l = (base_url or "").lower()
        model_l = (model or "").lower()
        hint = ""
        if "nvidia.com" in base_l and "deepseek" in model_l:
            hint = (
                "\n\nNVIDIA NIM often queues/hangs on deepseek-v4-flash. "
                "Try OpenRouter model `deepseek/deepseek-v4-flash-0731`, "
                "or NVIDIA `meta/llama-3.1-8b-instruct` (usually responds in <2s)."
            )
        elif "nvidia.com" in base_l:
            hint = (
                "\n\nNVIDIA endpoint accepted the connection but did not finish the reply. "
                "Switch model in Chat, or retry. `meta/llama-3.1-8b-instruct` is a reliable fallback."
            )
        raise LLMError(
            f"Request timed out after {timeout:.0f}s contacting the model API.{hint}"
        ) from e

    try:
        message = payload["choices"][0]["message"]
        content = _extract_assistant_text(message)
        tool_calls = message.get("tool_calls")
        if normalize_tools:
            content = ensure_executable_tool_format(
                content,
                tool_calls if isinstance(tool_calls, list) else None,
            )
        elif tool_calls and isinstance(tool_calls, list):
            converted = _convert_tool_calls_to_text_blocks(tool_calls)
            if converted:
                content = (content + "\n\n" if content else "") + converted
        # Last resort: some local/Qwen builds put the only text in reasoning
        if not (content or "").strip():
            content = _extract_reasoning_fallback(message)
    except (KeyError, IndexError, TypeError) as e:
        raise LLMError(f"Unexpected API response: {payload!r}"[:400]) from e

    usage = payload.get("usage") or {}
    usage_out = {
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
        "total_tokens": int(usage.get("total_tokens") or 0),
    }
    if return_usage:
        return content, usage_out
    return content


def chat_completion_stream(
    *,
    api_key: str,
    messages: list[dict[str, str]],
    model: str = "gpt-4o-mini",
    base_url: str = "https://api.openai.com/v1",
    timeout: float = 180.0,
    on_delta: Callable[[str], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
    chat_id: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    normalize_tools: bool = True,
    _transient_retry: bool = True,
) -> tuple[str, dict[str, int]]:
    """
    Stream chat completions (SSE). Calls on_delta(token) for each piece.
    Falls back to non-streaming if the server rejects stream=true.
    Returns (full_text, usage_dict). Stops early if should_stop() is True.

    Dual path: optional native `tools` + streamed tool_calls deltas merged by index;
    content JSON / <tool_call> normalized to text blocks at the end.
    Transient gateway errors (524/502/…) retry once (stream again, then non-stream).
    """
    key = (api_key or "").strip()
    if not key:
        raise LLMError("No API key configured. Open Settings / Providers and add a key.")

    url = base_url.rstrip("/") + "/chat/completions"
    msgs = trim_messages_to_context(messages, chat_id=chat_id)
    body: dict[str, Any] = {
        "model": model,
        "messages": msgs,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    body.update(build_api_body_extras())
    # Critical for OpenRouter low balance: never leave max_tokens unset (Grok → 65k → 402)
    _apply_safe_max_tokens(body, base_url=base_url, max_tokens=None)
    if tools:
        body["tools"] = tools
        body["tool_choice"] = tool_choice if tool_choice is not None else "auto"
    data = json.dumps(body).encode("utf-8")
    headers = _headers(key, base_url)
    headers["Accept"] = "text/event-stream"
    req = urllib.request.Request(url, data=data, method="POST", headers=headers)

    pieces: list[str] = []
    usage_out = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    stopped = False
    # Accumulate streamed tool_calls by index (OpenAI sends partial deltas)
    # shape: {index: {"id":..., "type":..., "function": {"name":..., "arguments":...}}}
    tool_call_acc: dict[int, dict[str, Any]] = {}

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            while True:
                if should_stop and should_stop():
                    stopped = True
                    break
                raw = resp.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").strip()
                if not line or line.startswith(":"):
                    continue
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if chunk.get("usage"):
                    u = chunk["usage"]
                    usage_out = {
                        "prompt_tokens": int(u.get("prompt_tokens") or 0),
                        "completion_tokens": int(u.get("completion_tokens") or 0),
                        "total_tokens": int(u.get("total_tokens") or 0),
                    }
                choices = chunk.get("choices") or []
                if not choices:
                    continue

                delta_info = choices[0].get("delta", {}) or {}
                tc_deltas = delta_info.get("tool_calls")
                if tc_deltas and isinstance(tc_deltas, list):
                    for td in tc_deltas:
                        if not isinstance(td, dict):
                            continue
                        idx = int(td.get("index") if td.get("index") is not None else 0)
                        slot = tool_call_acc.setdefault(
                            idx,
                            {
                                "id": "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            },
                        )
                        if td.get("id"):
                            slot["id"] = td["id"]
                        if td.get("type"):
                            slot["type"] = td["type"]
                        fn = td.get("function") or {}
                        if isinstance(fn, dict):
                            if fn.get("name"):
                                slot["function"]["name"] = (
                                    (slot["function"].get("name") or "") + str(fn["name"])
                                )
                            if fn.get("arguments") is not None:
                                slot["function"]["arguments"] = (
                                    (slot["function"].get("arguments") or "")
                                    + str(fn.get("arguments") or "")
                                )

                content_delta = delta_info.get("content") or ""
                if content_delta:
                    pieces.append(content_delta)
                    if on_delta:
                        try:
                            on_delta(content_delta)
                        except Exception:  # noqa: BLE001
                            pass
        if stopped and pieces:
            pieces.append("\n\n*(stopped)*")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:2000]
        # tools rejected while streaming → retry stream without tools, or non-stream
        if tools and e.code in (400, 404, 422) and _tools_rejected(detail):
            return chat_completion_stream(
                api_key=key,
                messages=messages,
                model=model,
                base_url=base_url,
                timeout=timeout,
                on_delta=on_delta,
                should_stop=should_stop,
                chat_id=chat_id,
                tools=None,
                tool_choice=None,
                normalize_tools=normalize_tools,
                _transient_retry=_transient_retry,
            )
        if e.code in (400, 404, 422, 501) or "stream" in detail.lower():
            text, usage = chat_completion(  # type: ignore[misc]
                api_key=key,
                messages=messages,
                model=model,
                base_url=base_url,
                timeout=timeout,
                return_usage=True,
                chat_id=chat_id,
                tools=tools,
                tool_choice=tool_choice,
                normalize_tools=normalize_tools,
            )
            assert isinstance(text, str)
            if on_delta and text:
                step = max(12, len(text) // 40)
                for i in range(0, len(text), step):
                    on_delta(text[i : i + step])
            return text, usage  # type: ignore[return-value]
        # 524 / gateway: one stream retry, then non-stream (often more reliable)
        if _transient_retry and int(e.code) in _TRANSIENT_HTTP:
            import time

            time.sleep(1.6 if int(e.code) in (524, 504, 408) else 1.0)
            try:
                return chat_completion_stream(
                    api_key=key,
                    messages=messages,
                    model=model,
                    base_url=base_url,
                    timeout=timeout,
                    on_delta=on_delta,
                    should_stop=should_stop,
                    chat_id=chat_id,
                    tools=tools,
                    tool_choice=tool_choice,
                    normalize_tools=normalize_tools,
                    _transient_retry=False,
                )
            except LLMError:
                # Final fallback: non-streaming (also has its own one-shot retry)
                text, usage = chat_completion(  # type: ignore[misc]
                    api_key=key,
                    messages=messages,
                    model=model,
                    base_url=base_url,
                    timeout=timeout,
                    return_usage=True,
                    chat_id=chat_id,
                    tools=tools,
                    tool_choice=tool_choice,
                    normalize_tools=normalize_tools,
                    _transient_retry=True,
                )
                assert isinstance(text, str)
                if on_delta and text:
                    step = max(12, len(text) // 40)
                    for i in range(0, len(text), step):
                        on_delta(text[i : i + step])
                return text, usage  # type: ignore[return-value]
        raise LLMError(format_llm_http_error(int(e.code), detail)) from e
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", None) or str(e)
        raise LLMError(f"Network error: {reason}") from e
    except TimeoutError as e:
        if _transient_retry:
            import time

            time.sleep(1.2)
            try:
                return chat_completion_stream(
                    api_key=key,
                    messages=messages,
                    model=model,
                    base_url=base_url,
                    timeout=timeout,
                    on_delta=on_delta,
                    should_stop=should_stop,
                    chat_id=chat_id,
                    tools=tools,
                    tool_choice=tool_choice,
                    normalize_tools=normalize_tools,
                    _transient_retry=False,
                )
            except LLMError:
                text, usage = chat_completion(  # type: ignore[misc]
                    api_key=key,
                    messages=messages,
                    model=model,
                    base_url=base_url,
                    timeout=timeout,
                    return_usage=True,
                    chat_id=chat_id,
                    tools=tools,
                    tool_choice=tool_choice,
                    normalize_tools=normalize_tools,
                )
                assert isinstance(text, str)
                if on_delta and text:
                    step = max(12, len(text) // 40)
                    for i in range(0, len(text), step):
                        on_delta(text[i : i + step])
                return text, usage  # type: ignore[return-value]
        raise LLMError(
            "Request timed out. Try again, or use a faster model / shorter prompt."
        ) from e

    full = "".join(pieces).strip()

    # Dual path: merge streamed tool_calls + normalize content JSON/XML
    ordered_tc: list[dict[str, Any]] | None = None
    if tool_call_acc:
        ordered_tc = [tool_call_acc[i] for i in sorted(tool_call_acc.keys())]
        ordered_tc = [tc for tc in ordered_tc if (tc.get("function") or {}).get("name")]
        if not ordered_tc:
            ordered_tc = None

    if normalize_tools:
        full = ensure_executable_tool_format(full, ordered_tc)
    elif ordered_tc:
        converted = _convert_tool_calls_to_text_blocks(ordered_tc)
        if converted:
            full = (full + "\n\n" if full else "") + converted

    # Fallback: non-streaming retry if nothing received
    if not full:
        text, usage = chat_completion(  # type: ignore[misc]
            api_key=key,
            messages=messages,
            model=model,
            base_url=base_url,
            timeout=timeout,
            return_usage=True,
            chat_id=chat_id,
            tools=tools,
            tool_choice=tool_choice,
            normalize_tools=normalize_tools,
        )
        if on_delta and isinstance(text, str):
            step = max(12, len(text) // 40)
            for i in range(0, len(text), step):
                on_delta(text[i : i + step])
        return text, usage  # type: ignore[return-value]

    if not usage_out.get("completion_tokens") and full:
        from app.core.services.data.usage_meter import estimate_tokens_from_text

        prompt_blob = "\n".join(m.get("content") or "" for m in msgs)
        usage_out = {
            "prompt_tokens": estimate_tokens_from_text(prompt_blob),
            "completion_tokens": estimate_tokens_from_text(full),
            "total_tokens": 0,
        }
        usage_out["total_tokens"] = usage_out["prompt_tokens"] + usage_out["completion_tokens"]

    return full, usage_out