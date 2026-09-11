"""Text-to-speech for chat — multi-provider, soft-degrade.

Engines (selected via voice_settings.tts_engine):
  - local: pyttsx3 → Windows SAPI → Linux espeak/spd-say / macOS say
  - openai: OpenAI-compatible POST {base}/audio/speech (mp3), then play
  - elevenlabs: ElevenLabs text-to-speech API (needs voice_elevenlabs_api_key)

Soft-degrades to local when API key missing or request fails.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path
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


def _selected_tts_engine() -> str:
    try:
        from app.core.services.ai.voice_settings import tts_engine

        return tts_engine()
    except Exception:  # noqa: BLE001
        return "local"


def _local_tts_probe() -> dict[str, Any]:
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


def _openai_tts_probe() -> dict[str, Any]:
    try:
        from app.core.services.ai.voice_settings import (
            resolve_openai_creds,
            tts_model,
            tts_voice,
        )
    except Exception as e:  # noqa: BLE001
        return {
            "available": False,
            "engines": ["openai"],
            "detail": f"voice_settings unavailable: {e}",
            "hint": "Check Studio install.",
            "platform": sys.platform,
        }
    creds = resolve_openai_creds()
    key = creds.get("api_key") or ""
    base = creds.get("base_url") or ""
    if not key:
        return {
            "available": False,
            "engines": ["openai"],
            "detail": "OpenAI TTS needs an API key (Settings → Providers / api_key).",
            "hint": "Add Studio API key, or switch TTS engine to local.",
            "platform": sys.platform,
            "base_url": base,
            "model": tts_model(),
            "voice": tts_voice(),
        }
    return {
        "available": True,
        "engines": ["openai"],
        "detail": f"OpenAI TTS @ {base} · {tts_model()} / {tts_voice()}",
        "hint": "",
        "platform": sys.platform,
        "base_url": base,
        "model": tts_model(),
        "voice": tts_voice(),
        "has_api_key": True,
    }


def _elevenlabs_tts_probe() -> dict[str, Any]:
    try:
        from app.core.services.ai.voice_settings import (
            elevenlabs_api_key,
            elevenlabs_voice_id,
        )
    except Exception as e:  # noqa: BLE001
        return {
            "available": False,
            "engines": ["elevenlabs"],
            "detail": f"voice_settings unavailable: {e}",
            "hint": "Check Studio install.",
            "platform": sys.platform,
        }
    key = elevenlabs_api_key()
    vid = elevenlabs_voice_id()
    if not key:
        return {
            "available": False,
            "engines": ["elevenlabs"],
            "detail": "ElevenLabs TTS needs voice_elevenlabs_api_key in Settings → Voice.",
            "hint": "Paste an ElevenLabs API key, or switch TTS engine to local/openai.",
            "platform": sys.platform,
            "voice_id": vid,
        }
    return {
        "available": True,
        "engines": ["elevenlabs"],
        "detail": f"ElevenLabs voice {vid}",
        "hint": "",
        "platform": sys.platform,
        "voice_id": vid,
        "has_api_key": True,
    }


def tts_capability() -> dict[str, Any]:
    selected = _selected_tts_engine()
    if selected == "openai":
        probe = _openai_tts_probe()
        probe["selected"] = "openai"
        return probe
    if selected == "elevenlabs":
        probe = _elevenlabs_tts_probe()
        probe["selected"] = "elevenlabs"
        return probe
    probe = _local_tts_probe()
    probe["selected"] = "local"
    return probe


def is_speaking() -> bool:
    return bool(_speak_thread and _speak_thread.is_alive() and not _stop.is_set())


def stop_speaking() -> None:
    global _speak_thread
    _stop.set()
    with _lock:
        _speak_thread = None


def _play_audio_file(path: str) -> dict[str, Any]:
    """Play mp3/wav via best available local player. Soft-degrade if none."""
    p = Path(path)
    if not p.is_file():
        return {"ok": False, "error": f"Audio file missing: {path}"}

    if _stop.is_set():
        return {"ok": False, "error": "stopped"}

    players: list[list[str]] = []
    if shutil.which("ffplay"):
        players.append(["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(p)])
    if sys.platform == "darwin" and shutil.which("afplay"):
        players.append(["afplay", str(p)])
    if sys.platform == "win32":
        # PowerShell MediaPlayer for mp3
        safe = str(p).replace("'", "''")
        players.append(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    "Add-Type -AssemblyName presentationCore; "
                    "$p = New-Object System.Windows.Media.MediaPlayer; "
                    f"$p.Open([uri]'{safe}'); $p.Play(); "
                    "while ($p.NaturalDuration.HasTimeSpan -eq $false) { Start-Sleep -Milliseconds 50 }; "
                    "Start-Sleep -Seconds ([math]::Ceiling($p.NaturalDuration.TimeSpan.TotalSeconds) + 0.5)"
                ),
            ]
        )
    for cmd in ("mpg123", "mpv", "cvlc", "paplay", "aplay"):
        if shutil.which(cmd):
            if cmd == "cvlc":
                players.append(["cvlc", "--play-and-exit", "--quiet", str(p)])
            elif cmd == "mpv":
                players.append(["mpv", "--no-video", "--really-quiet", str(p)])
            else:
                players.append([cmd, str(p)])

    last_err = "No audio player found (ffplay/afplay/mpg123/…)"
    for args in players:
        if _stop.is_set():
            return {"ok": False, "error": "stopped"}
        try:
            subprocess.run(args, capture_output=True, timeout=180)
            return {"ok": True, "player": args[0]}
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
    return {"ok": False, "error": last_err, "degraded": True}


def synthesize_openai_tts(
    text: str,
    *,
    api_key: str = "",
    base_url: str = "",
    model: str = "",
    voice: str = "",
    out_path: str = "",
) -> dict[str, Any]:
    """POST JSON to OpenAI-compatible /audio/speech. Returns {ok, path, ...}."""
    try:
        from app.core.services.ai.voice_settings import (
            resolve_openai_creds,
            tts_model,
            tts_voice,
        )
    except Exception:  # noqa: BLE001
        resolve_openai_creds = None  # type: ignore
        tts_model = lambda: "tts-1"  # noqa: E731
        tts_voice = lambda: "alloy"  # noqa: E731

    if not api_key or not base_url:
        creds = resolve_openai_creds() if resolve_openai_creds else {"api_key": "", "base_url": ""}
        api_key = api_key or creds.get("api_key") or ""
        base_url = (base_url or creds.get("base_url") or "https://api.openai.com/v1").rstrip("/")
    model = (model or (tts_model() if callable(tts_model) else "tts-1") or "tts-1").strip()
    voice = (voice or (tts_voice() if callable(tts_voice) else "alloy") or "alloy").strip()
    if not api_key:
        return {
            "ok": False,
            "error": "Missing API key for OpenAI TTS",
            "hint": "Set Studio API key in Settings, or switch TTS engine to local.",
            "engine": "openai",
            "degraded": True,
        }

    url = base_url.rstrip("/") + "/audio/speech"
    body = json.dumps(
        {
            "model": model,
            "voice": voice,
            "input": text,
            "response_format": "mp3",
        }
    ).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            audio = resp.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:600]
        hint = ""
        if e.code == 401:
            hint = "Check Studio API key."
        elif e.code == 404:
            hint = "Base URL may not support /audio/speech (OpenAI-compatible TTS)."
        return {
            "ok": False,
            "error": f"OpenAI TTS HTTP {e.code}: {detail}",
            "hint": hint,
            "engine": "openai",
            "degraded": True,
        }
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "error": f"OpenAI TTS request failed: {e}",
            "engine": "openai",
            "degraded": True,
        }

    if not audio:
        return {"ok": False, "error": "OpenAI TTS returned empty audio", "engine": "openai"}

    if out_path:
        path = Path(out_path)
    else:
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        path = Path(tmp.name)
        tmp.close()
    path.write_bytes(audio)
    return {
        "ok": True,
        "path": str(path),
        "engine": "openai",
        "model": model,
        "voice": voice,
        "bytes": len(audio),
    }


def synthesize_elevenlabs_tts(
    text: str,
    *,
    api_key: str = "",
    voice_id: str = "",
    out_path: str = "",
) -> dict[str, Any]:
    """POST to ElevenLabs text-to-speech. Soft stub when key missing."""
    try:
        from app.core.services.ai.voice_settings import (
            elevenlabs_api_key,
            elevenlabs_voice_id,
        )
    except Exception:  # noqa: BLE001
        elevenlabs_api_key = lambda: ""  # noqa: E731
        elevenlabs_voice_id = lambda: "21m00Tcm4TlvDq8ikWAM"  # noqa: E731

    api_key = (api_key or elevenlabs_api_key() or "").strip()
    voice_id = (voice_id or elevenlabs_voice_id() or "").strip()
    if not api_key:
        return {
            "ok": False,
            "error": "Missing ElevenLabs API key",
            "hint": "Set voice_elevenlabs_api_key in Settings → Voice.",
            "engine": "elevenlabs",
            "degraded": True,
        }
    if not voice_id:
        return {
            "ok": False,
            "error": "Missing ElevenLabs voice id",
            "engine": "elevenlabs",
            "degraded": True,
        }

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    body = json.dumps(
        {
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.5},
        }
    ).encode("utf-8")
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": api_key,
    }
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            audio = resp.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:600]
        return {
            "ok": False,
            "error": f"ElevenLabs HTTP {e.code}: {detail}",
            "hint": "Check ElevenLabs API key / voice id.",
            "engine": "elevenlabs",
            "degraded": True,
        }
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "error": f"ElevenLabs request failed: {e}",
            "engine": "elevenlabs",
            "degraded": True,
        }

    if not audio:
        return {"ok": False, "error": "ElevenLabs returned empty audio", "engine": "elevenlabs"}

    if out_path:
        path = Path(out_path)
    else:
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        path = Path(tmp.name)
        tmp.close()
    path.write_bytes(audio)
    return {
        "ok": True,
        "path": str(path),
        "engine": "elevenlabs",
        "voice_id": voice_id,
        "bytes": len(audio),
    }


def _speak_local(cleaned: str) -> dict[str, Any]:
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


def _speak_openai(cleaned: str) -> dict[str, Any]:
    probe = _openai_tts_probe()
    if not probe.get("available"):
        local = _speak_local(cleaned)
        if local.get("ok"):
            local["fallback_from"] = "openai"
            return local
        return {
            "ok": False,
            "error": probe.get("detail") or "OpenAI TTS unavailable",
            "hint": probe.get("hint") or "",
            "engine": "openai",
            "degraded": True,
        }

    syn = synthesize_openai_tts(cleaned)
    if not syn.get("ok"):
        local = _speak_local(cleaned)
        if local.get("ok"):
            local["fallback_from"] = "openai"
            local["openai_error"] = syn.get("error")
            return local
        return syn

    path = str(syn["path"])
    try:
        if _stop.is_set():
            return {"ok": False, "error": "stopped", "engine": "openai"}
        play = _play_audio_file(path)
        if play.get("ok"):
            return {
                "ok": True,
                "engine": "openai",
                "model": syn.get("model"),
                "voice": syn.get("voice"),
                "player": play.get("player"),
            }
        # Soft-degrade to local speak if player missing
        local = _speak_local(cleaned)
        if local.get("ok"):
            local["fallback_from"] = "openai"
            local["play_error"] = play.get("error")
            return local
        return {
            "ok": False,
            "error": play.get("error") or "Could not play TTS audio",
            "engine": "openai",
            "degraded": True,
            "path": path,
        }
    finally:
        try:
            Path(path).unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass


def _speak_elevenlabs(cleaned: str) -> dict[str, Any]:
    probe = _elevenlabs_tts_probe()
    if not probe.get("available"):
        local = _speak_local(cleaned)
        if local.get("ok"):
            local["fallback_from"] = "elevenlabs"
            return local
        return {
            "ok": False,
            "error": probe.get("detail") or "ElevenLabs TTS unavailable",
            "hint": probe.get("hint") or "",
            "engine": "elevenlabs",
            "degraded": True,
        }

    syn = synthesize_elevenlabs_tts(cleaned)
    if not syn.get("ok"):
        local = _speak_local(cleaned)
        if local.get("ok"):
            local["fallback_from"] = "elevenlabs"
            local["elevenlabs_error"] = syn.get("error")
            return local
        return syn

    path = str(syn["path"])
    try:
        if _stop.is_set():
            return {"ok": False, "error": "stopped", "engine": "elevenlabs"}
        play = _play_audio_file(path)
        if play.get("ok"):
            return {
                "ok": True,
                "engine": "elevenlabs",
                "voice_id": syn.get("voice_id"),
                "player": play.get("player"),
            }
        local = _speak_local(cleaned)
        if local.get("ok"):
            local["fallback_from"] = "elevenlabs"
            local["play_error"] = play.get("error")
            return local
        return {
            "ok": False,
            "error": play.get("error") or "Could not play TTS audio",
            "engine": "elevenlabs",
            "degraded": True,
            "path": path,
        }
    finally:
        try:
            Path(path).unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass


def speak_text(
    text: str,
    *,
    async_play: bool = True,
    max_chars: int = 2500,
    engine: str | None = None,
) -> dict[str, Any]:
    global _speak_thread, _last_engine

    selected = (engine or _selected_tts_engine() or "local").lower()
    cleaned = _strip_for_speech(text)
    if not cleaned:
        return {"ok": False, "error": "Empty text"}
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars] + "…"

    # Capability gate for selected engine; soft-degrade handled inside runners
    cap = tts_capability() if engine is None else (
        _openai_tts_probe()
        if selected == "openai"
        else _elevenlabs_tts_probe()
        if selected == "elevenlabs"
        else _local_tts_probe()
    )
    if selected == "local" and not cap.get("available"):
        return {
            "ok": False,
            "error": cap.get("detail") or "TTS unavailable",
            "hint": cap.get("hint") or "",
            "degraded": True,
            "engine": "none",
        }

    def _run() -> dict[str, Any]:
        _stop.clear()
        if selected == "openai":
            return _speak_openai(cleaned)
        if selected == "elevenlabs":
            return _speak_elevenlabs(cleaned)
        return _speak_local(cleaned)

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
        return {"ok": True, "engine": "async", "speaking": True, "selected": selected}

    res = _run()
    _last_engine = str(res.get("engine") or "")
    return res
