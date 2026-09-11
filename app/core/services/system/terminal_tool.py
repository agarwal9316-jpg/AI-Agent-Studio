"""Run shell commands for the LLM — unrestricted by default."""

from __future__ import annotations

import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable

TERMINAL_BLOCK_RE = re.compile(
    r"<<<TERMINAL>>>\s*(.*?)\s*<<<END_TERMINAL>>>",
    re.DOTALL | re.IGNORECASE,
)

# Active process (for Stop button kill)
_active_lock = threading.Lock()
_active_proc: Any = None


def kill_active_terminal() -> bool:
    """Kill currently running terminal process if any. Returns True if killed."""
    global _active_proc
    with _active_lock:
        proc = _active_proc
    if proc is None:
        return False
    try:
        if proc.poll() is None:
            proc.kill()
            try:
                proc.wait(timeout=3)
            except Exception:  # noqa: BLE001
                pass
            return True
    except Exception:  # noqa: BLE001
        pass
    return False

# Soft threshold only for optional user choice on huge output
LARGE_OUTPUT_CHARS = 200_000
# Default: no truncation unless user chooses
DEFAULT_TIMEOUT_SEC = 300  # generous; was 45
MAX_ROUNDS = 50  # was 6 — high by default

# Optional safety patterns — OFF by default (empty). Enable only if safety_mode=True.
OPTIONAL_BLOCKED_PATTERNS = [
    re.compile(r"format\s+[a-z]:", re.I),
    re.compile(r"rm\s+-rf\s+/\s*", re.I),
]


_FAIL_STDERR_RE = re.compile(
    r"(ModuleNotFoundError|ImportError|Traceback \(most recent call last\)|"
    r"Error while finding module|SyntaxError|NameError|IndentationError|"
    r"not recognized as an internal|ParserError|InvalidEndOfLine|"
    r"The filename, directory name, or volume label syntax is incorrect|"
    r"Application exited with error)",
    re.I,
)
_WIN_PATH_RE = re.compile(
    r'(?<!["\'])([A-Za-z]:\\(?:[^\\/:*?"<>|\r\n&]+\\)*'
    r'[^\\/:*?"<>|\r\n&]*?)'
    r'(?=\s+-\w|\s*&&|\s*\|\||\s*$|["\'])'
)
_CMD_C_RE = re.compile(r"^\s*cmd(?:\.exe)?\s+/c\s+", re.I)
_FILE_DUMP_CMD_RE = re.compile(
    r"^\s*(type|Get-Content|gc|cat|less|more)\s+"
    r"[\"']?(.+?\.(?:py|ts|js|tsx|jsx|java|cs|md|json|txt|bat|ps1|xml|yml|yaml))[\"']?\s*$",
    re.I,
)
_HAS_LIMIT_RE = re.compile(
    r"\|\s*Select-Object|-TotalCount|-First\b|\|\s*head\b",
    re.I,
)


def command_fingerprint(cmd: str) -> str:
    return re.sub(r"\s+", " ", (cmd or "").strip()).lower()


def quote_windows_paths(cmd: str) -> str:
    """Wrap unquoted C:\\… paths that contain spaces so cmd/PowerShell do not split them."""

    def _repl(m: re.Match[str]) -> str:
        p = (m.group(1) or "").rstrip()
        while p and p[-1] in ".,;:":
            p = p[:-1]
        if " " in p:
            return f'"{p}"'
        return p

    return _WIN_PATH_RE.sub(_repl, cmd or "")


def unwrap_cmd_c(cmd: str) -> str | None:
    raw = (cmd or "").strip()
    if not _CMD_C_RE.match(raw):
        return None
    inner = _CMD_C_RE.sub("", raw, count=1).strip()
    if len(inner) >= 2 and inner[0] == inner[-1] and inner[0] in "\"'":
        inner = inner[1:-1]
    return inner


def looks_like_source_dump_cmd(cmd: str) -> str:
    """If this is `type file.py` / Get-Content without a limit, return the path."""
    t = (cmd or "").strip()
    if not t or _HAS_LIMIT_RE.search(t):
        return ""
    m = _FILE_DUMP_CMD_RE.match(t)
    return (m.group(2) if m else "").strip()


def should_use_cmd_exe(cmd: str) -> bool:
    low = (cmd or "").lower()
    if "start-process" in low:
        return False
    if _CMD_C_RE.match(cmd or "") or "cd /d" in low:
        return True
    if "&&" in (cmd or "") and re.search(r"[A-Za-z]:\\", cmd or ""):
        return True
    return False


