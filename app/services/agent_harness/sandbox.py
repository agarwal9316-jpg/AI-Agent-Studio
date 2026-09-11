"""Workspace sandbox — restrict writes outside allowed roots.

Task #15: optional per-chat cwd lock (agent may only touch that folder tree).
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from app.paths import app_root, data_dir
from app.core.services.data.storage import load_config

# Per-thread / active chat sandbox context (set by chat send)
_ctx_lock = threading.Lock()
_chat_ctx: dict[str, Any] = {
    "chat_id": "",
    "cwd": "",
    "cwd_lock": False,
}


def set_chat_context(
    *,
    chat_id: str = "",
    cwd: str = "",
    cwd_lock: bool = False,
) -> dict[str, Any]:
    """Bind sandbox roots to the active chat (Task #15)."""
    with _ctx_lock:
        _chat_ctx["chat_id"] = str(chat_id or "")
        _chat_ctx["cwd"] = str(cwd or "").strip()
        _chat_ctx["cwd_lock"] = bool(cwd_lock)
        return dict(_chat_ctx)


def clear_chat_context() -> None:
    set_chat_context(chat_id="", cwd="", cwd_lock=False)


def get_chat_context() -> dict[str, Any]:
    with _ctx_lock:
        return dict(_chat_ctx)


def sandbox_enabled() -> bool:
    cfg = load_config()
    # Cwd lock forces sandbox on for that chat
    ctx = get_chat_context()
    if ctx.get("cwd_lock") and ctx.get("cwd"):
        return True
    return bool(cfg.get("agent_sandbox_enabled", False))


def sandbox_profile() -> str:
    cfg = load_config()
    ctx = get_chat_context()
    if ctx.get("cwd_lock") and ctx.get("cwd"):
        # Locked chats use workspace-style root = chat cwd
        p = str(cfg.get("agent_sandbox_profile") or "workspace").lower()
        if p == "off":
            return "workspace"
        return p if p in ("workspace", "strict", "read_only") else "workspace"
    p = str(cfg.get("agent_sandbox_profile") or "workspace").lower()
    if p not in ("off", "workspace", "strict", "read_only"):
        return "workspace"
    return p


def allowed_write_roots() -> list[Path]:
    """Paths where write/delete is allowed under workspace profile."""
    ctx = get_chat_context()
    lock = bool(ctx.get("cwd_lock"))
    chat_cwd = str(ctx.get("cwd") or "").strip()

    # Task #15: hard lock — only chat cwd (+ data for app media)
    if lock and chat_cwd:
        roots: list[Path] = []
        try:
            roots.append(Path(chat_cwd).expanduser().resolve())
        except Exception:  # noqa: BLE001
            pass
        roots.append(data_dir().resolve())  # allow chat media / logs
        return _unique_roots(roots)

    roots = [
        app_root().resolve(),
        data_dir().resolve(),
        Path.home().resolve() / ".grok",
    ]
    cfg = load_config()
    extra = cfg.get("agent_sandbox_extra_write") or []
    if isinstance(extra, list):
        for e in extra:
            try:
                roots.append(Path(str(e)).expanduser().resolve())
            except Exception:  # noqa: BLE001
                pass
    # cwd from chat context or config
    cwd = chat_cwd or cfg.get("terminal_cwd") or cfg.get("agent_cwd")
    if cwd:
        try:
            roots.append(Path(str(cwd)).expanduser().resolve())
        except Exception:  # noqa: BLE001
            pass
    return _unique_roots(roots)


def _unique_roots(roots: list[Path]) -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()
    for r in roots:
        k = str(r).lower()
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:  # noqa: BLE001
        return False


def check_path_access(
    path: str | Path,
    *,
    write: bool = False,
    profile: str | None = None,
) -> dict[str, Any]:
    """
    Returns {ok, error?, path}.
    profile: off | workspace | strict | read_only
    """
    ctx = get_chat_context()
    lock = bool(ctx.get("cwd_lock") and ctx.get("cwd"))
    prof = (profile or sandbox_profile()).lower()

    # When cwd lock is on, never fully disable sandbox
    if (prof == "off" or not sandbox_enabled()) and not lock:
        try:
            p = Path(path).expanduser().resolve()
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"bad path: {e}", "path": str(path)}
        return {"ok": True, "path": str(p), "profile": "off", "cwd_lock": False}

    try:
        p = Path(path).expanduser().resolve()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"bad path: {e}", "path": str(path)}

    if prof == "read_only" and write:
        return {
            "ok": False,
            "error": "Sandbox read_only: writes blocked",
            "path": str(p),
            "profile": prof,
            "cwd_lock": lock,
        }

    roots = allowed_write_roots()
    if prof == "strict" and not lock:
        # only app root + data (unless chat lock tighter)
        roots = [app_root().resolve(), data_dir().resolve()]
        if ctx.get("cwd"):
            try:
                roots.append(Path(str(ctx["cwd"])).expanduser().resolve())
            except Exception:  # noqa: BLE001
                pass
            roots = _unique_roots(roots)

    # Cwd lock: both read and write must stay under roots (not only writes)
    if lock or write or prof == "strict":
        if not any(_is_under(p, r) for r in roots):
            return {
                "ok": False,
                "error": (
                    f"Sandbox ({'cwd_lock' if lock else prof}): path outside allowed roots: {p}. "
                    f"Allowed: {[str(r) for r in roots[:6]]}"
                    + (" — unlock cwd in Chat (Cwd…) to use other folders." if lock else "")
                ),
                "path": str(p),
                "profile": prof,
                "cwd_lock": lock,
            }

    # Deny sensitive patterns always when sandbox on
    deny_globs = (
        ".env",
        "id_rsa",
        "id_ed25519",
        ".pem",
        "credentials.json",
        "secrets.json",
    )
    name = p.name.lower()
    if write and any(name.endswith(d) or name == d.lstrip(".") for d in deny_globs):
        cfg = load_config()
        if not cfg.get("agent_sandbox_allow_secrets"):
            return {
                "ok": False,
                "error": f"Sandbox: writing sensitive file blocked: {p.name}",
                "path": str(p),
                "profile": prof,
                "cwd_lock": lock,
            }

    return {"ok": True, "path": str(p), "profile": prof, "cwd_lock": lock}


def status() -> dict[str, Any]:
    ctx = get_chat_context()
    return {
        "enabled": sandbox_enabled(),
        "profile": sandbox_profile(),
        "write_roots": [str(r) for r in allowed_write_roots()],
        "chat_id": ctx.get("chat_id") or "",
        "cwd": ctx.get("cwd") or "",
        "cwd_lock": bool(ctx.get("cwd_lock")),
    }
