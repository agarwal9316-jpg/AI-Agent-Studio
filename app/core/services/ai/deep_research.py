"""
Deep research, crawl, scrape, download — full internet operator tools.

Blocks the LLM can emit:
  <<<DEEP_RESEARCH>>>   multi-hop: search → open pages → follow links → synthesize pack
  <<<WEB_CRAWL>>>       BFS crawl from a start URL (same-domain optional)
  <<<WEB_SCRAPE>>>      extract text / links / tables / CSS-selected nodes from a URL
  <<<WEB_DOWNLOAD>>>    save a file from a URL into data/browser_downloads

Uses existing web_search, web_fetch, browser_tool. Safety limits from config.
"""

from __future__ import annotations

import html as html_lib
import json
import re
import time
import urllib.parse
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import deque
from pathlib import Path
from typing import Any  # noqa: F401 — used in annotations

from app.paths import data_dir

DEEP_RE = re.compile(
    r"<<<DEEP_RESEARCH>>>\s*(.*?)\s*<<<END_DEEP_RESEARCH>>>",
    re.DOTALL | re.IGNORECASE,
)
CRAWL_RE = re.compile(
    r"<<<WEB_CRAWL>>>\s*(.*?)\s*<<<END_WEB_CRAWL>>>",
    re.DOTALL | re.IGNORECASE,
)
SCRAPE_RE = re.compile(
    r"<<<WEB_SCRAPE>>>\s*(.*?)\s*<<<END_WEB_SCRAPE>>>",
    re.DOTALL | re.IGNORECASE,
)
DOWNLOAD_RE = re.compile(
    r"<<<WEB_DOWNLOAD>>>\s*(.*?)\s*<<<END_WEB_DOWNLOAD>>>",
    re.DOTALL | re.IGNORECASE,
)


def _cfg() -> dict[str, Any]:
    try:
        from app.core.services.data.storage import load_config

        return load_config()
    except Exception:  # noqa: BLE001
        return {}


def _limits() -> dict[str, int]:
    c = _cfg()
    def i(key: str, default: int, lo: int, hi: int) -> int:
        try:
            v = int(c.get(key, default))
        except Exception:  # noqa: BLE001
            v = default
        return max(lo, min(hi, v))

    return {
        "crawl_max_pages": i("research_crawl_max_pages", 12, 1, 40),
        "crawl_max_depth": i("research_crawl_max_depth", 2, 0, 4),
        "research_sources": i("research_max_sources", 8, 2, 20),
        "research_follow": i("research_follow_links", 4, 0, 12),
        "max_chars_page": i("research_max_chars_page", 8000, 1000, 30000),
    }


def tool_instructions() -> str:
    lim = _limits()
    return f"""
## Deep research · crawl · scrape · download (full internet)

You can do **multi-page research**, **site crawling**, **scraping**, and **file downloads**
on this PC. Prefer these over inventing answers.

### 1) DEEP_RESEARCH — best for “research X thoroughly”
Search the web, open top sources, optionally follow key links, return a packed brief.

<<<DEEP_RESEARCH>>>
query: impact of EU AI Act on open source models 2025
sources: {lim['research_sources']}
follow: {lim['research_follow']}
fetch_chars: {lim['max_chars_page']}
<<<END_DEEP_RESEARCH>>>

Fields: query (required), sources (how many search hits to open), follow (extra links from those pages),
same_domain (true/false — when following), use_browser (true = JS pages via Chromium).

### 2) WEB_CRAWL — explore a site from a start URL
<<<WEB_CRAWL>>>
url: https://docs.python.org/3/library/asyncio.html
max_pages: {lim['crawl_max_pages']}
max_depth: {lim['crawl_max_depth']}
same_domain: true
<<<END_WEB_CRAWL>>>

### 3) WEB_SCRAPE — extract structured content from one page
<<<WEB_SCRAPE>>>
url: https://example.com
mode: full
<<<END_WEB_SCRAPE>>>

<<<WEB_SCRAPE>>>
url: https://example.com/news
mode: links
<<<END_WEB_SCRAPE>>>

<<<WEB_SCRAPE>>>
url: https://example.com
mode: css
selector: article h2, article p
<<<END_WEB_SCRAPE>>>

<<<WEB_SCRAPE>>>
url: https://example.com/data
mode: tables
<<<END_WEB_SCRAPE>>>

Modes: full | text | links | tables | css | meta
use_browser: true when page needs JavaScript.

### 4) WEB_DOWNLOAD — save a file
<<<WEB_DOWNLOAD>>>
url: https://example.com/report.pdf
<<<END_WEB_DOWNLOAD>>>

Files land in data/browser_downloads/.

### When to use which
| Goal | Tool |
|------|------|
| Quick facts / news list | WEB_SEARCH |
| Thorough brief with citations | DEEP_RESEARCH |
| Walk a docs site | WEB_CRAWL |
| Pull headlines / table / selector | WEB_SCRAPE |
| Save PDF/zip/image | WEB_DOWNLOAD |
| Login / click / form | BROWSER session |
| Raw API JSON | WEB_FETCH |

Always cite URLs from tool results. Never claim you crawled a site without a tool result.
Limits (Settings): max_pages≈{lim['crawl_max_pages']}, depth≈{lim['crawl_max_depth']}, sources≈{lim['research_sources']}.
""".strip()


