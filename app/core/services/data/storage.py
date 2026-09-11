"""JSON file storage under ./data (portable)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.paths import agents_dir, config_path, runs_dir, tasks_dir


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def _write_json(path: Path, data: Any) -> None:
    """Crash-safe atomic write: temp file then replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{uuid.uuid4().hex[:8]}.tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            try:
                import os

                os.fsync(f.fileno())
            except Exception:  # noqa: BLE001
                pass
        tmp.replace(path)
    except Exception:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:  # noqa: BLE001
            pass
        # last resort non-atomic
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


def load_config() -> dict[str, Any]:
    default = {
        "theme": "dark",
        "api_key": "",
        "api_base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "system_prompt": "",  # empty = use built-in default
        "created_at": _now(),
    }
    cfg = _read_json(config_path(), default)
    if not isinstance(cfg, dict):
        cfg = default
    for k, v in default.items():
        cfg.setdefault(k, v)
    if not config_path().exists():
        _write_json(config_path(), cfg)
    return cfg


def save_config(cfg: dict[str, Any]) -> None:
    cfg["updated_at"] = _now()
    _write_json(config_path(), cfg)


def list_agents() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for p in sorted(agents_dir().glob("*.json")):
        data = _read_json(p, None)
        if isinstance(data, dict) and data.get("id"):
            items.append(data)
    return items


def save_agent(agent: dict[str, Any]) -> dict[str, Any]:
    if not agent.get("id"):
        agent["id"] = str(uuid.uuid4())
        agent["created_at"] = _now()
    # Per-agent OpenAI-compatible LLM (empty = use Settings defaults / "Default")
    agent.setdefault("llm_model", "")
    agent.setdefault("llm_base_url", "")
    agent.setdefault("llm_api_key", "")
    agent.setdefault("llm_provider_id", "")  # empty = Default provider
    # Permanent prompts (never merge temporary assignments into these)
    agent.setdefault("system_prompt", "")
    agent.setdefault("worker_prompt", "")
    # Optional fallback model (explicit only — never silent switch)
    agent.setdefault("fallback_enabled", False)
    agent.setdefault("fallback_provider_id", "")
    agent.setdefault("fallback_model", "")
    agent.setdefault("fallback_base_url", "")
    agent.setdefault("fallback_api_key", "")
    agent.setdefault("attachments", [])
    agent.setdefault("tool_permissions", {})
    agent.setdefault("enabled", True)
    agent["updated_at"] = _now()
    path = agents_dir() / f"{agent['id']}.json"
    _write_json(path, agent)
    return agent


def mask_api_key(key: str) -> str:
    """Display-safe masked API key (never full secret)."""
    k = (key or "").strip()
    if not k:
        return "(Default / none)"
    if len(k) <= 8:
        return "••••••••"
    return f"{k[:3]}••••••••••{k[-4:]}"


