"""Per-chat findings list — durable task memory (not the context window)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.paths import data_dir

MAX_FINDINGS = 40
MAX_PROMPT_FINDINGS = 20

_ERROR_LINE_RE = re.compile(
    r"(?:^|\n)\s*((?:ModuleNotFoundError|ImportError|AttributeError|SyntaxError|"
    r"NameError|TypeError|ValueError|FileNotFoundError|PermissionError|"
    r"sqlalchemy\.exc\.\w+Error|Error while finding module)[^\n]{8,220})",
    re.I,
)
_TRACE_FILE_RE = re.compile(
    r'File "([^"]+\.py)", line (\d+)',
    re.I,
)
_EDITED_RE = re.compile(
    r"(?:Edited|Wrote|search_replace)\s+(\S+\.(?:py|ts|js|md|json|bat|ps1))",
    re.I,
)
_FINDING_RE = re.compile(
    r"<<<FINDING>>>\s*(.*?)\s*(?:<<<END_FINDING>>>|$)",
    re.I | re.S,
)
_RESOLVE_RE = re.compile(
    r"<<<(?:RESOLVE_FINDING|CLOSE_FINDING)>>>\s*(.*?)\s*(?:<<<END_(?:RESOLVE_FINDING|CLOSE_FINDING)>>>|$)",
    re.I | re.S,
)
_REOPEN_RE = re.compile(
    r"<<<REOPEN_FINDING>>>\s*(.*?)\s*(?:<<<END_REOPEN_FINDING>>>|$)",
    re.I | re.S,
)
_ACTION_FINDING_RE = re.compile(
    r'\{\s*"action"\s*:\s*"finding"\s*,\s*"text"\s*:\s*"((?:\\.|[^"\\])*)"',
    re.I,
)
_ACTION_RESOLVE_RE = re.compile(
    r'\{\s*"action"\s*:\s*"(?:resolve_finding|close_finding)"\s*,\s*"text"\s*:\s*"((?:\\.|[^"\\])*)"',
    re.I,
)
_SKIP_RE = re.compile(
    r"tool omitted|working with tools|timed out after|press enter to exit|"
    r"not recognized as an internal|invalidendofLine",
    re.I,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ledger_path(chat_id: str) -> Path:
    d = data_dir() / "chat_ledgers"
    d.mkdir(parents=True, exist_ok=True)
    cid = (chat_id or "default").replace("/", "_").replace("\\", "_")[:80]
    return d / f"{cid}.json"


def empty_ledger() -> dict[str, Any]:
    return {
        "goal": "",
        "findings": [],
        "last_command": "",
        "last_ok": None,
        "next_hint": "",
        "done_check": "Prove the result is visible (window / test / file).",
        "updated_at": "",
    }


def load_ledger(chat: dict[str, Any] | None = None, chat_id: str = "") -> dict[str, Any]:
    led = empty_ledger()
    cid = chat_id or str((chat or {}).get("id") or "")
    if chat and isinstance(chat.get("task_ledger"), dict):
        led.update({k: chat["task_ledger"].get(k, led.get(k)) for k in led})
        led["findings"] = list(chat["task_ledger"].get("findings") or [])
        return led
    if cid:
        p = _ledger_path(cid)
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    led.update({k: data.get(k, led.get(k)) for k in led})
                    led["findings"] = list(data.get("findings") or [])
            except Exception:  # noqa: BLE001
                pass
    return led


def save_ledger(chat: dict[str, Any] | None, ledger: dict[str, Any]) -> dict[str, Any]:
    ledger = dict(ledger or empty_ledger())
    ledger["updated_at"] = _now()
    findings = list(ledger.get("findings") or [])
    if len(findings) > MAX_FINDINGS:
        # Never drop unique errors — drop oldest facts/success first
        errors = [f for f in findings if f.get("kind") == "error"]
        rest = [f for f in findings if f.get("kind") != "error"]
        keep_rest = rest[-(MAX_FINDINGS - min(len(errors), MAX_FINDINGS)) :]
        ledger["findings"] = (errors + keep_rest)[-MAX_FINDINGS:]
    if chat is not None:
        chat["task_ledger"] = ledger
    cid = str((chat or {}).get("id") or "")
    if cid:
        try:
            _ledger_path(cid).write_text(json.dumps(ledger, indent=2), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    return ledger


def _clip(text: str, n: int = 180) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    if len(t) <= n:
        return t
    return t[: n - 1] + "…"


def _fp(kind: str, text: str) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip().lower())
    t = re.sub(r"[\"']", "", t)
    return f"{kind}:{t[:160]}"


def add_finding(
    ledger: dict[str, Any],
    *,
    kind: str,
    text: str,
    path: str = "",
) -> bool:
    text = _clip(text, 200)
    if len(text) < 8 or _SKIP_RE.search(text):
        return False
    kind = kind if kind in ("error", "success", "fact") else "fact"
    item = {"kind": kind, "text": text, "path": path or "", "at": _now(), "open": True}
    key = _fp(kind, text)
    existing = list(ledger.get("findings") or [])
    for old in existing:
        if _fp(str(old.get("kind") or ""), str(old.get("text") or "")) == key:
            return False
    existing.append(item)
    ledger["findings"] = existing
    return True


def extract_from_text(text: str, *, role: str = "") -> list[dict[str, str]]:
    """Pull error / edit facts from one message body."""
    raw = text or ""
    out: list[dict[str, str]] = []
    if _SKIP_RE.search(raw[:80]) and "Error" not in raw and "Import" not in raw:
        pass
    last_file = ""
    files = _TRACE_FILE_RE.findall(raw)
    if files:
        last_file = files[-1][0]
    for m in _ERROR_LINE_RE.finditer(raw):
        line = _clip(m.group(1), 200)
        out.append({"kind": "error", "text": line, "path": last_file})
    for m in _EDITED_RE.finditer(raw):
        p = m.group(1)
        out.append({"kind": "success", "text": f"Edited {p}", "path": p})
    if role == "assistant":
        for m in _FINDING_RE.finditer(raw):
            t = _clip(m.group(1), 200)
            if t:
                k = "error" if re.search(r"error|fail|cannot|missing", t, re.I) else "fact"
                out.append({"kind": k, "text": t, "path": ""})
        m = _ACTION_FINDING_RE.search(raw)
        if m:
            t = _clip(m.group(1).replace('\\"', '"'), 200)
            if t:
                out.append({"kind": "fact", "text": t, "path": ""})
    return out


def ingest_message(ledger: dict[str, Any], msg: dict[str, Any] | None) -> int:
    if not msg:
        return 0
    role = str(msg.get("role") or "")
    body = str(msg.get("content") or "")
    n = 0
    if role == "assistant":
        n += apply_llm_status_tags(ledger, body)
    for item in extract_from_text(body, role=role):
        if add_finding(ledger, kind=item["kind"], text=item["text"], path=item.get("path") or ""):
            n += 1
    if role == "terminal":
        cmd = str(msg.get("command") or "")
        if cmd:
            ledger["last_command"] = _clip(cmd, 160)
            ledger["last_ok"] = bool(msg.get("ok")) if msg.get("ok") is not None else (
                msg.get("exit_code") == 0
            )
    return n


def backfill_from_history(
    history: list[dict[str, Any]] | None,
    ledger: dict[str, Any] | None = None,
) -> dict[str, Any]:
    led = ledger or empty_ledger()
    for m in history or []:
        ingest_message(led, m)
    return led


def format_for_prompt(ledger: dict[str, Any] | None, *, max_items: int = MAX_PROMPT_FINDINGS) -> str:
    led = ledger or empty_ledger()
    findings = list(led.get("findings") or [])
    if not findings and not led.get("goal"):
        return ""
    lines = [
        "## Findings (task memory — do not rediscover; do not repeat a listed command)",
    ]
    g = str(led.get("goal") or "").strip()
    if g:
        lines.append(f"Goal: {g}")
    open_ones = [f for f in findings if f.get("open") is not False]
    closed = [f for f in findings if f.get("open") is False]
    show = open_ones[-max_items:]
    if not show:
        lines.append("(no open findings)")
    for i, f in enumerate(show, 1):
        k = str(f.get("kind") or "fact").upper()
        extra = f"  [{f.get('path')}]" if f.get("path") else ""
        lines.append(f"{i}. [{k}] {f.get('text')}{extra}")
    last_err = next((f for f in reversed(open_ones) if f.get("kind") == "error"), None)
    if last_err:
        lines.append(f"Latest error to fix next: {last_err.get('text')}")
    if closed:
        lines.append(f"Resolved (do not reopen unless needed): {len(closed)}")
    cmd = str(led.get("last_command") or "").strip()
    if cmd:
        lines.append(f"Last command ({'ok' if led.get('last_ok') else 'FAIL'}): {cmd}")
    if led.get("next_hint"):
        lines.append(f"Next: {led.get('next_hint')}")
    return "\n".join(lines)


def format_for_gui(ledger: dict[str, Any] | None, *, max_items: int = 4) -> str:
    findings = list((ledger or {}).get("findings") or [])
    if not findings:
        return "Findings · click to open list (none yet)"
    open_ones = [f for f in findings if f.get("open") is not False]
    bits: list[str] = []
    for f in open_ones[-max_items:]:
        mark = {"error": "ERR", "success": "OK", "fact": "NOTE"}.get(str(f.get("kind")), "NOTE")
        bits.append(f"{mark}: {f.get('text')}")
    n_err = sum(1 for f in open_ones if f.get("kind") == "error")
    head = f"Findings · {len(open_ones)} open"
    if n_err:
        head += f" · {n_err} errors"
    if len(open_ones) > len(bits):
        head += f" (+{len(open_ones) - len(bits)} more)"
    return head + " · click to open  ·  " + "  |  ".join(bits)


def finding_key(item: dict[str, Any]) -> str:
    return _fp(str(item.get("kind") or ""), str(item.get("text") or ""))


def set_finding_open(ledger: dict[str, Any], key: str, open_now: bool) -> dict[str, Any]:
    needle = re.sub(r"\s+", " ", (key or "").strip().lower())
    for f in list(ledger.get("findings") or []):
        fk = finding_key(f)
        text = re.sub(r"\s+", " ", str(f.get("text") or "").lower())
        if fk == key or (needle and needle in text) or (needle and needle in fk):
            f["open"] = bool(open_now)
    return ledger


def apply_llm_status_tags(ledger: dict[str, Any], text: str) -> int:
    """LLM can close/reopen items: <<<RESOLVE_FINDING>>>Alias<<<END_RESOLVE_FINDING>>>."""
    n = 0
    for m in _RESOLVE_RE.finditer(text or ""):
        set_finding_open(ledger, m.group(1) or "", False)
        n += 1
    for m in _ACTION_RESOLVE_RE.finditer(text or ""):
        set_finding_open(ledger, (m.group(1) or "").replace('\\"', '"'), False)
        n += 1
    for m in _REOPEN_RE.finditer(text or ""):
        set_finding_open(ledger, m.group(1) or "", True)
        n += 1
    return n


def sync_chat_ledger(
    chat: dict[str, Any] | None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Load, backfill if empty, ingest one more message, save onto the chat."""
    ch = chat if isinstance(chat, dict) else {}
    led = load_ledger(ch, str(ch.get("id") or ""))
    if not (led.get("findings") or []):
        backfill_from_history(ch.get("messages") or [], led)
    if extra:
        ingest_message(led, extra)
    g = str(ch.get("current_goal") or "").strip()
    if g:
        led["goal"] = g
    return save_ledger(ch, led)


def last_error_text(ledger: dict[str, Any] | None) -> str:
    for f in reversed((ledger or {}).get("findings") or []):
        if f.get("kind") == "error" and f.get("open") is not False:
            return str(f.get("text") or "")
    return ""
