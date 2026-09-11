"""Tests for PENDING_TASKS.md #10 version / update-check UX."""

from __future__ import annotations

import json
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

    from app.version import __version__, APP_NAME
    from app.services.version_check import (
        parse_version,
        compare_versions,
        install_summary,
        check_for_updates,
        write_local_version_files,
        install_mode,
    )

    check(parse_version("1.26.0") == (1, 26, 0), "parse 1.26.0")
    check(parse_version("v2.0.1-beta") == (2, 0, 1), "parse with prefix")
    check(compare_versions("1.0.0", "1.0.1") == -1, "1.0.0 < 1.0.1")
    check(compare_versions("1.2.3", "1.2.3") == 0, "equal")
    check(compare_versions("2.0.0", "1.9.9") == 1, "2 > 1.9")

    info = install_summary()
    check(info.get("app_name") == APP_NAME, "app name")
    check(info.get("version") == __version__, f"version matches {__version__}")
    check(info.get("mode") in ("development", "portable"), f"mode {info.get('mode')}")
    check(bool(info.get("app_root")), "app_root set")
    check(bool(info.get("data_dir")), "data_dir set")
    check(bool(info.get("launch")), "launch hint")

    r = check_for_updates()
    check(r.get("ok") is True, "check ok")
    check(r.get("current") == __version__, "current version")
    check(r.get("status") in ("up_to_date", "update_available", "unknown"), f"status {r.get('status')}")
    check(bool(r.get("message")), "has message")
    # Local VERSION / changelog should usually report up_to_date when stamped
    if r.get("status") == "up_to_date":
        check(r.get("latest") == __version__ or compare_versions(r.get("latest") or "", __version__) <= 0,
              "latest consistent")

    # write files
    p = write_local_version_files()
    check(p.is_file(), "VERSION written")
    check(__version__ in p.read_text(encoding="utf-8"), "VERSION content")
    man = ROOT / "version_manifest.json"
    check(man.is_file(), "manifest exists")
    data = json.loads(man.read_text(encoding="utf-8"))
    check(data.get("version") == __version__, "manifest version")

    check(install_mode() in ("development", "portable"), "install_mode")

    if fails:
        print("FAILED:", fails)
        return 1
    print("All pending-task #10 version checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
