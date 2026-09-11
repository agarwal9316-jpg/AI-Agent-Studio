"""
AI Organisation execution helpers.

Structured reports, gap analysis, objective completeness, conflict detection,
and worker inspector payloads — without fabricating chain-of-thought.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Callable


def _get_company():
    """Lazy import to break circular dependency."""
    from app.services import company_store as company
    return company


def _get_wfg():
    """Lazy import to break circular dependency."""
    from app.services import workflow_graph as wfg
    return wfg


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_worker_system_message(
    node: dict[str, Any],
    agent: dict[str, Any] | None = None,
) -> str:
    """Permanent system + worker prompts only (no temporary assignments)."""
    ag = agent or {}
    parts: list[str] = []
    sys_p = (ag.get("system_prompt") or node.get("system_prompt") or "").strip()
    work_p = (
        ag.get("worker_prompt")
        or node.get("worker_prompt")
        or node.get("instructions")
        or ag.get("backstory")
        or ""
    ).strip()
    role = ag.get("role") or node.get("agent_role") or node.get("title") or "AI Worker"
    if sys_p:
        parts.append(sys_p)
    else:
        parts.append(f"You are {role} in a hierarchical AI organisation.")
    if work_p:
        parts.append(f"## Worker role (permanent)\n{work_p}")
    parts.append(
        "Report structured findings with evidence, assumptions, confidence, "
        "and unresolved issues. Do not invent tool results."
    )
    return "\n\n".join(parts)


def build_assignment_user_message(
    *,
    objective: str,
    goal: str = "",
    assignment: str = "",
    expected_outcome: str = "",
    requirements: list[str] | None = None,
    constraints: list[str] | None = None,
    parent_context: str = "",
    prior_results: str = "",
    attachment_text: str = "",
) -> str:
    """Temporary task content — never written into worker_prompt."""
    lines = [
        "## OBJECTIVE (user)",
        objective or "(none)",
        "",
        "## GOAL",
        goal or "(inherited from objective)",
        "",
        "## ASSIGNMENT",
        assignment or objective,
        "",
        "## EXPECTED OUTCOME",
        expected_outcome or "Clear findings with evidence suitable for manager review.",
    ]
    if requirements:
        lines += ["", "## REQUIREMENTS", *[f"- {r}" for r in requirements]]
    if constraints:
        lines += ["", "## CONSTRAINTS", *[f"- {c}" for c in constraints]]
    if parent_context:
        lines += ["", "## PARENT / MANAGER CONTEXT", parent_context[:8000]]
    if prior_results:
        lines += ["", "## RELEVANT PRIOR RESULTS", prior_results[:12000]]
    if attachment_text:
        lines += ["", "## ATTACHMENT TEXT (extracted)", attachment_text[:12000]]
    lines += [
        "",
        "## OUTPUT FORMAT",
        "Return a structured report with:",
        "- Summary",
        "- Key findings (with evidence)",
        "- Assumptions",
        "- Limitations / unresolved issues",
        "- Confidence (low/medium/high)",
        "- Recommendation / next action",
        "- Self-evaluation: did you complete the assignment?",
    ]
    return "\n".join(lines)


def parse_structured_report(text: str) -> dict[str, Any]:
    """Best-effort parse of worker report into structured artifacts (no CoT)."""
    body = (text or "").strip()
    out: dict[str, Any] = {
        "summary": "",
        "findings": [],
        "assumptions": [],
        "limitations": [],
        "confidence": "",
        "recommendation": "",
        "self_evaluation": {},
        "raw": body,
    }
    if not body:
        return out

    # Try JSON block first
    m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", body)
    if m:
        try:
            data = json.loads(m.group(1))
            if isinstance(data, dict):
                out["summary"] = str(data.get("summary") or data.get("result") or "")[:4000]
                for key, dest in (
                    ("findings", "findings"),
                    ("key_findings", "findings"),
                    ("assumptions", "assumptions"),
                    ("limitations", "limitations"),
                    ("issues", "limitations"),
                ):
                    val = data.get(key)
                    if isinstance(val, list):
                        out[dest] = [str(x) for x in val][:40]
                    elif isinstance(val, str) and val.strip():
                        out[dest] = [val.strip()]
                out["confidence"] = str(data.get("confidence") or "")[:40]
                out["recommendation"] = str(
                    data.get("recommendation") or data.get("next_action") or ""
                )[:2000]
                se = data.get("self_evaluation") or data.get("self_eval")
                if isinstance(se, dict):
                    out["self_evaluation"] = se
                return out
        except Exception:  # noqa: BLE001
            pass

    # Heuristic sections
    out["summary"] = body[:1500]
    conf = re.search(r"confidence\s*[:\-]\s*(low|medium|high|\d+%?)", body, re.I)
    if conf:
        out["confidence"] = conf.group(1)
    return out


def build_self_evaluation(
    assignment: str,
    result_text: str,
    structured: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Advisory self-evaluation object (manager must still review)."""
    st = structured or parse_structured_report(result_text)
    completed = bool((result_text or "").strip()) and len((result_text or "").strip()) > 40
    return {
        "assignment": assignment,
        "completed": completed,
        "requirements_note": "See report for requirement coverage",
        "known_limitations": st.get("limitations") or [],
        "confidence": st.get("confidence") or "unspecified",
        "needs_additional_work": bool(st.get("limitations")),
        "recommended_next_step": st.get("recommendation") or "",
        "advisory": True,
    }


