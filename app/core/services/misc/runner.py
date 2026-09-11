"""Sequential task runner — mock or real OpenAI-compatible LLM."""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from app.services import storage
from app.core.services.llm.llm import LLMError, chat_completion


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tasks_for_run(task_ids: list[str] | None) -> list[dict[str, Any]]:
    tasks = storage.list_tasks()
    if task_ids:
        idset = set(task_ids)
        tasks = [t for t in tasks if t.get("id") in idset]
    if not tasks:
        tasks = [
            {
                "id": "demo",
                "name": "Demo task",
                "description": "Demo run (no tasks saved yet)",
                "expected_output": "Confirmation log",
                "agent_id": "",
            }
        ]
    return tasks


def run_mock(
    task_ids: list[str] | None = None,
    on_line: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Run a mock sequential pipeline; emit log lines via on_line."""

    def log(msg: str) -> None:
        if on_line:
            on_line(msg)

    tasks = _tasks_for_run(task_ids)
    run: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "mode": "mock",
        "status": "running",
        "messages": [],
        "task_ids": [t.get("id") for t in tasks],
        "started_at": _now(),
    }
    storage.save_run(run)

    def add(role: str, content: str) -> None:
        run["messages"].append({"role": role, "content": content, "at": _now()})
        log(f"[{role}] {content}")

    add("system", "Mock run started.")
    for i, task in enumerate(tasks, start=1):
        agent = (
            storage.get_agent(task.get("agent_id") or "") if task.get("agent_id") else None
        )
        agent_name = (agent or {}).get("name") or (agent or {}).get("role") or "Unassigned"
        add(
            "system",
            f"Task {i}/{len(tasks)}: {task.get('name') or task.get('description', '')[:60]}",
        )
        add(agent_name, f"Working on: {task.get('description', '')}")
        time.sleep(0.05)
        expected = task.get("expected_output") or "done"
        add(agent_name, f"Completed. Expected output met: {expected}")

    run["status"] = "success"
    run["finished_at"] = _now()
    storage.save_run(run)
    add("system", "Mock run finished successfully.")
    return run


def run_llm(
    task_ids: list[str] | None = None,
    on_line: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Sequential multi-task run using OpenAI-compatible API when key is set."""

    def log(msg: str) -> None:
        if on_line:
            on_line(msg)

    cfg = storage.load_config()
    api_key = (cfg.get("api_key") or "").strip()
    if not api_key:
        log("[system] No API key — falling back to mock run.")
        return run_mock(task_ids=task_ids, on_line=on_line)

    tasks = _tasks_for_run(task_ids)
    base_url = (cfg.get("api_base_url") or "https://api.openai.com/v1").strip()
    model = (cfg.get("model") or "gpt-4o-mini").strip()

    run: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "mode": "llm",
        "status": "running",
        "messages": [],
        "task_ids": [t.get("id") for t in tasks],
        "model": model,
        "started_at": _now(),
    }
    storage.save_run(run)

    def add(role: str, content: str) -> None:
        run["messages"].append({"role": role, "content": content, "at": _now()})
        log(f"[{role}] {content}")

    add("system", f"LLM run started (model={model}).")
    prior_context: list[str] = []

    try:
        for i, task in enumerate(tasks, start=1):
            agent = (
                storage.get_agent(task.get("agent_id") or "")
                if task.get("agent_id")
                else None
            )
            agent_name = (
                (agent or {}).get("name")
                or (agent or {}).get("role")
                or "Assistant"
            )
            role = (agent or {}).get("role") or agent_name
            goal = (agent or {}).get("goal") or "Complete the assigned task carefully."
            backstory = (agent or {}).get("backstory") or ""

            add(
                "system",
                f"Task {i}/{len(tasks)}: {task.get('name') or task.get('description', '')[:60]}",
            )

            system_parts = [
                f"You are an agent named {agent_name}.",
                f"Role: {role}",
                f"Goal: {goal}",
            ]
            if backstory:
                system_parts.append(f"Backstory: {backstory}")
            system_parts.append(
                "Respond with a clear, complete answer for this single task only."
            )

            user_parts = [
                f"Task: {task.get('name') or ''}",
                f"Description: {task.get('description') or ''}",
                f"Expected output: {task.get('expected_output') or 'Useful result'}",
            ]
            if prior_context:
                user_parts.append(
                    "Context from previous tasks:\n" + "\n---\n".join(prior_context[-3:])
                )

            messages = [
                {"role": "system", "content": "\n".join(system_parts)},
                {"role": "user", "content": "\n".join(user_parts)},
            ]
            add(agent_name, "Calling LLM…")
            reply = chat_completion(
                api_key=api_key,
                messages=messages,
                model=model,
                base_url=base_url,
            )
            add(agent_name, reply)
            prior_context.append(
                f"Task {i} ({task.get('name')}): {reply[:2000]}"
            )

        run["status"] = "success"
        add("system", "LLM run finished successfully.")
    except LLMError as e:
        run["status"] = "failed"
        add("system", f"LLM run failed: {e}")
    except Exception as e:  # noqa: BLE001
        run["status"] = "failed"
        add("system", f"Unexpected error: {e}")

    run["finished_at"] = _now()
    storage.save_run(run)
    return run


def run_pipeline(
    *,
    use_llm: bool = False,
    task_ids: list[str] | None = None,
    on_line: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Entry used by the GUI."""
    if use_llm:
        return run_llm(task_ids=task_ids, on_line=on_line)
    return run_mock(task_ids=task_ids, on_line=on_line)
