"""
Honest provider capability matrix — what each backend can actually do.
Used by Settings, image gen, and chat chrome (disable/warn when unsupported).
"""

from __future__ import annotations

from typing import Any

from app.services import providers as prov
from app.core.services.data.storage import load_config

# Default capabilities by provider id (honest, not marketing)
_CAP_DEFAULTS: dict[str, dict[str, Any]] = {
    "openai": {
        "chat": True,
        "stream": True,
        "images": True,
        "vision": True,
        "image_models": ["dall-e-3", "dall-e-2", "gpt-image-1"],
        "notes": "Full OpenAI images + vision support",
    },
    "openrouter": {
        "chat": True,
        "stream": True,
        "images": "limited",  # only some models / endpoints
        "vision": "limited",
        "image_models": [
            "openai/dall-e-3",
            "black-forest-labs/flux-1.1-pro",
            "stabilityai/stable-diffusion-xl",
        ],
        "notes": "Chat yes; image gen only for image-capable models — test before relying",
    },
    "groq": {
        "chat": True,
        "stream": True,
        "images": False,
        "vision": "limited",
        "image_models": [],
        "notes": "Fast chat; no native /images/generations",
    },
    "together": {
        "chat": True,
        "stream": True,
        "images": "limited",
        "vision": "limited",
        "image_models": [],
        "notes": "Open models; image gen varies",
    },
    "ollama": {
        "chat": True,
        "stream": True,
        "images": False,
        "vision": "limited",
        "image_models": [],
        "notes": "Offline · Ollama (local) — local chat only; vision if multimodal model pulled; no DALL·E",
    },
    "custom": {
        "chat": True,
        "stream": True,
        "images": "unknown",
        "vision": "unknown",
        "image_models": [],
        "notes": "Depends on your server — use Test image gen",
    },
}

# Image model presets for Settings / Gen dialog
IMAGE_PRESETS: list[dict[str, str]] = [
    {"id": "openai-dalle3", "label": "OpenAI DALL·E 3", "model": "dall-e-3", "provider_hint": "openai"},
    {"id": "openai-dalle2", "label": "OpenAI DALL·E 2", "model": "dall-e-2", "provider_hint": "openai"},
    {"id": "or-dalle3", "label": "OpenRouter · DALL·E 3", "model": "openai/dall-e-3", "provider_hint": "openrouter"},
    {"id": "or-flux", "label": "OpenRouter · Flux 1.1 Pro", "model": "black-forest-labs/flux-1.1-pro", "provider_hint": "openrouter"},
    {"id": "custom", "label": "Custom (Settings image_model)", "model": "", "provider_hint": ""},
]


def capabilities_for_provider(provider_id: str) -> dict[str, Any]:
    pid = (provider_id or "custom").lower().strip()
    base = dict(_CAP_DEFAULTS.get(pid) or _CAP_DEFAULTS["custom"])
    base["provider_id"] = pid
    return base


def active_capabilities() -> dict[str, Any]:
    try:
        active = prov.resolve_active_llm()
        pid = str(active.get("provider_id") or "custom")
    except Exception:  # noqa: BLE001
        pid = "custom"
        active = {}
    caps = capabilities_for_provider(pid)
    caps["provider_name"] = active.get("provider_name") or pid
    caps["model"] = active.get("model") or load_config().get("model") or ""
    caps["base_url"] = active.get("base_url") or load_config().get("api_base_url") or ""
    return caps


def images_supported(caps: dict[str, Any] | None = None) -> bool:
    c = caps or active_capabilities()
    v = c.get("images")
    return v is True or v == "limited" or v == "unknown"


def format_capability_matrix() -> str:
    """Human-readable matrix for Settings / Tools list."""
    lines = [
        "Provider capability matrix (honest)",
        f"{'Provider':<14} {'Chat':<6} {'Stream':<8} {'Images':<10} {'Vision':<10} Notes",
        "-" * 72,
    ]
    for pid, caps in _CAP_DEFAULTS.items():
        lines.append(
            f"{pid:<14} {str(caps['chat']):<6} {str(caps['stream']):<8} "
            f"{str(caps['images']):<10} {str(caps['vision']):<10} {caps.get('notes','')[:40]}"
        )
    return "\n".join(lines)


def format_active_status_line() -> str:
    c = active_capabilities()
    img = c.get("images")
    img_s = "img✓" if img is True else ("img~" if img in ("limited", "unknown") else "img✗")
    return f"{c.get('provider_name') or c.get('provider_id')} · {img_s}"


def resolve_image_model(preset_id: str = "", explicit: str = "") -> str:
    if (explicit or "").strip():
        return explicit.strip()
    cfg = load_config()
    if (preset_id or "").strip() and preset_id != "custom":
        for p in IMAGE_PRESETS:
            if p["id"] == preset_id and p.get("model"):
                return p["model"]
    return (cfg.get("image_model") or "dall-e-3").strip()
