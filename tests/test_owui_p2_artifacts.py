"""P2.2 — Artifacts persistent store (personal Saved library).

Metadata + blob under data/artifacts/, save-from-turn, search, export, soft-degrade.
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

from app.core.services.misc import artifacts_store as ast  # noqa: E402
from app.version import __version__  # noqa: E402


def _iso(td: Path):
    return patch.object(ast, "artifacts_dir", lambda: td)


def test_version():
    assert __version__ == "1.27.95", __version__
    print("✓ version 1.27.95")


def test_crud_search_tags():
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)
        with _iso(td):
            assert ast.list_artifacts() == []
            src = td / "hello.txt"
            src.write_text("hello artifact world", encoding="utf-8")
            res = ast.save_artifact(
                src,
                title="Hello Doc",
                chat_id="chat-1",
                tags=["report", "demo"],
            )
            assert res["ok"], res
            art = res["artifact"]
            assert art["id"]
            assert art["title"] == "Hello Doc"
            assert art["chat_id"] == "chat-1"
            assert "report" in art["tags"]
            assert art["mime"].startswith("text/")
            assert art["size"] > 0
            assert (td / art["path"]).is_file()

            got = ast.get_artifact(art["id"])
            assert got and got["title"] == "Hello Doc"

            hits = ast.search_artifacts("hello doc")
            assert len(hits) == 1 and hits[0]["id"] == art["id"]
            hits2 = ast.list_artifacts(chat_id="chat-1")
            assert len(hits2) == 1
            hits3 = ast.list_artifacts(tag="demo")
            assert len(hits3) == 1
            assert ast.list_artifacts(chat_id="other") == []

            # second artifact
            img = td / "pic.png"
            img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 24)
            r2 = ast.save_artifact(img, title="Pic", tags=["image"])
            assert r2["ok"]
            assert len(ast.list_artifacts()) == 2

            upd = ast.update_tags(art["id"], ["report", "v2"])
            assert upd["ok"] and "v2" in (upd["artifact"] or {}).get("tags", [])

            deleted = ast.delete_artifact(art["id"])
            assert deleted["ok"]
            assert ast.get_artifact(art["id"]) is None
            assert len(ast.list_artifacts()) == 1
            assert ast.delete_artifact("missing-xyz")["ok"] is False
    print("✓ CRUD + search + tags")


def test_save_from_turn_and_export():
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)
        with _iso(td):
            src = td / "report.md"
            src.write_text("# Findings\nAll good.\n", encoding="utf-8")
            turn = {
                "kind": "report",
                "title": "Findings",
                "path": str(src),
                "meta": "research pack",
                "source": "research",
            }
            res = ast.save_from_turn_item(turn, chat_id="c9")
            assert res["ok"], res
            art = res["artifact"]
            assert art["chat_id"] == "c9"
            assert "research" in art["tags"] or "report" in art["tags"]

            # diff without path
            dres = ast.save_from_turn_item(
                {
                    "kind": "diff",
                    "title": "Edit foo.py",
                    "path": "",
                    "diff": "- old\n+ new\n",
                    "source": "harness",
                },
                chat_id="c9",
            )
            assert dres["ok"], dres
            assert dres["artifact"]["kind"] == "diff"

            # link soft-saves pointer
            lres = ast.save_from_turn_item(
                {"kind": "link", "title": "docs", "path": "https://example.com/x"},
                chat_id="c9",
            )
            assert lres["ok"], lres

            # empty → soft fail
            bad = ast.save_from_turn_item({"kind": "file", "title": "x", "path": ""})
            assert bad["ok"] is False

            out = td / "exports" / "out.md"
            exp = ast.export_artifact(art["id"], out)
            assert exp["ok"], exp
            assert Path(exp["path"]).is_file()
            assert "Findings" in Path(exp["path"]).read_text(encoding="utf-8")
    print("✓ save-from-turn + export")


def test_soft_degrade_disk_errors():
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)
        with _iso(td):
            # missing source
            res = ast.save_artifact(td / "nope.bin", title="x")
            assert res["ok"] is False
            assert "not found" in (res.get("note") or "").lower() or "source" in (
                res.get("note") or ""
            ).lower()

            # export missing id
            exp = ast.export_artifact("missing", td / "out.bin")
            assert exp["ok"] is False

            # store_status ok on writable tmp
            st = ast.store_status()
            assert st.get("ok") is True
            assert st.get("writable") is True

            # force index write failure via unwritable parent simulation:
            # patch _write_json to raise OSError
            with patch(
                "app.core.services.misc.artifacts_store._write_json",
                side_effect=OSError("disk full"),
            ):
                src = td / "a.txt"
                src.write_text("a", encoding="utf-8")
                r = ast.save_artifact(src, title="A")
                assert r["ok"] is False
                assert "disk" in (r.get("note") or "").lower() or "error" in (
                    r.get("note") or ""
                ).lower()

            # list never raises even if index corrupt
            (td / "index.json").write_text("{not-json", encoding="utf-8")
            assert isinstance(ast.list_artifacts(), list)
    print("✓ soft-degrade disk errors")


def test_paths_helper():
    from app.paths import artifacts_dir

    d = artifacts_dir()
    assert d.name == "artifacts"
    assert d.is_dir()
    print("✓ artifacts_dir()")


def main() -> int:
    fails: list[str] = []

    def run(fn):
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            print(f"FAIL {fn.__name__}: {e}")
            fails.append(f"{fn.__name__}: {e}")

    run(test_version)
    run(test_crud_search_tags)
    run(test_save_from_turn_and_export)
    run(test_soft_degrade_disk_errors)
    run(test_paths_helper)

    # collect_artifacts still works (ephemeral)
    from app.services import artifacts as arts

    b = arts.collect_artifacts(messages=[], this_turn_only=True)
    assert b.get("ok") and "items" in b
    print("✓ ephemeral collect_artifacts still ok")

    if fails:
        print("FAILED:", fails)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
