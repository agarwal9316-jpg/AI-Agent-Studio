"""Roadmap — Export/import full studio bundle (data zip) (1.27.99).

Round-trip with temp dirs: export selected data/, redact secrets by default,
import merge/replace, soft-degrade on bad zip.
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.version import __version__  # noqa: E402
from app.core.services.misc import studio_bundle as sb  # noqa: E402


def test_version():
    assert __version__ == "1.27.99", __version__
    print("✓ version 1.27.99")


def _seed(data: Path) -> None:
    data.mkdir(parents=True, exist_ok=True)
    (data / "config.json").write_text(
        json.dumps(
            {
                "api_key": "sk-secret-SHOULD-REDACT-12345678",
                "model": "grok-test",
                "theme": "dark",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (data / "providers.json").write_text(
        json.dumps(
            {
                "active_provider_id": "xai",
                "providers": [
                    {
                        "id": "xai",
                        "name": "xAI",
                        "base_url": "https://api.x.ai/v1",
                        "keys": [
                            {
                                "id": "k1",
                                "label": "main",
                                "key": "sk-xai-SUPERSECRET-99999999",
                            }
                        ],
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (data / "automations.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "id": "auto1",
                        "name": "Morning",
                        "prompt": "Say hi",
                        "schedule_kind": "daily",
                        "enabled": True,
                    }
                ],
                "updated_at": "2026-01-01T00:00:00+00:00",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    chats = data / "chats"
    chats.mkdir(exist_ok=True)
    (chats / "index.json").write_text(
        json.dumps(
            {
                "active_id": "c1",
                "chats": [
                    {"id": "c1", "title": "Alpha", "updated_at": "2026-01-01T00:00:00+00:00"}
                ],
                "folders": [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    # Full chat body should NOT be exported
    (chats / "c1.json").write_text(
        json.dumps({"id": "c1", "title": "Alpha", "messages": [{"role": "user", "content": "secret chat"}]}),
        encoding="utf-8",
    )
    notes = data / "notes"
    notes.mkdir(exist_ok=True)
    (notes / "n1.json").write_text(
        json.dumps({"id": "n1", "title": "Note One", "body": "hello note", "updated_at": "t"}),
        encoding="utf-8",
    )
    channels = data / "channels"
    channels.mkdir(exist_ok=True)
    (channels / "index.json").write_text(
        json.dumps({"active_id": "ch1", "channels": [{"id": "ch1", "name": "General"}]}),
        encoding="utf-8",
    )
    (channels / "ch1.json").write_text(
        json.dumps({"id": "ch1", "name": "General", "messages": [{"role": "user", "content": "hi"}]}),
        encoding="utf-8",
    )
    knowledge = data / "knowledge"
    knowledge.mkdir(exist_ok=True)
    (knowledge / "rag.sqlite").write_bytes(b"SQLiteFAKE")
    artifacts = data / "artifacts"
    artifacts.mkdir(exist_ok=True)
    (artifacts / "index.json").write_text(
        json.dumps({"items": [{"id": "a1", "title": "Art", "path": "blobs/a1/x.txt"}], "updated_at": "t"}),
        encoding="utf-8",
    )
    blobs = artifacts / "blobs" / "a1"
    blobs.mkdir(parents=True, exist_ok=True)
    (blobs / "x.txt").write_text("blob-should-not-export", encoding="utf-8")
    # excluded noise
    (data / "runs").mkdir(exist_ok=True)
    (data / "runs" / "r1.json").write_text("{}", encoding="utf-8")


def test_export_redacts_secrets_and_skips_excluded(tmp_path: Path):
    data = tmp_path / "data"
    _seed(data)
    dest = tmp_path / "out.zip"
    result = sb.export_studio_bundle(dest, include_secrets=False, data_root=data)
    assert result.get("ok"), result
    assert dest.is_file()
    with zipfile.ZipFile(dest, "r") as zf:
        names = set(zf.namelist())
        assert "studio_bundle.json" in names
        assert "data/config.json" in names
        assert "data/providers.json" in names
        assert "data/automations.json" in names
        assert "data/chats/index.json" in names
        assert "data/notes/n1.json" in names
        assert "data/channels/ch1.json" in names
        assert "data/knowledge/rag.sqlite" in names
        assert "data/artifacts/index.json" in names
        # excluded
        assert "data/chats/c1.json" not in names
        assert not any("blobs/" in n for n in names)
        assert "data/runs/r1.json" not in names
        cfg = json.loads(zf.read("data/config.json"))
        assert "SHOULD-REDACT" not in json.dumps(cfg)
        assert cfg.get("api_key") in ("", "***REDACTED***")
        assert cfg.get("model") == "grok-test"
        prov = json.loads(zf.read("data/providers.json"))
        key = prov["providers"][0]["keys"][0]["key"]
        assert key == "***REDACTED***"
        assert "SUPERSECRET" not in json.dumps(prov)
    print("✓ export redacts secrets + skips chat bodies / artifact blobs / runs")


def test_export_include_secrets(tmp_path: Path):
    data = tmp_path / "data"
    _seed(data)
    dest = tmp_path / "sec.zip"
    result = sb.export_studio_bundle(dest, include_secrets=True, data_root=data)
    assert result.get("ok"), result
    with zipfile.ZipFile(dest, "r") as zf:
        cfg = json.loads(zf.read("data/config.json"))
        assert "SHOULD-REDACT" in cfg.get("api_key", "")
        prov = json.loads(zf.read("data/providers.json"))
        assert "SUPERSECRET" in prov["providers"][0]["keys"][0]["key"]
    print("✓ export include_secrets keeps keys")


def test_round_trip_merge_and_replace(tmp_path: Path):
    src_data = tmp_path / "src"
    _seed(src_data)
    zpath = tmp_path / "bundle.zip"
    assert sb.export_studio_bundle(zpath, include_secrets=False, data_root=src_data)["ok"]

    # Merge into empty target
    dst = tmp_path / "dst"
    dst.mkdir()
    r = sb.import_studio_bundle(zpath, mode="merge", data_root=dst)
    assert r.get("ok"), r
    assert (dst / "notes" / "n1.json").is_file()
    assert (dst / "chats" / "index.json").is_file()
    assert not (dst / "chats" / "c1.json").exists()  # never in zip
    assert (dst / "knowledge" / "rag.sqlite").read_bytes() == b"SQLiteFAKE"
    cfg = json.loads((dst / "config.json").read_text(encoding="utf-8"))
    assert cfg.get("model") == "grok-test"

    # Merge: local-only note kept; incoming note updated
    (dst / "notes" / "local.json").write_text(
        json.dumps({"id": "local", "title": "Local Only", "body": "keep"}),
        encoding="utf-8",
    )
    # Change source note and re-export
    (src_data / "notes" / "n1.json").write_text(
        json.dumps({"id": "n1", "title": "Note One Updated", "body": "new"}),
        encoding="utf-8",
    )
    z2 = tmp_path / "bundle2.zip"
    assert sb.export_studio_bundle(z2, data_root=src_data)["ok"]
    r2 = sb.import_studio_bundle(z2, mode="merge", data_root=dst)
    assert r2.get("ok"), r2
    assert (dst / "notes" / "local.json").is_file()
    n1 = json.loads((dst / "notes" / "n1.json").read_text(encoding="utf-8"))
    assert n1["title"] == "Note One Updated"

    # Replace notes category clears locals when notes present in zip
    r3 = sb.import_studio_bundle(z2, mode="replace", data_root=dst)
    assert r3.get("ok"), r3
    assert not (dst / "notes" / "local.json").exists()
    assert (dst / "notes" / "n1.json").is_file()
    print("✓ round-trip merge + replace")


def test_merge_preserves_local_secrets_when_zip_redacted(tmp_path: Path):
    src = tmp_path / "src"
    _seed(src)
    zpath = tmp_path / "b.zip"
    assert sb.export_studio_bundle(zpath, include_secrets=False, data_root=src)["ok"]

    dst = tmp_path / "dst"
    dst.mkdir()
    (dst / "config.json").write_text(
        json.dumps({"api_key": "sk-local-KEEPME-abcdefgh", "model": "old-model"}),
        encoding="utf-8",
    )
    r = sb.import_studio_bundle(zpath, mode="merge", data_root=dst)
    assert r.get("ok"), r
    cfg = json.loads((dst / "config.json").read_text(encoding="utf-8"))
    assert cfg["api_key"] == "sk-local-KEEPME-abcdefgh"
    assert cfg["model"] == "grok-test"
    print("✓ merge keeps local secrets over redacted placeholders")


def test_bad_zip_soft_degrade(tmp_path: Path):
    bad = tmp_path / "bad.zip"
    bad.write_text("not a zip", encoding="utf-8")
    r = sb.import_studio_bundle(bad, data_root=tmp_path / "d")
    assert r.get("ok") is False
    assert "zip" in (r.get("error") or "").lower() or "valid" in (r.get("error") or "").lower()

    empty = tmp_path / "empty.zip"
    with zipfile.ZipFile(empty, "w") as zf:
        zf.writestr("readme.txt", "no data")
    r2 = sb.import_studio_bundle(empty, data_root=tmp_path / "d2")
    assert r2.get("ok") is False

    missing = sb.import_studio_bundle(tmp_path / "nope.zip", data_root=tmp_path / "d3")
    assert missing.get("ok") is False

    # describe bad
    d = sb.describe_bundle(bad)
    assert d.get("ok") is False
    print("✓ bad zip soft-degrades (no raise)")


def test_list_bundle_sections():
    secs = sb.list_bundle_sections()
    ids = {s["id"] for s in secs}
    for need in ("config", "knowledge", "notes", "channels", "automations", "chats_meta", "artifacts_index"):
        assert need in ids
    print("✓ section inventory")


if __name__ == "__main__":
    import tempfile

    test_version()
    test_list_bundle_sections()
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)
        test_export_redacts_secrets_and_skips_excluded(td / "e1")
        test_export_include_secrets(td / "e2")
        test_round_trip_merge_and_replace(td / "e3")
        test_merge_preserves_local_secrets_when_zip_redacted(td / "e4")
        test_bad_zip_soft_degrade(td / "e5")
    print("ALL PASS")
