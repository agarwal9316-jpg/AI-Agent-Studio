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
