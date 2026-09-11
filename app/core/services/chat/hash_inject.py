"""OWUI-inspired `#` doc + URL inject into chat context (P0.3).

Habit: type `#filename`, `#path/to/file`, or `#https://…` in the composer to
pull truncated content into the current turn. Ideas from Open WebUI `#`
Knowledge / web attach — reimplemented cleanly for Studio (no GPL blobs).

Resolution order per token:
  1. http(s) URL → web_fetch (truncated text + source)
  2. readable local file path → truncated text
  3. knowledge index hit (title / basename / FTS) → excerpt + citation
  4. unknown → soft-degrade note (never crash send)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlparse

# Max payload budgets (chars)
DEFAULT_MAX_CHARS_PER = 12_000
DEFAULT_MAX_TOTAL = 40_000

# Word-boundary `#token` — URLs, Windows/POSIX paths, or bare names.
# Avoid matching markdown `## heading` by requiring non-# after `#`.
_HASH_TOKEN_RE = re.compile(
    r"(?<![\w/#])#("
    r"https?://[^\s<>\"'`]+"  # URL
    r"|"
    r"(?:[A-Za-z]:[\\/]|\\\\|~/|/|\./|\.\./)[^\s<>\"'`]+"  # path-ish
    r"|"
    r"[^\s<>\"'`#]+"  # bare name / filename
    r")"
)

# Trailing punctuation often stuck to URLs / tokens in prose
_TRAIL_PUNCT = ".,;:!?)]}>\"'"


def _clean_token(raw: str) -> str:
    t = (raw or "").strip()
    while t and t[-1] in _TRAIL_PUNCT:
        t = t[:-1]
    return t.strip()


def parse_hash_tokens(text: str) -> list[str]:
    """Return unique `#` tokens (without the leading `#`), left-to-right."""
    seen: set[str] = set()
    out: list[str] = []
    for m in _HASH_TOKEN_RE.finditer(text or ""):
        tok = _clean_token(m.group(1) or "")
        if not tok or tok in seen:
            continue
        # Skip pure numeric hashes / empty
        if tok.startswith("#"):
            continue
        seen.add(tok)
        out.append(tok)
    return out


def classify_token(token: str) -> str:
    """Return 'url' | 'path' | 'name'."""
    t = (token or "").strip()
    low = t.lower()
    if low.startswith("http://") or low.startswith("https://"):
        return "url"
    # Drive letter, UNC, home, absolute/relative path markers
    if re.match(r"^[A-Za-z]:[\\/]", t) or t.startswith("\\\\") or t.startswith("~/"):
        return "path"
    if t.startswith("/") or t.startswith("./") or t.startswith("../"):
        return "path"
    # Looks like a path with separators and a file extension
    if ("/" in t or "\\" in t) and Path(t).suffix:
        return "path"
    if Path(t).suffix and ("/" in t or "\\" in t or t.count(".") == 1):
        # e.g. notes.md → name (knowledge); ./notes.md already path
        if "/" not in t and "\\" not in t:
            return "name"
        return "path"
    return "name"


def _truncate(text: str, max_chars: int) -> tuple[str, bool]:
    t = text or ""
    if len(t) <= max_chars:
        return t, False
    return t[: max(0, max_chars - 1)] + "…", True


def resolve_url(
    url: str,
    *,
    max_chars: int = DEFAULT_MAX_CHARS_PER,
    fetch_fn: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Fetch URL text via web_fetch (injectable for tests)."""
    u = (url or "").strip()
    if not u.lower().startswith(("http://", "https://")):
        return {
            "ok": False,
            "kind": "url",
            "token": u,
            "source": u,
            "title": u,
            "text": "",
            "note": "Not an http(s) URL",
        }
    try:
        if fetch_fn is None:
            from app.core.services.web.web_fetch import web_fetch

            fetch_fn = web_fetch
        res = fetch_fn(u, max_chars=max_chars) or {}
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "kind": "url",
            "token": u,
            "source": u,
            "title": u,
            "text": "",
            "note": f"URL fetch failed: {e}",
        }
    if not res.get("ok"):
        return {
            "ok": False,
            "kind": "url",
            "token": u,
            "source": str(res.get("url") or u),
            "title": u,
            "text": "",
            "note": str(res.get("error") or "URL fetch failed"),
        }
    body = str(res.get("text") or "")
    body, trunc = _truncate(body, max_chars)
    title = urlparse(str(res.get("url") or u)).path.rsplit("/", 1)[-1] or u
    title = unquote(title) or u
    return {
        "ok": True,
        "kind": "url",
        "token": u,
        "source": str(res.get("url") or u),
        "title": title,
        "text": body,
        "truncated": trunc or bool(res.get("truncated")),
        "note": "",
    }


