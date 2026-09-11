# AI Agent Studio — Pending improvement tasks

**Source:** market research + product audit (2026)  
**Rule:** Execute **one task at a time** → test/debug → mark done → next.  
**Status:** `pending` | `in_progress` | `done` | `blocked` | `skipped`

Last updated: 2026-09-11 · App version: **1.27.84**  
*(Tasks #1–15 done at 1.26.x; #16 audit log done at 1.27.82; #17 Offline Ollama done at 1.27.83; #18 Voice done at 1.27.84; #19 tray done at 1.27.81. Next sequential task is #20.)*

---

## Execution order (do in sequence)

| # | Task | Priority | Status | Notes |
|---|------|----------|--------|-------|
| 1 | Direct xAI Grok as primary agent path (console.x.ai key, no OpenRouter required) | P0 | **done** | 1.25.3–1.25.4 · activate prefer xai · repair mismatch · tests |
| 2 | Provider/model **health check** button + structured errors with next actions | P0 | **done** | `_test_active_llm_connection` · Settings + Grok bar |
| 3 | **Token/cost meter** before send (and per team run) | P0 | **done** | `estimate_request_budget` on composer · live while typing |
| 4 | **Risk tiers** for PC tools: Read-only / Ask / Full | P0 | **done** | Chip + Settings · maps plan/ask/auto + sandbox |
| 5 | Home **preset modes**: Research / Control PC / Code / Team | P0 | **done** | `home_presets` · Home buttons · 1.25.5 |
| 6 | Team: **living plan** + always one clean final user answer | P0 | **done** | living_plan + clean_team_final_text · 1.25.6 |
| 7 | **Chat-with-folder** + RAG **citations** always clickable | P0 | **done** | Folder button · file:// links · 1.25.7 |
| 8 | **Diff view** when agent edits files | P1 | **done** | unified diff + chips · 1.25.8 |
| 9 | **Pause/resume** long agent runs + background jobs | P1 | **done** | Chat Pause + Team Pause · 1.25.9 |
| 10 | Installer / **auto-update** or clear version-check UX | P1 | **done** | About/Settings version check · 1.26.0 |
| 11 | Prompt library / system presets per project | P1 | **done** | presets + project bind · 1.26.0 |
| 12 | Artifacts panel (files/images/reports this turn) | P1 | **done** | Live → Artifacts · 1.26.1 |
| 13 | Global hotkey: ask about clipboard/selection | P1 | **done** | Ctrl+Shift+G · 1.26.1 |
| 14 | Parallel agents with budget/time caps | P1 | **done** | PARALLEL_AGENTS + caps · 1.26.2 |
| 15 | Sandbox / cwd lock per chat | P1 | **done** | cwd lock 🔒 · 1.26.2 |
| 16 | Export audit log of all tool calls | P1 | **done** | 1.27.82 · `audit_log` · Settings export JSON/CSV |
| 17 | Offline Ollama path clearly labeled | P1 | **done** | 1.27.83 · `ollama_local` · Offline · Ollama (local) |
| 18 | Voice in/out first-class | P2 | **done** | 1.27.84 · Settings Voice · mic/speak · soft-degrade |
| 19 | System tray + run in background | P2 | **done** | 1.27.81 · pystray Show/Hide/Quit · start minimized |
| 20 | Optional Grok CLI session reuse (if product/legal allows) | P2 | pending | Research first |

---

## Done log

| # | Task | Version | Date |
|---|------|---------|------|
| 18 | Voice in/out first-class | 1.27.84 | 2026-09-11 |
| 17 | Offline Ollama path clearly labeled | 1.27.83 | 2026-09-11 |
| 19 | System tray + run in background | 1.27.81 | 2026-09-11 |
| 16 | Export audit log of all tool calls | 1.27.82 | 2026-09-11 |
| 14–15 | Parallel agents + cwd lock sandbox | 1.26.2 | 2026-08-05 |
| 12–13 | Artifacts panel · global clipboard hotkey | 1.26.1 | 2026-08-05 |
| 10–11 | Version check UX · prompt library | 1.26.0 | 2026-08-05 |
| 9 | Pause/resume chat + team runs | 1.25.9 | 2026-08-05 |
| 8 | Diff view for agent file edits | 1.25.8 | 2026-08-05 |
| 7 | Chat-with-folder + clickable RAG citations | 1.25.7 | 2026-08-05 |
| 6 | Team living plan + clean final answer | 1.25.6 | 2026-08-05 |
| 5 | Home preset modes Research/PC/Code/Team | 1.25.5 | 2026-08-05 |
| 1–4 | xAI primary · health check · token meter · risk tiers | 1.25.4 | 2026-08-05 |
| — | GUI Batches 1–3 | 1.24.x | prior |
| — | Use Grok / routing fixes | 1.25.0–1.25.3 | prior |

---

## Current focus

**Next sequential task:** **#20** — Optional Grok CLI session reuse (research first).

**App head:** **1.27.84** (Voice #18 · see CHANGELOG).

---

## Test checklist (per task)

- [x] Code change compiles / imports (#1–4)
- [x] Scripted happy path (`tests/test_pending_tasks_01_04.py`)
- [x] Failure path shows clear message (402 / need_key / risk deny)
- [x] Version + CHANGELOG updated (1.25.4)
- [x] Mark tasks 1–4 `done` in this file
