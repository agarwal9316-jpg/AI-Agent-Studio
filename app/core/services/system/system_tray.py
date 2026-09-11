"""System tray + run in background (PENDING #19).

Uses pystray + Pillow when available (Windows-first; soft-degrades elsewhere).
Tray menu: Show / Hide / Quit. Config: system_tray_enabled, start_minimized,
close_to_tray, minimize_to_tray.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Any, Callable

from app.core.services.data.storage import load_config, save_config
from app.paths import app_root
from app.version import APP_NAME, __version__

_lock = threading.Lock()
_icon: Any = None
_running = False
_callbacks: dict[str, Callable[[], None] | None] = {
    "show": None,
    "hide": None,
    "quit": None,
}


def is_supported() -> bool:
    """True when pystray can be imported (tray works best on Windows)."""
    try:
        import pystray  # noqa: F401
        from PIL import Image  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        return False


def tray_enabled() -> bool:
    cfg = load_config()
    return bool(cfg.get("system_tray_enabled", True))


def set_tray_enabled(on: bool) -> None:
    cfg = load_config()
    cfg["system_tray_enabled"] = bool(on)
    save_config(cfg)


def start_minimized() -> bool:
    return bool(load_config().get("start_minimized", False))


def set_start_minimized(on: bool) -> None:
    cfg = load_config()
    cfg["start_minimized"] = bool(on)
    save_config(cfg)


def close_to_tray() -> bool:
    cfg = load_config()
    # Default on when tray feature is enabled
    return bool(cfg.get("close_to_tray", True))


def set_close_to_tray(on: bool) -> None:
    cfg = load_config()
    cfg["close_to_tray"] = bool(on)
    save_config(cfg)


def minimize_to_tray() -> bool:
    cfg = load_config()
    return bool(cfg.get("minimize_to_tray", True))


def set_minimize_to_tray(on: bool) -> None:
    cfg = load_config()
    cfg["minimize_to_tray"] = bool(on)
    save_config(cfg)


def should_use_tray() -> bool:
    return is_supported() and tray_enabled()


def set_callbacks(
    *,
    show: Callable[[], None] | None = None,
    hide: Callable[[], None] | None = None,
    quit_app: Callable[[], None] | None = None,
) -> None:
    with _lock:
        if show is not None:
            _callbacks["show"] = show
        if hide is not None:
            _callbacks["hide"] = hide
        if quit_app is not None:
            _callbacks["quit"] = quit_app


def _emit(name: str) -> None:
    with _lock:
        fn = _callbacks.get(name)
    if fn:
        try:
            fn()
        except Exception:  # noqa: BLE001
            pass


def _icon_image():
    """Build a simple tray icon (Pillow). Prefer branding pack, then assets/tray_icon.png."""
    from PIL import Image, ImageDraw

    try:
        from app.core.services.system import branding as _branding

        branded = _branding.tray_icon_path()
        if branded is not None and branded.is_file():
            return Image.open(branded).convert("RGBA")
    except Exception:  # noqa: BLE001
        pass
    assets = app_root() / "assets" / "tray_icon.png"
    if assets.is_file():
        try:
            return Image.open(assets).convert("RGBA")
        except Exception:  # noqa: BLE001
            pass
    # 64x64 indigo tile with white "A"
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((2, 2, size - 3, size - 3), radius=14, fill=(99, 102, 241, 255))
    # Simple "A" mark without depending on a font file
    draw.polygon(
        [(32, 14), (18, 50), (24, 50), (28, 38), (36, 38), (40, 50), (46, 50)],
        fill=(255, 255, 255, 255),
    )
    draw.rectangle((27, 30, 37, 34), fill=(99, 102, 241, 255))
    return img


def ensure_tray_icon_asset() -> Path:
    """Write assets/tray_icon.png if missing (portable / first run)."""
    out = app_root() / "assets" / "tray_icon.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.is_file():
        return out
    try:
        img = _icon_image()
        img.save(out, format="PNG")
    except Exception:  # noqa: BLE001
        pass
    return out


def start() -> bool:
    """Start the tray icon in a daemon thread. Idempotent."""
    global _icon, _running
    if not should_use_tray():
        return False
    with _lock:
        if _running and _icon is not None:
            return True
        try:
            import pystray
            from pystray import MenuItem as Item

            ensure_tray_icon_asset()
            image = _icon_image()

            def on_show(icon=None, item=None) -> None:  # noqa: ANN001, ARG001
                _emit("show")

            def on_hide(icon=None, item=None) -> None:  # noqa: ANN001, ARG001
                _emit("hide")

            def on_quit(icon=None, item=None) -> None:  # noqa: ANN001, ARG001
                _emit("quit")

            menu = pystray.Menu(
                Item("Show", on_show, default=True),
                Item("Hide", on_hide),
                pystray.Menu.SEPARATOR,
                Item("Quit", on_quit),
            )
            icon = pystray.Icon(
                "ai_agent_studio",
                image,
                f"{APP_NAME} v{__version__}",
                menu,
            )
            _icon = icon
            _running = True

            def _run() -> None:
                global _running
                try:
                    icon.run()
                except Exception:  # noqa: BLE001
                    pass
                finally:
                    _running = False

            t = threading.Thread(target=_run, daemon=True, name="system-tray")
            t.start()
            return True
        except Exception:  # noqa: BLE001
            _icon = None
            _running = False
            return False


def stop() -> None:
    """Stop the tray icon (call on real quit)."""
    global _icon, _running
    with _lock:
        icon = _icon
        _icon = None
        _running = False
    if icon is not None:
        try:
            icon.stop()
        except Exception:  # noqa: BLE001
            pass


def notify(title: str, message: str) -> None:
    """Optional balloon/notification if the backend supports it."""
    with _lock:
        icon = _icon
    if icon is None:
        return
    try:
        icon.notify(message, title)
    except Exception:  # noqa: BLE001
        pass


def status() -> dict[str, Any]:
    return {
        "supported": is_supported(),
        "enabled": tray_enabled(),
        "running": _running,
        "start_minimized": start_minimized(),
        "close_to_tray": close_to_tray(),
        "minimize_to_tray": minimize_to_tray(),
        "platform": sys.platform,
        "should_use": should_use_tray(),
    }
