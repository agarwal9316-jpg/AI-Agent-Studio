"""Data models for the control plane (JSON-serializable dicts)."""
from __future__ import annotations

from typing import Any, TypedDict


class Company(TypedDict, total=False):
    id: str
    name: str
    goal: str
    status: str  # active | paused | archived
    budget_monthly_cents: int
    spent_monthly_cents: int
    require_approval: bool
    created_at: str
    updated_at: str


class Agent(TypedDict, total=False):
    id: str
    company_id: str
    name: str
    title: str
    role: str  # worker | manager | board
    reports_to: str
    status: str  # active | paused | terminated
    adapter_type: str  # studio_builtin | process | http
    adapter_config: dict[str, Any]
    budget_monthly_cents: int
    spent_monthly_cents: int
    heartbeat_interval_sec: int
    last_heartbeat_at: str
    capabilities: str
    require_approval: bool
    created_at: str
    updated_at: str


class Task(TypedDict, total=False):
    id: str
    company_id: str
    agent_id: str
    title: str
    description: str
    status: str  # backlog | ready | in_progress | blocked | done | cancelled
    priority: int
    blockers: list[str]
    comments: list[dict[str, Any]]
    created_at: str
    updated_at: str


class Run(TypedDict, total=False):
    id: str
    company_id: str
    agent_id: str
    task_id: str
    status: str  # running | succeeded | failed | cancelled
    started_at: str
    finished_at: str
    cost_cents: int
    summary: str
    logs: list[str]


class Approval(TypedDict, total=False):
    id: str
    company_id: str
    agent_id: str
    kind: str  # strategy | spend | tool | hire
    title: str
    detail: str
    status: str  # pending | approved | rejected
    created_at: str
    resolved_at: str
    resolved_by: str
