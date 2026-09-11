"""Universal tool-call normalizer — handles ANY model output format.

Strategies (applied in order):
  0. Repair hybrid / XML-ish pseudo tool calls (<tool_call>, {\"TERMINAL\"}, etc.)
  1. Text blocks: <<<TERMINAL>>>\\ncmd\\n<<<END_TERMINAL>>>  (passthrough if clean)
  2. OpenAI tool_calls: {\"name\":\"run_terminal\",\"arguments\":{\"command\":\"...\"}}
  3. Simplified JSON key-value: {\"terminal\": \"cmd\"} / {\"queries\": [...]}

After normalization, the reply contains text-block format which
existing extraction functions in chat.py can handle natively.

Why models emit JSON instead of text blocks
-------------------------------------------
Most LLMs (Qwen, Llama, GPT, etc.) are trained heavily on OpenAI-style
function calling and XML tool wrappers. Even when the system prompt
demands <<<TERMINAL>>>…<<<END_TERMINAL>>>, they often fall back to:
  - <tool_call>{\"terminal\": \"...\"}</tool_call>
  - {\"name\": \"run_terminal\", \"arguments\": {...}}
  - hybrid: <tool_call>{\"TERMINAL\"}\\ncmd\\n<<<END_TERMINAL>>>
This module converts those into the app's real text-block protocol so tools
actually execute.
"""

from __future__ import annotations

import json
import re
from typing import Any


# ---------------------------------------------------------------------------
# Strategy 3: Simplified JSON → Text Block mappings
# ---------------------------------------------------------------------------

# Maps simplified JSON keys to (block_name, default_body_label).
# default_body_label: used for string values; for TERMINAL/WEB_SEARCH we may
# emit a raw body (no "key: " prefix) because extractors expect that.
_SIMPLE_KEY_MAP: dict[str, tuple[str, str]] = {
    # terminal / shell
    "terminal": ("TERMINAL", "command"),
    "shell": ("TERMINAL", "command"),
    "shell_exec": ("TERMINAL", "command"),
    "execute": ("TERMINAL", "command"),
    "run_terminal": ("TERMINAL", "command"),
    "execute_command": ("TERMINAL", "command"),
    "cmd": ("TERMINAL", "command"),
    "command": ("TERMINAL", "command"),
    # search
    "web_search": ("WEB_SEARCH", "query"),
    "search": ("WEB_SEARCH", "query"),
    "google_search": ("WEB_SEARCH", "query"),
    "bing_search": ("WEB_SEARCH", "query"),
    "brave_search": ("WEB_SEARCH", "query"),
    "queries": ("WEB_SEARCH", "query"),  # array of queries
    # thinking / reasoning (for models like Nemotron, QwQ, etc.)
    "thinking": ("THINKING", "content"),
    "reasoning": ("REASONING", "content"),
    "thought": ("THINKING", "content"),
    "thoughts": ("THINKING", "content"),
    "reason": ("REASONING", "content"),
    # file operations (harness format)
    "read_file": ("READ_FILE", None),
    "write_file": ("WRITE_FILE", None),
    "search_replace": ("SEARCH_REPLACE", None),
    "set_goal": ("SET_GOAL", "goal"),
    "update_goal": ("SET_GOAL", "goal"),
    "finding": ("FINDING", "text"),
    "add_finding": ("FINDING", "text"),
    "resolve_finding": ("RESOLVE_FINDING", "text"),
    "close_finding": ("RESOLVE_FINDING", "text"),
    "reopen_finding": ("REOPEN_FINDING", "text"),
    "list_dir": ("LIST_DIR", None),
    "grep_search": ("GREP", None),
    "grep": ("GREP", None),
    # git
    "git_status": ("GIT_STATUS", None),
    "git_diff": ("GIT_DIFF", None),
    "git_commit": ("GIT_COMMIT", None),
    "git_add": ("GIT_ADD", None),
    "git_log": ("GIT_LOG", None),
    # browser
    "browser": ("BROWSER", None),
    "open_url": ("BROWSER", None),
    # image gen
    "image_gen": ("IMAGE_GEN", None),
    "generate_image": ("IMAGE_GEN", None),
    "dalle3": ("IMAGE_GEN", None),
    "dall_e_3": ("IMAGE_GEN", None),
    # MCP
    "mcp": ("MCP", None),
    # screenshot / GUI
    "screenshot": ("SCREENSHOT", None),
    "take_screenshot": ("SCREENSHOT", None),
    "gui": ("GUI", None),
    "click": ("GUI", None),
    "type_text": ("GUI", None),
    "keyboard": ("GUI", None),
    # clipboard
    "clipboard": ("CLIPBOARD", None),
    "read_clipboard": ("CLIPBOARD", None),
    # windows / focus
    "windows": ("WINDOWS", None),
    "focus_app": ("WINDOWS", None),
    "list_windows": ("WINDOWS", None),
    # knowledge / rag
    "knowledge": ("KNOWLEDGE", None),
    "rag_search": ("KNOWLEDGE", None),
    # ocr
    "ocr": ("OCR", None),
    # skills
    "skill": ("SKILL", None),
    "load_skill": ("SKILL", None),
    # web fetch / browse
    "web_fetch": ("WEB_FETCH", None),
    "fetch_url": ("WEB_FETCH", None),
    # deep research
    "deep_research": ("DEEP_RESEARCH", None),
    # crawl / scrape
    "crawl": ("CRAWL", None),
    "scrape": ("SCRAPE", None),
    "download": ("DOWNLOAD", None),
    # patch review
    "patch_review": ("PATCH_REVIEW", None),
    # self-improve
    "self_improve": ("SELF_IMPROVE", None),
    "backup": ("BACKUP", None),
    "rollback": ("ROLLBACK", None),
    # subagent
    "spawn_subagent": ("SPAWN_SUBAGENT", None),
    # todo / plan
    "todo_write": ("TODO_WRITE", None),
    "plan_write": ("PLAN_WRITE", None),
    "ask_user": ("ASK_USER", None),
}

