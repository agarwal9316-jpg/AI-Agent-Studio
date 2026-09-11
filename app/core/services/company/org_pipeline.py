"""
Hard organisational multi-agent pipeline.

When Chat "Org pipeline" is ON:
  0. CEO/planner LLM decides agent flow (who runs, in what order) from the org chart
  1. Expand / bind work tasks for selected agents
  2. Each agent runs (own LLM if set) with prior agent outputs
  3. CEO synthesis is blocked until selected agents finish
  4. Final output is evaluated for coverage
  5. CEO answer is returned as the Chat final reply
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Callable

from app.services import company_store as company
from app.services import workflow_graph as wfg


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_org_agent_catalog(graph: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Flat list of AI worker seats available for planning (any depth)."""
    from app.core.services.data.storage import get_agent

    g = graph or wfg.get_active_graph()
    dept_name: dict[str, str] = {}
    for n in g.get("nodes") or []:
        if n.get("type") == "department":
            dept_name[str(n.get("id"))] = str(n.get("title") or "Department")

    catalog: list[dict[str, Any]] = []
    for n in wfg.walk_tree(g):
        if n.get("type") not in ("agent", "role", "worker"):
            continue
        if n.get("enabled") is False:
            continue
        parent = str(n.get("parent_id") or "")
        dname = dept_name.get(parent, "")
        if not dname:
            p = wfg.get_node(g, parent) if parent else None
            climb = 0
            while p and p.get("type") != "department" and climb < 12:
                pid = p.get("parent_id")
                p = wfg.get_node(g, pid) if pid else None
                climb += 1
            dname = (p.get("title") if p else None) or "Organisation"
        ag = get_agent(n.get("agent_id") or "") if n.get("agent_id") else None
        catalog.append(
            {
                "org_node_id": str(n.get("id") or ""),
                "title": str(n.get("title") or "AI Worker"),
                "department": dname,
                "role": str((ag or {}).get("role") or n.get("agent_role") or ""),
                "goal": str((ag or {}).get("goal") or n.get("agent_goal") or ""),
                "instructions": str(
                    n.get("worker_prompt") or n.get("instructions") or ""
                )[:300],
                "agent_id": str(n.get("agent_id") or ""),
                "is_manager": bool(n.get("_is_manager")),
                "depth": int(n.get("_depth") or 0),
            }
        )
    return catalog


