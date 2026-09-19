# Refactor progress — split large pages

## Status (2026-09-19 — service helpers + hygiene)

| Module | Status | Notes |
|--------|--------|-------|
| page_router.py | done | lazy imports for heavy pages |
| models / chats / mgmt / team / org_chart | done | extracted |
| chat_* UI components | done | thinking/rail/send/dialogs/render/misc |
| **chat_display.py** | **NEW** | strip/hide tool markup helpers (from chat.py) |
| **web_search_rank.py** | **NEW** | rank/dedupe/URL cleanup (from web_search.py) |
| ensure + Launch.bat | done | clone → Launch.bat auto-materializes |
| legacy single-digit payloads | cleaning | prefer `*_v2.zNN` / zero-padded only |

## Reliability

- `data/last_materialize.txt` health log
- `scripts/smoke_launch.py` headless check
- CI: payload decompress integrity

## How to run

1. `git clone https://github.com/agarwal9316-jpg/AI-Agent-Studio.git`
2. Double-click **Launch.bat** (or `python scripts/smoke_launch.py`)
3. First run materializes stubs automatically

## Optional later

- Thin `app_window.py` further (~4500 lines)
- Finish deleting remaining legacy `*.zN.b64` (single-digit) when v2 sets exist
- Point `chat.py` / `web_search.py` fully at the new helper modules (re-export only)
