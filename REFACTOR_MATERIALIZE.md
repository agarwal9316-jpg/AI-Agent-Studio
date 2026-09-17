# Materialize extracted modules

## Status (2026-09-17)

- Branch: `refactor/split-god-class`
- Goal: replace god-class `app_window.py` (~20k lines) with focused modules.
- **Local recovery tarball** has the full good tree (thinned app_window + all chat/settings modules).
- Some original zlib payloads on the branch were corrupted during push; use verified v2 payloads or the FULL tarball.

## One module this turn: chat_thinking

```bash
git pull origin refactor/split-god-class
python scripts/install_chat_thinking_v2.py
# writes app/ui/components/chat_thinking.py (~37 KB)
```

Remaining modules to materialize next (same pattern): chat_rail, chat_send, chat_dialogs, chat_render, chat_misc, chat_page, settings_page, app_window.

## Wiring

Thinned `app_window.py` already uses lazy imports, e.g.:

```python
from app.ui.components.chat_thinking import ...
from app.ui.pages.chat_page import page_chat
```

After materializing all modules, launch via normal entrypoint and smoke-test Chat + Settings.
