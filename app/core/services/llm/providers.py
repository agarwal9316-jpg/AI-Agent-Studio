"""
LLM service providers + multi-key management (Open WebUI style).

Stores providers (OpenRouter, OpenAI, custom, …), base URLs, and multiple API keys.
Fetches model lists from OpenAI-compatible /models endpoints when possible.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any

from app.paths import data_dir
from app.core.services.data.storage import _read_json, _write_json, load_config, save_config

# NVIDIA Integrate catalog lists alphabetically (yi-large first). Keep Ultra 550
# unless the user explicitly picks another model (config.model_user_pinned).
NVIDIA_NEMOTRON_550 = "nvidia/nemotron-3-ultra-550b-a55b"


def is_nvidia_integrate(base_url: str = "", provider_id: str = "") -> bool:
    b = (base_url or "").lower()
    p = (provider_id or "").lower()
    return "nvidia.com" in b or "integrate.api.nvidia" in b or p == "nvidia"


def pinned_or_active_model(
    model: str = "",
    *,
    base_url: str = "",
    provider_id: str = "",
    user_pinned: bool | None = None,
) -> str:
    """Prefer Nemotron 550 on NVIDIA Integrate unless the user pinned another id."""
    m = (model or "").strip()
    if user_pinned is None:
        try:
            user_pinned = bool(load_config().get("model_user_pinned"))
        except Exception:  # noqa: BLE001
            user_pinned = False
    if is_nvidia_integrate(base_url, provider_id) and not user_pinned:
        return NVIDIA_NEMOTRON_550
    return m

# Built-in provider templates
PROVIDER_PRESETS: list[dict[str, Any]] = [
    {
        "id": "openrouter",
        "name": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "models_path": "/models",
        "notes": "https://openrouter.ai/models — multi-provider router (includes x-ai/grok-*)",
    },
    {
        "id": "xai",
        "name": "xAI Grok",
        "base_url": "https://api.x.ai/v1",
        "models_path": "/models",
        "notes": "Direct Grok API — https://console.x.ai (OpenAI-compatible)",
    },
    {
        "id": "openai",
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "models_path": "/models",
        "notes": "Official OpenAI API",
    },
    {
        "id": "groq",
        "name": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "models_path": "/models",
        "notes": "Fast inference",
    },
    {
        "id": "together",
        "name": "Together AI",
        "base_url": "https://api.together.xyz/v1",
        "models_path": "/models",
        "notes": "Open models",
    },
    {
        "id": "ollama",
        "name": "Ollama (local)",
        "base_url": "http://127.0.0.1:11434/v1",
        "models_path": "/models",
        "notes": "Local OpenAI-compatible; key can be ollama",
    },
    {
        "id": "custom",
        "name": "Custom OpenAI-compatible",
        "base_url": "http://127.0.0.1:8000/v1",
        "models_path": "/models",
        "notes": "Any /v1/chat/completions server",
    },
]

# Preferred Grok model ids (OpenRouter first — most users already have that key).
# Prefer ids known to complete on OpenRouter; some catalog ids (e.g. grok-4.5) 400.
GROK_MODEL_PREFS_OPENROUTER: list[str] = [
    "x-ai/grok-4.3",
    "x-ai/grok-4.20",
    "x-ai/grok-4",
    "x-ai/grok-3",
    "x-ai/grok-3-mini",
    "x-ai/grok-2",
    "x-ai/grok-4.5",  # may appear in /models but still 400 for some accounts
]
# Direct xAI API model ids (NOT "x-ai/…" — that is OpenRouter-only)
GROK_MODEL_PREFS_XAI: list[str] = [
    "grok-3",
    "grok-3-latest",
    "grok-3-mini",
    "grok-3-mini-fast",
    "grok-2",
    "grok-2-latest",
    "grok-2-1212",
    "grok-4",
    "grok-4-latest",
]
# Catalog ids that often 400 on chat even when listed in /models
GROK_MODEL_BLOCKLIST: set[str] = {
    "x-ai/grok-4.5",
    "x-ai/grok-4.20-multi-agent",
    "x-ai/grok-build-0.1",
    "~x-ai/grok-latest",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def providers_path():
    return data_dir() / "providers.json"


def _default_store() -> dict[str, Any]:
    providers = []
    for p in PROVIDER_PRESETS:
        providers.append(
            {
                "id": p["id"],
                "name": p["name"],
                "base_url": p["base_url"],
                "models_path": p.get("models_path") or "/models",
                "notes": p.get("notes") or "",
                "keys": [],  # [{id, label, key, created_at}]
                "models_cache": [],
                "models_fetched_at": "",
                "enabled": True,
            }
        )
    return {
        "active_provider_id": "openrouter",
        "active_key_id": "",
        "active_model": "",
        "providers": providers,
        "updated_at": _now(),
    }


def ensure_builtin_providers(store: dict[str, Any] | None = None) -> dict[str, Any]:
    """Add missing preset providers (e.g. xAI Grok) without wiping user keys."""
    store = store if store is not None else load_providers()
    existing = {str(p.get("id") or "") for p in (store.get("providers") or [])}
    changed = False
    for preset in PROVIDER_PRESETS:
        pid = str(preset.get("id") or "")
        if not pid or pid in existing:
            continue
        store.setdefault("providers", []).append(
            {
                "id": pid,
                "name": preset.get("name") or pid,
                "base_url": preset.get("base_url") or "",
                "models_path": preset.get("models_path") or "/models",
                "notes": preset.get("notes") or "",
                "keys": [],
                "models_cache": [],
                "models_fetched_at": "",
                "enabled": True,
            }
        )
        existing.add(pid)
        changed = True
    if changed:
        save_providers(store)
    return store


def load_providers() -> dict[str, Any]:
    data = _read_json(providers_path(), None)
    if isinstance(data, dict) and data.get("providers"):
        data.setdefault("active_provider_id", "openrouter")
        data.setdefault("active_key_id", "")
        data.setdefault("active_model", "")
        # Migrate: ensure xAI Grok preset exists on older installs
        try:
            ids = {str(p.get("id") or "") for p in (data.get("providers") or [])}
            if "xai" not in ids:
                data["providers"].append(
                    {
                        "id": "xai",
                        "name": "xAI Grok",
                        "base_url": "https://api.x.ai/v1",
                        "models_path": "/models",
                        "notes": "Direct Grok API — https://console.x.ai",
                        "keys": [],
                        "models_cache": [],
                        "models_fetched_at": "",
                        "enabled": True,
                    }
                )
                save_providers(data)
        except Exception:  # noqa: BLE001
            pass
        return data
    store = _default_store()
    # seed from legacy config if present
    cfg = load_config()
    if cfg.get("api_key") or cfg.get("api_base_url"):
        for p in store["providers"]:
            if "openai.com" in (cfg.get("api_base_url") or "") or p["id"] == "openai":
                if cfg.get("api_key") and p["id"] == "openai":
                    p["keys"].append(
                        {
                            "id": str(uuid.uuid4())[:8],
                            "label": "default",
                            "key": cfg.get("api_key") or "",
                            "created_at": _now(),
                        }
                    )
                    store["active_provider_id"] = "openai"
                    store["active_key_id"] = p["keys"][0]["id"]
                    store["active_model"] = cfg.get("model") or ""
                    p["base_url"] = cfg.get("api_base_url") or p["base_url"]
                    break
            if "openrouter" in (cfg.get("api_base_url") or ""):
                if p["id"] == "openrouter" and cfg.get("api_key"):
                    p["keys"].append(
                        {
                            "id": str(uuid.uuid4())[:8],
                            "label": "default",
                            "key": cfg.get("api_key") or "",
                            "created_at": _now(),
                        }
                    )
                    store["active_provider_id"] = "openrouter"
                    store["active_key_id"] = p["keys"][0]["id"]
                    store["active_model"] = cfg.get("model") or ""
                    break
    save_providers(store)
    return store


def save_providers(store: dict[str, Any]) -> None:
    store["updated_at"] = _now()
    _write_json(providers_path(), store)
    # keep legacy config in sync for older code paths
    try:
        active = resolve_active_llm()
        cfg = load_config()
        if active.get("api_key"):
            cfg["api_key"] = active["api_key"]
        if active.get("base_url"):
            cfg["api_base_url"] = active["base_url"]
        if active.get("model"):
            cfg["model"] = active["model"]
        cfg["provider_id"] = active.get("provider_id") or ""
        save_config(cfg)
    except Exception:  # noqa: BLE001
        pass


def list_providers() -> list[dict[str, Any]]:
    return list(load_providers().get("providers") or [])


def get_provider(provider_id: str) -> dict[str, Any] | None:
    for p in list_providers():
        if p.get("id") == provider_id:
            return p
    return None


def upsert_provider(
    *,
    provider_id: str = "",
    name: str = "",
    base_url: str = "",
    notes: str = "",
) -> dict[str, Any]:
    store = load_providers()
    if provider_id:
        for p in store["providers"]:
            if p["id"] == provider_id:
                if name:
                    p["name"] = name
                if base_url:
                    p["base_url"] = base_url.rstrip("/")
                if notes is not None:
                    p["notes"] = notes
                save_providers(store)
                return p
    pid = provider_id or str(uuid.uuid4())[:8]
    p = {
        "id": pid,
        "name": name or "Custom",
        "base_url": (base_url or "http://127.0.0.1:8000/v1").rstrip("/"),
        "models_path": "/models",
        "notes": notes or "",
        "keys": [],
        "models_cache": [],
        "models_fetched_at": "",
        "enabled": True,
    }
    store["providers"].append(p)
    save_providers(store)
    return p


def add_key(provider_id: str, key: str, label: str = "default") -> dict[str, Any]:
    store = load_providers()
    for p in store["providers"]:
        if p["id"] != provider_id:
            continue
        entry = {
            "id": str(uuid.uuid4())[:8],
            "label": label.strip() or "key",
            "key": key.strip(),
            "created_at": _now(),
        }
        p.setdefault("keys", []).append(entry)
        if not store.get("active_key_id"):
            store["active_provider_id"] = provider_id
            store["active_key_id"] = entry["id"]
        save_providers(store)
        return entry
    raise ValueError(f"Provider not found: {provider_id}")


def delete_key(provider_id: str, key_id: str) -> None:
    store = load_providers()
    for p in store["providers"]:
        if p["id"] != provider_id:
            continue
        p["keys"] = [k for k in (p.get("keys") or []) if k.get("id") != key_id]
        if store.get("active_key_id") == key_id:
            store["active_key_id"] = (p["keys"][0]["id"] if p["keys"] else "")
        save_providers(store)
        return


def _first_key_id(provider_id: str) -> str:
    """Pick best API key for a provider (skip obvious test placeholders)."""
    p = get_provider(provider_id) or {}
    keys = [k for k in (p.get("keys") or []) if (k.get("key") or "").strip() and k.get("id")]
    if not keys:
        return ""

    def score(k: dict[str, Any]) -> tuple:
        raw = str(k.get("key") or "").strip()
        lab = str(k.get("label") or "").lower()
        s = 0
        if raw.startswith("sk-or-"):
            s += 50
        if raw.startswith("xai-") or (provider_id == "xai" and len(raw) > 20):
            s += 40
        if "test" in lab or raw.startswith("sk-test") or "not-real" in raw:
            s -= 100
        if lab in ("default", "grok", "main", "primary"):
            s += 10
        s += min(len(raw), 80)  # prefer real-looking long keys
        return (s,)

    keys.sort(key=score, reverse=True)
    return str(keys[0].get("id") or "")


def _normalize_model_for_provider(provider_id: str, model: str) -> str:
    """
    OpenRouter uses ids like x-ai/grok-4.3; direct xAI uses grok-3 / grok-4.
    Mixing them causes HTTP 400 Model not found.
    """
    m = (model or "").strip()
    pid = (provider_id or "").lower()
    if not m:
        return m
    if pid == "xai":
        # Strip OpenRouter-style vendor prefix
        if m.lower().startswith("x-ai/"):
            m = m.split("/", 1)[-1]
        if m.startswith("~"):
            m = m.lstrip("~")
        return m
    if pid == "openrouter":
        # If bare grok-* without vendor, prefix for OpenRouter
        low = m.lower()
        if low.startswith("grok") and "/" not in m:
            return f"x-ai/{m}"
        if low.startswith("~x-ai/"):
            return m  # leave alias; probe will reject if bad
        return m
    return m


def set_active(provider_id: str, key_id: str = "", model: str = "") -> None:
    store = load_providers()
    prev_pid = str(store.get("active_provider_id") or "")
    store["active_provider_id"] = provider_id
    # Always bind key to the *target* provider (never keep OpenRouter key on xAI)
    if key_id:
        # Only accept key_id if it belongs to this provider
        p = get_provider(provider_id) or {}
        ids = {str(k.get("id") or "") for k in (p.get("keys") or [])}
        if key_id in ids:
            store["active_key_id"] = key_id
        else:
            store["active_key_id"] = _first_key_id(provider_id)
    else:
        # Switching providers → always re-pick a key for that provider
        if prev_pid != provider_id or not store.get("active_key_id"):
            store["active_key_id"] = _first_key_id(provider_id)
        else:
            # Ensure current key_id still belongs to active provider
            p = get_provider(provider_id) or {}
            ids = {str(k.get("id") or "") for k in (p.get("keys") or [])}
            if str(store.get("active_key_id") or "") not in ids:
                store["active_key_id"] = _first_key_id(provider_id)
    if model:
        store["active_model"] = _normalize_model_for_provider(provider_id, model)
    save_providers(store)


def repair_provider_model_mismatch() -> bool:
    """
    Fix broken combos that cause HTTP 400 Model not found:
    - OpenRouter model id (x-ai/…) on xAI host
    - OpenRouter key (sk-or-…) on xAI host
    - Bare grok-* on OpenRouter without prefix
    Returns True if store was changed.
    """
    store = load_providers()
    cfg = load_config()
    pid = str(store.get("active_provider_id") or "")
    model = str(store.get("active_model") or "")
    changed = False

    # Detect OpenRouter-style key sitting as active while provider is xAI
    p = get_provider(pid) or {}
    kid = str(store.get("active_key_id") or "")
    key_val = ""
    for k in p.get("keys") or []:
        if str(k.get("id") or "") == kid:
            key_val = str(k.get("key") or "")
            break
    if not key_val:
        key_val = str(cfg.get("api_key") or "")

    or_model = model.lower().startswith("x-ai/") or model.lower().startswith("~x-ai/")
    or_key = key_val.strip().startswith("sk-or-")
    xai_host = pid == "xai" or "api.x.ai" in str(p.get("base_url") or "").lower()

    if xai_host and (or_model or or_key or not _provider_has_key("xai")):
        # Prefer OpenRouter if we have a key there
        if _provider_has_key("openrouter") or or_key:
            store["active_provider_id"] = "openrouter"
            store["active_key_id"] = _first_key_id("openrouter")
            if or_key and not store["active_key_id"]:
                # ensure OR key exists on openrouter provider
                try:
                    entry = add_key("openrouter", key_val, label="repaired")
                    store = load_providers()
                    store["active_provider_id"] = "openrouter"
                    store["active_key_id"] = entry.get("id") or ""
                except Exception:  # noqa: BLE001
                    pass
            if model and not model.lower().startswith("x-ai/"):
                if model.lower().startswith("grok"):
                    model = f"x-ai/{model}"
            if model.lower() in {b.lower() for b in GROK_MODEL_BLOCKLIST} or "4.5" in model:
                model = "x-ai/grok-4.3"
            store["active_model"] = model or "x-ai/grok-4.3"
            changed = True
        elif _provider_has_key("xai"):
            store["active_provider_id"] = "xai"
            store["active_key_id"] = _first_key_id("xai")
            store["active_model"] = _normalize_model_for_provider("xai", model or "grok-3")
            changed = True

    if pid == "openrouter" and model.lower().startswith("grok") and "/" not in model:
        store["active_model"] = f"x-ai/{model}"
        changed = True

    if changed:
        save_providers(store)
    return changed


def resolve_active_llm() -> dict[str, str]:
    """Active provider + key + model for chat (Open WebUI style selection)."""
    try:
        repair_provider_model_mismatch()
    except Exception:  # noqa: BLE001
        pass
    store = load_providers()
    cfg = load_config()
    pid = store.get("active_provider_id") or "openai"
    p = get_provider(pid) or {}
    key = ""
    kid = store.get("active_key_id") or ""
    # Only use keys that belong to this provider
    key_ids = {str(k.get("id") or ""): k for k in (p.get("keys") or [])}
    if kid and kid in key_ids:
        key = key_ids[kid].get("key") or ""
    if not key and (p.get("keys") or []):
        key = p["keys"][0].get("key") or ""
        kid = p["keys"][0].get("id") or ""
    # Legacy config key — only when it matches this provider type
    if not (key or "").strip():
        legacy = (cfg.get("api_key") or "").strip()
        if legacy and pid == "openrouter" and (
            legacy.startswith("sk-or-") or "openrouter" in (cfg.get("api_base_url") or "")
        ):
            key = legacy
        elif legacy and pid == "xai" and not legacy.startswith("sk-or-"):
            key = legacy
        elif legacy and pid not in ("openrouter", "xai"):
            key = legacy
    model = store.get("active_model") or ""
    model = _normalize_model_for_provider(pid, model)
    # Auto-heal mismatched store (e.g. x-ai/* stuck on xAI provider)
    if model and model != (store.get("active_model") or ""):
        try:
            store["active_model"] = model
            save_providers(store)
        except Exception:  # noqa: BLE001
            pass
    if not model and p.get("models_cache"):
        model = p["models_cache"][0]
        model = _normalize_model_for_provider(pid, model)
    if not model:
        model = cfg.get("model") or "gpt-4o-mini"
        model = _normalize_model_for_provider(pid, str(model))
    # Prefer provider's own base_url — never mix hosts
    base = (p.get("base_url") or "").rstrip("/")
    if not base:
        base = (cfg.get("api_base_url") or "https://api.openai.com/v1").rstrip("/")
    # NVIDIA catalog first-item (yi-large / llama vision) must not become the agent
    pinned = pinned_or_active_model(
        model,
        base_url=base,
        provider_id=str(pid),
        user_pinned=bool(cfg.get("model_user_pinned")),
    )
    if pinned and pinned != (model or ""):
        model = pinned
        try:
            store["active_model"] = model
            save_providers(store)
        except Exception:  # noqa: BLE001
            pass
        try:
            if (cfg.get("model") or "") != model:
                cfg["model"] = model
                save_config(cfg)
        except Exception:  # noqa: BLE001
            pass
    return {
        "provider_id": pid,
        "provider_name": p.get("name") or pid,
        "base_url": base,
        "api_key": key,
        "model": model,
        "key_id": kid,
    }


def has_active_api_key() -> bool:
    """True if chat can authenticate — provider store and/or legacy config.api_key."""
    try:
        active = resolve_active_llm()
        if (active.get("api_key") or "").strip():
            return True
    except Exception:  # noqa: BLE001
        pass
    try:
        return bool((load_config().get("api_key") or "").strip())
    except Exception:  # noqa: BLE001
        return False


def fetch_models(provider_id: str, *, force: bool = False) -> list[str]:
    """GET {base}/models and cache ids. Works for OpenAI + OpenRouter style."""
    store = load_providers()
    p = None
    for item in store["providers"]:
        if item["id"] == provider_id:
            p = item
            break
    if not p:
        raise ValueError(f"Unknown provider: {provider_id}")

    if p.get("models_cache") and not force:
        return list(p["models_cache"])

    key = ""
    kid = store.get("active_key_id") or ""
    for k in p.get("keys") or []:
        if k.get("id") == kid or not key:
            key = k.get("key") or key
    if not key and p.get("keys"):
        key = p["keys"][0].get("key") or ""

    base = (p.get("base_url") or "").rstrip("/")
    path = p.get("models_path") or "/models"
    url = base + path
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    # OpenRouter recommends these
    if "openrouter" in base:
        headers["HTTP-Referer"] = "https://ai-agent-studio.local"
        headers["X-Title"] = "AI Agent Studio"

    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"Models fetch HTTP {e.code}: {detail}") from e
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"Models fetch failed: {e}") from e

    models: list[str] = []
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, list):
        for m in data:
            if isinstance(m, dict) and m.get("id"):
                models.append(str(m["id"]))
            elif isinstance(m, str):
                models.append(m)
    elif isinstance(payload, dict) and isinstance(payload.get("models"), list):
        for m in payload["models"]:
            if isinstance(m, dict) and m.get("id"):
                models.append(str(m["id"]))
            elif isinstance(m, str):
                models.append(m)

    models = sorted(set(models), key=str.lower)
    p["models_cache"] = models
    p["models_fetched_at"] = _now()
    save_providers(store)
    return models


def provider_prompt_block() -> str:
    active = resolve_active_llm()
    lines = [
        "## Active LLM provider (chat selection)",
        f"- Provider: {active.get('provider_name')} (`{active.get('provider_id')}`)",
        f"- Base URL: {active.get('base_url')}",
        f"- Model: {active.get('model')}",
        "- Keys are managed in Settings → Providers (multiple keys per provider).",
        "- Org agents may override model/base/key individually.",
    ]
    return "\n".join(lines)


def _pick_grok_model(models: list[str], prefs: list[str]) -> str:
    """Choose best Grok id from a list (exact pref first, then any *grok* hit)."""
    blocked = {b.lower() for b in GROK_MODEL_BLOCKLIST}
    usable = [m for m in models if m and m.lower() not in blocked]
    lower_map = {m.lower(): m for m in usable}
    for pref in prefs:
        if pref.lower() in blocked:
            continue
        if pref.lower() in lower_map:
            return lower_map[pref.lower()]
    # fuzzy: prefer higher version-ish names (skip multi-agent / build / aliases)
    groks = [
        m
        for m in usable
        if "grok" in m.lower()
        and "build" not in m.lower()
        and "multi-agent" not in m.lower()
        and not m.startswith("~")
    ]
    if not groks:
        groks = [m for m in usable if "grok" in m.lower()]
    if not groks:
        return ""

    def score(m: str) -> tuple:
        s = m.lower()
        if "4.3" in s:
            return (9, s)
        if "4.20" in s or "4-20" in s:
            return (8, s)
        if "4.5" in s:
            return (1, s)  # catalog ghost — deprioritize
        if "grok-4" in s or "/grok-4" in s:
            return (6, s)
        if "grok-3" in s and "mini" not in s:
            return (5, s)
        if "mini" in s:
            return (2, s)
        return (3, s)

    groks.sort(key=score, reverse=True)
    return groks[0]


def _probe_chat_model(*, api_key: str, base_url: str, model: str, timeout: float = 45.0) -> bool:
    """Return True if a minimal chat completion succeeds (filters catalog ghosts)."""
    if not (api_key or "").strip() or not (model or "").strip():
        return False
    try:
        from app.core.services.llm.llm import LLMError, chat_completion

        chat_completion(
            api_key=api_key,
            messages=[{"role": "user", "content": "Reply with exactly: OK"}],
            model=model,
            base_url=base_url,
            timeout=timeout,
            max_tokens=16,
            temperature=0,
            tools=None,
            normalize_tools=False,
            _transient_retry=False,
        )
        return True
    except Exception:  # noqa: BLE001
        return False


def _provider_has_key(provider_id: str) -> bool:
    p = get_provider(provider_id) or {}
    for k in p.get("keys") or []:
        if (k.get("key") or "").strip():
            return True
    return False


def activate_grok_as_agent(
    *,
    prefer: str = "xai",
    fetch: bool = True,
) -> dict[str, Any]:
    """
    Switch Studio to use Grok as the chat/agent brain (desktop, no CLI).

    prefer:
      - "xai" (default) — direct https://api.x.ai/v1  ← recommended, no OpenRouter
      - "openrouter" — OpenRouter x-ai/grok-* (needs OpenRouter credits)
      - "auto" — xAI if key present, else OpenRouter if key present, else ask for xAI key

    Returns {ok, provider_id, model, message, need_key, provider_name}.
    """
    ensure_builtin_providers()
    prefer = (prefer or "xai").lower().strip()

    or_has = _provider_has_key("openrouter")
    xai_has = _provider_has_key("xai")
    # Legacy single key on OpenRouter base also counts for openrouter path only
    try:
        cfg = load_config()
        if not or_has and "openrouter" in (cfg.get("api_base_url") or "") and (cfg.get("api_key") or "").strip():
            or_has = True
            try:
                add_key("openrouter", str(cfg.get("api_key") or ""), label="legacy")
            except Exception:  # noqa: BLE001
                pass
        # xAI key sometimes only in env
        import os

        env_xai = (os.environ.get("XAI_API_KEY") or os.environ.get("GROK_API_KEY") or "").strip()
        if env_xai and not xai_has:
            try:
                add_key("xai", env_xai, label="env")
                xai_has = True
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass

    if prefer == "auto":
        # Prefer direct xAI so users are not forced through OpenRouter credits
        path = "xai" if xai_has else ("openrouter" if or_has else "xai")
    elif prefer in ("openrouter", "xai"):
        path = prefer
    else:
        path = "xai"

    # Default path is xAI — do NOT silently fall back to OpenRouter (402 when broke)
    if path == "xai" and not xai_has:
        return {
            "ok": False,
            "need_key": True,
            "provider_id": "xai",
            "provider_name": "xAI Grok",
            "model": "",
            "message": (
                "To use Grok directly in Studio (no CLI, no OpenRouter):\n\n"
                "1. Open https://console.x.ai\n"
                "2. Create an API key\n"
                "3. Paste it when prompted (or Settings → xAI Grok)\n"
                "4. Tap Use Grok again\n\n"
                "Note: a grok.com website login is NOT the same as an API key.\n"
                "OpenRouter is optional and needs separate paid credits."
            ),
        }

    if path == "openrouter" and not or_has:
        if xai_has:
            path = "xai"
        else:
            return {
                "ok": False,
                "need_key": True,
                "provider_id": "xai",
                "provider_name": "xAI Grok",
                "model": "",
                "message": (
                    "No OpenRouter key — and OpenRouter needs credits anyway.\n"
                    "Use direct xAI instead: get a key at https://console.x.ai"
                ),
            }

    pid = path
    prefs = GROK_MODEL_PREFS_OPENROUTER if pid == "openrouter" else GROK_MODEL_PREFS_XAI
    p = get_provider(pid) or {}
    models = list(p.get("models_cache") or [])
    if fetch:
        try:
            models = fetch_models(pid, force=True) or models
        except Exception:  # noqa: BLE001
            pass

    # Candidate list: prefs first, then other grok ids from catalog
    candidates: list[str] = []
    for pref in prefs:
        if pref in models and pref not in candidates:
            candidates.append(pref)
    picked = _pick_grok_model(models, prefs)
    if picked and picked not in candidates:
        candidates.insert(0, picked)
    for m in models:
        if "grok" in m.lower() and m not in candidates and m.lower() not in {
            b.lower() for b in GROK_MODEL_BLOCKLIST
        }:
            candidates.append(m)
    if not candidates:
        candidates = [prefs[0]] if prefs else ["x-ai/grok-4.3"]

    # Normalize candidates for this host (never probe x-ai/* against api.x.ai)
    candidates = [_normalize_model_for_provider(pid, c) for c in candidates]
    candidates = [c for c in candidates if c]
    # Deduplicate preserving order
    seen: set[str] = set()
    candidates = [c for c in candidates if not (c in seen or seen.add(c))]  # type: ignore[func-returns-value]

    # Resolve key/base for probe — bind key to this provider only
    kid = _first_key_id(pid)
    set_active(pid, key_id=kid, model=candidates[0] if candidates else "")
    active0 = resolve_active_llm()
    api_key = (active0.get("api_key") or "").strip()
    base_url = (active0.get("base_url") or "").rstrip("/")
    # Hard guard: OpenRouter key must hit OpenRouter host
    if api_key.startswith("sk-or-") and "openrouter" not in base_url.lower():
        pid = "openrouter"
        prefs = GROK_MODEL_PREFS_OPENROUTER
        candidates = list(prefs)
        kid = _first_key_id("openrouter")
        set_active("openrouter", key_id=kid, model=candidates[0])
        active0 = resolve_active_llm()
        api_key = (active0.get("api_key") or "").strip()
        base_url = (active0.get("base_url") or "").rstrip("/")
    if not api_key:
        return {
            "ok": False,
            "need_key": True,
            "provider_id": pid,
            "provider_name": active0.get("provider_name") or pid,
            "model": "",
            "message": "API key missing for Grok. Open Settings and paste a key.",
        }

    model = ""
    tried: list[str] = []
    for cand in candidates[:8]:
        tried.append(cand)
        if _probe_chat_model(api_key=api_key, base_url=base_url, model=cand):
            model = cand
            break
    if not model:
        return {
            "ok": False,
            "need_key": False,
            "provider_id": pid,
            "provider_name": active0.get("provider_name") or pid,
            "model": "",
            "message": (
                "Could not start any Grok model on this provider.\n\n"
                f"Tried: {', '.join(tried)}\n\n"
                "Check OpenRouter credits / model access, or add an xAI key at console.x.ai "
                "and choose “xAI direct” when prompted."
            ),
        }

    set_active(pid, model=model)
    active = resolve_active_llm()
    return {
        "ok": True,
        "need_key": False,
        "provider_id": pid,
        "provider_name": active.get("provider_name") or pid,
        "model": active.get("model") or model,
        "base_url": active.get("base_url") or "",
        "message": (
            f"Grok is now your agent brain.\n\n"
            f"Provider: {active.get('provider_name')}\n"
            f"Model: {active.get('model') or model}\n\n"
            "Open Chat and type — Studio tools (terminal, search, browser) still run here. "
            "You do not need the CLI for normal agent chat."
        ),
    }


def is_grok_active() -> bool:
    """True if active model looks like Grok."""
    try:
        m = (resolve_active_llm().get("model") or "").lower()
        pid = (resolve_active_llm().get("provider_id") or "").lower()
        return "grok" in m or pid == "xai" or m.startswith("x-ai/grok")
    except Exception:  # noqa: BLE001
        return False


def estimate_request_budget(*, prompt_chars: int = 0) -> dict[str, Any]:
    """
    Rough pre-send budget for UI meter (Task #3).
    OpenRouter reserves credits against max_tokens; show that clearly.
    """
    active = resolve_active_llm()
    base = (active.get("base_url") or "").lower()
    model = active.get("model") or ""
    # Mirror llm._apply_safe_max_tokens defaults
    if "openrouter.ai" in base:
        max_out = 512
        note = "OpenRouter reserves credits for max_tokens — keep prompts short or add credits"
    elif "api.x.ai" in base:
        max_out = 2048
        note = "Direct xAI — billed by actual usage (API key from console.x.ai)"
    else:
        max_out = 2048
        note = "Estimated completion cap"
    # crude token estimate ~4 chars/token
    prompt_est = max(1, int(prompt_chars / 4))
    total_est = prompt_est + max_out
    return {
        "provider_id": active.get("provider_id"),
        "provider_name": active.get("provider_name"),
        "model": model,
        "base_url": active.get("base_url"),
        "prompt_tokens_est": prompt_est,
        "max_completion_tokens": max_out,
        "total_tokens_est": total_est,
        "note": note,
        "line": (
            f"{active.get('provider_name') or '?'} · {model or '?'} · "
            f"~{prompt_est} prompt + up to {max_out} reply tokens"
        ),
    }
