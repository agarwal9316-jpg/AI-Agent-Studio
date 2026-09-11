"""
In-chat media: LLM can show images/videos (local paths OR http/https URLs).
Media is downloaded/copied under data/chat_media/ for stable display.
"""

from __future__ import annotations

import json
import re
import shutil
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from app.paths import data_dir

IMAGE_BLOCK_RE = re.compile(
    r"<<<(?:SHOW_)?IMAGE>>>\s*(.*?)\s*<<<END_(?:SHOW_)?IMAGE>>>",
    re.DOTALL | re.IGNORECASE,
)
VIDEO_BLOCK_RE = re.compile(
    r"<<<(?:SHOW_)?VIDEO>>>\s*(.*?)\s*<<<END_(?:SHOW_)?VIDEO>>>",
    re.DOTALL | re.IGNORECASE,
)
# Markdown image: ![alt](path_or_url)
MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
# Bare https image URL on its own line (fallback if LLM forgets blocks)
BARE_IMAGE_URL_RE = re.compile(
    r"(?m)^(https?://[^\s<>\"']+\.(?:png|jpe?g|gif|webp|bmp|ico)(?:\?[^\s]*)?)\s*$",
    re.IGNORECASE,
)

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico"}
VIDEO_EXT = {".mp4", ".webm", ".mkv", ".avi", ".mov", ".wmv", ".m4v"}

# Wikimedia production standard thumbnail widths (direct hotlinks only)
# https://www.mediawiki.org/wiki/Common_thumbnail_sizes
WIKI_THUMB_STEPS = (20, 40, 60, 120, 250, 330, 500, 960, 1280, 1920, 3840)

_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 "
        "AI-Agent-Studio/1.4"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def media_root() -> Path:
    d = data_dir() / "chat_media"
    d.mkdir(parents=True, exist_ok=True)
    return d


def chat_media_dir(chat_id: str = "default") -> Path:
    d = media_root() / (chat_id or "default")
    d.mkdir(parents=True, exist_ok=True)
    return d


def media_tool_instructions() -> str:
    return """
## Show images & videos IN the chat UI (full media support)

You can display media inside the user's chat bubbles.
Use a **local file path** OR a public **https:// URL**.

### Show an image (URL or path)
<<<IMAGE>>>
https://example.com/photo.jpg
<<<END_IMAGE>>>

<<<IMAGE>>>
C:\\path\\to\\image.png
<<<END_IMAGE>>>

### Show a video
<<<VIDEO>>>
C:\\path\\to\\video.mp4
<<<END_VIDEO>>>

Also: markdown `![caption](https://.../image.jpg)`

Rules:
- Prefer direct image URLs (jpg/png/webp/gif). The app downloads them and shows the picture in chat.
- For Wikipedia/Wikimedia: prefer the full file URL (no /thumb/) or a standard thumb width
  (250, 330, 500, 960, 1280). Avoid non-standard sizes like 800px.
- Do NOT leave IMAGE blocks as plain text for the user — the UI will convert them to images.
- After SCREENSHOT, the image is auto-shown.
- Multiple IMAGE/VIDEO blocks allowed.
""".strip()


def _extract_path(body: str) -> str:
    line = (body or "").strip().splitlines()[0].strip().strip('"').strip("'")
    if line.lower().startswith("file:///"):
        line = line[8:]
    elif line.lower().startswith("file://"):
        line = line[7:]
    return line.strip()


def _is_http_url(s: str) -> bool:
    return s.lower().startswith("http://") or s.lower().startswith("https://")


def _guess_ext_from_url(url: str, content_type: str = "") -> str:
    path = unquote(urlparse(url).path)
    ext = Path(path).suffix.lower()
    if ext in IMAGE_EXT or ext in VIDEO_EXT:
        return ext
    ct = (content_type or "").lower()
    if "png" in ct:
        return ".png"
    if "jpeg" in ct or "jpg" in ct:
        return ".jpg"
    if "gif" in ct:
        return ".gif"
    if "webp" in ct:
        return ".webp"
    if "mp4" in ct:
        return ".mp4"
    if "webm" in ct:
        return ".webm"
    return ".jpg"


