"""Run multi-AI goals into a Teams-style channel.

Modes:
  - pipeline: existing org_pipeline, posts each agent/CEO into the channel
  - coordinate: agents read the channel and take turns until CEO finals
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from app.services import team_channel as tc
from app.services import workflow_graph as wfg


ProgressCb = Callable[[str], None]


def _prog(cb: ProgressCb | None, msg: str) -> None:
    if cb:
        try:
            cb(msg)
        except Exception:  # noqa: BLE001
            pass


def start_team_goal(
    goal: str,
    *,
    title: str = "",
    org_mode: str = "fixed",
    org_graph_id: str = "",
    run_mode: str = "pipeline",
    max_rounds: int = 12,
    on_progress: ProgressCb | None = None,
    should_stop: Callable[[], bool] | None = None,
    on_channel_ready: Callable[[dict[str, Any]], None] | None = None,
    project_id: str = "",
) -> dict[str, Any]:
    """
    Create channel + resolve org + run pipeline or coordinate mode.

    on_channel_ready: called as soon as the channel exists (UI can open it live).
    Returns {ok, channel, channel_id, final_text, error?, pipe?}
    """
    goal = (goal or "").strip()
    if not goal:
        return {"ok": False, "error": "Empty goal"}

    graph = None
    org_name = ""
    gid = (org_graph_id or "").strip()

    if should_stop and should_stop():
        return {"ok": False, "error": "Stopped by user", "cancelled": True}

    if org_mode == "llm_create":
        _prog(on_progress, "Step 1/3: Designing your AI team for this goal…")
        from app.core.services.company.org_ai import generate_org_chart, summarize_graph_tree

        gen = generate_org_chart(goal, make_active=False, link_agents=True)
        if not gen.get("ok"):
            return {"ok": False, "error": f"AI org create failed: {gen.get('error')}"}
        graph = gen.get("graph")
        gid = str(gen.get("graph_id") or "")
        org_name = str(gen.get("graph_name") or "")
        try:
            for ln in summarize_graph_tree(graph).splitlines()[:12]:
                _prog(on_progress, ln)
        except Exception:  # noqa: BLE001
            pass
    else:
        _prog(on_progress, "Step 1/3: Loading your team setup…")
        graph = wfg.resolve_graph(graph_id=gid or None)
        gid = str(graph.get("id") or "")
        org_name = str(graph.get("name") or "")

    if should_stop and should_stop():
        return {"ok": False, "error": "Stopped by user", "cancelled": True}

    _prog(on_progress, "Step 2/3: Opening team channel…")
    ch = tc.new_channel(
        goal,
        title=title or goal[:60],
        org_graph_id=gid,
        org_name=org_name,
        mode=run_mode if run_mode in ("pipeline", "coordinate") else "pipeline",
        graph=graph,
        max_rounds=max_rounds,
    )
    tc.set_channel_status(ch, "running")
    tc.append_message(
        ch,
        role="system",
        agent_name="System",
        content=(
            f"Goal started.\n\n**{ch.get('title')}**\n\n"
            f"Team: {org_name or 'auto'}\n"
            f"Mode: {'one by one' if ch.get('mode') == 'pipeline' else 'discuss together'}\n\n"
            "You will see each helper post here as they finish. "
            "Press **Stop team** if you want to cancel."
        ),
    )
    _prog(on_progress, f"Channel open: {ch.get('title')} · team={org_name or 'auto'}")

    # Let UI open the feed immediately (before long agent work)
    if on_channel_ready:
        try:
            on_channel_ready(dict(ch))
        except Exception:  # noqa: BLE001
            pass

    _prog(on_progress, "Step 3/3: Team is working… watch the message feed")

    if ch.get("mode") == "coordinate":
        result = run_coordinate_mode(
            ch,
            graph=graph,
            on_progress=on_progress,
            should_stop=should_stop,
        )
    else:
        result = run_pipeline_into_channel(
            ch,
            graph=graph,
            project_id=project_id,
            on_progress=on_progress,
            should_stop=should_stop,
        )

    ch2 = tc.load_channel(str(ch["id"])) or ch
    return {
        "ok": bool(result.get("ok")),
        "channel": ch2,
        "channel_id": ch2.get("id"),
        "final_text": ch2.get("final_text") or result.get("final_text") or "",
        "error": result.get("error"),
        "pipe": result.get("pipe"),
        "mode": ch2.get("mode"),
        "cancelled": bool(result.get("cancelled") or result.get("error") == "Stopped by user"),
    }


def run_pipeline_into_channel(
    ch: dict[str, Any],
    *,
    graph: dict[str, Any] | None = None,
    project_id: str = "",
    on_progress: ProgressCb | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Org pipeline with live posts into the channel (each agent as they finish)."""
    from app.core.services.company.org_pipeline import run_org_pipeline

    goal = str(ch.get("goal") or "")
    g = graph or wfg.resolve_graph(graph_id=str(ch.get("org_graph_id") or "") or None)

    # Mark all agents waiting; CEO waiting
    for r in ch.get("roster") or []:
        r["status"] = "waiting"
    tc.save_channel(ch)

    channel_id = str(ch["id"])
    posted_agent_keys: set[str] = set()
    plan_posted = {"v": False}
    last_working = {"name": ""}

    def progress(msg: str) -> None:
        _prog(on_progress, msg)
        # Heuristic: "running [i/n] Name" → set working + one heartbeat per agent
        m = re.search(r"running\s*\[\d+/\d+\]\s*(.+?)(?:…|\.\.\.|$)", msg, re.I)
        if m:
            name = m.group(1).strip()
            ch_live = tc.load_channel(channel_id) or ch
            for r in ch_live.get("roster") or []:
                if str(r.get("name") or "") in name or name in str(r.get("name") or ""):
                    oid = str(r.get("org_node_id") or "")
                    tc.set_roster_status(ch_live, oid, "working")
                    try:
                        if g and oid:
                            wfg.set_worker_status(g, oid, "running")
                    except Exception:  # noqa: BLE001
                        pass
                    break
            if name and name != last_working["name"]:
                last_working["name"] = name
                try:
                    tc.append_message(
                        ch_live,
                        role="system",
                        agent_name="Progress",
                        content=f"⏳ Working now: **{name}**… (this can take a minute)",
                    )
                except Exception:  # noqa: BLE001
                    pass

    def on_flow_planned(fp: dict[str, Any]) -> None:
        if plan_posted["v"]:
            return
        plan_posted["v"] = True
        ch_live = tc.load_channel(channel_id) or ch
        order = " → ".join(str(x) for x in (fp.get("ordered_ids") or [])[:12])
        # Living plan: one step per planned agent (or roster agents)
        steps: list[dict[str, Any]] = []
        ordered = list(fp.get("ordered_ids") or [])
        roster = list(ch_live.get("roster") or [])
        if ordered:
            for i, oid in enumerate(ordered[:16]):
                name = next(
                    (
                        str(r.get("name") or "")
                        for r in roster
                        if str(r.get("org_node_id") or "") == str(oid)
                    ),
                    str(oid),
                )
                steps.append(
                    {
                        "id": str(oid),
                        "title": name or f"Helper {i+1}",
                        "owner": name,
                        "status": "pending",
                    }
                )
        else:
            for r in roster:
                if r.get("kind") == "ceo":
                    continue
                steps.append(
                    {
                        "id": str(r.get("org_node_id") or r.get("name") or ""),
                        "title": str(r.get("name") or "Helper"),
                        "owner": str(r.get("name") or ""),
                        "status": "pending",
                    }
                )
        steps.append(
            {
                "id": "ceo_final",
                "title": "CEO — write finished answer",
                "owner": "CEO",
                "status": "pending",
            }
        )
        rationale = str(fp.get("rationale") or "Team will work one by one.")
        tc.init_living_plan(
            ch_live,
            steps,
            summary=f"Plan: {rationale[:160]}",
        )
        plan_md = tc.format_living_plan(ch_live)
        tc.append_message(
            ch_live,
            role="ceo",
            agent_name="CEO Planner",
            agent_role="ceo",
            content=(
                f"**Living plan** ({fp.get('source') or 'planner'})\n\n"
                f"{rationale}\n\n"
                f"Who runs: {fp.get('total_agents', len(steps)-1)} helper(s)\n"
                f"Order: {order or '(default tree order)'}\n\n"
                f"```\n{plan_md}\n```"
            ),
            org_node_id=next(
                (
                    r.get("org_node_id")
                    for r in (ch_live.get("roster") or [])
                    if r.get("kind") == "ceo"
                ),
                "",
            ),
        )
        _prog(on_progress, "Living plan posted — agents starting…")

    def on_agent_complete(a: dict[str, Any]) -> None:
        """Post each agent to the feed immediately (not after full pipeline)."""
        key = str(a.get("task_id") or a.get("org_node_id") or a.get("agent_name") or "")
        if key and key in posted_agent_keys:
            return
        if key:
            posted_agent_keys.add(key)
        ch_live = tc.load_channel(channel_id) or ch
        name = str(a.get("agent_name") or a.get("title") or "Agent")
        body = str(a.get("result") or "").strip() or "(no output)"
        # Hide heavy tool log noise from feed body when finalizing later
        body = re.split(r"\n###\s*Tools used this turn\b", body, maxsplit=1, flags=re.I)[0].strip() or body
        st = str(a.get("status") or "")
        oid = str(a.get("org_node_id") or "")
        idx = a.get("index")
        total = a.get("total")
        head = f"**[{a.get('department') or 'Team'}]**"
        if idx and total:
            head += f"  ({idx}/{total})"
        head += f"  status={st}"
        step_status = "done" if st == "done" else ("failed" if st == "failed" else "done")
        if oid:
            tc.set_roster_status(
                ch_live,
                oid,
                step_status,
            )
            # Live org-chart execution map
            try:
                if g and oid:
                    map_st = (
                        "completed"
                        if step_status == "done"
                        else ("error" if step_status == "failed" else "running")
                    )
                    wfg.set_worker_status(g, oid, map_st)
            except Exception:  # noqa: BLE001
                pass
        tc.update_living_plan_step(
            ch_live,
            step_id=oid,
            owner=name,
            title=name,
            status=step_status,
            summary=f"Working: {name} finished ({st or 'done'})",
        )
        tc.append_message(
            ch_live,
            role="agent",
            agent_name=name,
            agent_role=str(a.get("agent_role") or ""),
            org_node_id=oid,
            content=f"{head}\n\n{body}",
        )
        _prog(on_progress, f"Posted to feed: {name} ({st})")

    pipe = run_org_pipeline(
        goal,
        project_id=project_id,
        on_progress=progress,
        should_stop=should_stop,
        force_auto_approve=True,
        graph=g,
        on_agent_complete=on_agent_complete,
        on_flow_planned=on_flow_planned,
    )

    ch = tc.load_channel(channel_id) or ch

    # Fallback: if live posts missed any agents (e.g. older path), post remaining
    for a in pipe.get("agent_results") or []:
        key = str(a.get("task_id") or a.get("org_node_id") or a.get("agent_name") or "")
        if key and key in posted_agent_keys:
            continue
        on_agent_complete(a)

    # Planner fallback if on_flow_planned never fired
    fp = pipe.get("flow_plan") or {}
    if not plan_posted["v"] and (fp.get("rationale") or fp.get("ordered_ids")):
        on_flow_planned(
            {
                **fp,
                "total_agents": len(pipe.get("agent_results") or []),
            }
        )

    final = tc.clean_team_final_text(str(pipe.get("final_text") or "").strip())
    if final:
        ceo_id = next(
            (r.get("org_node_id") for r in (ch.get("roster") or []) if r.get("kind") == "ceo"),
            "",
        )
        if ceo_id:
            tc.set_roster_status(ch, str(ceo_id), "done")
        tc.update_living_plan_step(
            ch,
            step_id="ceo_final",
            owner="CEO",
            title="CEO — write finished answer",
            status="done",
            summary="Complete — finished answer ready",
        )
        tc.append_message(
            ch,
            role="ceo",
            agent_name="CEO",
            agent_role="ceo",
            org_node_id=str(ceo_id or ""),
            content=f"**FINISHED ANSWER**\n\n{final}",
        )
        tc.set_final(ch, final)
        _prog(on_progress, "Finished answer posted ✓")
    elif pipe.get("cancelled"):
        tc.set_channel_status(ch, "cancelled")
        tc.append_message(
            ch, role="system", agent_name="System", content="⏹ Run stopped by you."
        )
        _prog(on_progress, "Stopped by user")
    elif not pipe.get("ok"):
        tc.set_channel_status(ch, "failed")
        tc.append_message(
            ch,
            role="system",
            agent_name="System",
            content=f"Pipeline failed: {pipe.get('error') or 'unknown'}",
        )
        _prog(on_progress, f"Failed: {pipe.get('error') or 'unknown'}")
    else:
        tc.set_channel_status(ch, "done")

    ch = tc.load_channel(channel_id) or ch
    return {
        "ok": bool(pipe.get("ok")) or bool(final),
        "final_text": final,
        "error": pipe.get("error"),
        "pipe": pipe,
        "channel": ch,
        "cancelled": bool(pipe.get("cancelled")),
    }


