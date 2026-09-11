"""Voice in/out settings (PENDING #18) — mic STT + TTS read-aloud.

Config keys (data/config.json via storage.load_config):
  voice_mic_enabled      bool  — show/use mic in chat (default True)
  voice_mic_mode         str   — "push_to_talk" | "toggle" (default push_to_talk)
  voice_tts_enabled      bool  — allow Speak / read-aloud (default True)
  voice_auto_read_aloud  bool  — speak assistant replies automatically (default False)
  voice_language         str   — STT language tag (default en-US)
"""

from __future__ import annotations

from typing import Any, Literal

from app.core.services.data.storage import load_config, save_config

MicMode = Literal["push_to_talk", "toggle"]

_DEFAULTS: dict[str, Any] = {
    "voice_mic_enabled": True,
    "voice_mic_mode": "push_to_talk",
    "voice_tts_enabled": True,
    "voice_auto_read_aloud": False,
    "voice_language": "en-US",
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
        "stt": stt,
        "tts": tts,
        "mic_usable": bool(mic_enabled() and stt.get("available")),
        "tts_usable": bool(tts_enabled() and tts.get("available")),
    }
