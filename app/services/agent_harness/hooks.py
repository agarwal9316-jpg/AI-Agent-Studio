"""Lifecycle hooks: SessionStart, PreToolUse, PostToolUse, Stop (command or HTTP)."""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from app.paths import data_dir
from app.core.services.data.storage import load_config


def hooks_dir() -> Path:
    d = data_dir() / "hooks"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_hook_files() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    # app data hooks
    for p in sorted(hooks_dir().glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data["_source"] = str(p)
                out.append(data)
        except Exception:  # noqa: BLE001
            continue
    # optional ~/.grok/hooks
    home_hooks = Path.home() / ".grok" / "hooks"
    if home_hooks.is_dir():
        for p in sorted(home_hooks.glob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    data["_source"] = str(p)
                    out.append(data)
            except Exception:  # noqa: BLE001
                continue
    return out


def hooks_enabled() -> bool:
    return bool(load_config().get("agent_hooks_enabled", True))


def run_hooks(
    event: str,
    *,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Run hooks for event. PreToolUse may return {blocked: true, reason}.
    """
    if not hooks_enabled():
        return {"ok": True, "ran": 0, "blocked": False}

    payload = payload or {}
    ran = 0
    logs: list[str] = []
    for doc in _load_hook_files():
        hooks_map = doc.get("hooks") or {}
        entries = hooks_map.get(event) or []
        if not isinstance(entries, list):
            continue
        for entry in entries:
            for h in entry.get("hooks") or [entry]:
                htype = (h.get("type") or "command").lower()
                try:
                    if htype == "command":
                        cmd = h.get("command") or ""
                        if not cmd:
                            continue
                        env_payload = json.dumps(payload)
                        # inject as env var
                        import os

                        env = os.environ.copy()
                        env["STUDIO_HOOK_EVENT"] = event
                        env["STUDIO_HOOK_PAYLOAD"] = env_payload[:8000]
                        r = subprocess.run(
                            cmd,
                            shell=True,
                            capture_output=True,
                            text=True,
                            timeout=float(h.get("timeout") or 30),
                            env=env,
                        )
                        ran += 1
                        out = (r.stdout or "") + (r.stderr or "")
                        logs.append(f"cmd exit={r.returncode}: {out[:300]}")
                        if event == "PreToolUse" and r.returncode != 0:
                            return {
                                "ok": False,
                                "blocked": True,
                                "reason": out.strip() or f"hook exit {r.returncode}",
                                "ran": ran,
                                "logs": logs,
                            }
                        # special stdout: BLOCK: reason
                        for line in (r.stdout or "").splitlines():
                            if line.upper().startswith("BLOCK:"):
                                return {
                                    "ok": False,
                                    "blocked": True,
                                    "reason": line[6:].strip() or "blocked by hook",
                                    "ran": ran,
                                    "logs": logs,
                                }
                    elif htype == "http":
                        url = h.get("url") or ""
                        if not url:
                            continue
                        body = json.dumps({"event": event, "payload": payload}).encode("utf-8")
                        req = urllib.request.Request(
                            url,
                            data=body,
                            method="POST",
                            headers={"Content-Type": "application/json"},
                        )
                        with urllib.request.urlopen(req, timeout=float(h.get("timeout") or 15)) as resp:
                            resp_body = resp.read().decode("utf-8", errors="replace")[:500]
                        ran += 1
                        logs.append(f"http {url}: {resp_body[:200]}")
                        try:
                            j = json.loads(resp_body)
                            if j.get("block") or j.get("blocked"):
                                return {
                                    "ok": False,
                                    "blocked": True,
                                    "reason": j.get("reason") or "blocked by HTTP hook",
                                    "ran": ran,
                                    "logs": logs,
                                }
                        except json.JSONDecodeError:
                            pass
                except Exception as e:  # noqa: BLE001
                    logs.append(f"hook error: {e}")
                    if h.get("fail_closed") and event == "PreToolUse":
                        return {
                            "ok": False,
                            "blocked": True,
                            "reason": f"hook error (fail_closed): {e}",
                            "ran": ran,
                            "logs": logs,
                        }
    return {"ok": True, "blocked": False, "ran": ran, "logs": logs[:20]}


def list_hooks() -> list[dict[str, Any]]:
    out = []
    for doc in _load_hook_files():
        out.append(
            {
                "source": doc.get("_source"),
                "events": list((doc.get("hooks") or {}).keys()),
            }
        )
    return out