def run_coordinate_mode(
    ch: dict[str, Any],
    *,
    graph: dict[str, Any] | None = None,
    on_progress: ProgressCb | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """
    Multi-turn coordination: facilitator picks next agent; they post to channel;
    until CEO posts FINAL or max rounds.
    """
    from app.core.services.llm.llm import LLMError, chat_completion
    from app.core.services.llm.providers import resolve_active_llm
    from app.core.services.data.storage import load_config, resolve_agent_llm, get_agent

    channel_id = str(ch["id"])
    g = graph or wfg.resolve_graph(graph_id=str(ch.get("org_graph_id") or "") or None)
    max_rounds = int((ch.get("settings") or {}).get("max_rounds") or 12)
    goal = str(ch.get("goal") or "")

    active = resolve_active_llm()
    cfg = load_config()
    default_key = (active.get("api_key") or cfg.get("api_key") or "").strip()
    default_model = (active.get("model") or cfg.get("model") or "gpt-4o-mini").strip()
    default_base = (
        active.get("base_url") or cfg.get("api_base_url") or "https://api.openai.com/v1"
    ).strip()
    if not default_key:
        tc.append_message(
            ch, role="system", agent_name="System", content="No API key configured."
        )
        tc.set_channel_status(ch, "failed")
        return {"ok": False, "error": "No API key"}

    # Build seat map
    seats: list[dict[str, Any]] = []
    for r in ch.get("roster") or []:
        seats.append(dict(r))
    if not seats:
        seats = tc.roster_from_graph(g)
        ch["roster"] = seats
        tc.save_channel(ch)

    # Living plan for coordinate mode (Task #6)
    coord_steps = []
    for r in seats:
        if r.get("kind") == "ceo":
            continue
        coord_steps.append(
            {
                "id": str(r.get("org_node_id") or r.get("name") or ""),
                "title": str(r.get("name") or "Helper"),
                "owner": str(r.get("name") or ""),
                "status": "pending",
            }
        )
    coord_steps.append(
        {
            "id": "ceo_final",
            "title": "CEO — write finished answer",
            "owner": "CEO",
            "status": "pending",
        }
    )
    tc.init_living_plan(
        ch,
        coord_steps,
        summary=f"Discuss mode · up to {max_rounds} turns",
    )
    tc.append_message(
        ch,
        role="system",
        agent_name="System",
        content="**Living plan**\n\n```\n" + tc.format_living_plan(ch) + "\n```",
    )

    def _llm(
        messages: list[dict[str, str]],
        *,
        agent_id: str = "",
        temperature: float = 0.4,
        max_tokens: int = 1200,
    ) -> str:
        key, model, base = default_key, default_model, default_base
        if agent_id:
            ag = get_agent(agent_id)
            if ag:
                llm = resolve_agent_llm(ag)
                key = (llm.get("api_key") or key).strip()
                model = (llm.get("model") or model).strip()
                base = (llm.get("base_url") or base).strip()
        out = chat_completion(
            api_key=key,
            messages=messages,
            model=model,
            base_url=base,
            timeout=180.0,
            temperature=temperature,
            max_tokens=max_tokens,
            normalize_tools=False,
        )
        text = str(out or "").strip()
        # Empty reply (common with Qwen thinking models) → one forced retry
        if not text:
            retry_msgs = list(messages) + [
                {
                    "role": "user",
                    "content": (
                        "Your previous reply was empty. Answer now with real content only. "
                        "Do not leave the message blank. Write at least 3 sentences of useful output."
                    ),
                }
            ]
            out2 = chat_completion(
                api_key=key,
                messages=retry_msgs,
                model=model,
                base_url=base,
                timeout=180.0,
                temperature=min(0.7, temperature + 0.2),
                max_tokens=max(max_tokens, 2000),
                normalize_tools=False,
            )
            text = str(out2 or "").strip()
        return text

    # Opening CEO plan
    _prog(on_progress, "Coordinate mode: CEO opening plan…")
    ceo_seat = next((s for s in seats if s.get("kind") == "ceo"), seats[0])
    tc.set_roster_status(ch, str(ceo_seat.get("org_node_id") or ""), "working")
    try:
        plan = _llm(
            [
                {
                    "role": "system",
                    "content": (
                        "You are the CEO facilitating a multi-agent team in a shared channel. "
                        "Write a short plan: who should speak and in what spirit. "
                        "List team members and first speaker. Be concise."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Goal:\n{goal}\n\nTeam:\n"
                        + "\n".join(
                            f"- {s.get('name')} ({s.get('role')}) dept={s.get('department')}"
                            for s in seats
                        )
                    ),
                },
            ],
            agent_id=str(ceo_seat.get("agent_id") or ""),
        )
    except (LLMError, Exception) as e:  # noqa: BLE001
        tc.append_message(ch, role="system", agent_name="System", content=f"CEO plan failed: {e}")
        tc.set_channel_status(ch, "failed")
        return {"ok": False, "error": str(e)}

    tc.append_message(
        ch,
        role="ceo",
        agent_name=str(ceo_seat.get("name") or "CEO"),
        agent_role="ceo",
        org_node_id=str(ceo_seat.get("org_node_id") or ""),
        content=f"**Team kickoff**\n\n{plan}",
        round_n=0,
    )
    tc.set_roster_status(ch, str(ceo_seat.get("org_node_id") or ""), "done")

    final_text = ""
    recent_speakers: list[str] = []
    empty_streak = 0

    for round_i in range(1, max_rounds + 1):
        if should_stop and should_stop():
            tc.append_message(ch, role="system", agent_name="System", content="Stopped by user.")
            tc.set_channel_status(ch, "cancelled")
            return {
                "ok": False,
                "error": "Stopped by user",
                "final_text": final_text,
                "cancelled": True,
            }

        ch = tc.load_channel(channel_id) or ch
        ch["round"] = round_i
        tc.save_channel(ch)
        _prog(on_progress, f"Coordinate round {round_i}/{max_rounds}: facilitator…")

        # Last 2 rounds: force wrap-up so goals actually complete
        force_finish = round_i >= max(2, max_rounds - 1)

        transcript = tc.format_channel_transcript(ch, max_msgs=30)
        seat_json = [
            {
                "org_node_id": s.get("org_node_id"),
                "name": s.get("name"),
                "role": s.get("role"),
                "kind": s.get("kind"),
            }
            for s in seats
        ]
        fac_prompt = (
            "You are the facilitator. Read the team channel and decide the next step.\n"
            "Reply ONLY with JSON:\n"
            '{"next":"<org_node_id>|ceo|done","instruction":"what they should do next",'
            '"reason":"why"}\n'
            "Rules:\n"
            "- Use next=done as soon as the team has enough material for a usable user answer "
            "(even if imperfect). Do NOT loop forever.\n"
            "- Prefer agents who have not spoken recently. Never pick the same agent 3 times in a row.\n"
            "- If messages are empty/useless, pick a different agent or next=done.\n"
            "- On the last rounds, prefer next=done so the CEO writes FINAL.\n"
            "- Goal is for the END USER — deliver something concrete, not more process talk."
        )
        if force_finish:
            fac_prompt += "\nIMPORTANT: This is a late round — prefer next=done."

        try:
            fac_raw = _llm(
                [
                    {"role": "system", "content": fac_prompt},
                    {
                        "role": "user",
                        "content": (
                            f"Seats: {json.dumps(seat_json)}\n"
                            f"Recent speakers: {recent_speakers[-6:]}\n\n"
                            f"{transcript}\n\n"
                            f"Round {round_i}/{max_rounds}. Decide next."
                        ),
                    },
                ],
                temperature=0.2,
                max_tokens=400,
            )
        except (LLMError, Exception) as e:  # noqa: BLE001
            _prog(on_progress, f"Facilitator error: {e}")
            empty_streak += 1
            if empty_streak >= 2 or force_finish:
                _prog(on_progress, "Facilitator failing — forcing FINAL…")
                final_text = _ceo_final(ch, seats, goal, _llm, ceo_seat)
                break
            continue

        decision = _parse_facilitator(fac_raw, seats)
        nxt = decision.get("next") or "done"
        instruction = str(decision.get("instruction") or "Contribute toward the goal.")

        if force_finish:
            nxt = "done"

        if nxt == "done":
            _prog(on_progress, "Facilitator requested FINAL…")
            final_text = _ceo_final(ch, seats, goal, _llm, ceo_seat)
            break

        # Resolve seat
        seat = None
        if nxt == "ceo":
            seat = ceo_seat
        else:
            seat = next(
                (s for s in seats if str(s.get("org_node_id") or "") == str(nxt)),
                None,
            )
        if not seat:
            seat = next((s for s in seats if s.get("kind") == "agent"), ceo_seat)

        # Avoid same-agent spam (was hanging Telegram goal on Keyword Search forever)
        oid = str(seat.get("org_node_id") or "")
        if recent_speakers[-2:] == [oid, oid]:
            alt = next(
                (
                    s
                    for s in seats
                    if s.get("kind") == "agent"
                    and str(s.get("org_node_id") or "") not in recent_speakers[-2:]
                ),
                None,
            )
            if alt:
                seat = alt
                oid = str(seat.get("org_node_id") or "")
                instruction = (
                    "Previous agent repeated — add NEW useful content toward the goal, "
                    "or say you are done so CEO can finalize."
                )

        name = str(seat.get("name") or "Agent")
        _prog(on_progress, f"Round {round_i}/{max_rounds}: @{name} speaking (tools ON)…")
        tc.set_roster_status(ch, oid, "working")
        tc.update_living_plan_step(
            ch,
            step_id=oid,
            owner=name,
            title=name,
            status="working",
            summary=f"Round {round_i}/{max_rounds}: {name} working…",
        )

        # Real tool loop: terminal + web search/fetch (same capability as Chat Action)
        from app.core.services.company.team_agent_tools import run_tool_agent

        is_ceo_seat = seat.get("kind") == "ceo"
        try:
            tool_res = run_tool_agent(
                user_brief=(
                    f"## Facilitator instruction\n{instruction}\n\n"
                    f"## Original goal\n{goal}\n\n"
                    + (
                        "If the goal is met, start your message with FINAL: then the complete answer."
                        if is_ceo_seat
                        else "Use TERMINAL / WEB_SEARCH / WEB_FETCH when you need real data. "
                        "Do not invent “I checked” without tool results."
                    )
                ),
                agent_name=name,
                agent_role=str(seat.get("role") or "specialist"),
                department=str(seat.get("department") or "Team"),
                goal=goal,
                agent_id=str(seat.get("agent_id") or ""),
                transcript=tc.format_channel_transcript(ch, max_msgs=25),
                max_tool_rounds=5 if not is_ceo_seat else 4,
                on_progress=on_progress,
                should_stop=should_stop,
                enable_terminal=True,
                enable_web=True,
            )
            reply = str(tool_res.get("text") or "").strip()
            tlog = tool_res.get("tool_log") or []
            # Keep tool log on feed posts; final answer path strips via clean_team_final_text
            feed_reply = reply
            if tlog and reply:
                feed_reply = (
                    reply
                    + "\n\n### Tools used this turn\n"
                    + "\n".join(f"- {x}" for x in tlog[:20])
                )
            if tool_res.get("error") and not reply:
                reply = f"(failed: {tool_res.get('error')})"
                feed_reply = reply
                tc.set_roster_status(ch, oid, "failed")
                tc.update_living_plan_step(ch, step_id=oid, owner=name, status="failed")
                empty_streak += 1
            elif not reply:
                reply = (
                    f"⚠ {name} produced no text after tool rounds. Skipping this turn."
                )
                feed_reply = reply
                tc.set_roster_status(ch, oid, "failed")
                tc.update_living_plan_step(ch, step_id=oid, owner=name, status="failed")
                empty_streak += 1
            else:
                tc.set_roster_status(ch, oid, "done")
                tc.update_living_plan_step(ch, step_id=oid, owner=name, status="done")
                empty_streak = 0
        except (LLMError, Exception) as e:  # noqa: BLE001
            reply = f"(failed to respond: {e})"
            feed_reply = reply
            tc.set_roster_status(ch, oid, "failed")
            tc.update_living_plan_step(ch, step_id=oid, owner=name, status="failed")
            empty_streak += 1

        recent_speakers.append(oid)
        role = "ceo" if is_ceo_seat else "agent"
        post_body = (feed_reply or reply or "").strip() or f"(empty reply from {name})"
        tc.append_message(
            ch,
            role=role,
            agent_name=name,
            agent_role=str(seat.get("role") or role),
            org_node_id=oid,
            content=post_body,
            round_n=round_i,
        )

        if re.match(r"^\s*FINAL\s*:", reply or "", re.I):
            final_text = tc.clean_team_final_text(reply or "")
            tc.set_final(ch, final_text)
            tc.append_message(
                ch,
                role="system",
                agent_name="System",
                content="CEO marked FINAL — goal complete. See green Finished answer.",
            )
            _prog(on_progress, "FINAL received — done")
            break

        # Too many empty turns → force finish rather than hang
        if empty_streak >= 3:
            _prog(on_progress, "Too many empty turns — forcing FINAL…")
            final_text = _ceo_final(ch, seats, goal, _llm, ceo_seat)
            break

    if not final_text:
        # Force CEO synthesis so status becomes done
        _prog(on_progress, "Max rounds or no FINAL — CEO synthesizing…")
        final_text = _ceo_final(ch, seats, goal, _llm, ceo_seat)

    ch = tc.load_channel(channel_id) or ch
    # Guarantee status is not stuck on "running"
    if final_text and str(ch.get("status") or "") != "done":
        tc.set_final(ch, final_text)
        ch = tc.load_channel(channel_id) or ch
    elif not final_text:
        tc.set_channel_status(ch, "failed")
        tc.append_message(
            ch,
            role="system",
            agent_name="System",
            content="Run ended without a finished answer. Edit the goal (simpler) or try One by one mode.",
        )

    return {
        "ok": bool(final_text),
        "final_text": final_text or ch.get("final_text") or "",
        "channel": ch,
    }


def _parse_facilitator(raw: str, seats: list[dict[str, Any]]) -> dict[str, Any]:
    text = (raw or "").strip()
    if "```" in text:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.I)
        if m:
            text = m.group(1).strip()
    try:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            obj = json.loads(text[start : end + 1])
            if isinstance(obj, dict):
                return obj
    except (json.JSONDecodeError, TypeError):
        pass
    # fallback: first agent
    agent = next((s for s in seats if s.get("kind") == "agent"), None)
    return {
        "next": (agent or seats[0]).get("org_node_id") if seats else "done",
        "instruction": "Continue work on the goal.",
        "reason": "fallback parse",
    }


