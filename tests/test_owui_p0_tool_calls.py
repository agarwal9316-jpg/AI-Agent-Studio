"""P0.1 — Structured OpenAI tool_calls (JSON) alongside text blocks.

Unit tests with mocked HTTP: native tool_calls round-trip + text-block fallback
when the provider rejects `tools`.
"""

from __future__ import annotations

import io
import json
import sys
import urllib.error
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.services.llm.llm import (  # noqa: E402
    _convert_tool_calls_to_text_blocks,
    _tools_rejected,
    chat_completion,
    ensure_executable_tool_format,
)
from app.core.services.tools.native_tool_calls import (  # noqa: E402
    append_native_tool_results,
    ensure_tool_call_ids,
    make_tool_result_message,
    prefer_native_openai_tools,
    provider_supports_native_tools,
    sanitize_native_tool_pairs,
    should_send_native_tools,
    tool_calls_to_text_blocks,
)
from app.core.services.chat.chat import build_api_messages  # noqa: E402


def _openai_tool_calls_payload(
    *,
    content: str = "",
    tool_calls: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    msg: dict[str, Any] = {"role": "assistant", "content": content}
    if tool_calls is not None:
        msg["tool_calls"] = tool_calls
    return {
        "choices": [{"message": msg, "finish_reason": "tool_calls" if tool_calls else "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


class _FakeResp:
    def __init__(self, payload: dict[str, Any], code: int = 200):
        self._payload = payload
        self.code = code

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_convert_tool_calls_to_terminal_block():
    tcs = [
        {
            "id": "call_abc",
            "type": "function",
            "function": {
                "name": "run_terminal",
                "arguments": json.dumps({"command": "echo hi"}),
            },
        }
    ]
    blocks = _convert_tool_calls_to_text_blocks(tcs)
    assert "<<<TERMINAL>>>" in blocks
    assert "echo hi" in blocks
    print("✓ convert tool_calls → TERMINAL")


def test_ensure_executable_merges_native_and_content():
    tcs = [
        {
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "web_search",
                "arguments": '{"query": "python tutorials"}',
            },
        }
    ]
    out = ensure_executable_tool_format("Checking…", tcs)
    assert "Checking" in out
    assert "<<<WEB_SEARCH>>>" in out
    assert "python tutorials" in out
    print("✓ ensure_executable merges content + tool_calls")


def test_tools_rejected_heuristic():
    assert _tools_rejected("tools is not supported on this model")
    assert _tools_rejected("Unknown field: tool_choice")
    assert not _tools_rejected("rate limit exceeded")
    print("✓ tools-rejected heuristic")


def test_chat_completion_returns_tool_calls_mocked():
    payload = _openai_tool_calls_payload(
        content="I'll run that.",
        tool_calls=[
            {
                "id": "call_xyz",
                "type": "function",
                "function": {
                    "name": "run_terminal",
                    "arguments": '{"command": "dir"}',
                },
            }
        ],
    )
    with patch("urllib.request.urlopen", return_value=_FakeResp(payload)):
        content, usage, tcs = chat_completion(  # type: ignore[misc]
            api_key="sk-test",
            messages=[{"role": "user", "content": "list files"}],
            model="gpt-test",
            base_url="https://example.test/v1",
            return_usage=True,
            return_tool_calls=True,
            tools=[{"type": "function", "function": {"name": "run_terminal"}}],
            normalize_tools=True,
            _tools_retry=False,
            _transient_retry=False,
        )
    assert "<<<TERMINAL>>>" in content  # dual-path conversion for execution
    assert "dir" in content
    assert usage.get("prompt_tokens") == 10
    assert tcs and tcs[0]["id"] == "call_xyz"
    assert tcs[0]["function"]["name"] == "run_terminal"
    print("✓ mocked HTTP returns structured tool_calls + text blocks")


def test_soft_degrade_retries_without_tools():
    """Provider 400 rejecting tools → retry text-only; still normalizes content JSON."""
    calls: list[dict[str, Any]] = []

    def fake_urlopen(req, timeout=0):  # noqa: ANN001
        body = json.loads(req.data.decode("utf-8"))
        calls.append(body)
        if body.get("tools"):
            raise urllib.error.HTTPError(
                req.full_url,
                400,
                "Bad Request",
                hdrs=None,  # type: ignore[arg-type]
                fp=io.BytesIO(b'{"error":{"message":"tools is not supported"}}'),
            )
        # text-only success with JSON tool in content
        return _FakeResp(
            _openai_tool_calls_payload(
                content=json.dumps({"terminal": "echo fallback"}),
                tool_calls=None,
            )
        )

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        content, usage = chat_completion(  # type: ignore[misc]
            api_key="sk-test",
            messages=[{"role": "user", "content": "hi"}],
            model="gpt-test",
            base_url="https://example.test/v1",
            return_usage=True,
            tools=[{"type": "function", "function": {"name": "run_terminal"}}],
            normalize_tools=True,
            _transient_retry=False,
        )
    assert len(calls) == 2
    assert "tools" in calls[0]
    assert "tools" not in calls[1]
    assert "<<<TERMINAL>>>" in content
    assert "echo fallback" in content
    print("✓ soft-degrade: tools rejected → text-only retry")


def test_prefer_native_default_on():
    assert prefer_native_openai_tools({}) is True
    assert prefer_native_openai_tools({"prefer_native_openai_tools": False}) is False
    assert prefer_native_openai_tools({"prefer_native_openai_tools": True}) is True
    print("✓ prefer_native default ON")


def test_should_send_native_tools_respects_toggle_and_mode():
    assert should_send_native_tools(mode="plan", cfg={"prefer_native_openai_tools": True}) is False
    assert should_send_native_tools(
        mode="action", cfg={"prefer_native_openai_tools": False}, provider_id="openai"
    ) is False
    assert should_send_native_tools(
        mode="action", cfg={"prefer_native_openai_tools": True}, provider_id="openai"
    ) is True
    assert provider_supports_native_tools("openrouter")
    print("✓ should_send_native_tools gating")


def test_append_native_tool_results_pairs_role_tool():
    hist: list[dict[str, Any]] = [
        {
            "role": "assistant",
            "content": "<<<TERMINAL>>>\necho hi\n<<<END_TERMINAL>>>",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "run_terminal",
                        "arguments": '{"command": "echo hi"}',
                    },
                }
            ],
        },
        {"role": "terminal", "content": "### terminal\nexit 0\nhi"},
    ]
    appended = append_native_tool_results(
        hist, asst_index=0, tool_calls=hist[0]["tool_calls"]
    )
    assert len(appended) == 1
    assert appended[0]["role"] == "tool"
    assert appended[0]["tool_call_id"] == "call_1"
    assert "exit 0" in appended[0]["content"]
    assert hist[1].get("_native_paired") is True
    assert hist[0].get("_native_tools") is True
    print("✓ append_native_tool_results → role:tool")


