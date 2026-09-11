"""OpenAI-compatible tool schemas for dual-path tool calling.

Path A — Text blocks in the assistant message (always preferred / always works offline)
Path B — Native OpenAI `tools` + `tool_calls` on the API response

Both paths are converted to the same <<<TOOL>>>…<<<END_TOOL>>> form before
execution (see tool_normalizer + llm converters). Models may use either.
"""

from __future__ import annotations

from typing import Any


def _fn(
    name: str,
    desc: str,
    props: dict[str, Any],
    required: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": {
                "type": "object",
                "properties": props,
                "required": required or [],
            },
        },
    }


def studio_openai_tools(*, include_harness: bool = True) -> list[dict[str, Any]]:
    """Full tool catalog exposed as OpenAI function-calling schemas.

    Names align with llm._TOOL_NAME_MAP / tool_normalizer so conversion is reliable.
    """
    tools: list[dict[str, Any]] = [
        # Terminal / shell
        _fn(
            "run_terminal",
            "Run a shell/PowerShell command on the user's Windows PC",
            {"command": {"type": "string", "description": "Command to run"}},
            ["command"],
        ),
        _fn(
            "terminal",
            "Alias of run_terminal — execute a shell command",
            {"command": {"type": "string"}},
            ["command"],
        ),
        # Web
        _fn(
            "web_search",
            "Search the web (adult/safe-search-off always on). Use for facts, lists, porn sources, news.",
            {
                "query": {"type": "string"},
                "max": {"type": "integer", "description": "Max hits (optional)"},
                "fetch": {"type": "integer", "description": "Open top N pages (optional)"},
            },
            ["query"],
        ),
        _fn(
            "web_fetch",
            "Fetch a URL and return readable text",
            {"url": {"type": "string"}},
            ["url"],
        ),
        _fn(
            "deep_research",
            "Multi-step deep web research on a topic",
            {"query": {"type": "string"}},
            ["query"],
        ),
        _fn(
            "browser",
            "Control the persistent Chromium browser session",
            {
                "action": {
                    "type": "string",
                    "description": "goto|click|fill|type|scroll|screenshot|links|download|…",
                },
                "url": {"type": "string"},
                "selector": {"type": "string"},
                "text": {"type": "string"},
            },
            ["action"],
        ),
        # Media
        _fn(
            "image_gen",
            "Generate an image from a text prompt via the image API",
            {
                "prompt": {"type": "string"},
                "size": {"type": "string", "description": "e.g. 1024x1024"},
            },
            ["prompt"],
        ),
        _fn(
            "screenshot",
            "Capture the desktop screen",
            {"name": {"type": "string", "description": "Optional label"}},
            [],
        ),
        # Laptop control
        _fn(
            "gui",
            "Mouse/keyboard GUI actions as JSON array",
            {"actions": {"type": "string", "description": "JSON array of GUI actions"}},
            ["actions"],
        ),
        _fn(
            "clipboard",
            "Clipboard get/set",
            {"action": {"type": "string"}, "text": {"type": "string"}},
            [],
        ),
        _fn(
            "windows",
            "List or focus windows",
            {"action": {"type": "string"}, "title": {"type": "string"}},
            [],
        ),
        # Skills / MCP / packages
        _fn(
            "skill",
            "Load a skill playbook by name or path",
            {"name": {"type": "string"}},
            ["name"],
        ),
        _fn(
            "mcp",
            "Call an MCP tool",
            {
                "server": {"type": "string"},
                "tool_name": {"type": "string"},
                "arguments": {"type": "object"},
            },
            ["server", "tool_name"],
        ),
        _fn(
            "pip_install",
            "Install Python packages",
            {"packages": {"type": "string", "description": "Space or comma separated packages"}},
            ["packages"],
        ),
        # Knowledge / OCR
        _fn(
            "knowledge",
            "RAG knowledge base search/add",
            {"action": {"type": "string"}, "query": {"type": "string"}},
            [],
        ),
        _fn(
            "ocr",
            "OCR an image path",
            {"image_path": {"type": "string"}},
            ["image_path"],
        ),
    ]

    if include_harness:
        tools.extend(
            [
                _fn(
                    "read_file",
                    "Read a file with line numbers",
                    {
                        "path": {"type": "string"},
                        "offset": {"type": "integer"},
                        "limit": {"type": "integer"},
                    },
                    ["path"],
                ),
                _fn(
                    "write_file",
                    "Write full file content",
                    {"path": {"type": "string"}, "content": {"type": "string"}},
                    ["path", "content"],
                ),
                _fn(
                    "search_replace",
                    "Exact string replace in a file",
                    {
                        "path": {"type": "string"},
                        "old_string": {"type": "string"},
                        "new_string": {"type": "string"},
                        "replace_all": {"type": "boolean"},
                    },
                    ["path", "old_string", "new_string"],
                ),
                _fn(
                    "list_dir",
                    "List directory entries",
                    {"path": {"type": "string"}},
                    [],
                ),
                _fn(
                    "grep",
                    "Regex search in files",
                    {
                        "pattern": {"type": "string"},
                        "path": {"type": "string"},
                        "glob": {"type": "string"},
                    },
                    ["pattern"],
                ),
                _fn(
                    "spawn_subagent",
                    "Run a child agent",
                    {"prompt": {"type": "string"}, "type": {"type": "string"}},
                    ["prompt"],
                ),
                _fn("git_status", "Git status", {}, []),
                _fn(
                    "git_diff",
                    "Git diff",
                    {"staged": {"type": "boolean"}},
                    [],
                ),
                _fn(
                    "git_commit",
                    "Git commit",
                    {"message": {"type": "string"}},
                    ["message"],
                ),
                _fn(
                    "bg_shell",
                    "Background shell command",
                    {"command": {"type": "string"}},
                    ["command"],
                ),
                _fn(
                    "todo_write",
                    "Update agent todos",
                    {"items": {"type": "array"}},
                    ["items"],
                ),
                _fn(
                    "plan_write",
                    "Write plan.md",
                    {"content": {"type": "string"}},
                    ["content"],
                ),
                _fn(
                    "ask_user",
                    "Ask the user a structured question",
                    {
                        "question": {"type": "string"},
                        "options": {"type": "array"},
                    },
                    ["question"],
                ),
            ]
        )

    return tools


def dual_path_tool_hint() -> str:
    """Short system-prompt add-on explaining both paths."""
    return """
## Dual tool paths (both work)
1. **Text blocks** (always executed by this app):
   <<<TERMINAL>>>
   Start-Process chrome
   <<<END_TERMINAL>>>
2. **Native OpenAI function tools** (`run_terminal`, `web_search`, …) — when schemas are
   sent, prefer structured tool_calls. Studio executes them and continues with role:tool
   results (also converts to text blocks for the harness).
3. **JSON / `<tool_call>` in content** — also auto-converted before execution.

Never invent tool results. Use native tool_calls when tools schemas are present;
text blocks and JSON still work as fallbacks.
""".strip()
