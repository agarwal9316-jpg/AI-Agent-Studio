"""Load AGENTS.md / project rules (Grok-style hierarchical discovery)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.paths import app_root


RULE_NAMES = (
    "AGENTS.md",
    "Agents.md",
    "AGENT.md",
    "CLAUDE.md",
    "Claude.md",
    "CLAUDE.local.md",
)


def _read(p: Path, max_chars: int = 12000) -> str:
    try:
        t = p.read_text(encoding="utf-8", errors="replace")
        if len(t) > max_chars:
            return t[:max_chars] + f"\n\n…(truncated {len(t) - max_chars} chars)"
        return t
    except OSError:
        return ""


def discover_rules(cwd: str | Path | None = None) -> list[dict[str, Any]]:
    """Walk from cwd up to filesystem root (stop at drive root), collect rule files."""
    start = Path(cwd).expanduser().resolve() if cwd else app_root().resolve()
    if start.is_file():
        start = start.parent
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    cur = start
    for _ in range(24):
        # rules directories
        for sub in (".grok/rules", ".claude/rules", ".cursor/rules", ".agents/rules"):
            rd = cur / sub
            if rd.is_dir():
                for md in sorted(rd.glob("*.md")):
                    key = str(md.resolve()).lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    found.append(
                        {
                            "path": str(md.resolve()),
                            "name": md.name,
                            "dir": str(cur),
                            "kind": "rules_dir",
                        }
                    )
        for name in RULE_NAMES:
            p = cur / name
            if p.is_file():
                key = str(p.resolve()).lower()
                if key in seen:
                    continue
                seen.add(key)
                found.append(
                    {
                        "path": str(p.resolve()),
                        "name": name,
                        "dir": str(cur),
                        "kind": "agents_md",
                    }
                )
        parent = cur.parent
        if parent == cur:
            break
        cur = parent
    # home-level
    home = Path.home()
    for base, sub in (
        (home / ".grok" / "rules", "home_grok"),
        (home / ".claude" / "rules", "home_claude"),
        (home / ".cursor" / "rules", "home_cursor"),
    ):
        if base.is_dir():
            for md in sorted(base.glob("*.md")):
                key = str(md.resolve()).lower()
                if key in seen:
                    continue
                seen.add(key)
                found.append(
                    {
                        "path": str(md.resolve()),
                        "name": md.name,
                        "dir": str(base),
                        "kind": sub,
                    }
                )
    return found


def load_rules_text(cwd: str | Path | None = None, *, max_total: int = 24000) -> dict[str, Any]:
    items = discover_rules(cwd)
    parts: list[str] = []
    loaded: list[str] = []
    total = 0
    # Prefer closer (later in walk = higher? we walked up so reverse for closer first)
    # discover walks up; reverse so cwd rules first
    for it in reversed(items):
        body = _read(Path(it["path"]), max_chars=8000)
        if not body.strip():
            continue
        block = f"### Project rules: {it['name']} ({it['dir']})\n{body.strip()}\n"
        if total + len(block) > max_total:
            break
        parts.append(block)
        loaded.append(it["path"])
        total += len(block)
    text = "\n".join(parts).strip()
    return {
        "ok": True,
        "count": len(loaded),
        "files": loaded,
        "text": text,
        "chars": len(text),
    }


def inject_block(cwd: str | Path | None = None) -> str:
    r = load_rules_text(cwd)
    if not r.get("text"):
        return ""
    return (
        "## Project rules (AGENTS.md / rules dirs — follow these)\n\n"
        + r["text"]
    )
