"""P1.1 — Notes workspace + attach-to-chat full-context inject.

CRUD under data/notes/, search, attach context block, AI rewrite soft-degrade.
No GPL OWUI blobs — Studio reimplementation.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.services.chat import notes_store as ns  # noqa: E402


def _iso_notes(td: Path):
    return patch.object(ns, "notes_dir", lambda: td)


def test_crud_and_search():
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)
        with _iso_notes(td):
            assert ns.list_notes() == []
            n = ns.create_note(title="Alpha Plan", body="Ship the **notes** feature soon.")
            assert n["id"]
            assert n["title"] == "Alpha Plan"
            assert "notes" in n["body"]
            assert n["updated_at"]
            got = ns.get_note(n["id"])
            assert got and got["title"] == "Alpha Plan"
            upd = ns.update_note(n["id"], title="Alpha Plan v2", body="Updated body with widget")
            assert upd and upd["title"] == "Alpha Plan v2"
            assert upd["updated_at"] >= n["updated_at"]
            n2 = ns.create_note(title="Beta", body="unrelated")
            hits = ns.search_notes("widget")
            assert len(hits) == 1 and hits[0]["id"] == n["id"]
            hits2 = ns.search_notes("alpha plan")
            assert any(h["id"] == n["id"] for h in hits2)
            assert ns.delete_note(n["id"]) is True
            assert ns.get_note(n["id"]) is None
            assert ns.delete_note("missing-id-xyz") is False
            assert len(ns.list_notes()) == 1
    print("✓ CRUD + search")


def test_attach_context_block_and_soft_miss():
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)
        with _iso_notes(td):
            a = ns.create_note(title="Spec", body="SPEC LINE ALPHA\n" + ("x" * 100))
            b = ns.create_note(title="Short", body="hello")
            block, res = ns.build_attach_context_block([a["id"], b["id"], "nope-id"])
            assert block
            assert "Attached notes" in block
            assert "SPEC LINE ALPHA" in block
            assert "Short" in block
            assert any(not r.get("ok") for r in res)
            assert "unresolved" in block.lower() or "missing" in block.lower()
            empty, er = ns.build_attach_context_block([])
            assert empty == "" and er == []
            # truncation
            big = ns.create_note(title="Big", body="Z" * 50_000)
            blk2, res2 = ns.build_attach_context_block([big["id"]], max_chars_per=200)
            assert "truncated" in blk2.lower() or any(r.get("truncated") for r in res2)
    print("✓ attach context + soft miss + truncate")


def test_rewrite_soft_degrade_no_key():
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)
        with _iso_notes(td):
            with patch("app.core.services.chat.notes_store.resolve_active_llm", create=True):
                pass
            # Force no key via fake resolve + load_config
            with patch(
                "app.core.services.llm.providers.resolve_active_llm",
                return_value={"api_key": "", "base_url": "http://x", "model": "m"},
            ), patch(
                "app.core.services.data.storage.load_config",
                return_value={"api_key": ""},
            ):
                res = ns.rewrite_text("Please rewrite this sentence.")
                assert res["ok"] is False
                assert "key" in (res.get("note") or "").lower() or "soft" in (
                    res.get("note") or ""
                ).lower()
                assert res["text"] == "Please rewrite this sentence."

            # With mock completion
            def fake_cc(**kwargs):
                return "Rewritten clearly."

            with patch(
                "app.core.services.llm.providers.resolve_active_llm",
                return_value={
                    "api_key": "sk-test",
                    "base_url": "http://x",
                    "model": "m",
                },
            ):
                res2 = ns.rewrite_text("raw text", chat_completion_fn=fake_cc)
                assert res2["ok"] is True
                assert res2["text"] == "Rewritten clearly."

            # empty selection
            res3 = ns.rewrite_text("   ")
            assert res3["ok"] is False
    print("✓ rewrite soft-degrade + mock ok")


def test_persist_files_on_disk():
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)
        with _iso_notes(td):
            n = ns.create_note(title="Disk", body="persist me")
            path = td / f"{n['id']}.json"
            assert path.is_file()
            raw = path.read_text(encoding="utf-8")
            assert "persist me" in raw
            assert "Disk" in raw
    print("✓ persist JSON under data/notes/")


def test_preview_and_normalize():
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)
        with _iso_notes(td):
            n = ns.create_note(title="", body="a" * 200)
            assert n["title"] == "Untitled"
            prev = ns.preview_text(n, limit=40)
            assert len(prev) <= 40
            assert prev.endswith("…")
    print("✓ preview + untitled normalize")




def test_version_and_wiring():
    from app.version import __version__
    assert __version__ == "1.27.90", f"expected 1.27.90 got {__version__}"
    from app.core.services.chat.chat import send_user_message
    import inspect
    sig = inspect.signature(send_user_message)
    assert "attached_note_ids" in sig.parameters
    from app.paths import notes_dir
    assert notes_dir().name == "notes"
    print("✓ version + send_user_message wiring")


if __name__ == "__main__":
    test_crud_and_search()
    test_attach_context_block_and_soft_miss()
    test_rewrite_soft_degrade_no_key()
    test_persist_files_on_disk()
    test_preview_and_normalize()
    test_version_and_wiring()
    print("\nAll P1.1 notes tests passed.")