def prepare_windows_command(cmd: str) -> tuple[list[str], str]:
    """Return (argv, display_cmd) for Windows. Quotes paths; uses cmd.exe when needed."""
    raw = (cmd or "").strip()
    inner = unwrap_cmd_c(raw)
    body = quote_windows_paths(inner if inner is not None else raw)
    if should_use_cmd_exe(raw) or inner is not None:
        return ["cmd.exe", "/c", body], body
    # PowerShell 5 does not accept bash-style &&
    if "&&" in body and "start-process" not in body.lower():
        body = re.sub(r"\s*&&\s*", "; ", body)
    return [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        body,
    ], body


def stderr_means_failure(stderr: str, stdout: str = "") -> str:
    blob = f"{stderr or ''}\n{stdout or ''}"
    m = _FAIL_STDERR_RE.search(blob)
    if not m:
        return ""
    return m.group(1)


def extract_terminal_commands(text: str) -> list[str]:
    """Extract shell commands from <<<TERMINAL>>> blocks.

    Accepts raw body (preferred) or labeled forms produced by converters:
      command: Start-Process chrome
      cmd: dir
    """
    cmds: list[str] = []
    for m in TERMINAL_BLOCK_RE.finditer(text or ""):
        cmd = (m.group(1) or "").strip()
        if not cmd:
            continue
        # Strip common key:value wrappers from JSON→text converters
        low = cmd.lower()
        for prefix in ("command:", "cmd:", "text:", "shell:"):
            if low.startswith(prefix):
                cmd = cmd[len(prefix) :].strip()
                break
        # Multi-line body: if first line is only a label, drop it
        lines = cmd.splitlines()
        if lines and re.match(r"^(command|cmd|text|shell)\s*:\s*$", lines[0], re.I):
            cmd = "\n".join(lines[1:]).strip()
        if cmd:
            cmds.append(cmd)
    return cmds


def is_blocked(command: str, *, safety_mode: bool = False) -> str | None:
    """No blocks unless safety_mode is explicitly True."""
    if not safety_mode:
        return None
    for pat in OPTIONAL_BLOCKED_PATTERNS:
        if pat.search(command):
            return f"Blocked by optional safety mode: {pat.pattern}"
    return None


