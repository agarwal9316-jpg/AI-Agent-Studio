"""Mission Control: unified ops events + hardware/process snapshots."""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.paths import ops_dir
from app.core.services.data.storage import _read_json, _write_json

_lock = threading.Lock()
MAX_EVENTS = 5000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def events_path() -> Path:
    return ops_dir() / "events.jsonl"


def snapshot_path() -> Path:
    return ops_dir() / "last_snapshot.json"


def log_event(
    kind: str,
    message: str,
    *,
    source: str = "app",
    level: str = "info",
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append a structured ops event (thread-safe)."""
    ev = {
        "id": f"{int(time.time() * 1000):x}",
        "at": _now(),
        "kind": (kind or "event").strip()[:64],
        "level": (level or "info").strip()[:16],
        "source": (source or "app").strip()[:64],
        "message": (message or "")[:2000],
        "meta": meta or {},
    }
    line = json.dumps(ev, ensure_ascii=False) + "\n"
    with _lock:
        path = events_path()
        try:
            with path.open("a", encoding="utf-8") as f:
                f.write(line)
        except Exception:  # noqa: BLE001
            pass
        # trim file if huge
        try:
            if path.exists() and path.stat().st_size > 8_000_000:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
                keep = lines[-MAX_EVENTS:]
                path.write_text("\n".join(keep) + "\n", encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    return ev


def list_events(*, limit: int = 200, kind: str = "", source: str = "") -> list[dict[str, Any]]:
    path = events_path()
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:  # noqa: BLE001
        return []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if kind and str(ev.get("kind") or "") != kind:
            continue
        if source and str(ev.get("source") or "") != source:
            continue
        out.append(ev)
        if len(out) >= limit:
            break
    return out


def hardware_snapshot() -> dict[str, Any]:
    """Best-effort CPU/RAM/GPU/Disk/Network/Process snapshot for Mission Control."""
    snap: dict[str, Any] = {
        "at": _now(), 
        "cpu_percent": None, 
        "ram": {}, 
        "gpu": [], 
        "disk": {}, 
        "net": {}, 
        "process": {}
    }
    try:
        import psutil  # type: ignore

        snap["cpu_percent"] = psutil.cpu_percent(interval=0.05)
        vm = psutil.virtual_memory()
        snap["ram"] = {
            "total_gb": round(vm.total / (1024**3), 2),
            "used_gb": round(vm.used / (1024**3), 2),
            "percent": vm.percent,
        }

        # Disk I/O counters
        dio = psutil.disk_io_counters()
        if dio:
            snap["disk"] = {
                "read_mb": round(dio.read_bytes / (1024**2), 1),
                "write_mb": round(dio.write_bytes / (1024**2), 1),
                "read_count": dio.read_count,
                "write_count": dio.write_count,
            }

        # Network I/O counters
        nio = psutil.net_io_counters()
        if nio:
            snap["net"] = {
                "sent_mb": round(nio.bytes_sent / (1024**2), 1),
                "recv_mb": round(nio.bytes_recv / (1024**2), 1),
                "packets_sent": nio.packets_sent,
                "packets_recv": nio.packets_recv,
                "errin": nio.errin,
                "errout": nio.errout,
            }

        # Current process stats
        try:
            p = psutil.Process()
            snap["process"] = {
                "cpu_percent": p.cpu_percent(),
                "mem_mb": round(p.memory_info().rss / (1024**2), 1),
                "threads": p.num_threads(),
                "fds": p.num_fds() if hasattr(p, "num_fds") else 0,
            }
        except Exception:
            pass

    except Exception:  # noqa: BLE001
        try:
            import os

            snap["cpu_count"] = os.cpu_count()
        except Exception:  # noqa: BLE001
            pass

    # nvidia-smi if present
    try:
        import subprocess

        r = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=3,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if r.returncode == 0 and r.stdout.strip():
            for line in r.stdout.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 4:
                    snap["gpu"].append(
                        {
                            "name": parts[0],
                            "util_percent": float(parts[1] or 0),
                            "mem_used_mb": float(parts[2] or 0),
                            "mem_total_mb": float(parts[3] or 0),
                        }
                    )
    except Exception:  # noqa: BLE001
        pass

    try:
        _write_json(snapshot_path(), snap)
    except Exception:  # noqa: BLE001
        pass
    return snap


def mission_summary() -> dict[str, Any]:
    """Aggregate for Monitor page header."""
    from app.core.services.data.usage_meter import get_summary

    usage = {}
    try:
        usage = get_summary()
    except Exception:  # noqa: BLE001
        usage = {}

    train_jobs = []
    try:
        from app.core.services.ai.train_lab import list_jobs

        train_jobs = list_jobs(limit=5)
    except Exception:  # noqa: BLE001
        pass

    team_n = 0
    try:
        from app.core.services.company.team_channel import list_channels

        team_n = len(list_channels(limit=20))
    except Exception:  # noqa: BLE001
        pass

    profiles_n = 0
    try:
        from app.core.services.llm.model_profiles import list_profiles

        profiles_n = len(list_profiles())
    except Exception:  # noqa: BLE001
        pass

    hw = hardware_snapshot()
    recent = list_events(limit=30)
    return {
        "at": _now(),
        "usage": usage,
        "hardware": hw,
        "recent_events": recent,
        "train_jobs": train_jobs,
        "team_channels": team_n,
        "model_profiles": profiles_n,
        "alerts": _derive_alerts(hw, usage, recent),
    }


def _derive_alerts(
    hw: dict[str, Any], usage: dict[str, Any], recent: list[dict[str, Any]]
) -> list[str]:
    alerts: list[str] = []
    ram = hw.get("ram") or {}
    if float(ram.get("percent") or 0) > 90:
        alerts.append(f"High RAM: {ram.get('percent')}%")
    for g in hw.get("gpu") or []:
        if float(g.get("util_percent") or 0) > 95:
            alerts.append(f"GPU busy: {g.get('name')}")
        tot = float(g.get("mem_total_mb") or 1)
        used = float(g.get("mem_used_mb") or 0)
        if tot > 0 and used / tot > 0.92:
            alerts.append(f"GPU VRAM high: {g.get('name')}")
    err_n = sum(1 for e in recent if e.get("level") in ("error", "err", "fail"))
    if err_n >= 3:
        alerts.append(f"{err_n} recent errors in ops log")
    return alerts