# Tools that should emit raw body (no "key: value") when value is a plain string
_RAW_BODY_BLOCKS = frozenset({
    "TERMINAL", "WEB_SEARCH", "SKILL", "WEB_FETCH", "DEEP_RESEARCH",
    "SCREENSHOT", "OCR",
    # thinking / reasoning - emit raw body
    "THINKING", "REASONING",
    "SET_GOAL",
    "FINDING",
    "RESOLVE_FINDING",
    "REOPEN_FINDING",
})

# Known block names for hybrid repair {"TERMINAL"} / {"WEB_SEARCH"}
_KNOWN_BLOCK_NAMES = frozenset({
    "TERMINAL", "WEB_SEARCH", "READ_FILE", "WRITE_FILE", "SEARCH_REPLACE",
    "LIST_DIR", "GREP", "GIT_STATUS", "GIT_DIFF", "GIT_COMMIT", "GIT_ADD", "GIT_LOG",
    "BROWSER", "IMAGE_GEN", "MCP", "SCREENSHOT", "GUI", "CLIPBOARD",
    "WINDOWS", "KNOWLEDGE", "OCR", "SKILL", "WEB_FETCH", "DEEP_RESEARCH",
    "CRAWL", "SCRAPE", "DOWNLOAD", "PATCH_REVIEW", "SELF_IMPROVE",
    "BACKUP", "ROLLBACK", "IMAGE", "VIDEO", "ORG_COMMAND", "PIP_INSTALL",
    "AGENTS", "TODO_WRITE", "PLAN_WRITE", "ENTER_PLAN", "EXIT_PLAN",
    "SPAWN_SUBAGENT", "GET_SUBAGENT", "BG_SHELL", "BG_STATUS", "BG_KILL",
    "ASK_USER", "PROJECT_RULES", "SANDBOX_STATUS", "PERMISSION_STATUS",
    "PIP", "SUBAGENT",
    # thinking / reasoning blocks
    "THINKING", "REASONING",
    "SET_GOAL",
    "FINDING",
    "RESOLVE_FINDING",
    "REOPEN_FINDING",
})


# XML-style tool tags like <TERMINAL>cmd</TERMINAL>, <WEB_SEARCH>query</WEB_SEARCH>
# Some models (e.g. Nemotron) output this format instead of <<<TERMINAL>>>...<<<END_TERMINAL>>>
_XML_TOOL_TAG_RE = re.compile(
    r"<([A-Z][A-Z0-9_]*)>\s*(.*?)\s*</\1>",
    re.DOTALL | re.IGNORECASE,
)


def _normalize_simple_value(value: Any, key_label: str) -> tuple[str, str] | None:
    """Convert a simple value to (text_key, formatted_text). Returns None if can't convert."""
    if isinstance(value, str):
        return key_label, value
    if isinstance(value, dict):
        for candidate_key in ["command", "cmd", "query", "q", "text", "content", "action", "url", "prompt", "goal"]:
            if candidate_key in value and isinstance(value[candidate_key], str):
                return key_label, value[candidate_key]
    if isinstance(value, list):
        items = [str(v) for v in value if isinstance(v, str)]
        if items:
            return key_label, "\n".join(items)
    return None


