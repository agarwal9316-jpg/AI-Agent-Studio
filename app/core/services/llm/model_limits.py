"""
Discover model context / completion limits from provider /models metadata
plus safe heuristics so the UI can show “max supported” for context & response.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from app.core.services.data.storage import load_config, save_config

# Heuristic fallbacks when API does not expose context_length
_NAME_HINTS: list[tuple[re.Pattern[str], int, int]] = [
    (re.compile(r"gemini.*1\.5|gemini.*2|gemini-pro", re.I), 1_000_000, 8192),
    (re.compile(r"claude-3-7|claude-4|claude-opus-4|claude-sonnet-4", re.I), 200_000, 16384),
    (re.compile(r"claude-3\.5|claude-3-5|claude-sonnet|claude-opus|claude-haiku", re.I), 200_000, 8192),
    (re.compile(r"gpt-4\.1|gpt-4o|o3|o4|o1", re.I), 128_000, 16384),
    (re.compile(r"gpt-4-turbo|gpt-4-1106|gpt-4-0125", re.I), 128_000, 4096),
    (re.compile(r"gpt-3\.5|gpt-35", re.I), 16_385, 4096),
    (re.compile(r"qwen.*72b|qwen2\.5|qwen3", re.I), 131_072, 8192),
    (re.compile(r"llama.?3\.1|llama.?3\.3|llama-4", re.I), 128_000, 8192),
    (re.compile(r"llama.?3|llama3", re.I), 8192, 4096),
    (re.compile(r"mistral|mixtral|codestral", re.I), 32_768, 8192),
    (re.compile(r"deepseek", re.I), 64_000, 8192),
    (re.compile(r"grok", re.I), 131_072, 8192),
    (re.compile(r"35b|32b|34b", re.I), 32_768, 8192),
    (re.compile(r"7b|8b|9b", re.I), 16_384, 4096),
]


def _heuristic(model_id: str) -> dict[str, Any]:
    mid = model_id or ""
    for pat, ctx, max_out in _NAME_HINTS:
        if pat.search(mid):
            return {
                "context_length": ctx,
                "max_completion_tokens": max_out,
                "source": "heuristic",
            }
    return {
        "context_length": 32_768,
        "max_completion_tokens": 8192,
        "source": "default",
    }


def _extract_meta(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize OpenRouter / OpenAI-style model objects."""
    mid = str(item.get("id") or item.get("name") or "")
    ctx = (
        item.get("context_length")
        or item.get("context_window")
        or item.get("max_context_length")
        or (item.get("top_provider") or {}).get("context_length")
        or None
    )
    # nested architecture
    if not ctx and isinstance(item.get("architecture"), dict):
        ctx = item["architecture"].get("context_length")
    max_out = (
        item.get("max_completion_tokens")
        or item.get("max_output_tokens")
        or item.get("max_tokens")
        or (item.get("top_provider") or {}).get("max_completion_tokens")
        or None
    )
    # OpenRouter pricing block sometimes has max_completion_tokens
    try:
        ctx = int(ctx) if ctx is not None else None
    except Exception:  # noqa: BLE001
        ctx = None
    try:
        max_out = int(max_out) if max_out is not None else None
    except Exception:  # noqa: BLE001
        max_out = None
    return {
        "id": mid,
        "context_length": ctx,
        "max_completion_tokens": max_out,
        "raw_name": str(item.get("name") or mid),
    }