def resolve_file(
    path_str: str,
    *,
    cwd: str | Path | None = None,
    max_chars: int = DEFAULT_MAX_CHARS_PER,
) -> dict[str, Any]:
    """Read a local file if it exists and is readable."""
    raw = (path_str or "").strip()
    try:
        p = Path(raw).expanduser()
        if not p.is_absolute():
            base = Path(cwd).expanduser() if cwd else Path.cwd()
            p = (base / p).resolve()
        else:
            p = p.resolve()
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "kind": "file",
            "token": raw,
            "source": raw,
            "title": Path(raw).name or raw,
            "text": "",
            "note": f"Bad path: {e}",
        }
    if not p.is_file():
        return {
            "ok": False,
            "kind": "file",
            "token": raw,
            "source": str(p),
            "title": p.name,
            "text": "",
            "note": f"File not found: {p}",
        }
    try:
        from app.core.services.data.rag_knowledge import read_file_text

        text = read_file_text(p)
    except Exception as e:  # noqa: BLE001
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception as e2:  # noqa: BLE001
            return {
                "ok": False,
                "kind": "file",
                "token": raw,
                "source": str(p),
                "title": p.name,
                "text": "",
                "note": f"Read failed: {e2 or e}",
            }
    if not (text or "").strip():
        return {
            "ok": False,
            "kind": "file",
            "token": raw,
            "source": str(p),
            "title": p.name,
            "text": "",
            "note": f"Empty or unreadable: {p}",
        }
    body, trunc = _truncate(text, max_chars)
    return {
        "ok": True,
        "kind": "file",
        "token": raw,
        "source": str(p),
        "title": p.name,
        "text": body,
        "truncated": trunc,
        "note": "",
    }


def _knowledge_docs() -> list[dict[str, Any]]:
    try:
        from app.core.services.data.rag_knowledge import list_documents

        return list(list_documents() or [])
    except Exception:  # noqa: BLE001
        return []


def _match_knowledge_doc(token: str) -> dict[str, Any] | None:
    """Best-effort match against indexed documents (title / basename / path)."""
    q = (token or "").strip().lower()
    if not q:
        return None
    docs = _knowledge_docs()
    if not docs:
        return None

    def score(doc: dict[str, Any]) -> int:
        path = str(doc.get("path") or "")
        title = str(doc.get("title") or "")
        base = Path(path).name.lower() if path else ""
        tl = title.lower()
        pl = path.lower()
        if tl == q or base == q:
            return 100
        if tl.startswith(q) or base.startswith(q):
            return 80
        if q in tl or q in base:
            return 60
        if q in pl:
            return 40
        return 0

    ranked = sorted(((score(d), d) for d in docs), key=lambda x: -x[0])
    if ranked and ranked[0][0] > 0:
        return ranked[0][1]
    return None