def _parse_kv_block(body: str, defaults: dict[str, str]) -> dict[str, str]:
    meta = dict(defaults)
    for line in (body or "").splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip().lower(), v.strip()
        if k in meta or k in (
            "query",
            "url",
            "q",
            "sources",
            "follow",
            "fetch_chars",
            "max_pages",
            "max_depth",
            "same_domain",
            "use_browser",
            "mode",
            "selector",
            "name",
            "filename",
        ):
            if k in ("q",):
                meta["query"] = v
            else:
                meta[k] = v
    if not meta.get("url") and (body or "").strip().startswith("http"):
        meta["url"] = body.strip().splitlines()[0].strip()
    if not meta.get("query") and body and not meta.get("url"):
        # whole body as query for deep research
        lines = [ln.strip() for ln in body.splitlines() if ln.strip() and ":" not in ln[:20]]
        if lines:
            meta["query"] = lines[0]
    return meta


def extract_deep_research_blocks(text: str) -> list[dict[str, str]]:
    out = []
    for m in DEEP_RE.finditer(text or ""):
        meta = _parse_kv_block(
            m.group(1) or "",
            {
                "query": "",
                "sources": "8",
                "follow": "4",
                "fetch_chars": "8000",
                "same_domain": "false",
                "use_browser": "false",
            },
        )
        if meta.get("query"):
            out.append(meta)
    return out


def extract_crawl_blocks(text: str) -> list[dict[str, str]]:
    out = []
    for m in CRAWL_RE.finditer(text or ""):
        meta = _parse_kv_block(
            m.group(1) or "",
            {
                "url": "",
                "max_pages": "12",
                "max_depth": "2",
                "same_domain": "true",
                "use_browser": "false",
            },
        )
        if meta.get("url"):
            out.append(meta)
    return out


def extract_scrape_blocks(text: str) -> list[dict[str, str]]:
    out = []
    for m in SCRAPE_RE.finditer(text or ""):
        meta = _parse_kv_block(
            m.group(1) or "",
            {
                "url": "",
                "mode": "full",
                "selector": "body",
                "use_browser": "false",
                "max_chars": "12000",
            },
        )
        if meta.get("url"):
            out.append(meta)
    return out


def extract_download_blocks(text: str) -> list[dict[str, str]]:
    out = []
    for m in DOWNLOAD_RE.finditer(text or ""):
        meta = _parse_kv_block(
            m.group(1) or "",
            {"url": "", "filename": "", "name": ""},
        )
        if meta.get("name") and not meta.get("filename"):
            meta["filename"] = meta["name"]
        if meta.get("url"):
            out.append(meta)
    return out


def downloads_dir() -> Path:
    d = data_dir() / "browser_downloads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def research_dir() -> Path:
    d = data_dir() / "research"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _bool(v: object, default: bool = False) -> bool:
    if v is None or v == "":
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _domain(url: str) -> str:
    try:
        h = urllib.parse.urlparse(url).netloc.lower()
        return h[4:] if h.startswith("www.") else h
    except Exception:  # noqa: BLE001
        return ""


def _same_site(a: str, b: str) -> bool:
    return _domain(a) == _domain(b) and bool(_domain(a))


