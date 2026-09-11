"""
Laptop GUI / OS control for the LLM — screenshots, mouse, keyboard, windows, clipboard.
Unrestricted by default (user Safety switch is separate, in terminal layer).
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from app.paths import data_dir

GUI_BLOCK_RE = re.compile(
    r"<<<GUI>>>\s*(.*?)\s*<<<END_GUI>>>",
    re.DOTALL | re.IGNORECASE,
)
SCREENSHOT_BLOCK_RE = re.compile(
    r"<<<SCREENSHOT>>>\s*(.*?)\s*<<<END_SCREENSHOT>>>",
    re.DOTALL | re.IGNORECASE,
)
CLIPBOARD_BLOCK_RE = re.compile(
    r"<<<CLIPBOARD>>>\s*(.*?)\s*<<<END_CLIPBOARD>>>",
    re.DOTALL | re.IGNORECASE,
)
WINDOWS_BLOCK_RE = re.compile(
    r"<<<WINDOWS>>>\s*(.*?)\s*<<<END_WINDOWS>>>",
    re.DOTALL | re.IGNORECASE,
)


def _import_gui():
    try:
        import pyautogui  # type: ignore

        pyautogui.FAILSAFE = True  # corner abort
        pyautogui.PAUSE = 0.05
        return pyautogui, None
    except Exception as e:  # noqa: BLE001
        return None, str(e)


def screenshots_dir() -> Path:
    d = data_dir() / "screenshots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def take_screenshot(name: str | None = None) -> dict[str, Any]:
    pag, err = _import_gui()
    if not pag:
        return {"ok": False, "error": f"pyautogui unavailable: {err}"}
    try:
        from datetime import datetime

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = (name or f"shot_{ts}").replace(" ", "_")
        if not fname.lower().endswith(".png"):
            fname += ".png"
        path = screenshots_dir() / fname
        img = pag.screenshot()
        img.save(str(path))
        w, h = img.size
        return {
            "ok": True,
            "path": str(path.resolve()),
            "width": w,
            "height": h,
            "note": "Screenshot saved. Open the file or attach it in a later message if the model supports vision.",
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def run_gui_actions(script: str) -> dict[str, Any]:
    """
    Execute a small JSON or line-oriented GUI script.

    Preferred JSON list:
    [
      {"action": "click", "x": 100, "y": 200},
      {"action": "type", "text": "hello", "interval": 0.02},
      {"action": "hotkey", "keys": ["ctrl", "s"]},
      {"action": "press", "key": "enter"},
      {"action": "move", "x": 50, "y": 50, "duration": 0.2},
      {"action": "scroll", "clicks": -3},
      {"action": "sleep", "seconds": 0.5},
      {"action": "position"}
    ]
    """
    pag, err = _import_gui()
    if not pag:
        return {"ok": False, "error": f"pyautogui unavailable: {err}. pip install pyautogui pillow"}

    text = (script or "").strip()
    actions: list[Any]
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            actions = [parsed]
        elif isinstance(parsed, list):
            actions = parsed
        else:
            return {"ok": False, "error": "GUI JSON must be object or array"}
    except json.JSONDecodeError:
        # line protocol: action arg...
        actions = []
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(maxsplit=1)
            act = parts[0].lower()
            rest = parts[1] if len(parts) > 1 else ""
            if act == "click":
                x, y = [int(float(v)) for v in rest.split()[:2]]
                actions.append({"action": "click", "x": x, "y": y})
            elif act == "type":
                actions.append({"action": "type", "text": rest})
            elif act == "hotkey":
                actions.append({"action": "hotkey", "keys": rest.split()})
            elif act == "press":
                actions.append({"action": "press", "key": rest.strip()})
            elif act == "sleep":
                actions.append({"action": "sleep", "seconds": float(rest or "0.5")})
            elif act == "position":
                actions.append({"action": "position"})
            else:
                return {"ok": False, "error": f"Unknown line action: {act}"}

    log: list[str] = []
    try:
        for step in actions:
            a = (step.get("action") or "").lower()
            if a == "click":
                pag.click(int(step["x"]), int(step["y"]), clicks=int(step.get("clicks") or 1))
                log.append(f"click {step['x']},{step['y']}")
            elif a == "move":
                pag.moveTo(
                    int(step["x"]),
                    int(step["y"]),
                    duration=float(step.get("duration") or 0.15),
                )
                log.append(f"move {step['x']},{step['y']}")
            elif a == "type":
                pag.typewrite(str(step.get("text") or ""), interval=float(step.get("interval") or 0.02))
                log.append(f"type {len(str(step.get('text') or ''))} chars")
            elif a == "write":
                # unicode-friendly
                pag.write(str(step.get("text") or ""), interval=float(step.get("interval") or 0.02))
                log.append("write text")
            elif a == "hotkey":
                keys = step.get("keys") or []
                pag.hotkey(*[str(k) for k in keys])
                log.append(f"hotkey {'+'.join(map(str, keys))}")
            elif a == "press":
                pag.press(str(step.get("key") or "enter"))
                log.append(f"press {step.get('key')}")
            elif a == "scroll":
                pag.scroll(int(step.get("clicks") or 0))
                log.append(f"scroll {step.get('clicks')}")
            elif a == "sleep":
                time.sleep(float(step.get("seconds") or 0.5))
                log.append(f"sleep {step.get('seconds')}")
            elif a == "position":
                x, y = pag.position()
                log.append(f"position {x},{y}")
            elif a == "screenshot":
                r = take_screenshot(step.get("name"))
                log.append(f"screenshot {r}")
            else:
                log.append(f"skip unknown {a}")
        return {"ok": True, "steps": log, "count": len(log)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "steps": log}


def clipboard_op(body: str) -> dict[str, Any]:
    """
    get
    set <text>
    or JSON {"op":"get"} / {"op":"set","text":"..."}
    """
    text = (body or "").strip()
    op = "get"
    value = ""
    try:
        data = json.loads(text)
        op = (data.get("op") or "get").lower()
        value = data.get("text") or ""
    except json.JSONDecodeError:
        if text.lower().startswith("set"):
            op = "set"
            value = text[3:].lstrip()
        elif text.lower() in ("get", ""):
            op = "get"
        else:
            op = "set"
            value = text

    try:
        import tkinter as tk

        r = tk.Tk()
        r.withdraw()
        r.update()
        if op == "get":
            try:
                content = r.clipboard_get()
            except tk.TclError:
                content = ""
            r.destroy()
            return {"ok": True, "op": "get", "text": content}
        r.clipboard_clear()
        r.clipboard_append(value)
        r.update()
        r.destroy()
        return {"ok": True, "op": "set", "chars": len(value)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def windows_op(body: str) -> dict[str, Any]:
    """list | focus <title substring> | JSON"""
    text = (body or "list").strip()
    op = "list"
    title = ""
    try:
        data = json.loads(text)
        op = (data.get("op") or "list").lower()
        title = data.get("title") or ""
    except json.JSONDecodeError:
        parts = text.split(maxsplit=1)
        op = parts[0].lower()
        title = parts[1] if len(parts) > 1 else ""

    if op == "list":
        # PowerShell list
        import subprocess

        ps = (
            "Get-Process | Where-Object {$_.MainWindowTitle} | "
            "Select-Object Id,ProcessName,MainWindowTitle | ConvertTo-Json -Compress"
        )
        try:
            proc = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    ps,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            return {
                "ok": proc.returncode == 0,
                "op": "list",
                "stdout": (proc.stdout or "")[:50000],
                "stderr": proc.stderr or "",
            }
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    if op == "focus" and title:
        import subprocess

        # Best-effort focus by window title
        ps = f"""
