# Data model & layout

**Root:** `data/` next to app (dev project root or portable exe folder).  
**Helper:** `app.paths.data_dir()`.  
**App version:** 1.27.14 (docs stamp; runtime from `app/version.py`).

---

## 1. Directory tree

```
data/
  config.json              # global settings
  providers.json           # multi-provider LLM configs
  mcp.json                 # MCP server definitions
  usage.json               # usage meter
  schedules.json           # scheduled jobs
  watch_folders.json       # knowledge folder watches
  pending_patches.json     # patch review queue
  agent_runs.json          # agent tracker summary
  agents/*.json
  tasks/*.json
  runs/*.json
  chats/
    index.json             # active_id + chats[] meta (title, pinned, list_order, message_count)
    current.json           # legacy pointer
    <chat_id>.json         # full messages + flags
  company/
    org.json               # includes approval_mode
    goals/*.json
    work_tasks/*.json
    approvals/
    workflow_graphs.json   # multi org charts (see § Org graphs)
  team_channels/           # Team workspace feeds
  projects/*.json
  project_outputs/<project_id>/
  memory/memory.json
  knowledge/rag.sqlite
  backups/self_improve/*.zip + *.json
  chat_media/<chat_id>/
  generated_images/<chat_id>/
  browser_shots/
  screenshots/
  exports/
  last_launch_error.txt    # if Launch fails
```

### Org graphs (`company/workflow_graphs.json`)

```json
{
  "active_id": "<graph-uuid>",
  "graphs": [
    {
      "id": "...",
      "name": "Test SWAT",
      "source": "ai",
      "org_kind": "Rapid-response unit",
      "ai_rationale": "...",
      "nodes": [
        {
          "id": "ceo",
          "type": "ceo|department|agent",
          "title": "CEO",
          "parent_id": null,
          "order": 0,
          "instructions": "",
          "agent_id": "",
          "agent_role": "",
          "agent_goal": "",
          "system_prompt": "",
          "worker_prompt": "",
          "llm_model": "",
          "enabled": true,
          "status": "idle"
        }
      ]
    }
  ]
}
```

- AI create (`org_ai`) fills `system_prompt` / `worker_prompt` and links `agents/*.json` profiles.
- Export strips secrets (`export_graph_safe`).
- Diagnostics: `data/logs/app.log`, `data/logs/org_ai.log` (JSON lines via `app.services.app_log`).

---

## 2. Core entities

### Agent (`agents/<id>.json`)

```text
id, name, role, goal, backstory?, created_at, …
```

### Task (`tasks/<id>.json`)

```text
id, name, description, expected_output, agent_id, created_at, …
```

### Run (`runs/<id>.json`)

```text
id, status, messages[], task_ids[], created_at, …
```

### Chat (`chats/<id>.json`)

```text
id, title, pinned?, messages[], agent_id?,
terminal_enabled, skills_enabled, mcp_enabled,
laptop_enabled, use_workflow_graph, safety_mode,
mode: "plan"|"action",
system_prompt?, model_params?, …
```

### Config (`config.json` keys — common)

| Key | Meaning |
|-----|---------|
| `api_key` / provider keys | LLM auth |
| `api_base_url` | Completions base |
| `model` | Default chat model |
| `image_model` | e.g. dall-e-3 |
| `stream_replies` | Streaming on/off |
| `tool_approval_required` | Gate risky tools |
| `ui_theme` | Theme name |
| `approval_mode` | mirrored with company org |
| `auto_save_results_to_project` | Project outputs |

### Company org

```text
approval_mode: "manual" | "auto"
departments / roles as stored by company_store
```

### Work task

```text
id, title, role_id, description, status,
auto_approved?, …
```

---

## 3. RAG

- Store: `knowledge/rag.sqlite` (FTS)
- Optional vectors via `local_embeddings`
- Watch list: `watch_folders.json`

---

## 4. Backups (self-improve)

- Zip + meta JSON under `backups/self_improve/`
- Created before `SELF_IMPROVE` write
- Rollback by id or latest

---

## 5. Portability rules

1. Never hardcode absolute machine paths in saved data when relative works.  
2. User may delete entire `data/` to reset.  
3. Do not put secrets in docs or git if publishing.  
4. `browsers/` is large binary cache — not under `data/` but portable next to app.

---

## 6. Reset

Close app → delete `data/` (and optionally `browsers/` to re-download Chromium).
