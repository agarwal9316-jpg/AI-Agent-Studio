"""
Local Knowledge RAG — index PDFs, Markdown, code, text into SQLite FTS5
and retrieve relevant chunks for chat (private, on-disk).
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.paths import data_dir

KNOWLEDGE_RE = re.compile(
    r"<<<KNOWLEDGE>>>\s*(.*?)\s*<<<END_KNOWLEDGE>>>",
    re.DOTALL | re.IGNORECASE,
)

TEXT_EXTS = {
    ".md",
    ".txt",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".csv",
    ".html",
    ".css",
    ".rs",
    ".go",
    ".java",
    ".c",
    ".cpp",
    ".h",
    ".cs",
    ".rb",
    ".php",
    ".sql",
    ".sh",
    ".ps1",
    ".bat",
    ".xml",
    ".rst",
    ".log",
}


def db_path() -> Path:
    d = data_dir() / "knowledge"
    d.mkdir(parents=True, exist_ok=True)
    return d / "rag.sqlite"


def sources_dir() -> Path:
    d = data_dir() / "knowledge" / "sources"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(db_path()))
    c.row_factory = sqlite3.Row
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            title TEXT,
            source_type TEXT,
            bytes INTEGER,
            mtime TEXT,
            indexed_at TEXT,
            chunk_count INTEGER DEFAULT 0
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id TEXT NOT NULL,
            chunk_index INTEGER,
            content TEXT NOT NULL,
            FOREIGN KEY(doc_id) REFERENCES documents(id)
        )
        """
    )
    # FTS5 virtual table
    c.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            content,
            doc_id UNINDEXED,
            chunk_index UNINDEXED,
            content='chunks',
            content_rowid='id'
        )
        """
    )
    c.execute(
        """
        CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
          INSERT INTO chunks_fts(rowid, content, doc_id, chunk_index)
          VALUES (new.id, new.content, new.doc_id, new.chunk_index);
        END
        """
    )
    c.execute(
        """
        CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
          INSERT INTO chunks_fts(chunks_fts, rowid, content, doc_id, chunk_index)
          VALUES('delete', old.id, old.content, old.doc_id, old.chunk_index);
        END
        """
    )
    c.commit()
    return c


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _doc_id(path: str) -> str:
    return hashlib.sha256(path.encode("utf-8", errors="replace")).hexdigest()[:20]


def chunk_text(text: str, *, size: int = 900, overlap: int = 120) -> list[str]:
    text = (text or "").replace("\r\n", "\n")
    if not text.strip():
        return []
    chunks = []
    i = 0
    n = len(text)
    while i < n:
        end = min(n, i + size)
        # prefer break at paragraph/newline
        if end < n:
            br = text.rfind("\n\n", i + size // 2, end)
            if br == -1:
                br = text.rfind("\n", i + size // 2, end)
            if br > i:
                end = br
        piece = text[i:end].strip()
        if piece:
            chunks.append(piece)
        if end >= n:
            break
        i = max(i + 1, end - overlap)
    return chunks


def read_file_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        # try pypdf / PyPDF2
        try:
            from pypdf import PdfReader  # type: ignore

            reader = PdfReader(str(path))
            parts = []
            for page in reader.pages:
                try:
                    parts.append(page.extract_text() or "")
                except Exception:  # noqa: BLE001
                    pass
            return "\n".join(parts)
        except ImportError:
            try:
                import PyPDF2  # type: ignore

                with path.open("rb") as f:
                    reader = PyPDF2.PdfReader(f)
                    return "\n".join((p.extract_text() or "") for p in reader.pages)
            except Exception as e:  # noqa: BLE001
                return f"[PDF read failed: {e}. pip install pypdf]"
        except Exception as e:  # noqa: BLE001
            return f"[PDF error: {e}]"
    if ext in TEXT_EXTS or ext == "":
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001
            return f"[Read failed: {e}]"
    # try utf-8 anyway for unknown
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def index_file(path: str | Path, *, title: str = "") -> dict[str, Any]:
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        return {"ok": False, "error": f"Not a file: {p}"}
    text = read_file_text(p)
    if not text.strip():
        return {"ok": False, "error": "Empty or unreadable file"}
    chunks = chunk_text(text)
    did = _doc_id(str(p))
    mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat()
    with _conn() as c:
        c.execute("DELETE FROM chunks WHERE doc_id=?", (did,))
        c.execute("DELETE FROM documents WHERE id=?", (did,))
        c.execute(
            """
            INSERT INTO documents(id, path, title, source_type, bytes, mtime, indexed_at, chunk_count)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                did,
                str(p),
                title or p.name,
                p.suffix.lower().lstrip(".") or "txt",
                p.stat().st_size,
                mtime,
                _now(),
                len(chunks),
            ),
        )
        for i, ch in enumerate(chunks):
            c.execute(
                "INSERT INTO chunks(doc_id, chunk_index, content) VALUES (?,?,?)",
                (did, i, ch),
            )
        c.commit()
    return {
        "ok": True,
        "doc_id": did,
        "path": str(p),
        "title": title or p.name,
        "chunks": len(chunks),
        "chars": len(text),
    }