def plan_agent_flow(
    objective: str,
    catalog: list[dict[str, Any]],
    *,
    on_progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """
    LLM (CEO planner) decides which agents run and in what order.

    Returns:
      ordered_ids: list[org_node_id]
      rationale: str
      source: llm | tree_fallback
      raw: optional model text
    """
    if not catalog:
        return {
            "ordered_ids": [],
            "rationale": "No agents in organisation tree.",
            "source": "empty",
            "steps": [],
        }

    # Default = tree order (walk order of catalog)
    default_ids = [c["org_node_id"] for c in catalog if c.get("org_node_id")]

    def prog(msg: str) -> None:
        if on_progress:
            try:
                on_progress(msg)
            except Exception:  # noqa: BLE001
                pass

    prog("CEO planner: deciding agent flow before pipeline…")

    lines = []
    for i, c in enumerate(catalog, 1):
        lines.append(
            f"{i}. id=`{c.get('org_node_id')}` | [{c.get('department')}] {c.get('title')} "
            f"| role={c.get('role') or '—'} | goal={c.get('goal') or '—'} "
            f"| notes={(c.get('instructions') or '')[:120]}"
        )
    catalog_text = "\n".join(lines)

    system = (
        "You are the CEO of a multi-agent organisation. "
        "Before work starts, you design the execution flow.\n"
        "Rules:\n"
        "- Choose ONLY agents from the catalog (use their exact id values).\n"
        "- Order agents so earlier outputs help later ones when useful "
        "(e.g. product/requirements before engineering, engineering before QA).\n"
        "- You may SKIP agents that are irrelevant to the objective.\n"
        "- Prefer a focused team (typically 2–8 agents) unless the task truly needs everyone.\n"
        "- Always return valid JSON only, no markdown fences."
    )
    user = (
        f"## User objective\n{objective}\n\n"
        f"## Agent catalog\n{catalog_text}\n\n"
        "Return JSON with this shape:\n"
        "{\n"
        '  "flow": [\n'
        '    {"id": "org_node_id", "why": "short reason"},\n'
        "    ...\n"
        "  ],\n"
        '  "rationale": "1-3 sentences on overall sequencing"\n'
        "}\n"
    )

    try:
        from app.core.services.llm.llm import chat_completion
        from app.core.services.data.storage import resolve_agent_llm

        llm = resolve_agent_llm(None)
        if not llm.get("api_key"):
            raise RuntimeError("No API key for CEO planner")
        raw = chat_completion(
            api_key=llm["api_key"],
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            model=llm["model"],
            base_url=llm["base_url"],
            timeout=90.0,
        )
        assert isinstance(raw, str)
        plan = _parse_flow_json(raw, allowed_ids=set(default_ids))
        if not plan.get("ordered_ids"):
            raise RuntimeError("Planner returned empty flow")
        steps = plan.get("steps") or []
        prog(
            f"CEO planner decided flow: {len(plan['ordered_ids'])} of {len(catalog)} agents"
        )
        for i, sid in enumerate(plan["ordered_ids"], 1):
            title = next(
                (c["title"] for c in catalog if c.get("org_node_id") == sid),
                sid,
            )
            why = ""
            for s in steps:
                if s.get("id") == sid:
                    why = str(s.get("why") or "")
                    break
            prog(f"  Flow [{i}/{len(plan['ordered_ids'])}]: {title}" + (f" — {why}" if why else ""))
        plan["source"] = "llm"
        plan["raw"] = raw[:4000]
        return plan
    except Exception as e:  # noqa: BLE001
        prog(f"CEO planner fallback to org-tree order ({e})")
        return {
            "ordered_ids": default_ids,
            "rationale": f"Tree depth-first order (planner unavailable: {e})",
            "source": "tree_fallback",
            "steps": [
                {"id": i, "why": "org tree order"} for i in default_ids
            ],
        }


def _parse_flow_json(text: str, *, allowed_ids: set[str]) -> dict[str, Any]:
    """Extract ordered agent ids from planner JSON (robust to fences/extra text)."""
    raw = (text or "").strip()
    # strip ```json fences
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
    raw = re.sub(r"\s*```$", "", raw)
    data: Any = None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            try:
                data = json.loads(m.group(0))
            except json.JSONDecodeError:
                data = None
    if not isinstance(data, dict):
        return {"ordered_ids": [], "rationale": "", "steps": []}

    flow = data.get("flow") or data.get("order") or data.get("agents") or []
    steps: list[dict[str, str]] = []
    ordered: list[str] = []
    seen: set[str] = set()

    def _add(aid: str, why: str = "") -> None:
        aid = (aid or "").strip()
        if not aid or aid in seen:
            return
        # exact id
        if aid in allowed_ids:
            seen.add(aid)
            ordered.append(aid)
            steps.append({"id": aid, "why": why})
            return
        # fuzzy: title match against allowed by scanning catalog later handled by caller
        # try case-insensitive id
        for a in allowed_ids:
            if a.lower() == aid.lower():
                if a not in seen:
                    seen.add(a)
                    ordered.append(a)
                    steps.append({"id": a, "why": why})
                return

    if isinstance(flow, list):
        for item in flow:
            if isinstance(item, str):
                _add(item)
            elif isinstance(item, dict):
                _add(
                    str(item.get("id") or item.get("org_node_id") or item.get("agent_id") or ""),
                    str(item.get("why") or item.get("reason") or ""),
                )
    # also accept plain list of ids
    if not ordered and isinstance(data.get("ids"), list):
        for item in data["ids"]:
            _add(str(item))

    return {
        "ordered_ids": ordered,
        "rationale": str(data.get("rationale") or data.get("summary") or ""),
        "steps": steps,
    }


def reorder_tasks_by_plan(
    agent_tasks: list[dict[str, Any]],
    ordered_ids: list[str],
    catalog: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Reorder agent tasks to match LLM plan.
    Tasks without org_node_id matched by title; unplanned tasks are dropped if plan non-empty.
    """
    if not ordered_ids:
        return list(agent_tasks)

    by_node: dict[str, dict[str, Any]] = {}
    by_title: dict[str, dict[str, Any]] = {}
    for t in agent_tasks:
        nid = str(t.get("org_node_id") or "")
        if nid:
            by_node[nid] = t
        title = str(t.get("title") or t.get("agent_name") or "").lower()
        if title:
            by_title[title] = t

    # Map catalog id → titles for fuzzy
    id_to_titles: dict[str, list[str]] = {}
    for c in catalog:
        nid = str(c.get("org_node_id") or "")
        id_to_titles.setdefault(nid, []).append(
            f"[{c.get('department')}] {c.get('title')}".lower()
        )
        id_to_titles[nid].append(str(c.get("title") or "").lower())

    ordered_tasks: list[dict[str, Any]] = []
    used: set[str] = set()
    for nid in ordered_ids:
        t = by_node.get(nid)
        if t is None:
            for tit in id_to_titles.get(nid, []):
                t = by_title.get(tit)
                if t:
                    break
        if t is None:
            continue
        tid = str(t.get("id") or "")
        if tid in used:
            continue
        used.add(tid)
        ordered_tasks.append(t)

    # If planner returned nothing usable, keep original
    if not ordered_tasks:
        return list(agent_tasks)
    return ordered_tasks


def evaluate_agent_outputs(
    objective: str,
    agent_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Check every agent produced usable output."""
    issues: list[str] = []
    ok_agents: list[str] = []
    failed: list[str] = []
    for a in agent_results:
        name = str(a.get("agent_name") or a.get("title") or "agent")
        status = str(a.get("status") or "")
        result = (a.get("result") or "").strip()
        if status == "failed" or not result:
            failed.append(name)
            issues.append(f"Agent “{name}” has no usable result (status={status or 'empty'}).")
        elif len(result) < 40:
            issues.append(f"Agent “{name}” result is very short ({len(result)} chars).")
            ok_agents.append(name)
        else:
            ok_agents.append(name)
    ok = len(failed) == 0 and len(agent_results) > 0
    if not agent_results:
        issues.append("No agents ran — org tree may have no agent seats.")
        ok = False
    report = (
        f"## Agent completion evaluation\n"
        f"- Objective: {objective[:200]}\n"
        f"- Agents total: {len(agent_results)}\n"
        f"- Succeeded: {', '.join(ok_agents) or '(none)'}\n"
        f"- Failed/empty: {', '.join(failed) or '(none)'}\n"
        f"- Issues: {'; '.join(issues) if issues else 'none'}\n"
    )
    return {
        "ok": ok,
        "issues": issues,
        "ok_agents": ok_agents,
        "failed_agents": failed,
        "report": report,
    }


def evaluate_final_output(
    objective: str,
    agent_results: list[dict[str, Any]],
    final_text: str,
) -> dict[str, Any]:
    """Heuristic: final answer should reflect agents / not be empty."""
    issues: list[str] = []
    text = (final_text or "").strip()
    if len(text) < 80:
        issues.append("Final CEO answer is too short.")
    names = [
        str(a.get("agent_name") or a.get("title") or "").strip()
        for a in agent_results
        if (a.get("agent_name") or a.get("title"))
    ]
    mentioned = []
    low = text.lower()
    for n in names:
        if n and n.lower() in low:
            mentioned.append(n)
        else:
            # dept tags like [Product]
            pass
    # Soft coverage: mention count or section-like structure
    coverage = len(mentioned) / max(1, len(names)) if names else 1.0
    if names and coverage < 0.25 and len(text) < 500:
        issues.append(
            "Final answer may not clearly reference individual agent contributions "
            f"(mentioned {len(mentioned)}/{len(names)} agent names)."
        )
    ok = len(text) >= 80 and (not names or coverage >= 0.15 or len(text) >= 400)
    report = (
        f"## Final answer evaluation\n"
        f"- Length: {len(text)} chars\n"
        f"- Agent names mentioned: {len(mentioned)}/{len(names)}\n"
        f"- Coverage score: {coverage:.0%}\n"
        f"- Issues: {'; '.join(issues) if issues else 'none'}\n"
        f"- Pass: {'yes' if ok else 'review recommended'}\n"
    )
    return {
        "ok": ok,
        "issues": issues,
        "coverage": coverage,
        "mentioned": mentioned,
        "report": report,
    }


def build_full_handoff_pack(agent_results: list[dict[str, Any]]) -> str:
    """Full prior outputs for CEO (not truncated hard)."""
    parts: list[str] = [
        "## Complete multi-agent outputs (YOU MUST USE ALL OF THESE)",
        "For each agent below, incorporate their findings into the final user answer.",
        "If you omit an agent, explicitly say why.",
        "",
    ]
    for i, a in enumerate(agent_results, 1):
        name = a.get("agent_name") or a.get("title") or f"Agent {i}"
        dept = a.get("department") or ""
        status = a.get("status") or ""
        result = (a.get("result") or "").strip() or "(no result)"
        # Cap extremely long single agent at 12k to protect context
        if len(result) > 12000:
            result = result[:12000] + "\n…(truncated for context)"
        parts.append(f"### [{i}] {name}" + (f" — {dept}" if dept else ""))
        parts.append(f"Status: {status}")
        parts.append(result)
        parts.append("")
    return "\n".join(parts)


def run_org_pipeline(
    objective: str,
    *,
    project_id: str = "",
    on_progress: Callable[[str], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
    force_auto_approve: bool = True,
    graph_id: str | None = None,
    graph: dict[str, Any] | None = None,
    on_agent_complete: Callable[[dict[str, Any]], None] | None = None,
    on_flow_planned: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """
    Run full org pipeline synchronously (call from chat worker thread).

    graph / graph_id: use a specific org chart (Chat selector). Default = active.
    on_agent_complete: called after each agent finishes (for live Team feed).
    on_flow_planned: called once CEO planner locks order.

    Returns:
      ok, goal_id, agent_results, final_text, evaluation, tasks, error?, graph_id, graph_name
    """
    from app.core.services.chat.orchestrator import get_orchestrator

    objective = (objective or "").strip()
    if not objective:
        return {"ok": False, "error": "Empty objective"}

    def prog(msg: str) -> None:
        if on_progress:
            try:
                on_progress(msg)
            except Exception:  # noqa: BLE001
                pass

    def _agent_done(row: dict[str, Any]) -> None:
        if on_agent_complete:
            try:
                on_agent_complete(row)
            except Exception:  # noqa: BLE001
                pass

    orch = get_orchestrator()
    # Pause background queue so we own execution
    orch.begin_exclusive_pipeline()
    try:
        prog("Org pipeline: creating goal from your request…")
        goal = company.new_goal(
            objective[:80] or "Org goal",
            objective,
            project_id=project_id,
        )
        goal["status"] = "running"
        company.save_goal(goal)
        goal_id = str(goal["id"])

        # 0) LLM plans who runs and in what order (before any agent work)
        graph = wfg.resolve_graph(graph=graph, graph_id=graph_id)
        prog(
            f"Org chart: {graph.get('name') or graph.get('id') or 'active'} "
            f"({len(graph.get('nodes') or [])} nodes)"
        )
        catalog = list_org_agent_catalog(graph)
        flow_plan = plan_agent_flow(objective, catalog, on_progress=prog)
        if should_stop and should_stop():
            return {"ok": False, "error": "Stopped by user", "cancelled": True, "goal_id": goal_id}

        prog("Org pipeline: expanding organisation tree → agent tasks…")
        created = wfg.expand_to_company_tasks(
            objective,
            graph=graph,
            goal_id=goal_id,
            project_id=project_id,
            force_auto_approve=force_auto_approve,
        )
        if not created:
            return {
                "ok": False,
                "error": "No tasks created — add agents under departments in Workflow, then retry.",
                "goal_id": goal_id,
            }

        agent_tasks = [
            t
            for t in created
            if str(t.get("role_id") or "") != "ceo"
            and not str(t.get("title") or "").startswith("[CEO]")
        ]
        ceo_tasks = [
            t
            for t in created
            if str(t.get("role_id") or "") == "ceo"
            or str(t.get("title") or "").startswith("[CEO]")
        ]

        # Apply CEO planner order / selection (drop unselected agents)
        ordered_ids = list(flow_plan.get("ordered_ids") or [])
        if ordered_ids and catalog:
            agent_tasks = reorder_tasks_by_plan(agent_tasks, ordered_ids, catalog)
            # Cancel tasks not selected so they don't run in background later
            selected_ids = {str(t.get("id")) for t in agent_tasks}
            for t in created:
                if (
                    str(t.get("role_id") or "") != "ceo"
                    and not str(t.get("title") or "").startswith("[CEO]")
                    and str(t.get("id")) not in selected_ids
                ):
                    tt = company.get_work_task(str(t.get("id") or "")) or t
                    tt["status"] = "cancelled"
                    tt["result"] = "Skipped by CEO planner (not in chosen flow)."
                    company.save_work_task(tt)
            # CEO depends only on selected agents
            if ceo_tasks:
                ceo = company.get_work_task(str(ceo_tasks[0].get("id") or "")) or ceo_tasks[0]
                ceo["depends_on"] = [str(t.get("id")) for t in agent_tasks]
                ceo["status"] = "blocked"
                ceo["description"] = (
                    str(ceo.get("description") or "")
                    + "\n\n## CEO planner flow\n"
                    + str(flow_plan.get("rationale") or "")
                    + "\nOrder: "
                    + " → ".join(
                        next(
                            (
                                c["title"]
                                for c in catalog
                                if c.get("org_node_id") == oid
                            ),
                            oid,
                        )
                        for oid in ordered_ids
                    )
                )
                company.save_work_task(ceo)
                ceo_tasks = [ceo]

        # Fallback if tree had no agents: expand already may create defaults
        if not agent_tasks and not ceo_tasks:
            return {
                "ok": False,
                "error": "Org expansion produced no runnable tasks.",
                "goal_id": goal_id,
            }

        total_agents = len(agent_tasks)
        prog(
            f"Org pipeline: flow locked — {total_agents} agent(s) will run "
            f"(planner={flow_plan.get('source')}) + {len(ceo_tasks)} CEO · done 0/{total_agents}"
        )
        if flow_plan.get("rationale"):
            prog(f"Flow rationale: {str(flow_plan.get('rationale'))[:240]}")
        if on_flow_planned:
            try:
                on_flow_planned(
                    {
                        "source": flow_plan.get("source"),
                        "rationale": flow_plan.get("rationale"),
                        "ordered_ids": flow_plan.get("ordered_ids"),
                        "steps": flow_plan.get("steps"),
                        "total_agents": total_agents,
                    }
                )
            except Exception:  # noqa: BLE001
                pass

        agent_results: list[dict[str, Any]] = []
        done_count = 0
        failed_count = 0
        for i, task in enumerate(agent_tasks, 1):
            if should_stop and should_stop():
                return {
                    "ok": False,
                    "error": "Stopped by user",
                    "goal_id": goal_id,
                    "agent_results": agent_results,
                    "cancelled": True,
                    "flow_plan": {
                        "source": flow_plan.get("source"),
                        "rationale": flow_plan.get("rationale"),
                        "ordered_ids": flow_plan.get("ordered_ids"),
                        "steps": flow_plan.get("steps"),
                    },
                }
            # Reload task
            tid = task["id"]
            t = company.get_work_task(tid) or task
            if force_auto_approve:
                t["auto_approved"] = True
                t["status"] = "queued"
                company.save_work_task(t)
            name = t.get("agent_name") or t.get("title") or f"Agent {i}"
            prog(
                f"Agents {done_count}/{total_agents} done · "
                f"running [{i}/{total_agents}] {name}…"
            )
            orch.run_task_now(t)
            t2 = company.get_work_task(tid) or t
            # One automatic retry on gateway/timeout (common: Cloudflare HTTP 524)
            err_body = str(t2.get("result") or "")
            if str(t2.get("status") or "") == "failed" and any(
                x in err_body.lower()
                for x in ("524", "timeout", "timed out", "502", "503", "504", "connection")
            ):
                prog(
                    f"Agents {done_count}/{total_agents} done · "
                    f"retry [{i}/{total_agents}] {name} after temporary error…"
                )
                t2["status"] = "queued"
                t2["auto_approved"] = True
                t2["result"] = ""
                company.save_work_task(t2)
                orch.run_task_now(t2)
                t2 = company.get_work_task(tid) or t2
            # Communication log: worker → manager/CEO
            try:
                from app.services import org_comms

                org_comms.log_worker_result_upward(
                    worker_name=str(t2.get("agent_name") or name),
                    worker_id=str(t2.get("org_node_id") or ""),
                    manager_name="CEO",
                    manager_id="ceo",
                    assignment_id=tid,
                    objective_id=goal_id,
                    goal_id=goal_id,
                    result_summary=str(t2.get("result") or "")[:400],
                    status=str(t2.get("status") or "done"),
                )
            except Exception:  # noqa: BLE001
                pass
            # Heuristic manager review (parent accountability)
            try:
                from app.services import org_execution as org_ex

                review = org_ex.run_manager_review_llm(
                    manager_name="Manager/CEO",
                    objective=objective,
                    worker_name=str(t2.get("agent_name") or name),
                    assignment=str(t2.get("title") or ""),
                    worker_result=str(t2.get("result") or ""),
                )
                company.save_manager_review(
                    tid,
                    reviewed_by=str(review.get("reviewed_by") or "Manager/CEO"),
                    assessment=str(review.get("assessment") or ""),
                    state=str(review.get("state") or "approved"),
                    action=str(review.get("action") or ""),
                )
                t2 = company.get_work_task(tid) or t2
                try:
                    from app.services import org_comms

                    org_comms.log_manager_review_comm(
                        manager_name="Manager/CEO",
                        worker_name=str(t2.get("agent_name") or name),
                        worker_id=str(t2.get("org_node_id") or ""),
                        assignment_id=tid,
                        objective_id=goal_id,
                        review_state=str(review.get("state") or ""),
                        assessment=str(review.get("assessment") or ""),
                    )
                except Exception:  # noqa: BLE001
                    pass
            except Exception:  # noqa: BLE001
                pass

            row = {
                "task_id": tid,
                "title": t2.get("title"),
                "agent_name": t2.get("agent_name") or name,
                "agent_role": t2.get("agent_role") or t2.get("role_id"),
                "department": _dept_from_title(str(t2.get("title") or "")),
                "org_node_id": t2.get("org_node_id") or "",
                "status": t2.get("status"),
                "result": t2.get("result") or "",
                "model": (t2.get("runtime_llm") or {}).get("model")
                or t2.get("llm_model")
                or "",
                "runtime_llm": t2.get("runtime_llm") or {},
                "review": t2.get("review") or {},
                "index": i,
                "total": total_agents,
            }
            agent_results.append(row)
            st = t2.get("status")
            body = str(t2.get("result") or "").strip()
            if st in ("done", "completed") and body:
                done_count += 1
            elif st == "failed" or not body:
                failed_count += 1
                # still count as finished for progress denominator of "processed"
                done_count += 1  # finished processing this slot
            else:
                done_count += 1
            # Live Team feed: post this agent immediately (do not wait for whole pipeline)
            # Normalize status for feed (done/completed)
            if row.get("status") == "completed":
                row["status"] = "done"
            _agent_done(row)
            prog(
                f"Agents {done_count}/{total_agents} done"
                f"{f' · {failed_count} failed' if failed_count else ''} · "
                f"[{i}/{total_agents}] {name} → {st} ({len(body)} chars)"
            )
            # Put a readable preview of this agent's output into live Thinking
            if body:
                preview = body.replace("\n", " ").strip()
                if len(preview) > 420:
                    preview = preview[:400] + "…"
                prog(f"   ↳ {name} output: {preview}")
            else:
                prog(f"   ↳ {name} output: (empty)")

        agent_eval = evaluate_agent_outputs(objective, agent_results)
        prog(
            f"Agents {done_count}/{total_agents} done — evaluation complete"
            f"{f' · {failed_count} with issues' if failed_count else ''}"
        )
        if agent_eval.get("issues"):
            for iss in agent_eval["issues"][:5]:
                prog(f"  ⚠ {iss}")

        # Structured enrichment + gap analysis (AI Organisation upgrade)
        from app.services import org_execution as org_ex

        for a in agent_results:
            tid = str(a.get("task_id") or "")
            if not tid:
                continue
            t_en = company.get_work_task(tid)
            if t_en:
                try:
                    org_ex.enrich_task_after_run(t_en)
                except Exception:  # noqa: BLE001
                    pass
                # Mark org node status
                nid = str(t_en.get("org_node_id") or a.get("org_node_id") or "")
                if nid:
                    try:
                        st_node = "completed" if t_en.get("status") in ("done", "completed") else (
                            "error" if t_en.get("status") == "failed" else "idle"
                        )
                        wfg.set_worker_status(graph, nid, st_node)
                    except Exception:  # noqa: BLE001
                        pass

        gaps = org_ex.gap_analysis(objective, agent_results)
        prog(
            f"Gap analysis: known={len(gaps.get('known') or [])} "
            f"incomplete={len(gaps.get('incomplete') or [])} "
            f"conflicts={len(gaps.get('contradictory') or [])} "
            f"needs_more={gaps.get('needs_additional_work')}"
        )
        for c in (gaps.get("contradictory") or [])[:3]:
            prog(f"  ⚡ conflict: {c}")

        # Optional follow-up assignments from gaps
        follow_ups: list[dict[str, Any]] = []
        verification_results: list[dict[str, Any]] = []
        if gaps.get("needs_additional_work") and gaps.get("additional_assignments"):
            try:
                follow_ups = org_ex.create_follow_up_assignments(
                    gaps,
                    objective_id=goal_id,
                    goal_id=goal_id,
                    assigned_by="ceo",
                    project_id=project_id,
                )
                prog(f"Created {len(follow_ups)} follow-up assignment(s) from gap analysis")
            except Exception as e:  # noqa: BLE001
                prog(f"Follow-up creation skipped: {e}")

        # Independent verification pass for contradictions (bounded: max 2)
        verify_items = [
            x
            for x in (gaps.get("additional_assignments") or [])
            if "verif" in str(x.get("title") or "").lower()
            or "conflict" in str(x.get("reason") or "").lower()
            or "Independent verification" in str(x.get("title") or "")
        ]
        if not verify_items and gaps.get("contradictory"):
            verify_items = [
                {
                    "title": "Independent verification of conflicting claims",
                    "reason": str((gaps.get("contradictory") or [""])[0]),
                }
            ]
        for item in verify_items[:2]:
            if should_stop and should_stop():
                break
            title = str(item.get("title") or "Independent verification")
            prog(f"Independent verification: {title[:80]}…")
            try:
                vtask = company.new_assignment(
                    title,
                    objective_id=goal_id,
                    goal_id=goal_id,
                    assigned_by="ceo",
                    expected_outcome="Independent check of conflicting claims with evidence",
                    requirements=[str(item.get("reason") or "Verify conflicting findings")],
                    project_id=project_id,
                )
                vtask["auto_approved"] = True
                vtask["status"] = "queued"
                vtask["pipeline"] = "org"
                vtask["agent_name"] = "Verification Worker"
                vtask["agent_role"] = "verifier"
                vtask["description"] = (
                    f"Objective: {objective}\n"
                    f"Independent verification task.\n"
                    f"Reason: {item.get('reason')}\n"
                    "Do not copy prior workers. Re-check and report evidence.\n"
                )
                company.save_work_task(vtask)
                orch.run_task_now(vtask)
                v2 = company.get_work_task(str(vtask["id"])) or vtask
                verification_results.append(
                    {
                        "task_id": v2.get("id"),
                        "title": v2.get("title"),
                        "status": v2.get("status"),
                        "result": v2.get("result") or "",
                        "agent_name": "Verification Worker",
                    }
                )
                agent_results.append(
                    {
                        "task_id": v2.get("id"),
                        "title": v2.get("title"),
                        "agent_name": "Verification Worker",
                        "agent_role": "verifier",
                        "department": "Verification",
                        "org_node_id": "",
                        "status": v2.get("status"),
                        "result": v2.get("result") or "",
                        "model": "",
                        "index": len(agent_results) + 1,
                        "total": total_agents + 1,
                    }
                )
                prog(f"Verification → {v2.get('status')}")
            except Exception as e:  # noqa: BLE001
                prog(f"Verification skipped: {e}")
        if verification_results:
            # Re-run gap analysis with verification included
            gaps = org_ex.gap_analysis(objective, agent_results)

        # CEO synthesis with full handoff
        final_text = ""
        ceo_status = "skipped"
        if ceo_tasks:
            if should_stop and should_stop():
                return {
                    "ok": False,
                    "error": "Stopped by user before CEO synthesis",
                    "goal_id": goal_id,
                    "agent_results": agent_results,
                    "agent_evaluation": agent_eval,
                    "gap_analysis": gaps,
                    "cancelled": True,
                }
            handoff = build_full_handoff_pack(agent_results)
            handoff += "\n\n" + agent_eval.get("report", "")
            handoff += "\n\n## Gap analysis (manager/CEO)\n"
            handoff += (
                f"Needs additional work: {gaps.get('needs_additional_work')}\n"
                f"Failed workers: {', '.join(gaps.get('failed_workers') or []) or 'none'}\n"
                f"Contradictions: {'; '.join(gaps.get('contradictory') or []) or 'none'}\n"
                f"Incomplete: {'; '.join((gaps.get('incomplete') or [])[:5]) or 'none'}\n"
            )
            ceo = company.get_work_task(ceo_tasks[0]["id"]) or ceo_tasks[0]
            # Unblock CEO — only now
            ceo["status"] = "queued"
            ceo["auto_approved"] = True
            ceo["depends_on"] = []  # deps satisfied
            ceo["description"] = (
                str(ceo.get("description") or "")
                + "\n\n"
                + handoff
                + "\n\n## CEO synthesis rules (objective achievement)\n"
                "- Produce the final answer for the end user.\n"
                "- Explicitly use every agent section above.\n"
                "- Structure: executive summary, confirmed findings, evidence, "
                "assumptions, uncertainty, remaining gaps, recommendations.\n"
                "- Task completion ≠ objective achievement — if gaps are material, say so.\n"
                "- If an agent failed, note the gap.\n"
                "- Do NOT simply concatenate worker responses.\n"
            )
            company.save_work_task(ceo)
            prog(
                f"Agents {done_count}/{total_agents} done · "
                f"CEO synthesizing all agent outputs…"
            )
            try:
                orch.run_task_now(ceo)
            except Exception as e:  # noqa: BLE001
                prog(f"CEO task error: {e} — combining agent outputs")
            ceo2 = company.get_work_task(ceo["id"]) or ceo
            final_text = str(ceo2.get("result") or "").strip()
            ceo_status = str(ceo2.get("status") or "")
            # Fallback if CEO empty/failed (timeouts) — still complete the goal
            if not final_text or ceo_status == "failed":
                prog("CEO empty/failed — building finished answer from agent results")
                try:
                    from app.core.services.company.team_agent_tools import strip_tool_blocks
                except Exception:  # noqa: BLE001

                    def strip_tool_blocks(x: str) -> str:  # type: ignore
                        return x

                parts = [
                    "### Finished answer (assembled from team agents)\n",
                    f"**Goal:** {objective}\n",
                ]
                for a in agent_results:
                    body = strip_tool_blocks(str(a.get("result") or "").strip())
                    if body:
                        parts.append(
                            f"## {a.get('agent_name') or a.get('title')}\n{body[:4000]}\n"
                        )
                final_text = "\n".join(parts).strip()
                ceo_status = "done_fallback"
            prog(
                f"Agents {done_count}/{total_agents} done · "
                f"CEO → {ceo_status} ({len(final_text)} chars)"
            )
        else:
            # No CEO node — concatenate agent results as final
            final_text = "\n\n".join(
                f"## {a.get('agent_name')}\n{a.get('result')}" for a in agent_results
            )
            prog(
                f"Agents {done_count}/{total_agents} done · "
                f"no CEO node — combined agent outputs as final"
            )

        final_eval = evaluate_final_output(objective, agent_results, final_text)
        prog(
            f"Agents {done_count}/{total_agents} done · final evaluation complete"
        )

        obj_check = org_ex.objective_completeness_check(
            objective, agent_results, final_text, gaps=gaps
        )
        prog(
            f"Objective check: sufficient={obj_check.get('sufficient_for_final_answer')} "
            f"— {obj_check.get('rationale')}"
        )

        # If evaluation weak, append evaluation notes to final for transparency
        if not final_eval.get("ok") or not agent_eval.get("ok"):
            final_text = (
                final_text.rstrip()
                + "\n\n---\n"
                + agent_eval.get("report", "")
                + "\n"
                + final_eval.get("report", "")
            )
        if obj_check.get("advise_additional_work"):
            final_text = (
                final_text.rstrip()
                + "\n\n---\n## Objective completeness note\n"
                + str(obj_check.get("rationale") or "")
                + "\nAdditional work may improve the result; follow-up assignments were "
                + f"queued where applicable ({len(follow_ups)})."
            )

        goal = company.get_goal(goal_id)
        if goal:
            goal["status"] = "done" if (agent_eval.get("ok") and final_eval.get("ok")) else "running"
            goal["ceo_assessment"] = str(obj_check.get("rationale") or "")
            goal["gap_analysis"] = gaps
            goal["kind"] = goal.get("kind") or "objective"
            company.save_goal(goal)

        ok = bool(final_text.strip()) and bool(agent_results)
        prog(
            f"Org pipeline complete · agents {done_count}/{total_agents} done"
            if ok
            else f"Org pipeline finished with issues · agents {done_count}/{total_agents} done"
        )
        return {
            "ok": ok,
            "goal_id": goal_id,
            "agent_results": agent_results,
            "final_text": final_text,
            "agent_evaluation": agent_eval,
            "final_evaluation": final_eval,
            "gap_analysis": gaps,
            "objective_check": obj_check,
            "verification_results": verification_results,
            "follow_up_assignments": [
                {"id": f.get("id"), "title": f.get("title")} for f in follow_ups
            ],
            "ceo_status": ceo_status,
            "task_count": len(created),
            "agents_total": total_agents,
            "agents_done": done_count,
            "agents_failed": failed_count,
            "flow_plan": {
                "source": flow_plan.get("source"),
                "rationale": flow_plan.get("rationale"),
                "ordered_ids": flow_plan.get("ordered_ids"),
                "steps": flow_plan.get("steps"),
            },
            "graph_id": str(graph.get("id") or ""),
            "graph_name": str(graph.get("name") or ""),
            "at": _now(),
        }
    finally:
        orch.end_exclusive_pipeline()


def _dept_from_title(title: str) -> str:
    # titles like "[Engineering] Coder"
    if title.startswith("[") and "]" in title:
        return title[1 : title.index("]")]
    return ""


def format_pipeline_for_chat(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Build chat history: thinking with agent previews + full agent cards + CEO final."""
    msgs: list[dict[str, Any]] = []
    steps: list[str] = []
    agents = list(result.get("agent_results") or [])
    total = int(result.get("agents_total") or len(agents) or 0)
    done_n = int(result.get("agents_done") or len(agents) or 0)
    fail_n = int(result.get("agents_failed") or 0)
    fp = result.get("flow_plan") or {}
    gname = str(result.get("graph_name") or "").strip()
    steps.append(
        f"Org pipeline · agents total {total} · done {done_n}/{total}"
        + (f" · failed {fail_n}" if fail_n else "")
        + (f" · chart “{gname}”" if gname else "")
    )
    steps.append(
        f"CEO planner ({fp.get('source') or 'n/a'}): decided flow before any agent work"
    )
    if fp.get("rationale"):
        steps.append(f"Flow rationale: {str(fp.get('rationale'))[:300]}")
    plan_steps = fp.get("steps") or []
    if plan_steps or fp.get("ordered_ids"):
        steps.append("Planned order:")
        ids = list(fp.get("ordered_ids") or [])
        for i, oid in enumerate(ids, 1):
            why = ""
            for s in plan_steps:
                if str(s.get("id")) == str(oid):
                    why = str(s.get("why") or "")
                    break
            # prefer agent name from results
            name = next(
                (
                    str(a.get("agent_name") or a.get("title") or oid)
                    for a in agents
                    if str(a.get("org_node_id") or "") == str(oid)
                ),
                oid,
            )
            # results may not have org_node_id — use index order
            if name == oid and i <= len(agents):
                name = str(agents[i - 1].get("agent_name") or agents[i - 1].get("title") or oid)
            steps.append(f"  {i}. {name}" + (f" — {why}" if why else ""))
    steps.append("Agents ran in planned order, then CEO synthesized")
    for i, a in enumerate(agents, 1):
        name = a.get("agent_name") or a.get("title") or f"Agent {i}"
        st = a.get("status") or "?"
        body = str(a.get("result") or "").strip()
        n = len(body)
        steps.append(f"[{i}/{total}] {name} → {st} ({n} chars) · progress {i}/{total}")
        if body:
            # Multi-line block inside thinking so expand shows real agent content
            preview = body if len(body) <= 900 else body[:880] + "\n…(open agent card below for full text)"
            for ln in preview.splitlines()[:24]:
                steps.append(f"    {ln}" if ln.strip() else "    ")
        else:
            steps.append("    (no output)")
    ae = result.get("agent_evaluation") or {}
    steps.append(
        f"Agents {done_n}/{total} done · eval: {'pass' if ae.get('ok') else 'issues'} "
        f"({len(ae.get('ok_agents') or [])} ok, {len(ae.get('failed_agents') or [])} failed)"
    )
    steps.append(f"CEO synthesis → {result.get('ceo_status') or 'n/a'}")
    fe = result.get("final_evaluation") or {}
    steps.append(
        f"Final eval: {'pass' if fe.get('ok') else 'review'} "
        f"coverage={float(fe.get('coverage') or 0):.0%}"
    )
    steps.append(
        f"Org pipeline finished · {done_n}/{total} agents done — full cards + CEO answer below"
    )
    msgs.append(
        {
            "role": "thinking",
            "content": "\n".join(f"• {s}" for s in steps),
            "steps": steps,
            "status": "done" if result.get("ok") else "error",
            "collapsed": True,
            "at": _now(),
            "pipeline": "org",
        }
    )
    # ONE user-visible reply only (agent details live inside collapsed Thinking).
    # Separate org_agent cards were showing as many chat "replies" and felt broken.
    final = (result.get("final_text") or "").strip()
    if not final:
        final = "Org pipeline finished but produced no CEO answer. Expand Thinking for agent steps."
    total = int(result.get("agents_total") or len(result.get("agent_results") or []) or 0)
    done_n = int(result.get("agents_done") or total)
    header = (
        f"_Org pipeline · agents {done_n}/{total} done · "
        f"goal `{str(result.get('goal_id') or '')[:8]}`_\n\n"
    )
    msgs.append(
        {
            "role": "assistant",
            "content": header + final,
            "agent_name": "CEO",
            "model": "org-pipeline",
            "at": _now(),
            "org_pipeline": True,
        }
    )
    return msgs