def _extract_nested_args(value: Any) -> dict[str, str] | None:
    """Extract normalized string arguments from a complex (dict/list) value."""
    if isinstance(value, dict):
        if not value:
            return {}
        result: dict[str, str] = {}
        arg_keys = [
            "path", "offset", "limit", "content", "old_string", "new_string",
            "old", "new",
            "replace_all", "pattern", "glob", "action", "url", "selector",
            "size", "prompt", "query", "command", "cmd", "text", "message",
            "server", "tool_name", "arguments", "reason", "mode", "note",
            "type", "name", "cwd", "timeout", "goal",
        ]
        for k in arg_keys:
            if k in value:
                v = value[k]
                if isinstance(v, str):
                    result[k] = v
                elif isinstance(v, (int, float, bool)):
                    result[k] = str(v)
                elif isinstance(v, (dict, list)):
                    result[k] = json.dumps(v, ensure_ascii=False)
        return result
    return None


def _build_text_block(block_name: str, args: dict[str, str] | None, *, raw: str | None = None) -> str:
    """Build a text block from parsed arguments or a raw body string."""
    if raw is not None:
        body = raw.strip()
        return f"<<<{block_name}>>>\n{body}\n<<<END_{block_name}>>>"

    args = args or {}
    # TERMINAL with single command → raw body (extractors take whole body as cmd)
    if block_name == "TERMINAL":
        for k in ("command", "cmd", "text"):
            if k in args and args[k].strip():
                return f"<<<TERMINAL>>>\n{args[k].strip()}\n<<<END_TERMINAL>>>"
        if len(args) == 1:
            only = next(iter(args.values()))
            if only.strip():
                return f"<<<TERMINAL>>>\n{only.strip()}\n<<<END_TERMINAL>>>"

    # WEB_SEARCH with single query → raw body preferred
    if block_name == "WEB_SEARCH" and "query" in args and len(args) == 1:
        return f"<<<WEB_SEARCH>>>\n{args['query'].strip()}\n<<<END_WEB_SEARCH>>>"

    if block_name == "SET_GOAL":
        for k in ("goal", "text", "content"):
            if k in args and str(args[k]).strip():
                return f"<<<SET_GOAL>>>\n{str(args[k]).strip()}\n<<<END_SET_GOAL>>>"
        if len(args) == 1:
            only = next(iter(args.values()))
            if str(only).strip():
                return f"<<<SET_GOAL>>>\n{str(only).strip()}\n<<<END_SET_GOAL>>>"

    lines: list[str] = []
    for key, val in args.items():
        # Normalize terminal labels
        label = key
        if block_name == "TERMINAL" and key in ("cmd", "command"):
            continue  # already handled
        lines.append(f"{label}: {val}")
    body = "\n".join(lines).strip()
    if not body and block_name in ("GIT_STATUS", "SCREENSHOT", "SANDBOX_STATUS", "PERMISSION_STATUS"):
        return f"<<<{block_name}>>>\n<<<END_{block_name}>>>"
    return f"<<<{block_name}>>>\n{body}\n<<<END_{block_name}>>>"


def _try_parse_json_at(text: str, pos: int) -> tuple[Any, int] | None:
    """Try to parse a JSON value starting at pos in text. Returns parsed value and end position."""
    depth = 0
    start = pos
    in_string = False
    escape = False

    for i in range(pos, len(text)):
        ch = text[i]

        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in ("{", "["):
            depth += 1
        elif ch in ("}", "]"):
            depth -= 1
            if depth == 0:
                segment = text[start : i + 1]
                try:
                    return json.loads(segment), i + 1
                except (json.JSONDecodeError, ValueError):
                    return None
    return None


