"""
Ensure native LLM tools are ready (playwright + portable Chromium + pypdf).

Called automatically by Launch.bat before starting the GUI.
If already installed under ./browsers, returns immediately.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def app_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def browsers_dir() -> Path:
    d = app_root() / "browsers"
    d.mkdir(parents=True, exist_ok=True)
    return d


def chromium_installed() -> bool:
    root = browsers_dir()
    for p in root.rglob("chrome.exe"):
        if p.is_file():
            return True
    for p in root.rglob("chrome"):
        if p.is_file():
            return True
    return False


def playwright_importable() -> bool:
    try:
        import playwright  # noqa: F401

        return True
    except ImportError:
        return False


def pypdf_importable() -> bool:
    try:
        import pypdf  # noqa: F401

        return True
    except ImportError:
        return False


def is_ready() -> bool:
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_dir().resolve())
    return playwright_importable() and chromium_installed() and pypdf_importable()


def _pip_install() -> int:
    req = app_root() / "requirements.txt"
    cmd = [sys.executable, "-m", "pip", "install", "-q"]
    if req.is_file():
        cmd += ["-r", str(req)]
    else:
        cmd += ["playwright>=1.40.0", "pypdf>=4.0.0", "customtkinter>=5.2.0", "Pillow>=10.0.0", "pyautogui>=0.9.54"]
    print("Installing Python packages…")
    return subprocess.call(cmd)


def _install_chromium() -> int:
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_dir().resolve())
    print("Installing portable Chromium into:", browsers_dir())
    env = {**os.environ, "PLAYWRIGHT_BROWSERS_PATH": str(browsers_dir().resolve())}
    return subprocess.call(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        env=env,
    )


def ensure(*, force: bool = False) -> int:
    """
    If native tools missing (or force), install them.
    Returns 0 on success / already ready, non-zero on failure.
    """
    root = app_root()
    os.chdir(root)
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_dir().resolve())

    if not force and is_ready():
        print("Native tools OK (playwright + Chromium + pypdf).")
        return 0

    print("Native tools not ready — setting up (one-time)…")
    if not playwright_importable() or not pypdf_importable() or force:
        code = _pip_install()
        if code != 0:
            print("ERROR: pip install failed")
            return code

    if not chromium_installed() or force:
        code = _install_chromium()
        if code != 0:
            print("ERROR: playwright install chromium failed")
            return code

    if is_ready():
        print("Native tools ready.")
        return 0

    print("WARNING: setup finished but readiness check still failed.")
    print("  playwright:", playwright_importable())
    print("  chromium: ", chromium_installed())
    print("  pypdf:    ", pypdf_importable())
    print("  path:     ", browsers_dir())
    # Do not block GUI launch — browser tool will show error if used
    return 0


def main() -> int:
    force = "--force" in sys.argv
    return ensure(force=force)


if __name__ == "__main__":
    raise SystemExit(main())