def gap_analysis(
    objective: str,
    agent_results: list[dict[str, Any]],
    *,
    final_text: str = "",
) -> dict[str, Any]:
    """
    Determine known / unknown / contradictory / incomplete after subordinate results.
    Does not invent facts — only inspects provided outputs.
    """
    known: list[str] = []
    unknown: list[str] = []
    uncertain: list[str] = []
    contradictory: list[str] = []
    incomplete: list[str] = []
    failed: list[str] = []

    bodies: list[tuple[str, str]] = []
    for a in agent_results:
        name = str(a.get("agent_name") or a.get("title") or "Worker")
        status = str(a.get("status") or "")
        body = str(a.get("result") or "").strip()
        if status == "failed" or not body:
            failed.append(name)
            incomplete.append(f"{name}: no usable result")
            continue
        known.append(f"{name}: produced {len(body)} chars")
        bodies.append((name, body))
        low = body.lower()
        if any(x in low for x in ("unknown", "unclear", "not enough", "cannot determine", "missing")):
            uncertain.append(f"{name}: report signals uncertainty")
        if any(x in low for x in ("limitation", "unresolved", "incomplete", "partial")):
            incomplete.append(f"{name}: report signals incompleteness")

    # Simple numeric/market-size conflict heuristic
    nums: list[tuple[str, str]] = []
    for name, body in bodies:
        for m in re.finditer(
            r"(market size|estimate|total)\s*[:=]?\s*([\$€]?\d[\d,\.]*\s*(?:billion|million|k|m|b)?)",
            body,
            re.I,
        ):
            nums.append((name, m.group(0).strip()))
    if len(nums) >= 2:
        vals = {n[1].lower() for n in nums}
        if len(vals) > 1:
            contradictory.append(
                "Conflicting quantitative claims: " + "; ".join(f"{n}: {v}" for n, v in nums[:6])
            )

    if not bodies:
        unknown.append("No worker produced a usable result for the objective")
    if objective and final_text and len(final_text) < 80:
        incomplete.append("Final synthesis is very short relative to objective")

    needs_more = bool(failed or contradictory or (incomplete and len(bodies) < 2))
    additional: list[dict[str, str]] = []
    for name in failed[:5]:
        additional.append(
            {
                "title": f"Retry / cover gap left by {name}",
                "reason": f"{name} failed or returned empty",
            }
        )
    for c in contradictory[:3]:
        additional.append(
            {
                "title": "Independent verification of conflicting claims",
                "reason": c,
            }
        )

    return {
        "known": known[:30],
        "unknown": unknown[:20],
        "uncertain": uncertain[:20],
        "contradictory": contradictory[:20],
        "incomplete": incomplete[:20],
        "failed_workers": failed,
        "needs_additional_work": needs_more,
        "additional_assignments": additional,
        "at": _now(),
    }


