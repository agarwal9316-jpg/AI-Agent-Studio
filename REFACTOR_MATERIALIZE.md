# Materialize extracted modules (v2)

Branch: `refactor/split-god-class`

## One command (after all payloads are on the branch)

```bash
git pull origin refactor/split-god-class
python scripts/install_all_refactor_v2.py
```

## Per-module

```bash
python scripts/install_chat_thinking_v2.py   # DONE payloads z00-z03
python scripts/install_chat_rail_v2.py
python scripts/install_chat_send_v2.py
python scripts/install_chat_dialogs_v2.py
python scripts/install_chat_render_v2.py
python scripts/install_chat_misc_v2.py
python scripts/install_chat_page_v2.py
python scripts/install_settings_page_v2.py
python scripts/install_app_window_v2.py
```

## Status

| Module | Payload chunks | Status |
|--------|----------------|--------|
| chat_thinking | z00-z03 (4) | **COMPLETE on branch** |
| chat_rail | 5 | pending push |
| chat_send | 5 | pending push |
| chat_dialogs | 6 | pending push |
| chat_render | 7 | pending push |
| chat_misc | 8 | pending push |
| chat_page | 5 | pending push |
| settings_page | 6 | pending push |
| app_window | 15 | pending push |

Installers for all modules are already on the branch.
