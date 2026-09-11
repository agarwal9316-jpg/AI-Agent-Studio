"""Format / parse the API context so Chat can show and edit it."""

from __future__ import annotations

from typing import Any

_ROLES = ("system", "user", "assistant")


def format_api_context(messages: list[dict[str, Any]] | None) -> str:
    chunks: list[str] = []
    for m in messages or []:
        role = str(m.get("role") or "user").strip().lower()
        if role not in _ROLES:
            continue
        content = str(m.get("content") or "")
        chunks.append(f"### {role}\n{content}")
    return "\n\n".join(chunks)


def parse_api_context(text: str) -> list[dict[str, str]]:
    lines = (text or "").replace("\r\n", "\n").split("\n")
    out: list[dict[str, str]] = []
    cur_role: str | None = None
    buf: list[str] = []

    def flush() -> None:
        if cur_role is None:
            return
        out.append({"role": cur_role, "content": "\n".join(buf).strip()})

    for line in lines:
        if line.startswith("### "):
            role = line[4:].strip().lower()
            if role in _ROLES:
                flush()
                cur_role = role
                buf = []
                continue
        buf.append(line)
    flush()
    return [m for m in out if m["content"] or m["role"] == "system"]


def preview_chat_context(
    history: list[dict[str, Any]] | None,
    *,
    system_prompt: str = "",
) -> list[dict[str, str]]:
    from app.core.services.chat.chat import build_api_messages

    return build_api_messages(list(history or []), system_prompt=system_prompt or "")
