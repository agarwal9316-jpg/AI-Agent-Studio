"""Filesystem sandbox profiles — named allow-roots / deny-writes / allow-shell.

Near-term roadmap: selectable profiles (Read-only workspace, Project-only,
Full disk with ask) plus optional custom roots. Extends cwd lock / agent_sandbox.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from app.paths import app_root, data_dir
from app.core.services.data.storage import load_config, save_config

# Per-thread / active chat sandbox context (set by chat send)
_ctx_lock = threading.Lock()
_chat_ctx: dict[str, Any] = {
    "chat_id": "",
    "cwd": "",
    "cwd_lock": False,
}

# ---------------------------------------------------------------------------
# Built-in named profiles (id, label, allow_roots, deny_writes, allow_shell)
# allow_roots tokens: workspace|project|cwd|app|data|home_grok|full
# ---------------------------------------------------------------------------

BUILTIN_PROFILES: list[dict[str, Any]] = [
    {
        "id": "read_only_workspace",
        "label": "Read-only workspace",
        "allow_roots": ["workspace", "data"],
        "deny_writes": True,
        "allow_shell": False,
        "description": "Read files under workspace (+ data); block all writes and shell",
    },
    {
        "id": "project_only",
        "label": "Project-only",
        "allow_roots": ["workspace", "data"],
        "deny_writes": False,
        "allow_shell": True,
        "description": "Read/write/shell only inside project cwd (+ data for media/logs)",
    },
    {
        "id": "workspace",
        "label": "Workspace",
        "allow_roots": ["app", "data", "home_grok", "workspace"],
        "deny_writes": False,
        "allow_shell": True,
        "description": "Writes limited to app/data/~/.grok/cwd; shell allowed in those roots",
    },
    {
        "id": "strict",
        "label": "Strict (app + data)",
        "allow_roots": ["app", "data", "workspace"],
        "deny_writes": False,
        "allow_shell": True,
        "description": "Legacy strict — app root + data (+ chat cwd)",
    },
    {
        "id": "full_ask",
        "label": "Full disk with ask",
        "allow_roots": ["full"],
        "deny_writes": False,
        "allow_shell": True,
        "description": "No path sandbox; risky tools still pause for approval (Ask tier)",
    },
    {
        "id": "off",
        "label": "Off",
        "allow_roots": ["full"],
        "deny_writes": False,
        "allow_shell": True,
        "description": "Sandbox disabled (cwd lock still enforced when set)",
    },
]

# Legacy config values → canonical profile ids
_LEGACY_PROFILE_ALIASES: dict[str, str] = {
    "read_only": "read_only_workspace",
    "readonly": "read_only_workspace",
    "read-only": "read_only_workspace",
    "project": "project_only",
    "full": "full_ask",
    "full_disk": "full_ask",
    "full-disk": "full_ask",
}

_PROFILE_BY_ID: dict[str, dict[str, Any]] = {p["id"]: p for p in BUILTIN_PROFILES}


def list_profiles() -> list[dict[str, Any]]:
    """Return built-in profiles (copies) for Settings / Chat UI."""
    return [dict(p) for p in BUILTIN_PROFILES]


def profile_ids() -> list[str]:
    return [p["id"] for p in BUILTIN_PROFILES]


def profile_labels() -> dict[str, str]:
    return {p["id"]: str(p["label"]) for p in BUILTIN_PROFILES}


def normalize_profile_id(raw: str | None) -> str:
    """Map config / legacy strings to a known profile id."""
    p = str(raw or "workspace").strip().lower().replace(" ", "_").replace("-", "_")
    if p in _LEGACY_PROFILE_ALIASES:
        p = _LEGACY_PROFILE_ALIASES[p]
    if p in _PROFILE_BY_ID:
        return p
    return "workspace"


def get_profile(profile_id: str | None = None) -> dict[str, Any]:
    """Resolve a profile dict (builtin). Falls back to workspace."""
    pid = normalize_profile_id(profile_id if profile_id is not None else active_profile_id())
    return dict(_PROFILE_BY_ID.get(pid) or _PROFILE_BY_ID["workspace"])


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
    ctx = get_chat_context()
    if ctx.get("cwd_lock") and ctx.get("cwd"):
        return True
    pid = normalize_profile_id(cfg.get("agent_sandbox_profile"))
    if pid == "off":
        return False
    # Named restrictive / ask profiles imply sandbox is on
    if pid in ("read_only_workspace", "project_only", "strict", "full_ask"):
        return True
    return bool(cfg.get("agent_sandbox_enabled", False))


def active_profile_id() -> str:
    """Canonical active profile id (cwd lock forces project-style roots)."""
    cfg = load_config()
    ctx = get_chat_context()
    pid = normalize_profile_id(cfg.get("agent_sandbox_profile") or "workspace")
    if ctx.get("cwd_lock") and ctx.get("cwd"):
        # Locked chats never go fully off / full-disk
        if pid in ("off", "full_ask"):
            return "project_only"
        return pid
    if not bool(cfg.get("agent_sandbox_enabled", False)) and pid not in ("off", "full_ask"):
        # Master switch off → treat as off unless user picked full_ask/off explicitly
        if pid == "workspace" and not cfg.get("agent_sandbox_enabled", False):
            # Preserve explicit profile when switch is on via profile choice
            pass
    return pid


def sandbox_profile() -> str:
    """Backward-compatible profile string (canonical id)."""
    return active_profile_id()


def set_active_profile(
    profile_id: str,
    *,
    custom_roots: list[str] | None = None,
    enabled: bool | None = None,
) -> dict[str, Any]:
    """Persist active profile (+ optional custom roots) into config."""
    pid = normalize_profile_id(profile_id)
    cfg = load_config()
    cfg["agent_sandbox_profile"] = pid
    if enabled is None:
        cfg["agent_sandbox_enabled"] = pid != "off"
    else:
        cfg["agent_sandbox_enabled"] = bool(enabled)
    if custom_roots is not None:
        cleaned: list[str] = []
        for r in custom_roots:
            s = str(r or "").strip()
            if s:
                cleaned.append(s)
        cfg["agent_sandbox_custom_roots"] = cleaned
        # Keep legacy key in sync for older readers
        cfg["agent_sandbox_extra_write"] = list(cleaned)
    # Align risk tier lightly for full_ask / read_only
    if pid == "read_only_workspace":
        cfg.setdefault("agent_risk_tier", "read_only")
        if cfg.get("agent_risk_tier") == "full":
            cfg["agent_risk_tier"] = "read_only"
    elif pid == "full_ask":
        cfg["agent_risk_tier"] = "ask"
        cfg["tool_approval_required"] = True
        cfg["agent_permission_mode"] = "ask"
    save_config(cfg)
    return status()


def custom_roots_from_config(cfg: dict[str, Any] | None = None) -> list[str]:
    c = cfg if cfg is not None else load_config()
    roots = c.get("agent_sandbox_custom_roots")
    if not isinstance(roots, list):
        roots = c.get("agent_sandbox_extra_write") or []
    if not isinstance(roots, list):
        return []
    return [str(x).strip() for x in roots if str(x).strip()]


def _unique_roots(roots: list[Path]) -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()
    for r in roots:
        try:
            rr = r.resolve()
        except Exception:  # noqa: BLE001
            rr = r
        k = str(rr).lower()
        if k not in seen:
            seen.add(k)
            out.append(rr)
    return out


def _resolve_token(token: str, *, chat_cwd: str, cfg: dict[str, Any]) -> list[Path]:
    t = (token or "").strip().lower()
    if t in ("full", "*", "any"):
        return []  # empty list + full flag handled by caller
    roots: list[Path] = []
    if t in ("workspace", "project", "cwd"):
        cwd = chat_cwd or str(cfg.get("terminal_cwd") or cfg.get("agent_cwd") or "").strip()
        if cwd:
            try:
                roots.append(Path(cwd).expanduser().resolve())
            except Exception:  # noqa: BLE001
                pass
        else:
            try:
                roots.append(app_root().resolve())
            except Exception:  # noqa: BLE001
                pass
    elif t == "app":
        roots.append(app_root().resolve())
    elif t == "data":
        roots.append(data_dir().resolve())
    elif t in ("home_grok", "grok"):
        roots.append((Path.home() / ".grok").resolve())
    elif t == "home":
        roots.append(Path.home().resolve())
    else:
        # Treat unknown token as a literal path
        try:
            roots.append(Path(token).expanduser().resolve())
        except Exception:  # noqa: BLE001
            pass
    return roots


def resolve_allow_roots(
    profile: dict[str, Any] | None = None,
    *,
    include_custom: bool = True,
) -> tuple[list[Path], bool]:
    """
    Resolve allow_roots for the active (or given) profile.
    Returns (roots, is_full). is_full=True means no path restriction.
    """
    prof = profile or get_profile()
    ctx = get_chat_context()
    chat_cwd = str(ctx.get("cwd") or "").strip()
    lock = bool(ctx.get("cwd_lock") and chat_cwd)
    cfg = load_config()
    tokens = list(prof.get("allow_roots") or [])

    # Cwd lock: hard-limit to chat cwd + data regardless of profile tokens
    if lock:
        roots: list[Path] = []
        try:
            roots.append(Path(chat_cwd).expanduser().resolve())
        except Exception:  # noqa: BLE001
            pass
        roots.append(data_dir().resolve())
        if include_custom:
            for e in custom_roots_from_config(cfg):
                try:
                    roots.append(Path(e).expanduser().resolve())
                except Exception:  # noqa: BLE001
                    pass
        return _unique_roots(roots), False

    if any(str(t).lower() in ("full", "*", "any") for t in tokens):
        return [], True

    roots = []
    for tok in tokens:
        roots.extend(_resolve_token(str(tok), chat_cwd=chat_cwd, cfg=cfg))

    if include_custom:
        for e in custom_roots_from_config(cfg):
            try:
                roots.append(Path(e).expanduser().resolve())
            except Exception:  # noqa: BLE001
                pass
        # legacy extra write key already covered by custom_roots_from_config

    return _unique_roots(roots), False


def allowed_write_roots() -> list[Path]:
    """Paths where write/delete is allowed (empty if full / unrestricted)."""
    roots, is_full = resolve_allow_roots()
    if is_full:
        # Unrestricted — return a sentinel-ish broad list for status display only
        return roots
    return roots


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
    Returns {ok, error?, path, profile, cwd_lock}.
    Enforces active (or given) sandbox profile.
    """
    ctx = get_chat_context()
    lock = bool(ctx.get("cwd_lock") and ctx.get("cwd"))
    prof = get_profile(profile if profile is not None else active_profile_id())
    pid = str(prof["id"])
    deny_writes = bool(prof.get("deny_writes"))

    # Off + no cwd lock → unrestricted
    cfg = load_config()
    master_on = bool(cfg.get("agent_sandbox_enabled", False))
    if pid == "off" and not lock:
        try:
            p = Path(path).expanduser().resolve()
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"bad path: {e}", "path": str(path)}
        return {"ok": True, "path": str(p), "profile": pid, "cwd_lock": False}

    # full_ask with no lock: unrestricted paths (ask handled by permissions)
    roots, is_full = resolve_allow_roots(prof)
    if is_full and not lock and not deny_writes:
        try:
            p = Path(path).expanduser().resolve()
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"bad path: {e}", "path": str(path)}
        return {"ok": True, "path": str(p), "profile": pid, "cwd_lock": False, "full": True}

    # If master switch off and profile is workspace default without lock → allow
    if not master_on and not lock and pid in ("workspace",) and profile is None:
        # Explicit: when user disabled sandbox switch, don't enforce workspace
        # unless they picked a restrictive profile id
        try:
            p = Path(path).expanduser().resolve()
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"bad path: {e}", "path": str(path)}
        return {"ok": True, "path": str(p), "profile": "off", "cwd_lock": False}

    try:
        p = Path(path).expanduser().resolve()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"bad path: {e}", "path": str(path)}

    label = str(prof.get("label") or pid)

    if deny_writes and write:
        return {
            "ok": False,
            "error": (
                f"Sandbox profile '{label}' denies writes "
                f"(read-only). Switch profile in Settings → Agent harness, "
                f"or Chat risk tier."
            ),
            "path": str(p),
            "profile": pid,
            "cwd_lock": lock,
            "denied": True,
        }

    # Restrict reads under project_only / cwd lock / non-full profiles for writes;
    # project_only and lock also restrict reads.
    restrict_reads = lock or pid in ("project_only", "strict", "read_only_workspace")
    if write or restrict_reads:
        if not roots:
            # Shouldn't happen unless misconfigured
            pass
        elif not any(_is_under(p, r) for r in roots):
            return {
                "ok": False,
                "error": (
                    f"Sandbox profile '{label}'"
                    f"{' (cwd lock)' if lock else ''}: path outside allowed roots: {p}. "
                    f"Allowed: {[str(r) for r in roots[:6]]}"
                    + (
                        " — unlock cwd in Chat (Cwd…) or pick Full disk with ask / add custom roots."
                        if not lock
                        else " — unlock cwd in Chat (Cwd…) to use other folders."
                    )
                ),
                "path": str(p),
                "profile": pid,
                "cwd_lock": lock,
                "denied": True,
            }

    # workspace profile: only restrict writes to roots (legacy behavior)
    if write and pid == "workspace" and roots and not any(_is_under(p, r) for r in roots):
        return {
            "ok": False,
            "error": (
                f"Sandbox profile '{label}': write outside allowed roots: {p}. "
                f"Allowed: {[str(r) for r in roots[:6]]}"
            ),
            "path": str(p),
            "profile": pid,
            "cwd_lock": lock,
            "denied": True,
        }

    # Deny sensitive patterns when sandbox on
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
        if not cfg.get("agent_sandbox_allow_secrets"):
            return {
                "ok": False,
                "error": f"Sandbox: writing sensitive file blocked: {p.name}",
                "path": str(p),
                "profile": pid,
                "cwd_lock": lock,
                "denied": True,
            }

    return {"ok": True, "path": str(p), "profile": pid, "cwd_lock": lock}


