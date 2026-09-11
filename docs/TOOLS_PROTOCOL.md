# LLM Tools Protocol

Tool calls are **text blocks** in the assistant message. The app parses them after each reply (**Action** mode only).

Source of live instructions: `capability_manual.py` + each `*_instructions()` in services.

---

## Dual path (both always work)

| Path | How the model calls tools | How the app runs them |
|------|---------------------------|------------------------|
| **A — Text blocks** | `<<<TERMINAL>>>…<<<END_TERMINAL>>>` | Parsed directly by extractors |
| **B — Native OpenAI tools** | API `tools` + `tool_calls` (`run_terminal`, `web_search`, …) | Execute via harness + continue with `role:tool` (`tool_call_id`); also converted → text blocks |
| **C — JSON / XML in content** | `{"terminal":"…"}`, `<tool_call>…` | `tool_normalizer` → text blocks |

Why models often pick B/C: they are trained on OpenAI function calling and XML wrappers.
The studio **sends full tool schemas** in Action mode when **Prefer native OpenAI tool calls** is on (Settings, default ON) so native tool_calls are valid,
keeps structured `tool_calls` on the assistant message, appends `role:tool` results, and **always normalizes** content before execution so JSON/text blocks still work when the provider
does not support tools (retry without `tools` is automatic).

Pipeline: API response → `ensure_executable_tool_format` (+ raw `tool_calls`) → `normalize_tool_calls` → extractors → `append_native_tool_results` → next LLM turn.

---

## Modes

| Mode | Tools execute? |
|------|----------------|
| **plan** | No — plan only |
| **action** | Yes |

---

## Block catalog

### Terminal

```
<<<TERMINAL>>>
Get-ChildItem
<<<END_TERMINAL>>>
```

### Skill load

```
<<<SKILL>>>
skill-name-or-path
<<<END_SKILL>>>
```

### MCP

```
<<<MCP>>>
server.tool_name
{"arg": "value"}
<<<END_MCP>>>
```

### Screenshot / GUI / Clipboard / Windows

```
<<<SCREENSHOT>>>
optional_name
<<<END_SCREENSHOT>>>

<<<GUI>>>
[{"action":"click","x":10,"y":10}]
<<<END_GUI>>>

<<<CLIPBOARD>>>
get
<<<END_CLIPBOARD>>>

<<<WINDOWS>>>
list
<<<END_WINDOWS>>>
```

### Show existing media in chat

```
<<<IMAGE>>>
C:\path\to\file.png
<<<END_IMAGE>>>

<<<VIDEO>>>
C:\path\to\file.mp4
<<<END_VIDEO>>>
```

### Generate new image (API — required for “draw a picture”)

```
<<<IMAGE_GEN>>>
1024x1024
cute orange cat, soft studio lighting
<<<END_IMAGE_GEN>>>
```

**Do not** substitute SVG/HTML/ASCII when the user wants a generated picture.

### Browser (portable Chromium)

```
<<<BROWSER>>>
action: screenshot
url: https://example.com
<<<END_BROWSER>>>
```

### Web search

```
<<<WEB_SEARCH>>>
query text
<<<END_WEB_SEARCH>>>
```

### Agent harness (Grok-style — v1.15+)

Surgical file / repo / subagent tools. Prefer these over whole-file SELF_IMPROVE when editing code.

```
<<<READ_FILE>>>
path: app/services/chat.py
offset: 1
limit: 80
<<<END_READ_FILE>>>

<<<WRITE_FILE>>>
path: notes.txt
content: full body
<<<END_WRITE_FILE>>>

<<<SEARCH_REPLACE>>>
path: app/foo.py
old: exact old text
new: replacement
<<<END_SEARCH_REPLACE>>>

<<<LIST_DIR>>>
path: app/services
<<<END_LIST_DIR>>>

<<<GREP>>>
pattern: def send_user_message
path: app
glob: *.py
<<<END_GREP>>>

<<<SPAWN_SUBAGENT>>>
prompt: Explore how web_search works
type: explore
<<<END_SPAWN_SUBAGENT>>>

<<<GIT_STATUS>>>
<<<END_GIT_STATUS>>>

<<<BG_SHELL>>>
command: pytest -q
<<<END_BG_SHELL>>>

<<<TODO_WRITE>>>
items: [{"id":"1","content":"Do X","status":"in_progress"}]
<<<END_TODO_WRITE>>>

<<<PLAN_WRITE>>>
content: # Plan
## Approach
...
<<<END_PLAN_WRITE>>>

<<<ASK_USER>>>
question: Which option?
options: A; B; C
<<<END_ASK_USER>>>
```

Settings → **Agent harness**: permission mode, sandbox, hooks.  
Headless: `python studio_agent.py -p "…" --json`

### OCR

```
<<<OCR>>>
optional_image_path
<<<END_OCR>>>
```

### Knowledge

```
<<<KNOWLEDGE>>>
action: search
query: ...
<<<END_KNOWLEDGE>>>
```

### Patch review (queued for user)

```
<<<PATCH_REVIEW>>>
path: app/services/example.py
mode: write
note: ...
---
file content
<<<END_PATCH_REVIEW>>>
```

### Self-improve (direct, backed up)

```
<<<BACKUP>>>
reason: ...
<<<END_BACKUP>>>

<<<SELF_IMPROVE>>>
path: app/services/example.py
mode: write
note: ...
---
full file content
<<<END_SELF_IMPROVE>>>

<<<ROLLBACK>>>
backup_id_or_empty_for_latest
<<<END_ROLLBACK>>>
```

See [SELF_IMPROVE.md](SELF_IMPROVE.md).

---

## Approvals & budgets

- If **Tool approval** is ON, risky tools wait on **Approvals** page.  
- Budgets: `tool_budget.py` limits per-run tool counts.  
- Safety switch may further restrict laptop/terminal.

---

## Selection guide

| User need | Prefer |
|-----------|--------|
| Generate picture | **IMAGE_GEN** |
| Show existing file | IMAGE / VIDEO |
| Shell / files | TERMINAL |
| See screen | SCREENSHOT |
| Click/type apps | GUI |
| Web facts | WEB_SEARCH |
| Browse page | BROWSER |
| Code change (safe) | PATCH_REVIEW |
| Code change (fast) | SELF_IMPROVE |
| Org multi-agent | Company / workflow, not fake subagents |

---

## Grok parity (summary)

This is **not** the Grok Build TUI. Native: terminal, IMAGE_GEN, WEB_SEARCH, skills, MCP, browser, RAG, company queue.  
Host-only elsewhere: spawn_subagent, .rhai workflows — use closest alternatives above.
