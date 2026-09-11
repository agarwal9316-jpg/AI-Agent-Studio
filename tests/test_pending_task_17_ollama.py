"""Tests for PENDING_TASKS.md #17 — Offline Ollama path clearly labeled."""

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
    from app.core.services.llm import ollama_local as ol
    from app.core.services.llm import providers as prov
    from app.core.services.llm import model_profiles as mp

    check(__version__ == "1.27.83", f"version is 1.27.83 (got {__version__})")

    check(ol.OFFLINE_LABEL == "Offline · Ollama (local)", "OFFLINE_LABEL constant")
    check(ol.DEFAULT_HOST == "http://127.0.0.1:11434", "DEFAULT_HOST")
    check(ol.DEFAULT_OPENAI_BASE == "http://127.0.0.1:11434/v1", "DEFAULT_OPENAI_BASE")
    check(ol.display_label() == ol.OFFLINE_LABEL, "display_label")

    check(ol.normalize_host("") == "http://127.0.0.1:11434", "normalize empty → default")
    check(ol.normalize_host("http://127.0.0.1:11434/v1") == "http://127.0.0.1:11434", "strip /v1")
    check(ol.normalize_host("127.0.0.1:11434") == "http://127.0.0.1:11434", "add scheme")
    check(ol.openai_base_from_host("http://127.0.0.1:11434") == "http://127.0.0.1:11434/v1", "openai base")
    check(ol.host_from_openai_base("http://127.0.0.1:11434/v1") == "http://127.0.0.1:11434", "host from base")

    check(ol.is_ollama_provider("ollama"), "is_ollama by id")
    check(ol.is_ollama_provider(name="Offline · Ollama (local)"), "is_ollama by label")
    check(ol.is_ollama_provider(base_url="http://127.0.0.1:11434/v1"), "is_ollama by url")
    check(not ol.is_ollama_provider("openrouter"), "not openrouter")

    # Soft-degrade health when down (mock urlopen failure)
    class _Boom(Exception):
        pass

    def _fail_urlopen(*_a, **_k):
        raise ConnectionRefusedError("Connection refused")

    with mock.patch("urllib.request.urlopen", side_effect=_fail_urlopen):
        h = ol.health("http://127.0.0.1:11434")
    check(h.get("running") is False, "health running False when down")
    check(h.get("ok") is False, "health ok False when down")
    check(h.get("offline") is True, "health offline True")
    check(h.get("label") == ol.OFFLINE_LABEL, "health label")
    check(isinstance(h.get("next_actions"), list) and len(h["next_actions"]) >= 2, "next_actions present")
    check("ollama serve" in " ".join(h["next_actions"]).lower() or "Start Ollama" in " ".join(h["next_actions"]), "start action")
    check("○" in (h.get("status_line") or ""), "status_line down marker")
    check(h.get("error"), "error string when down")

    # Soft-degrade: health never raises even on weird errors
    with mock.patch("urllib.request.urlopen", side_effect=RuntimeError("boom")):
        h2 = ol.health()
    check(h2.get("running") is False and "boom" in (h2.get("error") or ""), "health soft RuntimeError")

    # Health when up — mock tags response
    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(
                {"models": [{"name": "llama3.2:latest", "size": 1}, {"name": "qwen2.5:7b", "size": 2}]}
            ).encode("utf-8")

    with mock.patch("urllib.request.urlopen", return_value=_Resp()):
        hu = ol.health()
    check(hu.get("running") is True and hu.get("ok") is True, "health up")
    check(hu.get("model_names") == ["llama3.2:latest", "qwen2.5:7b"], f"model_names {hu.get('model_names')}")
    check("●" in (hu.get("status_line") or ""), "status_line up marker")
    check(ol.OFFLINE_LABEL in (hu.get("status_line") or ""), "label in status_line")

    # list_local_models / model_profiles wrappers
    with mock.patch("urllib.request.urlopen", side_effect=_fail_urlopen):
        lm = ol.list_local_models()
        mp_lm = mp.ollama_list_models()
    check(lm.get("running") is False and mp_lm.get("running") is False, "list wrappers when down")
    check(mp_lm.get("label") == ol.OFFLINE_LABEL or "Offline" in str(mp_lm.get("label") or ""), "mp label")

    # Provider preset labeled Offline
    presets = {p["id"]: p for p in prov.PROVIDER_PRESETS}
    check("ollama" in presets, "ollama in PROVIDER_PRESETS")
    check(presets["ollama"]["name"] == ol.OFFLINE_LABEL, f"preset name {presets['ollama']['name']}")
    check("11434" in presets["ollama"]["base_url"], "preset base has 11434")
    check("Offline" in (presets["ollama"].get("notes") or "") or "local" in (presets["ollama"].get("notes") or "").lower(), "preset notes")

    # ensure_offline_label renames legacy without wiping keys — isolate providers.json
    tmp = Path(tempfile.mkdtemp(prefix="ollama17_"))
    real_path = prov.providers_path
    fake = tmp / "providers.json"
    fake.write_text(
        json.dumps(
            {
                "active_provider_id": "openrouter",
                "active_key_id": "",
                "active_model": "",
                "providers": [
                    {
                        "id": "openrouter",
                        "name": "OpenRouter",
                        "base_url": "https://openrouter.ai/api/v1",
                        "models_path": "/models",
                        "notes": "",
                        "keys": [{"id": "k1", "label": "default", "key": "sk-or-test", "created_at": ""}],
                        "models_cache": [],
                        "models_fetched_at": "",
                        "enabled": True,
                    },
                    {
                        "id": "ollama",
                        "name": "Ollama (local)",
                        "base_url": "http://127.0.0.1:11434/v1",
                        "models_path": "/models",
                        "notes": "Local OpenAI-compatible; key can be ollama",
                        "keys": [{"id": "ok1", "label": "local", "key": "ollama", "created_at": ""}],
                        "models_cache": [],
                        "models_fetched_at": "",
                        "enabled": True,
                    },
                ],
                "updated_at": "",
            }
        ),
        encoding="utf-8",
    )
    prov.providers_path = lambda: fake  # type: ignore
    try:
        ol.ensure_offline_label()
        store = json.loads(fake.read_text(encoding="utf-8"))
        ollama_p = next(x for x in store["providers"] if x["id"] == "ollama")
        check(ollama_p["name"] == ol.OFFLINE_LABEL, f"migrated name {ollama_p['name']}")
        check(len(ollama_p.get("keys") or []) == 1, "keys preserved")
        check(ollama_p["keys"][0]["key"] == "ollama", "key value preserved")
        or_p = next(x for x in store["providers"] if x["id"] == "openrouter")
        check(or_p["keys"][0]["key"] == "sk-or-test", "other providers untouched")

        # fetch when down → clear error, does not wipe other providers
        with mock.patch("urllib.request.urlopen", side_effect=_fail_urlopen):
            res = ol.fetch_models_for_provider(force=True)
        check(res.get("ok") is False and res.get("running") is False, "fetch_models_for_provider down")
        check(res.get("next_actions"), "fetch down has next_actions")

        with mock.patch("urllib.request.urlopen", return_value=_Resp()):
            res_up = ol.fetch_models_for_provider(force=True)
        check(res_up.get("ok") is True, "fetch up ok")
        check(res_up.get("models") == ["llama3.2:latest", "qwen2.5:7b"], "fetch models cached list")
        store2 = json.loads(fake.read_text(encoding="utf-8"))
        o2 = next(x for x in store2["providers"] if x["id"] == "ollama")
        check(o2.get("models_cache") == ["llama3.2:latest", "qwen2.5:7b"], "models_cache updated")
        check(o2["name"] == ol.OFFLINE_LABEL, "name still Offline after fetch")
        or2 = next(x for x in store2["providers"] if x["id"] == "openrouter")
        check(or2["keys"][0]["key"] == "sk-or-test", "openrouter still intact after ollama fetch")

        # providers.fetch_models soft path raises clear RuntimeError when down
        with mock.patch("urllib.request.urlopen", side_effect=_fail_urlopen):
            raised = None
            try:
                prov.fetch_models("ollama", force=True)
            except RuntimeError as e:
                raised = str(e)
            check(raised is not None and "Offline" in raised, f"fetch_models clear error ({raised})")
    finally:
        prov.providers_path = real_path  # type: ignore

    # UI strings present
    mp_src = (ROOT / "app" / "ui" / "pages" / "models_page.py").read_text(encoding="utf-8")
    check("Offline · Ollama (local)" in mp_src, "models_page Offline label")
    check("127.0.0.1:11434" in mp_src, "models_page default URL hint")
    check("Check Offline Ollama" in mp_src or "next_actions" in mp_src, "models_page health UX")
    check("not a cloud API" in mp_src.lower() or "not a cloud API" in mp_src, "models_page cloud disclaimer")

    aw = (ROOT / "app" / "ui" / "app_window.py").read_text(encoding="utf-8")
    check("Offline · Ollama (local)" in aw, "Settings mentions Offline Ollama")
    check("127.0.0.1:11434" in aw, "Settings base URL hint")

    # Docs / version files
    pending = (ROOT / "docs" / "PENDING_TASKS.md").read_text(encoding="utf-8")
    check("| 17 |" in pending and "done" in pending.lower(), "PENDING #17 marked")
    # more precise: row 17 status
    import re

    m = re.search(r"\|\s*17\s*\|[^|]+\|[^|]+\|\s*\*\*done\*\*", pending)
    check(m is not None, "PENDING #17 row status **done**")
    check("1.27.83" in pending, "PENDING mentions 1.27.83")

    cl = (ROOT / "docs" / "CHANGELOG.md").read_text(encoding="utf-8")
    check("1.27.83" in cl and "#17" in cl, "CHANGELOG 1.27.83 #17")
    feat = (ROOT / "docs" / "FEATURES.md").read_text(encoding="utf-8")
    check("1.27.83" in feat and ("Offline" in feat and "Ollama" in feat), "FEATURES Offline Ollama")

    ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    check(ver == "1.27.83", f"VERSION file {ver}")
    man = json.loads((ROOT / "version_manifest.json").read_text(encoding="utf-8"))
    check(man.get("version") == "1.27.83", "version_manifest 1.27.83")

    # Other providers preset still present (soft-degrade / no break)
    for pid in ("openrouter", "xai", "openai", "groq"):
        check(pid in presets, f"preset {pid} still present")

    if fails:
        print("\nFAILED:")
        for f in fails:
            print(" -", f)
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
