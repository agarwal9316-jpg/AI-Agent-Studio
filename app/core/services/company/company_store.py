"""AI company structure: org roles, goals, work tasks, approvals, assignments."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.paths import (
    company_approvals_dir,
    company_dir,
    company_goals_dir,
    company_org_path,
    company_work_tasks_dir,
)
from app.core.services.data.storage import _read_json, _write_json, load_config, save_config


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Assignment lifecycle (completion ≠ correctness)
ASSIGNMENT_STATUSES = (
    "pending",
    "assigned",
    "accepted",
    "running",
    "waiting",
    "blocked",
    "completed",
    "failed",
    "needs_review",
    "rejected",
    "reassigned",
    "cancelled",
    "timed_out",
)

# Manager review states
REVIEW_STATES = (
    "approved",
    "needs_revision",
    "needs_more_information",
    "needs_verification",
    "blocked",
    "rejected",
)

# Goal kinds: objective is user-level; goal/subgoal are organisational
GOAL_KINDS = ("objective", "goal", "subgoal")


DEFAULT_ORG = {
    "name": "AI Company",
    "approval_mode": "manual",  # manual | auto
    "ceo_notes": "CEO coordinates goals, assigns work to AI roles, reviews approvals.",
    "roles": [
        {
            "id": "ceo",
            "title": "CEO",
            "description": "Sets goals, assigns work, prioritizes, reviews outcomes",
            "system_extra": "You are the CEO. Break goals into tasks and assign clearly.",
        },
        {
            "id": "pm",
            "title": "Product Manager",
            "description": "Clarifies requirements and acceptance criteria",
            "system_extra": "You are a PM. Write clear requirements and success criteria.",
        },
        {
            "id": "engineer",
            "title": "Engineer",
            "description": "Implements technical work via tools",
            "system_extra": "You are an engineer. Use tools to implement and verify.",
        },
        {
            "id": "researcher",
            "title": "Researcher",
            "description": "Researches and summarizes findings",
            "system_extra": "You are a researcher. Gather facts and cite sources when possible.",
        },
        {
            "id": "qa",
            "title": "QA",
            "description": "Tests and finds issues",
            "system_extra": "You are QA. Verify claims with evidence and list risks.",
        },
    ],
    "updated_at": "",
}


def load_org() -> dict[str, Any]:
    data = _read_json(company_org_path(), None)
    if isinstance(data, dict) and data.get("roles"):
        data.setdefault("approval_mode", "manual")
        return data
    org = dict(DEFAULT_ORG)
    org["updated_at"] = _now()
    save_org(org)
    return org


def save_org(org: dict[str, Any]) -> None:
    org["updated_at"] = _now()
    _write_json(company_org_path(), org)


def get_approval_mode() -> str:
    mode = load_org().get("approval_mode") or load_config().get("approval_mode") or "manual"
    return mode if mode in ("auto", "manual") else "manual"


def set_approval_mode(mode: str) -> None:
    org = load_org()
    org["approval_mode"] = "auto" if mode == "auto" else "manual"
    save_org(org)
    cfg = load_config()
    cfg["approval_mode"] = org["approval_mode"]
    save_config(cfg)


def list_roles() -> list[dict[str, Any]]:
    return list(load_org().get("roles") or [])


def add_role(title: str, description: str = "", system_extra: str = "") -> dict[str, Any]:
    org = load_org()
    role = {
        "id": str(uuid.uuid4())[:8],
        "title": title.strip() or "Role",
        "description": description.strip(),
        "system_extra": system_extra.strip()
        or f"You are the {title}. Complete assigned work carefully.",
    }
    org.setdefault("roles", []).append(role)
    save_org(org)
    return role


# --- Goals ---


def list_goals() -> list[dict[str, Any]]:
    out = []
    for p in sorted(company_goals_dir().glob("*.json"), reverse=True):
        d = _read_json(p, None)
        if isinstance(d, dict) and d.get("id"):
            out.append(d)
    return out


def save_goal(goal: dict[str, Any]) -> dict[str, Any]:
    if not goal.get("id"):
        goal["id"] = str(uuid.uuid4())
        goal["created_at"] = _now()
        goal.setdefault("status", "open")  # open | running | done | failed
    goal["updated_at"] = _now()
    _write_json(company_goals_dir() / f"{goal['id']}.json", goal)
    return goal


def new_goal(title: str, description: str = "", project_id: str = "") -> dict[str, Any]:
    return save_goal(
        {
            "title": title.strip(),
            "description": description.strip(),
            "project_id": project_id,
            "status": "open",
            "kind": "objective",  # objective | goal | subgoal
            "parent_goal_id": "",
            "owner_node_id": "",  # org worker responsible
            "assigned_to_node_id": "",
            "success_criteria": "",
            "open_issues": [],
            "decisions": [],
            "created_at": _now(),
        }
    )


def new_org_goal(
    title: str,
    *,
    description: str = "",
    kind: str = "goal",
    parent_goal_id: str = "",
    owner_node_id: str = "",
    assigned_to_node_id: str = "",
    objective_id: str = "",
    project_id: str = "",
    success_criteria: str = "",
) -> dict[str, Any]:
    """Create a structured organisational goal / sub-goal under an objective."""
    k = kind if kind in GOAL_KINDS else "goal"
    return save_goal(
        {
            "title": title.strip(),
            "description": description.strip(),
            "project_id": project_id,
            "status": "open",
            "kind": k,
            "parent_goal_id": parent_goal_id or objective_id or "",
            "objective_id": objective_id or parent_goal_id or "",
            "owner_node_id": owner_node_id,
            "assigned_to_node_id": assigned_to_node_id,
            "success_criteria": success_criteria,
            "open_issues": [],
            "decisions": [],
            "created_at": _now(),
        }
    )


def get_goal(goal_id: str) -> dict[str, Any] | None:
    d = _read_json(company_goals_dir() / f"{goal_id}.json", None)
    return d if isinstance(d, dict) else None


# --- Work tasks (company workflow, not Agents page tasks) ---


def list_work_tasks(goal_id: str = "") -> list[dict[str, Any]]:
    out = []
    for p in sorted(company_work_tasks_dir().glob("*.json"), reverse=True):
        d = _read_json(p, None)
        if not isinstance(d, dict) or not d.get("id"):
            continue
        if goal_id and d.get("goal_id") != goal_id:
            continue
        out.append(d)
    return out


def recover_stale_running_tasks(reason: str = "app restarted while task was running") -> int:
    """
    Mark orphaned 'running' work tasks as failed.

    If the app exits mid-task, status stays 'running' forever and the Work badge
    shows a permanent count. Call this when the background worker starts.
    """
    n = 0
    for t in list_work_tasks():
        st = str(t.get("status") or "").lower()
        if st not in ("running", "in_progress", "active"):
            continue
        t["status"] = "failed"
        t["result"] = (t.get("result") or "") or f"Interrupted: {reason}"
        log = list(t.get("log") or [])
        log.append({"at": _now(), "msg": f"failed: {reason}"})
        t["log"] = log
        save_work_task(t)
        n += 1
    return n


def save_work_task(task: dict[str, Any]) -> dict[str, Any]:
    if not task.get("id"):
        task["id"] = str(uuid.uuid4())
        task["created_at"] = _now()
        task.setdefault("status", "queued")
        # queued | waiting_approval | running | done | failed | cancelled
    task["updated_at"] = _now()
    _write_json(company_work_tasks_dir() / f"{task['id']}.json", task)
    return task


def get_work_task(task_id: str) -> dict[str, Any] | None:
    d = _read_json(company_work_tasks_dir() / f"{task_id}.json", None)
    return d if isinstance(d, dict) else None


def new_work_task(
    title: str,
    *,
    goal_id: str = "",
    role_id: str = "",
    description: str = "",
    project_id: str = "",
) -> dict[str, Any]:
    return save_work_task(
        {
            "title": title.strip(),
            "description": description.strip(),
            "goal_id": goal_id,
            "role_id": role_id,
            "project_id": project_id,
            "status": "queued",
            "result": "",
            "log": [],
        }
    )


def new_assignment(
    task: str,
    *,
    objective_id: str = "",
    goal_id: str = "",
    parent_goal_id: str = "",
    assigned_by: str = "",
    assigned_to: str = "",
    expected_outcome: str = "",
    requirements: str | list[str] = "",
    constraints: str | list[str] = "",
    priority: str = "normal",
    dependencies: list[str] | None = None,
    inputs: dict[str, Any] | None = None,
    attachments: list[dict[str, Any]] | None = None,
    project_id: str = "",
) -> dict[str, Any]:
    """
    Persistent structured assignment (AI Organisation).

    Distinct from temporary worker_prompt content.
    Status lifecycle uses ASSIGNMENT_STATUSES.
    """
    reqs = requirements if isinstance(requirements, list) else (
        [requirements] if str(requirements).strip() else []
    )
    cons = constraints if isinstance(constraints, list) else (
        [constraints] if str(constraints).strip() else []
    )
    return save_work_task(
        {
            "title": (task or "Assignment")[:120].strip(),
            "description": (task or "").strip(),
            "task": (task or "").strip(),
            "kind": "assignment",
            "goal_id": goal_id,
            "objective_id": objective_id or goal_id,
            "parent_goal_id": parent_goal_id,
            "assigned_by": assigned_by,
            "assigned_to": assigned_to,
            "org_node_id": assigned_to,
            "expected_outcome": expected_outcome,
            "requirements": reqs,
            "constraints": cons,
            "priority": priority or "normal",
            "dependencies": list(dependencies or []),
            "depends_on": list(dependencies or []),
            "inputs": dict(inputs or {}),
            "attachments": list(attachments or []),
            "project_id": project_id,
            "status": "assigned",
            "result": "",
            "evidence": [],
            "confidence": "",
            "issues": [],
            "review": {},
            "revision_count": 0,
            "revisions": [],
            "self_evaluation": {},
            "findings": {},
            "decisions": [],
            "activity": [],
            "tool_calls": [],
            "effective_context": {},
            "runtime_llm": {},
            "returned_to": assigned_by,
            "started_at": "",
            "completed_at": "",
            "log": [{"at": _now(), "msg": "assignment created"}],
        }
    )


def append_assignment_activity(task_id: str, msg: str, **extra: Any) -> dict[str, Any] | None:
    """Record an observable execution event (no fabricated thinking)."""
    t = get_work_task(task_id)
    if not t:
        return None
    act = list(t.get("activity") or [])
    entry = {"at": _now(), "msg": msg}
    entry.update({k: v for k, v in extra.items() if v is not None})
    act.append(entry)
    t["activity"] = act
    log = list(t.get("log") or [])
    log.append({"at": entry["at"], "msg": msg})
    t["log"] = log
    return save_work_task(t)


def set_assignment_status(task_id: str, status: str, *, note: str = "") -> dict[str, Any] | None:
    t = get_work_task(task_id)
    if not t:
        return None
    st = (status or "").strip().lower().replace(" ", "_")
    # Accept both assignment and legacy work-task statuses
    if st not in ASSIGNMENT_STATUSES and st not in (
        "queued",
        "waiting_approval",
        "running",
        "done",
        "failed",
        "cancelled",
        "blocked",
        "in_progress",
    ):
        st = "pending"
    t["status"] = st
    if st in ("running", "accepted") and not t.get("started_at"):
        t["started_at"] = _now()
    if st in ("completed", "done", "failed", "cancelled", "timed_out", "rejected"):
        t["completed_at"] = _now()
    if note:
        append_assignment_activity(task_id, note)
        t = get_work_task(task_id) or t
    return save_work_task(t)


def save_manager_review(
    task_id: str,
    *,
    reviewed_by: str,
    assessment: str,
    state: str = "approved",
    action: str = "",
    follow_up_assignment_id: str = "",
) -> dict[str, Any] | None:
    t = get_work_task(task_id)
    if not t:
        return None
    rev_state = (state or "approved").lower().replace(" ", "_")
    if rev_state not in REVIEW_STATES:
        rev_state = "approved"
    review = {
        "reviewed_by": reviewed_by,
        "assessment": assessment,
        "state": rev_state,
        "action": action,
        "follow_up_assignment_id": follow_up_assignment_id,
        "at": _now(),
    }
    t["review"] = review
    if rev_state == "approved":
        t["status"] = "completed"
        t["completed_at"] = _now()
    elif rev_state in ("needs_revision", "needs_more_information", "needs_verification"):
        t["status"] = "needs_review"
    elif rev_state == "rejected":
        t["status"] = "rejected"
        t["completed_at"] = _now()
    elif rev_state == "blocked":
        t["status"] = "blocked"
    # Persist status + review first, then append activity log
    act = list(t.get("activity") or [])
    act.append(
        {
            "at": _now(),
            "msg": f"Manager review: {rev_state}",
            "reviewed_by": reviewed_by,
        }
    )
    t["activity"] = act
    log = list(t.get("log") or [])
    log.append({"at": _now(), "msg": f"Manager review: {rev_state}"})
    t["log"] = log
    return save_work_task(t)


def record_revision(task_id: str, revised_result: str, *, note: str = "") -> dict[str, Any] | None:
    """Preserve prior result and store a new revision (never overwrite history)."""
    t = get_work_task(task_id)
    if not t:
        return None
    revs = list(t.get("revisions") or [])
    if t.get("result"):
        revs.append(
            {
                "revision": len(revs) + 1,
                "result": t.get("result"),
                "at": t.get("completed_at") or t.get("updated_at") or _now(),
                "note": "prior result before revision",
            }
        )
    revs.append(
        {
            "revision": len(revs) + 1,
            "result": revised_result,
            "at": _now(),
            "note": note or "revision",
        }
    )
    t["revisions"] = revs
    t["revision_count"] = len(revs)
    t["result"] = revised_result
    t["status"] = "needs_review"
    return save_work_task(t)


def decisions_path():
    d = company_dir() / "decisions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_decision(
    decision: str,
    *,
    reason: str = "",
    evidence: list[str] | None = None,
    confidence: str = "",
    owner: str = "",
    goal_id: str = "",
    assignment_id: str = "",
) -> dict[str, Any]:
    """Organisational decision log entry."""
    row = {
        "id": str(uuid.uuid4()),
        "decision": decision,
        "reason": reason,
        "evidence": list(evidence or []),
        "confidence": confidence,
        "owner": owner,
        "goal_id": goal_id,
        "assignment_id": assignment_id,
        "created_at": _now(),
    }
    _write_json(decisions_path() / f"{row['id']}.json", row)
    return row


def list_decisions(goal_id: str = "") -> list[dict[str, Any]]:
    out = []
    for p in sorted(decisions_path().glob("*.json"), reverse=True):
        d = _read_json(p, None)
        if not isinstance(d, dict) or not d.get("id"):
            continue
        if goal_id and d.get("goal_id") != goal_id:
            continue
        out.append(d)
    return out


def objective_dashboard(goal_id: str) -> dict[str, Any]:
    """
    Objective-level view: goals, assignment counts, open issues.
    No fake percentage progress.
    """
    goal = get_goal(goal_id)
    if not goal:
        return {"ok": False, "error": "Objective not found"}
    tasks = list_work_tasks(goal_id=goal_id)
    # Also include tasks that reference objective_id
    for t in list_work_tasks():
        if t.get("objective_id") == goal_id and t not in tasks:
            if t.get("id") not in {x.get("id") for x in tasks}:
                tasks.append(t)
    by_status: dict[str, int] = {}
    for t in tasks:
        st = str(t.get("status") or "unknown")
        by_status[st] = by_status.get(st, 0) + 1
    open_issues = list(goal.get("open_issues") or [])
    for t in tasks:
        for iss in t.get("issues") or []:
            open_issues.append(iss if isinstance(iss, dict) else {"text": str(iss)})
    child_goals = [
        g
        for g in list_goals()
        if g.get("parent_goal_id") == goal_id or g.get("objective_id") == goal_id
    ]
    return {
        "ok": True,
        "objective": goal.get("title") or goal.get("description") or "",
        "objective_id": goal_id,
        "status": goal.get("status") or "open",
        "goals": [
            {
                "id": g.get("id"),
                "title": g.get("title"),
                "status": g.get("status"),
                "kind": g.get("kind") or "goal",
                "owner_node_id": g.get("owner_node_id") or "",
            }
            for g in child_goals
        ],
        "assignments_total": len(tasks),
        "by_status": by_status,
        "active": by_status.get("running", 0)
        + by_status.get("assigned", 0)
        + by_status.get("accepted", 0)
        + by_status.get("queued", 0),
        "completed": by_status.get("completed", 0) + by_status.get("done", 0),
        "failed": by_status.get("failed", 0) + by_status.get("timed_out", 0),
        "open_issues": open_issues[:50],
        "ceo_assessment": goal.get("ceo_assessment") or "",
        "decisions": list_decisions(goal_id=goal_id)[:20],
    }


# --- Approvals ---


def list_approvals(status: str = "") -> list[dict[str, Any]]:
    out = []
    for p in sorted(company_approvals_dir().glob("*.json"), reverse=True):
        d = _read_json(p, None)
        if not isinstance(d, dict) or not d.get("id"):
            continue
        if status and d.get("status") != status:
            continue
        out.append(d)
    return out


def save_approval(ap: dict[str, Any]) -> dict[str, Any]:
    if not ap.get("id"):
        ap["id"] = str(uuid.uuid4())
        ap["created_at"] = _now()
        ap.setdefault("status", "pending")  # pending | approved | rejected
    ap["updated_at"] = _now()
    _write_json(company_approvals_dir() / f"{ap['id']}.json", ap)
    return ap


def get_approval(ap_id: str) -> dict[str, Any] | None:
    d = _read_json(company_approvals_dir() / f"{ap_id}.json", None)
    return d if isinstance(d, dict) else None


def request_approval(task_id: str, summary: str) -> dict[str, Any]:
    return save_approval(
        {
            "task_id": task_id,
            "summary": summary,
            "status": "pending",
        }
    )
