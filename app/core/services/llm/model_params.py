"""Model parameters + max-capability context window management."""

from __future__ import annotations

from typing import Any

from app.core.services.data.storage import load_config, save_config
from app.core.services.data.usage_meter import estimate_tokens_from_text

# Max LLM use defaults: large window + room for long tool-using replies
DEFAULTS = {
    "temperature": 0.4,
    "top_p": 1.0,
    "max_tokens": 0,  # 0 = provider default (often best)
    "presence_penalty": 0.0,
    "frequency_penalty": 0.0,
    "context_window": 128000,  # use large-context models fully
    "context_reserve_reply": 8000,  # leave room for long completions + tools
}


def get_model_params() -> dict[str, Any]:
    cfg = load_config()
    out = dict(DEFAULTS)
    stored = cfg.get("model_params") or {}
    if isinstance(stored, dict):
        for k, v in stored.items():
            if k in out or k in DEFAULTS:
                out[k] = v
    # also top-level overrides
    for k in DEFAULTS:
        if k in cfg and cfg[k] is not None:
            out[k] = cfg[k]
    # coerce types
    try:
        out["temperature"] = float(out.get("temperature", 0.4))
    except (TypeError, ValueError):
        out["temperature"] = 0.4
    try:
        out["top_p"] = float(out.get("top_p", 1.0))
    except (TypeError, ValueError):
        out["top_p"] = 1.0
    try:
        out["max_tokens"] = int(out.get("max_tokens") or 0)
    except (TypeError, ValueError):
        out["max_tokens"] = 0
    try:
        out["context_window"] = max(4000, int(out.get("context_window") or 128000))
    except (TypeError, ValueError):
        out["context_window"] = 128000
    try:
        out["context_reserve_reply"] = max(512, int(out.get("context_reserve_reply") or 8000))
    except (TypeError, ValueError):
        out["context_reserve_reply"] = 8000
    try:
        out["presence_penalty"] = float(out.get("presence_penalty") or 0)
        out["frequency_penalty"] = float(out.get("frequency_penalty") or 0)
    except (TypeError, ValueError):
        out["presence_penalty"] = 0.0
        out["frequency_penalty"] = 0.0
    return out


def save_model_params(params: dict[str, Any]) -> dict[str, Any]:
    cfg = load_config()
    merged = get_model_params()
    for k, v in (params or {}).items():
        if k in DEFAULTS:
            merged[k] = v
    cfg["model_params"] = merged
    cfg["temperature"] = merged["temperature"]
    cfg["max_tokens"] = merged["max_tokens"]
    cfg["context_window"] = merged["context_window"]
    save_config(cfg)
    return get_model_params()


def build_api_body_extras() -> dict[str, Any]:
    p = get_model_params()
    body: dict[str, Any] = {
        "temperature": p["temperature"],
    }
    if p.get("top_p") is not None and float(p["top_p"]) < 1.0:
        body["top_p"] = float(p["top_p"])
    if int(p.get("max_tokens") or 0) > 0:
        body["max_tokens"] = int(p["max_tokens"])
    if abs(float(p.get("presence_penalty") or 0)) > 0.001:
        body["presence_penalty"] = float(p["presence_penalty"])
    if abs(float(p.get("frequency_penalty") or 0)) > 0.001:
        body["frequency_penalty"] = float(p["frequency_penalty"])
    return body


def _norm_role(role: str) -> str:
    r = (role or "user").lower()
    if r not in ("user", "assistant"):
        return "user"
    return r