def _extract_links(html: str, base_url: str) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    for m in re.finditer(
        r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>',
        html or "",
        re.I,
    ):
        href = html_lib.unescape(m.group(1).strip())
        title = re.sub(r"<[^>]+>", " ", m.group(2) or "")
        title = re.sub(r"\s+", " ", title).strip()[:160]
        if href.startswith("#") or href.lower().startswith("javascript:"):
            continue
        full = urllib.parse.urljoin(base_url, href)
        if not full.startswith("http"):
            continue
        if full in seen:
            continue
        seen.add(full)
        links.append({"url": full, "title": title or full})
        if len(links) >= 80:
            break
    return links


def _extract_tables(html: str, max_tables: int = 5) -> list[list[list[str]]]:
    tables: list[list[list[str]]] = []
    for tm in re.finditer(r"(?is)<table[^>]*>(.*?)</table>", html or ""):
        rows: list[list[str]] = []
        for rm in re.finditer(r"(?is)<tr[^>]*>(.*?)</tr>", tm.group(1)):
            cells = re.findall(r"(?is)<t[dh][^>]*>(.*?)</t[dh]>", rm.group(1))
            row = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip()[:120] for c in cells]
            if any(row):
                rows.append(row)
        if rows:
            tables.append(rows[:40])
        if len(tables) >= max_tables:
            break
    return tables


def _fetch_page(url: str, *, use_browser: bool, max_chars: int) -> dict[str, Any]:
    """Get text + html-ish content for a URL."""
    from app.core.services.web.web_search import fetch_page_text

    if use_browser:
        try:
            from app.core.services.web.browser_tool import run_browser

            go = run_browser(action="goto", url=url, wait_ms="1500")
            if not go.get("ok"):
                # fall through to http
                pass
            else:
                tx = run_browser(action="text", selector="article, main, body", wait_ms="400")
                html_res = run_browser(action="html", wait_ms="100")
                text = (tx.get("text") or "")[:max_chars]
                html = (html_res.get("html") or "")[:200000]
                return {
                    "ok": bool(text or html),
                    "url": tx.get("url") or go.get("url") or url,
                    "title": tx.get("title") or go.get("title") or "",
                    "text": text,
                    "html": html,
                    "method": "browser",
                    "links": _extract_links(html, url),
                }
        except Exception as e:  # noqa: BLE001
            browser_err = str(e)
    else:
        browser_err = ""

    # HTTP path via web_search readability + raw fetch for links
    page = fetch_page_text(url, max_chars=max_chars)
    html = ""
    try:
        from app.core.services.web.web_fetch import web_fetch

        raw = web_fetch(url, max_chars=min(100000, max_chars * 8), save=False)
        if raw.get("ok") and raw.get("text") and "html" in (raw.get("content_type") or "").lower():
            # web_fetch strips tags for text; re-get bytes path not available — use browser html skip
            pass
        # Always try urllib for raw html for link extraction
        import urllib.request

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                )
            },
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="replace")[:200000]
    except Exception:  # noqa: BLE001
        pass

    if page.get("ok"):
        return {
            "ok": True,
            "url": page.get("url") or url,
            "title": page.get("title") or "",
            "text": (page.get("text") or "")[:max_chars],
            "html": html,
            "method": page.get("method") or "http",
            "links": _extract_links(html, url) if html else [],
            "browser_err": browser_err or None,
        }
    return {
        "ok": False,
        "url": url,
        "error": page.get("error") or browser_err or "fetch failed",
        "links": _extract_links(html, url) if html else [],
        "html": html,
        "text": "",
    }


# ─── Public runners ──────────────────────────────────────────────────────────