def index_folder(
    folder: str | Path,
    *,
    recursive: bool = True,
    limit: int = 500,
) -> dict[str, Any]:
    root = Path(folder).expanduser().resolve()
    if not root.is_dir():
        return {"ok": False, "error": f"Not a folder: {root}"}
    pattern = "**/*" if recursive else "*"
    results = []
    errors = []
    n = 0
    for p in root.glob(pattern):
        if not p.is_file():
            continue
        if p.suffix.lower() not in TEXT_EXTS and p.suffix.lower() != ".pdf":
            continue
        if any(x in p.parts for x in (".venv", "node_modules", "__pycache__", ".git")):
            continue
        r = index_file(p)
        if r.get("ok"):
            results.append(r)
        else:
            errors.append({"path": str(p), "error": r.get("error")})
        n += 1
        if n >= limit:
            break
    return {
        "ok": True,
        "folder": str(root),
        "indexed": len(results),
        "errors": len(errors),
        "files": results[:50],
        "error_samples": errors[:10],
    }


def list_documents() -> list[dict[str, Any]]:
    with _conn() as c:
        rows = c.execute(
            "SELECT id, path, title, source_type, bytes, chunk_count, indexed_at FROM documents ORDER BY indexed_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def delete_document(doc_id: str) -> bool:
    with _conn() as c:
        c.execute("DELETE FROM chunks WHERE doc_id=?", (doc_id,))
        c.execute("DELETE FROM documents WHERE id=?", (doc_id,))
        c.commit()
    return True


def clear_all() -> None:
    with _conn() as c:
        c.execute("DELETE FROM chunks")
        c.execute("DELETE FROM documents")
        c.commit()


def _fts_query(q: str) -> str:
    # simple tokenize for FTS5
    terms = re.findall(r"[A-Za-z0-9_]{2,}", q or "")
    if not terms:
        return (q or "").strip().replace('"', " ")
    return " OR ".join(terms[:20])


def path_to_file_uri(path: str | Path) -> str:
    """Windows-safe file:// URI for clickable citations in chat."""
    try:
        p = Path(path).expanduser().resolve()
        # pathlib.as_uri() → file:///C:/...
        return p.as_uri()
    except Exception:  # noqa: BLE001
        s = str(path or "").strip()
        if not s:
            return ""
        if s.lower().startswith("file:"):
            return s
        return "file:///" + s.replace("\\", "/")


def search(
    query: str,
    *,
    limit: int = 8,
    path_prefix: str = "",
) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []
    fts = _fts_query(q)
    prefix = ""
    if path_prefix:
        try:
            prefix = str(Path(path_prefix).expanduser().resolve()).lower()
        except Exception:  # noqa: BLE001
            prefix = str(path_prefix).lower()
    with _conn() as c:
        try:
            rows = c.execute(
                """
                SELECT c.content, c.doc_id, c.chunk_index, d.path, d.title,
                       bm25(chunks_fts) AS score
                FROM chunks_fts
                JOIN chunks c ON c.id = chunks_fts.rowid
                JOIN documents d ON d.id = c.doc_id
                WHERE chunks_fts MATCH ?
                ORDER BY score
                LIMIT ?
                """,
                (fts, max(limit * 4, limit) if prefix else limit),
            ).fetchall()
        except sqlite3.OperationalError:
            # fallback LIKE
            rows = c.execute(
                """
                SELECT content, doc_id, chunk_index, '' as path, '' as title, 0 as score
                FROM chunks
                WHERE content LIKE ?
                LIMIT ?
                """,
                (f"%{q[:80]}%", max(limit * 4, limit) if prefix else limit),
            ).fetchall()
            # attach paths
            out = []
            for r in rows:
                d = c.execute("SELECT path, title FROM documents WHERE id=?", (r["doc_id"],)).fetchone()
                out.append(
                    {
                        "content": r["content"],
                        "doc_id": r["doc_id"],
                        "chunk_index": r["chunk_index"],
                        "path": (d["path"] if d else ""),
                        "title": (d["title"] if d else ""),
                        "score": 0,
                    }
                )
            if prefix:
                out = [x for x in out if prefix in str(x.get("path") or "").lower()]
            return out[:limit]
    results = [dict(r) for r in rows]
    if prefix:
        results = [x for x in results if prefix in str(x.get("path") or "").lower()]
    return results[:limit]



# ---------------------------------------------------------------------------
# P0.4 Hybrid RAG — BM25 (FTS5) + optional embeddings + RRF / cross-score
# Ideas from Open WebUI hybrid search (BM25 + vector + Ensemble/RRF),
# reimplemented with stdlib + existing hashing embeddings (no vector DB).
# ---------------------------------------------------------------------------

HYBRID_RRF_K = 60
DEFAULT_BM25_WEIGHT = 0.5
DEFAULT_HYBRID_CANDIDATE_MULT = 4


def hybrid_rag_enabled(cfg: dict[str, Any] | None = None) -> bool:
    """Settings toggle — Hybrid RAG ON by default (safe: soft-degrades to lexical)."""
    if cfg is None:
        try:
            from app.core.services.data.storage import load_config

            cfg = load_config()
        except Exception:  # noqa: BLE001
            return True
    return bool((cfg or {}).get("hybrid_rag_enabled", True))


def hybrid_bm25_weight(cfg: dict[str, Any] | None = None) -> float:
    """Weight for BM25 vs embedding in RRF / cross-score (0=vector-only, 1=BM25-only)."""
    if cfg is None:
        try:
            from app.core.services.data.storage import load_config

            cfg = load_config()
        except Exception:  # noqa: BLE001
            cfg = {}
    try:
        w = float((cfg or {}).get("hybrid_rag_bm25_weight", DEFAULT_BM25_WEIGHT))
    except Exception:  # noqa: BLE001
        w = DEFAULT_BM25_WEIGHT
    return max(0.0, min(1.0, w))


def _hit_key(h: dict[str, Any]) -> str:
    did = str(h.get("doc_id") or "")
    idx = h.get("chunk_index")
    if did and idx is not None:
        return f"{did}:{idx}"
    path = str(h.get("path") or "")
    content = str(h.get("content") or "")
    return hashlib.sha256(f"{path}|{content[:240]}".encode("utf-8", errors="replace")).hexdigest()[:24]


def reciprocal_rank_fusion(
    ranked_lists: list[list[dict[str, Any]]],
    *,
    weights: list[float] | None = None,
    k: int = HYBRID_RRF_K,
) -> list[dict[str, Any]]:
    """
    Reciprocal Rank Fusion (Cormack et al.).

    For each ranked list i with weight w_i:
        score(d) += w_i / (k + rank_i(d))
    where rank is 1-based. Documents are keyed by doc_id:chunk_index.

    Returns merged hits sorted by rrf_score descending (fields from first sighting).
    """
    if not ranked_lists:
        return []
    if weights is None:
        weights = [1.0] * len(ranked_lists)
    if len(weights) != len(ranked_lists):
        raise ValueError("weights length must match ranked_lists")
    k = max(1, int(k))
    scores: dict[str, float] = {}
    best: dict[str, dict[str, Any]] = {}
    for lst, w in zip(ranked_lists, weights):
        w = float(w)
        if w <= 0 or not lst:
            continue
        for rank, h in enumerate(lst, start=1):
            key = _hit_key(h)
            scores[key] = scores.get(key, 0.0) + w / (k + rank)
            if key not in best:
                best[key] = dict(h)
            else:
                # keep richer metadata / better lexical score if present
                cur = best[key]
                if not cur.get("content") and h.get("content"):
                    cur["content"] = h["content"]
                if h.get("emb_score") is not None and cur.get("emb_score") is None:
                    cur["emb_score"] = h["emb_score"]
                if h.get("bm25_score") is not None and cur.get("bm25_score") is None:
                    cur["bm25_score"] = h["bm25_score"]
    out: list[dict[str, Any]] = []
    for key, sc in sorted(scores.items(), key=lambda kv: kv[1], reverse=True):
        row = best[key]
        row["rrf_score"] = round(sc, 6)
        row["score"] = row["rrf_score"]
        out.append(row)
    return out


def _normalize_bm25_scores(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    SQLite FTS5 bm25() is more-negative = better. Convert to [0,1] relevance
    where 1 is best among this result set.
    """
    if not hits:
        return []
    raw: list[float] = []
    for h in hits:
        try:
            raw.append(float(h.get("score") if h.get("score") is not None else 0.0))
        except Exception:  # noqa: BLE001
            raw.append(0.0)
    # more negative → better; shift so best (min) → 1
    mn = min(raw)
    mx = max(raw)
    span = (mx - mn) or 1.0
    out = []
    for h, r in zip(hits, raw):
        # invert: best (mn) → 1.0, worst (mx) → 0.0
        norm = (mx - r) / span
        row = dict(h)
        row["bm25_score"] = round(r, 4)
        row["bm25_norm"] = round(norm, 4)
        out.append(row)
    return out


def _embeddings_available() -> bool:
    try:
        from app.core.services.ai import local_embeddings as _le  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        return False


def vector_search(
    query: str,
    *,
    limit: int = 8,
    path_prefix: str = "",
    pool_limit: int = 2000,
) -> list[dict[str, Any]]:
    """
    Embedding similarity over stored hashing-trick vectors (soft-optional).

    Returns hits with emb_score in [approx -1,1] (cosine), best first.
    Empty list when embeddings module or vectors unavailable.
    """
    q = (query or "").strip()
    if not q:
        return []
    try:
        from app.core.services.ai.local_embeddings import cosine, embed_text
    except Exception:  # noqa: BLE001
        return []
    prefix = ""
    if path_prefix:
        try:
            prefix = str(Path(path_prefix).expanduser().resolve()).lower()
        except Exception:  # noqa: BLE001
            prefix = str(path_prefix).lower()
    qv = embed_text(q)
    scored: list[dict[str, Any]] = []
    try:
        conn = sqlite3.connect(str(db_path()))
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chunk_embeddings (
                chunk_id INTEGER PRIMARY KEY,
                dim INTEGER,
                vector TEXT
            )
            """
        )
        rows = conn.execute(
            """
            SELECT e.chunk_id, e.vector, c.content, c.doc_id, c.chunk_index,
                   d.path, d.title
            FROM chunk_embeddings e
            JOIN chunks c ON c.id = e.chunk_id
            JOIN documents d ON d.id = c.doc_id
            ORDER BY e.chunk_id DESC
            LIMIT ?
            """,
            (max(1, int(pool_limit)),),
        ).fetchall()
        # If no precomputed vectors, fall back to scoring a lexical candidate pool
        if not rows:
            lex = search(q, limit=max(limit * 8, 24), path_prefix=path_prefix)
            for h in lex:
                content = h.get("content") or ""
                sc = cosine(qv, embed_text(content))
                scored.append(
                    {
                        **h,
                        "emb_score": round(float(sc), 4),
                        "score": round(float(sc), 4),
                    }
                )
            conn.close()
            scored.sort(key=lambda x: float(x.get("emb_score") or 0), reverse=True)
            return scored[:limit]
        for r in rows:
            path = r["path"] or ""
            if prefix and prefix not in str(path).lower():
                continue
            try:
                vec = [float(x) for x in (r["vector"] or "").split(",") if x != ""]
            except Exception:  # noqa: BLE001
                continue
            if not vec:
                continue
            sc = cosine(qv, vec)
            scored.append(
                {
                    "content": r["content"],
                    "doc_id": r["doc_id"],
                    "chunk_index": r["chunk_index"],
                    "path": path,
                    "title": r["title"] or "",
                    "emb_score": round(float(sc), 4),
                    "score": round(float(sc), 4),
                }
            )
        conn.close()
    except Exception:  # noqa: BLE001
        return []
    scored.sort(key=lambda x: float(x.get("emb_score") or 0), reverse=True)
    return scored[:limit]


def cross_score_rerank(
    hits: list[dict[str, Any]],
    *,
    bm25_weight: float = DEFAULT_BM25_WEIGHT,
) -> list[dict[str, Any]]:
    """
    Lightweight cross-score rerank after RRF.

    final = w * bm25_norm + (1-w) * emb_norm
    Missing side → use the available score only (soft-degrade).
    """
    w = max(0.0, min(1.0, float(bm25_weight)))
    emb_vals = [float(h.get("emb_score") or 0.0) for h in hits]
    e_mn = min(emb_vals) if emb_vals else 0.0
    e_mx = max(emb_vals) if emb_vals else 0.0
    e_span = (e_mx - e_mn) or 1.0
    out: list[dict[str, Any]] = []
    for h in hits:
        row = dict(h)
        has_b = row.get("bm25_norm") is not None
        has_e = row.get("emb_score") is not None
        b = float(row.get("bm25_norm") or 0.0)
        e_raw = float(row.get("emb_score") or 0.0)
        e = (e_raw - e_mn) / e_span if has_e else 0.0
        if has_b and has_e:
            final = w * b + (1.0 - w) * e
        elif has_b:
            final = b
        elif has_e:
            final = e
        else:
            final = float(row.get("rrf_score") or 0.0)
        row["emb_norm"] = round(e, 4) if has_e else None
        row["hybrid_score"] = round(final, 4)
        out.append(row)
    out.sort(key=lambda x: float(x.get("hybrid_score") or 0), reverse=True)
    return out


def hybrid_search(
    query: str,
    *,
    limit: int = 8,
    path_prefix: str = "",
    bm25_weight: float | None = None,
    use_embeddings: bool = True,
    rrf_k: int = HYBRID_RRF_K,
    rerank: bool = True,
) -> list[dict[str, Any]]:
    """
    Hybrid retrieve: BM25 lexical (FTS5) + embedding cosine when available,
    merged with Reciprocal Rank Fusion, then optional cross-score rerank.

    Soft-degrades to lexical-only if embeddings unavailable or use_embeddings=False.
    """
    q = (query or "").strip()
    if not q:
        return []
    if bm25_weight is None:
        bm25_weight = hybrid_bm25_weight()
    w = max(0.0, min(1.0, float(bm25_weight)))
    pool = max(limit * DEFAULT_HYBRID_CANDIDATE_MULT, limit)

    # --- Lexical (BM25 via FTS5) ---
    lex_raw = search(q, limit=pool, path_prefix=path_prefix)
    lex = _normalize_bm25_scores(lex_raw)

    # --- Vector (soft-optional) ---
    vec: list[dict[str, Any]] = []
    if use_embeddings and w < 1.0 and _embeddings_available():
        try:
            vec = vector_search(q, limit=pool, path_prefix=path_prefix)
        except Exception:  # noqa: BLE001
            vec = []

    if not lex and not vec:
        return []

    # Pure modes
    if not vec or w >= 1.0:
        out = lex[:limit]
        for h in out:
            h.setdefault("hybrid_score", h.get("bm25_norm", 0))
            h.setdefault("method", "lexical")
        return out
    if w <= 0.0:
        out = vec[:limit]
        for h in out:
            h.setdefault("hybrid_score", h.get("emb_score", 0))
            h.setdefault("method", "vector")
        return out

    # Annotate lexical hits with emb_score when same key appears in vec
    vec_by_key = {_hit_key(h): h for h in vec}
    for h in lex:
        vh = vec_by_key.get(_hit_key(h))
        if vh and vh.get("emb_score") is not None:
            h["emb_score"] = vh["emb_score"]
    for h in vec:
        lh = next((x for x in lex if _hit_key(x) == _hit_key(h)), None)
        if lh and lh.get("bm25_norm") is not None:
            h["bm25_norm"] = lh["bm25_norm"]
            h["bm25_score"] = lh.get("bm25_score")

    merged = reciprocal_rank_fusion(
        [lex, vec],
        weights=[w, 1.0 - w],
        k=rrf_k,
    )
    if rerank:
        merged = cross_score_rerank(merged, bm25_weight=w)
    for h in merged:
        h["method"] = "hybrid"
    return merged[:limit]


def build_context_block_hybrid(
    query: str,
    *,
    limit: int = 6,
    max_chars: int = 6000,
    path_prefix: str = "",
    bm25_weight: float | None = None,
) -> str:
    """Context block using hybrid retrieve; citations stay clickable file:// links."""
    hits = hybrid_search(
        query,
        limit=limit,
        path_prefix=path_prefix,
        bm25_weight=bm25_weight,
        use_embeddings=True,
    )
    if not hits:
        return ""
    parts = ["## Local Knowledge (hybrid BM25 + embeddings + RRF)", ""]
    cite_lines: list[str] = []
    total = 0
    for i, h in enumerate(hits, 1):
        snip = (h.get("content") or "")[:1200]
        path = h.get("path") or ""
        title = h.get("title") or Path(path).name
        uri = path_to_file_uri(path) if path else ""
        hs = h.get("hybrid_score", h.get("rrf_score", h.get("emb_score")))
        score_bit = f" score={hs}" if hs is not None else ""
        src_line = f"Source: {uri or path}"
        block = f"### [{i}] {title}{score_bit}\n{src_line}\n\n{snip}\n"
        if total + len(block) > max_chars:
            break
        parts.append(block)
        if uri:
            cite_lines.append(f"[{i}] {title} — {uri}")
        else:
            cite_lines.append(f"[{i}] {title} — `{path}`")
        total += len(block)
    parts.append(
        "Use these excerpts when answering. **Cite sources inline** like [1], [2] "
        "matching the numbers above. End with a short **Sources** list using the "
        "exact file:// links from the Citation index so the user can click them. "
        "If insufficient, say so."
    )
    if cite_lines:
        parts.append("\n### Citation index\n" + "\n".join(cite_lines))
    return "\n".join(parts)


def format_citation_sources(hits: list[dict[str, Any]]) -> str:
    """User-facing Sources block with clickable file:// links (Task #7)."""
    lines: list[str] = []
    for i, h in enumerate(hits, 1):
        path = str(h.get("path") or "").strip()
        title = str(h.get("title") or (Path(path).name if path else f"Source {i}"))
        uri = path_to_file_uri(path) if path else ""
        if uri:
            lines.append(f"[{i}] {title} — {uri}")
        elif path:
            lines.append(f"[{i}] {title} — {path}")
        else:
            lines.append(f"[{i}] {title}")
    return "\n".join(lines)


def build_context_block(
    query: str,
    *,
    limit: int = 6,
    max_chars: int = 6000,
    path_prefix: str = "",
) -> str:
    # P0.4: prefer hybrid when Settings toggle is on (default ON)
    try:
        if hybrid_rag_enabled():
            block = build_context_block_hybrid(
                query, limit=limit, max_chars=max_chars, path_prefix=path_prefix
            )
            if block:
                return block
    except Exception:  # noqa: BLE001
        pass
    hits = search(query, limit=limit, path_prefix=path_prefix)
    if not hits:
        return ""
    parts = ["## Local Knowledge (retrieved from your indexed files)", ""]
    cite_lines: list[str] = []
    total = 0
    for i, h in enumerate(hits, 1):
        snip = (h.get("content") or "")[:1200]
        path = h.get("path") or ""
        title = h.get("title") or Path(path).name
        uri = path_to_file_uri(path) if path else ""
        src_line = f"Source: {uri or path}"
        block = f"### [{i}] {title}\n{src_line}\n\n{snip}\n"
        if total + len(block) > max_chars:
            break
        parts.append(block)
        if uri:
            cite_lines.append(f"[{i}] {title} — {uri}")
        else:
            cite_lines.append(f"[{i}] {title} — `{path}`")
        total += len(block)
    parts.append(
        "Use these excerpts when answering. **Cite sources inline** like [1], [2] "
        "matching the numbers above. End with a short **Sources** list using the "
        "exact file:// links from the Citation index so the user can click them. "
        "If insufficient, say so."
    )
    if cite_lines:
        parts.append("\n### Citation index\n" + "\n".join(cite_lines))
    return "\n".join(parts)


def chat_with_folder(folder: str | Path, *, recursive: bool = True, limit: int = 500) -> dict[str, Any]:
    """
    Index a folder for Chat-with-folder (Task #7).
    Returns {ok, folder, indexed, errors, path_prefix}.
    """
    r = index_folder(folder, recursive=recursive, limit=limit)
    if not r.get("ok"):
        return r
    try:
        root = str(Path(folder).expanduser().resolve())
    except Exception:  # noqa: BLE001
        root = str(folder)
    r["path_prefix"] = root
    r["message"] = (
        f"Folder ready for chat: {root}\n"
        f"Indexed {r.get('indexed', 0)} file(s). Ask questions — answers cite local files."
    )
    return r


def knowledge_health() -> dict[str, Any]:
    """Stats for Knowledge page / Settings."""
    try:
        conn = _conn()
        try:
            n_docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            n_chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "documents": 0, "chunks": 0}
    watches = 0
    try:
        from app.services import file_watcher

        watches = len(file_watcher.load_watches() or [])
    except Exception:  # noqa: BLE001
        pass
    return {
        "ok": True,
        "documents": int(n_docs or 0),
        "chunks": int(n_chunks or 0),
        "watches": watches,
    }


