"""P0.4 — Hybrid RAG (BM25 + embeddings + RRF / cross-score).

Tests use a temp SQLite knowledge DB (no heavy vector DB). Soft-degrade
path covered when embeddings are forced off.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.services.data import rag_knowledge as rag  # noqa: E402
from app.core.services.ai import local_embeddings as le  # noqa: E402


def _iso_db(td: Path):
    """Point rag DB at a temp dir for isolated tests."""
    return patch.multiple(
        rag,
        db_path=lambda: td / "rag.sqlite",
        sources_dir=lambda: (td / "sources").mkdir(parents=True, exist_ok=True) or (td / "sources"),
    )


def test_reciprocal_rank_fusion_prefers_consensus():
    a = [
        {"doc_id": "d", "chunk_index": 0, "content": "alpha"},
        {"doc_id": "d", "chunk_index": 1, "content": "beta"},
        {"doc_id": "d", "chunk_index": 2, "content": "gamma"},
    ]
    b = [
        {"doc_id": "d", "chunk_index": 1, "content": "beta"},
        {"doc_id": "d", "chunk_index": 3, "content": "delta"},
        {"doc_id": "d", "chunk_index": 0, "content": "alpha"},
    ]
    merged = rag.reciprocal_rank_fusion([a, b], weights=[0.5, 0.5], k=60)
    assert merged[0]["chunk_index"] == 1  # in both lists near top
    assert merged[0]["rrf_score"] >= merged[1]["rrf_score"]
    # weight extremes
    only_a = rag.reciprocal_rank_fusion([a, b], weights=[1.0, 0.0], k=60)
    assert [h["chunk_index"] for h in only_a[:3]] == [0, 1, 2]
    print("✓ RRF consensus + weight extremes")


def test_hybrid_rag_enabled_default_on():
    assert rag.hybrid_rag_enabled({}) is True
    assert rag.hybrid_rag_enabled({"hybrid_rag_enabled": True}) is True
    assert rag.hybrid_rag_enabled({"hybrid_rag_enabled": False}) is False
    assert 0.0 <= rag.hybrid_bm25_weight({}) <= 1.0
    assert rag.hybrid_bm25_weight({"hybrid_rag_bm25_weight": 0.7}) == 0.7
    assert rag.hybrid_bm25_weight({"hybrid_rag_bm25_weight": 9}) == 1.0
    print("✓ settings helpers")


def test_hybrid_search_lexical_and_hybrid(tmp_path: Path | None = None):
    with tempfile.TemporaryDirectory() as td_s:
        td = Path(td_s)
        with _iso_db(td):
            # clear any leftover from shared default path is avoided via patch
            f1 = td / "notes_alpha.md"
            f1.write_text(
                "Alpha project uses OAuth tokens for API access.\n\n"
                "More alpha details about authentication flow.\n",
                encoding="utf-8",
            )
            f2 = td / "notes_beta.md"
            f2.write_text(
                "Beta gardening tips: water the roses weekly.\n\n"
                "Soil and sunlight for flowering plants.\n",
                encoding="utf-8",
            )
            r1 = rag.index_file(f1)
            r2 = rag.index_file(f2)
            assert r1.get("ok") and r2.get("ok")

            # Lexical-only path
            hits_lex = rag.hybrid_search(
                "OAuth API authentication",
                limit=4,
                use_embeddings=False,
                bm25_weight=1.0,
            )
            assert hits_lex, "expected lexical hits"
            joined = " ".join(h.get("content") or "" for h in hits_lex)
            assert "OAuth" in joined or "Alpha" in joined or "authentication" in joined.lower()
            assert hits_lex[0].get("method") == "lexical"

            # Index hashing embeddings then hybrid
            # Point local_embeddings db_path at same temp db
            with patch.object(le, "db_path", rag.db_path):
                emb = le.index_embeddings_for_all(limit=100)
                assert emb.get("ok")
                hits_hy = rag.hybrid_search(
                    "OAuth tokens API",
                    limit=4,
                    use_embeddings=True,
                    bm25_weight=0.5,
                    rerank=True,
                )
                assert hits_hy
                assert hits_hy[0].get("method") in ("hybrid", "lexical", "vector")
                # citations / paths present for clickable Sources
                assert any(h.get("path") for h in hits_hy)
                block = rag.build_context_block_hybrid("OAuth tokens", limit=3)
                assert "Local Knowledge" in block
                assert "file://" in block or "Citation index" in block
                assert "[1]" in block

            # Soft-degrade: pretend embeddings module missing
            with patch.object(rag, "_embeddings_available", lambda: False):
                soft = rag.hybrid_search(
                    "OAuth",
                    limit=3,
                    use_embeddings=True,
                    bm25_weight=0.5,
                )
                assert soft
                assert soft[0].get("method") == "lexical"
    print("✓ hybrid_search lexical + hybrid + soft-degrade")


def test_build_context_respects_toggle():
    with tempfile.TemporaryDirectory() as td_s:
        td = Path(td_s)
        with _iso_db(td):
            f = td / "spec.md"
            f.write_text("Widget SERIAL-42 calibration procedure.\n", encoding="utf-8")
            assert rag.index_file(f).get("ok")
            with patch.object(rag, "hybrid_rag_enabled", lambda cfg=None: True):
                # even with hybrid on, empty query → empty
                assert rag.build_context_block("") == ""
                block = rag.build_context_block("SERIAL-42 calibration")
                assert "Knowledge" in block
                assert "SERIAL-42" in block or "calibration" in block.lower()
            with patch.object(rag, "hybrid_rag_enabled", lambda cfg=None: False):
                block2 = rag.build_context_block("SERIAL-42 calibration")
                assert "Knowledge" in block2
    print("✓ build_context_block toggle")


def test_cross_score_rerank_blend():
    hits = [
        {"doc_id": "a", "chunk_index": 0, "bm25_norm": 1.0, "emb_score": 0.1, "content": "x"},
        {"doc_id": "a", "chunk_index": 1, "bm25_norm": 0.2, "emb_score": 0.9, "content": "y"},
    ]
    # favor embeddings → chunk 1 first
    out = rag.cross_score_rerank(hits, bm25_weight=0.0)
    assert out[0]["chunk_index"] == 1
    # favor bm25 → chunk 0 first
    out2 = rag.cross_score_rerank(hits, bm25_weight=1.0)
    assert out2[0]["chunk_index"] == 0
    print("✓ cross_score_rerank")


def test_local_embeddings_delegates():
    """Wrapper still importable and calls rag hybrid."""
    with patch(
        "app.core.services.data.rag_knowledge.hybrid_search",
        return_value=[{"content": "hi", "path": "/t", "title": "t"}],
    ) as m:
        out = le.hybrid_search("q", limit=2)
        assert out and out[0]["content"] == "hi"
        m.assert_called()
    print("✓ local_embeddings.hybrid_search delegates")


def test_path_to_file_uri_clickable():
    uri = rag.path_to_file_uri("/tmp/example.md")
    assert uri.startswith("file:")
    print("✓ file:// citations")


if __name__ == "__main__":
    test_reciprocal_rank_fusion_prefers_consensus()
    test_hybrid_rag_enabled_default_on()
    test_hybrid_search_lexical_and_hybrid()
    test_build_context_respects_toggle()
    test_cross_score_rerank_blend()
    test_local_embeddings_delegates()
    test_path_to_file_uri_clickable()
    print("\nAll P0.4 hybrid RAG tests passed.")
