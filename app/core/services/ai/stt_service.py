"""Speech-to-text (mic) for chat input — multi-provider, soft-degrade.

Engines (selected via voice_settings.stt_engine):
  - local: SpeechRecognition (+ Google Web Speech) / Windows System.Speech
  - openai_whisper: OpenAI-compatible POST {base}/audio/transcriptions
                    using Studio API key + base_url; falls back to local on failure.

Graceful degrade when no mic / no engine / missing API key.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable


def _selected_stt_engine() -> str:
    try:
        from app.core.services.ai.voice_settings import stt_engine

        return stt_engine()
    except Exception:  # noqa: BLE001
        return "local"


def _local_stt_probe() -> dict[str, Any]:
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


def _openai_whisper_probe() -> dict[str, Any]:
    try:
        from app.core.services.ai.voice_settings import resolve_openai_creds, stt_model
    except Exception as e:  # noqa: BLE001
        return {
            "available": False,
            "engines": ["openai_whisper"],
            "detail": f"voice_settings unavailable: {e}",
            "hint": "Check Studio install.",
            "platform": sys.platform,
        }
    creds = resolve_openai_creds()
    key = creds.get("api_key") or ""
    base = creds.get("base_url") or ""
    local = _local_stt_probe()
    can_record = bool(local.get("has_speech_recognition") or sys.platform == "win32")
    if not key:
        return {
            "available": False,
            "engines": ["openai_whisper"],
            "detail": "OpenAI Whisper STT needs an API key (Settings → Providers / api_key).",
            "hint": "Add Studio API key, or switch STT engine to local.",
            "platform": sys.platform,
            "base_url": base,
            "model": stt_model(),
            "can_record": can_record,
        }
    detail = f"Whisper API @ {base} · model {stt_model()}"
    if not can_record:
        detail += " · mic capture may need SpeechRecognition/pyaudio"
    return {
        "available": True,
        "engines": ["openai_whisper"],
        "detail": detail,
        "hint": "" if can_record else "Install SpeechRecognition + pyaudio to capture mic audio.",
        "platform": sys.platform,
        "base_url": base,
        "model": stt_model(),
        "can_record": can_record,
        "has_api_key": True,
    }


def stt_capability() -> dict[str, Any]:
    """Probe STT availability for the selected engine (never raises)."""
    selected = _selected_stt_engine()
    if selected == "openai_whisper":
        probe = _openai_whisper_probe()
        probe["selected"] = "openai_whisper"
        # Soft-usable: API key present counts as available; mic issues surface at listen time.
        return probe
    probe = _local_stt_probe()
    probe["selected"] = "local"
    return probe


def _record_wav_path(
    *,
    timeout: float = 8.0,
    phrase_time_limit: float = 20.0,
    on_status: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Capture one utterance to a temp WAV file. Returns {ok, path?, error?}."""

    def status(m: str) -> None:
        if on_status:
            try:
                on_status(m)
            except Exception:  # noqa: BLE001
                pass

    try:
        import speech_recognition as sr  # type: ignore

        status("Recording…")
        r = sr.Recognizer()
        with sr.Microphone() as source:
            r.adjust_for_ambient_noise(source, duration=0.4)
            audio = r.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
        wav = audio.get_wav_data()
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.write(wav)
        tmp.close()
        return {"ok": True, "path": tmp.name, "engine": "speech_recognition"}
    except ImportError:
        return {
            "ok": False,
            "error": "SpeechRecognition not installed (needed to capture mic for Whisper API)",
            "hint": "pip install SpeechRecognition pyaudio",
            "degraded": True,
        }
    except OSError as e:
        return {
            "ok": False,
            "error": f"No microphone available: {e}",
            "degraded": True,
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"Mic capture failed: {e}", "degraded": True}