def _nearest_wiki_thumb_size(size: int) -> int:
    for s in WIKI_THUMB_STEPS:
        if s >= size:
            return s
    return WIKI_THUMB_STEPS[-1]


def _wikimedia_parse_thumb(url: str) -> dict[str, Any] | None:
    """Parse upload.wikimedia.org thumb or full path."""
    if "upload.wikimedia.org" not in url:
        return None
    try:
        parts = urlparse(url)
        segs = [s for s in parts.path.split("/") if s]
        # e.g. wikipedia/commons/thumb/3/3a/File.jpg/800px-File.jpg
        # or wikipedia/commons/3/3a/File.jpg
        if len(segs) < 4:
            return None
        project = segs[0]  # wikipedia
        bucket = segs[1]  # commons / en / …
        rest = segs[2:]
        is_thumb = bool(rest and rest[0] == "thumb")
        if is_thumb:
            rest = rest[1:]
        # rest: hash1, hash2, filename[, sizepx-filename]
        if len(rest) < 3:
            return None
        h1, h2, filename = rest[0], rest[1], rest[2]
        size = None
        if is_thumb and len(rest) >= 4:
            m = re.match(r"^(\d+)px-", rest[3], re.I)
            if m:
                size = int(m.group(1))
        return {
            "project": project,
            "bucket": bucket,
            "h1": h1,
            "h2": h2,
            "filename": filename,
            "size": size,
            "is_thumb": is_thumb,
            "scheme": parts.scheme or "https",
            "netloc": parts.netloc,
        }
    except Exception:  # noqa: BLE001
        return None


def _wikimedia_full_url(url: str) -> str | None:
    """Convert commons thumb URL to full file URL when needed."""
    info = _wikimedia_parse_thumb(url)
    if not info:
        return None
    path = (
        f"/{info['project']}/{info['bucket']}/"
        f"{info['h1']}/{info['h2']}/{info['filename']}"
    )
    return f"{info['scheme']}://{info['netloc']}{path}"


def _wikimedia_thumb_url(url: str, size: int) -> str | None:
    info = _wikimedia_parse_thumb(url)
    if not info:
        return None
    size = _nearest_wiki_thumb_size(size)
    fname = info["filename"]
    path = (
        f"/{info['project']}/{info['bucket']}/thumb/"
        f"{info['h1']}/{info['h2']}/{fname}/{size}px-{fname}"
    )
    return f"{info['scheme']}://{info['netloc']}{path}"


def _wikimedia_api_urls(url: str) -> list[str]:
    """Resolve image via MediaWiki imageinfo API (preferred for Wikimedia)."""
    info = _wikimedia_parse_thumb(url)
    if not info:
        return []
    # Decode filename for API title
    fname = unquote(info["filename"]).replace("_", " ")
    title = f"File:{fname}"
    # commons vs language projects
    if info["bucket"] == "commons":
        api_host = "https://commons.wikimedia.org/w/api.php"
    else:
        api_host = f"https://{info['bucket']}.wikipedia.org/w/api.php"
    out: list[str] = []
    for width in (960, 500, 330, 250, 0):
        params: dict[str, Any] = {
            "action": "query",
            "titles": title,
            "prop": "imageinfo",
            "iiprop": "url|mime|size",
            "format": "json",
        }
        if width:
            params["iiurlwidth"] = width
        api = api_host + "?" + urllib.parse.urlencode(params)
        try:
            req = urllib.request.Request(api, headers=_HTTP_HEADERS, method="GET")
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
            pages = (data.get("query") or {}).get("pages") or {}
            for page in pages.values():
                if page.get("missing") is not None:
                    continue
                for ii in page.get("imageinfo") or []:
                    for key in ("thumburl", "url"):
                        u = ii.get(key)
                        if u and u not in out:
                            out.append(u)
        except Exception:  # noqa: BLE001
            continue
    return out


