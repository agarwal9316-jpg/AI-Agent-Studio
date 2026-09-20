# Control plane (Paperclip-inspired)

Studio's **control plane** mirrors Paperclip's product concepts without copying
their Node/React/Postgres codebase (MIT allows reuse of *ideas*; reimplemented in Python).

Source of truth for Paperclip concepts used here:
- https://github.com/paperclipai/paperclip (`doc/PRODUCT.md`, schema under `packages/db/src/schema/`)
- Docs: companies, agents, tasks, heartbeats, budgets (80% soft / 100% hard), approvals, adapters

## Concepts

| Paperclip | Studio module |
|-----------|----------------|
| Company | `service.create_company` / `ensure_default_company` |
| Agent + org chart | `hire_agent` / `org_chart` |
| Task + goal path | `create_task` (stores `goal_path`) |
| Atomic checkout / release | `checkout_task` / `release_task` |
| Heartbeat | `run_heartbeat` / `tick_heartbeats` |
| Wake on assignment / approval | `wake_pending` flag |
| Budget soft 80% / hard 100% | `budget_warn` / `budget_ok` + `pause_reason=budget` |
| Cost events (provider/model/tokens) | `store.append_cost_event` / `list_cost_events` |
| Monthly budget reset | `reset_monthly_budgets` |
| Adapter | `adapters.execute_adapter` (`studio_builtin`, `process`, `http`) |
| Activity / runs | `list_activity` / `list_runs` / `dashboard` |
| Board approvals | hire + strategy; `resolve_approval` |

## Data

JSON under `data/control_plane/` (companies, agents, tasks, runs, activity, approvals, **cost_events**).

## What was upgraded from Paperclip source analysis (2026-09)

Verified against Paperclip PRODUCT.md + public schema inventory (not invented):

1. **Cost events ledger** — provider, model, input/output tokens, cost_cents
2. **pause_reason** on agents (`budget` | `board` | `error` | `manual`)
3. **Hard stop** sets `status=budget_exceeded` + `pause_reason=budget`
4. **Soft alert** at 80% (`BUDGET_SOFT_ALERT_RATIO`)
5. **release_task** after checkout
6. **wake_pending** on task assignment and approval resolution
7. **reset_monthly_budgets** for `budget_window=monthly_utc`
8. **terminated** agent status (no more heartbeats)

## What is *not* a full Paperclip clone (honest)

- No React web UI / Postgres (Studio stays desktop + local JSON)
- No full Claude Code / Codex / Cursor session adapters (use `process` / `http`)
- No Gmail/Calendar Connectors product
- No multi-tenant authenticated cloud mode
- No native Paperclip Runner / skill studio / ClipHub templates

Those remain Paperclip strengths. Studio's edge is **integrated desktop LLM + tools + zero extra server**.

## Usage

```python
from app.core.services.control_plane import service as cp

co = cp.ensure_default_company()
cp.create_task(co["id"], title="Research competitors", description="…")
cp.tick_heartbeats(co["id"])  # wakes due + wake_pending agents
print(cp.dashboard(co["id"]))
print(cp.list_cost_events(co["id"]))
```
