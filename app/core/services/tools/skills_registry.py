"""Discover Grok / agent skills (SKILL.md) for chat LLM use."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# All common skill roots on this machine (user asked for all skills support)
DEFAULT_SKILL_ROOTS = [
    Path.home() / ".grok" / "skills",
    Path.home() / ".grok" / "bundled" / "skills",
    Path.home() / ".agents" / "skills",
    Path.home() / ".claude" / "skills",
    Path.home() / ".codex" / "skills",
    Path.home() / ".cursor" / "skills",
]


def _project_skill_roots() -> list[Path]:
    """Project-local skill dirs (cwd → parents, limited)."""
    roots: list[Path] = []
    try:
        from app.paths import app_root

        cur = Path.cwd().resolve()
        app = app_root().resolve()
        for base in (cur, app):
            for sub in (".grok/skills", ".agents/skills", ".claude/skills", ".cursor/skills"):
                p = base / sub
                if p.is_dir():
                    roots.append(p)
    except Exception:  # noqa: BLE001
        pass
    return roots


def _parse_frontmatter(text: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    if not text.startswith("---"):
        return meta
    parts = text.split("---", 2)
    if len(parts) < 3:
        return meta
    for line in parts[1].splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip("\"'")
    return meta


def discover_skills(extra_roots: list[str | Path] | None = None) -> list[dict[str, Any]]:
    roots: list[Path] = []
    for r in list(_project_skill_roots()) + list(DEFAULT_SKILL_ROOTS) + list(extra_roots or []):
        p = Path(r).expanduser()
        if p.is_dir() and p not in roots:
            roots.append(p)

    found: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    for root in roots:
        for skill_md in root.rglob("SKILL.md"):
            try:
                text = skill_md.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            meta = _parse_frontmatter(text)
            name = meta.get("name") or skill_md.parent.name
            # Prefer first occurrence; user/project paths listed first in roots
            key = name.lower()
            if key in seen_names:
                continue
            seen_names.add(key)
            # Body without frontmatter for size estimate
            body = text
            if text.startswith("---"):
                bits = text.split("---", 2)
                if len(bits) >= 3:
                    body = bits[2]
            found.append(
                {
                    "name": name,
                    "description": meta.get("description") or meta.get("short-description") or "",
                    "path": str(skill_md.resolve()),
                    "dir": str(skill_md.parent.resolve()),
                    "chars": len(text),
                    "body_chars": len(body),
                }
            )

    found.sort(key=lambda x: x["name"].lower())
    return found


def load_skill_text(name_or_path: str) -> dict[str, Any]:
    """Load full SKILL.md by name or absolute path."""
    q = (name_or_path or "").strip()
    if not q:
        return {"ok": False, "error": "Empty skill name"}

    p = Path(q)
    if p.is_file():
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
            return {"ok": True, "name": p.parent.name, "path": str(p), "text": text}
        except OSError as e:
            return {"ok": False, "error": str(e)}

    for s in discover_skills():
        if s["name"].lower() == q.lower() or Path(s["path"]).parent.name.lower() == q.lower():
            try:
                text = Path(s["path"]).read_text(encoding="utf-8", errors="replace")
                return {
                    "ok": True,
                    "name": s["name"],
                    "path": s["path"],
                    "text": text,
                }
            except OSError as e:
                return {"ok": False, "error": str(e)}

    return {"ok": False, "error": f"Skill not found: {q}"}


def skills_catalog_prompt(skills: list[dict[str, Any]] | None = None) -> str:
    skills = skills if skills is not None else discover_skills()
    if not skills:
        return "No skills discovered on this machine."
    lines = [
        "### Available skills (load full text with SKILL blocks when needed)",
        f"Total: {len(skills)}",
        "",
    ]
    for s in skills:
        desc = re.sub(r"\s+", " ", (s.get("description") or "")[:160])
        lines.append(f"- **{s['name']}** — {desc}  `(path: {s['path']})`")
    lines.append("")
    lines.append(
        "To load a skill's full instructions into context, emit:\n"
        "<<<SKILL>>>\n"
        "skill-name-or-path\n"
        "<<<END_SKILL>>>\n"
    )
    return "\n".join(lines)


def extract_skill_requests(text: str) -> list[str]:
    import re as _re

    pat = _re.compile(
        r"<<<SKILL>>>\s*(.*?)\s*<<<END_SKILL>>>",
        _re.DOTALL | _re.IGNORECASE,
    )
    return [m.group(1).strip() for m in pat.finditer(text or "") if m.group(1).strip()]