def trim_messages_to_context(
    messages: list[dict[str, str]],
    *,
    context_window: int | None = None,
    reserve_reply: int | None = None,
    chat_id: str | None = None,
    update_summary: bool = True,
) -> list[dict[str, str]]:
    """
    Max-capability trim:
      1) Single leading system message
      2) Sticky / summary / memory messages (role user marked sticky) prefer keep
      3) Always try to keep the first real user goal
      4) Fill remaining budget with newest messages
      5) Dropped middle → rolling summary (chat_context)
    """
    p = get_model_params()
    budget = int(context_window if context_window is not None else p["context_window"])
    # Never wait for the configured 128k if the live model is ~32k — compact first.
    try:
        from app.core.services.llm.model_limits import get_model_limits

        mx = int((get_model_limits(refresh=False) or {}).get("context_length") or 0)
        if mx > 4000:
            budget = min(budget, mx)
    except Exception:  # noqa: BLE001
        pass
    reserve = int(reserve_reply if reserve_reply is not None else p["context_reserve_reply"])
    allowed = max(2000, budget - reserve)

    if not messages:
        return messages

    # ── split system vs rest ─────────────────────────────────────────────
    system_parts = [
        (m.get("content") or "").strip()
        for m in messages
        if m.get("role") == "system" and (m.get("content") or "").strip()
    ]
    rest_raw = [m for m in messages if m.get("role") != "system"]
    rest: list[dict[str, str]] = []
    for m in rest_raw:
        if m.get("role") == "system":
            rest.append(
                {
                    "role": "user",
                    "content": f"[system]\n{(m.get('content') or '').strip()}",
                }
            )
        else:
            rest.append(
                {
                    "role": _norm_role(str(m.get("role") or "user")),
                    "content": (m.get("content") or "").strip(),
                    **(
                        {"_sticky": True}
                        if (m.get("content") or "").startswith("[Sticky context")
                        or (m.get("content") or "").startswith("[Conversation memory")
                        else {}
                    ),
                }
            )

    system_text = "\n\n".join(system_parts)
    sys_tokens = estimate_tokens_from_text(system_text)
    remaining = allowed - sys_tokens
    if remaining < 400:
        remaining = 400

    # ── classify sticky / first goal / middle ────────────────────────────
    sticky: list[dict[str, str]] = []
    body: list[dict[str, str]] = []
    for m in rest:
        c = m.get("content") or ""
        if m.get("_sticky") or c.startswith("[Sticky context") or c.startswith(
            "[Conversation memory"
        ):
            sticky.append({"role": _norm_role(m.get("role") or "user"), "content": c})
        else:
            body.append({"role": _norm_role(m.get("role") or "user"), "content": c})

    # first user goal (non-context note)
    first_goal: dict[str, str] | None = None
    first_goal_idx = -1
    for i, m in enumerate(body):
        if m.get("role") == "user":
            c = m.get("content") or ""
            if c.startswith("[Context window]") or c.startswith("[Sticky"):
                continue
            first_goal = dict(m)
            first_goal_idx = i
            break

    def tok(m: dict[str, str]) -> int:
        return estimate_tokens_from_text(m.get("content") or "")

    # Budget: sticky first, then first goal, then newest body messages
    kept: list[dict[str, str]] = []
    used = 0

    for m in sticky:
        t = tok(m)
        if used + t > remaining and kept:
            # sticky too big — truncate content
            room = max(200, remaining - used)
            cut = (m.get("content") or "")[: room * 3]  # rough chars
            kept.append({"role": m["role"], "content": cut + "\n…(sticky truncated)"})
            used = remaining
            break
        kept.append({"role": m["role"], "content": m["content"]})
        used += t

    pinned_goal = False
    if first_goal and used < remaining:
        t = tok(first_goal)
        # always try to keep goal unless sticky ate everything
        if used + t <= remaining or not kept:
            if used + t > remaining:
                room = max(100, remaining - used)
                first_goal = {
                    "role": "user",
                    "content": (first_goal.get("content") or "")[: room * 3]
                    + "\n…(goal truncated)",
                }
                t = tok(first_goal)
            kept.append(first_goal)
            used += t
            pinned_goal = True

    # Newest-first fill from body (skip first goal if already pinned)
    recent_budget = max(200, remaining - used)
    selected_idx: list[int] = []
    recent_used = 0
    for i in range(len(body) - 1, -1, -1):
        if pinned_goal and i == first_goal_idx:
            continue
        m = body[i]
        t = tok(m)
        if selected_idx and recent_used + t > recent_budget:
            break
        if not selected_idx and t > recent_budget:
            room = max(100, recent_budget)
            body[i] = {
                "role": m["role"],
                "content": (m.get("content") or "")[: room * 3] + "\n…(truncated)",
            }
            selected_idx.append(i)
            recent_used = recent_budget
            break
        if recent_used + t > recent_budget:
            break
        selected_idx.append(i)
        recent_used += t

    selected_set = set(selected_idx)
    dropped = [
        body[i]
        for i in range(len(body))
        if i not in selected_set and not (pinned_goal and i == first_goal_idx)
    ]
    recent_kept = [body[i] for i in sorted(selected_idx)]
    used += recent_used
    kept.extend(recent_kept)

    # ── rolling summary from dropped ─────────────────────────────────────
    summary_note = ""
    if dropped and update_summary and chat_id:
        try:
            from app.core.services.chat.chat_context import update_rolling_summary

            update_rolling_summary(chat_id, dropped)
            summary_note = (
                f"[Context window] Compressed {len(dropped)} older message(s) into "
                f"rolling summary (budget ~{budget} tokens, reserve {reserve}). "
                f"Sticky memory + summary remain available."
            )
        except Exception:  # noqa: BLE001
            summary_note = (
                f"[Context window] Omitted {len(dropped)} older message(s) to fit "
                f"~{budget} token budget (reserve {reserve} for reply)."
            )
    elif dropped:
        summary_note = (
            f"[Context window] Omitted {len(dropped)} older message(s) to fit "
            f"~{budget} token budget (reserve {reserve} for reply)."
        )

    out: list[dict[str, str]] = []
    if system_text:
        out.append({"role": "system", "content": system_text})
    if summary_note:
        out.append({"role": "user", "content": summary_note})
    for m in kept:
        c = (m.get("content") or "").strip()
        if c:
            out.append({"role": _norm_role(m.get("role") or "user"), "content": c})
    return out
