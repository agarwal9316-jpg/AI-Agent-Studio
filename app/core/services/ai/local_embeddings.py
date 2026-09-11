"""
Lightweight local embeddings for Hybrid RAG (no heavy ML / vector DB).

Uses hashed bag-of-words vectors + cosine similarity, stored alongside SQLite FTS.
Hybrid retrieve (BM25 + RRF + cross-score) lives in rag_knowledge; this module
provides embed_text / index_embeddings_for_all and thin hybrid_search wrappers.
"""

from __future__ import annotations

import math
import re
import sqlite3
from pathlib import Path
from typing import Any

from app.core.services.data.rag_knowledge import db_path, search as fts_search

_TOKEN = re.compile(r"[A-Za-z0-9_]{2,}")
DIM = 384


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN.findall(text or "")]


def embed_text(text: str, dim: int = DIM) -> list[float]:
    """Hashing trick embedding (stable, fast, no model download)."""
    vec = [0.0] * dim
    tokens = _tokenize(text)
    if not tokens:
        return vec
    for t in tokens:
        h = hash(t)
        idx = abs(h) % dim
        sign = 1.0 if (h & 1) == 0 else -1.0
        vec[idx] += sign
    # L2 normalize
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    return sum(a[i] * b[i] for i in range(n))


def _ensure_emb_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chunk_embeddings (
            chunk_id INTEGER PRIMARY KEY,
            dim INTEGER,
            vector TEXT
        )
        """
    )
    conn.commit()


def index_embeddings_for_all(limit: int = 5000) -> dict[str, Any]:
    """Compute embeddings for chunks missing vectors."""
    conn = sqlite3.connect(str(db_path()))
    conn.row_factory = sqlite3.Row
    _ensure_emb_table(conn)
    rows = conn.execute(
        "SELECT id, content FROM chunks ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    n = 0
    for r in rows:
        exists = conn.execute(
            "SELECT 1 FROM chunk_embeddings WHERE chunk_id=?", (r["id"],)
        ).fetchone()
        if exists:
            continue
        vec = embed_text(r["content"] or "")
        conn.execute(
            "INSERT OR REPLACE INTO chunk_embeddings(chunk_id, dim, vector) VALUES (?,?,?)",
            (r["id"], DIM, ",".join(f"{v:.6f}" for v in vec)),
        )
        n += 1
    conn.commit()
    conn.close()
    return {"ok": True, "embedded": n}


def hybrid_search(query: str, *, limit: int = 8, path_prefix: str = "") -> list[dict[str, Any]]:
    """
    P0.4: delegate to rag_knowledge.hybrid_search (BM25 + embeddings + RRF).

    Kept here for Knowledge UI / callers that import local_embeddings.hybrid_search.
    Soft-degrades inside rag_knowledge when embeddings are unavailable.
    """
    from app.core.services.data.rag_knowledge import hybrid_search as _hybrid

    return _hybrid(query, limit=limit, path_prefix=path_prefix, use_embeddings=True)


def build_context_block_hybrid(
    query: str,
    *,
    limit: int = 6,
    max_chars: int = 6000,
    path_prefix: str = "",
) -> str:
    """Delegate to rag_knowledge hybrid context (clickable citations preserved)."""
    from app.core.services.data.rag_knowledge import (
        build_context_block,
        build_context_block_hybrid as _build_hybrid,
        hybrid_rag_enabled,
    )

    if hybrid_rag_enabled():
        block = _build_hybrid(
            query, limit=limit, max_chars=max_chars, path_prefix=path_prefix
        )
        if block:
            return block
    return build_context_block(
        query, limit=limit, max_chars=max_chars, path_prefix=path_prefix
    )
