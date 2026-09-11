"""Text-to-speech for chat (Windows-friendly)."""

from __future__ import annotations

import threading
from typing import Any


def speak_text(text: str, *, async_play: bool = True) -> dict[str, Any]:
    """Speak text using pyttsx3 if available, else Windows SAPI via powershell."""
    text = (text or "").strip()
    if not text:
        return {"ok": False, "error": "Empty text"}
    # keep short for TTS
    if len(text) > 2500:
        text = text[:2500] + "…"

    def _run() -> dict[str, Any]:
        try:
            import pyttsx3  # type: ignore

            eng = pyttsx3.init()
            eng.say(text)
            eng.runAndWait()
            return {"ok": True, "engine": "pyttsx3"}
        except Exception:
            pass
        try:
            import subprocess

            # Escape for PowerShell single-quoted string
            safe = text.replace("'", "''")
            ps = (
                "Add-Type -AssemblyName System.Speech; "
                "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                f"$s.Speak('{safe}')"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                capture_output=True,
                timeout=120,
            )
            return {"ok": True, "engine": "System.Speech"}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    if async_play:
        threading.Thread(target=_run, daemon=True).start()
        return {"ok": True, "engine": "async"}
    return _run()
