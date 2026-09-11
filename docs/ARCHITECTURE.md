# Architecture (as built)

**Version:** 1.27.18 (package layout stamp; see `app/version.py`)  
**Source of truth for runtime structure.** Parent Stage-A ADRs are summarized and extended here.

---

## 1. Locked decisions (ADR)

| ID | Decision | Choice | Status |
|----|----------|--------|--------|
| ADR-001 | Platform | Windows 10/11 desktop | Locked |
| ADR-002 | Distribution | Portable folder (no MSI required) | Locked |
| ADR-003 | Language | Python 3.11+ | Locked |
| ADR-004 | GUI | CustomTkinter | Locked |
| ADR-005 | Packaging | PyInstaller **onedir** | Locked |
| ADR-006 | Data location | `./data` next to app root / exe | Locked |
| ADR-007 | Persistence | JSON files + SQLite for RAG | Locked |
| ADR-008 | Agent model | name, role, goal, backstory | Locked |
| ADR-009 | Task model | description, expected_output, agent_id | Locked |
| ADR-010 | Run model | sequential tasks + transcript | Locked |
| ADR-011 | LLM | OpenAI-compatible HTTP (stdlib urllib) | Locked |
| ADR-012 | Frameworks | Study only; no hard AutoGen/CrewAI dep | Locked |
| ADR-013 | Flow canvas | Simplified workflow **tree** (not full Langflow) | Locked |
| ADR-014 | Continuity | README + Launch + **docs/** | Locked |
| ADR-015 | Launch | **Launch.bat** mandatory primary entry | Locked |
| ADR-016 | Browser | Portable Playwright browsers under `./browsers` | Locked |
| ADR-017 | Self-improve | Backup zip + path allowlist + compile rollback | Locked |
| ADR-018 | Chat UI | Message-first + visible mode/caps bar + ⋯ overflow | Locked |
| ADR-019 | Themes | Explicit high-contrast `themes.UI` palette | Locked |

---

## 2. Package layout

```
app/
  __main__.py          # python -m app
  main.py              # bootstrap
  paths.py             # app_root(), data_dir()
  version.py           # __version__, APP_NAME
  ui/
    app_window.py      # main window, Chat, most pages
    mgmt_pages.py      # CEO / company helpers
    org_page.py        # Organisation page (lists + panel + AI create UI)
    org_chart_view.py  # visual tree, pan, expand/collapse, connectors
    org_worker_dialogs.py  # configure / remove / move / inspector
  services/            # domain + tools (see module table)
    workflow_graph.py  # multi-graph org store + hierarchy ops
    org_ai.py          # LLM designs org tree + worker prompts (long timeout)
    app_log.py         # JSON-line logs under data/logs/
    chat_store.py      # multi-chat index + delete/pin/reorder
  tools/
    ensure_native.py   # Launch-time Chromium/playwright setup
    setup_native.py
```

---

## 3. Runtime flow — Chat send

```
User Send
  → chat_svc path in services/chat.py
  → build system: default/system prompt
                 + capability_manual (operator manual)
                 + live catalog (skills/MCP switches)
                 + tool instruction blocks (IMAGE_GEN, BROWSER, …)
                 + optional RAG hybrid block
                 + image-intent nudge when detected
  → llm.stream / complete (providers.resolve_active_llm)
  → on each assistant reply (Action mode):
       parse tool blocks → execute → append tool messages → loop
  → persist chat_store · usage_meter · agent_tracker / activity_log
```

**Plan mode** skips tool execution after the model reply.

---

## 4. Runtime flow — Company worker

```
CEO goal / workflow / scheduler
  → company_store work_tasks
  → orchestrator kick (background thread)
  → approval_mode manual | auto
  → agent LLM runs with role prompts
  → results in tasks / project_outputs / activity
Chat UI remains free (not blocked by worker).
```

---

## 5. Service module map

| Service | Role |
|---------|------|
| `chat.py` | Main chat tool loop |
| `chat_store.py` | Multi-chat JSON |
| `llm.py` | Completions + stream + trim |
| `providers.py` | Multi-provider config |
| `capability_manual.py` | Operator manual + parity matrix |
| `terminal_tool.py` | PowerShell |
| `laptop_control.py` | GUI / screenshot / clipboard / windows |
| `browser_tool.py` | Headless Chromium |
| `image_gen.py` | Images API |
| `media_chat.py` | IMAGE/VIDEO render + download |
| `web_search.py` | DuckDuckGo-style search |
| `ocr_service.py` | Screen/file OCR |
| `rag_knowledge.py` | FTS RAG |
| `local_embeddings.py` | Hybrid re-rank |
| `skills_registry.py` | Discover/enable skills |
| `mcp_client.py` / `mcp_marketplace.py` | MCP |
| `self_improve.py` / `patch_review.py` | Code change safety |
| `company_store.py` / `orchestrator.py` | Company AI |
| `workflow_graph.py` | Org/workflow tree |
| `tool_approvals.py` / `tool_budget.py` | Gates |
| `scheduler_service.py` | Schedules |
| `themes.py` | UI contrast palette |
| `storage.py` | config.json |

---

## 6. Paths

| Helper | Meaning |
|--------|---------|
| `app_root()` | Project root (dev) or folder next to exe (portable) |
| `data_dir()` | `app_root()/data` |

All user state must stay under `data/` for portability.

---

## 7. Threading model

| Thread | Work |
|--------|------|
| Tk main | UI only |
| Chat worker | LLM + tools for current send |
| Orchestrator | Company background tasks |
| Optional watchers | Clipboard / folder (deferred, non-blocking) |

UI updates use `after(0, …)`.

---

## 8. Security notes

- Tool approval can gate terminal/GUI/pip/MCP/self_improve.
- Self-improve allowlist: `app/`, select root files; never `data/`, `.venv/`.
- API keys in `data/config.json` / `providers.json` (local only).
- Do not log full secrets in activity export.

---

## 9. Packaging

- Dev: `Launch.bat` → `.venv\Scripts\python.exe -m app`
- Build: `build_portable.ps1` → `dist/AI-Agent-Studio/`
- Entry: `entry.py` → PyInstaller
- Native browsers: `ensure_native` on Launch when missing

See [LAUNCH.md](LAUNCH.md).
