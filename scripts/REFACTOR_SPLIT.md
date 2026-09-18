# AppWindow god-class split

Branch: `refactor/split-god-class`

## Modules extracted

| Module | Path | Role |
|--------|------|------|
| chat_thinking | `app/ui/components/chat_thinking.py` | Thinking UI / stream bubbles |
| chat_rail | `app/ui/components/chat_rail.py` | Chat rail / goal banner |
| chat_send | `app/ui/components/chat_send.py` | Send / auto-continue |
| chat_dialogs | `app/ui/components/chat_dialogs.py` | Chat dialogs / wizards |
| chat_render | `app/ui/components/chat_render.py` | Message rendering |
| chat_misc | `app/ui/components/chat_misc.py` | Misc chat helpers |
| chat_page | `app/ui/pages/chat_page.py` | Chat page builder |
| settings_page | `app/ui/pages/settings_page.py` | Settings page |
| app_window | `app/ui/app_window.py` | Thin host (~4.5k lines) with lazy imports |

## Materialize from payloads (if modules missing)

```bash
python scripts/install_all_refactor_v2.py
```

This prefers `fix_*_v2.py` (payload typo patches) when present, else `install_*_v2.py`.

## Wiring

`app_window.py` uses lazy imports, e.g.:

- `from app.ui.components.chat_rail import build_chat_view_bar`
- `from app.ui.components.chat_send import maybe_auto_continue_task`
- `from app.ui.components.chat_dialogs import open_findings_window`
- `from app.ui.pages.chat_page import ...`
- `from app.ui.pages.settings_page import ...`

## Verify

```bash
python -m py_compile app/ui/app_window.py \
  app/ui/components/chat_*.py \
  app/ui/pages/chat_page.py \
  app/ui/pages/settings_page.py
```