def _dict_to_blocks(parsed: dict[str, Any]) -> list[str]:
    """Convert one JSON object (simplified or OpenAI-style) into text blocks."""
    blocks: list[str] = []

    # OpenAI single: {"name": "run_terminal", "arguments": {...}}
    name = parsed.get("name") or parsed.get("tool") or parsed.get("function_name")
    args_val = parsed.get("arguments") or parsed.get("parameters") or parsed.get("args")
    if isinstance(name, str) and name and args_val is not None:
        blocks.extend(_openai_name_args_to_blocks(name, args_val))
        if blocks:
            return blocks

    # Nemotron / Studio-style: {"action": "search_replace", "path": "...", "old": "...", "new": "..."}
    action = parsed.get("action") or parsed.get("tool_name")
    if isinstance(action, str) and action.strip():
        act = action.lower().strip().replace("-", "_")
        if act in _SIMPLE_KEY_MAP:
            rest = {
                k: v
                for k, v in parsed.items()
                if str(k).lower() not in ("action", "tool_name")
            }
            if "old" in rest and "old_string" not in rest:
                rest["old_string"] = rest.pop("old")
            if "new" in rest and "new_string" not in rest:
                rest["new_string"] = rest.pop("new")
            return _dict_to_blocks({act: rest})

    # OpenAI nested: {"function": {"name": "...", "arguments": ...}}
    func_obj = parsed.get("function")
    if isinstance(func_obj, dict) and func_obj.get("name"):
        blocks.extend(
            _openai_name_args_to_blocks(
                str(func_obj["name"]),
                func_obj.get("arguments") or {},
            )
        )
        if blocks:
            return blocks

    # Simplified keys: {"terminal": "cmd"} / {"web_search": "q"} / {"queries": [...]}
    for key, value in parsed.items():
        key_lower = str(key).lower().strip()
        if key_lower not in _SIMPLE_KEY_MAP:
            # Bare tool name as key with empty/null value: {"TERMINAL": null} handled elsewhere
            if str(key).upper() in _KNOWN_BLOCK_NAMES and value in (None, "", {}, []):
                continue
            continue

        block_name, default_label = _SIMPLE_KEY_MAP[key_lower]

        # queries array → one WEB_SEARCH block per query (or multi-line)
        if key_lower == "queries" and isinstance(value, list):
            for q in value:
                if isinstance(q, str) and q.strip():
                    blocks.append(_build_text_block("WEB_SEARCH", None, raw=q.strip()))
            continue

        if isinstance(value, str) and default_label:
            if block_name in _RAW_BODY_BLOCKS:
                blocks.append(_build_text_block(block_name, None, raw=value))
            else:
                blocks.append(_build_text_block(block_name, {default_label: value}))
            continue

        if isinstance(value, dict):
            nested = _extract_nested_args(value)
            blocks.append(_build_text_block(block_name, nested or {}))
            continue

        if isinstance(value, list) and default_label:
            # list of strings for terminal multi-line or search
            strs = [str(v).strip() for v in value if str(v).strip()]
            if strs and block_name == "TERMINAL":
                for s in strs:
                    blocks.append(_build_text_block("TERMINAL", None, raw=s))
            elif strs and block_name == "WEB_SEARCH":
                for s in strs:
                    blocks.append(_build_text_block("WEB_SEARCH", None, raw=s))
            elif strs:
                blocks.append(_build_text_block(block_name, {default_label: "\n".join(strs)}))

    return blocks


def _openai_name_args_to_blocks(func_name: str, args_val: Any) -> list[str]:
    """Map function name + args into text blocks via llm converter when possible."""
    try:
        from app.core.services.llm.llm import _json_to_text_block
    except Exception:  # noqa: BLE001
        _json_to_text_block = None  # type: ignore[assignment]

    if isinstance(args_val, (dict, list)):
        args_str = json.dumps(args_val, ensure_ascii=False)
    else:
        args_str = str(args_val or "")

    # Prefer shared converter (handles run_terminal, web_search, etc.)
    if _json_to_text_block is not None:
        converted = _json_to_text_block(func_name, args_str)
        if converted and "<<<" in converted:
            # Fix TERMINAL bodies that still have command: prefix
            converted = _fix_terminal_block_bodies(converted)
            return [converted]

    # Fallback: treat name as simplified key
    key = func_name.lower().strip()
    if key in _SIMPLE_KEY_MAP:
        try:
            args_obj = json.loads(args_str) if args_str else {}
        except (json.JSONDecodeError, TypeError):
            args_obj = {"command": args_str} if args_str else {}
        return _dict_to_blocks({key: args_obj if isinstance(args_obj, dict) else args_str})

    return []


def _fix_terminal_block_bodies(text: str) -> str:
    """Ensure TERMINAL blocks have raw command bodies (strip command:/cmd: labels)."""

    def _fix(m: re.Match[str]) -> str:
        body = (m.group(1) or "").strip()
        for prefix in ("command:", "cmd:", "text:"):
            if body.lower().startswith(prefix):
                body = body[len(prefix) :].strip()
                break
        return f"<<<TERMINAL>>>\n{body}\n<<<END_TERMINAL>>>"

    return re.sub(
        r"<<<TERMINAL>>>\s*(.*?)\s*<<<END_TERMINAL>>>",
        _fix,
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )


