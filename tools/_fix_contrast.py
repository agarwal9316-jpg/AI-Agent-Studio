"""One-shot: replace text_color='gray' with high-contrast theme muted."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INJECT = """
from app.services.themes import UI as _THEME_UI

_HC_MUTED = _THEME_UI["muted"]
_HC_LABEL = _THEME_UI["label"]
"""

FILES = [
    ROOT / "app" / "ui" / "app_window.py",
    ROOT / "app" / "ui" / "mgmt_pages.py",
    ROOT / "app" / "ui" / "org_page.py",
]


def main() -> None:
    for path in FILES:
        text = path.read_text(encoding="utf-8")
        count = text.count('text_color="gray"')
        text = text.replace('text_color="gray"', "text_color=_HC_MUTED")
        if "_HC_MUTED" not in text.split("class ")[0] if "class " in text else text[:3000]:
            # inject after customtkinter import
            needle = "import customtkinter as ctk\n"
            if needle in text and "_HC_MUTED" not in text[:3500]:
                text = text.replace(needle, needle + INJECT + "\n", 1)
        path.write_text(text, encoding="utf-8")
        print(f"{path.name}: replaced {count} gray labels")


if __name__ == "__main__":
    main()