def fetch_models_metadata(provider_id: str | None = None, *, force: bool = False) -> list[dict[str, Any]]:
    """
    GET /models and return rich metadata; caches on provider as models_meta_cache.
    """
    from app.core.services.llm.providers import load_providers, save_providers, resolve_active_llm

    store = load_providers()
    if not provider_id:
        try:
            provider_id = str(resolve_active_llm().get("provider_id") or store.get("active_provider_id"))
        except Exception:  # noqa: BLE001
            provider_id = str(store.get("active_provider_id") or "custom")

    p = None
    for item in store.get("providers") or []:
        if item.get("id") == provider_id:
            p = item
            break
    if not p:
        return []

    if p.get("models_meta_cache") and not force:
        return list(p["models_meta_cache"])

    key = ""
    kid = store.get("active_key_id") or ""
    for k in p.get("keys") or []:
        if k.get("id") == kid or not key:
            key = k.get("key") or key
    if not key and p.get("keys"):
        key = (p["keys"][0] or {}).get("key") or ""
    cfg = load_config()
    if not key:
        key = (cfg.get("api_key") or "").strip()

    base = (p.get("base_url") or cfg.get("api_base_url") or "").rstrip("/")
    path = p.get("models_path") or "/models"
    url = base + path
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    if "openrouter" in base:
        headers["HTTP-Referer"] = "https://ai-agent-studio.local"
        headers["X-Title"] = "AI Agent Studio"

    meta_list: list[dict[str, Any]] = []
    try:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=45) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, list):
            for m in data:
                if isinstance(m, dict) and (m.get("id") or m.get("name")):
                    meta_list.append(_extract_meta(m))
                elif isinstance(m, str):
                    meta_list.append({"id": m, "context_length": None, "max_completion_tokens": None})
        # also refresh plain id cache
        ids = [m["id"] for m in meta_list if m.get("id")]
        if ids:
            p["models_cache"] = sorted(set(ids), key=str.lower)
    except Exception:  # noqa: BLE001
        # fall back to id-only cache
        for mid in p.get("models_cache") or []:
            meta_list.append({"id": str(mid), "context_length": None, "max_completion_tokens": None})

    p["models_meta_cache"] = meta_list
    from datetime import datetime, timezone

    p["models_meta_fetched_at"] = datetime.now(timezone.utc).isoformat()
    save_providers(store)
    return meta_list


def get_model_limits(model_id: str | None = None, *, refresh: bool = False) -> dict[str, Any]:
    """
    Returns {
      model, context_length, max_completion_tokens, source,
      recommended_context, recommended_max_tokens
    }
    """
    from app.core.services.llm.providers import resolve_active_llm

    try:
        active = resolve_active_llm()
    except Exception:  # noqa: BLE001
        active = {}
    mid = (model_id or active.get("model") or load_config().get("model") or "").strip()
    meta_hit: dict[str, Any] | None = None
    try:
        metas = fetch_models_metadata(str(active.get("provider_id") or ""), force=refresh)
        for m in metas:
            if str(m.get("id") or "").lower() == mid.lower():
                meta_hit = m
                break
            # partial match (provider/model)
            if mid and mid.lower() in str(m.get("id") or "").lower():
                meta_hit = m
                break
    except Exception:  # noqa: BLE001
        metas = []

    source = "unknown"
    ctx = None
    max_out = None
    if meta_hit:
        ctx = meta_hit.get("context_length")
        max_out = meta_hit.get("max_completion_tokens")
        if ctx:
            source = "provider"
    if not ctx:
        h = _heuristic(mid)
        ctx = h["context_length"]
        max_out = max_out or h["max_completion_tokens"]
        source = "heuristic" if source == "unknown" else source + "+heuristic"
    if not max_out:
        max_out = min(16384, max(2048, int(ctx) // 8))

    # Recommend using most of model capacity (leave headroom)
    rec_ctx = max(8000, min(int(ctx), int(ctx) - 1024 if int(ctx) > 16000 else int(ctx)))
    rec_out = max(1024, min(int(max_out), 16384))

    return {
        "model": mid,
        "provider_id": active.get("provider_id"),
        "context_length": int(ctx),
        "max_completion_tokens": int(max_out),
        "source": source,
        "recommended_context": int(rec_ctx),
        "recommended_max_tokens": int(rec_out),
        "label": (
            f"{mid or '?'}: context ≤ {int(ctx):,} · response ≤ {int(max_out):,} "
            f"({source})"
        ),
    }


def apply_limits_to_params(
    *,
    use_max_context: bool = False,
    use_max_response: bool = False,
) -> dict[str, Any]:
    """Optionally set model_params to model max (with safe headroom)."""
    from app.core.services.llm.model_params import get_model_params, save_model_params

    lim = get_model_limits()
    p = get_model_params()
    if use_max_context:
        # leave reserve room
        p["context_window"] = max(4000, int(lim["context_length"]) - int(p.get("context_reserve_reply") or 8000))
        if p["context_window"] > int(lim["context_length"]):
            p["context_window"] = int(lim["context_length"])
    if use_max_response:
        p["max_tokens"] = int(lim["max_completion_tokens"])
    save_model_params(p)
    cfg = load_config()
    cfg["context_window_locked"] = True  # user chose deliberately
    save_config(cfg)
    return {"params": get_model_params(), "limits": lim}
