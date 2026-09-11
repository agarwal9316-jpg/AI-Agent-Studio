"""Global hotkeys (Windows) — ask about clipboard / selection (Task #13).

Uses Win32 RegisterHotKey + a message pump thread (no extra pip deps).
Default: Ctrl+Shift+G → ask about current clipboard text.
"""

from __future__ import annotations

import sys
import threading
import time
from typing import Any, Callable

from app.core.services.data.storage import load_config, save_config

_lock = threading.Lock()
_thread: threading.Thread | None = None
_running = False
_listener: Callable[[dict[str, Any]], None] | None = None

# Win32
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
VK_G = 0x47
VK_V = 0x56
VK_Q = 0x51

HOTKEY_CLIPBOARD = 1  # Ctrl+Shift+G
HOTKEY_CLIPBOARD_ALT = 2  # Ctrl+Shift+Q (fallback / second)


def is_supported() -> bool:
    return sys.platform.startswith("win")


def hotkeys_enabled() -> bool:
    cfg = load_config()
    return bool(cfg.get("global_hotkeys_enabled", True))


def set_hotkeys_enabled(on: bool) -> None:
    cfg = load_config()
    cfg["global_hotkeys_enabled"] = bool(on)
    save_config(cfg)


def hotkey_labels() -> list[str]:
    return [
        "Ctrl+Shift+G — Ask about clipboard",
        "Ctrl+Shift+Q — Ask about clipboard (alternate)",
    ]


def set_listener(fn: Callable[[dict[str, Any]], None] | None) -> None:
    global _listener
    with _lock:
        _listener = fn


def _emit(ev: dict[str, Any]) -> None:
    with _lock:
        fn = _listener
    if fn:
        try:
            fn(ev)
        except Exception:  # noqa: BLE001
            pass


def _read_clipboard() -> str:
    try:
        from app.core.services.system.clipboard_watch import _read_clipboard_text

        return _read_clipboard_text() or ""
    except Exception:  # noqa: BLE001
        return ""


def _pump() -> None:
    """Register hotkeys and pump messages until stop."""
    global _running
    if not is_supported():
        _running = False
        return
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        # RegisterHotKey(hWnd, id, fsModifiers, vk)
        mods = MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT
        ok1 = user32.RegisterHotKey(None, HOTKEY_CLIPBOARD, mods, VK_G)
        ok2 = user32.RegisterHotKey(None, HOTKEY_CLIPBOARD_ALT, mods, VK_Q)
        if not ok1 and not ok2:
            _emit({"type": "error", "error": "RegisterHotKey failed (maybe already in use)"})
            _running = False
            return

        class MSG(ctypes.Structure):
            _fields_ = [
                ("hwnd", wintypes.HWND),
                ("message", wintypes.UINT),
                ("wParam", wintypes.WPARAM),
                ("lParam", wintypes.LPARAM),
                ("time", wintypes.DWORD),
                ("pt", wintypes.POINT),
            ]

        msg = MSG()
        while _running:
            # Use PeekMessage so we can exit cleanly
            has = user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1)  # PM_REMOVE=1
            if has:
                if msg.message == WM_HOTKEY:
                    wid = int(msg.wParam)
                    if wid in (HOTKEY_CLIPBOARD, HOTKEY_CLIPBOARD_ALT):
                        text = _read_clipboard()
                        _emit(
                            {
                                "type": "ask_clipboard",
                                "hotkey_id": wid,
                                "text": text,
                                "label": "Ctrl+Shift+G" if wid == HOTKEY_CLIPBOARD else "Ctrl+Shift+Q",
                            }
                        )
                else:
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
            else:
                time.sleep(0.05)
        user32.UnregisterHotKey(None, HOTKEY_CLIPBOARD)
        user32.UnregisterHotKey(None, HOTKEY_CLIPBOARD_ALT)
    except Exception as e:  # noqa: BLE001
        _emit({"type": "error", "error": str(e)})
    finally:
        _running = False


def start() -> bool:
    """Start global hotkey pump if enabled and on Windows."""
    global _running, _thread
    if not is_supported():
        return False
    if not hotkeys_enabled():
        return False
    with _lock:
        if _running:
            return True
        _running = True
        _thread = threading.Thread(target=_pump, daemon=True, name="global-hotkeys")
        _thread.start()
    return True


def stop() -> None:
    global _running
    _running = False


def status() -> dict[str, Any]:
    return {
        "supported": is_supported(),
        "enabled": hotkeys_enabled(),
        "running": _running,
        "labels": hotkey_labels(),
    }