def resolve_knowledge(
    name: str,
    *,
    max_chars: int = DEFAULT_MAX_CHARS_PER,
) -> dict[str, Any]:
    """Resolve a bare `#name` against the local knowledge index."""
    token = (name or "").strip()
    doc = _match_knowledge_doc(token)
    if doc:
        path = str(doc.get("path") or "")
        title = str(doc.get("title") or Path(path).name or token)
        # Prefer live file read; fall back to FTS chunks for that doc
        if path:
            file_res = resolve_file(path, max_chars=max_chars)
            if file_res.get("ok"):
                file_res["kind"] = "knowledge"
                file_res["token"] = token
                file_res["title"] = title
                try:
                    from app.core.services.data.rag_knowledge import path_to_file_uri

                    file_res["citation"] = path_to_file_uri(path) or path
                except Exception:  # noqa: BLE001
                    file_res["citation"] = path
                return file_res
        # Chunks via search constrained by title/path
        try:
            from app.core.services.data.rag_knowledge import search, path_to_file_uri

            hits = search(token, limit=4)
            # Prefer hits from matched doc
            did = str(doc.get("id") or "")
            prefer = [h for h in hits if str(h.get("doc_id") or "") == did] or hits
            parts = []
            total = 0
            for h in prefer:
                snip = str(h.get("content") or "")
                if not snip:
                    continue
                if total + len(snip) > max_chars:
                    snip = snip[: max(0, max_chars - total)]
                parts.append(snip)
                total += len(snip)
                if total >= max_chars:
                    break
            body = "\n\n---\n\n".join(parts)
            body, trunc = _truncate(body, max_chars)
            cite = path_to_file_uri(path) if path else path
            if body.strip():
                return {
                    "ok": True,
                    "kind": "knowledge",
                    "token": token,
                    "source": path or title,
                    "title": title,
                    "text": body,
                    "truncated": trunc,
                    "citation": cite or path or title,
                    "note": "",
                }
        except Exception:  # noqa: BLE001
            pass
        return {
            "ok": False,
            "kind": "knowledge",
            "token": token,
            "source": path or title,
            "title": title,
            "text": "",
            "note": f"Indexed as “{title}” but no readable content",
        }

    # FTS fallback — treat query as search
    try:
        from app.core.services.data.rag_knowledge import search, path_to_file_uri

        hits = search(token, limit=3)
        if hits:
            parts = []
            cites = []
            total = 0
            for i, h in enumerate(hits, 1):
                snip = str(h.get("content") or "")[: min(2000, max_chars)]
                path = str(h.get("path") or "")
                title = str(h.get("title") or Path(path).name or f"hit {i}")
                uri = path_to_file_uri(path) if path else path
                block = f"### [{i}] {title}\nSource: {uri or path}\n\n{snip}"
                if total + len(block) > max_chars:
                    break
                parts.append(block)
                cites.append(f"[{i}] {title} — {uri or path}")
                total += len(block)
            body = "\n\n".join(parts)
            return {
                "ok": True,
                "kind": "knowledge",
                "token": token,
                "source": cites[0] if cites else token,
                "title": token,
                "text": body,
                "truncated": False,
                "citation": "\n".join(cites),
                "note": "FTS match (no exact doc title)",
            }
    except Exception:  # noqa: BLE001
        pass

    return {
        "ok": False,
        "kind": "knowledge",
        "token": token,
        "source": token,
        "title": token,
        "text": "",
        "note": f"Unknown # token: no knowledge doc, file, or URL matched “{token}”",
    }


