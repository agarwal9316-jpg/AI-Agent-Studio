"""Offline · Ollama (local) — clearly labeled local LLM path (PENDING #17).

Not a cloud API. Models run on this machine via the Ollama daemon.
Soft-degrades: public helpers never raise into chat/Settings callers.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

# Display / identity
OFFLINE_PROVIDER_ID = "ollama"
OFFLINE_LABEL = "Offline · Ollama (local)"
LEGACY_LABELS = frozenset({"Ollama (local)", "Ollama", "ollama"})
DEFAULT_HOST = "http://127.0.0.1:11434"
DEFAULT_OPENAI_BASE = "http://127.0.0.1:11434/v1"
INSTALL_URL = "https://ollama.com"
DEFAULT_API_KEY = "ollama"

_NEXT_INSTALL = (
    f"Install Ollama from {INSTALL_URL} (free, local)",
    "Start Ollama (app or: ollama serve)",
    f"Confirm the base URL (default {DEFAULT_HOST})",
    "Refresh / Fetch models, then pick a local model",
)
_NEXT_START = (
    "Start Ollama on this computer (app menu or: ollama serve)",
    f"Check the base URL is reachable (default {DEFAULT_HOST})",
    "Then Refresh / Fetch models",
)
_NEXT_PULL = (
    "Pull a model: ollama pull llama3.2  (or use Models → Pull)",
    "Refresh the model list",
)


def is_ollama_provider(provider_id: str = "", name: str = "", base_url: str = "") -> bool:
    """True if this looks like the Offline Ollama path."""
    pid = (provider_id or "").strip().lower()
    if pid == OFFLINE_PROVIDER_ID:
        return True
    n = (name or "").strip()
    if n == OFFLINE_LABEL or n in LEGACY_LABELS:
        return True
    b = (base_url or "").lower()
    return "11434" in b or "ollama" in b


def normalize_host(url: str = "") -> str:
    """Return scheme://host:port for Ollama native API (no /v1)."""
    raw = (url or "").strip() or DEFAULT_HOST
    if "://" not in raw:
        raw = "http://" + raw
    parsed = urlparse(raw)
    scheme = parsed.scheme or "http"
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port
    if port is None:
        # path-only leftovers like 127.0.0.1:11434 already handled by urlparse
        if parsed.netloc and ":" in parsed.netloc and parsed.hostname:
            port = 11434 if host in ("127.0.0.1", "localhost") else None
        else:
            port = 11434
    if port:
        return f"{scheme}://{host}:{port}"
    return f"{scheme}://{host}"


def openai_base_from_host(host: str = "") -> str:
    """OpenAI-compatible base URL (.../v1) used by chat_completion."""
    h = normalize_host(host)
    return h.rstrip("/") + "/v1"


def host_from_openai_base(base_url: str = "") -> str:
    """Strip trailing /v1 from an OpenAI-compatible base."""
    raw = (base_url or "").strip().rstrip("/")
    if raw.lower().endswith("/v1"):
        raw = raw[:-3].rstrip("/")
    return normalize_host(raw or DEFAULT_HOST)


def display_label() -> str:
    return OFFLINE_LABEL


def get_configured_base() -> str:
    """Editable OpenAI-compatible base for Offline Ollama (from provider store)."""
    try:
        from app.core.services.llm.providers import get_provider

        p = get_provider(OFFLINE_PROVIDER_ID) or {}
        bu = (p.get("base_url") or "").strip()
        if bu:
            return openai_base_from_host(bu) if not bu.rstrip("/").lower().endswith("/v1") else bu.rstrip("/")
    except Exception:  # noqa: BLE001
        pass
    return DEFAULT_OPENAI_BASE


def get_configured_host() -> str:
    return host_from_openai_base(get_configured_base())


def set_configured_base(url: str) -> str:
    """Persist editable base URL on the ollama provider. Returns OpenAI base."""
    openai_base = openai_base_from_host(url or DEFAULT_HOST)
    try:
        from app.core.services.llm.providers import upsert_provider

        upsert_provider(
            provider_id=OFFLINE_PROVIDER_ID,
            name=OFFLINE_LABEL,
            base_url=openai_base,
            notes=(
                "Offline / local only — not a cloud API. "
                f"Default host {DEFAULT_HOST}. Key may be “ollama”."
            ),
        )
    except Exception:  # noqa: BLE001
        pass
    return openai_base


