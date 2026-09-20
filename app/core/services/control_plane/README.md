# Control plane (Paperclip-inspired)

Studio’s **control plane** mirrors Paperclip’s product concepts without copying
their Node/React codebase (MIT allows reuse of *ideas*; we reimplemented in Python).

## Concepts

| Paperclip | Studio module |
|-----------|----------------|
| Company | `service.create_company` / `ensure_default_company` |
| Agent + org chart | `hire_agent` / `org_chart` |
| Task + goal path | `create_task` (stores `goal_path`) |
| Heartbeat | `run_heartbeat` / `tick_heartbeats` |
| Budget | `record_spend` / `budget_ok` |
| Adapter | `adapters.execute_adapter` (`studio_builtin`, `process`, `http`) |
| Activity / runs | `list_activity` / `list_runs` / `dashboard` |

## Data

JSON under `data/control_plane/` (companies, agents, tasks, runs, activity).

## Usage

```python
from app.core.services.control_plane import service as cp

co = cp.ensure_default_company()
cp.create_task(co["id"], title="Research competitors", description="…")
cp.tick_heartbeats(co["id"])  # wakes due agents
print(cp.dashboard(co["id"]))
```

## What is *not* a full Paperclip clone

- No React web UI / Postgres (Studio stays desktop + local JSON)
- No full Claude Code / Codex / Cursor session adapters (use `process` / `http` to hook them)
- No Gmail/Calendar Connectors product yet
- No multi-tenant authenticated cloud mode

Those can be added incrementally on this same control-plane API.