def resolve_hash_token(
    token: str,
    *,
    cwd: str | Path | None = None,
    max_chars: int = DEFAULT_MAX_CHARS_PER,
    fetch_url: bool = True,
    fetch_fn: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Resolve one `#token` with soft-degrade on failure."""
    tok = _clean_token(token)
    if not tok:
        return {
            "ok": False,
            "kind": "empty",
            "token": "",
            "source": "",
            "title": "",
            "text": "",
            "note": "Empty # token",
        }
    kind = classify_token(tok)
    if kind == "url":
        if not fetch_url:
            return {
                "ok": False,
                "kind": "url",
                "token": tok,
                "source": tok,
                "title": tok,
                "text": "",
                "note": "URL fetch disabled",
            }
        return resolve_url(tok, max_chars=max_chars, fetch_fn=fetch_fn)
    if kind == "path":
        res = resolve_file(tok, cwd=cwd, max_chars=max_chars)
        if res.get("ok"):
            return res
        # Soft fallback: maybe it's an indexed name that looks path-ish
        kn = resolve_knowledge(Path(tok).name, max_chars=max_chars)
        if kn.get("ok"):
            return kn
        return res
    # name — try knowledge first, then cwd-relative file with that name
    kn = resolve_knowledge(tok, max_chars=max_chars)
    if kn.get("ok"):
        return kn
    file_try = resolve_file(tok, cwd=cwd, max_chars=max_chars)
    if file_try.get("ok"):
        return file_try
    # Prefer knowledge miss note (clearer) if we had an index miss
    if kn.get("note"):
        return kn
    return file_try


def build_hash_inject_block(
    text: str,
    *,
    cwd: str | Path | None = None,
    max_chars_per: int = DEFAULT_MAX_CHARS_PER,
    max_total: int = DEFAULT_MAX_TOTAL,
    fetch_url: bool = True,
    fetch_fn: Callable[..., dict[str, Any]] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Parse `#` tokens, resolve, and format a system-context block.

    Returns ``(block, resolutions)``. Empty block when no tokens.
    Never raises — soft-degrades per token.
    """
    tokens = parse_hash_tokens(text or "")
    if not tokens:
        return "", []

    resolutions: list[dict[str, Any]] = []
    parts: list[str] = [
        "## Hash inject (`#` docs / files / URLs)",
        "The user pulled the following into this turn with `#token` syntax. "
        "Use them as primary context; cite sources. Unknown tokens are noted — do not invent their content.",
        "",
    ]
    total = 0
    for i, tok in enumerate(tokens, 1):
        try:
            res = resolve_hash_token(
                tok,
                cwd=cwd,
                max_chars=max_chars_per,
                fetch_url=fetch_url,
                fetch_fn=fetch_fn,
            )
        except Exception as e:  # noqa: BLE001
            res = {
                "ok": False,
                "kind": "error",
                "token": tok,
                "source": tok,
                "title": tok,
                "text": "",
                "note": f"Resolve error: {e}",
            }
        resolutions.append(res)
        title = res.get("title") or tok
        source = res.get("source") or tok
        cite = res.get("citation") or source
        kind = res.get("kind") or "?"
        if res.get("ok") and (res.get("text") or "").strip():
            body = str(res.get("text") or "")
            remain = max_total - total
            if remain <= 200:
                parts.append(
                    f"### [{i}] #{tok} ({kind}) — omitted (context budget)\n"
                    f"Source: {cite}"
                )
                res = {**res, "ok": True, "truncated": True, "note": (res.get("note") or "") + " budget"}
                resolutions[-1] = res
                continue
            if len(body) > remain:
                body = body[: remain - 1] + "…"
                res = {**res, "truncated": True}
                resolutions[-1] = res
            flag = " truncated" if res.get("truncated") else ""
            block = (
                f"### [{i}] #{tok} · {title} ({kind}{flag})\n"
                f"Source: {cite}\n\n"
                f"{body}\n"
            )
            parts.append(block)
            total += len(block)
        else:
            note = res.get("note") or "unresolved"
            parts.append(
                f"### [{i}] #{tok} · unresolved ({kind})\n"
                f"Note: {note}\n"
                f"(Soft-degrade — continue without this source.)\n"
            )

    block = "\n".join(parts).strip()
    return block, resolutions


def suggest_hash_completions(
    partial: str,
    *,
    limit: int = 8,
) -> list[dict[str, str]]:
    """Lightweight autocomplete from knowledge titles/filenames (+ URL hint)."""
    q = (partial or "").lstrip("#").strip().lower()
    out: list[dict[str, str]] = []
    if q.startswith("http://") or q.startswith("https://"):
        return [{"label": f"#{partial.lstrip('#')}", "kind": "url", "detail": "Fetch URL into context"}]
    for doc in _knowledge_docs():
        path = str(doc.get("path") or "")
        title = str(doc.get("title") or Path(path).name or "")
        base = Path(path).name if path else title
        hay = f"{title} {base} {path}".lower()
        if q and q not in hay:
            continue
        label = title or base
        out.append({"label": f"#{label}", "kind": "knowledge", "detail": path or title})
        if len(out) >= limit:
            break
    if not q:
        # Seed a couple of syntax hints when user just typed `#`
        out.insert(0, {"label": "#https://…", "kind": "hint", "detail": "Paste a URL after #"})
        out.insert(1, {"label": "#path/to/file", "kind": "hint", "detail": "Local file path"})
    return out[:limit]


def hash_inject_help_text() -> str:
    """Short how-to for Help / CHANGELOG / composer tip."""
    return (
        "Type `#` in chat to pull content into this turn:\n"
        "  #my-notes.md          → knowledge doc or local file\n"
        "  #./README.md          → relative/absolute file path\n"
        "  #https://example.com  → fetch URL (truncated) + source\n"
        "Unknown tokens soft-degrade with a clear note (send still works)."
    )
