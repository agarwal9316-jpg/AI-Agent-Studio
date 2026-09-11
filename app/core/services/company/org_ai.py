"""AI generation of organisation charts (CEO → managers → AI workers).

Used by:
  - Org chart page “✨ AI create” — designs tree from org kind + requirements
  - Chat “LLM creates org for this goal” (legacy goal still accepted)
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from app.services import workflow_graph as wfg
from app.core.services.data.storage import list_agents, save_agent


MAX_NODES = 28
MAX_AGENTS = 18
# Design calls can be large JSON — long timeout + one retry
# Generous timeouts — never switch the user's model; report status instead
ORG_AI_TIMEOUT_S = 180.0
ORG_AI_TIMEOUT_RETRY_S = 240.0

_SIZE_GUIDE = {
    "small": "Keep it small: 1 CEO + about 2–4 workers total (flat or one layer of managers).",
    "medium": "Medium size: 1 CEO + 2–4 managers/departments + about 4–8 workers total.",
    "large": "Larger org: 1 CEO + several managers + up to ~12 workers; 2–3 hierarchy levels.",
    "custom": "Match the exact seat count requested by the user (including CEO).",
}


def _extract_json_object(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    if "```" in raw:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.I)
        if m:
            raw = m.group(1).strip()
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except (json.JSONDecodeError, TypeError):
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(raw[start : end + 1])
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, TypeError):
            pass
    return None


def org_generation_system_prompt() -> str:
    return """You design hierarchical multi-agent organisation TREES for AI Agent Studio.

The user describes what KIND of organisation they want and their REQUIREMENTS
(not only a single short task). You invent a realistic company tree and fill each
AI worker with permanent prompts so they can do that job.

Output ONLY valid JSON (no markdown, no commentary) with this shape:
{
  "name": "short org chart name",
  "rationale": "1-3 sentences: why this structure fits the user's kind/requirements",
  "nodes": [
    {
      "id": "ceo",
      "type": "ceo",
      "title": "CEO",
      "parent_id": null,
      "order": 0,
      "role": "Chief Executive",
      "goal": "Own the organisation mission and coordinate managers",
      "instructions": "Standing notes for the CEO seat",
      "system_prompt": "Permanent identity + rules for the CEO AI (who they are, decision style, what they never do)",
      "worker_prompt": "How the CEO AI leads, reviews reports, and synthesizes answers for the user"
    },
    {
      "id": "m1",
      "type": "agent",
      "title": "Engineering Manager",
      "parent_id": "ceo",
      "order": 0,
      "role": "Engineering Manager",
      "goal": "Deliver reliable product engineering",
      "instructions": "Manage engineering workers; escalate risks to CEO",
      "system_prompt": "You are the Engineering Manager… (identity, domain expertise, constraints)",
      "worker_prompt": "When given assignments: plan work, delegate, review outputs, report upward…"
    },
    {
      "id": "a1",
      "type": "agent",
      "title": "Backend Engineer",
      "parent_id": "m1",
      "order": 0,
      "role": "Backend Engineer",
      "goal": "Build APIs and services",
      "instructions": "Focus on correctness, tests, and clear handoffs",
      "system_prompt": "You are a Backend Engineer…",
      "worker_prompt": "Execute backend tasks carefully and return structured results…"
    }
  ]
}

Rules:
- Exactly one node with type "ceo" and parent_id null.
- Other nodes: type "agent" (AI workers/managers) or "department" (group label).
- Hierarchy may be multi-level: CEO → managers → workers (parent_id of a child = manager or department or CEO).
- Prefer managers as type "agent" with children under them (not only flat departments).
- Unique short ids (ceo, m1, a1, …).
- Titles human-readable and specific to the organisation kind.
- EVERY agent and the CEO MUST have non-empty system_prompt AND worker_prompt
  tailored to that seat (not copy-paste one generic blob).
