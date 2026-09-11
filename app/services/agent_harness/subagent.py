"""
Lightweight subagents: run a child chat loop with limited tools / own context,
return a summary to the parent. Not a full Grok host, but real parallel isolation.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from typing import Any, Callable

from app.paths import data_dir
from app.core.services.data.storage import load_config

_lock = threading.Lock()
_runs: dict[str, dict[str, Any]] = {}


AGENT_TYPES = {
    "general-purpose": {
        "label": "General purpose",
        "system_extra": "You are a focused subagent. Complete the task and return a clear summary.",
        "tools": "all",
    },
    "explore": {
        "label": "Explore (read-only)",
        "system_extra": (
            "You are a read-only explore agent. Use read_file, list_dir, grep, web_search only. "
            "Do not write or run destructive commands. End with findings."
        ),
        "tools": "read",
    },
    "plan": {
        "label": "Plan",
        "system_extra": (
            "You are a planning agent. Explore the codebase with read tools, write a structured "
            "implementation plan (context, approach, files, verification). Do not implement."
        ),
        "tools": "read",
    },
}


def _count_running() -> int:
    with _lock:
        return sum(1 for v in _runs.values() if v.get("status") == "running")


def spawn_subagent(
    prompt: str,
    *,
    subagent_type: str = "general-purpose",
    cwd: str | None = None,
    max_rounds: int = 8,
    background: bool = True,
    on_progress: Callable[[str], None] | None = None,
    parent_run_id: str = "",
    timeout_sec: float | None = None,
) -> dict[str, Any]:
    """
    Start a child agent. If background=True, returns subagent_id immediately.
    Honors parallel/time caps (Task #14).
    """
    from app.core.services.tools.tool_budget import check_and_consume, get_parallel_caps

    caps = get_parallel_caps()
    max_conc = int(caps.get("max_concurrent_subagents") or 4)
    if _count_running() >= max_conc:
        return {
            "ok": False,
            "error": (
                f"Too many concurrent subagents ({max_conc}). "
                "Wait for some to finish or raise Settings → Parallel agents."
            ),
            "budget": "concurrent",
        }
    if parent_run_id:
        ok_b, msg_b = check_and_consume(parent_run_id, "subagent", 1)
        if not ok_b:
            return {"ok": False, "error": msg_b, "budget": "subagent"}

    st = (subagent_type or "general-purpose").lower()
    if st not in AGENT_TYPES:
        st = "general-purpose"
    t_limit = float(
        timeout_sec
        if timeout_sec is not None
        else caps.get("subagent_timeout_sec") or 180
    )
    sid = uuid.uuid4().hex[:12]
    meta: dict[str, Any] = {
        "id": sid,
        "type": st,
        "prompt": (prompt or "")[:2000],
        "status": "running",
        "started": time.time(),
        "ended": None,
        "summary": "",
        "error": None,
        "cwd": cwd,
        "timeout_sec": t_limit,
        "parent_run_id": parent_run_id or "",
        "timed_out": False,
    }
    with _lock:
        _runs[sid] = meta

    def runner() -> None:
        try:
            summary = _run_child(
                prompt,
                agent_type=st,
                cwd=cwd,
                max_rounds=max_rounds,
                on_progress=on_progress,
                subagent_id=sid,
                deadline=time.time() + max(10.0, t_limit),
            )
            with _lock:
                cur = _runs.get(sid) or {}
                if cur.get("status") == "running":
                    _runs[sid].update(
                        {
                            "status": "completed",
                            "ended": time.time(),
                            "summary": summary,
                        }
                    )
            _persist(sid)
        except TimeoutError as e:
            with _lock:
                _runs[sid].update(
                    {
                        "status": "timeout",
                        "ended": time.time(),
                        "error": str(e),
                        "summary": f"Subagent timed out after {t_limit:.0f}s",
                        "timed_out": True,
                    }
                )
            _persist(sid)
        except Exception as e:  # noqa: BLE001
            with _lock:
                _runs[sid].update(
                    {
                        "status": "error",
                        "ended": time.time(),
                        "error": str(e),
                        "summary": f"Subagent failed: {e}",
                    }
                )
            _persist(sid)

    t = threading.Thread(target=runner, name=f"subagent-{sid}", daemon=True)
    t.start()
    if not background:
        t.join(timeout=max(15.0, t_limit + 5.0))
        return get_subagent(sid)
    return {"ok": True, "subagent_id": sid, "status": "running", "type": st, "timeout_sec": t_limit}


def spawn_parallel(
    tasks: list[dict[str, Any]] | list[str],
    *,
    cwd: str | None = None,
    max_rounds: int = 6,
    parent_run_id: str = "",
    wait: bool = True,
    on_progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """
    Run multiple subagents in parallel with budget/time caps (Task #14).

    tasks: list of strings (prompts) or dicts {prompt, type?, max_rounds?}.
    """
    from app.core.services.tools.tool_budget import get_parallel_caps

    caps = get_parallel_caps()
    max_batch = int(caps.get("max_parallel_batch") or 4)
    batch_timeout = float(caps.get("parallel_timeout_sec") or 300)
    sub_timeout = float(caps.get("subagent_timeout_sec") or 180)

    raw: list[dict[str, Any]] = []
    for t in tasks or []:
        if isinstance(t, str):
            if t.strip():
                raw.append({"prompt": t.strip(), "type": "general-purpose"})
        elif isinstance(t, dict):
            p = str(t.get("prompt") or t.get("task") or t.get("content") or "").strip()
            if p:
                raw.append(
                    {
                        "prompt": p,
                        "type": str(t.get("type") or t.get("subagent_type") or "general-purpose"),
                        "max_rounds": int(t.get("max_rounds") or max_rounds),
                    }
                )
    if not raw:
        return {"ok": False, "error": "No parallel tasks provided"}

    truncated = False
    if len(raw) > max_batch:
        raw = raw[:max_batch]
        truncated = True

    started: list[dict[str, Any]] = []
    for item in raw:
        r = spawn_subagent(
            item["prompt"],
            subagent_type=str(item.get("type") or "general-purpose"),
            cwd=cwd,
            max_rounds=int(item.get("max_rounds") or max_rounds),
            background=True,
            on_progress=on_progress,
            parent_run_id=parent_run_id,
            timeout_sec=sub_timeout,
        )
        started.append(r)
        if on_progress:
            try:
                on_progress(
                    f"parallel spawn: {r.get('subagent_id') or r.get('error') or '?'}"
                )
            except Exception:  # noqa: BLE001
                pass

    ids = [str(s.get("subagent_id") or "") for s in started if s.get("ok") and s.get("subagent_id")]
    if not wait:
        return {
            "ok": True,
            "parallel": True,
            "subagent_ids": ids,
            "started": started,
            "truncated": truncated,
            "max_batch": max_batch,
            "waiting": False,
        }

    # Wait for all or batch timeout
    deadline = time.time() + max(15.0, batch_timeout)
    results: list[dict[str, Any]] = []
    remaining = set(ids)
    while remaining and time.time() < deadline:
        done_now = []
        for sid in list(remaining):
            snap = get_subagent(sid)
            if snap.get("status") != "running":
                results.append(snap)
                done_now.append(sid)
        for sid in done_now:
            remaining.discard(sid)
        if remaining:
            time.sleep(0.25)
    # Timed-out remainders
    for sid in remaining:
        snap = get_subagent(sid)
        if snap.get("status") == "running":
            with _lock:
                if sid in _runs and _runs[sid].get("status") == "running":
                    _runs[sid].update(
                        {
                            "status": "timeout",
                            "ended": time.time(),
                            "timed_out": True,
                            "error": f"parallel batch timeout ({batch_timeout:.0f}s)",
                            "summary": _runs[sid].get("summary")
                            or f"(still running at batch timeout {batch_timeout:.0f}s)",
                        }
                    )
                    _persist(sid)
            snap = get_subagent(sid)
        results.append(snap)

    summaries = []
    for r in results:
        summaries.append(
            {
                "id": r.get("id") or r.get("subagent_id"),
                "status": r.get("status"),
                "type": r.get("type"),
                "summary": (r.get("summary") or r.get("error") or "")[:4000],
                "timed_out": bool(r.get("timed_out")),
            }
        )
    ok_n = sum(1 for s in summaries if s.get("status") == "completed")
    return {
        "ok": True,
        "parallel": True,
        "subagent_ids": ids,
        "results": summaries,
        "completed": ok_n,
        "total": len(summaries),
        "truncated": truncated,
        "max_batch": max_batch,
        "batch_timeout_sec": batch_timeout,
        "report": _format_parallel_report(summaries),
    }


def _format_parallel_report(summaries: list[dict[str, Any]]) -> str:
    lines = ["## Parallel agent results", ""]
    for i, s in enumerate(summaries, 1):
        st = s.get("status") or "?"
        lines.append(f"### [{i}] {s.get('type') or 'agent'} — {st} (`{s.get('id')}`)")
        lines.append(str(s.get("summary") or "(empty)")[:3000])
        lines.append("")
    return "\n".join(lines)


def _run_child(
    prompt: str,
    *,
    agent_type: str,
    cwd: str | None,
    max_rounds: int,
    on_progress: Callable[[str], None] | None,
    subagent_id: str,
    deadline: float | None = None,
) -> str:
    from app.services.agent_harness import project_rules
    from app.services.agent_harness.runtime import dispatch_named_tool, harness_tool_instructions
    from app.core.services.llm.llm import chat_completion
    from app.core.services.llm.providers import resolve_active_llm
    from app.core.services.web.web_search import run_search_command

    info = AGENT_TYPES[agent_type]
    active = resolve_active_llm()
    cfg = load_config()
    api_key = (active.get("api_key") or cfg.get("api_key") or "").strip()
    model = (active.get("model") or cfg.get("model") or "gpt-4o-mini").strip()
    base_url = (
        active.get("base_url") or cfg.get("api_base_url") or "https://api.openai.com/v1"
    ).strip()

    rules = project_rules.inject_block(cwd)
    system = (
        f"You are Studio subagent [{agent_type}].\n"
        f"{info['system_extra']}\n\n"
        f"{harness_tool_instructions(compact=True)}\n\n"
        f"{rules}\n"
        "When done, write a final answer with no more tool blocks.\n"
        "Work cwd hint: " + str(cwd or ".")
    )
    hist: list[dict[str, str]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]
    last = ""
    read_only = info["tools"] == "read"
    allowed_read = {
        "read_file",
        "list_dir",
        "grep",
        "web_search",
        "git_status",
        "git_diff",
        "git_log",
        "project_rules",
    }

    for i in range(max(1, max_rounds)):
        if deadline is not None and time.time() >= deadline:
            raise TimeoutError(f"subagent {subagent_id} hit time cap")
        if on_progress:
            try:
                on_progress(f"subagent {subagent_id} round {i + 1}")
            except Exception:  # noqa: BLE001
                pass
        try:
            from app.core.services.tools.tool_schemas import studio_openai_tools

            _tools = studio_openai_tools(include_harness=True)
        except Exception:  # noqa: BLE001
            _tools = None
        # Cap LLM call timeout to remaining budget
        llm_timeout = 120.0
        if deadline is not None:
            llm_timeout = max(15.0, min(120.0, deadline - time.time()))
        reply = chat_completion(
            api_key=api_key,
            messages=hist,
            model=model,
            base_url=base_url,
            timeout=llm_timeout,
            tools=_tools,
            tool_choice="auto" if _tools else None,
            normalize_tools=True,
        )
        assert isinstance(reply, str)
        last = reply
        hist.append({"role": "assistant", "content": reply})

        # Parse simple harness text blocks via dispatch (JSON already normalized by llm)
        from app.services.agent_harness.runtime import extract_harness_blocks

        blocks = extract_harness_blocks(reply)
        if not blocks:
            break
        tool_notes: list[str] = []
        for b in blocks:
            if deadline is not None and time.time() >= deadline:
                raise TimeoutError(f"subagent {subagent_id} hit time cap during tools")
            name = b.get("tool") or ""
            if read_only and name not in allowed_read:
                tool_notes.append(f"{name}: blocked (read-only subagent)")
                continue
            args = b.get("args") or {}
            if cwd and "path" not in args and name in ("list_dir", "grep", "read_file"):
                args.setdefault("path", cwd if name != "read_file" else args.get("path"))
            if name == "web_search":
                res = run_search_command({"query": args.get("query") or args.get("q") or "", "max": "8", "fetch": "0"})
            else:
                res = dispatch_named_tool(name, args, cwd=cwd, chat_id=f"sub_{subagent_id}")
            tool_notes.append(f"### {name}\n```json\n{json.dumps(res, ensure_ascii=False)[:8000]}\n```")
        hist.append({"role": "user", "content": "Tool results:\n\n" + "\n\n".join(tool_notes)})

    # Persist transcript snippet
    out_dir = data_dir() / "subagents"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{subagent_id}.json").write_text(
        json.dumps({"id": subagent_id, "type": agent_type, "prompt": prompt, "final": last}, indent=2),
        encoding="utf-8",
    )
    return (last or "").strip()[:12000]


def get_subagent(subagent_id: str, *, wait_ms: int = 0) -> dict[str, Any]:
    sid = (subagent_id or "").strip()
    deadline = time.time() + max(0, wait_ms) / 1000.0
    while True:
        with _lock:
            t = _runs.get(sid)
            if not t:
                # try disk
                p = data_dir() / "subagents" / f"{sid}.json"
                if p.exists():
                    try:
                        data = json.loads(p.read_text(encoding="utf-8"))
                        return {"ok": True, "id": sid, "status": "completed", "summary": data.get("final"), **data}
                    except Exception:  # noqa: BLE001
                        pass
                return {"ok": False, "error": f"unknown subagent: {sid}"}
            snap = dict(t)
        if snap.get("status") != "running" or wait_ms <= 0:
            return {"ok": True, **snap}
        if time.time() >= deadline:
            return {"ok": True, **snap, "waiting": True}
        time.sleep(0.2)


def _persist(sid: str) -> None:
    with _lock:
        t = dict(_runs.get(sid) or {})
    if not t:
        return
    d = data_dir() / "subagents"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{sid}_meta.json").write_text(json.dumps(t, indent=2, default=str), encoding="utf-8")


def list_subagents() -> list[dict[str, Any]]:
    with _lock:
        return [dict(v) for v in _runs.values()]
