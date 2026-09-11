"""Tests for PENDING_TASKS.md #18 — Voice in/out first-class."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    fails: list[str] = []

    def check(ok: bool, msg: str) -> None:
        print(("OK  " if ok else "FAIL") + " " + msg)
        if not ok:
            fails.append(msg)

    from app.version import __version__
    from app.core.services.ai import voice_settings as vs
    from app.core.services.ai import stt_service as stt
    from app.core.services.ai import tts_service as tts

    check(__version__ == "1.27.84", f"version is 1.27.84 (got {__version__})")

    # Defaults / settings API
    d = vs.ensure_defaults({})
    check(d.get("voice_mic_enabled") is True, "default mic enabled")
    check(d.get("voice_tts_enabled") is True, "default tts enabled")
    check(d.get("voice_auto_read_aloud") is False, "default auto-read off")
    check(d.get("voice_mic_mode") == "push_to_talk", "default mic mode")
    check(d.get("voice_language") == "en-US", "default language")
    bad = vs.ensure_defaults({"voice_mic_mode": "weird"})
    check(bad.get("voice_mic_mode") == "push_to_talk", "invalid mode normalized")

    # Capability probes never raise
    scap = stt.stt_capability()
    tcap = tts.tts_capability()
    check(isinstance(scap, dict) and "available" in scap and "detail" in scap, "stt_capability shape")
    check(isinstance(tcap, dict) and "available" in tcap and "detail" in tcap, "tts_capability shape")
    check(isinstance(scap.get("engines"), list), "stt engines list")
    check(isinstance(tcap.get("engines"), list), "tts engines list")

    summary = vs.voice_status_summary()
    check("mic_usable" in summary and "tts_usable" in summary, "voice_status_summary keys")
    check(summary.get("stt", {}).get("available") == scap.get("available"), "summary stt matches")

    # Soft-degrade: listen_once when unavailable returns ok=False, never raises
    with mock.patch.object(stt, "stt_capability", return_value={"available": False, "detail": "no mic", "hint": "install"}):
        res = stt.listen_once()
    check(res.get("ok") is False, "listen_once degraded ok=False")
    check(res.get("degraded") is True or "unavailable" in str(res.get("error") or "").lower() or res.get("error"), "listen_once error")

    # Soft-degrade: speak_text when unavailable
    with mock.patch.object(tts, "tts_capability", return_value={"available": False, "detail": "no tts", "hint": "install"}):
        sres = tts.speak_text("hello world", async_play=False)
    check(sres.get("ok") is False and sres.get("degraded") is True, "speak_text degraded")

    # Strip markdown for speech
    cleaned = tts._strip_for_speech("Hello **world** and `code` and [link](http://x)")
    check("Hello" in cleaned and "world" in cleaned and "http" not in cleaned, f"strip markdown {cleaned!r}")
    check(tts._strip_for_speech("") == "", "strip empty")
    check(tts._strip_for_speech("```\ncode\n```").find("code block") >= 0 or "code" in tts._strip_for_speech("```\nx\n```"), "strip fence")

    # stop/is_speaking safe when idle
    tts.stop_speaking()
    check(tts.is_speaking() is False, "is_speaking False idle")

    # Config getters/setters round-trip (temp config via storage mock)
    from app.core.services.data import storage as stor

    prev = stor.load_config()
    try:
        vs.set_mic_enabled(False)
        check(vs.mic_enabled() is False, "set_mic_enabled False")
        vs.set_mic_enabled(True)
        check(vs.mic_enabled() is True, "set_mic_enabled True")
        vs.set_mic_mode("toggle")
        check(vs.mic_mode() == "toggle", "mic_mode toggle")
        vs.set_mic_mode("push_to_talk")
        check(vs.mic_mode() == "push_to_talk", "mic_mode push")
        vs.set_tts_enabled(False)
        check(vs.tts_enabled() is False, "tts_enabled False")
        vs.set_tts_enabled(True)
        vs.set_auto_read_aloud(True)
        check(vs.auto_read_aloud() is True, "auto_read True")
        vs.set_auto_read_aloud(False)
        check(vs.auto_read_aloud() is False, "auto_read False")
        vs.set_voice_language("en-GB")
        check(vs.voice_language() == "en-GB", "language en-GB")
        vs.set_voice_language("en-US")
    finally:
        stor.save_config(prev)

    # continuous_running / stop safe
    stt.stop_continuous()
    check(stt.continuous_running() is False, "continuous not running")

    # start_continuous when unavailable invokes callback with degraded, does not hang
    seen: list[dict] = []
    with mock.patch.object(stt, "stt_capability", return_value={"available": False, "detail": "no eng"}):
        stt.start_continuous(lambda r: seen.append(r))
    check(seen and seen[0].get("ok") is False, f"continuous degraded callback {seen}")

    # UI wiring present
    aw = (ROOT / "app" / "ui" / "app_window.py").read_text(encoding="utf-8")
    check("voice_settings" in aw, "app_window imports voice_settings")
    check("_voice_refresh_composer_buttons" in aw, "composer refresh helper")
    check("_voice_maybe_auto_speak" in aw, "auto-speak helper")
    check("chat_speak_btn" in aw or "name_chat_composer_speak_btn" in aw, "speak button in composer")
    check("Voice (mic in / read-aloud out)" in aw, "Settings Voice section")
    check("voice_auto_read_aloud" in aw, "auto read-aloud setting")
    check("stt_capability" in aw and "tts_capability" in aw, "capability probes in Settings")

    wn = (ROOT / "app" / "ui" / "components" / "widget_names.py").read_text(encoding="utf-8")
    check("def name_chat_composer_speak_btn" in wn, "speak widget name helper")
    check("def name_chat_composer_mic_btn" in wn, "mic widget name helper")
    hh = (ROOT / "app" / "core" / "services" / "misc" / "hover_help.py").read_text(encoding="utf-8")
    check('"speak"' in hh, "hover_help speak key")

    # Modules importable; missing voice_settings was the thrash bug
    check((ROOT / "app" / "core" / "services" / "ai" / "voice_settings.py").is_file(), "voice_settings.py exists")

    # Docs / version
    pending = (ROOT / "docs" / "PENDING_TASKS.md").read_text(encoding="utf-8")
    import re

    m = re.search(r"\|\s*18\s*\|[^|]+\|[^|]+\|\s*\*\*done\*\*", pending)
    check(m is not None, "PENDING #18 row status **done**")
    check("1.27.84" in pending, "PENDING mentions 1.27.84")

    cl = (ROOT / "docs" / "CHANGELOG.md").read_text(encoding="utf-8")
    check("1.27.84" in cl and "#18" in cl, "CHANGELOG 1.27.84 #18")
    feat = (ROOT / "docs" / "FEATURES.md").read_text(encoding="utf-8")
    check("1.27.84" in feat and ("Voice" in feat or "voice" in feat), "FEATURES voice 1.27.84")

    ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    check(ver == "1.27.84", f"VERSION file {ver}")
    man = json.loads((ROOT / "version_manifest.json").read_text(encoding="utf-8"))
    check(man.get("version") == "1.27.84", "version_manifest 1.27.84")

    if fails:
        print("\nFAILED:")
        for f in fails:
            print(" -", f)
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
