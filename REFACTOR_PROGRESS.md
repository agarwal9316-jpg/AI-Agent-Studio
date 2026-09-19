# Refactor progress — split large pages

## Status (2026-09-19 — complete push)

| Module | Payload chunks | Installer | Remote decompress |
|--------|----------------|-----------|-------------------|
| team_page | z00–z15 | install_team_page_v1.py | needs integrity pass |
| team_dialogs | z00–z03 | install_team_dialogs_v1.py | needs integrity pass |
| org_chart_widgets | z00–z05 | install_org_chart_widgets_v1.py | **OK** |
| org_chart_view | z00–z08 | install_org_chart_view_v1.py | **OK** |
| mgmt_pages | z00–z05 | install_mgmt_pages_v1.py | **OK** |
| models_page | z00–z02 | install_models_page_v1.py | **OK** |
| models_advanced | z00–z08 | install_models_advanced_v1.py | needs integrity pass |
| chats_page | z00–z06 | install_chats_page_v1.py | **OK** |
| page_router / chats extract | prior | — | done |
| app_window / chat_* | prior | — | done |

## Launch.bat
Click **Launch.bat** only. `ensure_refactor_modules()` runs installers for any stub modules.

## Next (optional integrity)
Re-push team_page, team_dialogs, models_advanced last-chunk content if materialize fails; otherwise merge to main after Windows smoke.