$p = Get-Process | Where-Object {{ $_.MainWindowTitle -like '*{title.replace("'", "''")}*' }} | Select-Object -First 1
if ($null -eq $p) {{ throw 'Window not found' }}
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class W {{
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
}}
"@
[W]::SetForegroundWindow($p.MainWindowHandle) | Out-Null
$p | Select-Object Id,ProcessName,MainWindowTitle | ConvertTo-Json -Compress
"""
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            return {
                "ok": proc.returncode == 0,
                "op": "focus",
                "stdout": proc.stdout or "",
                "stderr": proc.stderr or "",
            }
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    return {"ok": False, "error": f"Unknown windows op or missing title: {text[:80]}"}


def extract_gui_blocks(text: str) -> list[str]:
    return [m.group(1).strip() for m in GUI_BLOCK_RE.finditer(text or "") if m.group(1).strip()]


def extract_screenshot_blocks(text: str) -> list[str]:
    return [m.group(1).strip() for m in SCREENSHOT_BLOCK_RE.finditer(text or "")]


def extract_clipboard_blocks(text: str) -> list[str]:
    return [m.group(1).strip() for m in CLIPBOARD_BLOCK_RE.finditer(text or "")]


def extract_windows_blocks(text: str) -> list[str]:
    vals = [m.group(1).strip() for m in WINDOWS_BLOCK_RE.finditer(text or "")]
    # empty body means list
    return vals if vals else []


def laptop_tool_instructions() -> str:
    return """
## Laptop control tools (full desktop use)

### Screenshot
<<<SCREENSHOT>>>
optional_name
<<<END_SCREENSHOT>>>

### GUI (mouse/keyboard) — JSON array preferred
<<<GUI>>>
[
  {"action": "position"},
  {"action": "click", "x": 100, "y": 200},
  {"action": "type", "text": "hello"},
  {"action": "hotkey", "keys": ["ctrl", "s"]},
  {"action": "press", "key": "enter"},
  {"action": "sleep", "seconds": 0.5}
]
<<<END_GUI>>>

### Clipboard
<<<CLIPBOARD>>>
get
<<<END_CLIPBOARD>>>
<<<CLIPBOARD>>>
set text to put on clipboard
<<<END_CLIPBOARD>>>

### Windows
<<<WINDOWS>>>
list
<<<END_WINDOWS>>>
<<<WINDOWS>>>
focus Notepad
<<<END_WINDOWS>>>

Use SCREENSHOT to see the UI, then GUI to interact. Combine with TERMINAL for installs and files.
Move mouse to the top-left screen corner to abort pyautogui failsafe if a loop goes wrong.
""".strip()
