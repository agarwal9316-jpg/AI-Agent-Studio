"""User-owned LLM profiles: cloud, local (Ollama), adapters, tool policy."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.paths import model_profiles_dir
from app.core.services.data.storage import _read_json, _write_json


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path(pid: str):
    return model_profiles_dir() / f"{pid}.json"


def list_profiles() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in sorted(model_profiles_dir().glob("*.json")):
        data = _read_json(p, None)
        if isinstance(data, dict) and data.get("id"):
            out.append(data)
    out.sort(key=lambda x: str(x.get("updated_at") or x.get("created_at") or ""), reverse=True)
    return out


def get_profile(profile_id: str) -> dict[str, Any] | None:
    if not profile_id:
        return None
    data = _read_json(_path(profile_id), None)
    return data if isinstance(data, dict) else None


def save_profile(profile: dict[str, Any]) -> dict[str, Any]:
    if not profile.get("id"):
        profile["id"] = str(uuid.uuid4())
    if not profile.get("created_at"):
        profile["created_at"] = _now()
    profile["updated_at"] = _now()
    # normalize
    profile.setdefault("name", "My model")
    profile.setdefault("kind", "openai_compatible")  # openai_compatible | ollama | cloud
    profile.setdefault("base_url", "https://api.openai.com/v1")
    profile.setdefault("model", "gpt-4o-mini")
    profile.setdefault("api_key", "")
    profile.setdefault("system_prompt", "")
    profile.setdefault("temperature", 0.4)
    profile.setdefault("max_tokens", 0)
    profile.setdefault("context_window", 128000)
    profile.setdefault("adapter_path", "")
    profile.setdefault("knowledge_enabled", True)
    profile.setdefault("tools_enabled", True)
    profile.setdefault("notes", "")
    _write_json(_path(str(profile["id"])), profile)
    try:
        from app.core.services.system.ops_monitor import log_event

        log_event("model_profile", f"Saved profile {profile.get('name')}", source="models", meta={"id": profile["id"]})
    except Exception:  # noqa: BLE001
        pass
    return profile


def delete_profile(profile_id: str) -> bool:
    p = _path(profile_id)
    if not p.exists():
        return False
    try:
        p.unlink()
        return True
    except Exception:  # noqa: BLE001
        return False


def create_profile(
    name: str,
    *,
    kind: str = "openai_compatible",
    base_url: str = "",
    model: str = "",
    api_key: str = "",
    system_prompt: str = "",
    adapter_path: str = "",
    notes: str = "",
) -> dict[str, Any]:
    defaults = {
        "ollama": ("http://127.0.0.1:11434/v1", "llama3.2", "ollama"),
        "openai_compatible": ("https://api.openai.com/v1", "gpt-4o-mini", ""),
        "cloud": ("https://openrouter.ai/api/v1", "openai/gpt-4o-mini", ""),
    }
    bu, mod, key = defaults.get(kind, defaults["openai_compatible"])
    return save_profile(
        {
            "name": (name or "My model").strip(),
            "kind": kind,
            "base_url": (base_url or bu).strip(),
            "model": (model or mod).strip(),
            "api_key": (api_key or key).strip(),
            "system_prompt": system_prompt or "",
            "adapter_path": adapter_path or "",
            "notes": notes or "",
        }
    )


def profile_to_llm_config(profile: dict[str, Any]) -> dict[str, str]:
    """Map profile → llm.chat_completion kwargs fields."""
    return {
        "api_key": str(profile.get("api_key") or "ollama"),
        "model": str(profile.get("model") or "gpt-4o-mini"),
        "base_url": str(profile.get("base_url") or "https://api.openai.com/v1"),
    }


def ollama_list_models() -> dict[str, Any]:
    """Query local Ollama tags."""
    import json
    import urllib.error
    import urllib.request

    url = "http://127.0.0.1:11434/api/tags"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        models = []
        for m in data.get("models") or []:
            models.append(
                {
                    "name": m.get("name") or m.get("model"),
                    "size": m.get("size"),
                    "modified_at": m.get("modified_at"),
                }
            )
        return {"ok": True, "models": models, "running": True}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "models": [], "running": False, "error": str(e)}


def ollama_pull(model: str, on_line: Any = None) -> dict[str, Any]:
    """Pull model via Ollama HTTP API (streaming NDJSON)."""
    import json
    import urllib.request

    model = (model or "").strip()
    if not model:
        return {"ok": False, "error": "Model name required"}
    body = json.dumps({"name": model, "stream": True}).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/pull",
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
        # Register profile
        prof = create_profile(
            f"Ollama · {model}",
            kind="ollama",
            base_url="http://127.0.0.1:11434/v1",
            model=model,
            api_key="ollama",
            notes=f"Pulled via Studio { _now() }",
        )
        return {"ok": True, "profile": prof}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def test_profile_completion(profile: dict[str, Any]) -> dict[str, Any]:
    """Short completion to verify profile works."""
    import time

    from app.core.services.llm.llm import LLMError, chat_completion

    cfg = profile_to_llm_config(profile)
    t0 = time.time()
    try:
        text = chat_completion(
            api_key=cfg["api_key"],
            model=cfg["model"],
            base_url=cfg["base_url"],
            messages=[
                {"role": "system", "content": "Reply with exactly: OK"},
                {"role": "user", "content": "ping"},
            ],
            timeout=45.0,
            max_tokens=16,
            temperature=0,
            normalize_tools=False,
        )
        ms = int((time.time() - t0) * 1000)
        return {"ok": True, "reply": str(text)[:200], "latency_ms": ms}
    except LLMError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
