"""Optional icons / branding pack (roadmap 1.28.2).

Looks under ``assets/branding/`` next to the app root. Soft-degrades when
files are missing — never raises into the UI path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.paths import app_root

# Canonical filenames (see docs/BRANDING.md)
ICON_SIZES = (256, 64, 32)
PNG_NAMES = {s: f"app_icon_{s}.png" for s in ICON_SIZES}
LOGO_SVG = "logo.svg"
TRAY_PNG = "tray_icon.png"
APP_ICO = "app_icon.ico"


def branding_dir() -> Path:
    return app_root() / "assets" / "branding"


def pack_present() -> bool:
    """True when the branding directory exists and has at least one PNG icon."""
    d = branding_dir()
    if not d.is_dir():
        return False
    for name in PNG_NAMES.values():
        if (d / name).is_file():
            return True
    return False


def icon_png(size: int) -> Path | None:
    """Return path to ``app_icon_{size}.png`` if present."""
    name = PNG_NAMES.get(int(size))
    if not name:
        # Allow any positive size file if named conventionally
        name = f"app_icon_{int(size)}.png"
    p = branding_dir() / name
    return p if p.is_file() else None


def best_icon_png(preferred: int = 256) -> Path | None:
    """Pick the closest available PNG (prefer ``preferred`` size)."""
    direct = icon_png(preferred)
    if direct is not None:
        return direct
    # Prefer larger first for quality when downscaling
    for size in sorted(ICON_SIZES, reverse=True):
        p = icon_png(size)
        if p is not None:
            return p
    d = branding_dir()
    if d.is_dir():
        for p in sorted(d.glob("app_icon_*.png")):
            if p.is_file():
                return p
    return None


def logo_svg() -> Path | None:
    p = branding_dir() / LOGO_SVG
    return p if p.is_file() else None


def ico_path() -> Path | None:
    p = branding_dir() / APP_ICO
    return p if p.is_file() else None


def tray_icon_path() -> Path | None:
    """Prefer branding tray, then legacy ``assets/tray_icon.png``."""
    p = branding_dir() / TRAY_PNG
    if p.is_file():
        return p
    legacy = app_root() / "assets" / "tray_icon.png"
    return legacy if legacy.is_file() else None


def status() -> dict[str, Any]:
    d = branding_dir()
    icons = {str(s): (icon_png(s) is not None) for s in ICON_SIZES}
    return {
        "dir": str(d),
        "present": pack_present(),
        "icons": icons,
        "logo_svg": logo_svg() is not None,
        "ico": ico_path() is not None,
        "tray": tray_icon_path() is not None,
        "best_png": str(best_icon_png() or ""),
    }


def load_pil_image(size: int = 256):
    """Open a branding PNG as RGBA Pillow image, or None."""
    try:
        from PIL import Image
    except Exception:  # noqa: BLE001
        return None
    path = best_icon_png(size)
    if path is None:
        return None
    try:
        img = Image.open(path).convert("RGBA")
        if img.size != (size, size):
            img = img.resize((size, size), Image.Resampling.LANCZOS)
        return img
    except Exception:  # noqa: BLE001
        return None


def apply_window_icon(window: Any) -> bool:
    """Set Tk/CTk window icon from branding pack. Soft-degrades on failure."""
    if window is None or not pack_present():
        return False
    applied = False
    # Windows .ico via iconbitmap when available
    ico = ico_path()
    if ico is not None:
        try:
            window.iconbitmap(default=str(ico))
            applied = True
        except Exception:  # noqa: BLE001
            try:
                window.iconbitmap(str(ico))
                applied = True
            except Exception:  # noqa: BLE001
                pass
    # Cross-platform PhotoImage (PNG)
    try:
        from PIL import Image, ImageTk

        path = best_icon_png(64) or best_icon_png(256) or best_icon_png(32)
        if path is None:
            return applied
        img = Image.open(path).convert("RGBA")
        # Keep a reference on the window so Tk does not GC the image
        photo = ImageTk.PhotoImage(img)
        window._branding_icon_photo = photo  # noqa: SLF001
        try:
            window.iconphoto(True, photo)
            applied = True
        except Exception:  # noqa: BLE001
            try:
                window.tk.call("wm", "iconphoto", window._w, photo)
                applied = True
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass
    return applied


def ctk_brand_image(size: int = 48):
    """Return a CTkImage for About / Home brand mark, or None."""
    try:
        import customtkinter as ctk
        from PIL import Image
    except Exception:  # noqa: BLE001
        return None
    path = best_icon_png(256) or best_icon_png(64) or best_icon_png(32)
    if path is None:
        return None
    try:
        im = Image.open(path).convert("RGBA")
        if im.size != (size, size):
            im = im.resize((size, size), Image.Resampling.LANCZOS)
        return ctk.CTkImage(light_image=im, dark_image=im, size=(size, size))
    except Exception:  # noqa: BLE001
        return None
