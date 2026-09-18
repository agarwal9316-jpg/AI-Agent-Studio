"""Application entry — called by Launch.bat via python -m app."""

from __future__ import annotations

import sys
import traceback
from datetime import datetime
from pathlib import Path


def _write_error_log(text: str) -> Path | None:
    try:
        # Prefer portable data next to project root
        if getattr(sys, "frozen", False):
            root = Path(sys.executable).resolve().parent
        else:
            root = Path(__file__).resolve().parent.parent
        data = root / "data"
        data.mkdir(parents=True, exist_ok=True)
        path = data / "last_launch_error.txt"
        path.write_text(
            f"{datetime.now().isoformat()}\n{text}\n",
            encoding="utf-8",
        )
        return path
    except OSError:
        return None


def _show_error_dialog(message: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("AI Agent Studio — failed to start", message)
        root.destroy()
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    # Launch progress bar — created as early as possible so the user sees the
    # app is starting even while Python imports customtkinter/themes and while
    # the (heavy) main window builds its pages.
    splash = None
    try:
        from app.ui.components.launch_progress import LaunchProgress

        splash = LaunchProgress()
        splash.stage("Preparing…", 5)
    except Exception:  # noqa: BLE001
        splash = None

    try:
        from app.paths import data_dir, app_root
        from app.core.services.data.storage import load_config
        from app._ensure_refactor_modules import ensure_refactor_modules, needs_materialize

        if splash is not None and needs_materialize():
            splash.stage("Preparing interface modules…", 15)
        ensure_refactor_modules(quiet=True)

        from app.ui.app_window import run_app

        if splash is not None:
            splash.stage("Loading configuration…", 25)
        data_dir()  # ensure portable data folder
        # Portable Chromium path for LLM browser tool (before any playwright import)
        try:
            import os
            from pathlib import Path

            bdir = app_root() / "browsers"
            bdir.mkdir(parents=True, exist_ok=True)
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(bdir.resolve())
        except Exception:  # noqa: BLE001
            pass
        if splash is not None:
            splash.stage("Loading configuration…", 45)
        load_config()
        if splash is not None:
            splash.stage("Starting interface…", 65)
        # run_app builds the AppWindow, closes the splash, then starts mainloop.
        run_app(splash)
        return 0
    except Exception as exc:  # noqa: BLE001 — show launch errors clearly
        tb = traceback.format_exc()
        print("AI Agent Studio failed to start.", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        print(tb, file=sys.stderr)
        print()
        print("Tips:")
        print("  1. Use Launch.bat (not a broken shortcut)")
        print("  2. .venv\\Scripts\\pip install -r requirements.txt")
        print("  3. Read data\\last_launch_error.txt")
        if splash is not None:
            try:
                splash.close()
            except Exception:  # noqa: BLE001
                pass
        log_path = _write_error_log(f"{exc}\n\n{tb}")
        detail = f"{exc}\n\nSee also:\n{log_path or 'console output'}"
        _show_error_dialog(detail)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