def _parse_simple_json_to_blocks(reply: str) -> list[str]:
    """Scan reply for JSON objects/arrays and convert known tool shapes to blocks."""
    blocks: list[str] = []
    i = 0

    while i < len(reply):
        # Find next { or [
        pos_brace = reply.find("{", i)
        pos_brack = reply.find("[", i)
        candidates = [p for p in (pos_brace, pos_brack) if p >= 0]
        if not candidates:
            break
        pos = min(candidates)

        # Skip if inside an odd number of quotes before pos
        quote_count = 0
        j = 0
        while j < pos:
            if reply[j] == "\\" and j + 1 < pos:
                j += 2
                continue
            if reply[j] == '"':
                quote_count += 1
            j += 1
        if quote_count % 2 == 1:
            i = pos + 1
            continue

        result = _try_parse_json_at(reply, pos)
        if result is None:
            i = pos + 1
            continue

        parsed, end_pos = result
        i = end_pos

        if isinstance(parsed, list):
            # OpenAI tool_calls array or list of simplified objects
            for elem in parsed:
                if isinstance(elem, dict):
                    blocks.extend(_dict_to_blocks(elem))
            continue

        if isinstance(parsed, dict):
            blocks.extend(_dict_to_blocks(parsed))

    return blocks


# ---------------------------------------------------------------------------
# Strategy 0: Hybrid / XML repair
# ---------------------------------------------------------------------------

# <tool_call> ... </tool_call> or bare <tool_call> without close
_TOOL_CALL_XML_RE = re.compile(
    r"<(?:tool_call|function_call|tool_request|invoke|functioncall)\b[^>]*>(.*?)</(?:tool_call|function_call|tool_request|invoke|functioncall)\s*>",
    re.DOTALL | re.IGNORECASE,
)
_TOOL_CALL_OPEN_RE = re.compile(
    r"<(?:tool_call|function_call|tool_request|invoke|functioncall)\b[^>]*>",
    re.IGNORECASE,
)
_TOOL_CALL_CLOSE_RE = re.compile(
    r"</(?:tool_call|function_call|tool_request|invoke|functioncall)\s*>",
    re.IGNORECASE,
)

# Hybrid: {"TERMINAL"} or {"WEB_SEARCH"} as a name-only object, body follows until END or next tag
_HYBRID_NAME_ONLY_RE = re.compile(
    r"<\s*tool_call\s*>\s*\{\s*[\"']([A-Za-z_][A-Za-z0-9_]*)[\"']\s*\}\s*"
    r"(.*?)"
    r"(?:<<<END_[A-Za-z0-9_]+>>>|</tool_call\s*>|(?=<\s*tool_call\s*>)|$)",
    re.DOTALL | re.IGNORECASE,
)

# Same hybrid without tool_call wrapper: {"TERMINAL"}\ncmd\n<<<END_TERMINAL>>>
_HYBRID_BARE_RE = re.compile(
    r"\{\s*[\"']([A-Za-z_][A-Za-z0-9_]*)[\"']\s*\}\s*\n"
    r"(.*?)"
    r"<<<END_([A-Za-z0-9_]+)>>>",
    re.DOTALL | re.IGNORECASE,
)

# Incomplete open: <<<TERMINAL missing, only END_ present after hybrid name
_MISSING_OPEN_RE = re.compile(
    r"(?:<\s*tool_call\s*>\s*)?\{\s*[\"']([A-Za-z_][A-Za-z0-9_]*)[\"']\s*\}\s*"
    r"(.*?)\s*<<<END_([A-Za-z0-9_]+)>>>",
    re.DOTALL | re.IGNORECASE,
)


