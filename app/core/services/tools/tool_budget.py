"""Per-agent / per-run tool budgets so workers cannot runaway."""

from __future__ import annotations

import threading
from typing import Any

from app.core.services.data.storage import load_config, save_config

# re-export for callers

_lock = threading.Lock()
# run_id -> {tool_type: count}
_usage: dict[str, dict[str, int]] = {}

DEFAULT_BUDGETS: dict[str, int] = {
    "terminal": 20,
    "gui": 40,
    "screenshot": 15,
    "clipboard": 20,
    "windows": 20,
    "mcp": 30,
    "skill": 25,
    "pip": 5,
    "org": 20,
    "browser": 15,
    "self_improve": 10,
    "llm_round": 12,
    # Task #14: parallel agents
    "subagent": 8,  # max subagent spawns per parent run
    "parallel_batch": 4,  # max agents in one parallel fan-out
}

# Soft global caps (config override)
DEFAULT_PARALLEL: dict[str, int | float] = {
    "max_concurrent_subagents": 4,  # simultaneous running
    "max_subagents_per_run": 8,  # total spawns per parent run_id
    "max_parallel_batch": 4,  # size of one parallel panel
    "subagent_timeout_sec": 180,  # wall clock per subagent
    "parallel_timeout_sec": 300,  # wall clock for whole parallel batch
}


def get_budgets() -> dict[str, int]:
    cfg = load_config()
    stored = cfg.get("tool_budgets") or {}
    out = dict(DEFAULT_BUDGETS)
    if isinstance(stored, dict):
        for k, v in stored.items():
            try:
                out[str(k)] = max(0, int(v))
            except (TypeError, ValueError):
                pass
    return out


def set_budgets(budgets: dict[str, int]) -> dict[str, int]:
    cfg = load_config()
    merged = get_budgets()
    for k, v in (budgets or {}).items():
        try:
            merged[str(k)] = max(0, int(v))
        except (TypeError, ValueError):
            pass
    cfg["tool_budgets"] = merged
    save_config(cfg)
    return merged


def begin_run(run_id: str) -> None:
    with _lock:
        _usage[run_id] = {}


def end_run(run_id: str) -> None:
    with _lock:
        _usage.pop(run_id, None)


def get_usage(run_id: str) -> dict[str, int]:
    with _lock:
        return dict(_usage.get(run_id) or {})


def check_and_consume(run_id: str, tool: str, n: int = 1) -> tuple[bool, str]:
    """
    Returns (allowed, message). If over budget, allowed=False.
    """
    tool = (tool or "other").lower()
    budgets = get_budgets()
    limit = int(budgets.get(tool, budgets.get("terminal", 20)))
    with _lock:
        bucket = _usage.setdefault(run_id or "_default", {})
        used = int(bucket.get(tool) or 0)
        if used + n > limit:
            return (
                False,
                f"Tool budget exceeded for '{tool}': used {used}/{limit}. "
                f"Raise limits in Settings → Tool budgets.",
            )
        bucket[tool] = used + n
        return True, f"{tool} {bucket[tool]}/{limit}"


def format_budgets_help() -> str:
    lines = ["## Tool budgets (per chat/agent run)", ""]
    for k, v in sorted(get_budgets().items()):
        lines.append(f"- {k}: max {v} calls")
    lines.append("")
    p = get_parallel_caps()
    lines.append("## Parallel agents (Task #14)")
    lines.append(f"- max concurrent subagents: {p['max_concurrent_subagents']}")
    lines.append(f"- max subagents per parent run: {p['max_subagents_per_run']}")
    lines.append(f"- max parallel batch size: {p['max_parallel_batch']}")
    lines.append(f"- per-subagent timeout: {p['subagent_timeout_sec']}s")
    lines.append(f"- parallel batch timeout: {p['parallel_timeout_sec']}s")
    lines.append("")
    lines.append("When a budget is hit, the tool is skipped and the model is told.")
    return "\n".join(lines)


def get_parallel_caps() -> dict[str, int | float]:
    """Task #14 caps for parallel / subagent runs."""
    cfg = load_config()
    stored = cfg.get("parallel_agent_caps") or {}
    out: dict[str, int | float] = dict(DEFAULT_PARALLEL)
    if isinstance(stored, dict):
        for k, v in stored.items():
            if k not in out:
                continue
            try:
                if "timeout" in k or k.endswith("_sec"):
                    out[k] = max(10.0, float(v))
                else:
                    out[k] = max(1, int(v))
            except (TypeError, ValueError):
                pass
    # Keep in sync with tool_budgets aliases when present
    budgets = get_budgets()
    if "subagent" in budgets:
        out["max_subagents_per_run"] = max(1, int(budgets["subagent"]))
    if "parallel_batch" in budgets:
        out["max_parallel_batch"] = max(1, int(budgets["parallel_batch"]))
    return out


def set_parallel_caps(caps: dict[str, Any]) -> dict[str, int | float]:
    cfg = load_config()
    merged = get_parallel_caps()
    for k, v in (caps or {}).items():
        if k not in DEFAULT_PARALLEL:
            continue
        try:
            if "timeout" in k or str(k).endswith("_sec"):
                merged[k] = max(10.0, float(v))
            else:
                merged[k] = max(1, int(v))
        except (TypeError, ValueError):
            pass
    cfg["parallel_agent_caps"] = merged
    # Mirror key tool budgets
    tb = get_budgets()
    tb["subagent"] = int(merged["max_subagents_per_run"])
    tb["parallel_batch"] = int(merged["max_parallel_batch"])
    cfg["tool_budgets"] = tb
    save_config(cfg)
    return merged
