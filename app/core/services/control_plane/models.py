"""Data shapes for the control plane (Paperclip-aligned concepts)."""
from __future__ import annotations

from typing import Any

ADAPTER_TYPES = (
    "studio_builtin",
    "process",
    "http",
)

AGENT_STATUSES = ("idle", "running", "paused", "error", "budget_exceeded")
TASK_STATUSES = (
    "backlog",
    "todo",
    "in_progress",
    "blocked",
    "in_review",
    "done",
    "cancelled",
)
COMPANY_STATUSES = ("active", "paused", "archived")


def empty_company(
    *,
    name: str = "AI Company",
    goal: str = "",
    budget_monthly_cents: int = 0,
) -> dict[str, Any]:
    return {
        "id": "",
        "name": name,
        "goal": goal,
        "status": "active",
        "budget_monthly_cents": int(budget_monthly_cents or 0),
        "spent_monthly_cents": 0,
        "require_approval": True,
        "created_at": "",
        "updated_at": "",
    }


def empty_agent(
    *,
    company_id: str,
    name: str,
    title: str = "",
    role: str = "worker",
    reports_to: str = "",
    adapter_type: str = "studio_builtin",
    adapter_config: dict[str, Any] | None = None,
    budget_monthly_cents: int = 0,
    heartbeat_interval_sec: int = 300,
    capabilities: str = "",
) -> dict[str, Any]:
    return {
        "id": "",
        "company_id": company_id,
        "name": name,
        "title": title or name,
        "role": role,
        "reports_to": reports_to or "",
        "status": "idle",
        "adapter_type": adapter_type if adapter_type in ADAPTER_TYPES else "studio_builtin",
        "adapter_config": dict(adapter_config or {}),
        "budget_monthly_cents": int(budget_monthly_cents or 0),
        "spent_monthly_cents": 0,
        "heartbeat_enabled": True,
        "heartbeat_interval_sec": max(30, int(heartbeat_interval_sec or 300)),
        "last_heartbeat_at": "",
        "capabilities": capabilities or "",
        "created_at": "",
        "updated_at": "",
    }


def empty_task(
    *,
    company_id: str,
    title: str,
    description: str = "",
    assignee_id: str = "",
    parent_id: str = "",
    priority: int = 3,
) -> dict[str, Any]:
    return {
        "id": "",
        "company_id": company_id,
        "title": title,
        "description": description or "",
        "status": "todo",
        "assignee_id": assignee_id or "",
        "parent_id": parent_id or "",
        "priority": int(priority),
        "goal_path": [],
        "checkout_by": "",
        "comments": [],
        "created_at": "",
        "updated_at": "",
    }


def empty_run(
    *,
    company_id: str,
    agent_id: str,
    task_id: str = "",
    adapter_type: str = "",
) -> dict[str, Any]:
    return {
        "id": "",
        "company_id": company_id,
        "agent_id": agent_id,
        "task_id": task_id or "",
        "adapter_type": adapter_type or "",
        "status": "running",
        "started_at": "",
        "finished_at": "",
        "cost_cents": 0,
        "log": [],
        "result_summary": "",
        "error": "",
    }
