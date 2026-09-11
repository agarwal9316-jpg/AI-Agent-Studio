"""Git helpers for the agent (status, diff, log, commit, branch)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from app.services.agent_harness.sandbox import check_path_access


def _run(args: list[str], cwd: str | Path | None) -> dict[str, Any]:
    try:
        r = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=60,
        )
        return {
            "ok": r.returncode == 0,
            "exit_code": r.returncode,
            "stdout": (r.stdout or "")[:20000],
            "stderr": (r.stderr or "")[:4000],
            "cmd": " ".join(args),
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "cmd": " ".join(args)}


def git_status(cwd: str | Path | None = None) -> dict[str, Any]:
    chk = check_path_access(cwd or ".", write=False)
    if not chk.get("ok"):
        return chk
    root = chk["path"]
    st = _run(["git", "status", "-sb"], root)
    br = _run(["git", "branch", "--show-current"], root)
    return {
        "ok": st.get("ok"),
        "cwd": root,
        "branch": (br.get("stdout") or "").strip(),
        "status": st.get("stdout"),
        "stderr": st.get("stderr"),
    }


def git_diff(cwd: str | Path | None = None, *, staged: bool = False) -> dict[str, Any]:
    chk = check_path_access(cwd or ".", write=False)
    if not chk.get("ok"):
        return chk
    args = ["git", "diff"]
    if staged:
        args.append("--staged")
    r = _run(args, chk["path"])
    r["cwd"] = chk["path"]
    return r


def git_log(cwd: str | Path | None = None, *, n: int = 10) -> dict[str, Any]:
    chk = check_path_access(cwd or ".", write=False)
    if not chk.get("ok"):
        return chk
    r = _run(["git", "log", f"-{max(1, min(50, n))}", "--oneline", "--decorate"], chk["path"])
    r["cwd"] = chk["path"]
    return r


def git_add(paths: list[str] | None = None, cwd: str | Path | None = None) -> dict[str, Any]:
    chk = check_path_access(cwd or ".", write=True)
    if not chk.get("ok"):
        return chk
    args = ["git", "add"]
    if paths:
        args.extend(paths)
    else:
        args.append("-A")
    r = _run(args, chk["path"])
    r["cwd"] = chk["path"]
    return r


def git_commit(message: str, cwd: str | Path | None = None) -> dict[str, Any]:
    chk = check_path_access(cwd or ".", write=True)
    if not chk.get("ok"):
        return chk
    msg = (message or "").strip()
    if not msg:
        return {"ok": False, "error": "empty commit message"}
    r = _run(["git", "commit", "-m", msg], chk["path"])
    r["cwd"] = chk["path"]
    return r


def git_branch(name: str | None = None, cwd: str | Path | None = None) -> dict[str, Any]:
    chk = check_path_access(cwd or ".", write=bool(name))
    if not chk.get("ok"):
        return chk
    if name:
        r = _run(["git", "checkout", "-b", name], chk["path"])
    else:
        r = _run(["git", "branch", "-vv"], chk["path"])
    r["cwd"] = chk["path"]
    return r
