# Refactor progress — split AppWindow god class

## Status

| Metric | Before | After (local) |
|--------|--------|---------------|
| `app/ui/app_window.py` lines | **20,438** | **~5,195** |
| Reduction | | **~75%** |

## Extracted modules

### Pages (`app/ui/pages/`)
home, help, about, knowledge, approvals, usage, agents, schedule, work_board,
settings (~1600 lines), chat (~1200 lines), track, patches, tasks

### Components (`app/ui/components/`)
system_monitor, status_bar, navigation,
chat_render, chat_dialogs, chat_rail, chat_send, chat_thinking, chat_misc,
chat_voice, chat_panels, chat_cycle_bar, sidebar_build, window_lifecycle,
page_helpers, artifacts_panel, command_palette, diff_viewer, settings_helpers

## Remaining in AppWindow
- `_init_ui` (~228 lines) — shell bootstrap
- `show_page` (~146 lines) — router
- Thin wrappers that delegate to extracted modules
- Smaller methods still being moved

## Next
1. Push all module files to this branch
2. Push thinned app_window.py
3. Windows GUI smoke test
4. Finish `_init_ui` / `show_page` extraction
