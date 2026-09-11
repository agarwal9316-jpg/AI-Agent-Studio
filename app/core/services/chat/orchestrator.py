"""
Background AI company orchestrator.

Runs work tasks on a worker thread so the Chat UI stays free.
Supports approval_mode: auto | manual.
"""

from __future__ import annotations

import threading
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Callable

from app.core.services.misc.default_prompts import get_default_system_prompt
from app.core.services.llm.llm import LLMError, chat_completion
from app.core.services.data.storage import load_config


# Lazy imports to break circular dependencies
def _get_company():
    from app.services import company_store
    return company_store


def _get_memory():
    from app.services import memory_store
    return memory_store


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BackgroundOrchestrator:
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._lock = threading.Lock()
        self._listeners: list[Callable[[str], None]] = []
        self._running_task_id: str | None = None
        self._status = "idle"
        self._pipeline_exclusive = False

    def add_listener(self, fn: Callable[[str], None]) -> None:
        self._listeners.append(fn)

    def _emit(self, msg: str) -> None:
        self._status = msg
        try:
            from app.core.services.data.activity_log import log as alog

            alog(msg, source="company")
        except Exception:  # noqa: BLE001
            pass
        for fn in list(self._listeners):
            try:
                fn(msg)
            except Exception:  # noqa: BLE001
                pass

    @property
    def status(self) -> str:
        return self._status

    @property
    def running_task_id(self) -> str | None:
        return self._running_task_id

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        # Orphaned "running" tasks from a previous process look forever busy in Work badge
        try:
            n = _get_company().recover_stale_running_tasks()
            if n:
                self._emit(f"recovered {n} interrupted work task(s)")
        except Exception:  # noqa: BLE001
            pass
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="AI-Company-Worker", daemon=True)
        self._thread.start()
        self._emit("background worker started")

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def kick(self) -> None:
        """Wake worker to pick up queued tasks."""
        self.start()
        self._wake.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception:  # noqa: BLE001
                self._emit(f"worker error: {traceback.format_exc()[:200]}")
            # wait until kick or timeout poll
            self._wake.wait(timeout=3.0)
            self._wake.clear()

    def begin_exclusive_pipeline(self) -> None:
        """Chat org pipeline owns execution; background queue pauses."""
        self._pipeline_exclusive = True
        self._emit("org pipeline exclusive mode ON")

    def end_exclusive_pipeline(self) -> None:
        self._pipeline_exclusive = False
        self._emit("org pipeline exclusive mode OFF")
        self.kick()

    def run_task_now(self, task: dict[str, Any]) -> dict[str, Any]:
        """Run one work task immediately (used by org pipeline)."""
        tid = task.get("id")
        if tid:
            fresh = _get_company().get_work_task(str(tid))
            if fresh:
                task = fresh
        # Resolve blocked deps
        deps = list(task.get("depends_on") or [])
        if deps:
            for did in deps:
                dt = _get_company().get_work_task(str(did))
                st = (dt or {}).get("status")
                if st not in ("done", "cancelled"):
                    task["status"] = "blocked"
                    task.setdefault("log", []).append(
                        {"at": _now(), "msg": f"still blocked on {did} ({st})"}
                    )
                    _get_company().save_work_task(task)
                    return task
            task["depends_on"] = []
        if task.get("status") == "blocked":
            task["status"] = "queued"
        task["auto_approved"] = True
        _get_company().save_work_task(task)
        self._run_task(task)
        return _get_company().get_work_task(str(task.get("id") or "")) or task

    def _unblock_ready_tasks(self) -> None:
        """Promote blocked tasks whose depends_on are all done."""
        for t in _get_company().list_work_tasks():
            if t.get("status") != "blocked":
                continue
            deps = list(t.get("depends_on") or [])
            if not deps:
                t["status"] = "queued"
                _get_company().save_work_task(t)
                continue
            ready = True
            for did in deps:
                dt = _get_company().get_work_task(str(did))
                if not dt or dt.get("status") not in ("done", "cancelled"):
                    ready = False
                    break
            if ready:
                t["status"] = "queued"
                t["depends_on"] = []
                t.setdefault("log", []).append({"at": _now(), "msg": "unblocked — deps done"})
                _get_company().save_work_task(t)

    def _tick(self) -> None:
        if self._pipeline_exclusive:
            self._status = "org-pipeline-exclusive"
            return
        mode = _get_company().get_approval_mode()
        # promote approved tasks
        for ap in _get_company().list_approvals(status="pending"):
            pass  # wait for user
        for ap in _get_company().list_approvals(status="approved"):
            tid = ap.get("task_id")
            if not tid:
                continue
            task = _get_company().get_work_task(tid)
            if task and task.get("status") == "waiting_approval":
                task["status"] = "queued"
                _get_company().save_work_task(task)
            ap["status"] = "consumed"
            _get_company().save_approval(ap)

        self._unblock_ready_tasks()

        # pick next queued task (never blocked)
        queued = [t for t in _get_company().list_work_tasks() if t.get("status") == "queued"]
        if not queued:
            # silent when idle — do not spam activity log
            self._status = "idle"
            return

        # oldest first
        queued.sort(key=lambda t: t.get("created_at") or "")
        task = queued[0]

        # Skip if deps not met (safety)
        deps = list(task.get("depends_on") or [])
        if deps:
            for did in deps:
                dt = _get_company().get_work_task(str(did))
                if not dt or dt.get("status") not in ("done", "cancelled"):
                    task["status"] = "blocked"
                    _get_company().save_work_task(task)
                    return

        if mode == "manual" and not task.get("auto_approved"):
            # first time: request approval instead of running
            if task.get("status") == "queued" and not task.get("approval_requested"):
                task["status"] = "waiting_approval"
                task["approval_requested"] = True
                _get_company().save_work_task(task)
                _get_company().request_approval(
                    task["id"],
                    f"Approve task: {task.get('title')}\n{task.get('description') or ''}",
                )
                self._emit(f"waiting approval: {task.get('title')}")
                return

        self._run_task(task)

    def _run_task(self, task: dict[str, Any]) -> None:
        with self._lock:
            self._running_task_id = task["id"]
        task["status"] = "running"
        task.setdefault("log", []).append({"at": _now(), "msg": "started"})
        _get_company().save_work_task(task)
        self._emit(f"running: {task.get('title')}")

        from app.core.services.data.storage import get_agent, resolve_agent_llm

        # Per-agent LLM (multi-model multi-agent)
        agent_profile = None
        if task.get("agent_id"):
            agent_profile = get_agent(str(task["agent_id"]))
        # Build a pseudo-agent from task overrides if needed
        if agent_profile is None and (
            task.get("llm_model") or task.get("llm_base_url") or task.get("llm_api_key")
        ):
            agent_profile = {
                "llm_model": task.get("llm_model") or "",
                "llm_base_url": task.get("llm_base_url") or "",
                "llm_api_key": task.get("llm_api_key") or "",
                "name": task.get("agent_name") or "",
                "role": task.get("agent_role") or "",
                "goal": task.get("agent_goal") or "",
                "system_prompt": task.get("system_prompt") or "",
                "worker_prompt": task.get("worker_prompt") or "",
                "attachments": task.get("attachments") or [],
                "fallback_enabled": task.get("fallback_enabled") or False,
                "fallback_model": task.get("fallback_model") or "",
                "fallback_base_url": task.get("fallback_base_url") or "",
                "fallback_api_key": task.get("fallback_api_key") or "",
            }
        llm = resolve_agent_llm(agent_profile)
        api_key = llm["api_key"]
        if not api_key:
            task["status"] = "failed"
            task["result"] = (
                "No API key for this agent. Set agent LLM key or global Settings API key."
            )
            task["log"].append({"at": _now(), "msg": "failed: no api key"})
            _get_company().save_work_task(task)
            self._running_task_id = None
            self._emit("failed: no api key")
            return

        # Runtime LLM traceability (no secrets)
        task["runtime_llm"] = {
            "model": llm.get("model"),
            "base_url": llm.get("base_url"),
            "provider_id": llm.get("provider_id") or "",
            "provider_name": llm.get("provider_name") or "",
            "model_source": llm.get("model_source") or "",
            "provider_source": llm.get("provider_source") or "",
            "display_model": llm.get("display_model") or llm.get("model"),
            "display_provider": llm.get("display_provider") or "",
            "is_fallback": False,
            "configured": llm.get("configured") or {},
        }
        task.setdefault("activity", []).append(
            {"at": _now(), "msg": "Received assignment / task started"}
        )
        task.setdefault("activity", []).append(
            {
                "at": _now(),
                "msg": (
                    f"Runtime model: {llm.get('model')} "
                    f"(source={llm.get('model_source')}) "
                    f"provider={llm.get('display_provider')}"
                ),
            }
        )

        roles = {r["id"]: r for r in _get_company().list_roles()}
        role = roles.get(task.get("role_id") or "", {})
        mem = _get_memory().memory_prompt_block(limit=20, project_id=task.get("project_id") or "")

        agent_name = (agent_profile or {}).get("name") or task.get("agent_name") or role.get("title") or "worker"
        agent_role = (agent_profile or {}).get("role") or task.get("agent_role") or ""
        agent_goal = (agent_profile or {}).get("goal") or task.get("agent_goal") or ""
        worker_prompt = (
            (agent_profile or {}).get("worker_prompt")
            or task.get("worker_prompt")
            or (agent_profile or {}).get("backstory")
            or ""
        ).strip()

        # Attachments → text (OCR for non-vision models)
        attachment_text = ""
        att_pack: dict[str, Any] = {}
        try:
            from app.core.services.misc.worker_attachments import (
                process_attachments_for_llm,
                sync_attachment_status_to_agent,
            )

            atts = list(
                task.get("attachments")
                or (agent_profile or {}).get("attachments")
                or []
            )
            if atts:
                att_pack = process_attachments_for_llm(
                    atts,
                    model_id=str(llm.get("model") or ""),
                    provider_id=str(llm.get("provider_id") or ""),
                )
                attachment_text = str(att_pack.get("text") or "")
                task["attachments"] = att_pack.get("items") or atts
                task.setdefault("activity", []).append(
                    {
                        "at": _now(),
                        "msg": (
                            f"Attachments processed: {att_pack.get('attachment_count', 0)} "
                            f"(vision_capable={att_pack.get('vision_capable')})"
                        ),
                    }
                )
                if task.get("agent_id"):
                    try:
                        sync_attachment_status_to_agent(
                            str(task["agent_id"]), list(att_pack.get("items") or [])
                        )
                    except Exception:  # noqa: BLE001
                        pass
        except Exception as e:  # noqa: BLE001
            task.setdefault("activity", []).append(
                {"at": _now(), "msg": f"Attachment processing skipped: {e}"}
            )

        # Prior multi-agent outputs for same goal (handoff) — larger pack for CEO
        prior = ""
        gid = task.get("goal_id") or ""
        is_ceo = str(task.get("role_id") or "") == "ceo" or str(task.get("title") or "").startswith("[CEO]")
        cap = 12000 if is_ceo else 4000
        if gid:
            siblings = _get_company().list_work_tasks(goal_id=gid)
            siblings.sort(key=lambda t: t.get("created_at") or "")
            done_bits = []
            for s in siblings:
                if s.get("id") == task.get("id"):
                    continue
                if s.get("status") == "done" and s.get("result"):
                    # for non-CEO, only earlier tasks; for CEO, all other done agents
                    if not is_ceo and (s.get("created_at") or "") > (task.get("created_at") or ""):
                        continue
                    if is_ceo and (
                        str(s.get("role_id") or "") == "ceo"
                        or str(s.get("title") or "").startswith("[CEO]")
                    ):
                        continue
                    body = str(s.get("result"))
                    if len(body) > cap:
                        body = body[:cap] + "\n…(truncated)"
                    done_bits.append(
                        f"### Prior agent: {s.get('agent_name') or s.get('title')}\n"
                        f"{body}"
                    )
            if done_bits:
                prior = (
                    "\n\n## Prior multi-agent results (use as context — required)\n"
                    + "\n\n".join(done_bits)
                )

        # Prefer per-agent system prompt + permanent worker prompt (never merge temp tasks)
        custom_sp = ((agent_profile or {}).get("system_prompt") or task.get("system_prompt") or "").strip()
        base_sp = custom_sp or get_default_system_prompt()
        system = (
            base_sp
            + "\n\n## You are a multi-agent worker in an org workflow\n"
            + f"Agent name: {agent_name}\n"
            + f"Agent role: {agent_role}\n"
            + f"Agent goal: {agent_goal}\n"
            + f"LLM model for this agent: {llm['model']} @ {llm['base_url']}\n"
            + (f"\n## Worker prompt (permanent role)\n{worker_prompt}\n" if worker_prompt else "")
            + (role.get("system_extra") or "")
            + "\n\n"
            + mem
            + "\n\nYou are running as a BACKGROUND company worker (not interactive chat). "
            "Complete the assigned task. Reply with a clear RESULT section.\n"
            "Include: findings, evidence, assumptions, confidence, limitations, recommendation.\n"
            "If you use tools, ONLY use text blocks like "
            "<<<TERMINAL>>>\\ncommand\\n<<<END_TERMINAL>>> or "
            "<<<WEB_SEARCH>>>\\nquery\\n<<<END_WEB_SEARCH>>> — "
            "never JSON, never <tool_call>, never {\"terminal\":...}."
        )
        # Tool permissions (optional per-worker allow map)
        tool_perm = dict(
            (agent_profile or {}).get("tool_permissions")
            or task.get("tool_permissions")
            or {}
        )
        enable_terminal = tool_perm.get("terminal", True) is not False
        enable_web = tool_perm.get("web", True) is not False

        assignment_body = (
            task.get("task")
            or task.get("description")
            or task.get("title")
            or ""
        )
        user = (
            f"Task title: {task.get('title')}\n"
            f"Assignment: {assignment_body}\n"
            f"Expected outcome: {task.get('expected_outcome') or 'Clear findings with evidence'}\n"
            f"Description: {task.get('description')}\n"
            f"Goal id: {task.get('goal_id')}\n"
            f"{prior}\n"
        )
        if attachment_text:
            user += f"\n## ATTACHMENTS (processed for this model)\n{attachment_text}\n"
        user += "\nProduce a useful completion summary and any concrete outputs."

        task["effective_context"] = {
            "system_instructions_set": bool(custom_sp),
            "worker_prompt_set": bool(worker_prompt),
            "has_prior_results": bool(prior),
            "has_attachments": bool(attachment_text),
            "attachment_warnings": list((att_pack or {}).get("warnings") or []),
            "vision_capable": bool((att_pack or {}).get("vision_capable")),
            "tools": {"terminal": enable_terminal, "web": enable_web},
        }
        task.setdefault("activity", []).append({"at": _now(), "msg": "Context assembled"})

        from app.services import agent_tracker

        run_id = agent_tracker.start_run(
            agent_name=agent_name,
            agent_role=agent_role,
            agent_id=str(task.get("agent_id") or ""),
            task_title=str(task.get("title") or ""),
            task_id=str(task.get("id") or ""),
            goal_id=str(task.get("goal_id") or ""),
            model=llm["model"],
            input_text=user,
            source="company",
        )
        try:
            task["log"].append(
                {
                    "at": _now(),
                    "msg": f"llm={llm['model']} base={llm['base_url']} agent={agent_name}",
                }
            )
            task["tracker_run_id"] = run_id
            _get_company().save_work_task(task)
            # CEO synthesis: plain LLM (short timeout). Workers: tool loop.
            used_fallback = False
            primary_err = ""

            def _run_primary() -> tuple[str, int, int, list]:
                if is_ceo:
                    text = chat_completion(
                        api_key=api_key,
                        messages=[
                            {
                                "role": "system",
                                "content": (
                                    system
                                    + "\n\nYou are CEO. Write the final answer for the user now. "
                                    "No tool blocks. Be concrete and complete. "
                                    "Distinguish confirmed findings, assumptions, gaps, recommendations."
                                ),
                            },
                            {"role": "user", "content": user},
                        ],
                        model=llm["model"],
                        base_url=llm["base_url"],
                        timeout=90.0,
                        max_tokens=2500,
                    )
                    return str(text or ""), 0, 1, []
                from app.core.services.company.team_agent_tools import run_tool_agent

                tool_res = run_tool_agent(
                    user_brief=user
                    + "\n\nComplete this task. Use TERMINAL / WEB_SEARCH / WEB_FETCH when needed. "
                    "End with a clear RESULT (no raw tool blocks).",
                    agent_name=str(agent_name),
                    agent_role=str(agent_role),
                    department=str(role.get("title") or "Team"),
                    goal=str(agent_goal or task.get("title") or ""),
                    agent_id=str(task.get("agent_id") or ""),
                    max_tool_rounds=4,
                    on_progress=lambda m: self._emit(m),
                    enable_terminal=enable_terminal,
                    enable_web=enable_web,
                )
                text = str(tool_res.get("text") or "").strip()
                tlog = list(tool_res.get("tool_log") or [])
                if tlog:
                    text = (
                        (text or "(no text)")
                        + "\n\n### Tools used\n"
                        + "\n".join(f"- {x}" for x in tlog[:24])
                    )
                if not text and tool_res.get("error"):
                    raise LLMError(str(tool_res.get("error")))
                if not text:
                    text = chat_completion(
                        api_key=api_key,
                        messages=[
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        model=llm["model"],
                        base_url=llm["base_url"],
                        timeout=120.0,
                    )
                return (
                    str(text or ""),
                    len(tlog),
                    int(tool_res.get("rounds") or 0),
                    tlog,
                )

            try:
                reply, tool_n, tool_rounds, tool_log = _run_primary()
            except Exception as primary_ex:  # noqa: BLE001
                primary_err = str(primary_ex)
                fb_on = bool((agent_profile or {}).get("fallback_enabled"))
                if not fb_on:
                    raise
                # Explicit fallback only
                fb_llm = resolve_agent_llm(agent_profile, use_fallback=True)
                if not fb_llm.get("api_key") and not fb_llm.get("model"):
                    raise
                task.setdefault("activity", []).append(
                    {
                        "at": _now(),
                        "msg": (
                            f"Primary failed: {llm.get('model')} — {primary_err[:200]}. "
                            f"Fallback used: {fb_llm.get('model')}"
                        ),
                    }
                )
                self._emit(
                    f"fallback: primary {llm.get('model')} failed → {fb_llm.get('model')}"
                )
                api_key = fb_llm["api_key"] or api_key
                llm = fb_llm
                used_fallback = True
                task["runtime_llm"] = {
                    "model": llm.get("model"),
                    "base_url": llm.get("base_url"),
                    "provider_id": llm.get("provider_id") or "",
                    "model_source": "fallback",
                    "is_fallback": True,
                    "primary_failed": primary_err[:500],
                    "primary_model": task.get("runtime_llm", {}).get("model"),
                    "display_model": f"Fallback — {llm.get('model')}",
                }
                reply, tool_n, tool_rounds, tool_log = _run_primary()

            task["tool_calls"] = [
                {"action": str(x), "status": "completed"} for x in (tool_log or [])[:40]
            ]
            if used_fallback:
                task.setdefault("activity", []).append(
                    {
                        "at": _now(),
                        "msg": f"Completed with fallback model {llm.get('model')}",
                    }
                )
            task["status"] = "done"
            task["result"] = reply
            task["returned_to"] = task.get("assigned_by") or "manager/ceo"
            task["completed_at"] = _now()
            task.setdefault("activity", []).append(
                {"at": _now(), "msg": "Report prepared and returned upward"}
            )
            task["log"].append(
                {
                    "at": _now(),
                    "msg": (
                        f"done tools={tool_n} rounds={tool_rounds} ceo={is_ceo}"
                        f"{' fallback=1' if used_fallback else ''}"
                    ),
                }
            )
            # Structured artifacts
            try:
                from app.services import org_execution as org_ex

                org_ex.enrich_task_after_run(
                    task,
                    runtime_llm=task.get("runtime_llm"),
                    tool_calls=task.get("tool_calls"),
                )
            except Exception:  # noqa: BLE001
                pass
            agent_tracker.finish_run(run_id, output=reply, status="done")
            # auto memory snippet
            _get_memory().add_item(
                f"Task done [{task.get('title')}]: {reply[:400]}",
                tags=["company", "task"],
                project_id=task.get("project_id") or "",
                source="background",
            )
            # Save agent result into project outputs folder
            try:
                from app.services import project_outputs

                project_outputs.save_result(
                    reply or "",
                    title=str(task.get("title") or "task"),
                    agent_name=agent_name,
                    project_id=str(task.get("project_id") or ""),
                    source="company",
                )
            except Exception:  # noqa: BLE001
                pass
            # if goal: mark running/done heuristically
            gid = task.get("goal_id")
            if gid:
                goal = _get_company().get_goal(gid)
                if goal:
                    siblings = _get_company().list_work_tasks(goal_id=gid)
                    if all(s.get("status") in ("done", "cancelled") for s in siblings):
                        goal["status"] = "done"
                    else:
                        goal["status"] = "running"
                    _get_company().save_goal(goal)
            self._emit(f"done: {task.get('title')} by {agent_name}")
        except LLMError as e:
            task["status"] = "failed"
            task["result"] = str(e)
            task["log"].append({"at": _now(), "msg": f"failed: {e}"})
            agent_tracker.finish_run(run_id, error=str(e), status="failed")
            self._emit(f"failed: {e}")
        except Exception as e:  # noqa: BLE001
            task["status"] = "failed"
            task["result"] = str(e)
            task["log"].append({"at": _now(), "msg": f"error: {e}"})
            agent_tracker.finish_run(run_id, error=str(e), status="failed")
            self._emit(f"error: {e}")

        _get_company().save_work_task(task)
        self._running_task_id = None

    def ceo_create_plan(self, goal_id: str) -> dict[str, Any]:
        """CEO: expand active org tree into agent tasks + blocked CEO synthesis."""
        from app.services import workflow_graph as wfg

        goal = _get_company().get_goal(goal_id)
        if not goal:
            return {"ok": False, "error": "goal not found"}
        goal["status"] = "running"
        _get_company().save_goal(goal)
        objective = f"{goal.get('title') or ''}\n{goal.get('description') or ''}".strip()
        created = wfg.expand_to_company_tasks(
            objective or str(goal.get("title") or "Goal"),
            goal_id=goal_id,
            project_id=goal.get("project_id") or "",
            force_auto_approve=_get_company().get_approval_mode() == "auto",
        )
        # For background queue: agents queued, CEO blocked until deps done
        for t in created:
            if t.get("status") == "blocked":
                continue
            if _get_company().get_approval_mode() == "auto":
                t["auto_approved"] = True
                t["status"] = "queued"
                _get_company().save_work_task(t)
        self.kick()
        return {
            "ok": True,
            "task_ids": [t.get("id") for t in created],
            "count": len(created),
            "source": "org_tree",
        }

    def approve(self, approval_id: str) -> None:
        ap = _get_company().get_approval(approval_id)
        if not ap:
            return
        ap["status"] = "approved"
        _get_company().save_approval(ap)
        self.kick()

    def reject(self, approval_id: str) -> None:
        ap = _get_company().get_approval(approval_id)
        if not ap:
            return
        ap["status"] = "rejected"
        _get_company().save_approval(ap)
        tid = ap.get("task_id")
        if tid:
            task = _get_company().get_work_task(tid)
            if task:
                task["status"] = "cancelled"
                _get_company().save_work_task(task)
        self.kick()


_orch: BackgroundOrchestrator | None = None


def get_orchestrator() -> BackgroundOrchestrator:
    global _orch
    if _orch is None:
        _orch = BackgroundOrchestrator()
        _orch.start()
    return _orch