def _http_get_bytes(url: str, *, referer: str | None = None) -> tuple[bytes, str] | None:
    headers = dict(_HTTP_HEADERS)
    parsed = urlparse(url)
    # Hotlink protection: always send a same-site Referer when possible
    if referer:
        headers["Referer"] = referer
    elif "wikimedia.org" in url or "wikipedia.org" in url:
        headers["Referer"] = "https://commons.wikimedia.org/"
    elif parsed.scheme and parsed.netloc:
        headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"
    headers.setdefault("Accept", "image/avif,image/webp,image/apng,image/*,*/*;q=0.8")
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        # Follow redirects (some CDNs bounce to signed URLs)
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
            ctype = resp.headers.get("Content-Type") or ""
            final_url = resp.geturl() or url
        # reject tiny / empty
        if not data or len(data) < 32:
            return None
        # HTML error / login / captcha page — not media
        head = data[:300].lower()
        if ("text/html" in ctype.lower() or b"<html" in head or b"<!doctype html" in head) and not (
            data[:8] == b"\x89PNG\r\n\x1a\n" or data[:3] == b"\xff\xd8\xff"
        ):
            return None
        # SVG is valid "image" for save (UI may open externally)
        if b"<svg" in head or "svg" in ctype.lower():
            return data, ctype or "image/svg+xml"
        # If no extension and no ctype, still accept image magic
        if data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n" or data[:6] in (
            b"GIF87a",
            b"GIF89a",
        ):
            return data, ctype or "image/jpeg"
        # remember final url via ctype annotation for caller? not needed — data is enough
        _ = final_url
        return data, ctype
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return None


