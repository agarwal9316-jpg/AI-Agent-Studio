"""P0.3 — `#` doc + URL inject into chat context (OWUI-style).

Parse tokens, resolve knowledge/file/URL with soft-degrade, format context
block. No network in default tests (URL fetch mocked).
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.services.chat.hash_inject import (  # noqa: E402
    build_hash_inject_block,
    classify_token,
    hash_inject_help_text,
    parse_hash_tokens,
    resolve_file,
    resolve_hash_token,
    resolve_url,
    suggest_hash_completions,
)


def test_parse_hash_tokens_basic():
    text = "Summarize #notes.md and also #https://example.com/page please"
    toks = parse_hash_tokens(text)
    assert "notes.md" in toks
    assert "https://example.com/page" in toks
    # dedupe
    assert parse_hash_tokens("#a #a #b") == ["a", "b"]
    # markdown headings should not yield empty / weird
    assert "## Heading" not in " ".join(parse_hash_tokens("## Heading only"))
    assert parse_hash_tokens("no hashes here") == []
    print("✓ parse_hash_tokens")


def test_classify_token():
    assert classify_token("https://x.ai/blog") == "url"
    assert classify_token("http://localhost:8080/x") == "url"
    assert classify_token("C:\\Users\\me\\doc.txt") == "path"
    assert classify_token("/tmp/readme.md") == "path"
    assert classify_token("./rel/file.py") == "path"
    assert classify_token("../up.md") == "path"
    assert classify_token("~/notes.md") == "path"
    assert classify_token("notes.md") == "name"
    assert classify_token("my-collection") == "name"
    print("✓ classify_token")


def test_resolve_file_and_soft_miss(tmp_path: Path | None = None):
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        f = base / "hello.md"
        f.write_text("# Hello\n\nWorld content here.\n", encoding="utf-8")
        ok = resolve_file(str(f), max_chars=100)
        assert ok["ok"] is True
        assert "World" in ok["text"]
        assert ok["kind"] == "file"
        miss = resolve_file(str(base / "nope.txt"))
        assert miss["ok"] is False
        assert "not found" in (miss.get("note") or "").lower() or "File not found" in (
            miss.get("note") or ""
        )
        # relative to cwd
        rel = resolve_file("hello.md", cwd=base)
        assert rel["ok"] is True
    print("✓ resolve_file + soft miss")


def test_resolve_url_mocked():
    def fake_fetch(url: str, **kwargs: Any) -> dict[str, Any]:
        return {
            "ok": True,
            "url": url,
            "text": "Fetched body " * 50,
            "truncated": False,
        }

    res = resolve_url("https://example.com/a", max_chars=40, fetch_fn=fake_fetch)
    assert res["ok"] is True
    assert res["kind"] == "url"
    assert res["truncated"] is True or len(res["text"]) <= 40
    bad = resolve_url("https://fail.test", fetch_fn=lambda u, **k: {"ok": False, "error": "down"})
    assert bad["ok"] is False
    assert "down" in (bad.get("note") or "")
    print("✓ resolve_url mocked")


def test_build_block_file_and_unknown():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        f = base / "spec.txt"
        f.write_text("SPEC ALPHA BRAVO CHARLIE", encoding="utf-8")
        msg = f"Please use #{f.name} and #totally-missing-xyz and #https://example.org/x"
        fake = lambda url, **k: {"ok": True, "url": url, "text": "URL BODY", "truncated": False}
        block, res = build_hash_inject_block(
            msg,
            cwd=base,
            max_chars_per=500,
            fetch_fn=fake,
        )
        assert block
        assert "Hash inject" in block
        assert "SPEC ALPHA" in block
        assert "URL BODY" in block
        # unknown soft-degrades
        assert any(not r.get("ok") for r in res)
        assert "unresolved" in block.lower() or "Unknown" in block or "soft-degrade" in block.lower()
        # never raises on empty
        empty, er = build_hash_inject_block("hello only")
        assert empty == "" and er == []
    print("✓ build_hash_inject_block file+url+unknown")


def test_resolve_hash_token_dispatch():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        f = base / "x.md"
        f.write_text("payload", encoding="utf-8")
        r = resolve_hash_token(str(f), cwd=base)
        assert r["ok"] and "payload" in r["text"]
        r2 = resolve_hash_token(
            "https://x.test",
            fetch_fn=lambda u, **k: {"ok": True, "url": u, "text": "T", "truncated": False},
        )
        assert r2["ok"] and r2["kind"] == "url"
        r3 = resolve_hash_token("no-such-doc-zzz-999")
        assert r3["ok"] is False
        assert r3.get("note")
    print("✓ resolve_hash_token dispatch")


def test_suggest_and_help():
    hints = suggest_hash_completions("", limit=5)
    assert any("https" in (h.get("label") or "") for h in hints)
    help_t = hash_inject_help_text()
    assert "#https://" in help_t or "#https" in help_t
    assert "soft-degrade" in help_t.lower() or "Unknown" in help_t
    print("✓ suggest + help text")


def test_chat_wiring_imports():
    """send path imports hash_inject; package exports it."""
    from app.core.services.chat import hash_inject as hi
    from app.core.services import chat as chat_pkg

    assert hasattr(chat_pkg, "hash_inject")
    src = (ROOT / "app/core/services/chat/chat.py").read_text(encoding="utf-8")
    assert "build_hash_inject_block" in src
    assert "P0.3" in src or "Hash inject" in src
    ui = (ROOT / "app/ui/app_window.py").read_text(encoding="utf-8")
    assert "suggest_hash_completions" in ui
    assert "Hash inject" in ui
    # version bump target
    from app.version import __version__

    assert __version__ == "1.27.88", f"expected 1.27.88 got {__version__}"
    print("✓ chat/UI wiring + version 1.27.88")


def test_docs_mention_p03():
    cl = (ROOT / "docs/CHANGELOG.md").read_text(encoding="utf-8")
    assert "1.27.88" in cl and ("hash" in cl.lower() or "#" in cl)
    feat = (ROOT / "docs/FEATURES.md").read_text(encoding="utf-8")
    assert "1.27.88" in feat
    road = (ROOT / "docs/ROADMAP.md").read_text(encoding="utf-8")
    assert "1.27.88" in road or "hash inject" in road.lower() or "# doc" in road.lower()
    print("✓ docs mention P0.3 / 1.27.88")


def main() -> int:
    test_parse_hash_tokens_basic()
    test_classify_token()
    test_resolve_file_and_soft_miss()
    test_resolve_url_mocked()
    test_build_block_file_and_unknown()
    test_resolve_hash_token_dispatch()
    test_suggest_and_help()
    test_chat_wiring_imports()
    test_docs_mention_p03()
    print("All P0.3 hash-inject checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
