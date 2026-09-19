# Refactor progress — split large pages

## Status (2026-09-19)

| Module | Lines (full) | Payload chunks | Installer | Stub + ensure | Remote |
|--------|-------------|----------------|-----------|---------------|--------|
| team_page | 1362 | z00–z15 (16) | install_team_page_v1.py | yes | done |
| team_dialogs | 398 | z00–z03 (4) | install_team_dialogs_v1.py | yes | done |
| org_chart_widgets | 428 | z00–z05 (6) | install_org_chart_widgets_v1.py | yes | done |
| org_chart_view | 766 | z00–z08 (9) | install_org_chart_view_v1.py | yes | done |
| mgmt_pages | 991 | z00–z11 (12) | install_mgmt_pages_v1.py | yes | done |
| models_page | 884 | z00–z10 (11) | install_models_page_v1.py | yes | done |

## How Launch.bat works
1. `app/main.py` calls `ensure_refactor_modules()`
2. Any stub (<5KB or Bootstrap header) is materialized from `scripts/refactor_payload/*.b64`
3. User only clicks Launch.bat — no manual install scripts needed

## Pending
- None for large-page split of team/org_chart/mgmt/models
- Optional: further sub-split of mgmt_pages (memory/projects/company/ceo) and models advanced panel