def test_build_api_messages_emits_openai_tool_pairs():
    hist = [
        {"role": "user", "content": "list files"},
        {
            "role": "assistant",
            "content": "Running dir",
            "tool_calls": [
                {
                    "id": "call_9",
                    "type": "function",
                    "function": {"name": "run_terminal", "arguments": '{"command":"dir"}'},
                }
            ],
            "_hide_ui": True,
            "_tool_round": True,
            "_native_tools": True,
        },
        {
            "role": "terminal",
            "content": "file list…",
            "_native_paired": True,
        },
        make_tool_result_message(
            tool_call_id="call_9", name="run_terminal", content="file list…"
        ),
    ]
    api = build_api_messages(hist, system_prompt="sys")
    roles = [m["role"] for m in api]
    assert roles[0] == "system"
    assert "assistant" in roles
    assert "tool" in roles
    asst = next(m for m in api if m["role"] == "assistant" and m.get("tool_calls"))
    assert asst["tool_calls"][0]["id"] == "call_9"
    tool = next(m for m in api if m["role"] == "tool")
    assert tool["tool_call_id"] == "call_9"
    # Paired UI terminal must not also become a fake user turn
    user_blobs = [m["content"] for m in api if m["role"] == "user"]
    assert not any(str(c).startswith("[terminal]") for c in user_blobs)
    print("✓ build_api_messages native tool pairs")


def test_sanitize_drops_orphan_tool_calls():
    msgs = [
        {"role": "system", "content": "s"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_ok",
                    "type": "function",
                    "function": {"name": "run_terminal", "arguments": "{}"},
                },
                {
                    "id": "call_orphan",
                    "type": "function",
                    "function": {"name": "web_search", "arguments": "{}"},
                },
            ],
        },
        {"role": "tool", "tool_call_id": "call_ok", "content": "ok"},
    ]
    clean = sanitize_native_tool_pairs(msgs)
    asst = next(m for m in clean if m["role"] == "assistant")
    ids = {tc["id"] for tc in asst["tool_calls"]}
    assert ids == {"call_ok"}
    print("✓ sanitize_native_tool_pairs")


def test_tool_calls_to_text_blocks_helper():
    tcs = ensure_tool_call_ids(
        [
            {
                "function": {
                    "name": "read_file",
                    "arguments": {"path": "app/main.py"},
                }
            }
        ]
    )
    assert tcs[0]["id"].startswith("call_")
    blocks = tool_calls_to_text_blocks(tcs)
    assert "<<<READ_FILE>>>" in blocks
    assert "app/main.py" in blocks
    print("✓ tool_calls_to_text_blocks + ensure ids")


def test_text_block_path_still_works_without_native():
    """Dual-path: pure text blocks remain executable via ensure_executable."""
    text = "<<<WEB_SEARCH>>>\nopenai tools\n<<<END_WEB_SEARCH>>>"
    out = ensure_executable_tool_format(text, None)
    assert "<<<WEB_SEARCH>>>" in out
    assert "openai tools" in out
    print("✓ text-block path unchanged")


if __name__ == "__main__":
    test_convert_tool_calls_to_terminal_block()
    test_ensure_executable_merges_native_and_content()
    test_tools_rejected_heuristic()
    test_chat_completion_returns_tool_calls_mocked()
    test_soft_degrade_retries_without_tools()
    test_prefer_native_default_on()
    test_should_send_native_tools_respects_toggle_and_mode()
    test_append_native_tool_results_pairs_role_tool()
    test_build_api_messages_emits_openai_tool_pairs()
    test_sanitize_drops_orphan_tool_calls()
    test_tool_calls_to_text_blocks_helper()
    test_text_block_path_still_works_without_native()
    print("\nAll P0.1 tool-call tests passed.")
