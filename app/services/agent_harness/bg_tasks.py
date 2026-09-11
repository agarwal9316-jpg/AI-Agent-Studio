"""Background shell tasks with task_id (Grok-style)."""

from __future__ import annotations

import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from app.paths import data_dir

_lock = threading.Lock()
_tasks: dict[str, dict[str, Any]] = {}


def _task_log_dir() -> Path:
    d = data_dir() / "bg_tasks"
    d.mkdir(parents=True, exist_ok=True)
    return d


def start_bg_shell(
    command: str,
    *,
    cwd: str | Path | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Start command in background; returns task_id immediately."""
    tid = uuid.uuid4().hex[:12]
    log_path = _task_log_dir() / f"{tid}.log"
    meta: dict[str, Any] = {
        "id": tid,
        "command": command,
        "cwd": str(cwd or ""),
        "status": "running",
        "started": time.time(),
        "ended": None,
        "exit_code": None,
        "log_path": str(log_path),
        "output": "",
    }

    def runner() -> None:
        try:
            with log_path.open("w", encoding="utf-8", errors="replace") as logf:
                proc = subprocess.Popen(
                    command,
                    shell=True,
                    cwd=str(cwd) if cwd else None,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    errors="replace",
                )
                with _lock:
                    _tasks[tid]["proc"] = proc
                chunks: list[str] = []
                assert proc.stdout is not None
                for line in proc.stdout:
                    chunks.append(line)
                    logf.write(line)
                    logf.flush()
                    if sum(len(c) for c in chunks) > 400_000:
                        chunks = chunks[-200:]
                code = proc.wait(timeout=timeout) if timeout else proc.wait()
                out = "".join(chunks)
                with _lock:
                    _tasks[tid].update(
                        {
                            "status": "completed",
                            "ended": time.time(),
                            "exit_code": code,
                            "output": out[-100_000:],
                        }
                    )
        except Exception as e:  # noqa: BLE001
            with _lock:
                _tasks[tid].update(
                    {
                        "status": "error",
                        "ended": time.time(),
                        "exit_code": -1,
                        "output": str(e),
                        "error": str(e),
                    }
                )

    with _lock:
        _tasks[tid] = meta
    t = threading.Thread(target=runner, name=f"bg-{tid}", daemon=True)
    t.start()
    return {"ok": True, "task_id": tid, "status": "running", "log_path": str(log_path)}


def get_task(task_id: str, *, wait_ms: int = 0) -> dict[str, Any]:
    tid = (task_id or "").strip()
    deadline = time.time() + max(0, wait_ms) / 1000.0
    while True:
        with _lock:
            t = _tasks.get(tid)
            if not t:
                return {"ok": False, "error": f"unknown task_id: {tid}"}
            snap = {k: v for k, v in t.items() if k != "proc"}
        if snap.get("status") != "running" or wait_ms <= 0:
            return {"ok": True, **snap}
        if time.time() >= deadline:
            return {"ok": True, **snap, "waiting": True}
        time.sleep(0.15)


def kill_task(task_id: str) -> dict[str, Any]:
    tid = (task_id or "").strip()
    with _lock:
        t = _tasks.get(tid)
        if not t:
            return {"ok": False, "error": f"unknown task_id: {tid}"}
        proc = t.get("proc")
    if proc is not None:
        try:
            proc.kill()
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e), "task_id": tid}
    with _lock:
        if tid in _tasks:
            _tasks[tid]["status"] = "killed"
            _tasks[tid]["ended"] = time.time()
    return {"ok": True, "task_id": tid, "status": "killed"}


def list_tasks() -> list[dict[str, Any]]:
    with _lock:
        return [
            {k: v for k, v in t.items() if k != "proc"}
            for t in _tasks.values()
        ]
