"""
Grok-style agent harness for AI Agent Studio (GUI retained).

Modules:
  file_tools, permissions, sandbox, plan_mode, project_rules,
  hooks, bg_tasks, git_tools, subagent, agent_todo, ask_user,
  runtime (dispatch + text blocks + OpenAI tool schemas)
"""

from __future__ import annotations

from app.services.agent_harness.runtime import (
    extract_harness_blocks,
    harness_tool_instructions,
    run_harness_from_reply,
    openai_tool_schemas,
    dispatch_named_tool,
    inject_project_context,
)

__all__ = [
    "extract_harness_blocks",
    "harness_tool_instructions",
    "run_harness_from_reply",
    "openai_tool_schemas",
    "dispatch_named_tool",
    "inject_project_context",
]
