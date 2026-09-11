#!/usr/bin/env python3
"""Headless CLI entry for AI Agent Studio agent harness.

Usage:
  python studio_agent.py -p "List files in app/services" --json
  python studio_agent.py -p "git status" --cwd .
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.agent_harness.headless import main

if __name__ == "__main__":
    raise SystemExit(main())