def _ceo_final(
    ch: dict[str, Any],
    seats: list[dict[str, Any]],
    goal: str,
    llm_fn: Any,
    ceo_seat: dict[str, Any],
) -> str:
    oid = str(ceo_seat.get("org_node_id") or "")
    tc.set_roster_status(ch, oid, "working")
    try:
        raw = llm_fn(
            [
                {
                    "role": "system",
                    "content": (
                        "You are the CEO. Write ONE clean final answer for the end user.\n"
                        "Rules:\n"
                        "- Start with FINAL: then the complete answer.\n"
                        "- Plain language; no tool logs, no <<<TOOL>>> blocks, no 'I will search'.\n"
                        "- Include only useful facts and conclusions from the team.\n"
                        "- If the team failed, still give the best answer you can + what is missing."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Goal:\n{goal}\n\n{tc.format_channel_transcript(ch)}",
                },
            ],
            agent_id=str(ceo_seat.get("agent_id") or ""),
            max_tokens=2000,
        )
    except Exception as e:  # noqa: BLE001
        # Fallback: assemble agent posts if CEO LLM fails
        bits = []
        for m in ch.get("messages") or []:
            if m.get("role") in ("agent", "ceo") and m.get("content"):
                bits.append(f"### {m.get('agent_name') or m.get('role')}\n{m.get('content')}")
        if bits:
            raw = "FINAL: " + "\n\n".join(bits[-6:])
        else:
            raw = f"FINAL: (synthesis failed: {e})"
    body = tc.clean_team_final_text(raw or "")
    if not body:
        # Last resort assemble
        parts = [
            str(m.get("content") or "")
            for m in (ch.get("messages") or [])
            if m.get("role") == "agent" and (m.get("content") or "").strip()
        ]
        body = tc.clean_team_final_text("\n\n".join(parts[-4:])) or "(No final answer produced.)"
    tc.set_roster_status(ch, oid, "done")
    tc.update_living_plan_step(
        ch,
        step_id="ceo_final",
        owner=str(ceo_seat.get("name") or "CEO"),
        title="CEO — write finished answer",
        status="done",
        summary="Complete — finished answer ready",
    )
    tc.append_message(
        ch,
        role="ceo",
        agent_name=str(ceo_seat.get("name") or "CEO"),
        agent_role="ceo",
        org_node_id=oid,
        content=f"**FINAL ANSWER**\n\n{body}",
    )
    tc.set_final(ch, body)
    return body