def run_deep_research(cmd: dict[str, str]) -> dict[str, Any]:
    """Search + open sources + follow a few promising links."""
    from app.core.services.web.web_search import web_search

    lim = _limits()
    query = (cmd.get("query") or "").strip()
    if not query:
        return {"ok": False, "error": "query required"}

    try:
        n_sources = int(cmd.get("sources") or lim["research_sources"])
    except ValueError:
        n_sources = lim["research_sources"]
    n_sources = max(2, min(lim["research_sources"], n_sources))
    try:
        n_follow = int(cmd.get("follow") or lim["research_follow"])
    except ValueError:
        n_follow = lim["research_follow"]
    n_follow = max(0, min(lim["research_follow"], n_follow))
    try:
        max_chars = int(cmd.get("fetch_chars") or lim["max_chars_page"])
    except ValueError:
        max_chars = lim["max_chars_page"]
    same_domain = _bool(cmd.get("same_domain"), False)
    use_browser = _bool(cmd.get("use_browser"), False)

    t0 = time.time()
    search = web_search(query, max_results=max(n_sources, 6), fetch=0, use_cache=True)
    hits = list(search.get("results") or [])[:n_sources]
    if not hits:
        return {
            "ok": False,
            "error": search.get("error") or "no search results",
            "query": query,
            "search": search,
        }

    pages: list[dict[str, Any]] = []

    def open_one(h: dict[str, str]) -> dict[str, Any]:
        u = h.get("url") or ""
        p = _fetch_page(u, use_browser=use_browser, max_chars=max_chars)
        p["search_title"] = h.get("title") or ""
        p["search_source"] = h.get("source") or ""
        p["search_snippet"] = h.get("snippet") or ""
        return p

    with ThreadPoolExecutor(max_workers=min(4, max(1, len(hits)))) as pool:
        futs = [pool.submit(open_one, h) for h in hits]
        for fut in as_completed(futs, timeout=90):
            try:
                pages.append(fut.result())
            except Exception as e:  # noqa: BLE001
                pages.append({"ok": False, "error": str(e)})

    # Follow additional links from successful pages
    followed: list[dict[str, Any]] = []
    if n_follow > 0:
        candidates: list[tuple[str, str]] = []  # url, from_title
        for p in pages:
            if not p.get("ok"):
                continue
            base = p.get("url") or ""
            for L in (p.get("links") or [])[:25]:
                u = L.get("url") or ""
                if not u or u == base:
                    continue
                if same_domain and not _same_site(base, u):
                    continue
                # skip obvious junk
                if any(x in u.lower() for x in ("login", "signup", "cart", "privacy", "cookie")):
                    continue
                candidates.append((u, p.get("title") or p.get("search_title") or ""))
        # unique
        seen = {p.get("url") for p in pages}
        uniq = []
        for u, src in candidates:
            if u in seen:
                continue
            seen.add(u)
            uniq.append((u, src))
            if len(uniq) >= n_follow:
                break

        def open_f(item: tuple[str, str]) -> dict[str, Any]:
            u, parent = item
            p = _fetch_page(u, use_browser=use_browser, max_chars=max_chars // 2)
            p["followed_from"] = parent
            return p

        if uniq:
            with ThreadPoolExecutor(max_workers=min(3, len(uniq))) as pool:
                futs = [pool.submit(open_f, it) for it in uniq]
                for fut in as_completed(futs, timeout=60):
                    try:
                        followed.append(fut.result())
                    except Exception as e:  # noqa: BLE001
                        followed.append({"ok": False, "error": str(e)})

    # Build report for the model
    sources_ok = [p for p in pages if p.get("ok")]
    lines = [
        f"# Deep research: {query}",
        f"Search engines: {', '.join(search.get('backends') or [])}",
        f"Opened {len(sources_ok)}/{len(pages)} primary sources; followed {sum(1 for f in followed if f.get('ok'))} more.",
        "",
        "## Sources",
    ]
    for i, p in enumerate(pages, 1):
        if not p.get("ok"):
            lines.append(f"{i}. FAIL {p.get('url')}: {p.get('error')}")
            continue
        lines.append(f"{i}. **{p.get('title') or p.get('search_title')}**")
        lines.append(f"   {p.get('url')}")
        if p.get("search_snippet"):
            lines.append(f"   snip: {p.get('search_snippet')[:200]}")
        lines.append(f"   extract: {(p.get('text') or '')[:2500]}")
        lines.append("")
    if followed:
        lines.append("## Followed links")
        for p in followed:
            if not p.get("ok"):
                continue
            lines.append(f"- **{p.get('title')}** — {p.get('url')}")
            lines.append(f"  {(p.get('text') or '')[:1200]}")
            lines.append("")

    report = "\n".join(lines)
    # Persist pack for user
    rid = uuid.uuid4().hex[:10]
    out_path = research_dir() / f"{rid}_deep.md"
    try:
        out_path.write_text(report, encoding="utf-8")
    except Exception:  # noqa: BLE001
        out_path = None

    return {
        "ok": True,
        "kind": "deep_research",
        "query": query,
        "search_count": len(hits),
        "pages_ok": len(sources_ok),
        "followed_ok": sum(1 for f in followed if f.get("ok")),
        "backends": search.get("backends"),
        "ms": int((time.time() - t0) * 1000),
        "report": report[:50000],
        "saved_path": str(out_path.resolve()) if out_path else None,
        "sources": [
            {
                "ok": p.get("ok"),
                "url": p.get("url"),
                "title": p.get("title") or p.get("search_title"),
                "method": p.get("method"),
                "chars": len(p.get("text") or ""),
                "error": p.get("error"),
            }
            for p in pages + followed
        ],
    }


def run_crawl(cmd: dict[str, str]) -> dict[str, Any]:
    lim = _limits()
    start = (cmd.get("url") or "").strip()
    if not start.startswith("http"):
        return {"ok": False, "error": "url must be http(s)"}
    try:
        max_pages = int(cmd.get("max_pages") or lim["crawl_max_pages"])
    except ValueError:
        max_pages = lim["crawl_max_pages"]
    max_pages = max(1, min(lim["crawl_max_pages"], max_pages))
    try:
        max_depth = int(cmd.get("max_depth") or lim["crawl_max_depth"])
    except ValueError:
        max_depth = lim["crawl_max_depth"]
    max_depth = max(0, min(lim["crawl_max_depth"], max_depth))
    same_domain = _bool(cmd.get("same_domain"), True)
    use_browser = _bool(cmd.get("use_browser"), False)
    max_chars = lim["max_chars_page"] // 2

    t0 = time.time()
    q: deque[tuple[str, int]] = deque([(start, 0)])
    seen: set[str] = set()
    pages: list[dict[str, Any]] = []

    while q and len(pages) < max_pages:
        url, depth = q.popleft()
        norm = url.split("#")[0].rstrip("/")
        if norm in seen:
            continue
        seen.add(norm)
        page = _fetch_page(url, use_browser=use_browser, max_chars=max_chars)
        page["depth"] = depth
        pages.append(
            {
                "ok": page.get("ok"),
                "url": page.get("url") or url,
                "title": page.get("title") or "",
                "depth": depth,
                "text": (page.get("text") or "")[:max_chars] if page.get("ok") else "",
                "error": page.get("error"),
                "link_count": len(page.get("links") or []),
            }
        )
        if not page.get("ok") or depth >= max_depth:
            continue
        for L in page.get("links") or []:
            u = (L.get("url") or "").split("#")[0]
            if not u.startswith("http"):
                continue
            if same_domain and not _same_site(start, u):
                continue
            n = u.rstrip("/")
            if n not in seen:
                q.append((u, depth + 1))

    # Report
    lines = [
        f"# Crawl: {start}",
        f"pages={len(pages)} depth≤{max_depth} same_domain={same_domain}",
        "",
    ]
    for p in pages:
        if not p.get("ok"):
            lines.append(f"- FAIL d{p.get('depth')}: {p.get('url')} — {p.get('error')}")
            continue
        lines.append(f"- d{p.get('depth')}: **{p.get('title')}**")
        lines.append(f"  {p.get('url')}")
        lines.append(f"  {(p.get('text') or '')[:1500]}")
        lines.append("")

    report = "\n".join(lines)
    rid = uuid.uuid4().hex[:10]
    path = research_dir() / f"{rid}_crawl.md"
    try:
        path.write_text(report, encoding="utf-8")
    except Exception:  # noqa: BLE001
        path = None

    return {
        "ok": True,
        "kind": "crawl",
        "start": start,
        "pages": len(pages),
        "ok_pages": sum(1 for p in pages if p.get("ok")),
        "ms": int((time.time() - t0) * 1000),
        "report": report[:50000],
        "saved_path": str(path.resolve()) if path else None,
        "items": pages,
    }


def run_scrape(cmd: dict[str, str]) -> dict[str, Any]:
    url = (cmd.get("url") or "").strip()
    if not url.startswith("http"):
        return {"ok": False, "error": "url required"}
    mode = (cmd.get("mode") or "full").lower().strip()
    selector = (cmd.get("selector") or "body").strip()
    use_browser = _bool(cmd.get("use_browser"), False)
    try:
        max_chars = int(cmd.get("max_chars") or 12000)
    except ValueError:
        max_chars = 12000

    # Prefer browser when css selector requested
    if mode == "css" or use_browser:
        try:
            from app.core.services.web.browser_tool import run_browser

            run_browser(action="goto", url=url, wait_ms="1500")
            if mode == "css":
                res = run_browser(action="text", selector=selector, wait_ms="400")
                return {
                    "ok": bool(res.get("ok")),
                    "kind": "scrape",
                    "mode": "css",
                    "url": res.get("url") or url,
                    "title": res.get("title"),
                    "selector": selector,
                    "text": (res.get("text") or "")[:max_chars],
                    "error": res.get("error"),
                }
            if mode == "links":
                res = run_browser(action="links", n="50")
                return {
                    "ok": bool(res.get("ok")),
                    "kind": "scrape",
                    "mode": "links",
                    "url": res.get("url") or url,
                    "links": (res.get("links") or [])[:50],
                    "error": res.get("error"),
                }
            html_res = run_browser(action="html", wait_ms="200")
            tx = run_browser(action="text", selector="article, main, body", wait_ms="200")
            html = html_res.get("html") or ""
            out: dict[str, Any] = {
                "ok": True,
                "kind": "scrape",
                "mode": mode,
                "url": tx.get("url") or url,
                "title": tx.get("title"),
                "method": "browser",
            }
            if mode in ("full", "text"):
                out["text"] = (tx.get("text") or "")[:max_chars]
            if mode in ("full", "links"):
                out["links"] = _extract_links(html, url)[:50]
            if mode in ("full", "tables"):
                out["tables"] = _extract_tables(html)[:5]
            if mode == "meta":
                out["meta"] = {
                    "title": tx.get("title"),
                    "url": tx.get("url"),
                    "chars": len(tx.get("text") or ""),
                }
            return out
        except Exception as e:  # noqa: BLE001
            if mode == "css":
                return {"ok": False, "error": f"css scrape needs browser: {e}"}

    page = _fetch_page(url, use_browser=False, max_chars=max_chars)
    html = page.get("html") or ""
    if not page.get("ok") and not html:
        return {"ok": False, "kind": "scrape", "error": page.get("error"), "url": url}

    out = {
        "ok": True,
        "kind": "scrape",
        "mode": mode,
        "url": page.get("url") or url,
        "title": page.get("title") or "",
        "method": page.get("method"),
    }
    if mode in ("full", "text"):
        out["text"] = (page.get("text") or "")[:max_chars]
    if mode in ("full", "links"):
        out["links"] = (page.get("links") or _extract_links(html, url))[:50]
    if mode in ("full", "tables"):
        out["tables"] = _extract_tables(html)[:5]
    if mode == "meta":
        out["meta"] = {
            "title": page.get("title"),
            "url": page.get("url"),
            "chars": len(page.get("text") or ""),
            "links": len(page.get("links") or []),
        }
    return out


def run_download(cmd: dict[str, str]) -> dict[str, Any]:
    url = (cmd.get("url") or "").strip()
    if not url.startswith("http"):
        return {"ok": False, "error": "url required"}
    filename = (cmd.get("filename") or cmd.get("name") or "").strip()

    # Prefer web_fetch save
    from app.core.services.web.web_fetch import web_fetch

    res = web_fetch(url, save=True, max_chars=500)
    if res.get("ok") and res.get("path"):
        path = Path(str(res["path"]))
        if filename:
            dest = downloads_dir() / Path(filename).name
            try:
                path.replace(dest)
                path = dest
            except Exception:  # noqa: BLE001
                pass
        return {
            "ok": True,
            "kind": "download",
            "url": url,
            "path": str(path.resolve()),
            "bytes": res.get("bytes") or (path.stat().st_size if path.is_file() else 0),
            "content_type": res.get("content_type"),
            "method": "http",
        }

    # Browser download fallback
    try:
        from app.core.services.web.browser_tool import run_browser

        b = run_browser(action="download", url=url)
        if b.get("ok") and b.get("path"):
            return {
                "ok": True,
                "kind": "download",
                "url": url,
                "path": b.get("path"),
                "bytes": b.get("bytes"),
                "method": "browser",
            }
        return {"ok": False, "error": b.get("error") or res.get("error") or "download failed", "url": url}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e) or res.get("error"), "url": url}


def run_research_command(kind: str, cmd: dict[str, str]) -> dict[str, Any]:
    kind = (kind or "").lower()
    if kind == "deep_research":
        return run_deep_research(cmd)
    if kind == "crawl":
        return run_crawl(cmd)
    if kind == "scrape":
        return run_scrape(cmd)
    if kind == "download":
        return run_download(cmd)
    return {"ok": False, "error": f"unknown research kind: {kind}"}
