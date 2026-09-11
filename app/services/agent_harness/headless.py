"""
Headless agent entry: studio_agent -p "prompt" --json
Also importable as run_headless_prompt().
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def run_headless_prompt(
    prompt: str,
    *,
    cwd: str | None = None,
    mode: str = "action",
    max_rounds: int | None = None,
    always_approve: bool = True,
    output_json: bool = False,
) -> dict[str, Any]:
    from app.core.services.data.storage import load_config, save_config

    cfg = load_config()
    if always_approve:
        cfg["agent_permission_mode"] = "always_approve"
        cfg["tool_approval_required"] = False
        save_config(cfg)

    hist: list[dict[str, Any]] = []
    progress: list[str] = []

    def on_progress(msg: str) -> None:
        progress.append(msg)

    from app.core.services.chat.chat import send_user_message

    hist, last = send_user_message(
        prompt,
        history=hist,
        mode=mode,
        terminal_enabled=True,
        skills_enabled=True,
        mcp_enabled=True,
        laptop_enabled=False,
        safety_mode=False,
        terminal_cwd=cwd or str(Path.cwd()),
        on_progress=on_progress,
        stream=False,
        auto_save=False,
        agent_name="Headless",
    )
    out: dict[str, Any] = {
        "ok": True,
        "reply": last,
        "messages": len(hist),
        "progress": progress[-50:],
    }
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="studio-agent", description="AI Agent Studio headless agent")
    p.add_argument("-p", "--prompt", required=False, help="User prompt (or '-' to read from stdin, or use --prompt-file)")
    p.add_argument("--prompt-file", default=None, help="Path to file containing the prompt")
    p.add_argument("--cwd", default=None, help="Working directory")
    p.add_argument("--mode", default="action", choices=("action", "plan"))
    p.add_argument("--json", action="store_true", help="Print JSON result")
    p.add_argument("--always-approve", action="store_true", default=True)
    args = p.parse_args(argv)

    # Resolve prompt from file, stdin, or direct argument
    prompt = args.prompt
    if args.prompt_file:
        prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    elif prompt == "-":
        prompt = sys.stdin.read()

    if not prompt:
        p.error("Prompt is required (use -p, --prompt-file, or pipe to stdin)")

    # ensure app imports work
    root = Path(__file__).resolve().parents[3]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    out = run_headless_prompt(
        prompt,
        cwd=args.cwd,
        mode=args.mode,
        always_approve=args.always_approve,
        output_json=args.json,
    )
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    else:
        reply = out.get("reply") or out.get("last_reply") or out.get("content") or out
        if isinstance(reply, dict):
            print(json.dumps(reply, ensure_ascii=False, indent=2, default=str))
        else:
            print(reply)
    return 0 if out.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