def _wikipedia_file_page_urls(url: str) -> list[str]:
    """If LLM linked a Wikipedia File: page, resolve to actual image URL(s)."""
    u = url or ""
    if "wikipedia.org" not in u and "wikimedia.org" not in u:
        return []
    # https://en.wikipedia.org/wiki/File:Something.jpg
    m = re.search(r"/wiki/File:([^?#]+)", u, re.I)
    if not m:
        return []
    fname = unquote(m.group(1)).replace("_", " ")
    title = f"File:{fname}"
    host = urlparse(u).netloc or "en.wikipedia.org"
    if "commons" in host:
        api = "https://commons.wikimedia.org/w/api.php"
    else:
        # language wiki
        api = f"https://{host}/w/api.php"
    out: list[str] = []
    for width in (960, 500, 0):
        params: dict[str, Any] = {
            "action": "query",
            "titles": title,
            "prop": "imageinfo",
            "iiprop": "url|mime|size",
            "format": "json",
        }
        if width:
            params["iiurlwidth"] = width
        try:
            req = urllib.request.Request(
                api + "?" + urllib.parse.urlencode(params),
                headers=_HTTP_HEADERS,
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
            pages = (data.get("query") or {}).get("pages") or {}
            for page in pages.values():
                for ii in page.get("imageinfo") or []:
                    for key in ("thumburl", "url"):
                        got = ii.get(key)
                        if got and got not in out:
                            out.append(got)
        except Exception:  # noqa: BLE001
            continue
    return out


def _candidate_urls(url: str) -> list[str]:
    """Build ordered download candidates for a remote media URL."""
    candidates: list[str] = [url]
    # Wikipedia File: page → real media
    for u in _wikipedia_file_page_urls(url):
        if u not in candidates:
            candidates.append(u)
    if "upload.wikimedia.org" in url:
        # 1) API-resolved URLs (best)
        for u in _wikimedia_api_urls(url):
            if u not in candidates:
                candidates.append(u)
        # 2) Full original
        full = _wikimedia_full_url(url)
        if full and full not in candidates:
            candidates.append(full)
        # 3) Standard thumb sizes near requested
        info = _wikimedia_parse_thumb(url)
        req_size = (info or {}).get("size") or 960
        for s in (
            _nearest_wiki_thumb_size(int(req_size)),
            960,
            500,
            330,
            250,
            1280,
        ):
            tu = _wikimedia_thumb_url(url, s)
            if tu and tu not in candidates:
                candidates.append(tu)
    return candidates


def download_url(url: str, chat_id: str = "default") -> str | None:
    """Download remote media into chat_media; return local path."""
    seen: set[str] = set()
    parsed0 = urlparse(url)
    default_ref = (
        f"{parsed0.scheme}://{parsed0.netloc}/" if parsed0.scheme and parsed0.netloc else None
    )
    for u in _candidate_urls(url):
        if u in seen:
            continue
        seen.add(u)
        # Try with site referer, then without, then with commons for wiki
        referers: list[str | None] = [default_ref, None]
        if "wikimedia" in u or "wikipedia" in u:
            referers = ["https://commons.wikimedia.org/", default_ref, None]
        got = None
        for ref in referers:
            got = _http_get_bytes(u, referer=ref)
            if got:
                break
        if not got:
            continue
        data, ctype = got
        is_svg = b"<svg" in data[:500].lower() or "svg" in (ctype or "").lower()
        # magic-byte sanity for common images
        if not (
            data[:3] == b"\xff\xd8\xff"  # jpeg
            or data[:8] == b"\x89PNG\r\n\x1a\n"
            or data[:6] in (b"GIF87a", b"GIF89a")
            or data[:4] == b"RIFF"
            or data[:4] == b"\x00\x00\x00\x18"
            or data[:4] == b"\x00\x00\x00\x1c"
            or is_svg
            or "image/" in (ctype or "").lower()
            or "video/" in (ctype or "").lower()
            or "octet-stream" in (ctype or "").lower()
        ):
            # still allow if large enough binary
            if len(data) < 200:
                continue
        ext = _guess_ext_from_url(u, ctype)
        if is_svg and ext not in (".svg",):
            ext = ".svg"
        dest = chat_media_dir(chat_id) / f"{uuid.uuid4().hex[:12]}_web{ext}"
        try:
            dest.write_bytes(data)
            return str(dest.resolve())
        except OSError:
            continue
    return None


def extract_media_from_text(text: str) -> tuple[list[str], list[str], str]:
    """
    Parse IMAGE/VIDEO blocks and markdown images from assistant text.
    Returns (image_refs, video_refs, cleaned_text_without_blocks).
    Refs may be local paths or http(s) URLs — stage_media_file resolves them.
    """
    images: list[str] = []
    videos: list[str] = []
    cleaned = text or ""
    had_blocks = False

    for m in IMAGE_BLOCK_RE.finditer(text or ""):
        had_blocks = True
        p = _extract_path(m.group(1))
        if p:
            images.append(p)
    cleaned = IMAGE_BLOCK_RE.sub("", cleaned)

    for m in VIDEO_BLOCK_RE.finditer(text or ""):
        had_blocks = True
        p = _extract_path(m.group(1))
        if p:
            videos.append(p)
    cleaned = VIDEO_BLOCK_RE.sub("", cleaned)

    for m in MD_IMAGE_RE.finditer(cleaned):
        p = _extract_path(m.group(1))
        if not p:
            continue
        had_blocks = True
        if _is_http_url(p):
            ext = Path(unquote(urlparse(p).path)).suffix.lower()
            if ext in VIDEO_EXT:
                videos.append(p)
            else:
                images.append(p)
        elif Path(p).suffix.lower() in IMAGE_EXT:
            images.append(p)
        elif Path(p).suffix.lower() in VIDEO_EXT:
            videos.append(p)

    cleaned = MD_IMAGE_RE.sub("", cleaned)

    # Bare image URLs on their own line (only if no blocks already grabbed them)
    if not images:
        for m in BARE_IMAGE_URL_RE.finditer(cleaned):
            u = m.group(1).strip()
            if u and u not in images:
                images.append(u)
                had_blocks = True
        if had_blocks:
            cleaned = BARE_IMAGE_URL_RE.sub("", cleaned)

    # Collapse leftover blank lines from removed blocks
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return images, videos, cleaned


def stage_media_file(src: str | Path, chat_id: str = "default") -> str | None:
    """Copy local file OR download http(s) URL into chat_media; return local path."""
    s = str(src).strip()
    if not s:
        return None

    if _is_http_url(s):
        return download_url(s, chat_id)

    p = Path(s)
    if not p.is_file():
        if not p.exists():
            return None
    try:
        dest_dir = chat_media_dir(chat_id)
        dest = dest_dir / f"{uuid.uuid4().hex[:10]}_{p.name}"
        shutil.copy2(str(p), str(dest))
        return str(dest.resolve())
    except OSError:
        try:
            return str(p.resolve()) if p.is_file() else None
        except OSError:
            return None


def stage_many(paths: list[str], chat_id: str = "default") -> list[str]:
    out: list[str] = []
    for p in paths:
        s = stage_media_file(p, chat_id)
        if s:
            out.append(s)
    return out


def stage_many_with_failures(
    paths: list[str], chat_id: str = "default"
) -> tuple[list[str], list[str]]:
    """Return (staged_local_paths, failed_original_refs)."""
    ok: list[str] = []
    failed: list[str] = []
    for p in paths:
        s = stage_media_file(p, chat_id)
        if s:
            ok.append(s)
        else:
            failed.append(str(p).strip())
    return ok, failed


def classify_path(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext in VIDEO_EXT:
        return "video"
    return "file"


def enrich_message_with_media(
    message: dict[str, Any],
    *,
    chat_id: str = "default",
    extra_images: list[str] | None = None,
    extra_videos: list[str] | None = None,
) -> dict[str, Any]:
    """Parse content for media blocks and merge staged paths onto message."""
    content = message.get("content") or ""
    imgs_raw, vids_raw, cleaned = extract_media_from_text(content)
    all_imgs = list(imgs_raw) + list(extra_images or [])
    all_vids = list(vids_raw) + list(extra_videos or [])

    imgs, failed_imgs = stage_many_with_failures(all_imgs, chat_id)
    vids, failed_vids = stage_many_with_failures(all_vids, chat_id)

    # stage any already-attached local/url paths
    existing_imgs, fail_e_i = stage_many_with_failures(list(message.get("images") or []), chat_id)
    existing_vids, fail_e_v = stage_many_with_failures(list(message.get("videos") or []), chat_id)
    imgs = list(dict.fromkeys(imgs + existing_imgs))
    vids = list(dict.fromkeys(vids + existing_vids))
    failed_imgs = list(dict.fromkeys(failed_imgs + fail_e_i + list(message.get("failed_images") or [])))
    failed_vids = list(dict.fromkeys(failed_vids + fail_e_v + list(message.get("failed_videos") or [])))

    # Always strip media markers when we found any refs — never leave raw IMAGE tags
    had_media = bool(imgs_raw or vids_raw or extra_images or extra_videos)
    if had_media:
        # Keep a short note if download failed and no text remains
        if not cleaned and (failed_imgs or failed_vids) and not (imgs or vids):
            n = len(failed_imgs) + len(failed_vids)
            cleaned = (
                f"(Media link could not be downloaded — open below · {n} file(s). "
                "Hotlink-blocked, login-walled, or not a direct image URL. "
                "Prefer a direct .jpg/.png link or use BROWSER/screenshot.)"
            )
        elif cleaned and (failed_imgs or failed_vids) and not (imgs or vids):
            n = len(failed_imgs) + len(failed_vids)
            cleaned = (
                cleaned.rstrip()
                + f"\n\n_(Could not embed {n} media link(s) — use **Open in browser** below.)_"
            )
        message["content"] = cleaned
    message["images"] = imgs
    message["videos"] = vids
    message["failed_images"] = [u for u in failed_imgs if _is_http_url(u) or u]
    message["failed_videos"] = [u for u in failed_vids if _is_http_url(u) or u]
    return message


def video_thumbnail(path: str, out_dir: Path | None = None) -> str | None:
    """Best-effort first-frame thumbnail for in-chat video preview."""
    p = Path(path)
    if not p.is_file():
        return None
    out_dir = out_dir or chat_media_dir("thumbs")
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{p.stem}_thumb.jpg"
    if dest.is_file():
        return str(dest)
    try:
        import cv2  # type: ignore

        cap = cv2.VideoCapture(str(p))
        ok, frame = cap.read()
        cap.release()
        if ok and frame is not None:
            cv2.imwrite(str(dest), frame)
            return str(dest)
    except Exception:  # noqa: BLE001
        pass
    return None
