"""Execution adapters — bridge control plane to agent runtimes (Paperclip-style).

Paperclip principle: control plane orchestrates; adapters execute.
Supported:
  - studio_builtin : use Studio's chat/LLM stack (default)
  - process        : run a local shell command / script
  - http           : POST webhook to external agent
"""
from __future__ import annotations

import json
import subprocess
import traceback
from typing import Any

import urllib.request
import urllib.error


def execute_adapter(
    adapter_type: str,
    adapter_config: dict[str, Any],
    *,
    agent: dict[str, Any],
    task: dict[str, Any] | None = None,
    company: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    adapter_type = (adapter_type or "studio_builtin").strip().lower()
    cfg = dict(adapter_config or {})
    ctx = dict(context or {})
    log: list[str] = []
    try:
        if adapter_type == "studio_builtin":
            return _run_studio_builtin(agent, task, company, cfg, ctx, log)
        if adapter_type == "process":
            return _run_process(agent, task, company, cfg, ctx, log)
        if adapter_type == "http":
            return _run_http(agent, task, company, cfg, ctx, log)
        return {
            "ok": False,
            "summary": "",
            "cost_cents": 0,
            "log": log,
            "error": f"Unknown adapter_type: {adapter_type}",
            "artifacts": {},
        }
    except Exception as e:
        log.append(traceback.format_exc())
        return {
            "ok": False,
            "summary": "",
            "cost_cents": 0,
            "log": log,
            "error": str(e),
            "artifacts": {},
        }


def _run_studio_builtin(
    agent: dict[str, Any],
    task: dict[str, Any] | None,
    company: dict[str, Any] | None,
    cfg: dict[str, Any],
    ctx: dict[str, Any],
    log: list[str],
) -> dict[str, Any]:
    """Invoke Studio LLM via resolve_active_llm + chat_completion (real work)."""
    log.append("adapter=studio_builtin")
    prompt_parts = []
    if company:
        prompt_parts.append(f"Company goal: {company.get('goal') or '(none)'}")
    prompt_parts.append(
        f"You are {agent.get('name')} ({agent.get('title') or agent.get('role')}). "
        "Respond with a short status update and next action for this heartbeat."
    )
    if agent.get("capabilities"):
        prompt_parts.append(f"Capabilities: {agent['capabilities']}")
    if task:
        prompt_parts.append(f"Assigned task: {task.get('title')}")
        if task.get("description"):
            prompt_parts.append(task["description"])
        if task.get("goal_path"):
            prompt_parts.append("Goal path: " + " → ".join(task["goal_path"]))
    else:
        prompt_parts.append("No specific task — review status and report briefly.")
    prompt = "\n\n".join(prompt_parts)
    log.append(f"prompt_chars={len(prompt)}")

    summary = ""
    cost_cents = 0
    try:
        from app.core.services.llm.providers import resolve_active_llm
        from app.core.services.llm.llm import chat_completion, LLMError

        llm = resolve_active_llm()
        api_key = (llm.get("api_key") or llm.get("key") or "").strip()
        model = llm.get("model") or "gpt-4o-mini"
        base_url = llm.get("base_url") or llm.get("api_base_url") or "https://api.openai.com/v1"
        if not api_key:
            raise LLMError("No API key configured")
        messages = [
            {
                "role": "system",
                "content": (
                    "You are an autonomous company agent on a scheduled heartbeat. "
                    "Be concise (3-8 sentences). State progress, blockers, next step."
                ),
            },
            {"role": "user", "content": prompt},
        ]
        result = chat_completion(
            api_key=api_key,
            messages=messages,
            model=model,
            base_url=base_url,
            timeout=float(cfg.get("timeout_sec") or 60),
            return_usage=True,
            max_tokens=int(cfg.get("max_tokens") or 600),
        )
        if isinstance(result, tuple):
            summary = str(result[0] or "")
            usage = result[1] if len(result) > 1 and isinstance(result[1], dict) else {}
            tok = int(usage.get("total_tokens") or usage.get("completion_tokens") or 0)
            if tok:
                cost_cents = max(1, int(tok * 0.015 / 10) or 1)
            log.append(f"llm ok model={model} tokens={tok}")
        else:
            summary = str(result or "")
            log.append(f"llm ok model={model}")
    except Exception as e:
        summary = (
            f"[studio_builtin offline] {agent.get('name')} heartbeat — "
            f"task={(task or {}).get('title', 'idle')}: {e}"
        )
        log.append(f"llm fallback: {type(e).__name__}: {e}")
        cost_cents = 0

    if cfg.get("cost_cents_per_run"):
        try:
            cost_cents = int(cfg["cost_cents_per_run"])
        except (TypeError, ValueError):
            pass

    return {
        "ok": True,
        "summary": (summary or "")[:8000],
        "cost_cents": int(cost_cents or 0),
        "log": log,
        "error": "",
        "artifacts": {"prompt": prompt[:2000]},
    }


def _run_process(
    agent: dict[str, Any],
    task: dict[str, Any] | None,
    company: dict[str, Any] | None,
    cfg: dict[str, Any],
    ctx: dict[str, Any],
    log: list[str],
) -> dict[str, Any]:
    log.append("adapter=process")
    cmd = cfg.get("command") or cfg.get("cmd")
    if not cmd:
        return {
            "ok": False,
            "summary": "",
            "cost_cents": 0,
            "log": log,
            "error": "process adapter requires adapter_config.command",
            "artifacts": {},
        }
    if isinstance(cmd, list):
        args = [str(x) for x in cmd]
    else:
        args = str(cmd)
    cwd = cfg.get("cwd") or None
    timeout = int(cfg.get("timeout_sec") or 120)
    import os
    env = dict(os.environ)
    if isinstance(cfg.get("env"), dict):
        env.update({str(k): str(v) for k, v in cfg["env"].items()})
    env["PAPERCLIP_AGENT_ID"] = str(agent.get("id") or "")
    env["PAPERCLIP_AGENT_NAME"] = str(agent.get("name") or "")
    if task:
        env["PAPERCLIP_TASK_ID"] = str(task.get("id") or "")
        env["PAPERCLIP_TASK_TITLE"] = str(task.get("title") or "")
    if company:
        env["PAPERCLIP_COMPANY_ID"] = str(company.get("id") or "")
        env["PAPERCLIP_COMPANY_GOAL"] = str(company.get("goal") or "")
    log.append(f"exec timeout={timeout}s cwd={cwd}")
    try:
        completed = subprocess.run(
            args,
            shell=isinstance(args, str),
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = (completed.stdout or "")[-4000:]
        err = (completed.stderr or "")[-2000:]
        log.append(f"exit={completed.returncode}")
        if err:
            log.append(f"stderr: {err[:500]}")
        return {
            "ok": completed.returncode == 0,
            "summary": out or err or f"exit {completed.returncode}",
            "cost_cents": int(cfg.get("cost_cents_per_run") or 0),
            "log": log,
            "error": "" if completed.returncode == 0 else err,
            "artifacts": {"stdout": out, "stderr": err, "returncode": completed.returncode},
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "summary": "",
            "cost_cents": 0,
            "log": log,
            "error": f"process timeout after {timeout}s",
            "artifacts": {},
        }


def _run_http(
    agent: dict[str, Any],
    task: dict[str, Any] | None,
    company: dict[str, Any] | None,
    cfg: dict[str, Any],
    ctx: dict[str, Any],
    log: list[str],
) -> dict[str, Any]:
    log.append("adapter=http")
    url = (cfg.get("url") or cfg.get("webhook") or "").strip()
    if not url:
        return {
            "ok": False,
            "summary": "",
            "cost_cents": 0,
            "log": log,
            "error": "http adapter requires adapter_config.url",
            "artifacts": {},
        }
    payload = {
        "agent": {"id": agent.get("id"), "name": agent.get("name"), "role": agent.get("role")},
        "task": task,
        "company": {"id": (company or {}).get("id"), "goal": (company or {}).get("goal")},
        "context": ctx,
    }
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if isinstance(cfg.get("headers"), dict):
        headers.update({str(k): str(v) for k, v in cfg["headers"].items()})
    method = (cfg.get("method") or "POST").upper()
    timeout = int(cfg.get("timeout_sec") or 60)
    log.append(f"{method} {url}")
    try:
        req = urllib.request.Request(url, data=data if method != "GET" else None, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")[:4000]
            log.append(f"status={resp.status}")
            return {
                "ok": 200 <= int(resp.status) < 300,
                "summary": body[:1500],
                "cost_cents": int(cfg.get("cost_cents_per_run") or 0),
                "log": log,
                "error": "",
                "artifacts": {"status": resp.status, "body": body},
            }
    except Exception as e:
        log.append(str(e))
        return {
            "ok": False,
            "summary": "",
            "cost_cents": 0,
            "log": log,
            "error": str(e),
            "artifacts": {},
        }
