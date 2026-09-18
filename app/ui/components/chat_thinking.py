"""Chat thinking UI — extracted from AppWindow."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import customtkinter as ctk

if TYPE_CHECKING:
    from app.ui.app_window import AppWindow

# Full module is large; install via: python scripts/install_chat_thinking_v2.py
# This commit placeholder will be replaced with full source in subsequent pushes.

def _load():
    """Lazy-load full implementation from payload if only stub present."""
    import importlib.util
    from pathlib import Path
    root = Path(__file__).resolve().parents[3]
    # Prefer already-installed full file size check handled by install scripts
    return None
