# Control plane (Paperclip-inspired)

Studio’s **control plane** implements Paperclip’s product concepts in Python
(desktop + local JSON). We reimplement ideas under MIT-compatible design;
we do **not** copy Paperclip’s Node/React source.

## Paperclip → Studio mapping

| Paperclip concept | Studio API |
|-------------------|------------|
| Company | `create_company` / `ensure_default_company` / `update_company` |
| Agent + org chart | `hire_agent` / `org_chart` / `pause_agent` / `resume_agent` |
| Task + goal path | `create_task` (stores `goal_path`) / `checkout_task` / blockers |
| Heartbeat | `run_heartbeat` / `tick_heartbeats` |
| Budget (80% warn, 100% stop) | `budget_ok` / `budget_warn` / `record_spend` |
| Adapter | `adapters.execute_adapter` (`studio_builtin`, `process`, `http`) |
| Approvals / board | `list_pending_approvals` / `resolve_approval` / `request_strategy_approval` |
| Activity / runs | `list_activity` / `list_runs` / `dashboard` |

## Data

JSON under `data/control_plane/` (companies, agents, tasks, runs, activity, approvals).

## Quick start

```python
from app.core.services.control_plane import service as cp

co = cp.ensure_default_company()
ceo = cp.hire_agent(co["id"], name="CEO", title="Chief Executive", role="ceo",
                    budget_monthly_cents=6000, heartbeat_interval_sec=120)
task = cp.create_task(co["id"], title="Draft Q1 strategy", assignee_id=ceo["id"])
cp.tick_heartbeats(co["id"])
print(cp.dashboard(co["id"]))
```

## What is intentionally different from full Paperclip

- Desktop CustomTkinter UI + local JSON (not React + Postgres)
- Adapters: `studio_builtin` / `process` / `http` (hook Claude Code / Codex via `process` or webhooks)
- No cloud multi-tenant auth mode yet
- No Gmail/Calendar Connectors product surface yet

Those can be added on the same control-plane API.
