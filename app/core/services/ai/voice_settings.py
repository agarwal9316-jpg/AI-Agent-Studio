"""Voice in/out settings — mic STT + TTS read-aloud (PENDING #18 + P2.1).

Config keys (data/config.json via storage.load_config):
  voice_mic_enabled       bool  — show/use mic in chat (default True)
  voice_mic_mode          str   — "push_to_talk" | "toggle" (default push_to_talk)
  voice_tts_enabled       bool  — allow Speak / read-aloud (default True)
  voice_auto_read_aloud   bool  — speak assistant replies automatically (default False)
  voice_language          str   — STT language tag (default en-US)
  voice_stt_engine        str   — "local" | "openai_whisper" (default local)
  voice_tts_engine        str   — "local" | "openai" | "elevenlabs" (default local)
  voice_stt_model         str   — Whisper model id (default whisper-1)
  voice_tts_model         str   — OpenAI TTS model (default tts-1)
  voice_tts_voice         str   — OpenAI TTS voice (default alloy)
  voice_elevenlabs_api_key str  — optional ElevenLabs key
  voice_elevenlabs_voice_id str — ElevenLabs voice id (default Rachel)
"""

from __future__ import annotations

from typing import Any, Literal

from app.core.services.data.storage import load_config, save_config

MicMode = Literal["push_to_talk", "toggle"]
SttEngine = Literal["local", "openai_whisper"]
TtsEngine = Literal["local", "openai", "elevenlabs"]

STT_ENGINES = ("local", "openai_whisper")
TTS_ENGINES = ("local", "openai", "elevenlabs")

_DEFAULTS: dict[str, Any] = {
    "voice_mic_enabled": True,
    "voice_mic_mode": "push_to_talk",
    "voice_tts_enabled": True,
    "voice_auto_read_aloud": False,
    "voice_language": "en-US",
    "voice_stt_engine": "local",
    "voice_tts_engine": "local",
    "voice_stt_model": "whisper-1",
    "voice_tts_model": "tts-1",
    "voice_tts_voice": "alloy",
    "voice_elevenlabs_api_key": "",
    "voice_elevenlabs_voice_id": "21m00Tcm4TlvDq8ikWAM",  # ElevenLabs "Rachel"
}


def _set(key: str, value: Any) -> None:
    cfg = load_config()
    cfg[key] = value
    save_config(cfg)


