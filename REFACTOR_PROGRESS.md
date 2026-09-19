# Refactor progress — split large pages

## Status (2026-09-19 — round 2)

| Module | Lines | Notes |
|--------|------:|-------|
| page_router.py | ~70 | **NEW** — show_page builders extracted |
| models_page.py | ~204 | thinned; advanced panel extracted |
| models_advanced.py | ~702 | **NEW** — profiles/Ollama/train lab |
| chats_page.py | ~510 | **NEW** — extracted from mgmt_pages |
| mgmt_pages.py | ~505 | memory/projects/company/ceo/workflow only |
| app_window.py | ~4500 | uses page_builders(); still large |
| team/org_chart | done | prior turn |

## Tests / CI
- `tests/test_refactor_smoke.py` covers all ensure targets + new modules + key symbols
- CI runs on `main` and `refactor/**`; materialize + py_compile + unittest

## Launch.bat
Still only: click Launch.bat → ensure materializes stubs.

## Still optional later
- Further chat_* splits (misc/render still 1.8k–2.2k)
- Service-layer splits (chat.py, web_search.py)
- Merge branch to main after Windows smoke
