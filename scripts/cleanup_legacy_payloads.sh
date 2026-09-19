#!/usr/bin/env bash
# Remove legacy single-digit payload chunks (safe if already gone).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
P="$ROOT/scripts/refactor_payload"
rm -f "$P"/app_window.z[0-9].b64 "$P"/app_window.z1[0-2].b64
rm -f "$P"/chat_dialogs.z[0-9].b64 "$P"/chat_misc.z[0-9].b64
rm -f "$P"/chat_page.z[0-9].b64 "$P"/chat_rail.z[0-9].b64
rm -f "$P"/chat_render.z[0-9].b64 "$P"/chat_send.z[0-9].b64
rm -f "$P"/chat_thinking.z[0-9].b64 "$P"/settings_page.z[0-9].b64
echo "Legacy payload cleanup done. Remaining:"
ls "$P" | wc -l