def objective_completeness_check(
    objective: str,
    agent_results: list[dict[str, Any]],
    final_text: str,
    gaps: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    CEO-level check: task completion ≠ objective achievement.
    Returns whether more work is advised (heuristic; LLM may refine).
    """
    gaps = gaps or gap_analysis(objective, agent_results, final_text=final_text)
    done = sum(
        1
        for a in agent_results
        if str(a.get("status")) in ("done", "completed") and str(a.get("result") or "").strip()
    )
    total = len(agent_results) or 1
    sufficient = (
        done > 0
        and not gaps.get("failed_workers")
        and not gaps.get("contradictory")
        and len((final_text or "").strip()) > 120
    )
    return {
        "objective": objective,
        "workers_with_results": done,
        "workers_total": total,
        "gaps": gaps,
        "sufficient_for_final_answer": sufficient and not gaps.get("needs_additional_work"),
        "advise_additional_work": bool(gaps.get("needs_additional_work")) or not sufficient,
        "rationale": (
            "Results look sufficient for a consolidated answer."
            if sufficient and not gaps.get("needs_additional_work")
            else "Gaps, failures, or contradictions suggest more work before claiming objective achievement."
        ),
        "at": _now(),
    }


def worker_inspector_payload(task: dict[str, Any]) -> dict[str, Any]:
    """
    Full inspector view for a worker assignment — summary + collapsible sections data.
    Never includes API keys.
    """
    runtime = dict(task.get("runtime_llm") or {})
    runtime.pop("api_key", None)
    if "api_key" in runtime:
        del runtime["api_key"]

    return {
        "worker": task.get("agent_name") or task.get("title") or "Worker",
        "status": task.get("status") or "unknown",
        "current_goal": task.get("goal_title") or task.get("goal_id") or "",
        "current_assignment": task.get("task") or task.get("description") or task.get("title") or "",
        "assigned_by": task.get("assigned_by") or "",
        "assigned_to": task.get("assigned_to") or task.get("org_node_id") or "",
        "sections": {
            "input_goal": {
                "goal": task.get("goal_title") or "",
                "parent_goal": task.get("parent_goal_id") or "",
                "assignment": task.get("task") or task.get("description") or "",
                "expected_outcome": task.get("expected_outcome") or "",
                "requirements": task.get("requirements") or [],
                "constraints": task.get("constraints") or [],
                "dependencies": task.get("dependencies") or task.get("depends_on") or [],
                "assigned_by": task.get("assigned_by") or "",
                "assigned_to": task.get("assigned_to") or "",
                "priority": task.get("priority") or "",
                "assignment_id": task.get("id") or "",
                "created_at": task.get("created_at") or "",
                "started_at": task.get("started_at") or "",
            },
            "effective_context": task.get("effective_context") or {},
            "attachments": task.get("attachments") or [],
            "tools": task.get("tool_calls") or [],
            "activity": task.get("activity") or task.get("log") or [],
            "findings": task.get("findings") or {},
            "decisions": task.get("decisions") or [],
            "result": {
                "text": task.get("result") or "",
                "evidence": task.get("evidence") or [],
                "status": task.get("status") or "",
            },
            "self_evaluation": task.get("self_evaluation") or {},
            "returned_to": {
                "recipient": task.get("returned_to") or task.get("assigned_by") or "",
                "assignment_id": task.get("id") or "",
                "timestamp": task.get("completed_at") or task.get("updated_at") or "",
                "status": task.get("status") or "",
            },
            "manager_review": task.get("review") or {},
            "follow_ups": task.get("follow_up_ids") or [],
            "revisions": task.get("revisions") or [],
            "timeline": task.get("activity") or task.get("log") or [],
            "usage": task.get("usage") or {},
            "runtime_llm": runtime,
            "errors": task.get("errors") or [],
        },
    }


def format_inspector_text(payload: dict[str, Any]) -> str:
    """Plain-text inspector for dialogs / export."""
    lines = [
        f"Worker: {payload.get('worker')}",
        f"Status: {payload.get('status')}",
        f"Goal: {payload.get('current_goal')}",
        f"Assignment: {payload.get('current_assignment')}",
        f"Assigned by: {payload.get('assigned_by')}",
        "",
    ]
    sec = payload.get("sections") or {}
    result = sec.get("result") or {}
    if result.get("text"):
        lines += ["## RESULT / OUTCOME", str(result.get("text"))[:4000], ""]
    review = sec.get("manager_review") or {}
    if review:
        lines += ["## MANAGER REVIEW", json.dumps(review, indent=2)[:2000], ""]
    se = sec.get("self_evaluation") or {}
    if se:
        lines += ["## SELF-EVALUATION", json.dumps(se, indent=2)[:1500], ""]
    runtime = sec.get("runtime_llm") or {}
    if runtime:
        safe = {k: v for k, v in runtime.items() if "key" not in k.lower()}
        lines += ["## RUNTIME MODEL", json.dumps(safe, indent=2)[:1000], ""]
    return "\n".join(lines)


def run_manager_review_llm(
    *,
    manager_name: str,
    objective: str,
    worker_name: str,
    assignment: str,
    worker_result: str,
    llm_call: Callable[..., str] | None = None,
) -> dict[str, Any]:
    """
    Optional LLM manager review. If llm_call is None, use heuristic approval.
    llm_call(system, user) -> str
    """
    if not llm_call:
        ok = bool((worker_result or "").strip()) and len(worker_result.strip()) > 40
        return {
            "reviewed_by": manager_name,
            "assessment": "Heuristic: non-empty result accepted for further synthesis."
            if ok
            else "Heuristic: empty/short result needs revision.",
            "state": "approved" if ok else "needs_revision",
            "action": "" if ok else "Request revision or reassign",
            "source": "heuristic",
            "at": _now(),
        }

    system = (
        f"You are {manager_name}, a manager in an AI organisation. "
        "Review the worker's result. Reply JSON only: "
        '{"state":"approved|needs_revision|needs_more_information|needs_verification|blocked|rejected",'
        '"assessment":"...","action":"..."}'
    )
    user = (
        f"Objective: {objective}\nWorker: {worker_name}\nAssignment: {assignment}\n\n"
        f"Worker result:\n{worker_result[:8000]}"
    )
    try:
        raw = llm_call(system, user)
        m = re.search(r"\{[\s\S]*\}", raw or "")
        if m:
            data = json.loads(m.group(0))
            return {
                "reviewed_by": manager_name,
                "assessment": str(data.get("assessment") or "")[:2000],
                "state": str(data.get("state") or "approved").lower().replace(" ", "_"),
                "action": str(data.get("action") or "")[:500],
                "source": "llm",
                "at": _now(),
            }
    except Exception as e:  # noqa: BLE001
        return {
            "reviewed_by": manager_name,
            "assessment": f"Review failed: {e}",
            "state": "needs_verification",
            "action": "Manual review",
            "source": "error",
            "at": _now(),
        }
    return {
        "reviewed_by": manager_name,
        "assessment": "Could not parse review",
        "state": "needs_verification",
        "action": "",
        "source": "parse_error",
        "at": _now(),
    }


def enrich_task_after_run(
    task: dict[str, Any],
    *,
    runtime_llm: dict[str, Any] | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Attach structured report artifacts after a worker finishes."""
    body = str(task.get("result") or "")
    structured = parse_structured_report(body)
    task["findings"] = {
        "key_findings": structured.get("findings") or [],
        "assumptions": structured.get("assumptions") or [],
        "limitations": structured.get("limitations") or [],
        "confidence": structured.get("confidence") or "",
        "recommendation": structured.get("recommendation") or "",
    }
    task["self_evaluation"] = build_self_evaluation(
        str(task.get("task") or task.get("title") or ""),
        body,
        structured,
    )
    if runtime_llm:
        safe = {k: v for k, v in runtime_llm.items() if "api_key" not in k.lower()}
        task["runtime_llm"] = safe
    if tool_calls is not None:
        task["tool_calls"] = tool_calls
    if task.get("status") in ("done", "completed") and not task.get("completed_at"):
        task["completed_at"] = _now()
    _get_company().save_work_task(task)
    return task


def create_follow_up_assignments(
    gaps: dict[str, Any],
    *,
    objective_id: str,
    goal_id: str = "",
    assigned_by: str = "ceo",
    project_id: str = "",
) -> list[dict[str, Any]]:
    """Materialise gap-analysis suggestions as new assignment tasks."""
    created: list[dict[str, Any]] = []
    for item in (gaps.get("additional_assignments") or [])[:8]:
        title = str(item.get("title") or "Follow-up work")
        reason = str(item.get("reason") or "")
        a = _get_company().new_assignment(
            title,
            objective_id=objective_id,
            goal_id=goal_id or objective_id,
            assigned_by=assigned_by,
            expected_outcome="Fill the identified gap with evidence",
            requirements=[reason] if reason else [],
            project_id=project_id,
        )
        a["status"] = "pending"
        a["priority"] = "high"
        _get_company().save_work_task(a)
        created.append(a)
    return created
