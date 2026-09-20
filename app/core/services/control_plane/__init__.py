"""Paperclip-inspired control plane for AI Agent Studio.

Control plane orchestrates companies, org agents, tasks, budgets, heartbeats,
approvals, and adapters. Execution happens via adapters — same split as Paperclip.

Public API:
  from app.core.services.control_plane import service as cp
  cp.ensure_default_company()
  cp.list_agents(company_id)
  cp.tick_heartbeats()
"""
from __future__ import annotations

from app.core.services.control_plane import service

__all__ = ["service"]
