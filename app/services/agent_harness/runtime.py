"""
Harness runtime: text-block protocol + dispatch + OpenAI tool schemas + chat integration.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from app.services.agent_harness import (
    agent_todo,
    ask_user,
    bg_tasks,
    file_tools,
    git_tools,
    hooks,
    permissions,
    plan_mode,
    project_rules,
    sandbox,
    subagent,
)
from app.core.services.data.storage import load_config


# <<<TOOL_NAME>>> key: value lines <<<END_TOOL_NAME>>>
_BLOCK = re.compile(
    r"<<<([A-Z][A-Z0-9_]*)>>>\s*(.*?)\s*<<<END_\1>>>",
    re.DOTALL | re.IGNORECASE,
)

# Tools handled by this harness (not the older chat blocks)
HARNESS_TOOLS = {
    "READ_FILE",
    "WRITE_FILE",
    "SEARCH_REPLACE",
    "APPLY_PATCH",
    "DELETE_FILE",
    "LIST_DIR",
    "GREP",
    "SPAWN_SUBAGENT",
    "GET_SUBAGENT",
    "PARALLEL_AGENTS",
    "GIT_STATUS",
    "GIT_DIFF",
    "GIT_LOG",
    "GIT_ADD",
    "GIT_COMMIT",
    "GIT_BRANCH",
    "BG_SHELL",
    "BG_STATUS",
    "BG_KILL",
    "TODO_WRITE",
    "TODO_READ",
    "ASK_USER",
    "PLAN_WRITE",
    "PLAN_READ",
    "ENTER_PLAN",
    "EXIT_PLAN",
    "PROJECT_RULES",
    "SANDBOX_STATUS",
    "PERMISSION_STATUS",
}


def harness_enabled() -> bool:
    return bool(load_config().get("agent_harness_enabled", True))


def harness_tool_instructions(*, compact: bool = False) -> str:
    if compact:
        return (
            "## Agent harness tools (text blocks)\n"
            "READ_FILE, WRITE_FILE, SEARCH_REPLACE, LIST_DIR, GREP, "
            "SPAWN_SUBAGENT, GIT_*, BG_SHELL, TODO_WRITE, PLAN_WRITE, ASK_USER.\n"
            "Example:\n"
            "<<<READ_FILE>>>\npath: app/main.py\noffset: 1\nlimit: 80\n<<<END_READ_FILE>>>\n"
        )
    return """
## Agent harness (Grok-style tools — ALWAYS ON with GUI)

Prefer these surgical tools over rewriting whole files via SELF_IMPROVE.

### Read / write / patch
<<<READ_FILE>>>
path: relative/or/absolute.py
offset: 1
limit: 120
<<<END_READ_FILE>>>

<<<WRITE_FILE>>>
path: notes.txt
content: full file body here
<<<END_WRITE_FILE>>>

<<<SEARCH_REPLACE>>>
path: app/foo.py
old: exact old text
new: replacement text
replace_all: false
<<<END_SEARCH_REPLACE>>>

<<<LIST_DIR>>>
path: .
<<<END_LIST_DIR>>>

<<<GREP>>>
pattern: def web_search
path: app
glob: *.py
<<<END_GREP>>>

### Subagents
<<<SPAWN_SUBAGENT>>>
prompt: Explore how chat tools work and summarize key files
type: explore
<<<END_SPAWN_SUBAGENT>>>

<<<GET_SUBAGENT>>>
id: SUBAGENT_ID
wait_ms: 60000
<<<END_GET_SUBAGENT>>>

### Parallel agents (budget + time caps)
<<<PARALLEL_AGENTS>>>
task: Research topic A with web search
task: List key files under app/services
type: explore
wait: true
<<<END_PARALLEL_AGENTS>>>

Types: general-purpose | explore (read-only) | plan
Caps: max concurrent / batch size / timeouts in Settings → Usage & budgets.

### Git
<<<GIT_STATUS>>>
<<<END_GIT_STATUS>>>

<<<GIT_DIFF>>>
staged: false
<<<END_GIT_DIFF>>>

<<<GIT_COMMIT>>>
message: fix: clarify search defaults
<<<END_GIT_COMMIT>>>

### Background shell
<<<BG_SHELL>>>
command: pytest -q
<<<END_BG_SHELL>>>

<<<BG_STATUS>>>
id: TASK_ID
wait_ms: 0
<<<END_BG_STATUS>>>

