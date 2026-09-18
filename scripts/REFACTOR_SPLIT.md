# AppWindow god-class split (merged to main)

## Launch

Double-click **Launch.bat**. No extra steps.

On first run, the app auto-materializes extracted modules from verified payloads
(`app/_ensure_refactor_modules.py`). Later runs skip that (~1ms check).

## Modules

| Module | Path |
|--------|------|
| chat_thinking | `app/ui/components/chat_thinking.py` |
| chat_rail | `app/ui/components/chat_rail.py` |
| chat_send | `app/ui/components/chat_send.py` |
| chat_dialogs | `app/ui/components/chat_dialogs.py` |
| chat_render | `app/ui/components/chat_render.py` |
| chat_misc | `app/ui/components/chat_misc.py` |
| chat_page | `app/ui/pages/chat_page.py` |
| settings_page | `app/ui/pages/settings_page.py` |
| app_window (thin host) | `app/ui/app_window.py` |

## Manual materialize (optional)

```bash
python -m app._ensure_refactor_modules
```
