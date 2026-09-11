"""
Lightweight local embeddings for RAG re-ranking (no heavy ML required).

Uses hashed bag-of-words vectors + cosine similarity, stored alongside SQLite FTS.
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


def hybrid_search(query: str, *, limit: int = 8) -> list[dict[str, Any]]:
    """FTS candidates re-ranked by local embedding cosine."""
    hits = fts_search(query, limit=max(limit * 3, 12))
    if not hits:
        return []
    qv = embed_text(query)
    # try load vectors
    conn = sqlite3.connect(str(db_path()))
    conn.row_factory = sqlite3.Row
    _ensure_emb_table(conn)
    scored = []
    for h in hits:
        # FTS may not return row id — match by content prefix
        content = h.get("content") or ""
        row = conn.execute(
            "SELECT id FROM chunks WHERE content=? LIMIT 1",
            (content,),
        ).fetchone()
        score_emb = 0.0
        if row:
            er = conn.execute(
                "SELECT vector FROM chunk_embeddings WHERE chunk_id=?",
                (row["id"],),
            ).fetchone()
            if er and er["vector"]:
                vec = [float(x) for x in er["vector"].split(",")]
                score_emb = cosine(qv, vec)
            else:
                vec = embed_text(content)
                score_emb = cosine(qv, vec)
                conn.execute(
                    "INSERT OR REPLACE INTO chunk_embeddings(chunk_id, dim, vector) VALUES (?,?,?)",
                    (row["id"], DIM, ",".join(f"{v:.6f}" for v in vec)),
                )
        else:
            score_emb = cosine(qv, embed_text(content))
        scored.append({**h, "emb_score": round(score_emb, 4)})
    conn.commit()
    conn.close()
    scored.sort(key=lambda x: float(x.get("emb_score") or 0), reverse=True)
    return scored[:limit]


def build_context_block_hybrid(
    query: str,
    *,
    limit: int = 6,
    max_chars: int = 6000,
    path_prefix: str = "",
) -> str:
    hits = hybrid_search(query, limit=limit * 3 if path_prefix else limit)
    if path_prefix:
        try:
            pref = str(Path(path_prefix).expanduser().resolve()).lower()
        except Exception:  # noqa: BLE001
            pref = str(path_prefix).lower()
        hits = [h for h in hits if pref in str(h.get("path") or "").lower()][:limit]
    if not hits:
        from app.core.services.data.rag_knowledge import build_context_block

        return build_context_block(
            query, limit=limit, max_chars=max_chars, path_prefix=path_prefix
        )
    from app.core.services.data.rag_knowledge import path_to_file_uri, format_citation_sources

    parts = ["## Local Knowledge (hybrid FTS + embeddings)", ""]
    total = 0
    used: list[dict] = []
    for i, h in enumerate(hits, 1):
        snip = (h.get("content") or "")[:1200]
        title = h.get("title") or ""
        path = h.get("path") or ""
        uri = path_to_file_uri(path) if path else ""
        block = (
            f"### [{i}] {title} (score={h.get('emb_score')})\n"
            f"Source: {uri or path}\n\n{snip}\n"
        )
        if total + len(block) > max_chars:
            break
        parts.append(block)
        used.append(h)
        total += len(block)
    parts.append(
        "Cite sources inline like [1], [2]. End with a **Sources** list using "
        "the exact file:// links so the user can click them."
    )
    if used:
        parts.append("\n### Citation index\n" + format_citation_sources(used))
    return "\n".join(parts)