def extract_knowledge_commands(text: str) -> list[dict[str, str]]:
    """
    <<<KNOWLEDGE>>>
    action: index_file | index_folder | search | list
    path: C:\\docs\\manual.pdf
    query: API keys meeting
    <<<END_KNOWLEDGE>>>
    """
    out = []
    for m in KNOWLEDGE_RE.finditer(text or ""):
        body = (m.group(1) or "").strip()
        meta: dict[str, str] = {"action": "search", "path": "", "query": "", "recursive": "true"}
        for line in body.splitlines():
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            meta[k.strip().lower()] = v.strip()
        out.append(meta)
    return out


def run_knowledge_command(cmd: dict[str, str]) -> dict[str, Any]:
    action = (cmd.get("action") or "search").lower()
    if action == "index_file":
        return index_file(cmd.get("path") or "")
    if action == "index_folder":
        return index_folder(
            cmd.get("path") or "",
            recursive=str(cmd.get("recursive") or "true").lower() in ("1", "true", "yes"),
        )
    if action == "list":
        return {"ok": True, "documents": list_documents()}
    if action == "clear":
        clear_all()
        return {"ok": True, "cleared": True}
    if action == "search":
        hits = search(cmd.get("query") or cmd.get("path") or "", limit=10)
        return {"ok": True, "hits": hits, "count": len(hits)}
    return {"ok": False, "error": f"Unknown action: {action}"}


def tool_instructions() -> str:
    return """
## Local Knowledge RAG (private document index)

Index PDFs, Markdown, code, notes on this PC. Query them in chat without cloud vector DBs.

### Index a file
<<<KNOWLEDGE>>>
action: index_file
path: C:\\path\\to\\manual.pdf
<<<END_KNOWLEDGE>>>

### Index a folder
<<<KNOWLEDGE>>>
action: index_folder
path: C:\\Users\\You\\Notes
recursive: true
<<<END_KNOWLEDGE>>>

### Search
<<<KNOWLEDGE>>>
action: search
query: API keys decision last meeting
<<<END_KNOWLEDGE>>>

### List indexed docs
<<<KNOWLEDGE>>>
action: list
<<<END_KNOWLEDGE>>>

The app also auto-retrieves relevant chunks into context when the user asks about their documents.
UI: Knowledge tab to index/browse. Data: data/knowledge/rag.sqlite
""".strip()