### Todos / plan / ask user
<<<TODO_WRITE>>>
items: [{"id":"1","content":"Implement X","status":"in_progress"}]
<<<END_TODO_WRITE>>>

<<<PLAN_WRITE>>>
content: # Plan\\n## Approach\\n...
<<<END_PLAN_WRITE>>>

<<<ENTER_PLAN>>>
<<<END_ENTER_PLAN>>>

<<<EXIT_PLAN>>>
approve: true
<<<END_EXIT_PLAN>>>

<<<ASK_USER>>>
question: Which approach?
options: A) patch in place; B) new module
<<<END_ASK_USER>>>

### Project rules
<<<PROJECT_RULES>>>
<<<END_PROJECT_RULES>>>

Sandbox + permission rules apply when enabled in Settings → Agent harness.
Legacy tools (TERMINAL, WEB_SEARCH, BROWSER, …) still work.
""".strip()


def _parse_body(body: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    lines = (body or "").splitlines()
    multiline_keys = {
        "content", "old", "new", "old_string", "new_string", "prompt",
        "message", "items", "text", "command", "tasks",
    }
    stop_keys = multiline_keys | {
        "path", "offset", "limit", "replace_all", "glob", "pattern", "type",
        "cwd", "id", "wait_ms", "staged", "approve", "options", "question",
        "name", "n", "max", "timeout", "multi", "merge", "subagent_type",
        "task_id", "subagent_id", "wait", "max_rounds", "i", "case_insensitive",
        "query", "q", "task",
    }
    task_list: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if ":" in line:
            k, v = line.split(":", 1)
            k = k.strip().lower()
            v = v.strip()
            # Collect repeated task: lines for PARALLEL_AGENTS
            if k == "task" and v:
                task_list.append(v)
                i += 1
                continue
            if k in multiline_keys:
                rest = [v] if v else []
                i += 1
                while i < len(lines):
                    nxt = lines[i]
                    if ":" in nxt:
                        nk = nxt.split(":", 1)[0].strip().lower()
                        if nk in stop_keys and " " not in nk:
                            break
                    rest.append(lines[i])
                    i += 1
                meta[k] = "\n".join(rest).strip()
                if k == "old":
                    meta["old_string"] = meta[k]
                if k == "new":
                    meta["new_string"] = meta[k]
                continue
            meta[k] = v
        i += 1
    if task_list:
        meta["tasks"] = task_list
        if "task" not in meta:
            meta["task"] = task_list[0]
    if not meta and body.strip():
        meta["content"] = body.strip()
    return meta


def extract_harness_blocks(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in _BLOCK.finditer(text or ""):
        name = (m.group(1) or "").upper()
        if name not in HARNESS_TOOLS:
            continue
        body = m.group(2) or ""
        args = _parse_body(body)
        # normalize tool name
        tool = name.lower()
        if tool == "apply_patch":
            tool = "search_replace"
        out.append({"tool": tool, "args": args, "raw": name})
    return out


def dispatch_named_tool(
    name: str,
    args: dict[str, Any],
    *,
    cwd: str | None = None,
    chat_id: str | None = None,
) -> dict[str, Any]:
    n = (name or "").lower().strip()
    a = {str(k).lower(): v for k, v in (args or {}).items()}

    def s(key: str, default: str = "") -> str:
        v = a.get(key, default)
        return "" if v is None else str(v)

    def b(key: str, default: bool = False) -> bool:
        v = a.get(key, default)
        if isinstance(v, bool):
            return v
        return str(v).lower() in ("1", "true", "yes", "on")

    def i(key: str, default: int = 0) -> int:
        try:
            return int(a.get(key, default))
        except Exception:  # noqa: BLE001
            return default

    try:
        if n == "read_file":
            return file_tools.read_file(s("path"), offset=i("offset", 1) or 1, limit=i("limit", 500) or 500)
        if n == "write_file":
            return file_tools.write_file(s("path"), s("content"))
        if n in ("search_replace", "apply_patch"):
            return file_tools.search_replace(
                s("path"),
                s("old_string") or s("old"),
                s("new_string") or s("new"),
                replace_all=b("replace_all"),
            )
        if n == "delete_file":
            return file_tools.delete_file(s("path"))
        if n == "list_dir":
            return file_tools.list_dir(s("path") or cwd or ".", max_entries=i("max", 200) or 200)
        if n == "grep":
            return file_tools.grep(
                s("pattern") or s("query"),
                s("path") or cwd or ".",
                glob=s("glob") or "*",
                max_matches=i("max", 80) or 80,
                case_insensitive=b("i") or b("case_insensitive"),
            )
        if n == "spawn_subagent":
            return subagent.spawn_subagent(
                s("prompt") or s("content"),
                subagent_type=s("type") or s("subagent_type") or "general-purpose",
                cwd=s("cwd") or cwd,
                max_rounds=i("max_rounds", 8) or 8,
                background=not b("wait"),
                parent_run_id=str(chat_id or ""),
            )
        if n == "get_subagent":
            return subagent.get_subagent(s("id") or s("subagent_id"), wait_ms=i("wait_ms", 0))
        if n == "parallel_agents":
            # Collect task lines from args + raw multiline
            tasks: list[Any] = []
            # task / tasks keys
            if a.get("tasks"):
                raw_t = a.get("tasks")
                if isinstance(raw_t, list):
                    tasks.extend(raw_t)
                elif isinstance(raw_t, str):
                    for line in raw_t.splitlines():
                        line = line.strip()
                        if line:
                            tasks.append(line)
            # repeated task: from body parse lands as last only — also accept content lines
            if a.get("task"):
                tasks.append(str(a.get("task")))
            if a.get("content") and not tasks:
                for line in str(a.get("content")).splitlines():
                    line = line.strip()
                    if line.lower().startswith("task:"):
                        tasks.append(line.split(":", 1)[-1].strip())
                    elif line:
                        tasks.append(line)
            stype = s("type") or s("subagent_type") or "general-purpose"
            # Apply default type to bare strings
            norm: list[Any] = []
            for t in tasks:
                if isinstance(t, str):
                    norm.append({"prompt": t, "type": stype})
                else:
                    norm.append(t)
            return subagent.spawn_parallel(
                norm,
                cwd=s("cwd") or cwd,
                max_rounds=i("max_rounds", 6) or 6,
                parent_run_id=str(chat_id or ""),
                wait=b("wait", True) if "wait" in a else True,
            )
        if n == "git_status":
            return git_tools.git_status(s("cwd") or cwd)
        if n == "git_diff":
            return git_tools.git_diff(s("cwd") or cwd, staged=b("staged"))
        if n == "git_log":
            return git_tools.git_log(s("cwd") or cwd, n=i("n", 10) or 10)
        if n == "git_add":
            paths = a.get("paths")
            if isinstance(paths, str):
                try:
                    paths = json.loads(paths)
                except json.JSONDecodeError:
                    paths = [p.strip() for p in paths.split(",") if p.strip()]
            return git_tools.git_add(paths if isinstance(paths, list) else None, s("cwd") or cwd)
        if n == "git_commit":
            return git_tools.git_commit(s("message") or s("content"), s("cwd") or cwd)
        if n == "git_branch":
            return git_tools.git_branch(s("name") or None, s("cwd") or cwd)
        if n == "bg_shell":
            return bg_tasks.start_bg_shell(s("command") or s("content"), cwd=s("cwd") or cwd)
        if n == "bg_status":
            return bg_tasks.get_task(s("id") or s("task_id"), wait_ms=i("wait_ms", 0))
        if n == "bg_kill":
            return bg_tasks.kill_task(s("id") or s("task_id"))
        if n == "todo_write":
            raw = a.get("items") or a.get("content") or "[]"
            if isinstance(raw, str):
                try:
                    items = json.loads(raw)
                except json.JSONDecodeError:
                    items = [{"id": "1", "content": raw, "status": "pending"}]
            else:
                items = raw
            return agent_todo.write_todos(list(items or []), chat_id=chat_id, merge=not b("replace"))
        if n == "todo_read":
            return {"ok": True, "todos": agent_todo.load_todos(chat_id)}
        if n == "ask_user":
            opts = a.get("options")
            if isinstance(opts, str):
                opts = [x.strip() for x in re.split(r"[;\n|]", opts) if x.strip()]
            return ask_user.ask_question(
                s("question") or s("content"),
                opts if isinstance(opts, list) else None,
                multi=b("multi"),
                timeout=float(i("timeout", 300) or 300),
            )
        if n == "plan_write":
            return plan_mode.write_plan(s("content") or s("text"), chat_id)
        if n == "plan_read":
            return plan_mode.read_plan(chat_id)
        if n == "enter_plan":
            return plan_mode.enter_plan_mode(chat_id)
        if n == "exit_plan":
            return plan_mode.exit_plan_mode(approve=b("approve", True))
        if n == "project_rules":
            return project_rules.load_rules_text(s("cwd") or cwd)
        if n == "sandbox_status":
            return sandbox.status()
        if n == "permission_status":
            return permissions.status()
        return {"ok": False, "error": f"unknown harness tool: {n}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "tool": n}


def openai_tool_schemas() -> list[dict[str, Any]]:
    """OpenAI function-calling tool definitions (full studio dual-path catalog)."""
    try:
        from app.core.services.tools.tool_schemas import studio_openai_tools

        return studio_openai_tools(include_harness=True)
    except Exception:  # noqa: BLE001
        # Minimal harness-only fallback
        def fn(
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

        return [
            fn(
                "read_file",
                "Read a file with line numbers",
                {
                    "path": {"type": "string"},
                    "offset": {"type": "integer"},
                    "limit": {"type": "integer"},
                },
                ["path"],
            ),
            fn(
                "run_terminal",
                "Run shell command",
                {"command": {"type": "string"}},
                ["command"],
            ),
            fn(
                "web_search",
                "Search the web",
                {"query": {"type": "string"}},
                ["query"],
            ),
        ]


def inject_project_context(cwd: str | None = None, chat_id: str | None = None) -> str:
    parts: list[str] = []
    if harness_enabled():
        parts.append(harness_tool_instructions())
        try:
            pr = project_rules.inject_block(cwd)
            if pr:
                parts.append(pr)
        except Exception:  # noqa: BLE001
            pass
        try:
            td = agent_todo.format_for_prompt(chat_id)
            if td:
                parts.append(td)
        except Exception:  # noqa: BLE001
            pass
        try:
            sb = sandbox.status()
            pm = permissions.status()
            parts.append(
                f"## Agent harness status\n"
                f"- sandbox: enabled={sb.get('enabled')} profile={sb.get('profile')}\n"
                f"- permissions: mode={pm.get('mode')}\n"
                f"- plan_mode: {plan_mode.is_plan_mode()}\n"
            )
        except Exception:  # noqa: BLE001
            pass
    return "\n\n".join(parts)


def run_harness_from_reply(
    reply: str,
    *,
    cwd: str | None = None,
    chat_id: str | None = None,
    allow_tool: Callable[[str, str, str], bool] | None = None,
    emit: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    """
    Execute all harness tool blocks in reply.
    Returns list of {tool, result} for injection into history.
    """
    if not harness_enabled():
        return []
    results: list[dict[str, Any]] = []
    for block in extract_harness_blocks(reply):
        tool = block["tool"]
        args = block["args"]
        summary = f"{tool} {json.dumps(args, ensure_ascii=False)[:120]}"
        # hooks PreToolUse
        hr = hooks.run_hooks(
            "PreToolUse",
            payload={"tool": tool, "args": args, "chat_id": chat_id},
        )
        if hr.get("blocked"):
            results.append(
                {
                    "tool": tool,
                    "result": {"ok": False, "error": f"hook blocked: {hr.get('reason')}"},
                }
            )
            if emit:
                emit(f"hook blocked {tool}")
            continue
        # permissions
        dec = permissions.evaluate(tool, summary, json.dumps(args)[:500])
        if dec.get("decision") == "deny":
            results.append({"tool": tool, "result": {"ok": False, "error": dec.get("reason"), "denied": True}})
            if emit:
                emit(f"denied {tool}: {dec.get('reason')}")
            continue
        # Always consult allow_tool when provided (chat approvals + plan filter)
        if allow_tool:
            try:
                ok_allow = allow_tool(tool, summary, json.dumps(args)[:500])
            except Exception:  # noqa: BLE001
                ok_allow = True
            if not ok_allow:
                results.append(
                    {
                        "tool": tool,
                        "result": {"ok": False, "error": "not allowed / rejected", "denied": True},
                    }
                )
                continue
        elif dec.get("decision") == "ask":
            results.append(
                {
                    "tool": tool,
                    "result": {
                        "ok": False,
                        "error": "ask mode: no approval callback",
                        "denied": True,
                    },
                }
            )
            continue
        if emit:
            emit(f"harness {tool}")
        res = dispatch_named_tool(tool, args, cwd=cwd, chat_id=chat_id)
        hooks.run_hooks(
            "PostToolUse",
            payload={"tool": tool, "args": args, "result_ok": bool(res.get("ok")), "chat_id": chat_id},
        )
        results.append({"tool": tool, "result": res})
    return results
