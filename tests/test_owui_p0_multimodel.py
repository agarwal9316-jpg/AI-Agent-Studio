"""P0.2 — Multi-model parallel chat / arena (OWUI-style).

Mocked parallel completions: concurrency, soft-degrade, no-tools default,
message shaping for the Compare UI.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.services.chat.multimodel import (  # noqa: E402
    COMPARE_SYSTEM_NOTE,
    MAX_COMPARE_MODELS,
    MIN_COMPARE_MODELS,
    CompareResult,
    build_compare_messages,
    make_compare_message,
    normalize_compare_models,
    pick_winning_content,
    run_parallel_completions,
    validate_compare_models,
)


def test_normalize_and_validate_models():
    assert normalize_compare_models(["a", "a", "b", "", "c", "d"]) == ["a", "b", "c"]
    ok, err, cleaned = validate_compare_models(["only-one"])
    assert not ok and MIN_COMPARE_MODELS == 2
    assert "at least" in err.lower()
    ok, err, cleaned = validate_compare_models(["m1", "m2", "m3"])
    assert ok and cleaned == ["m1", "m2", "m3"]
    assert len(cleaned) <= MAX_COMPARE_MODELS
    print("✓ normalize / validate models")


def test_build_compare_messages_is_tool_free():
    msgs = build_compare_messages(
        "Hello arena",
        system_prompt="You are helpful.",
        history=[
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hey", "compare": True},  # skipped
            {"role": "tool", "content": "should skip"},
            {"role": "assistant", "content": "prior answer"},
        ],
    )
    assert msgs[0]["role"] == "system"
    assert COMPARE_SYSTEM_NOTE in msgs[0]["content"]
    assert "helpful" in msgs[0]["content"]
    roles = [m["role"] for m in msgs]
    assert "tool" not in roles
    assert msgs[-1] == {"role": "user", "content": "Hello arena"}
    # compare history entry skipped
    assert not any(m.get("content") == "hey" for m in msgs)
    print("✓ compare messages are tool-free + history filtered")


def test_run_parallel_completions_mocked_order_and_concurrency():
    started: list[float] = []
    finished: list[str] = []

    def fake_completion(**kwargs: Any) -> tuple[str, dict[str, int]]:
        model = kwargs["model"]
        assert kwargs.get("tools") is None
        started.append(time.monotonic())
        # Stagger so slower model finishes later but all overlap
        time.sleep(0.05 if model != "slow" else 0.12)
        finished.append(model)
        return f"reply from {model}", {"prompt_tokens": 1, "completion_tokens": 2}

    t0 = time.monotonic()
    results = run_parallel_completions(
        models=["fast-a", "slow", "fast-b"],
        user_text="compare please",
        api_key="sk-test",
        base_url="https://example.test/v1",
        chat_completion_fn=fake_completion,
        timeout=5.0,
    )
    elapsed = time.monotonic() - t0
    # Parallel: should be closer to slowest (~0.12) than sum (~0.22)
    assert elapsed < 0.22, f"expected parallel overlap, took {elapsed:.3f}s"
    assert [r.model for r in results] == ["fast-a", "slow", "fast-b"]
    assert all(r.ok for r in results)
    assert results[0].content == "reply from fast-a"
    assert all(r.usage.get("completion_tokens") == 2 for r in results)
    print("✓ parallel completions preserve order + overlap")


def test_soft_degrade_one_failure():
    def fake_completion(**kwargs: Any) -> str:
        if kwargs["model"] == "bad":
            raise RuntimeError("provider 500 boom")
        return f"ok:{kwargs['model']}"

    results = run_parallel_completions(
        models=["good", "bad", "also-good"],
        user_text="x",
        api_key="sk-test",
        base_url="https://example.test/v1",
        chat_completion_fn=fake_completion,
    )
    assert len(results) == 3
    assert results[0].ok and results[0].content == "ok:good"
    assert not results[1].ok and results[1].error
    assert "500" in (results[1].error or "") or "boom" in (results[1].error or "")
    assert results[2].ok and results[2].content == "ok:also-good"
    print("✓ soft-degrade: one failure, others still show")


def test_make_compare_message_and_pick_winner():
    results = [
        CompareResult(model="a", ok=True, content="Answer A", elapsed_ms=10),
        CompareResult(model="b", ok=False, error="timeout", elapsed_ms=90),
    ]
    msg = make_compare_message(results, user_text="Q?")
    assert msg["compare"] is True
    assert msg["agent_name"] == "Compare"
    assert msg["role"] == "assistant"
    assert len(msg["compare_results"]) == 2
    assert pick_winning_content(msg["compare_results"][0]) == "Answer A"
    assert "error" in pick_winning_content(msg["compare_results"][1]).lower()
    print("✓ compare message shape + pick winner")


def test_invalid_models_returns_synthetic_error():
    results = run_parallel_completions(
        models=["solo"],
        user_text="x",
        api_key="sk-test",
        base_url="https://example.test/v1",
        chat_completion_fn=MagicMock(),
    )
    assert len(results) == 1
    assert not results[0].ok
    print("✓ invalid model list soft-fails")


if __name__ == "__main__":
    test_normalize_and_validate_models()
    test_build_compare_messages_is_tool_free()
    test_run_parallel_completions_mocked_order_and_concurrency()
    test_soft_degrade_one_failure()
    test_make_compare_message_and_pick_winner()
    test_invalid_models_returns_synthetic_error()
    print("\nAll P0.2 multimodel tests passed.")
