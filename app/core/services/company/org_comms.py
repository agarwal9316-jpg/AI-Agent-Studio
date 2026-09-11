"""
Organisational communication log — who sent what to whom, when, why.

Persisted under data/company/comms/. Never stores API keys.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.paths import company_dir
from app.core.services.data.storage import _read_json, _write_json


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def comms_dir():
    d = company_dir() / "comms"
    d.mkdir(parents=True, exist_ok=True)
    return d


def log_comm(
    *,
    from_id: str = "",
    from_name: str = "",
    to_id: str = "",
    to_name: str = "",
    message_type: str = "task_result",
    purpose: str = "",
    status: str = "delivered",
    objective_id: str = "",
    goal_id: str = "",
    assignment_id: str = "",
    summary: str = "",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = {
        "id": str(uuid.uuid4()),
        "from_id": from_id,
        "from_name": from_name,
        "to_id": to_id,
        "to_name": to_name,
        "message_type": message_type,
        "purpose": purpose,
        "status": status,
        "objective_id": objective_id,
        "goal_id": goal_id,
        "assignment_id": assignment_id,
        "summary": (summary or "")[:2000],
        "payload": _safe_payload(payload),
        "created_at": _now(),
    }
    _write_json(comms_dir() / f"{row['id']}.json", row)
    return row


def _safe_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return {}
    out: dict[str, Any] = {}
    for k, v in payload.items():
        lk = str(k).lower()
        if any(x in lk for x in ("api_key", "password", "token", "secret", "authorization")):
            continue
        out[k] = v
    return out


def list_comms(
    *,
    objective_id: str = "",
    goal_id: str = "",
    node_id: str = "",
    limit: int = 100,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in sorted(comms_dir().glob("*.json"), reverse=True):
        d = _read_json(p, None)
        if not isinstance(d, dict) or not d.get("id"):
            continue
        if objective_id and d.get("objective_id") != objective_id:
            continue
        if goal_id and d.get("goal_id") != goal_id:
            continue
        if node_id and node_id not in (
            d.get("from_id"),
            d.get("to_id"),
        ):
            continue
        out.append(d)
        if len(out) >= limit:
            break
    return out


def format_comm_graph(comms: list[dict[str, Any]]) -> str:
    lines = ["Communication flow (newest first)", ""]
    for c in comms[:40]:
        lines.append(
            f"{c.get('created_at', '')[:19]}  "
            f"{c.get('from_name') or c.get('from_id') or '?'}  →  "
            f"{c.get('to_name') or c.get('to_id') or '?'}  "
            f"[{c.get('message_type')}]  {c.get('purpose') or ''}"
        )
        if c.get("summary"):
            lines.append(f"    {str(c.get('summary'))[:160]}")
        lines.append(f"    status={c.get('status')}")
    return "\n".join(lines) if len(lines) > 2 else "No communication events yet."


def log_worker_result_upward(
    *,
    worker_name: str,
    worker_id: str = "",
    manager_name: str = "Manager/CEO",
    manager_id: str = "",
    assignment_id: str = "",
    objective_id: str = "",
    goal_id: str = "",
    result_summary: str = "",
    status: str = "needs_review",
) -> dict[str, Any]:
    return log_comm(
        from_id=worker_id,
        from_name=worker_name,
        to_id=manager_id,
        to_name=manager_name,
        message_type="task_result",
        purpose="Worker result returned upward",
        status=status,
        objective_id=objective_id,
        goal_id=goal_id,
        assignment_id=assignment_id,
        summary=result_summary[:500],
    )


def log_manager_review_comm(
    *,
    manager_name: str,
    manager_id: str = "",
    worker_name: str = "",
    worker_id: str = "",
    assignment_id: str = "",
    objective_id: str = "",
    review_state: str = "",
    assessment: str = "",
) -> dict[str, Any]:
    return log_comm(
        from_id=manager_id,
        from_name=manager_name,
        to_id=worker_id,
        to_name=worker_name,
        message_type="manager_review",
        purpose=f"Review: {review_state}",
        status="delivered",
        objective_id=objective_id,
        assignment_id=assignment_id,
        summary=assessment[:500],
    )
