"""P2.1 — Better voice: OpenAI Whisper STT + OpenAI/ElevenLabs TTS.

Multi-provider engines, settings, soft-degrade, mocked HTTP.
No GPL OWUI blobs — Studio reimplementation.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _FakeHTTPResponse:
    def __init__(self, data: bytes, status: int = 200):
        self._data = data
        self.status = status

    def read(self) -> bytes:
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _FakeHTTPError(Exception):
    def __init__(self, code: int, body: bytes = b"{}"):
        self.code = code
        self._body = body

    def read(self) -> bytes:
        return self._body


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
    from app.core.services.data import storage as stor

    check(__version__ == "1.27.94", f"version is 1.27.94 (got {__version__})")

    # Defaults include new engine keys
    d = vs.ensure_defaults({})
    check(d.get("voice_stt_engine") == "local", "default stt engine local")
    check(d.get("voice_tts_engine") == "local", "default tts engine local")
    check(d.get("voice_tts_voice") == "alloy", "default tts voice")
    check(d.get("voice_stt_model") == "whisper-1", "default stt model")
    check("voice_elevenlabs_api_key" in d, "elevenlabs key default present")
    bad = vs.ensure_defaults({"voice_stt_engine": "weird", "voice_tts_engine": "nope"})
    check(bad.get("voice_stt_engine") == "local", "invalid stt engine normalized")
    check(bad.get("voice_tts_engine") == "local", "invalid tts engine normalized")

    prev = stor.load_config()
    try:
        vs.set_stt_engine("openai_whisper")
        check(vs.stt_engine() == "openai_whisper", "set_stt_engine openai_whisper")
        vs.set_stt_engine("local")
        check(vs.stt_engine() == "local", "set_stt_engine local")
        vs.set_tts_engine("openai")
        check(vs.tts_engine() == "openai", "set_tts_engine openai")
        vs.set_tts_engine("elevenlabs")
        check(vs.tts_engine() == "elevenlabs", "set_tts_engine elevenlabs")
        vs.set_tts_engine("local")
        vs.set_tts_voice("nova")
        check(vs.tts_voice() == "nova", "tts_voice nova")
        vs.set_tts_voice("alloy")
        vs.set_elevenlabs_api_key("el_test_key")
        check(vs.elevenlabs_api_key() == "el_test_key", "elevenlabs key round-trip")
        vs.set_elevenlabs_api_key("")
        summary = vs.voice_status_summary()
        check(summary.get("stt_engine") == "local", "summary stt_engine")
        check("has_elevenlabs_key" in summary, "summary has_elevenlabs_key")
    finally:
        stor.save_config(prev)

    # Capability probes never raise
    scap = stt.stt_capability()
    tcap = tts.tts_capability()
    check(isinstance(scap, dict) and "available" in scap and "selected" in scap, "stt_capability shape")
    check(isinstance(tcap, dict) and "available" in tcap and "selected" in tcap, "tts_capability shape")

    # openai_whisper probe without key → unavailable + clear hint
    with mock.patch.object(vs, "resolve_openai_creds", return_value={"api_key": "", "base_url": "https://api.openai.com/v1"}):
        with mock.patch.object(vs, "stt_engine", return_value="openai_whisper"):
            p = stt.stt_capability()
    check(p.get("available") is False, "whisper probe no key → unavailable")
    check("API key" in str(p.get("detail") or "") or "api key" in str(p.get("hint") or "").lower(), "whisper missing key message")

    # openai TTS probe without key
    with mock.patch.object(vs, "resolve_openai_creds", return_value={"api_key": "", "base_url": "https://api.openai.com/v1"}):
        with mock.patch.object(vs, "tts_engine", return_value="openai"):
            tp = tts.tts_capability()
    check(tp.get("available") is False, "openai tts probe no key → unavailable")
    check("API key" in str(tp.get("detail") or ""), "openai tts missing key message")

    # elevenlabs probe without key
    with mock.patch.object(vs, "elevenlabs_api_key", return_value=""):
        with mock.patch.object(vs, "tts_engine", return_value="elevenlabs"):
            ep = tts.tts_capability()
    check(ep.get("available") is False, "elevenlabs probe no key → unavailable")
    check("ElevenLabs" in str(ep.get("detail") or ""), "elevenlabs missing key message")

    # Mocked Whisper HTTP transcription
    wav = Path("/tmp/studio_test_whisper.wav")
    wav.write_bytes(b"RIFF" + b"\x00" * 40)  # minimal stub bytes
    fake_json = json.dumps({"text": "hello studio whisper"}).encode("utf-8")

    def _urlopen_ok(req, timeout=120):
        return _FakeHTTPResponse(fake_json)

    with mock.patch("urllib.request.urlopen", side_effect=_urlopen_ok):
        with mock.patch.object(
            vs, "resolve_openai_creds", return_value={"api_key": "sk-test", "base_url": "https://api.openai.com/v1"}
        ):
            tres = stt.transcribe_openai_whisper(str(wav), language="en-US", api_key="sk-test", base_url="https://api.openai.com/v1")
    check(tres.get("ok") is True and tres.get("text") == "hello studio whisper", f"whisper mock ok {tres}")
    check(tres.get("engine") == "openai_whisper", "whisper engine tag")

    # Mocked Whisper HTTP error
    import urllib.error as ue

    def _urlopen_401(req, timeout=120):
        raise ue.HTTPError(req.full_url if hasattr(req, "full_url") else "http://x", 401, "Unauthorized", hdrs=None, fp=io.BytesIO(b'{"error":{"message":"bad key"}}'))

    with mock.patch("urllib.request.urlopen", side_effect=_urlopen_401):
        err = stt.transcribe_openai_whisper(str(wav), api_key="bad", base_url="https://api.openai.com/v1")
    check(err.get("ok") is False and err.get("degraded") is True, f"whisper 401 degraded {err}")
    check("401" in str(err.get("error") or ""), "whisper 401 in error")

    # Mocked OpenAI TTS synthesis
    mp3_bytes = b"ID3fake-mp3-audio"

    def _urlopen_mp3(req, timeout=120):
        return _FakeHTTPResponse(mp3_bytes)

    out_mp3 = Path("/tmp/studio_test_tts.mp3")
    with mock.patch("urllib.request.urlopen", side_effect=_urlopen_mp3):
        syn = tts.synthesize_openai_tts(
            "hello",
            api_key="sk-test",
            base_url="https://api.openai.com/v1",
            model="tts-1",
            voice="alloy",
            out_path=str(out_mp3),
        )
    check(syn.get("ok") is True and Path(syn["path"]).is_file(), f"openai tts syn {syn}")
    check(Path(syn["path"]).read_bytes() == mp3_bytes, "openai tts bytes written")
    check(syn.get("engine") == "openai", "openai tts engine tag")

    # OpenAI TTS missing key
    miss = tts.synthesize_openai_tts("hi", api_key="", base_url="https://api.openai.com/v1")
    check(miss.get("ok") is False and miss.get("degraded") is True, "openai tts no key degraded")

    # Mocked ElevenLabs synthesis
    with mock.patch("urllib.request.urlopen", side_effect=_urlopen_mp3):
        el = tts.synthesize_elevenlabs_tts(
            "hello",
            api_key="el-key",
            voice_id="voice123",
            out_path=str(Path("/tmp/studio_test_el.mp3")),
        )
    check(el.get("ok") is True and el.get("engine") == "elevenlabs", f"elevenlabs syn {el}")

    # ElevenLabs missing key soft stub
    el_miss = tts.synthesize_elevenlabs_tts("hi", api_key="", voice_id="x")
    check(el_miss.get("ok") is False and "ElevenLabs" in str(el_miss.get("error") or el_miss.get("hint") or ""), "elevenlabs no key")

    # Soft-degrade speak when openai selected but no key → falls to local (may still fail without engine)
    with mock.patch.object(vs, "tts_engine", return_value="openai"):
        with mock.patch.object(vs, "resolve_openai_creds", return_value={"api_key": "", "base_url": "https://api.openai.com/v1"}):
            with mock.patch.object(tts, "_speak_local", return_value={"ok": True, "engine": "pyttsx3"}):
                sres = tts.speak_text("hello world", async_play=False)
    check(sres.get("ok") is True and (sres.get("engine") == "pyttsx3" or sres.get("fallback_from") == "openai"), f"openai→local fallback {sres}")

    # Soft-degrade listen when whisper selected but no key → local path
    with mock.patch.object(vs, "stt_engine", return_value="openai_whisper"):
        with mock.patch.object(vs, "resolve_openai_creds", return_value={"api_key": "", "base_url": "https://api.openai.com/v1"}):
            with mock.patch.object(stt, "_listen_local", return_value={"ok": True, "text": "local hi", "engine": "speech_recognition"}):
                lres = stt.listen_once()
    check(lres.get("ok") is True and lres.get("text") == "local hi", f"whisper→local fallback {lres}")
    check(lres.get("fallback_from") == "openai_whisper", "fallback_from tagged")

    # Strip markdown still works
    cleaned = tts._strip_for_speech("Hello **world** and `code`")
    check("Hello" in cleaned and "world" in cleaned, "strip markdown")

    # UI wiring: Settings engine pickers + test buttons
    aw = (ROOT / "app" / "ui" / "app_window.py").read_text(encoding="utf-8")
    check("voice_stt_engine" in aw, "Settings STT engine")
    check("voice_tts_engine" in aw, "Settings TTS engine")
    check("openai_whisper" in aw, "Settings openai_whisper option")
    check("elevenlabs" in aw, "Settings elevenlabs option")
    check("Test STT" in aw and "Test TTS" in aw, "Settings test buttons")
    check("voice_elevenlabs_api_key" in aw, "Settings elevenlabs key save")
    check("_voice_test_stt" in aw and "_voice_test_tts" in aw, "test handlers")

    # Services expose helpers
    check(hasattr(stt, "transcribe_openai_whisper"), "transcribe_openai_whisper export")
    check(hasattr(tts, "synthesize_openai_tts"), "synthesize_openai_tts export")
    check(hasattr(tts, "synthesize_elevenlabs_tts"), "synthesize_elevenlabs_tts export")

    # Docs / version
    ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    check(ver == "1.27.94", f"VERSION file {ver}")
    man = json.loads((ROOT / "version_manifest.json").read_text(encoding="utf-8"))
    check(man.get("version") == "1.27.94", "version_manifest 1.27.94")
    cl = (ROOT / "docs" / "CHANGELOG.md").read_text(encoding="utf-8")
    check("1.27.94" in cl and ("P2.1" in cl or "Whisper" in cl or "voice" in cl.lower()), "CHANGELOG 1.27.94")
    feat = (ROOT / "docs" / "FEATURES.md").read_text(encoding="utf-8")
    check("1.27.94" in feat, "FEATURES 1.27.94")

    # cleanup temp files
    for p in (wav, out_mp3, Path("/tmp/studio_test_el.mp3")):
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass

    if fails:
        print("\nFAILED:")
        for f in fails:
            print(" -", f)
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
