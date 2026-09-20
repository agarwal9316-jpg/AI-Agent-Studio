"""Paperclip-inspired control plane for AI Agent Studio.

Control plane (this package) orchestrates companies, org agents, tasks,
budgets, and heartbeats. Execution happens via adapters (Studio builtin chat,
process, HTTP) — same split as Paperclip: orchestrate, don't mandate one runtime.

Public API:
  from app.core.services.control_plane import service as cp
  cp.ensure_default_company()
  cp.list_agents(company_id)
  cp.tick_heartbeats()
"""
from __future__ import annotations

from app.core.services.control_plane import service

__all__ = ["service"]