def transcribe_openai_whisper(
    audio_path: str,
    *,
    language: str = "en-US",
    api_key: str = "",
    base_url: str = "",
    model: str = "",
) -> dict[str, Any]:
    """POST multipart to OpenAI-compatible /audio/transcriptions.

    Pure HTTP helper — used by listen_once and unit tests (mockable).
    """
    try:
        from app.core.services.ai.voice_settings import resolve_openai_creds, stt_model
    except Exception:  # noqa: BLE001
        resolve_openai_creds = None  # type: ignore
        stt_model = lambda: "whisper-1"  # noqa: E731

    if not api_key or not base_url:
        creds = resolve_openai_creds() if resolve_openai_creds else {"api_key": "", "base_url": ""}
        api_key = api_key or creds.get("api_key") or ""
        base_url = (base_url or creds.get("base_url") or "https://api.openai.com/v1").rstrip("/")
    model = (model or (stt_model() if callable(stt_model) else "whisper-1") or "whisper-1").strip()
    if not api_key:
        return {
            "ok": False,
            "error": "Missing API key for Whisper STT",
            "hint": "Set Studio API key in Settings, or switch STT engine to local.",
            "engine": "openai_whisper",
            "degraded": True,
        }

    path = Path(audio_path)
    if not path.is_file():
        return {"ok": False, "error": f"Audio file missing: {audio_path}", "engine": "openai_whisper"}

    # Language: Whisper wants ISO-639-1 (en), not en-US
    lang = (language or "").strip()
    if "-" in lang:
        lang = lang.split("-", 1)[0].lower()
    elif len(lang) > 2:
        lang = lang[:2].lower()

    boundary = "----StudioWhisperBoundary7MA4YWxk"
    url = base_url.rstrip("/") + "/audio/transcriptions"
    filename = path.name or "audio.wav"
    file_bytes = path.read_bytes()
    parts: list[bytes] = []

    def _field(name: str, value: str) -> None:
        parts.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                f"{value}\r\n"
            ).encode("utf-8")
        )

    _field("model", model)
    if lang:
        _field("language", lang)
    parts.append(
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: audio/wav\r\n\r\n"
        ).encode("utf-8")
    )
    parts.append(file_bytes)
    parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(parts)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body)),
    }
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            payload = json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:600]
        hint = ""
        if e.code == 401:
            hint = "Check Studio API key."
        elif e.code == 404:
            hint = "Base URL may not support /audio/transcriptions (OpenAI-compatible Whisper)."
        return {
            "ok": False,
            "error": f"Whisper HTTP {e.code}: {detail}",
            "hint": hint,
            "engine": "openai_whisper",
            "degraded": True,
        }
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "error": f"Whisper request failed: {e}",
            "engine": "openai_whisper",
            "degraded": True,
        }

    text = ""
    if isinstance(payload, dict):
        text = str(payload.get("text") or "").strip()
    if not text:
        return {
            "ok": False,
            "error": "Whisper returned empty transcript",
            "engine": "openai_whisper",
            "raw": payload,
        }
    return {"ok": True, "text": text, "engine": "openai_whisper", "model": model, "raw": payload}


def _listen_local(
    *,
    timeout: float = 8.0,
    phrase_time_limit: float = 20.0,
    language: str = "en-US",
    on_status: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    def status(m: str) -> None:
        if on_status:
            try:
                on_status(m)
            except Exception:  # noqa: BLE001
                pass

    cap = _local_stt_probe()
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


def _listen_openai_whisper(
    *,
    timeout: float = 8.0,
    phrase_time_limit: float = 20.0,
    language: str = "en-US",
    on_status: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    def status(m: str) -> None:
        if on_status:
            try:
                on_status(m)
            except Exception:  # noqa: BLE001
                pass

    probe = _openai_whisper_probe()
    if not probe.get("available"):
        # Soft-degrade to local when key missing
        status("Whisper unavailable — trying local STT…")
        local = _listen_local(
            timeout=timeout,
            phrase_time_limit=phrase_time_limit,
            language=language,
            on_status=on_status,
        )
        if local.get("ok"):
            local["fallback_from"] = "openai_whisper"
            return local
        return {
            "ok": False,
            "error": probe.get("detail") or "Whisper STT unavailable",
            "hint": probe.get("hint") or "",
            "engine": "openai_whisper",
            "degraded": True,
            "local_error": local.get("error"),
        }

    rec = _record_wav_path(
        timeout=timeout, phrase_time_limit=phrase_time_limit, on_status=on_status
    )
    if not rec.get("ok"):
        # Soft-degrade to local listen path
        status("Mic capture for Whisper failed — trying local STT…")
        local = _listen_local(
            timeout=timeout,
            phrase_time_limit=phrase_time_limit,
            language=language,
            on_status=on_status,
        )
        if local.get("ok"):
            local["fallback_from"] = "openai_whisper"
            return local
        return {
            "ok": False,
            "error": rec.get("error") or "Mic capture failed",
            "hint": rec.get("hint") or "",
            "engine": "openai_whisper",
            "degraded": True,
        }

    wav_path = str(rec["path"])
    try:
        status("Transcribing (OpenAI Whisper)…")
        result = transcribe_openai_whisper(wav_path, language=language)
        if result.get("ok"):
            return result
        # Soft-degrade: try local recognition on same audio if SpeechRecognition present
        status(f"Whisper failed ({result.get('error')}) — trying local…")
        local = _listen_local(
            timeout=timeout,
            phrase_time_limit=phrase_time_limit,
            language=language,
            on_status=on_status,
        )
        if local.get("ok"):
            local["fallback_from"] = "openai_whisper"
            local["whisper_error"] = result.get("error")
            return local
        return result
    finally:
        try:
            Path(wav_path).unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass


def listen_once(
    *,
    timeout: float = 8.0,
    phrase_time_limit: float = 20.0,
    language: str = "en-US",
    on_status: Callable[[str], None] | None = None,
    engine: str | None = None,
) -> dict[str, Any]:
    """Capture one utterance from the default microphone using selected engine."""
    selected = (engine or _selected_stt_engine() or "local").lower()
    if selected == "openai_whisper":
        return _listen_openai_whisper(
            timeout=timeout,
            phrase_time_limit=phrase_time_limit,
            language=language,
            on_status=on_status,
        )
    return _listen_local(
        timeout=timeout,
        phrase_time_limit=phrase_time_limit,
        language=language,
        on_status=on_status,
    )


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
        # Still try local soft probe for continuous when API engine selected but no key
        local = _local_stt_probe()
        if not local.get("available"):
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
