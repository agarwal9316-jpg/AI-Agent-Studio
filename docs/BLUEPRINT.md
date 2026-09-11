# Product Blueprint — AI Agent Studio

**Status:** As-built through **v1.7.8**  
**Platform:** Windows 10/11 portable desktop  
**Stack:** Python 3.11+ · CustomTkinter · OpenAI-compatible LLM · local JSON/SQLite data  

---

## 1. Vision

A **portable multi-agent studio** you double-click on Windows:

- Chat with a real tool-using operator (terminal, browser, laptop GUI, skills, MCP).
- Run a **company** of background roles (CEO goals, PM → Engineer → QA, approvals).
- Keep **all state next to the app** (`./data`) so a USB copy works.
- Stay **honest** about capabilities (not a Grok Build host clone).

Inspired by AutoGen / CrewAI / Dify / Langflow **patterns only** — original code, not a clone.

---

## 2. Primary user journeys

| Journey | Path |
|---------|------|
| Daily chat | Launch.bat → Chat → Action mode → Send |
| Image from text | Chat Action → `IMAGE_GEN` or Ctrl+G |
| Company work | CEO → goal / Run plan → Approvals (or Tasks=auto) |
| Knowledge Q&A | Knowledge → index → ask in Chat (RAG inject) |
| Safe code change | Chat → PATCH_REVIEW → Patches page Apply |
| Direct self-edit | Chat → SELF_IMPROVE (backed up) → restart if UI |
| Portable handoff | `build_portable.ps1` → zip `dist\AI-Agent-Studio\` |

---

## 3. System layers

```
┌─────────────────────────────────────────────────────────┐
│  UI (app/ui)  CustomTkinter pages + chat chrome         │
├─────────────────────────────────────────────────────────┤
│  Chat orchestration (app/services/chat.py)              │
│  · system prompt + operator manual + tool catalog       │
│  · stream / stop · tool loop · media                    │
├─────────────────────────────────────────────────────────┤
│  Tools (services/*)  terminal · browser · image · RAG   │
│  laptop · MCP · skills · web · OCR · self-improve …     │
├─────────────────────────────────────────────────────────┤
│  Company (orchestrator + company_store + workflow_graph)│
├─────────────────────────────────────────────────────────┤
│  LLM (llm.py + providers.py)  OpenAI-compatible HTTP    │
├─────────────────────────────────────────────────────────┤
│  Data (paths.py → ./data)  JSON · SQLite RAG · backups  │
└─────────────────────────────────────────────────────────┘
```

---

## 4. Product modules (blueprint map)

| Module | Responsibility | Key code |
|--------|----------------|----------|
| Chat | Multi-chat, stream, tools, modes | `ui/app_window.py`, `services/chat.py` |
| Providers | OpenAI / OpenRouter / custom | `services/providers.py` |
| Terminal | PowerShell cwd + blocks | `services/terminal_tool.py` |
| Laptop | Screenshot / GUI / clipboard / windows | `services/laptop_control.py` |
| Browser | Portable Playwright Chromium | `services/browser_tool.py`, `./browsers` |
| Image gen | `/images/generations` | `services/image_gen.py` |
| Knowledge | FTS + local embeddings | `services/rag_knowledge.py` |
| Skills / MCP | Playbooks + stdio MCP | `skills_registry`, `mcp_*` |
| Company | Goals, tasks, approvals, workers | `company_store`, `orchestrator` |
| Workflow graph | Org tree + Flow canvas | `workflow_graph.py`, `flow_canvas.py`, Org chart UI |
| Approvals | Tool + company queues | `tool_approvals`, CEO page |
| Self-improve | Backup / patch / rollback | `self_improve.py` |
| Schedule | Timed company tasks | `scheduler_service.py` |
| Themes | High-contrast UI palette | `themes.py` |
| Launch | venv + optional native setup | `Launch.bat`, `tools/ensure_native.py` |

---

## 5. Modes & safety

| Control | Meaning |
|---------|---------|
| **plan** | Plan only; tool blocks not executed |
| **action** | Full tool loop |
| **Tasks manual/auto** | Company queue needs CEO click or not |
| **Tool approval** | Risky tools wait on Approvals page |
| **Safety limits** | Extra restrictions when ON (default often OFF) |
| **Terminal / Skills / MCP / Laptop / Workflow** | Per-chat capability switches |

---

## 6. Non-goals (honest)

| Not in this app | Closest alternative |
|-----------------|---------------------|
| Grok host `spawn_subagent` | Multiple chats / company roles / terminal |
| Grok `.rhai` workflows | Workflow graph + company queue |
| Full Langflow canvas clone | Workflow tree + optional richer Flow canvas (CustomTkinter; not Electron) |
| Silent self-heal of every bad reply | Explicit SELF_IMPROVE / user request |

---

## 7. Continuity principle

A person can open the project **months later** and continue using only:

1. Root `README.md` → Resume  
2. `docs/` (this tree)  
3. `Launch.bat`  

No chat history required. See [CONTINUITY.md](CONTINUITY.md).

---

## 8. Related docs

- Architecture detail → [ARCHITECTURE.md](ARCHITECTURE.md)  
- Feature checklist → [FEATURES.md](FEATURES.md)  
- Tool syntax → [TOOLS_PROTOCOL.md](TOOLS_PROTOCOL.md)  
- Parent stage checklists → [EXTERNAL.md](EXTERNAL.md)  
