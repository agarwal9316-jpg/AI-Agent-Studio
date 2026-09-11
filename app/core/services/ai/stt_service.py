"""Speech-to-text (mic) for chat input — Windows-friendly, optional deps."""

from __future__ import annotations

import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable


def listen_once(
    *,
    timeout: float = 8.0,
    phrase_time_limit: float = 20.0,
    language: str = "en-US",
    on_status: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """
    Capture one utterance from the default microphone.
    Tries: SpeechRecognition → Windows PowerShell SAPI → clear error.
    """
    def status(m: str) -> None:
        if on_status:
            try:
                on_status(m)
            except Exception:  # noqa: BLE001
                pass

    # 1) speech_recognition (best if installed)
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
            return {"ok": False, "error": f"Recognition service error: {e}", "engine": "speech_recognition"}
    except ImportError:
        pass
    except Exception as e:  # noqa: BLE001
        # mic missing etc. — try fallback
        status(f"SpeechRecognition failed: {e}")

    # 2) Windows PowerShell + System.Speech.Recognition (offline, free)
    status("Listening (Windows Speech)…")
    try:
        # Write a small PS1 to temp to avoid quoting hell
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
                    "error": "No speech detected. Install SpeechRecognition for better mic support: pip install SpeechRecognition pyaudio",
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
    """
    Continuous conversation loop: keep listening until stop_continuous().
    Each successful utterance invokes on_utterance.
    """
    global _loop_thread
    if _loop_thread and _loop_thread.is_alive():
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
