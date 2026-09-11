"""
Auto search / install Python packages when the task needs them.
LLM emits PIP blocks; we install into the active environment (venv if present).
"""

from __future__ import annotations

import importlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.paths import app_root

PIP_BLOCK_RE = re.compile(
    r"<<<PIP>>>\s*(.*?)\s*<<<END_PIP>>>",
    re.DOTALL | re.IGNORECASE,
)

# Common import name → pip name
IMPORT_TO_PIP = {
    "cv2": "opencv-python",
    "PIL": "Pillow",
    "sklearn": "scikit-learn",
    "yaml": "PyYAML",
    "bs4": "beautifulsoup4",
    "dotenv": "python-dotenv",
    "serial": "pyserial",
    "usb": "pyusb",
    "win32api": "pywin32",
    "win32com": "pywin32",
    "Crypto": "pycryptodome",
    "OpenSSL": "pyOpenSSL",
}


def extract_pip_commands(text: str) -> list[str]:
    return [m.group(1).strip() for m in PIP_BLOCK_RE.finditer(text or "") if m.group(1).strip()]


def pip_tool_instructions() -> str:
    return """
## Auto package install (Python libraries)

If a library is missing to achieve the user task, install it (do not ask the user to pip manually).

<<<PIP>>>
{"action": "ensure", "packages": ["requests", "pandas"], "imports": ["requests", "pandas"]}
<<<END_PIP>>>

<<<PIP>>>
{"action": "install", "packages": ["httpx"]}
<<<END_PIP>>>

<<<PIP>>>
{"action": "check", "imports": ["numpy", "cv2"]}
<<<END_PIP>>>

Actions:
- ensure: check imports; install missing packages (map common import→pip names)
- install: pip install packages into the app environment
- check: only report import status

Prefer small, well-known packages. After install, re-try the original task.
""".strip()


def _python_exe() -> str:
    venv = app_root() / ".venv" / "Scripts" / "python.exe"
    if venv.is_file():
        return str(venv)
    return sys.executable


def check_imports(names: list[str]) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for name in names:
        try:
            importlib.import_module(name)
            out[name] = True
        except Exception:  # noqa: BLE001
            out[name] = False
    return out


def install_packages(packages: list[str]) -> dict[str, Any]:
    packages = [p.strip() for p in packages if p and p.strip()]
    if not packages:
        return {"ok": False, "error": "No packages"}
    py = _python_exe()
    cmd = [py, "-m", "pip", "install", "--upgrade", *packages]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
            cwd=str(app_root()),
        )
        return {
            "ok": proc.returncode == 0,
            "packages": packages,
            "python": py,
            "stdout": (proc.stdout or "")[-4000:],
            "stderr": (proc.stderr or "")[-2000:],
            "exit_code": proc.returncode,
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "packages": packages}


def ensure_packages(packages: list[str] | None = None, imports: list[str] | None = None) -> dict[str, Any]:
    packages = list(packages or [])
    imports = list(imports or [])
    status = check_imports(imports) if imports else {}
    missing_imports = [k for k, ok in status.items() if not ok]
    to_install = list(packages)
    for imp in missing_imports:
        pip_name = IMPORT_TO_PIP.get(imp, imp)
        if pip_name not in to_install:
            to_install.append(pip_name)
    if not to_install and not missing_imports:
        return {"ok": True, "message": "All imports available", "imports": status}
    if not to_install:
        return {"ok": False, "message": "Imports missing but no package names", "imports": status}
    result = install_packages(to_install)
    # re-check
    status2 = check_imports(imports) if imports else {}
    result["imports_after"] = status2
    result["ok"] = result.get("ok") and (not imports or all(status2.values()))
    return result


def run_pip_command(body: str) -> dict[str, Any]:
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        # plain package list
        pkgs = [p.strip() for p in body.replace(",", " ").split() if p.strip()]
        return ensure_packages(packages=pkgs)

    if not isinstance(data, dict):
        return {"ok": False, "error": "PIP JSON must be object"}
    action = (data.get("action") or "ensure").lower()
    packages = data.get("packages") or data.get("package") or []
    if isinstance(packages, str):
        packages = [packages]
    imports = data.get("imports") or data.get("import") or []
    if isinstance(imports, str):
        imports = [imports]

    if action == "check":
        st = check_imports(list(imports))
        return {"ok": all(st.values()) if st else True, "imports": st}
    if action == "install":
        return install_packages(list(packages))
    return ensure_packages(packages=list(packages), imports=list(imports))