def run_command(
    command: str,
    *,
    cwd: str | Path | None = None,
    timeout: float = DEFAULT_TIMEOUT_SEC,
    safety_mode: bool = False,
    ask_large_output: Callable[[int, str], str] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """
    Execute one shell command (cancellable via should_stop / kill_active_terminal).
    ask_large_output(len, preview) -> 'full'|'head'|'tail'|'truncate'
    """
    global _active_proc
    cmd = (command or "").strip()
    if not cmd:
        return {
            "ok": False,
            "command": cmd,
            "error": "Empty command",
            "stdout": "",
            "stderr": "",
            "exit_code": None,
        }

    blocked = is_blocked(cmd, safety_mode=safety_mode)
    if blocked:
        return {
            "ok": False,
            "command": cmd,
            "error": blocked,
            "stdout": "",
            "stderr": blocked,
            "exit_code": None,
        }

    # Filesystem sandbox profiles — deny shell when profile.allow_shell is False
    # or cwd is outside allowed roots.
    try:
        from app.services.agent_harness.sandbox import check_shell_access

        _shell = check_shell_access(cwd)
        if not _shell.get("ok"):
            err = str(_shell.get("error") or "Sandbox denied shell")
            return {
                "ok": False,
                "command": cmd,
                "error": err,
                "stdout": "",
                "stderr": err,
                "exit_code": None,
                "denied": True,
                "sandbox_profile": _shell.get("profile"),
            }
    except Exception:  # noqa: BLE001
        pass

    dump_path = looks_like_source_dump_cmd(cmd)
    if dump_path:
        return {
            "ok": False,
            "command": cmd,
            "error": (
                f"Do not dump source with type/Get-Content ({dump_path}). "
                f"Use <<<READ_FILE>>>\\npath: {dump_path}\\n<<<END_READ_FILE>>> instead."
            ),
            "stdout": "",
            "stderr": "",
            "exit_code": None,
        }

    workdir = Path(cwd) if cwd else Path.cwd()
    if not workdir.is_dir():
        return {
            "ok": False,
            "command": cmd,
            "error": f"Working directory does not exist: {workdir}",
            "stdout": "",
            "stderr": "",
            "exit_code": None,
        }

    display_cmd = cmd
    if os.name == "nt":
        full, display_cmd = prepare_windows_command(cmd)
    else:
        full = ["bash", "-lc", cmd]

    try:
        try:
            from app.core.services.data.activity_log import log as alog

            alog(f"$ {display_cmd}", source="terminal")
        except Exception:  # noqa: BLE001
            pass

        proc = subprocess.Popen(
            full,
            cwd=str(workdir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
        )
        with _active_lock:
            _active_proc = proc

        deadline = time.time() + float(timeout)
        cancelled = False
        while proc.poll() is None:
            if should_stop and should_stop():
                cancelled = True
                try:
                    proc.kill()
                except Exception:  # noqa: BLE001
                    pass
                break
            if time.time() > deadline:
                try:
                    proc.kill()
                except Exception:  # noqa: BLE001
                    pass
                out, err = proc.communicate(timeout=5)
                return {
                    "ok": False,
                    "command": cmd,
                    "error": f"Timed out after {timeout}s",
                    "stdout": out or "",
                    "stderr": (err or "") + f"\nTimed out after {timeout}s",
                    "exit_code": None,
                    "cwd": str(workdir),
                }
            time.sleep(0.08)

        try:
            out, err = proc.communicate(timeout=5)
        except Exception:  # noqa: BLE001
            out, err = "", ""
        out = out or ""
        err = err or ""

        with _active_lock:
            if _active_proc is proc:
                _active_proc = None

        if cancelled:
            try:
                from app.core.services.data.activity_log import log as alog

                alog("terminal cancelled by Stop", source="terminal")
            except Exception:  # noqa: BLE001
                pass
            return {
                "ok": False,
                "command": cmd,
                "error": "Cancelled by user (Stop)",
                "stdout": out,
                "stderr": err + "\nCancelled by user (Stop)",
                "exit_code": proc.returncode,
                "cwd": str(workdir),
                "cancelled": True,
            }

        try:
            from app.core.services.data.activity_log import log as alog

            if out:
                alog(out[-1500:], source="stdout")
            if err:
                alog(err[-800:], source="stderr")
            alog(f"exit={proc.returncode}", source="terminal")
        except Exception:  # noqa: BLE001
            pass

        def maybe_trim(label: str, text: str) -> str:
            if len(text) <= LARGE_OUTPUT_CHARS or ask_large_output is None:
                return text  # no default truncation
            choice = ask_large_output(len(text), text[:500])
            if choice == "head":
                return text[:LARGE_OUTPUT_CHARS] + f"\n...[{label} head only by user choice]..."
            if choice == "tail":
                return text[-LARGE_OUTPUT_CHARS:] + f"\n...[{label} tail only by user choice]..."
            if choice == "truncate":
                return text[:LARGE_OUTPUT_CHARS] + f"\n...[{label} truncated by user choice]..."
            return text  # full

        out = maybe_trim("stdout", out)
        err = maybe_trim("stderr", err)

        fail_why = stderr_means_failure(err, out)
        ok = proc.returncode == 0 and not fail_why
        extra_err = ""
        if fail_why and proc.returncode == 0:
            extra_err = (
                f"Process exited 0 but output shows failure ({fail_why}). "
                "Treat this as NOT done."
            )
        return {
            "ok": ok,
            "command": display_cmd,
            "stdout": out,
            "stderr": (err + ("\n" + extra_err if extra_err else "")).strip(),
            "error": extra_err or None,
            "exit_code": proc.returncode,
            "cwd": str(workdir),
        }
    except OSError as e:
        with _active_lock:
            _active_proc = None
        return {
            "ok": False,
            "command": cmd,
            "error": str(e),
            "stdout": "",
            "stderr": str(e),
            "exit_code": None,
            "cwd": str(workdir),
        }


def format_result_for_llm(result: dict[str, Any]) -> str:
    parts = [
        "### Terminal result",
        f"Command: `{result.get('command', '')}`",
        f"Cwd: `{result.get('cwd', '')}`",
        f"Exit code: {result.get('exit_code')}",
        f"OK: {result.get('ok')}",
    ]
    if result.get("error"):
        parts.append(f"Error: {result['error']}")
    if result.get("stdout"):
        parts.append("Stdout:\n```\n" + result["stdout"] + "\n```")
    if result.get("stderr"):
        parts.append("Stderr:\n```\n" + result["stderr"] + "\n```")
    return "\n".join(parts)


def terminal_instructions() -> str:
    return (
        "You have FULL terminal access on the user's machine (unless they disabled it).\n"
        "There are no default command restrictions.\n"
        "To run a command, include EXACTLY:\n"
        "<<<TERMINAL>>>\n"
        "your-command-here\n"
        "<<<END_TERMINAL>>>\n"
        "Multiple blocks run in order.\n"
        "Windows: quote every path that contains spaces. "
        "Use cmd.exe /c for cd /d … && … (do not mix unquoted cmd into PowerShell). "
        "Start-Process exit 0 is NOT success if stderr has Traceback/ModuleNotFoundError.\n"
        "To read source files use <<<READ_FILE>>>, never type/Get-Content of .py files.\n"
        "After launching a GUI, list windows or take a screenshot — do not claim done without that.\n"
        "Do not invent output — wait for real results.\n"
    )