def _repair_hybrid_pseudo_calls(reply: str) -> tuple[str, list[str]]:
    """
    Repair hybrid / XML-ish tool pseudo-syntax into proper text blocks.
    Returns (cleaned_reply_without_pseudo, list_of_converted_blocks).
    """
    blocks: list[str] = []
    text = reply or ""

    # 1) Full <tool_call>...</tool_call> bodies → try JSON then hybrid name
    def _xml_repl(m: re.Match[str]) -> str:
        inner = (m.group(1) or "").strip()
        if not inner:
            return ""
        # Try pure JSON inside
        try:
            parsed = json.loads(inner)
            if isinstance(parsed, dict):
                blocks.extend(_dict_to_blocks(parsed))
                return ""
            if isinstance(parsed, list):
                for elem in parsed:
                    if isinstance(elem, dict):
                        blocks.extend(_dict_to_blocks(elem))
                return ""
        except (json.JSONDecodeError, TypeError):
            pass
        # Hybrid: {"TERMINAL"}\nbody or TERMINAL\nbody
        hm = re.match(
            r"\{\s*[\"']([A-Za-z_][A-Za-z0-9_]*)[\"']\s*\}\s*(.*)$",
            inner,
            re.DOTALL,
        )
        if hm:
            name = hm.group(1).upper()
            body = (hm.group(2) or "").strip()
            # Strip trailing END markers
            body = re.sub(r"<<<END_[A-Za-z0-9_]+>>>\s*$", "", body, flags=re.I).strip()
            if name in _KNOWN_BLOCK_NAMES or name in {k.upper() for k in _SIMPLE_KEY_MAP}:
                mapped = _SIMPLE_KEY_MAP.get(name.lower())
                block_name = mapped[0] if mapped else name
                # Strip partial open markers
                body = re.sub(r"^<<<[A-Za-z0-9_]+>>>\s*", "", body).strip()
                blocks.append(_build_text_block(block_name, None, raw=body if body else ""))
                return ""
        # Name on first line, body rest (SPAWN_SUBAGENT style)
        lines = inner.splitlines()
        if lines:
            first = lines[0].strip().strip("{}").strip("\"'")
            if first.upper() in _KNOWN_BLOCK_NAMES or first.lower() in _SIMPLE_KEY_MAP:
                mapped = _SIMPLE_KEY_MAP.get(first.lower())
                block_name = mapped[0] if mapped else first.upper()
                body = "\n".join(lines[1:]).strip()
                body = re.sub(r"<<<END_[A-Za-z0-9_]+>>>\s*$", "", body, flags=re.I).strip()
                blocks.append(_build_text_block(block_name, None, raw=body if body else ""))
                return ""
        # Leave unparsed JSON-like for later scanners — strip wrapper only
        return inner

    text = _TOOL_CALL_XML_RE.sub(_xml_repl, text)

    # 2) Bare open tags without close: <tool_call>\n{json or hybrid}
    # Process remaining <tool_call> ... until next tag or end
    def _open_only_repl(m: re.Match[str]) -> str:
        start = m.end()
        rest = text[start:]
        # End at next tool_call open, close tag, or double newline + non-json
        end_m = re.search(
            r"(?:</(?:tool_call|function_call)\s*>|(?=<\s*tool_call\s*>)|(?=\n\n[^<{]))",
            rest,
            re.I,
        )
        # Prefer consume one JSON object if present
        stripped = rest.lstrip()
        if stripped.startswith("{") or stripped.startswith("["):
            # Find offset of JSON in rest
            jpos = rest.find("{") if "{" in rest[:20] else rest.find("[")
            if jpos < 0:
                jpos = 0
            # Adjust: find first { or [
            for ch, idx in (("{", rest.find("{")), ("[", rest.find("["))):
                pass
            jstart = -1
            for i, ch in enumerate(rest):
                if ch in "{[":
                    jstart = i
                    break
            if jstart >= 0:
                parsed_res = _try_parse_json_at(rest, jstart)
                if parsed_res:
                    parsed, jend = parsed_res
                    after = rest[jend:]
                    # Optional trailing END marker
                    after = re.sub(r"^\s*<<<END_[A-Za-z0-9_]+>>>", "", after, count=1)
                    after = re.sub(r"^\s*</(?:tool_call|function_call)\s*>", "", after, count=1, flags=re.I)
                    if isinstance(parsed, dict):
                        # Name-only {"TERMINAL"} with body after JSON
                        keys = list(parsed.keys())
                        if (
                            len(keys) == 1
                            and parsed[keys[0]] in (None, "", True)
                            and str(keys[0]).upper() in _KNOWN_BLOCK_NAMES
                        ):
                            body = after.strip()
                            body = re.sub(r"<<<END_[A-Za-z0-9_]+>>>\s*$", "", body, flags=re.I).strip()
                            # Stop body at next tool_call
                            body = re.split(r"<\s*tool_call\s*>", body, maxsplit=1)[0].strip()
                            bn = str(keys[0]).upper()
                            mapped = _SIMPLE_KEY_MAP.get(bn.lower())
                            block_name = mapped[0] if mapped else bn
                            blocks.append(_build_text_block(block_name, None, raw=body))
                            return after[len(after) - len(after.lstrip()) :]  # won't use
                        blocks.extend(_dict_to_blocks(parsed))
                    elif isinstance(parsed, list):
                        for elem in parsed:
                            if isinstance(elem, dict):
                                blocks.extend(_dict_to_blocks(elem))
                    # Remove consumed portion from rest by returning empty for match+json
                    # We rewrite whole string differently below
        return m.group(0)  # keep for now if not handled

    # Simpler pass for open-only tool_call + JSON on next lines
    open_pat = re.compile(
        r"<\s*tool_call\s*>\s*(\{.*?\})\s*(?:<<<END_[A-Za-z0-9_]+>>>|</tool_call\s*>)?",
        re.DOTALL | re.IGNORECASE,
    )

    def _open_json_repl(m: re.Match[str]) -> str:
        blob = m.group(1)
        try:
            parsed = json.loads(blob)
        except (json.JSONDecodeError, TypeError):
            # Name-only may fail strict JSON if followed by body — try name-only extract
            nm = re.match(r'\{\s*["\']([A-Za-z_][A-Za-z0-9_]*)["\']\s*\}', blob.strip())
            if nm and nm.group(1).upper() in _KNOWN_BLOCK_NAMES:
                # Body is after the name object in original — handled by MISSING_OPEN
                return m.group(0)
            return m.group(0)
        if isinstance(parsed, dict):
            keys = list(parsed.keys())
            # Name-only object like {"TERMINAL": null} or invalid {"TERMINAL"} already fails
            if len(keys) == 1 and parsed[keys[0]] in (None, "", True, False) and str(keys[0]).upper() in _KNOWN_BLOCK_NAMES:
                return m.group(0)
            got = _dict_to_blocks(parsed)
            if got:
                blocks.extend(got)
                return "\n".join(got)
        return m.group(0)

    text2 = open_pat.sub(_open_json_repl, text)
    if text2 != text:
        text = text2

    # 3) Hybrid name-only with END marker (broken open tag)
    def _missing_open_repl(m: re.Match[str]) -> str:
        name = m.group(1).upper()
        body = (m.group(2) or "").strip()
        end_name = (m.group(3) or name).upper()
        if name not in _KNOWN_BLOCK_NAMES and name.lower() not in _SIMPLE_KEY_MAP:
            return m.group(0)
        mapped = _SIMPLE_KEY_MAP.get(name.lower())
        block_name = mapped[0] if mapped else name
        # Prefer END name if known
        if end_name in _KNOWN_BLOCK_NAMES:
            block_name = end_name if end_name != "SUBAGENT" else "SPAWN_SUBAGENT"
        body = re.sub(r"^<<<[A-Za-z0-9_]+>>>\s*", "", body).strip()
        # If body starts with JSON, leave for other pass — but usually it's cmd text
        blk = _build_text_block(block_name, None, raw=body if body else "")
        blocks.append(blk)
        return blk

    text = _MISSING_OPEN_RE.sub(_missing_open_repl, text)

    # 3.5) Handle XML-style tool tags: <TERMINAL>cmd</TERMINAL>, <WEB_SEARCH>query</WEB_SEARCH>, etc.
    # Some models (e.g. Nemotron) output this format instead of <<<TERMINAL>>>...<<<END_TERMINAL>>>
    def _xml_tool_tag_repl(m: re.Match[str]) -> str:
        name = m.group(1).upper()
        body = (m.group(2) or "").strip()
        # Strip trailing END markers that might have been included
        body = re.sub(r"<<<END_[A-Za-z0-9_]+>>>\\s*$", "", body, flags=re.I).strip()
        if name in _KNOWN_BLOCK_NAMES or name in {k.upper() for k in _SIMPLE_KEY_MAP}:
            mapped = _SIMPLE_KEY_MAP.get(name.lower())
            block_name = mapped[0] if mapped else name
            blocks.append(_build_text_block(block_name, None, raw=body if body else ""))
            return ""
        return m.group(0)

    text = _XML_TOOL_TAG_RE.sub(_xml_tool_tag_repl, text)

    # 4) Strip leftover wrappers that no longer wrap content
    text = _TOOL_CALL_OPEN_RE.sub("", text)
    text = _TOOL_CALL_CLOSE_RE.sub("", text)

    # Deduplicate blocks while preserving order
    seen: set[str] = set()
    uniq: list[str] = []
    for b in blocks:
        if b not in seen:
            seen.add(b)
            uniq.append(b)

    return text, uniq


