"""Version info + optional update check (Task #10).

No mandatory cloud auto-update: portable app stays offline-friendly.
Checks, in order:
  1. Optional config update_check_url (JSON: {version, notes, download_url})
  2. Local VERSION / version_manifest.json next to app root
  3. docs/CHANGELOG.md latest **x.y.z** line (dev convenience)

Result is always plain English for the About / Settings UI.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from app.paths import app_root, data_dir
from app.core.services.data.storage import load_config, save_config
from app.version import APP_NAME, __version__

_SEMVER = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def parse_version(v: str) -> tuple[int, int, int]:
    m = _SEMVER.search(v or "")
    if not m:
        return (0, 0, 0)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def compare_versions(a: str, b: str) -> int:
    """-1 if a<b, 0 if equal, 1 if a>b."""
    ta, tb = parse_version(a), parse_version(b)
    if ta < tb:
        return -1
    if ta > tb:
        return 1
    return 0


def install_mode() -> str:
    if getattr(sys, "frozen", False):
        return "portable"
    return "development"


def install_summary() -> dict[str, Any]:
    root = app_root()
    mode = install_mode()
    launch = "AI-Agent-Studio.exe" if mode == "portable" else "Launch.bat"
    return {
        "app_name": APP_NAME,
        "version": __version__,
        "mode": mode,
        "mode_label": "Portable (exe)" if mode == "portable" else "Development (Python venv)",
        "app_root": str(root),
        "data_dir": str(data_dir()),
        "launch": launch,
        "python": sys.version.split()[0],
        "frozen": bool(getattr(sys, "frozen", False)),
    }


def _read_local_manifest() -> dict[str, Any] | None:
    root = app_root()
    for name in ("version_manifest.json", "VERSION.json"):
        p = root / name
        if p.is_file():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("version"):
                    return data
            except Exception:  # noqa: BLE001
                pass
    # Plain VERSION file: first line is version
    plain = root / "VERSION"
    if plain.is_file():
        try:
            line = plain.read_text(encoding="utf-8").strip().splitlines()[0].strip()
            if parse_version(line) != (0, 0, 0):
                return {"version": line, "source": "VERSION", "notes": ""}
        except Exception:  # noqa: BLE001
            pass
    return None


def _read_changelog_latest() -> dict[str, Any] | None:
    p = app_root() / "docs" / "CHANGELOG.md"
    if not p.is_file():
        return None
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return None
    # Prefer table rows like | **1.25.9** | notes |
    m = re.search(r"\|\s*\*\*(\d+\.\d+\.\d+)\*\*\s*\|\s*([^|]+)\|", text)
    if m:
        return {
            "version": m.group(1),
            "notes": (m.group(2) or "").strip()[:300],
            "source": "docs/CHANGELOG.md",
        }
    m2 = re.search(r"##\s*v?(\d+\.\d+\.\d+)", text)
    if m2:
        return {"version": m2.group(1), "notes": "", "source": "docs/CHANGELOG.md"}
    return None


def _fetch_remote_manifest(url: str, *, timeout: float = 8.0) -> dict[str, Any] | None:
    url = (url or "").strip()
    if not url.startswith("http"):
        return None
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": f"{APP_NAME}/{__version__}", "Accept": "application/json"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(200_000).decode("utf-8", errors="replace")
        data = json.loads(raw)
        if isinstance(data, dict) and data.get("version"):
            data.setdefault("source", url)
            return data
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    except Exception:  # noqa: BLE001
        return None
    return None


def write_local_version_files() -> Path:
    """Write VERSION + version_manifest.json to app root (for portable packages)."""
    root = app_root()
    plain = root / "VERSION"
    plain.write_text(f"{__version__}\n", encoding="utf-8")
    manifest = {
        "name": APP_NAME,
        "version": __version__,
        "notes": f"Local package version {__version__}",
        "download_url": "",
        "source": "local",
    }
    (root / "version_manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    return plain


def check_for_updates(*, force_remote: bool = False) -> dict[str, Any]:
    """
    Returns:
      ok, current, latest, status (up_to_date|update_available|unknown|error),
      notes, source, download_url, message, install
    """
    install = install_summary()
    current = install["version"]
    cfg = load_config()
    remote_url = str(cfg.get("update_check_url") or "").strip()

    remote = None
    if remote_url:
        remote = _fetch_remote_manifest(remote_url)
    local = _read_local_manifest()
    changelog = _read_changelog_latest()

    # Prefer remote if available; else local manifest; else changelog
    candidate = remote or local or changelog
    if not candidate:
        return {
            "ok": True,
            "current": current,
            "latest": current,
            "status": "unknown",
            "notes": "",
            "source": "",
            "download_url": "",
            "message": (
                f"You are on {APP_NAME} v{current} ({install['mode_label']}).\n"
                "No update feed configured. Set Settings → Updates → check URL, "
                "or keep VERSION next to the app when you install a newer portable build."
            ),
            "install": install,
        }

    latest = str(candidate.get("version") or current)
    notes = str(candidate.get("notes") or candidate.get("changelog") or "")[:500]
    source = str(candidate.get("source") or "manifest")
    download = str(candidate.get("download_url") or candidate.get("url") or "")
    cmp = compare_versions(current, latest)

    if cmp < 0:
        status = "update_available"
        msg = (
            f"Update available: v{latest} (you have v{current}).\n"
            f"{notes}\n\n"
            + (
                f"Download: {download}"
                if download
                else "Replace this folder with the newer portable build, or re-run build_portable.ps1."
            )
        )
    elif cmp > 0:
        status = "up_to_date"
        msg = (
            f"You are ahead of the feed (app v{current} > reported v{latest}). "
            "Likely a dev build."
        )
    else:
        status = "up_to_date"
        msg = f"You have the latest version: v{current}."

    # Persist last check
    try:
        cfg["last_update_check"] = {
            "at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            "status": status,
            "latest": latest,
            "source": source,
        }
        save_config(cfg)
    except Exception:  # noqa: BLE001
        pass

    return {
        "ok": True,
        "current": current,
        "latest": latest,
        "status": status,
        "notes": notes,
        "source": source,
        "download_url": download,
        "message": msg.strip(),
        "install": install,
        "compare": cmp,
    }


def should_auto_check() -> bool:
    cfg = load_config()
    # Default ON for clear UX; user can disable
    return bool(cfg.get("update_check_on_start", True))


def set_auto_check(on: bool) -> None:
    cfg = load_config()
    cfg["update_check_on_start"] = bool(on)
    save_config(cfg)


def set_update_check_url(url: str) -> None:
    cfg = load_config()
    cfg["update_check_url"] = (url or "").strip()
    save_config(cfg)