def ensure_offline_label() -> None:
    """Rename legacy “Ollama (local)” → Offline · Ollama (local) without wiping keys."""
    try:
        from app.core.services.llm.providers import load_providers, save_providers

        store = load_providers()
        changed = False
        for p in store.get("providers") or []:
            if str(p.get("id") or "") != OFFLINE_PROVIDER_ID:
                continue
            name = str(p.get("name") or "")
            if name != OFFLINE_LABEL:
                p["name"] = OFFLINE_LABEL
                changed = True
            notes = str(p.get("notes") or "")
            if "Offline" not in notes and "local" in notes.lower():
                p["notes"] = (
                    "Offline / local only — not a cloud API. "
                    f"Default host {DEFAULT_HOST}. Key may be “ollama”."
                )
                changed = True
            elif "Offline" not in notes:
                p["notes"] = (
                    "Offline / local only — not a cloud API. "
                    f"Default host {DEFAULT_HOST}. Key may be “ollama”."
                )
                changed = True
            bu = (p.get("base_url") or "").strip()
            if not bu:
                p["base_url"] = DEFAULT_OPENAI_BASE
                changed = True
        if changed:
            save_providers(store)
    except Exception:  # noqa: BLE001
        pass


def _next_actions(*, running: bool, models: list[Any]) -> list[str]:
    if not running:
        return list(_NEXT_INSTALL)
    if not models:
        return list(_NEXT_PULL)
    return [
        "Select a local model and Set active provider",
        "No cloud key required — API key can be “ollama”",
    ]


def health(
    base_url: str = "",
    *,
    timeout: float = 3.0,
    fetch_models: bool = True,
) -> dict[str, Any]:
    """
    Detect whether Offline Ollama is running.

    Returns a soft-degraded dict (never raises):
      ok, running, label, offline, base_url, host, models, model_names,
      error, next_actions, status_line
    """
    label = OFFLINE_LABEL
    host = host_from_openai_base(base_url or get_configured_base())
    openai_base = openai_base_from_host(host)
    out: dict[str, Any] = {
        "ok": False,
        "running": False,
        "label": label,
        "offline": True,
        "base_url": openai_base,
        "host": host,
        "models": [],
        "model_names": [],
        "error": "",
        "next_actions": list(_NEXT_START),
        "status_line": f"○ {label} not running",
    }
    if not fetch_models:
        # connectivity-only probe via /api/tags still used below
        pass
    url = host.rstrip("/") + "/api/tags"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        models: list[dict[str, Any]] = []
        for m in data.get("models") or []:
            if not isinstance(m, dict):
                continue
            models.append(
                {
                    "name": m.get("name") or m.get("model"),
                    "size": m.get("size"),
                    "modified_at": m.get("modified_at"),
                }
            )
        names = [str(m.get("name")) for m in models if m.get("name")]
        out.update(
            {
                "ok": True,
                "running": True,
                "models": models,
                "model_names": names,
                "error": "",
                "next_actions": _next_actions(running=True, models=models),
                "status_line": (
                    f"● {label} running · {len(names)} model(s)"
                    + (f" · {', '.join(names[:8])}" if names else " · (none pulled yet)")
                ),
            }
        )
        return out
    except urllib.error.URLError as e:
        out["error"] = str(getattr(e, "reason", e) or e)
    except Exception as e:  # noqa: BLE001
        out["error"] = str(e)
    out["next_actions"] = list(_NEXT_INSTALL if "refused" in (out["error"] or "").lower() or "10061" in (out["error"] or "") else _NEXT_START)
    # Prefer start-focused when connection refused; install+start otherwise
    err_l = (out["error"] or "").lower()
    if any(x in err_l for x in ("refused", "10061", "actively refused", "errno 111")):
        out["next_actions"] = list(_NEXT_START)
    else:
        out["next_actions"] = list(_NEXT_INSTALL)
    out["status_line"] = f"○ {label} not reachable ({out['error'] or 'offline'})"
    return out


