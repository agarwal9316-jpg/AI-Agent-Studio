"""Speech-to-text (mic) for chat input — cross-platform, optional deps.

Engines (first available wins):
  1) speech_recognition + Microphone (+ Google Web Speech)
  2) Windows PowerShell System.Speech.Recognition (offline)
Graceful degrade when no mic / no engine.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable


def stt_capability() -> dict[str, Any]:
    """Probe STT availability without capturing audio."""
    engines: list[str] = []
    detail = ""
    has_sr = False
    has_mic_api = False
    try:
        import speech_recognition as sr  # type: ignore  # noqa: F401

        has_sr = True
        engines.append("speech_recognition")
        try:
            names = sr.Microphone.list_microphone_names()  # type: ignore[attr-defined]
            has_mic_api = True
            if names:
                detail = f"{len(names)} mic device(s)"
            else:
                detail = "SpeechRecognition installed but no mic devices listed"
        except Exception as e:  # noqa: BLE001
            detail = f"Microphone probe failed: {e}"
    except ImportError:
        detail = "SpeechRecognition not installed (optional: pip install SpeechRecognition pyaudio)"
    except Exception as e:  # noqa: BLE001
        detail = str(e)

    if sys.platform == "win32":
        engines.append("System.Speech")
        if not detail:
            detail = "Windows System.Speech fallback available"

    available = bool(engines) and (has_sr or sys.platform == "win32")
    if sys.platform != "win32" and not has_sr:
        available = False
    return {
        "available": available,
        "engines": engines,
        "has_speech_recognition": has_sr,
        "has_mic_list": has_mic_api,
        "platform": sys.platform,
        "detail": detail or ("ready" if available else "STT unavailable"),
        "hint": (
            ""
            if available
            else "Install SpeechRecognition + pyaudio, or use Windows Speech Recognition."
        ),
    }


def listen_once(
    *,
    timeout: float = 8.0,
    phrase_time_limit: float = 20.0,
    language: str = "en-US",
    on_status: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Capture one utterance from the default microphone."""

    def status(m: str) -> None:
        if on_status:
            try:
                on_status(m)
            except Exception:  # noqa: BLE001
                pass

    cap = stt_capability()
    if not cap.get("available"):
        return {
            "ok": False,
            "error": cap.get("detail") or "Mic / STT unavailable",
            "hint": cap.get("hint") or "",
            "engine": "none",
            "degraded": True,
        }

    try:
        import speech_recognition as sr  # type: ignore

        status("Listening (SpeechRecognition)…")
        r = sr.Recognizer()
        with sr.Microphone() as source:
            r.adjust_for_ambient_noise(source, duration=0.4)
            audio = r.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
        status("Recognizing…")
        try:
            text = r.recognize_google(audio, language=language)
            return {"ok": True, "text": text, "engine": "google+speech_recognition"}
        except sr.UnknownValueError:
            return {"ok": False, "error": "Could not understand audio", "engine": "speech_recognition"}
        except sr.RequestError as e:
            return {
                "ok": False,
                "error": f"Recognition service error: {e}",
                "engine": "speech_recognition",
            }
    except ImportError:
        pass
    except OSError as e:
        status(f"No microphone: {e}")
        if sys.platform != "win32":
            return {
                "ok": False,
                "error": f"No microphone available: {e}",
                "engine": "speech_recognition",
                "degraded": True,
            }
    except Exception as e:  # noqa: BLE001
        status(f"SpeechRecognition failed: {e}")
        if sys.platform != "win32":
            return {
                "ok": False,
                "error": f"Mic STT failed: {e}",
                "engine": "speech_recognition",
                "degraded": True,
            }

    if sys.platform != "win32":
        return {
            "ok": False,
            "error": (
                "Mic STT unavailable on this platform without SpeechRecognition. "
                "Optional: pip install SpeechRecognition pyaudio"
            ),
            "engine": "none",
            "degraded": True,
        }

    status("Listening (Windows Speech)…")
    try:
        ps = r"""
Add-Type -AssemblyName System.Speech
$rec = New-Object System.Speech.Recognition.SpeechRecognitionEngine
$rec.SetInputToDefaultAudioDevice()
$grammar = New-Object System.Speech.Recognition.DictationGrammar
$rec.LoadGrammar($grammar)
$rec.InitialSilenceTimeout = [TimeSpan]::FromSeconds(5)
$rec.BabbleTimeout = [TimeSpan]::FromSeconds(4)
$rec.EndSilenceTimeout = [TimeSpan]::FromSeconds(1.2)
try {
  $result = $rec.Recognize([TimeSpan]::FromSeconds(18))
  if ($null -eq $result) { Write-Output '' } else { Write-Output $result.Text }
} catch {
  Write-Output ("ERR:" + $_.Exception.Message)
}
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".ps1", delete=False, encoding="utf-8"
        ) as f:
            f.write(ps)
            script = f.name
        try:
            proc = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    script,
                ],
                capture_output=True,
                text=True,
                timeout=max(25, int(timeout) + 15),
            )
            out = (proc.stdout or "").strip()
            if out.startswith("ERR:"):
                return {"ok": False, "error": out[4:].strip(), "engine": "System.Speech"}
            if not out:
                return {
                    "ok": False,
                    "error": (
                        "No speech detected. Install SpeechRecognition for better mic support: "
                        "pip install SpeechRecognition pyaudio"
                    ),
                    "engine": "System.Speech",
                }
            return {"ok": True, "text": out, "engine": "System.Speech"}
        finally:
            try:
                Path(script).unlink(missing_ok=True)
            except Exception:  # noqa: BLE001
                pass
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "error": (
                f"Mic STT unavailable: {e}. "
                "Optional: pip install SpeechRecognition pyaudio"
            ),
            "engine": "none",
            "degraded": True,
        }


def listen_async(
    callback: Callable[[dict[str, Any]], None],
    **kwargs: Any,
) -> None:
    def _run() -> None:
        result = listen_once(**kwargs)
        try:
            callback(result)
        except Exception:  # noqa: BLE001
            pass

    threading.Thread(target=_run, daemon=True).start()


_loop_stop = threading.Event()
_loop_thread: threading.Thread | None = None


def start_continuous(
    on_utterance: Callable[[dict[str, Any]], None],
    *,
    pause_between: float = 0.6,
    language: str = "en-US",
    on_status: Callable[[str], None] | None = None,
) -> None:
    """Continuous conversation loop until stop_continuous()."""
    global _loop_thread
    if _loop_thread and _loop_thread.is_alive():
        return
    cap = stt_capability()
    if not cap.get("available"):
        try:
            on_utterance(
                {
                    "ok": False,
                    "error": cap.get("detail") or "STT unavailable",
                    "degraded": True,
                    "engine": "none",
                }
            )
        except Exception:  # noqa: BLE001
            pass
        if on_status:
            try:
                on_status(str(cap.get("detail") or "STT unavailable"))
            except Exception:  # noqa: BLE001
                pass
        return

    _loop_stop.clear()

    def _run() -> None:
        while not _loop_stop.is_set():
            if on_status:
                try:
                    on_status("Listening… (continuous)")
                except Exception:  # noqa: BLE001
                    pass
            result = listen_once(
                timeout=6.0,
                phrase_time_limit=25.0,
                language=language,
                on_status=on_status,
            )
            if _loop_stop.is_set():
                break
            if result.get("ok") and result.get("text"):
                try:
                    on_utterance(result)
                except Exception:  # noqa: BLE001
                    pass
            elif result.get("degraded"):
                try:
                    on_utterance(result)
                except Exception:  # noqa: BLE001
                    pass
                break
            import time as _t

            _t.sleep(pause_between)
        if on_status:
            try:
                on_status("Continuous voice stopped")
            except Exception:  # noqa: BLE001
                pass

    _loop_thread = threading.Thread(target=_run, daemon=True)
    _loop_thread.start()


def stop_continuous() -> None:
    _loop_stop.set()


def continuous_running() -> bool:
    return bool(_loop_thread and _loop_thread.is_alive() and not _loop_stop.is_set())
