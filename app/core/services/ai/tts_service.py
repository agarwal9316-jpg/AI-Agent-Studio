"""Text-to-speech for chat — cross-platform, optional deps.

Engines: pyttsx3 → Windows SAPI → Linux espeak/spd-say / macOS say.
Supports stop + capability probe. Soft-degrades when no speakers/engine.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import threading
from typing import Any

_lock = threading.Lock()
_stop = threading.Event()
_speak_thread: threading.Thread | None = None
_last_engine: str = ""


def _strip_for_speech(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    t = re.sub(r"```[\s\S]*?```", " (code block) ", t)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    t = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    t = re.sub(r"[#*_>~]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def tts_capability() -> dict[str, Any]:
    engines: list[str] = []
    detail = ""
    try:
        import pyttsx3  # type: ignore  # noqa: F401

        engines.append("pyttsx3")
    except Exception:  # noqa: BLE001
        pass

    if sys.platform == "win32":
        engines.append("System.Speech")

    for cmd in ("espeak-ng", "espeak", "spd-say", "say"):
        if shutil.which(cmd):
            engines.append(cmd)

    available = bool(engines)
    if not available:
        detail = (
            "No TTS engine found. Optional: pip install pyttsx3 "
            "(Windows also has System.Speech; Linux: espeak-ng)."
        )
    else:
        detail = "engines: " + ", ".join(engines)
    return {
        "available": available,
        "engines": engines,
        "platform": sys.platform,
        "detail": detail,
        "hint": "" if available else "Install pyttsx3 or a system speech synthesizer.",
    }


def is_speaking() -> bool:
    return bool(_speak_thread and _speak_thread.is_alive() and not _stop.is_set())


def stop_speaking() -> None:
    global _speak_thread
    _stop.set()
    with _lock:
        _speak_thread = None


def speak_text(
    text: str,
    *,
    async_play: bool = True,
    max_chars: int = 2500,
) -> dict[str, Any]:
    global _speak_thread, _last_engine

    cap = tts_capability()
    if not cap.get("available"):
        return {
            "ok": False,
            "error": cap.get("detail") or "TTS unavailable",
            "hint": cap.get("hint") or "",
            "degraded": True,
            "engine": "none",
        }

    cleaned = _strip_for_speech(text)
    if not cleaned:
        return {"ok": False, "error": "Empty text"}
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars] + "…"

    def _run() -> dict[str, Any]:
        _stop.clear()
        try:
            import pyttsx3  # type: ignore

            if _stop.is_set():
                return {"ok": False, "error": "stopped", "engine": "pyttsx3"}
            eng = pyttsx3.init()
            eng.say(cleaned)
            eng.runAndWait()
            return {"ok": True, "engine": "pyttsx3"}
        except Exception:
            pass

        last_err = ""
        if sys.platform == "win32":
            try:
                if _stop.is_set():
                    return {"ok": False, "error": "stopped", "engine": "System.Speech"}
                safe = cleaned.replace("'", "''")
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
                last_err = str(e)

        for cmd, args_fn in (
            ("espeak-ng", lambda t: ["espeak-ng", t]),
            ("espeak", lambda t: ["espeak", t]),
            ("spd-say", lambda t: ["spd-say", t]),
            ("say", lambda t: ["say", t]),
        ):
            if not shutil.which(cmd):
                continue
            try:
                if _stop.is_set():
                    return {"ok": False, "error": "stopped", "engine": cmd}
                subprocess.run(args_fn(cleaned), capture_output=True, timeout=120)
                return {"ok": True, "engine": cmd}
            except Exception as e:  # noqa: BLE001
                last_err = str(e)

        return {
            "ok": False,
            "error": last_err or "TTS failed",
            "degraded": True,
            "engine": "none",
        }

    if async_play:
        stop_speaking()
        _stop.clear()

        def _wrap() -> None:
            global _last_engine
            res = _run()
            _last_engine = str(res.get("engine") or "")

        with _lock:
            _speak_thread = threading.Thread(target=_wrap, daemon=True)
            _speak_thread.start()
        return {"ok": True, "engine": "async", "speaking": True}

    res = _run()
    _last_engine = str(res.get("engine") or "")
    return res
