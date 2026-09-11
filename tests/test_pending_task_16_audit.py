"""Tests for PENDING_TASKS.md #16 — export audit log of all tool calls."""

from __future__ import annotations

import csv
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    fails: list[str] = []

    def check(ok: bool, msg: str) -> None:
        print(("OK  " if ok else "FAIL") + " " + msg)
        if not ok:
            fails.append(msg)

    from app.version import __version__
    from app.core.services.data import audit_log

    check(__version__ == "1.27.82", f"version is 1.27.82 (got {__version__})")

    # Isolate audit file under a temp data dir via monkeypatch of audit_path
    tmp = Path(tempfile.mkdtemp(prefix="audit16_"))
    real_path = audit_log.audit_path
    real_exports = audit_log.exports_dir
    audit_file = tmp / "tool_audit.json"
    exp_dir = tmp / "exports"
    exp_dir.mkdir(parents=True, exist_ok=True)

    audit_log.audit_path = lambda: audit_file  # type: ignore
    audit_log.exports_dir = lambda: exp_dir  # type: ignore
    try:
        audit_log.clear()
        check(audit_log.count() == 0, "empty after clear")

        e1 = audit_log.record(
            "terminal",
            args={"command": "echo hi", "api_key": "sk-abcdefghijklmnopqrstuvwxyz012345"},
            result={"ok": True, "exit_code": 0, "stdout": "hi\n"},
            chat_id="chat-abc",
            session_id="sess-1",
            source="test",
            duration_ms=12,
        )
        check(isinstance(e1, dict) and e1.get("tool") == "terminal", "record returns entry")
        check(e1.get("chat_id") == "chat-abc", "chat_id persisted")
        check(e1.get("status") == "ok", "status ok from result")
        check("sk-abcdefghijklmnopqrstuvwxyz012345" not in (e1.get("args_summary") or ""), "secret truncated/redacted")
        check("REDACTED" in (e1.get("args_summary") or ""), "api_key redacted in args")

        e2 = audit_log.record(
            "read_file",
            args={"path": "README.md"},
            result={"ok": False, "error": "missing"},
            chat_id="chat-abc",
            source="harness",
        )
        check(e2.get("status") == "error", "error status from ok=False")
        check("missing" in (e2.get("error") or ""), "error text stored")

        e3 = audit_log.record(
            "write_file",
            args={"path": "x.py"},
            result={"ok": False, "denied": True, "error": "ask mode"},
            status="denied",
            chat_id="chat-xyz",
            source="harness",
        )
        check(e3.get("status") == "denied", "denied status")

        check(audit_log.count() == 3, f"count == 3 (got {audit_log.count()})")
        listed = audit_log.list_entries(limit=10)
        check(len(listed) == 3, "list_entries returns 3")
        by_chat = audit_log.list_entries(chat_id="chat-abc")
        check(len(by_chat) == 2, "filter by chat_id")
        by_tool = audit_log.list_entries(tool="terminal")
        check(len(by_tool) == 1 and by_tool[0]["tool"] == "terminal", "filter by tool")

        # Soft-degrade: record never raises even with broken path
        audit_log.audit_path = lambda: Path("/proc/does_not_exist_audit_dir_xx/no.json")  # type: ignore
        soft = audit_log.record("noop", args={"a": 1}, result={"ok": True})
        # may return None on failure — must not raise
        check(soft is None or isinstance(soft, dict), "soft-degrade record does not raise")
        audit_log.audit_path = lambda: audit_file  # type: ignore

        # Re-seed for export (soft path may have failed mid-flight)
        audit_log.clear()
        for i in range(5):
            audit_log.record(
                f"tool_{i}",
                args={"i": i, "token": "sk-ORTOKENVALUE1234567890abcd"},
                result={"ok": True},
                chat_id="export-chat",
                source="test",
            )
        check(audit_log.count() == 5, "reseeded 5")

        jpath = exp_dir / "out.json"
        cpath = exp_dir / "out.csv"
        jout = audit_log.export_json(jpath)
        cout = audit_log.export_csv(cpath)
        check(jout.is_file(), "export_json wrote file")
        check(cout.is_file(), "export_csv wrote file")
        payload = json.loads(jout.read_text(encoding="utf-8"))
        check(payload.get("count") == 5, "json export count")
        check(isinstance(payload.get("entries"), list) and len(payload["entries"]) == 5, "json entries")
        with cout.open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        check(len(rows) == 5, "csv rows")
        check("tool" in rows[0] and "args_summary" in rows[0], "csv headers")

        removed = audit_log.rotate(keep=2)
        check(removed == 3, f"rotate removed 3 (got {removed})")
        check(audit_log.count() == 2, "after rotate keep 2")
        n = audit_log.clear()
        check(n == 2 and audit_log.count() == 0, "clear works")

        # summarize helpers
        s = audit_log.summarize_args({"password": "hunter2", "cmd": "ls"})
        check("REDACTED" in s and "hunter2" not in s, "summarize_args redacts password")
        rs = audit_log.summarize_result({"ok": True, "stdout": "x" * 5000})
        check(len(rs) < 2000, "summarize_result truncates")

        st = audit_log.status_summary()
        check(isinstance(st, dict) and "count" in st and "path" in st, "status_summary keys")
    finally:
        audit_log.audit_path = real_path  # type: ignore
        audit_log.exports_dir = real_exports  # type: ignore

    # Harness wiring
    rt = (ROOT / "app" / "services" / "agent_harness" / "runtime.py").read_text(encoding="utf-8")
    check("audit_log" in rt and "record(" in rt, "harness runtime records audit")

    chat = (ROOT / "app" / "core" / "services" / "chat" / "chat.py").read_text(encoding="utf-8")
    check("PENDING #16" in chat or "audit_log" in chat, "chat.py hooks audit_log")
    check("_audit_tool" in chat, "chat has _audit_tool helper")

    aw = (ROOT / "app" / "ui" / "app_window.py").read_text(encoding="utf-8")
    check("Tool call audit log" in aw, "Settings has Tool call audit log")
    check("Export JSON" in aw and "Export CSV" in aw, "Settings Export JSON/CSV")
    check("_export_tool_audit" in aw, "app_window has _export_tool_audit")
    check("Rotate (keep 1000)" in aw or "rotate" in aw.lower(), "optional rotate UI")

    # package exports
    from app.services import audit_log as al2

    check(al2 is not None and hasattr(al2, "export_json"), "app.services.audit_log export")

    pending = (ROOT / "docs" / "PENDING_TASKS.md").read_text(encoding="utf-8")
    row16 = [ln for ln in pending.splitlines() if ln.startswith("| 16 |")]
    check(bool(row16) and "**done**" in row16[0], f"PENDING #16 marked done ({row16[:1]})")

    cl = (ROOT / "docs" / "CHANGELOG.md").read_text(encoding="utf-8")
    check("1.27.82" in cl and "audit" in cl.lower(), "CHANGELOG mentions 1.27.82 audit")

    feat = (ROOT / "docs" / "FEATURES.md").read_text(encoding="utf-8")
    check("audit" in feat.lower() and "tool" in feat.lower(), "FEATURES mentions tool audit")

    ver_files = [
        (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
        json.loads((ROOT / "version_manifest.json").read_text(encoding="utf-8")).get("version"),
    ]
    check(all(v == "1.27.82" for v in ver_files), f"VERSION files are 1.27.82 ({ver_files})")

    # Do not claim #17/#18/#19 changed by this task beyond soft-degrade
    check("| 17 |" in pending and "pending" in [ln for ln in pending.splitlines() if ln.startswith("| 17 |")][0], "#17 still pending")
    check("| 19 |" in pending and "**done**" in [ln for ln in pending.splitlines() if ln.startswith("| 19 |")][0], "#19 still done")

    if fails:
        print("FAILED:", fails)
        return 1
    print("All pending-task #16 audit log checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
