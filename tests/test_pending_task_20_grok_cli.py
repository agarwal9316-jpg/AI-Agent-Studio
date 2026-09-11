"""Tests for PENDING_TASKS.md #20 — Grok CLI session reuse (skipped with research)."""

from __future__ import annotations

import re
import sys
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

    research = ROOT / "docs" / "research" / "GROK_CLI_SESSION_REUSE.md"
    check(research.is_file(), "research doc exists")
    body = research.read_text(encoding="utf-8") if research.is_file() else ""
    check("SKIP" in body.upper() or "skipped" in body.lower(), "research records skip decision")
    check("console.x.ai" in body or "api.x.ai" in body, "research mentions official API path")
    check("cookie" in body.lower() or "auth.json" in body.lower(), "research addresses cookie/auth.json risk")
    check("Acceptable Use" in body or "AUP" in body or "ToS" in body, "research cites ToS/AUP")

    pending = (ROOT / "docs" / "PENDING_TASKS.md").read_text(encoding="utf-8")
    # Row for task 20 must be skipped
    m = re.search(r"\|\s*20\s*\|[^|]+\|[^|]+\|\s*\*\*?skipped\*\*?\s*\|", pending, re.I)
    check(m is not None, "PENDING #20 status is skipped")
    check("GROK_CLI_SESSION_REUSE.md" in pending, "PENDING links research doc")

    from app.version import __version__

    check(__version__ == "1.27.85", f"version is 1.27.85 (got {__version__})")
    check((ROOT / "VERSION").read_text(encoding="utf-8").strip() == "1.27.85", "VERSION file")
    cl = (ROOT / "docs" / "CHANGELOG.md").read_text(encoding="utf-8")
    check("1.27.85" in cl and "#20" in cl, "CHANGELOG mentions 1.27.85 / #20")

    # Guard: no new auth.json / cookie scrape implementation for this task
    providers = (ROOT / "app" / "core" / "services" / "llm" / "providers.py").read_text(encoding="utf-8")
    check("auth.json" not in providers, "providers.py does not read CLI auth.json")
    check("cli-chat-proxy" not in providers.lower(), "providers.py does not call CLI chat proxy")

    if fails:
        print("FAILED:", fails)
        return 1
    print("All pending-task #20 Grok CLI skip checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