def ensure_defaults(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    data = cfg if cfg is not None else load_config()
    for k, v in _DEFAULTS.items():
        data.setdefault(k, v)
    mode = str(data.get("voice_mic_mode") or "push_to_talk").lower()
    if mode not in ("push_to_talk", "toggle"):
        data["voice_mic_mode"] = "push_to_talk"
    stt = str(data.get("voice_stt_engine") or "local").lower()
    if stt not in STT_ENGINES:
        data["voice_stt_engine"] = "local"
    tts = str(data.get("voice_tts_engine") or "local").lower()
    if tts not in TTS_ENGINES:
        data["voice_tts_engine"] = "local"
    return data


def mic_enabled() -> bool:
    return bool(load_config().get("voice_mic_enabled", True))


def set_mic_enabled(on: bool) -> None:
    _set("voice_mic_enabled", bool(on))


def mic_mode() -> MicMode:
    mode = str(load_config().get("voice_mic_mode") or "push_to_talk").lower()
    return "toggle" if mode == "toggle" else "push_to_talk"


def set_mic_mode(mode: str) -> None:
    m = (mode or "").strip().lower()
    if m not in ("push_to_talk", "toggle"):
        m = "push_to_talk"
    _set("voice_mic_mode", m)


def tts_enabled() -> bool:
    return bool(load_config().get("voice_tts_enabled", True))


def set_tts_enabled(on: bool) -> None:
    _set("voice_tts_enabled", bool(on))


def auto_read_aloud() -> bool:
    return bool(load_config().get("voice_auto_read_aloud", False))


def set_auto_read_aloud(on: bool) -> None:
    _set("voice_auto_read_aloud", bool(on))


def voice_language() -> str:
    return str(load_config().get("voice_language") or "en-US")


def set_voice_language(lang: str) -> None:
    _set("voice_language", (lang or "en-US").strip() or "en-US")


def stt_engine() -> SttEngine:
    eng = str(load_config().get("voice_stt_engine") or "local").lower()
    return "openai_whisper" if eng == "openai_whisper" else "local"


def set_stt_engine(engine: str) -> None:
    e = (engine or "").strip().lower()
    if e not in STT_ENGINES:
        e = "local"
    _set("voice_stt_engine", e)


def tts_engine() -> TtsEngine:
    eng = str(load_config().get("voice_tts_engine") or "local").lower()
    if eng == "openai":
        return "openai"
    if eng == "elevenlabs":
        return "elevenlabs"
    return "local"


def set_tts_engine(engine: str) -> None:
    e = (engine or "").strip().lower()
    if e not in TTS_ENGINES:
        e = "local"
    _set("voice_tts_engine", e)


def stt_model() -> str:
    return str(load_config().get("voice_stt_model") or "whisper-1").strip() or "whisper-1"


def set_stt_model(model: str) -> None:
    _set("voice_stt_model", (model or "whisper-1").strip() or "whisper-1")


def tts_model() -> str:
    return str(load_config().get("voice_tts_model") or "tts-1").strip() or "tts-1"


def set_tts_model(model: str) -> None:
    _set("voice_tts_model", (model or "tts-1").strip() or "tts-1")


def tts_voice() -> str:
    return str(load_config().get("voice_tts_voice") or "alloy").strip() or "alloy"


def set_tts_voice(voice: str) -> None:
    _set("voice_tts_voice", (voice or "alloy").strip() or "alloy")


def elevenlabs_api_key() -> str:
    return str(load_config().get("voice_elevenlabs_api_key") or "").strip()


def set_elevenlabs_api_key(key: str) -> None:
    _set("voice_elevenlabs_api_key", (key or "").strip())


def elevenlabs_voice_id() -> str:
    return str(
        load_config().get("voice_elevenlabs_voice_id") or _DEFAULTS["voice_elevenlabs_voice_id"]
    ).strip() or _DEFAULTS["voice_elevenlabs_voice_id"]


def set_elevenlabs_voice_id(voice_id: str) -> None:
    _set(
        "voice_elevenlabs_voice_id",
        (voice_id or "").strip() or _DEFAULTS["voice_elevenlabs_voice_id"],
    )


def resolve_openai_creds() -> dict[str, str]:
    """Studio API key + base_url for OpenAI-compatible audio endpoints."""
    cfg = load_config()
    key = ""
    base = ""
    try:
        from app.core.services.llm.providers import resolve_active_llm

        active = resolve_active_llm()
        key = str(active.get("api_key") or "").strip()
        base = str(active.get("base_url") or "").strip()
    except Exception:  # noqa: BLE001
        pass
    if not key:
        key = str(cfg.get("api_key") or "").strip()
    if not base:
        base = str(cfg.get("api_base_url") or "https://api.openai.com/v1").strip()
    base = base.rstrip("/")
    return {"api_key": key, "base_url": base or "https://api.openai.com/v1"}


def voice_status_summary() -> dict[str, Any]:
    from app.core.services.ai.stt_service import stt_capability
    from app.core.services.ai.tts_service import tts_capability

    stt = stt_capability()
    tts = tts_capability()
    return {
        "mic_enabled": mic_enabled(),
        "mic_mode": mic_mode(),
        "tts_enabled": tts_enabled(),
        "auto_read_aloud": auto_read_aloud(),
        "language": voice_language(),
        "stt_engine": stt_engine(),
        "tts_engine": tts_engine(),
        "stt_model": stt_model(),
        "tts_model": tts_model(),
        "tts_voice": tts_voice(),
        "has_elevenlabs_key": bool(elevenlabs_api_key()),
        "stt": stt,
        "tts": tts,
        "mic_usable": bool(mic_enabled() and stt.get("available")),
        "tts_usable": bool(tts_enabled() and tts.get("available")),
    }
