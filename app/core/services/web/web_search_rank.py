"""Web search ranking / dedupe / URL cleanup helpers.

Extracted from web_search.py so ranking logic can be tested and reused
without loading every search provider.
"""
from __future__ import annotations

import html as html_lib
import re
import urllib.parse
from typing import Any

# Defaults mirrored from web_search (avoid circular import)
TARGET_UNIQUE_DOMAINS = 18
HARD_MAX_RESULTS = 40

_JUNK_TITLE = re.compile(
    r"^(report a security|status|sign in|log in|privacy|cookie|subscribe|"
    r"advertisement|home\s*$|menu\s*$|skip to|enable javascript)",
    re.I,
)


def _clean_text(s: str) -> str:
    t = html_lib.unescape((s or "").strip())
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def _unwrap_ddg_url(url: str) -> str:
    try:
        if "duckduckgo.com/l/?" in url or "duckduckgo.com/l?" in url:
            q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            uddg = q.get("uddg") or q.get("u")
            if uddg:
                return urllib.parse.unquote(uddg[0])
    except Exception:
        pass
    return url


def _unwrap_google_news_url(url: str) -> str:
    try:
        if "news.google.com" in url:
            q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            for key in ("url", "q"):
                if key in q and q[key]:
                    return urllib.parse.unquote(q[key][0])
    except Exception:
        pass
    return url


def _is_bad_url(url: str) -> bool:
    u = (url or "").lower()
    if not u.startswith("http"):
        return True
    bad = (
        "javascript:",
        "mailto:",
        "/login",
        "/signin",
        "/signup",
        "accounts.google",
        "consent.google",
    )
    return any(b in u for b in bad)


def _is_challenge_page(title: str, snippet: str) -> bool:
    blob = f"{title} {snippet}".lower()
    markers = (
        "captcha",
        "unusual traffic",
        "enable javascript",
        "access denied",
        "cf-browser-verification",
    )
    return any(m in blob for m in markers)


def _domain(url: str) -> str:
    try:
        host = urllib.parse.urlparse(url).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def _query_tokens(query: str) -> set[str]:
    toks = re.findall(r"[a-z0-9]{3,}", (query or "").lower())
    return set(toks)


def _score_result(item: dict[str, Any], query: str) -> float:
    title = _clean_text(str(item.get("title") or ""))
    snippet = _clean_text(str(item.get("snippet") or item.get("body") or ""))
    url = str(item.get("url") or item.get("link") or "")
    if _is_bad_url(url) or _is_challenge_page(title, snippet):
        return -1.0
    if _JUNK_TITLE.search(title):
        return -0.5
    q = _query_tokens(query)
    blob = f"{title} {snippet}".lower()
    hits = sum(1 for t in q if t in blob)
    score = hits * 1.5
    score += min(len(snippet), 240) / 120.0
    if title:
        score += 0.5
    return score


def rank_and_dedupe(
    results: list[dict[str, Any]],
    query: str,
    *,
    max_results: int = 25,
    min_domains: int = TARGET_UNIQUE_DOMAINS,
) -> list[dict[str, Any]]:
    """Score, sort, and dedupe results by URL/domain diversity."""
    scored: list[tuple[float, dict[str, Any]]] = []
    for item in results or []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or item.get("link") or "")
        url = _unwrap_google_news_url(_unwrap_ddg_url(url))
        item = dict(item)
        item["url"] = url
        item.setdefault("title", item.get("title") or "")
        item.setdefault("snippet", item.get("snippet") or item.get("body") or "")
        sc = _score_result(item, query)
        if sc < 0:
            continue
        scored.append((sc, item))
    scored.sort(key=lambda x: x[0], reverse=True)
    return _dedupe([it for _, it in scored], max_results=max_results, min_domains=min_domains)


def _dedupe(
    items: list[dict[str, Any]],
    *,
    max_results: int = 25,
    min_domains: int = TARGET_UNIQUE_DOMAINS,
) -> list[dict[str, Any]]:
    seen_url: set[str] = set()
    seen_dom: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        url = str(item.get("url") or "")
        if not url or url in seen_url:
            continue
        dom = _domain(url)
        # Soft domain diversity: allow repeats after min_domains satisfied
        if dom and dom in seen_dom and len(seen_dom) < min_domains and len(out) < max_results:
            # still allow if we have room and need volume
            pass
        seen_url.add(url)
        if dom:
            seen_dom.add(dom)
        out.append(item)
        if len(out) >= max_results or len(out) >= HARD_MAX_RESULTS:
            break
    return out
