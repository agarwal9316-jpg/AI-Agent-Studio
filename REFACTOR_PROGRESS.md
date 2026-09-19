# Refactor progress — split large pages

## Status (2026-09-19 — post-merge improvements)

| Module | Status | Notes |
|--------|--------|-------|
| page_router.py | done | show_page builders extracted; lazy imports for heavy pages |
| models_page / models_advanced | done | advanced panel extracted |
| chats_page / mgmt_pages | done | memory/projects vs chats split |
| team_page / team_dialogs | done | message card + goal dialog extracted |
| org_chart_view / widgets | done | WorkerCard helpers extracted |
| org_page / org_page_ai | done | AI callbacks extracted |
| chat_* components | done | thinking/rail/send/dialogs/render/misc |
| app_window.py | ~4500 | uses page_builders(); still large but functional |
| ensure + Launch.bat | done | clone → Launch.bat auto-materializes |

## Reliability (this pass)

- `app/_ensure_refactor_modules.py` — clearer errors, `data/last_materialize.txt` health log, `materialize_status()` for diagnostics
- `scripts/smoke_launch.py` — headless materialize + py_compile (Windows-safe)
- CI — payload decompress integrity check + smoke_launch
- `tests/test_refactor_smoke.py` — payload decompress tests

## How to run

1. `git clone https://github.com/agarwal9316-jpg/AI-Agent-Studio.git`
2. Double-click **Launch.bat** (or `python scripts/smoke_launch.py` for headless check)
3. First run materializes stubs from `scripts/refactor_payload/*.b64` automatically

## Optional later

- Further thin `app_window.py` (window chrome / lifecycle helpers)
- Service splits: `chat.py` (~2.8k), `web_search.py` (~2.4k)
- Remove legacy single-digit payload leftovers (`*.z0.b64` …) once only `*_v2.zNN` / zero-padded sets are used
- Lazy-import remaining heavy service modules on first use