def check_shell_access(
    cwd: str | Path | None = None,
    *,
    profile: str | None = None,
) -> dict[str, Any]:
    """
    Enforce allow_shell + cwd-under-roots for terminal / bg_shell.
    Returns {ok, error?, profile, cwd}.
    """
    prof = get_profile(profile if profile is not None else active_profile_id())
    pid = str(prof["id"])
    label = str(prof.get("label") or pid)
    ctx = get_chat_context()
    lock = bool(ctx.get("cwd_lock") and ctx.get("cwd"))

    cfg = load_config()
    master_on = bool(cfg.get("agent_sandbox_enabled", False))

    work = str(cwd or ctx.get("cwd") or cfg.get("terminal_cwd") or cfg.get("agent_cwd") or "").strip()
    if not work:
        work = str(Path.cwd())

    if pid == "off" and not lock:
        return {"ok": True, "profile": pid, "cwd": work, "allow_shell": True}

    if not bool(prof.get("allow_shell", True)):
        return {
            "ok": False,
            "error": (
                f"Sandbox profile '{label}' denies shell/terminal. "
                f"Pick Project-only, Workspace, or Full disk with ask in Settings."
            ),
            "profile": pid,
            "cwd": work,
            "allow_shell": False,
            "denied": True,
        }

    roots, is_full = resolve_allow_roots(prof)
    if is_full and not lock:
        return {"ok": True, "profile": pid, "cwd": work, "allow_shell": True, "full": True}

    if not master_on and not lock and pid == "workspace":
        return {"ok": True, "profile": "off", "cwd": work, "allow_shell": True}

    try:
        p = Path(work).expanduser().resolve()
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "error": f"Sandbox profile '{label}': bad shell cwd: {e}",
            "profile": pid,
            "cwd": work,
            "denied": True,
        }

    if roots and not any(_is_under(p, r) for r in roots):
        return {
            "ok": False,
            "error": (
                f"Sandbox profile '{label}': shell cwd outside allowed roots: {p}. "
                f"Allowed: {[str(r) for r in roots[:6]]}"
            ),
            "profile": pid,
            "cwd": str(p),
            "allow_shell": True,
            "denied": True,
        }
    return {"ok": True, "profile": pid, "cwd": str(p), "allow_shell": True}


def status() -> dict[str, Any]:
    ctx = get_chat_context()
    prof = get_profile()
    roots, is_full = resolve_allow_roots(prof)
    return {
        "enabled": sandbox_enabled(),
        "profile": prof["id"],
        "profile_label": prof.get("label"),
        "deny_writes": bool(prof.get("deny_writes")),
        "allow_shell": bool(prof.get("allow_shell")),
        "allow_roots_tokens": list(prof.get("allow_roots") or []),
        "write_roots": [str(r) for r in roots],
        "full_disk": bool(is_full),
        "custom_roots": custom_roots_from_config(),
        "profiles": [{"id": p["id"], "label": p["label"]} for p in BUILTIN_PROFILES],
        "chat_id": ctx.get("chat_id") or "",
        "cwd": ctx.get("cwd") or "",
        "cwd_lock": bool(ctx.get("cwd_lock")),
    }