def resolve_agent_llm(
    agent: dict[str, Any] | None = None,
    *,
    use_fallback: bool = False,
) -> dict[str, Any]:
    """
    Return effective LLM config for an agent.

    Empty agent fields mean **Default** (global Settings / active provider).
    Explicit overrides stay fixed when global settings change.

    Returns:
      model, base_url, api_key,
      provider_id, provider_name,
      model_source ("default"|"override"|"fallback"),
      provider_source, base_url_source, api_key_source,
      configured: {model, provider_id, base_url} as stored (may be empty = Default)
    """
    cfg = load_config()
    ag = agent or {}
    try:
        from app.core.services.llm.providers import get_provider, list_providers, resolve_active_llm

        active = resolve_active_llm()
    except Exception:  # noqa: BLE001
        active = {
            "model": cfg.get("model") or "gpt-4o-mini",
            "base_url": cfg.get("api_base_url") or "https://api.openai.com/v1",
            "api_key": cfg.get("api_key") or "",
            "provider_id": "",
            "provider_name": "Default",
        }
        get_provider = None  # type: ignore
        list_providers = lambda: []  # type: ignore

    configured = {
        "model": (ag.get("llm_model") or "").strip(),
        "provider_id": (ag.get("llm_provider_id") or "").strip(),
        "base_url": (ag.get("llm_base_url") or "").strip(),
        "has_api_key": bool((ag.get("llm_api_key") or "").strip()),
    }

    # Fallback path (only when explicitly enabled and requested)
    if use_fallback and ag.get("fallback_enabled"):
        fb_model = (ag.get("fallback_model") or "").strip()
        fb_base = (ag.get("fallback_base_url") or "").strip()
        fb_key = (ag.get("fallback_api_key") or "").strip()
        fb_pid = (ag.get("fallback_provider_id") or "").strip()
        if fb_pid and get_provider:
            try:
                p = get_provider(fb_pid)
                if p:
                    fb_base = fb_base or (p.get("base_url") or "")
                    if not fb_key:
                        for k in p.get("keys") or []:
                            if k.get("key"):
                                fb_key = k.get("key") or ""
                                break
            except Exception:  # noqa: BLE001
                pass
        return {
            "model": fb_model or active.get("model") or cfg.get("model") or "gpt-4o-mini",
            "base_url": (
                fb_base
                or active.get("base_url")
                or cfg.get("api_base_url")
                or "https://api.openai.com/v1"
            ).strip(),
            "api_key": (
                fb_key or active.get("api_key") or cfg.get("api_key") or ""
            ).strip(),
            "provider_id": fb_pid or active.get("provider_id") or "",
            "provider_name": fb_pid or active.get("provider_name") or "Fallback",
            "model_source": "fallback",
            "provider_source": "fallback" if fb_pid else "default",
            "base_url_source": "fallback" if fb_base else "default",
            "api_key_source": "fallback" if fb_key else "default",
            "configured": configured,
            "is_fallback": True,
        }

    # Optional provider override (empty provider_id = Default)
    pid = configured["provider_id"]
    prov_base = ""
    prov_key = ""
    prov_name = active.get("provider_name") or "Default"
    if pid and get_provider:
        try:
            p = get_provider(pid)
            if p:
                prov_name = p.get("name") or pid
                prov_base = (p.get("base_url") or "").strip()
                for k in p.get("keys") or []:
                    if k.get("key"):
                        prov_key = k.get("key") or ""
                        break
        except Exception:  # noqa: BLE001
            pass

    model_override = configured["model"]
    base_override = configured["base_url"]
    key_override = (ag.get("llm_api_key") or "").strip()

    model = (
        model_override
        or active.get("model")
        or cfg.get("model")
        or "gpt-4o-mini"
    ).strip()
    base_url = (
        base_override
        or prov_base
        or active.get("base_url")
        or cfg.get("api_base_url")
        or "https://api.openai.com/v1"
    ).strip()
    api_key = (
        key_override
        or prov_key
        or active.get("api_key")
        or cfg.get("api_key")
        or ""
    ).strip()

    return {
        "model": model,
        "base_url": base_url,
        "api_key": api_key,
        "provider_id": pid or active.get("provider_id") or "",
        "provider_name": prov_name if pid else (active.get("provider_name") or "Default"),
        "model_source": "override" if model_override else "default",
        "provider_source": "override" if pid else "default",
        "base_url_source": "override" if base_override else ("provider" if prov_base and pid else "default"),
        "api_key_source": "override" if key_override else ("provider" if prov_key and pid else "default"),
        "configured": configured,
        "is_fallback": False,
        "api_key_masked": mask_api_key(api_key if key_override else ""),
        "display_provider": (
            f"Default — {active.get('provider_name') or 'global'}"
            if not pid
            else prov_name
        ),
        "display_model": (
            f"Default — {active.get('model') or cfg.get('model') or 'global'}"
            if not model_override
            else model_override
        ),
    }


def resolve_worker_llm(
    node: dict[str, Any] | None = None,
    agent: dict[str, Any] | None = None,
    *,
    use_fallback: bool = False,
) -> dict[str, Any]:
    """
    Resolve LLM for an org-chart worker node + optional linked agent profile.
    Node fields win over agent profile for model/provider; empty = Default.
    """
    merged: dict[str, Any] = {}
    if agent:
        merged.update(agent)
    if node:
        # Prefer non-empty node overrides
        for k in (
            "llm_model",
            "llm_base_url",
            "llm_api_key",
            "llm_provider_id",
            "fallback_enabled",
            "fallback_provider_id",
            "fallback_model",
            "fallback_base_url",
            "fallback_api_key",
            "system_prompt",
            "worker_prompt",
        ):
            v = node.get(k)
            if v is not None and v != "" and v != [] and v != {}:
                merged[k] = v
        # If agent has key and node doesn't, keep agent key
        if not (node.get("llm_api_key") or "").strip() and agent:
            merged["llm_api_key"] = agent.get("llm_api_key") or ""
    return resolve_agent_llm(merged, use_fallback=use_fallback)


def delete_agent(agent_id: str) -> None:
    path = agents_dir() / f"{agent_id}.json"
    if path.exists():
        path.unlink()


def get_agent(agent_id: str) -> dict[str, Any] | None:
    path = agents_dir() / f"{agent_id}.json"
    data = _read_json(path, None)
    return data if isinstance(data, dict) else None


def list_tasks() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for p in sorted(tasks_dir().glob("*.json")):
        data = _read_json(p, None)
        if isinstance(data, dict) and data.get("id"):
            items.append(data)
    return items


def save_task(task: dict[str, Any]) -> dict[str, Any]:
    if not task.get("id"):
        task["id"] = str(uuid.uuid4())
        task["created_at"] = _now()
    task["updated_at"] = _now()
    path = tasks_dir() / f"{task['id']}.json"
    _write_json(path, task)
    return task


def delete_task(task_id: str) -> None:
    path = tasks_dir() / f"{task_id}.json"
    if path.exists():
        path.unlink()


def list_runs() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for p in sorted(runs_dir().glob("*.json"), reverse=True):
        data = _read_json(p, None)
        if isinstance(data, dict) and data.get("id"):
            items.append(data)
    return items


def save_run(run: dict[str, Any]) -> dict[str, Any]:
    if not run.get("id"):
        run["id"] = str(uuid.uuid4())
        run["created_at"] = _now()
    run["updated_at"] = _now()
    path = runs_dir() / f"{run['id']}.json"
    _write_json(path, run)
    return run


def get_run(run_id: str) -> dict[str, Any] | None:
    path = runs_dir() / f"{run_id}.json"
    data = _read_json(path, None)
    return data if isinstance(data, dict) else None
