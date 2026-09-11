"""P1.2 — Workspace Channels: timeline, @model ask, soft pins/threads.

CRUD under data/channels/, user posts without key, model ask soft-degrade.
No GPL OWUI blobs — Studio reimplementation. Does not touch team_channels.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.services.chat import channels_store as cs  # noqa: E402


def _iso(td: Path):
    return patch.object(cs, "channels_dir", lambda: td)


def test_crud_rename_delete():
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)
        with _iso(td):
            assert cs.list_channels() == []
            ch = cs.create_channel(name="general", description="daily sync")
            assert ch["id"] and ch["name"] == "general"
            assert ch["description"] == "daily sync"
            assert any(m.get("role") == "system" for m in ch["messages"])
            got = cs.get_channel(ch["id"])
            assert got and got["name"] == "general"
            items = cs.list_channels()
            assert len(items) == 1 and items[0]["id"] == ch["id"]
            hits = cs.list_channels(query="daily")
            assert len(hits) == 1
            ren = cs.rename_channel(ch["id"], "ops")
            assert ren and ren["name"] == "ops"
            assert cs.delete_channel(ch["id"]) is True
            assert cs.get_channel(ch["id"]) is None
            assert cs.delete_channel("missing") is False
            assert cs.list_channels() == []
    print("✓ CRUD + rename + delete + search")


def test_user_post_without_api_key():
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)
        with _iso(td):
            ch = cs.create_channel(name="chat")
            res = cs.post_user_message(ch["id"], "Hello team @grok-3")
            assert res and res["message"]["role"] == "user"
            assert res["message"]["content"] == "Hello team @grok-3"
            assert "grok-3" in res["message"]["mentions"]
            refreshed = cs.get_channel(ch["id"])
            assert refreshed and any(
                m.get("content") == "Hello team @grok-3" for m in refreshed["messages"]
            )
            # empty rejected
            assert cs.post_user_message(ch["id"], "   ") is None
    print("✓ user post works without API key + mentions")


def test_soft_pin_and_thread_reply():
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)
        with _iso(td):
            ch = cs.create_channel(name="pins")
            r1 = cs.post_user_message(ch["id"], "Root idea")
            mid = r1["message"]["id"]
            pinned = cs.toggle_pin(ch["id"], mid)
            assert pinned and pinned["pinned"] is True
            assert len(cs.list_pinned(ch["id"])) == 1
            pinned2 = cs.toggle_pin(ch["id"], mid)
            assert pinned2 and pinned2["pinned"] is False

            r2 = cs.post_user_message(
                ch["id"], "Thread reply", reply_to=mid, parent_id=mid
            )
            assert r2["message"]["parent_id"] == mid
            assert r2["message"]["reply_to"] == mid
            thread = cs.list_thread(ch["id"], mid)
            assert len(thread) >= 2
            assert thread[0]["id"] == mid
            # bad parent soft-ignored
            r3 = cs.post_user_message(ch["id"], "orphan", parent_id="nope")
            assert r3["message"]["parent_id"] is None
    print("✓ soft pin + thread reply")


def test_mention_extract():
    assert cs.extract_model_mentions("hi @gpt-4o and @xai/grok-3 please") == [
        "gpt-4o",
        "xai/grok-3",
    ]
    # email addresses should not count as mentions (word char before @)
    assert "host.com" not in cs.extract_model_mentions("email me@host.com")
    # @you filtered
    assert "you" not in [m.lower() for m in cs.extract_model_mentions("hey @you @grok-3")]
    assert "grok-3" in cs.extract_model_mentions("hey @you @grok-3")
    plain = cs.replace_mentions_for_prompt("Ask @grok-3 now")
    assert "@" not in plain or "grok-3" in plain
    print("✓ mention extract")


def test_ask_model_soft_degrade_no_key():
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)
        with _iso(td):
            ch = cs.create_channel(name="ask")
            with patch.object(
                cs,
                "resolve_model_for_ask",
                return_value={
                    "ok": True,
                    "api_key": "",
                    "base_url": "http://x",
                    "model": "m1",
                },
            ):
                res = cs.ask_model_reply(
                    ch["id"], model_id="m1", user_text="What is 2+2?", post_user=True
                )
                assert res["ok"] is False
                assert "key" in (res.get("note") or "").lower() or "soft" in (
                    res.get("note") or ""
                ).lower()
                # user post kept
                assert res.get("user_message") is not None
                refreshed = cs.get_channel(ch["id"])
                assert any(
                    m.get("content") == "What is 2+2?" for m in refreshed["messages"]
                )
                assert any(
                    "soft" in (m.get("content") or "").lower()
                    or "key" in (m.get("content") or "").lower()
                    for m in refreshed["messages"]
                    if m.get("role") == "system"
                )
    print("✓ ask_model soft-degrade keeps user post")


def test_ask_model_mock_ok():
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)
        with _iso(td):
            ch = cs.create_channel(name="ok")
            cs.post_user_message(ch["id"], "Context line")

            def fake_cc(**kwargs):
                assert kwargs.get("model") == "mock-model"
                assert kwargs.get("api_key") == "sk-test"
                assert any(m.get("role") == "system" for m in kwargs.get("messages") or [])
                return "Four."

            with patch.object(
                cs,
                "resolve_model_for_ask",
                return_value={
                    "ok": True,
                    "api_key": "sk-test",
                    "base_url": "http://x",
                    "model": "mock-model",
                },
            ):
                res = cs.ask_model_reply(
                    ch["id"],
                    model_id="mock-model",
                    user_text="2+2?",
                    post_user=True,
                    chat_completion_fn=fake_cc,
                )
                assert res["ok"] is True
                assert res["message"]["role"] == "model"
                assert res["message"]["content"] == "Four."
                assert res["message"]["model_id"] == "mock-model"
    print("✓ ask_model mock completion ok")


def test_persist_files_on_disk():
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)
        with _iso(td):
            ch = cs.create_channel(name="disk")
            cs.post_user_message(ch["id"], "persist me")
            path = td / f"{ch['id']}.json"
            assert path.is_file()
            raw = path.read_text(encoding="utf-8")
            assert "persist me" in raw
            assert "disk" in raw.lower() or "Disk" in raw or '"name": "disk"' in raw
            idx = td / "index.json"
            assert idx.is_file()
    print("✓ persist JSON under data/channels/")


def test_team_channels_untouched():
    """Org team_channel module path must remain distinct."""
    from app.paths import team_channels_dir, channels_dir

    assert channels_dir().name == "channels"
    assert team_channels_dir().name == "team_channels"
    assert channels_dir().name != team_channels_dir().name
    # importing team_channel still works
    from app.core.services.company import team_channel as tc

    assert hasattr(tc, "list_channels")
    print("✓ Org team_channels untouched")


def test_version_and_wiring():
    from app.version import __version__

    assert __version__ == "1.27.91", f"expected 1.27.91 got {__version__}"
    from app.paths import channels_dir

    assert channels_dir().name == "channels"
    # Avoid importing CustomTkinter/Tk in headless CI — check sources on disk
    page_py = ROOT / "app" / "ui" / "pages" / "channels_page.py"
    assert page_py.is_file()
    page_src = page_py.read_text(encoding="utf-8")
    assert "def page_channels" in page_src
    aw_src = (ROOT / "app" / "ui" / "app_window.py").read_text(encoding="utf-8")
    assert "channels_page.page_channels" in aw_src
    assert '"Channels"' in aw_src
    assert "Channels" in (ROOT / "app" / "ui" / "themes.py").read_text(encoding="utf-8")
    store_src = (ROOT / "app" / "core" / "services" / "chat" / "channels_store.py").read_text(
        encoding="utf-8"
    )
    assert "ask_model_reply" in store_src
    assert "gpl" in store_src.lower()
    print("✓ version + wiring")


if __name__ == "__main__":
    test_crud_rename_delete()
    test_user_post_without_api_key()
    test_soft_pin_and_thread_reply()
    test_mention_extract()
    test_ask_model_soft_degrade_no_key()
    test_ask_model_mock_ok()
    test_persist_files_on_disk()
    test_team_channels_untouched()
    test_version_and_wiring()
    print("\nAll P1.2 channels tests passed.")
