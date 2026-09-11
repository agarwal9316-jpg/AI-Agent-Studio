"""
WEB_FETCH — raw HTTP access for the agent (any public URL).

Use for APIs, RSS, static pages, downloads. Prefer BROWSER for JS-heavy sites.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from app.paths import data_dir

FETCH_RE = re.compile(
    r"<<<WEB_FETCH>>>\s*(.*?)\s*<<<END_WEB_FETCH>>>",
    re.DOTALL | re.IGNORECASE,
)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def tool_instructions() -> str:
    return """
## WEB_FETCH — open any URL via HTTP (full internet GET/POST)

Use when you need the raw content of a URL, API JSON, RSS, or a static page.
Does **not** run JavaScript — for SPAs use BROWSER instead.

<<<WEB_FETCH>>>
url: https://api.github.com/repos/python/cpython
method: GET
<<<END_WEB_FETCH>>>

<<<WEB_FETCH>>>
url: https://example.com
max_chars: 15000
<<<END_WEB_FETCH>>>

<<<WEB_FETCH>>>
url: https://httpbin.org/post
method: POST
body: {"q":"test"}
content_type: application/json
<<<END_WEB_FETCH>>>

<<<WEB_FETCH>>>
url: https://example.com/file.pdf
save: true
<<<END_WEB_FETCH>>>

Fields: url (required), method (GET|POST|HEAD), headers (JSON), body, content_type,
max_chars (default 20000), save (true = download to data/browser_downloads).
""".strip()


def extract_fetch_blocks(text: str) -> list[dict[str, str]]:
    out = []
    for m in FETCH_RE.finditer(text or ""):
        body = (m.group(1) or "").strip()
        meta: dict[str, str] = {
            "url": "",
            "method": "GET",
            "body": "",
            "content_type": "",
            "headers": "",
            "max_chars": "20000",
            "save": "false",
        }
        for line in body.splitlines():
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            k = k.strip().lower()
            v = v.strip()
            if k in meta or k in ("url", "method", "body", "content_type", "headers", "max_chars", "save"):
                if k == "json":
                    meta["body"] = v
                    meta["content_type"] = meta.get("content_type") or "application/json"
                else:
                    meta[k] = v
        if not meta.get("url") and body.startswith("http"):
            meta["url"] = body.splitlines()[0].strip()
        if meta.get("url"):
            out.append(meta)
    return out


def downloads_dir() -> Path:
    d = data_dir() / "browser_downloads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def web_fetch(
    url: str,
    *,
    method: str = "GET",
    body: str = "",
    content_type: str = "",
    headers_json: str = "",
    max_chars: int = 20000,
    save: bool = False,
) -> dict[str, Any]:
    url = (url or "").strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        return {"ok": False, "error": "url must be http(s)"}

    method = (method or "GET").upper().strip()
    if method not in ("GET", "POST", "HEAD", "PUT", "DELETE"):
        return {"ok": False, "error": f"method not allowed: {method}"}

    headers = {
        "User-Agent": _UA,
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "identity",
    }
    if headers_json:
        try:
            extra = json.loads(headers_json)
            if isinstance(extra, dict):
                headers.update({str(k): str(v) for k, v in extra.items()})
        except Exception:  # noqa: BLE001
            pass
    data = None
    if body and method in ("POST", "PUT"):
        data = body.encode("utf-8")
        headers["Content-Type"] = content_type or "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read()
            ctype = resp.headers.get("Content-Type") or ""
            status = resp.status
            final = resp.geturl()
    except urllib.error.HTTPError as e:
        raw = e.read() if e.fp else b""
        ctype = e.headers.get("Content-Type") if e.headers else ""
        status = e.code
        final = url
        if not raw:
            return {"ok": False, "error": f"HTTP {e.code}", "url": url, "status": e.code}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "url": url}

    path = ""
    if save or _looks_binary(ctype, raw):
        ext = _ext_from(url, ctype)
        dest = downloads_dir() / f"{uuid.uuid4().hex[:10]}_fetch{ext}"
        dest.write_bytes(raw)
        path = str(dest.resolve())
        if save or _looks_binary(ctype, raw):
            return {
                "ok": True,
                "url": final,
                "status": status,
                "content_type": ctype,
                "bytes": len(raw),
                "path": path,
                "saved": True,
                "text": "" if _looks_binary(ctype, raw) else raw.decode("utf-8", errors="replace")[: max_chars],
            }

    # Text
    text = raw.decode("utf-8", errors="replace")
    # strip scripts for HTML
    if "html" in (ctype or "").lower() or text.lstrip().lower().startswith("<!doctype") or text.lstrip().startswith("<html"):
        text = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", text)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()

    max_chars = max(500, min(100000, int(max_chars or 20000)))
    return {
        "ok": True,
        "url": final,
        "status": status,
        "content_type": ctype,
        "bytes": len(raw),
        "text": text[:max_chars],
        "chars": min(len(text), max_chars),
        "truncated": len(text) > max_chars,
        "path": path or None,
    }


def run_fetch_command(cmd: dict[str, str]) -> dict[str, Any]:
    try:
        mx = int(cmd.get("max_chars") or 20000)
    except ValueError:
        mx = 20000
    save = str(cmd.get("save") or "").lower() in ("1", "true", "yes")
    return web_fetch(
        cmd.get("url") or "",
        method=cmd.get("method") or "GET",
        body=cmd.get("body") or "",
        content_type=cmd.get("content_type") or "",
        headers_json=cmd.get("headers") or "",
        max_chars=mx,
        save=save,
    )


def _looks_binary(ctype: str, raw: bytes) -> bool:
    ct = (ctype or "").lower()
    if any(x in ct for x in ("image/", "video/", "audio/", "pdf", "zip", "octet-stream", "msword", "spreadsheet")):
        return True
    if raw[:4] == b"%PDF" or raw[:2] == b"PK":
        return True
    return False


def _ext_from(url: str, ctype: str) -> str:
    path = urllib.parse.urlparse(url).path
    suf = Path(path).suffix.lower()
    if suf and len(suf) < 8:
        return suf
    ct = (ctype or "").lower()
    if "pdf" in ct:
        return ".pdf"
    if "json" in ct:
        return ".json"
    if "png" in ct:
        return ".png"
    if "jpeg" in ct or "jpg" in ct:
        return ".jpg"
    if "html" in ct:
        return ".html"
    return ".bin"
