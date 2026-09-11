"""Image generation via OpenAI-compatible /images/generations API."""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from app.paths import data_dir
from app.core.services.chat.media_chat import chat_media_dir
from app.core.services.llm.providers import resolve_active_llm
from app.core.services.data.storage import load_config


class ImageGenError(Exception):
    pass


def generated_dir(chat_id: str = "default") -> Path:
    d = data_dir() / "generated_images" / (chat_id or "default")
    d.mkdir(parents=True, exist_ok=True)
    return d


def generate_image(
    prompt: str,
    *,
    size: str = "1024x1024",
    model: str = "",
    api_key: str = "",
    base_url: str = "",
    chat_id: str = "default",
    n: int = 1,
) -> dict[str, Any]:
    """
    Call OpenAI-compatible images API. Returns {ok, paths, raw}.
    Works with OpenAI; some OpenRouter models may not support images — error is clear.
    """
    prompt = (prompt or "").strip()
    if not prompt:
        raise ImageGenError("Image prompt is empty")

    cfg = load_config()
    try:
        active = resolve_active_llm()
    except Exception:  # noqa: BLE001
        active = {}

    key = (api_key or active.get("api_key") or cfg.get("api_key") or "").strip()
    if not key:
        raise ImageGenError("No API key for image generation. Add one in Settings.")

    base = (base_url or active.get("base_url") or cfg.get("api_base_url") or "https://api.openai.com/v1").rstrip(
        "/"
    )
    # Prefer dedicated image model if configured (presets via capabilities)
    try:
        from app.core.services.tools.capabilities import resolve_image_model

        img_model = (
            model
            or resolve_image_model(str(cfg.get("image_preset") or ""), str(cfg.get("image_model") or ""))
            or "dall-e-3"
        ).strip()
    except Exception:  # noqa: BLE001
        img_model = (model or cfg.get("image_model") or "dall-e-3").strip()

    # Honest warn path: provider with no image support still attempts API (user may override)
    try:
        from app.core.services.tools.capabilities import active_capabilities

        caps = active_capabilities()
        if caps.get("images") is False and not model:
            raise ImageGenError(
                f"Provider '{caps.get('provider_id')}' does not support image generation. "
                "Switch to OpenAI (dall-e-3) or set an image-capable model in Settings."
            )
    except ImageGenError:
        raise
    except Exception:  # noqa: BLE001
        pass

    url = base + "/images/generations"
    body: dict[str, Any] = {
        "model": img_model,
        "prompt": prompt,
        "n": max(1, min(4, int(n))),
        "size": size or "1024x1024",
    }
    # Some APIs want response_format
    if "openai.com" in base or "openrouter" in base:
        body["response_format"] = "b64_json"

    data = json.dumps(body).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
    }
    if "openrouter.ai" in base:
        headers["HTTP-Referer"] = "https://ai-agent-studio.local"
        headers["X-Title"] = "AI Agent Studio"

    req = urllib.request.Request(url, data=data, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:800]
        hint = ""
        if e.code in (400, 404, 422) and "openrouter" in base:
            hint = (
                " | OpenRouter tip: set Settings → Image model to a model that supports "
                "image generation, or use OpenAI base URL with dall-e-3."
            )
        if e.code == 401:
            hint = " | Check API key in Settings."
        raise ImageGenError(f"Image gen HTTP {e.code}: {detail}{hint}") from e
    except urllib.error.URLError as e:
        raise ImageGenError(f"Network error: {e.reason}") from e
    except TimeoutError as e:
        raise ImageGenError("Image generation timed out") from e

    paths: list[str] = []
    items = payload.get("data") or []
    for item in items:
        b64 = item.get("b64_json")
        u = item.get("url")
        dest = generated_dir(chat_id) / f"{uuid.uuid4().hex[:12]}_gen.png"
        try:
            if b64:
                dest.write_bytes(base64.b64decode(b64))
                paths.append(str(dest.resolve()))
            elif u:
                # download
                from app.core.services.chat.media_chat import download_url

                local = download_url(u, chat_id)
                if local:
                    paths.append(local)
                else:
                    # save url ref
                    dest.write_text(u, encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            raise ImageGenError(f"Failed to save image: {e}") from e

    if not paths:
        raise ImageGenError(f"No image data in response: {str(payload)[:300]}")

    # also stage into chat_media for display
    staged = []
    for p in paths:
        try:
            import shutil

            d = chat_media_dir(chat_id) / Path(p).name
            shutil.copy2(p, d)
            staged.append(str(d.resolve()))
        except Exception:  # noqa: BLE001
            staged.append(p)

    return {
        "ok": True,
        "paths": staged or paths,
        "model": img_model,
        "prompt": prompt,
        "raw_count": len(items),
    }


def image_gen_instructions() -> str:
    return """
## Generate images (IMAGE_GEN) — REQUIRED for picture requests

When the user asks to generate, draw, paint, create, or invent an **image/picture/photo/illustration**:
you MUST emit this block in **Action** mode (do not only describe the image; do not write SVG instead):

<<<IMAGE_GEN>>>
a watercolor painting of a mountain lake at sunrise
<<<END_IMAGE_GEN>>>

Optional size on the first line, then the prompt:
<<<IMAGE_GEN>>>
1024x1024
cute orange tabby cat, soft studio lighting, high detail
<<<END_IMAGE_GEN>>>

Rules:
1. IMAGE_GEN calls the real images API (OpenAI-compatible `/images/generations`). Settings → **Image model** (default `dall-e-3`).
2. After the tool runs, the PNG is shown in chat — you may briefly caption it.
3. **Forbidden substitutes** when the user wants a picture: writing `cat.svg`, HTML/CSS art, ASCII art, or claiming "file saved" without IMAGE_GEN.
4. Exception: only use SVG/code if the user **explicitly** asked for SVG, vector code, or source graphics.
5. If the tool returns an error (no key, model not supported on OpenRouter, etc.), report that error honestly and suggest: OpenAI key + `dall-e-3`, or a provider that supports image generation.
6. To **display** an existing file use `<<<IMAGE>>>path<<<END_IMAGE>>>` — that is not generation.
""".strip()


def extract_image_gen_blocks(text: str) -> list[str]:
    import re

    return [
        m.group(1).strip()
        for m in re.finditer(
            r"<<<IMAGE_GEN>>>\s*(.*?)\s*<<<END_IMAGE_GEN>>>",
            text or "",
            re.DOTALL | re.IGNORECASE,
        )
    ]