def list_local_models(base_url: str = "", *, timeout: float = 3.0) -> dict[str, Any]:
    """Fetch local tags; same shape as legacy model_profiles.ollama_list_models + extras."""
    h = health(base_url, timeout=timeout, fetch_models=True)
    return {
        "ok": bool(h.get("ok")),
        "running": bool(h.get("running")),
        "models": list(h.get("models") or []),
        "model_names": list(h.get("model_names") or []),
        "error": h.get("error") or "",
        "label": h.get("label") or OFFLINE_LABEL,
        "offline": True,
        "base_url": h.get("base_url") or DEFAULT_OPENAI_BASE,
        "host": h.get("host") or DEFAULT_HOST,
        "next_actions": list(h.get("next_actions") or []),
        "status_line": h.get("status_line") or "",
    }


def fetch_models_for_provider(*, force: bool = True, timeout: float = 8.0) -> dict[str, Any]:
    """
    When Ollama is up, refresh provider models_cache with local ids.
    When down, return a clear error without raising (soft-degrade).
    """
    ensure_offline_label()
    h = health(timeout=timeout)
    if not h.get("running"):
        return {
            "ok": False,
            "running": False,
            "models": [],
            "error": h.get("error") or "Ollama not running",
            "next_actions": list(h.get("next_actions") or []),
            "status_line": h.get("status_line") or "",
            "label": OFFLINE_LABEL,
        }
    names = list(h.get("model_names") or [])
    try:
        from app.core.services.llm.providers import load_providers, save_providers
        from datetime import datetime, timezone

        store = load_providers()
        for p in store.get("providers") or []:
            if str(p.get("id") or "") != OFFLINE_PROVIDER_ID:
                continue
            if force or not p.get("models_cache"):
                p["models_cache"] = names
                p["models_fetched_at"] = datetime.now(timezone.utc).isoformat()
                p["name"] = OFFLINE_LABEL
            break
        save_providers(store)
    except Exception as e:  # noqa: BLE001
        return {
            "ok": True,
            "running": True,
            "models": names,
            "error": f"models listed but cache save failed: {e}",
            "next_actions": list(h.get("next_actions") or []),
            "status_line": h.get("status_line") or "",
            "label": OFFLINE_LABEL,
        }
    return {
        "ok": True,
        "running": True,
        "models": names,
        "error": "",
        "next_actions": list(h.get("next_actions") or []),
        "status_line": h.get("status_line") or "",
        "label": OFFLINE_LABEL,
    }


def pull_model(model: str, on_line: Any = None, *, base_url: str = "") -> dict[str, Any]:
    """Pull via native /api/pull; register a profile on success. Soft-degrades."""
    model = (model or "").strip()
    if not model:
        return {"ok": False, "error": "Model name required", "next_actions": list(_NEXT_PULL)}
    host = host_from_openai_base(base_url or get_configured_base())
    body = json.dumps({"name": model, "stream": True}).encode("utf-8")
    req = urllib.request.Request(
        host.rstrip("/") + "/api/pull",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=3600) as resp:
            for raw in resp:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if on_line:
                    try:
                        on_line(chunk)
                    except Exception:  # noqa: BLE001
                        pass
                if chunk.get("error"):
                    return {"ok": False, "error": str(chunk.get("error"))}
        from datetime import datetime, timezone

        from app.core.services.llm.model_profiles import create_profile

        prof = create_profile(
            f"{OFFLINE_LABEL} · {model}",
            kind="ollama",
            base_url=openai_base_from_host(host),
            model=model,
            api_key=DEFAULT_API_KEY,
            notes=f"Pulled via Studio {datetime.now(timezone.utc).isoformat()} (offline local)",
        )
        try:
            fetch_models_for_provider(force=True)
        except Exception:  # noqa: BLE001
            pass
        return {"ok": True, "profile": prof, "label": OFFLINE_LABEL}
    except Exception as e:  # noqa: BLE001
        h = health(base_url=base_url or "", timeout=2.0)
        return {
            "ok": False,
            "error": str(e),
            "next_actions": list(h.get("next_actions") or _NEXT_START),
            "label": OFFLINE_LABEL,
        }
