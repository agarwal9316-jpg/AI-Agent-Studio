"""OWUI-inspired multi-model parallel chat / arena (P0.2).

One user prompt → 2–3 models answer concurrently. Soft-degrade: one failure
does not block others. Compare mode is intentionally **text-only** (no tools /
native tool_calls) to avoid parallel tool-execution chaos.

Ideas adapted from Open WebUI `selectedModels` + side-by-side responses —
reimplemented cleanly for Studio (no GPL blobs).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

# Soft limits (OWUI allows more; Studio keeps UI readable)
MIN_COMPARE_MODELS = 2
MAX_COMPARE_MODELS = 3

COMPARE_SYSTEM_NOTE = (
    "You are answering in a multi-model compare / arena mode. "
    "Give a clear, helpful text reply only. Do not call tools, emit tool blocks, "
    "or request side effects — read-only text answers."
)


@dataclass
class CompareResult:
    model: str
    ok: bool
    content: str = ""
    error: str | None = None
    elapsed_ms: int = 0
    usage: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def normalize_compare_models(models: list[str] | None) -> list[str]:
    """Dedupe, strip, clamp to 2–3 unique model ids."""
    out: list[str] = []
    seen: set[str] = set()
    for m in models or []:
        mid = str(m or "").strip()
        if not mid or mid.startswith("(") or mid in seen:
            continue
        seen.add(mid)
        out.append(mid)
        if len(out) >= MAX_COMPARE_MODELS:
            break
    return out


def validate_compare_models(models: list[str] | None) -> tuple[bool, str, list[str]]:
    cleaned = normalize_compare_models(models)
    if len(cleaned) < MIN_COMPARE_MODELS:
        return (
            False,
            f"Pick at least {MIN_COMPARE_MODELS} different models to compare.",
            cleaned,
        )
    if len(cleaned) > MAX_COMPARE_MODELS:
        cleaned = cleaned[:MAX_COMPARE_MODELS]
    return True, "", cleaned


def build_compare_messages(
    user_text: str,
    *,
    system_prompt: str = "",
    history: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build a short, tool-free message list for each model."""
    msgs: list[dict[str, Any]] = []
    sys_parts = [COMPARE_SYSTEM_NOTE]
    sp = (system_prompt or "").strip()
    if sp:
        # Keep compact — compare is not Action mode
        if len(sp) > 2000:
            sp = sp[:2000].rstrip() + "\n…"
        sys_parts.append(sp)
    msgs.append({"role": "system", "content": "\n\n".join(sys_parts)})
    # Optional prior turns (user/assistant only, capped)
    prior = []
    for m in history or []:
        role = (m.get("role") or "").lower()
        if role not in ("user", "assistant"):
            continue
        if m.get("compare") or m.get("_streaming") or m.get("_hide_ui"):
            continue
        content = str(m.get("content") or "").strip()
        if not content:
            continue
        prior.append({"role": role, "content": content[:4000]})
    # Keep last few turns only
    if len(prior) > 8:
        prior = prior[-8:]
    msgs.extend(prior)
    msgs.append({"role": "user", "content": (user_text or "").strip() or "(empty)"})
    return msgs


def _one_completion(
    *,
    model: str,
    api_key: str,
    base_url: str,
    messages: list[dict[str, Any]],
    timeout: float,
    temperature: float | None,
    max_tokens: int | None,
    chat_completion_fn: Callable[..., Any] | None = None,
) -> CompareResult:
    import time

    t0 = time.monotonic()
    try:
        fn = chat_completion_fn
        if fn is None:
            from app.core.services.llm.llm import chat_completion as fn  # type: ignore

        out = fn(
            api_key=api_key,
            messages=messages,
            model=model,
            base_url=base_url,
            timeout=timeout,
            return_usage=True,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=None,  # explicit: no tools in compare
            normalize_tools=True,
        )
        usage: dict[str, int] = {}
        content = ""
        if isinstance(out, tuple):
            content = str(out[0] or "")
            if len(out) > 1 and isinstance(out[1], dict):
                usage = {str(k): int(v) for k, v in out[1].items() if str(v).lstrip("-").isdigit()}
        else:
            content = str(out or "")
        elapsed = int((time.monotonic() - t0) * 1000)
        return CompareResult(
            model=model,
            ok=True,
            content=content.strip() or "(empty reply)",
            elapsed_ms=elapsed,
            usage=usage,
        )
    except Exception as e:  # noqa: BLE001 — soft-degrade per model
        elapsed = int((time.monotonic() - t0) * 1000)
        try:
            from app.core.services.llm.llm import format_llm_error_message

            err = format_llm_error_message(e)
        except Exception:  # noqa: BLE001
            err = str(e)
        return CompareResult(
            model=model,
            ok=False,
            content="",
            error=err,
            elapsed_ms=elapsed,
        )