def _has_clean_text_blocks(reply: str) -> bool:
    """True if reply already has well-formed <<<NAME>>>...<<<END_NAME>>> pairs."""
    if "<<<" not in reply or "END_" not in reply:
        return False
    # At least one proper pair
    pair_re = re.compile(
        r"<<<([A-Za-z0-9_]+)>>>\s*.*?\s*<<<END_\1>>>",
        re.DOTALL | re.IGNORECASE,
    )
    if pair_re.search(reply):
        # If also has broken hybrid markers, still need repair
        if re.search(r"<\s*tool_call\s*>", reply, re.I):
            return False
        if re.search(r'\{\s*["\'][A-Za-z_]+["\']\s*\}\s*\n', reply):
            # name-only hybrid still present
            if not pair_re.search(reply):
                return False
            # If we have clean pairs and no tool_call, OK
            return True
        return True
    return False


def _is_openai_tool_calls_array(text: str) -> bool:
    """Detect if text is an OpenAI-style tool_calls array."""
    try:
        parsed = json.loads(text.strip())
        if isinstance(parsed, list) and len(parsed) > 0:
            first = parsed[0]
            if isinstance(first, dict):
                func = first.get("function", {})
                if isinstance(func, dict) and func.get("name") and (
                    func.get("arguments") is not None or "arguments" in func
                ):
                    return True
                if first.get("name") and (
                    first.get("arguments") is not None or "arguments" in first
                ):
                    return True
    except (json.JSONDecodeError, TypeError):
        pass
    return False