- system_prompt = permanent identity, expertise, tone, hard rules.
- worker_prompt = how they operate day-to-day and report results.
- role + goal + instructions also filled for UI/config.
- Match scale to the size guidance in the user message.
- Max 24 nodes; max 14 agents (non-ceo).
"""


def build_org_design_brief(
    *,
    org_kind: str = "",
    requirements: str = "",
    goal: str = "",
    name_hint: str = "",
    size: str = "medium",
    seat_count: int | None = None,
) -> str:
    """
    Build the user message for the org-design LLM.

    Prefer org_kind + requirements. Legacy `goal` is still accepted (chat / pipeline).
    seat_count: optional exact number of seats including CEO.
    """
    kind = (org_kind or "").strip()
    req = (requirements or "").strip()
    legacy = (goal or "").strip()
    hint = (name_hint or "").strip()
    size_key = (size or "medium").strip().lower()
    seats: int | None = None
    try:
        if seat_count is not None:
            seats = max(2, min(MAX_AGENTS + 1, int(seat_count)))
    except (TypeError, ValueError):
        seats = None
    if seats is not None:
        size_key = "custom"

    if size_key not in _SIZE_GUIDE:
        size_key = "medium"

    parts: list[str] = [
        "Design a full organisation TREE for AI Agent Studio.",
        f"Size guidance: {_SIZE_GUIDE[size_key]}",
    ]
    if seats is not None:
        parts.append(
            f"EXACT SEAT COUNT: produce exactly {seats} nodes of type ceo/agent "
            f"(CEO counts as 1). Departments optional and do not count toward the seat total "
            f"if you use them only as labels — prefer counting managers/workers as agent seats. "
            f"Target about {seats} AI-capable seats (ceo + agents)."
        )
    if kind:
        parts.append(f"Kind of organisation I want:\n{kind}")
    if req:
        parts.append(f"My requirements for the tree and roles:\n{req}")
    if legacy and legacy not in (kind, req):
        parts.append(
            "Additional mission / work this org should be able to handle:\n" + legacy
        )
    if not kind and not req and legacy:
        parts.append(
            "User described this mission (infer a suitable organisation kind and structure):\n"
            + legacy
        )
    if not kind and not req and not legacy:
        parts.append(
            "No details given — design a balanced general product company org "
            "with CEO, a few managers, and specialist workers."
        )
    parts.append(
        "CRITICAL: Every ceo and agent node MUST include non-empty system_prompt AND "
        "worker_prompt strings (3–8 sentences each, role-specific). Never leave them blank "
        "or as a single word."
    )
    if hint:
        parts.append(f"Preferred chart name: {hint}")
    return "\n\n".join(parts)


def build_org_user_prompt(goal: str, *, name_hint: str = "") -> str:
    """Backward-compatible wrapper (goal-only callers)."""
    return build_org_design_brief(goal=goal, name_hint=name_hint, size="medium")


def normalize_org_payload(
    payload: dict[str, Any],
    *,
    goal: str = "",
    org_kind: str = "",
) -> dict[str, Any]:
    """Validate and normalize LLM JSON into a saveable graph (nodes + name)."""
    name = str(payload.get("name") or "").strip() or "AI organisation"
    if name in ("AI organisation", "organisation", "Organization"):
        seed = (org_kind or goal or "").strip()
        if seed:
            name = f"{seed[:48].strip()}"

    raw_nodes = payload.get("nodes") or payload.get("org") or []
    if not isinstance(raw_nodes, list):
        raw_nodes = []

    nodes_in: list[dict[str, Any]] = []
    for n in raw_nodes[:MAX_NODES]:
        if not isinstance(n, dict):
            continue
        ntype = str(n.get("type") or "agent").lower().strip()
        if ntype not in ("ceo", "department", "agent", "role", "worker"):
            if ntype in ("dept", "division"):
                ntype = "department"
            else:
                ntype = "agent"
        if ntype in ("role", "worker"):
            ntype = "agent"
        nid = str(n.get("id") or "").strip() or str(uuid.uuid4())[:8]
        sys_p = str(
            n.get("system_prompt") or n.get("system") or n.get("identity") or ""
        ).strip()
        work_p = str(
            n.get("worker_prompt")
            or n.get("prompt")
            or n.get("operating_prompt")
            or ""
        ).strip()
        instr = str(n.get("instructions") or n.get("description") or "").strip()
        role = str(n.get("role") or n.get("agent_role") or "").strip()
        ag_goal = str(n.get("goal") or n.get("agent_goal") or "").strip()
        title = str(n.get("title") or n.get("name") or ntype.title()).strip()

        # Ensure prompts are never empty for seats that run as AI
        if ntype in ("ceo", "agent") and not sys_p:
            sys_p = (
                f"You are {title}"
                + (f", a {role}" if role else "")
                + ". Follow company hierarchy, be precise, and never invent fake credentials."
            )
        if ntype in ("ceo", "agent") and not work_p:
            work_p = (
                f"As {title}, complete assigned work carefully. "
                f"Report clear results upward."
                + (f" Standing goal: {ag_goal}" if ag_goal else "")
            )
        if ntype in ("ceo", "agent") and not instr:
            instr = work_p[:400]

        nodes_in.append(
            {
                "id": nid,
                "type": ntype,
                "title": title,
                "parent_id": n.get("parent_id"),
                "order": int(n.get("order") or 0),
                "instructions": instr,
                "role": role,
                "goal": ag_goal,
                "system_prompt": sys_p,
                "worker_prompt": work_p,
                "agent_id": "",
            }
        )

    # Ensure one CEO
    ceos = [n for n in nodes_in if n["type"] == "ceo"]
    if not ceos:
        ceo_id = "ceo"
        nodes_in.insert(
            0,
            {
                "id": ceo_id,
                "type": "ceo",
                "title": "CEO",
                "parent_id": None,
                "order": 0,
                "instructions": "Lead the organisation and synthesize the final answer.",
                "role": "Chief Executive",
                "goal": "Coordinate the organisation toward its mission",
                "system_prompt": (
                    "You are the CEO of this AI organisation. You set priorities, "
                    "delegate to managers, review results, and produce the final answer for the user."
                ),
                "worker_prompt": (
                    "When given a mission: break it into workstreams, assign managers, "
                    "resolve conflicts, and return a clear executive summary."
                ),
                "agent_id": "",
            },
        )
        ceos = [nodes_in[0]]
    ceo = ceos[0]
    ceo["parent_id"] = None
    for n in ceos[1:]:
        n["type"] = "agent"
        n["parent_id"] = ceo["id"]

    id_set = {n["id"] for n in nodes_in}
    # Fix parent links — allow multi-level managers (agent under agent / ceo)
    for n in nodes_in:
        if n["type"] == "ceo":
            n["parent_id"] = None
            continue
        pid = n.get("parent_id")
        if pid is not None:
            pid = str(pid)
        if not pid or pid not in id_set or pid == n["id"]:
            n["parent_id"] = ceo["id"]
        else:
            n["parent_id"] = pid

    # Cap agents (non-ceo seats)
    agents = [n for n in nodes_in if n["type"] == "agent"]
    if len(agents) > MAX_AGENTS:
        keep_ids = {a["id"] for a in agents[:MAX_AGENTS]}
        nodes_in = [n for n in nodes_in if n["type"] != "agent" or n["id"] in keep_ids]

    # Ensure at least one agent under CEO
    if not any(n["type"] == "agent" for n in nodes_in):
        context = (org_kind or goal or "the organisation mission")[:200]
        nodes_in.append(
            {
                "id": "a-specialist",
                "type": "agent",
                "title": "Specialist",
                "parent_id": ceo["id"],
                "order": 0,
                "instructions": f"Execute specialist work for: {context}",
                "role": "Specialist",
                "goal": f"Support: {context}",
                "system_prompt": (
                    f"You are a Specialist AI worker supporting: {context}. "
                    "Be practical, structured, and honest about limits."
                ),
                "worker_prompt": (
                    "Complete assignments thoroughly. Return findings, risks, and next steps."
                ),
                "agent_id": "",
            }
        )

    # Force non-empty system_prompt / worker_prompt for every AI seat
    out_nodes: list[dict[str, Any]] = []
    for n in nodes_in:
        title = str(n.get("title") or "Worker")
        role = str(n.get("role") or "")
        sys_p = str(n.get("system_prompt") or "").strip()
        work_p = str(n.get("worker_prompt") or "").strip()
        if n.get("type") in ("ceo", "agent") and len(sys_p) < 40:
            sys_p = (
                f"You are {title}"
                + (f", serving as {role}." if role else ".")
                + " You are a permanent member of this AI organisation. "
                "Follow hierarchy, be precise, cite uncertainty, and never invent credentials. "
                "Stay in character for your role when collaborating with other seats."
            )
        if n.get("type") in ("ceo", "agent") and len(work_p) < 40:
            work_p = (
                f"As {title}, execute assigned work carefully. "
                "Break tasks into steps, produce structured results, escalate blockers, "
                "and report clear outcomes to your manager or the CEO."
            )
        out_nodes.append(
            {
                "id": n["id"],
                "type": n["type"],
                "title": n["title"],
                "parent_id": n["parent_id"],
                "order": int(n.get("order") or 0),
                "instructions": n.get("instructions") or work_p[:400],
                "agent_id": "",
                "agent_role": n.get("role") or "",
                "agent_goal": n.get("goal") or "",
                "system_prompt": sys_p,
                "worker_prompt": work_p,
                "enabled": True,
                "status": "idle",
            }
        )

    return {
        "name": name[:80],
        "rationale": str(payload.get("rationale") or "").strip()[:800],
        "nodes": out_nodes,
        "org_kind": (org_kind or "")[:200],
    }


def ensure_agents_for_graph(graph: dict[str, Any]) -> dict[str, Any]:
    """Create Studio agent profiles for each AI seat with system/worker prompts filled."""
    existing = list_agents()
    by_name = {
        str(a.get("name") or "").strip().lower(): a for a in existing if a.get("name")
    }

    for n in graph.get("nodes") or []:
        if n.get("type") not in ("agent", "role", "worker", "ceo"):
            # departments are labels; still ok to skip unless they need agents
            if n.get("type") != "ceo":
                continue
        # Link agent profile for workers and optionally CEO if agent_id empty
        if n.get("type") == "department":
            continue
        if n.get("agent_id") and n.get("type") != "ceo":
            # Refresh prompts on linked profile when AI just created rich prompts
            pass

        title = str(n.get("title") or "Agent").strip()
        key = title.lower()
        sys_p = str(n.get("system_prompt") or "").strip()
        work_p = str(n.get("worker_prompt") or "").strip()
        role = str(n.get("agent_role") or n.get("role") or "Specialist")
        goal = str(
            n.get("agent_goal") or n.get("goal") or n.get("instructions") or "Complete work"
        )[:500]
        backstory = str(n.get("instructions") or work_p or "")[:1500]

        profile = by_name.get(key) if n.get("type") != "ceo" else None
        # Prefer fresh profile when prompts are rich so we don't stick empty legacy agents
        reuse = profile is not None and not (
            sys_p and not str(profile.get("system_prompt") or "").strip()
        )

        if profile is None or (sys_p and not reuse):
            # Unique name if collision with empty-prompt agent
            save_name = title
            if key in by_name and not reuse:
                save_name = f"{title} · {str(graph.get('name') or 'org')[:20]}"
            profile = save_agent(
                {
                    "name": save_name,
                    "role": role,
                    "goal": goal,
                    "backstory": backstory,
                    "system_prompt": sys_p,
                    "worker_prompt": work_p or backstory,
                    "llm_model": "",
                    "llm_base_url": "",
                    "llm_api_key": "",
                }
            )
            by_name[str(profile.get("name") or save_name).strip().lower()] = profile
        else:
            # Prefer richer prompts from the org node (AI create must win over empty stubs)
            changed = False
            old_sp = str(profile.get("system_prompt") or "").strip()
            old_wp = str(profile.get("worker_prompt") or "").strip()
            if sys_p and (len(sys_p) > len(old_sp) or not old_sp):
                profile["system_prompt"] = sys_p
                changed = True
            if work_p and (len(work_p) > len(old_wp) or not old_wp):
                profile["worker_prompt"] = work_p
                changed = True
            if role and (
                not str(profile.get("role") or "").strip()
                or profile.get("role") == "Specialist"
            ):
                profile["role"] = role
                changed = True
            if goal and (
                not profile.get("goal")
                or profile.get("goal") == "Complete work"
            ):
                profile["goal"] = goal
                changed = True
            if backstory and not str(profile.get("backstory") or "").strip():
                profile["backstory"] = backstory
                changed = True
            if changed:
                profile = save_agent(profile)
                by_name[key] = profile

        if n.get("type") != "ceo":
            n["agent_id"] = profile["id"]
        elif not n.get("agent_id"):
            # Optional: CEO can also hold a linked profile for chat-as-CEO
            n["agent_id"] = profile["id"] if profile else n.get("agent_id") or ""

        n["agent_role"] = profile.get("role") or n.get("agent_role") or role
        n["agent_goal"] = profile.get("goal") or n.get("agent_goal") or goal
        n["system_prompt"] = sys_p or profile.get("system_prompt") or n.get("system_prompt") or ""
        n["worker_prompt"] = work_p or profile.get("worker_prompt") or n.get("worker_prompt") or ""
        wfg.normalize_node(n)
    return graph


def graph_from_normalized(
    normalized: dict[str, Any],
    *,
    make_active: bool = True,
    link_agents: bool = True,
) -> dict[str, Any]:
    """Persist a new graph from normalize_org_payload output."""
    nodes = list(normalized.get("nodes") or [])
    for n in nodes:
        wfg.normalize_node(n)
    g = {
        "id": str(uuid.uuid4()),
        "name": normalized.get("name") or "AI organisation",
        "created_at": wfg._now(),
        "updated_at": wfg._now(),
        "nodes": nodes,
        "ai_rationale": normalized.get("rationale") or "",
        "org_kind": normalized.get("org_kind") or "",
        "source": "ai",
    }
    if link_agents:
        g = ensure_agents_for_graph(g)
    g = wfg.save_graph(g)
    if make_active:
        wfg.set_active_graph(g["id"])
    return g


def generate_org_chart(
    goal: str = "",
    *,
    org_kind: str = "",
    requirements: str = "",
    size: str = "medium",
    seat_count: int | None = None,
    name_hint: str = "",
    api_key: str = "",
    model: str = "",
    base_url: str = "",
    timeout_s: float | None = None,
    make_active: bool = True,
    link_agents: bool = True,
    on_status: Any = None,
) -> dict[str, Any]:
    """
    Call LLM and create a saved organisation chart with prompts filled.

    Preferred inputs: org_kind + requirements (+ size or seat_count).
    Legacy: goal alone (chat / Team pipeline) still works.

    Never changes the user's model. Optional on_status(str) reports progress.
    """
    import time

    from app.core.services.misc.app_log import log_event
    from app.core.services.llm.llm import LLMError, chat_completion, chat_completion_stream
    from app.core.services.llm.providers import resolve_active_llm
    from app.core.services.data.storage import load_config

    def _status(msg: str) -> None:
        log_event("org_ai_status", channel="org_ai", message=str(msg)[:400])
        if callable(on_status):
            try:
                on_status(str(msg))
            except Exception:  # noqa: BLE001
                pass

    kind = (org_kind or "").strip()
    req = (requirements or "").strip()
    legacy_goal = (goal or "").strip()
    if not kind and not req and not legacy_goal:
        return {
            "ok": False,
            "error": "Describe what kind of organisation you want (and any requirements).",
        }

    active = resolve_active_llm()
    cfg = load_config()
    key = (api_key or active.get("api_key") or cfg.get("api_key") or "").strip()
    # Use exactly the model the user selected — never swap to another model
    mod = (model or active.get("model") or cfg.get("model") or "gpt-4o-mini").strip()
    base = (
        base_url
        or active.get("base_url")
        or cfg.get("api_base_url")
        or "https://api.openai.com/v1"
    ).strip()
    if not key:
        log_event(
            "org_ai_fail",
            channel="org_ai",
            level="error",
            error="no_api_key",
            model=mod,
            base_url=base,
        )
        return {
            "ok": False,
            "error": "No API key — set one in Settings / Providers or in the AI create LLM section.",
            "model": mod,
            "base_url": base,
        }

    seats: int | None = None
    try:
        if seat_count is not None and str(seat_count).strip() != "":
            seats = max(2, min(MAX_AGENTS + 1, int(seat_count)))
    except (TypeError, ValueError):
        seats = None

    user_msg = build_org_design_brief(
        org_kind=kind,
        requirements=req,
        goal=legacy_goal,
        name_hint=name_hint,
        size=size if seats is None else "custom",
        seat_count=seats,
    )
    messages = [
        {"role": "system", "content": org_generation_system_prompt()},
        {"role": "user", "content": user_msg},
    ]
    t0 = time.time()
    timeout = float(timeout_s or ORG_AI_TIMEOUT_S)
    is_nvidia = "nvidia.com" in base.lower() or "integrate.api.nvidia" in base.lower()
    max_tok = 2800 if (seats or 0) >= 10 or (size or "").lower() == "large" else 2400

    log_event(
        "org_ai_start",
        channel="org_ai",
        model=mod,
        base_url=base,
        size=size,
        seat_count=seats,
        org_kind=kind[:120],
        timeout_s=timeout,
        max_tokens=max_tok,
        key_present=bool(key),
    )
    _status(
        f"Starting design with your model “{mod}”\n"
        f"Base: {base}\n"
        f"Seats: {seats or size} · timeout {int(timeout)}s · log: data/logs/org_ai.log"
    )

    def _call_model(*, use_timeout: float, phase: str) -> str:
        """Use the user-selected model only. Stream first (like Chat), then non-stream once."""
        _status(
            f"Calling “{mod}” ({phase})…\n"
            f"This can take 1–4 minutes for a full org JSON. Keep this window open."
        )
        try:
            text, _usage = chat_completion_stream(
                api_key=key,
                messages=messages,
                model=mod,
                base_url=base,
                timeout=use_timeout,
                normalize_tools=False,
                _transient_retry=False,
            )
            if (text or "").strip():
                _status(f"Received stream reply from “{mod}” ({len(text)} chars). Building chart…")
                return text
            _status(f"Stream from “{mod}” was empty — retrying non-stream on the same model…")
        except LLMError as stream_err:
            log_event(
                "org_ai_stream_fallback",
                channel="org_ai",
                level="warn",
                model=mod,
                error=str(stream_err)[:300],
            )
            _status(
                f"Stream failed on “{mod}”: {stream_err}\n"
                f"Retrying non-stream with the same model (not switching models)…"
            )
        _status(f"Non-stream call to “{mod}” (up to {int(use_timeout)}s)…")
        return str(
            chat_completion(
                api_key=key,
                messages=messages,
                model=mod,
                base_url=base,
                timeout=use_timeout,
                temperature=0.35,
                max_tokens=max_tok,
                normalize_tools=False,
                _transient_retry=False,
            )
            or ""
        )

    raw = ""
    try:
        log_event(
            "org_ai_model_try",
            channel="org_ai",
            model=mod,
            attempt=1,
            timeout_s=timeout,
            mode="user_model_only_stream_first",
        )
        try:
            raw = _call_model(use_timeout=timeout, phase="stream")
        except LLMError as e1:
            # One retry on same model only (longer wait) — never change model
            err1 = str(e1).lower()
            if any(
                x in err1
                for x in ("timed out", "timeout", "504", "502", "524", "gateway", "network")
            ):
                _status(
                    f"Provider error on “{mod}”: {e1}\n"
                    f"Retrying once with the same model (timeout {int(ORG_AI_TIMEOUT_RETRY_S)}s)…"
                )
                log_event(
                    "org_ai_retry_same_model",
                    channel="org_ai",
                    level="warn",
                    model=mod,
                    error=str(e1)[:400],
                    timeout_s=ORG_AI_TIMEOUT_RETRY_S,
                )
                raw = _call_model(
                    use_timeout=float(ORG_AI_TIMEOUT_RETRY_S),
                    phase="retry same model",
                )
            else:
                raise
    except LLMError as e:
        log_event(
            "org_ai_fail",
            channel="org_ai",
            level="error",
            error=str(e)[:500],
            model=mod,
            base_url=base,
            elapsed_s=round(time.time() - t0, 2),
        )
        msg = str(e)
        low = msg.lower()
        if any(x in low for x in ("timed out", "timeout", "504", "524", "gateway")):
            msg = (
                f"❌ Provider timed out / gateway error while using your model:\n"
                f"   {mod}\n   {base}\n\n"
                f"{msg}\n\n"
                f"Your model was NOT changed. Chat can still work because replies are smaller "
                f"and streamed. Org create needs a large JSON (full tree + prompts).\n"
                f"Tips: wait and retry, use fewer seats, or pick a faster model yourself "
                f"in the LLM section and Save LLM settings.\n"
                f"Log: data/logs/org_ai.log"
            )
        elif "404" in msg or "not found" in low:
            msg = (
                f"❌ Model not found on this provider account:\n"
                f"   {mod}\n   {base}\n\n"
                f"{msg}\n\n"
                f"Model was NOT auto-switched. Choose another model in the LLM section "
                f"and click Save LLM settings if you want a different one.\n"
                f"Log: data/logs/org_ai.log"
            )
        else:
            msg = (
                f"❌ Org AI failed with your model “{mod}”:\n{msg}\n\n"
                f"Model was not changed. See data/logs/org_ai.log"
            )
        _status(msg)
        return {
            "ok": False,
            "error": msg,
            "elapsed_s": round(time.time() - t0, 2),
            "model": mod,
            "base_url": base,
        }
    except Exception as e:  # noqa: BLE001
        log_event(
            "org_ai_fail",
            channel="org_ai",
            level="error",
            error=f"{type(e).__name__}: {e}"[:500],
            model=mod,
            elapsed_s=round(time.time() - t0, 2),
        )
        msg = f"❌ LLM failed with your model “{mod}”: {e}"
        _status(msg)
        return {
            "ok": False,
            "error": msg,
            "elapsed_s": round(time.time() - t0, 2),
            "model": mod,
            "base_url": base,
        }

    assert isinstance(raw, str)
    _status(f"Parsing reply from “{mod}” ({len(raw)} chars)…")
    payload = _extract_json_object(raw)
    if not payload:
        log_event(
            "org_ai_fail",
            channel="org_ai",
            level="error",
            error="invalid_json",
            raw_preview=(raw or "")[:300],
            elapsed_s=round(time.time() - t0, 2),
            model=mod,
        )
        msg = (
            f"❌ “{mod}” returned text that is not valid org JSON.\n"
            f"Model was not changed. See data/logs/org_ai.log"
        )
        _status(msg)
        return {
            "ok": False,
            "error": msg,
            "raw_preview": (raw or "")[:400],
            "model": mod,
            "base_url": base,
            "elapsed_s": round(time.time() - t0, 2),
        }

    try:
        _status(f"Building organisation from “{mod}” reply…")
        normalized = normalize_org_payload(
            payload,
            goal=legacy_goal,
            org_kind=kind or legacy_goal[:80],
        )
        if (name_hint or "").strip():
            normalized["name"] = name_hint.strip()[:80]
        graph = graph_from_normalized(
            normalized, make_active=make_active, link_agents=link_agents
        )
    except Exception as e:  # noqa: BLE001
        log_event(
            "org_ai_fail",
            channel="org_ai",
            level="error",
            error=f"build: {e}"[:400],
            elapsed_s=round(time.time() - t0, 2),
            model=mod,
        )
        msg = f"❌ Could not build chart from “{mod}” reply: {e}"
        _status(msg)
        return {
            "ok": False,
            "error": msg,
            "model": mod,
            "base_url": base,
            "elapsed_s": round(time.time() - t0, 2),
        }

    # Count how many seats have real system prompts
    prompted = sum(
        1
        for n in (graph.get("nodes") or [])
        if n.get("type") in ("ceo", "agent", "worker", "role")
        and len(str(n.get("system_prompt") or "").strip()) >= 40
    )
    elapsed = round(time.time() - t0, 2)
    log_event(
        "org_ai_ok",
        channel="org_ai",
        graph_id=graph.get("id"),
        graph_name=graph.get("name"),
        node_count=len(graph.get("nodes") or []),
        prompted_workers=prompted,
        elapsed_s=elapsed,
        model=mod,
        seat_count=seats,
    )
    _status(
        f"✓ Saved “{graph.get('name')}” with model “{mod}” · "
        f"{len(graph.get('nodes') or [])} nodes · {prompted} with system prompts · {elapsed}s"
    )

    return {
        "ok": True,
        "graph": graph,
        "graph_id": graph.get("id"),
        "graph_name": graph.get("name"),
        "rationale": normalized.get("rationale") or "",
        "node_count": len(graph.get("nodes") or []),
        "prompted_workers": prompted,
        "org_kind": kind or "",
        "elapsed_s": elapsed,
        "model": mod,
        "base_url": base,
    }


def summarize_graph_tree(graph: dict[str, Any] | None) -> str:
    """Short text tree for Thinking / status."""
    if not graph:
        return "(no graph)"
    lines = [f"Chart: {graph.get('name') or graph.get('id')}"]
    if graph.get("org_kind"):
        lines.append(f"Kind: {graph.get('org_kind')}")
    if graph.get("ai_rationale"):
        lines.append(f"Why: {str(graph.get('ai_rationale'))[:160]}")
    for n in wfg.walk_tree(graph):
        depth = int(n.get("_depth") or 0)
        pad = "  " * depth
        t = n.get("type") or "?"
        title = n.get("title") or "?"
        role = n.get("agent_role") or n.get("_agent_role") or ""
        has_sp = "✓prompt" if str(n.get("system_prompt") or "").strip() else "no-prompt"
        extra = f" · {role}" if role else ""
        lines.append(f"{pad}- [{t}] {title}{extra} ({has_sp})")
    return "\n".join(lines[:40])