def run_parallel_completions(
    *,
    models: list[str],
    user_text: str,
    api_key: str,
    base_url: str,
    system_prompt: str = "",
    history: list[dict[str, Any]] | None = None,
    timeout: float = 90.0,
    temperature: float | None = 0.4,
    max_tokens: int | None = None,
    max_workers: int | None = None,
    chat_completion_fn: Callable[..., Any] | None = None,
    on_model_done: Callable[[CompareResult], None] | None = None,
) -> list[CompareResult]:
    """Run 2–3 model completions in a thread pool; preserve input order.

    Tools are never sent. Failures become CompareResult(ok=False) so siblings
    still appear in the UI.
    """
    ok, err, cleaned = validate_compare_models(models)
    if not ok:
        # Single synthetic failure for the UI / tests
        return [
            CompareResult(model="(compare)", ok=False, error=err or "invalid models")
        ]

    messages = build_compare_messages(
        user_text, system_prompt=system_prompt, history=history
    )
    workers = max_workers or min(len(cleaned), MAX_COMPARE_MODELS)
    results_by_model: dict[str, CompareResult] = {}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                _one_completion,
                model=mid,
                api_key=api_key,
                base_url=base_url,
                messages=messages,
                timeout=timeout,
                temperature=temperature,
                max_tokens=max_tokens,
                chat_completion_fn=chat_completion_fn,
            ): mid
            for mid in cleaned
        }
        for fut in as_completed(futures):
            mid = futures[fut]
            try:
                res = fut.result()
            except Exception as e:  # noqa: BLE001
                res = CompareResult(model=mid, ok=False, error=str(e))
            results_by_model[mid] = res
            if on_model_done:
                try:
                    on_model_done(res)
                except Exception:  # noqa: BLE001
                    pass

    # Preserve picker order
    ordered = [results_by_model[m] for m in cleaned if m in results_by_model]
    return ordered


def make_compare_message(
    results: list[CompareResult] | list[dict[str, Any]],
    *,
    user_text: str = "",
) -> dict[str, Any]:
    """Build a chat history message for the arena pane."""
    rows: list[dict[str, Any]] = []
    for r in results:
        if isinstance(r, CompareResult):
            rows.append(r.to_dict())
        elif isinstance(r, dict):
            rows.append(dict(r))
    ok_n = sum(1 for r in rows if r.get("ok"))
    summary_bits = [f"{ok_n}/{len(rows)} models replied"]
    for r in rows:
        label = str(r.get("model") or "?")
        if r.get("ok"):
            preview = str(r.get("content") or "").strip().replace("\n", " ")[:80]
            summary_bits.append(f"· {label}: {preview}…")
        else:
            summary_bits.append(f"· {label}: error")
    return {
        "role": "assistant",
        "agent_name": "Compare",
        "compare": True,
        "compare_results": rows,
        "content": "Multi-model compare\n" + "\n".join(summary_bits[:6]),
        "at": datetime.now(timezone.utc).isoformat(),
        "user_prompt": user_text,
    }


def pick_winning_content(result: dict[str, Any] | CompareResult) -> str:
    if isinstance(result, CompareResult):
        if result.ok:
            return result.content
        return f"(compare error for {result.model}: {result.error})"
    if result.get("ok"):
        return str(result.get("content") or "")
    return f"(compare error for {result.get('model')}: {result.get('error')})"


__all__ = [
    "MIN_COMPARE_MODELS",
    "MAX_COMPARE_MODELS",
    "COMPARE_SYSTEM_NOTE",
    "CompareResult",
    "normalize_compare_models",
    "validate_compare_models",
    "build_compare_messages",
    "run_parallel_completions",
    "make_compare_message",
    "pick_winning_content",
]