def normalize_tool_calls(reply: str) -> str:
    """Universal tool-call normalizer.

    Converts any common model output format into text blocks the app executes.
    """
    if reply is None:
        return reply  # type: ignore[return-value]

    stripped = (reply or "").strip()
    if not stripped:
        return reply

    original = reply
    collected: list[str] = []

    # Strategy 0: repair hybrid / XML pseudo-calls first
    needs_hybrid = bool(
        re.search(r"<\s*tool_call\s*>", stripped, re.I)
        or re.search(r"<\s*function_call\s*>", stripped, re.I)
        or re.search(r'\{\s*["\'][A-Z][A-Za-z0-9_]*["\']\s*\}', stripped)
    )
    if needs_hybrid or not _has_clean_text_blocks(stripped):
        cleaned, hybrid_blocks = _repair_hybrid_pseudo_calls(reply)
        collected.extend(hybrid_blocks)
        reply = cleaned
        stripped = (reply or "").strip()

    # Strategy 1: Already has clean text blocks — still fix TERMINAL command: labels
    if _has_clean_text_blocks(stripped) and not collected:
        fixed = _fix_terminal_block_bodies(reply)
        # Also scan for any leftover simplified JSON beside blocks
        extra = _parse_simple_json_to_blocks(reply)
        # Only keep extras that aren't already present as blocks
        extra = [e for e in extra if e not in fixed]
        if extra:
            return fixed.rstrip() + "\n\n---\n" + "\n\n".join(extra)
        return fixed

    # Strategy 2a: Entire reply is OpenAI tool_calls array
    if _is_openai_tool_calls_array(stripped):
        from app.core.services.llm.llm import _convert_tool_calls_to_text_blocks

        parsed = json.loads(stripped)
        standard_format = []
        for elem in parsed:
            if isinstance(elem, dict):
                func_name = None
                args_val = None
                func_obj = elem.get("function", {})
                if isinstance(func_obj, dict) and func_obj.get("name"):
                    func_name = func_obj["name"]
                    args_val = func_obj.get("arguments", "")
                    if not isinstance(args_val, str):
                        args_val = json.dumps(args_val, ensure_ascii=False)
                elif elem.get("name") is not None:
                    func_name = elem["name"]
                    args_val = elem.get("arguments", "")
                    if not isinstance(args_val, str):
                        args_val = json.dumps(args_val, ensure_ascii=False)
                if func_name:
                    standard_format.append(
                        {"function": {"name": func_name, "arguments": args_val or "{}"}}
                    )
        if standard_format:
            converted = _convert_tool_calls_to_text_blocks(standard_format)
            converted = _fix_terminal_block_bodies(converted)
            if converted:
                collected.append(converted)

    # Strategy 2b: Entire reply is single OpenAI tool object
    if not collected:
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict):
                got = _dict_to_blocks(parsed)
                if got:
                    collected.extend(got)
        except (json.JSONDecodeError, TypeError):
            pass

    # Strategy 3: Scan reply for any simplified / embedded JSON tool shapes
    json_blocks = _parse_simple_json_to_blocks(reply)
    for b in json_blocks:
        if b not in collected:
            collected.append(b)

    if not collected:
        # Maybe only terminal label fix
        if "<<<TERMINAL>>>" in (reply or ""):
            return _fix_terminal_block_bodies(reply)
        return original

    # Merge: keep human-readable prose, append converted blocks
    prose = reply
    # Drop pure-JSON-only replies from prose when entire content was tool call
    pure_json = False
    try:
        json.loads(stripped)
        pure_json = True
    except (json.JSONDecodeError, TypeError):
        pure_json = False

    # Remove converted JSON snippets from prose roughly (optional cleanup of tool_call shells)
    prose = _TOOL_CALL_OPEN_RE.sub("", prose)
    prose = _TOOL_CALL_CLOSE_RE.sub("", prose)
    prose = prose.strip()

    # Dedup blocks
    seen: set[str] = set()
    uniq_blocks: list[str] = []
    for b in collected:
        b = _fix_terminal_block_bodies(b)
        if b not in seen:
            seen.add(b)
            uniq_blocks.append(b)

    block_blob = "\n\n".join(uniq_blocks)

    if pure_json or not prose or prose in ("---",):
        return block_blob

    # If prose already contains the same blocks, don't double
    if all(b in prose for b in uniq_blocks):
        return _fix_terminal_block_bodies(prose)

    return f"{prose}\n\n---\n{block_blob}"
