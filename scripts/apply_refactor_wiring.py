#!/usr/bin/env python3
"""Apply SystemMonitor + StatusBar wiring to app/ui/app_window.py.

Run from repo root:
  python scripts/apply_refactor_wiring.py

Idempotent where possible. Requires:
  app/ui/components/system_monitor.py
  app/ui/components/status_bar.py
  app/ui/components/navigation.py
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "app" / "ui" / "app_window.py"


def main() -> int:
    if not TARGET.exists():
        print("ERROR: app/ui/app_window.py not found", file=sys.stderr)
        return 1
    for req in (
        ROOT / "app/ui/components/system_monitor.py",
        ROOT / "app/ui/components/status_bar.py",
        ROOT / "app/ui/components/navigation.py",
    ):
        if not req.exists():
            print(f"ERROR: missing {req}", file=sys.stderr)
            return 1

    src = TARGET.read_text(encoding="utf-8")
    if "from app.ui.components.system_monitor import SystemMonitorBar" in src:
        print("Wiring already present (SystemMonitorBar import found). Skipping.")
        return 0

    old_import = "from app.ui.components.tooltip import add_tooltip"
    new_import = """from app.ui.components.tooltip import add_tooltip
from app.ui.components.system_monitor import SystemMonitorBar
from app.ui.components.status_bar import (
    ToastHost,
    attach_tooltip,
    build_status_text,
    ensure_version_in_message,
    toast_kind_from_text,
)
from app.ui.components.navigation import (
    nav_hubs as _nav_hubs_data,
    nav_label_for as _nav_label_for_data,
    default_hub_expanded,
)"""
    if old_import not in src:
        print("ERROR: import anchor not found", file=sys.stderr)
        return 1
    src = src.replace(old_import, new_import, 1)

    old_set = '''    def _set_sysmon_collapsed(self, hidden: bool, *, persist: bool = True) -> None:
        self._sysmon_collapsed = bool(hidden)
        bar = getattr(self, "_sysmon_bar", None)
        try:
            if bar is not None:
                if hidden:
                    bar.grid_remove()
                else:
                    bar.grid()
        except Exception:  # noqa: BLE001
            pass
        if persist:
            self._persist_chrome()
        self._refresh_view_buttons()
'''
    new_set = '''    def _set_sysmon_collapsed(self, hidden: bool, *, persist: bool = True) -> None:
        self._sysmon_collapsed = bool(hidden)
        mon = getattr(self, "_sysmon", None)
        if mon is not None:
            mon.set_collapsed(hidden)
        else:
            bar = getattr(self, "_sysmon_bar", None)
            try:
                if bar is not None:
                    if hidden:
                        bar.grid_remove()
                    else:
                        bar.grid()
            except Exception:  # noqa: BLE001
                pass
        if persist:
            self._persist_chrome()
        self._refresh_view_buttons()
'''
    if old_set not in src:
        print("ERROR: _set_sysmon_collapsed body not found", file=sys.stderr)
        return 1
    src = src.replace(old_set, new_set, 1)

    old_toggle = '''    def _toggle_sysmon_bar(self) -> None:
        nxt = not bool(getattr(self, "_sysmon_collapsed", False))
        self._set_sysmon_collapsed(nxt)
        self.set_status("CPU bar hidden" if nxt else "CPU bar shown")
'''
    new_toggle = '''    def _toggle_sysmon_bar(self) -> None:
        mon = getattr(self, "_sysmon", None)
        if mon is not None:
            nxt = mon.toggle()
            self._sysmon_collapsed = nxt
        else:
            nxt = not bool(getattr(self, "_sysmon_collapsed", False))
            self._set_sysmon_collapsed(nxt)
        self.set_status("CPU bar hidden" if nxt else "CPU bar shown")
        self._persist_chrome()
        self._refresh_view_buttons()
'''
    if old_toggle not in src:
        print("ERROR: _toggle_sysmon_bar body not found", file=sys.stderr)
        return 1
    src = src.replace(old_toggle, new_toggle, 1)

    tree = ast.parse(src)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "AppWindow")
    targets = {
        "_build_system_monitor_bar",
        "_update_system_monitor",
        "_draw_mini_graph",
        "_status_text",
        "set_status",
        "_toast",
        "_destroy_toast",
        "_tooltip",
        "_start_status_refresh",
        "_nav_hubs",
        "_nav_label_for",
    }
    ranges = {}
    for n in cls.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in targets:
            ranges[n.name] = (n.lineno - 1, n.end_lineno)

    missing = targets - set(ranges)
    if missing:
        print(f"ERROR: methods not found: {sorted(missing)}", file=sys.stderr)
        return 1

    replacements = {
        "_build_system_monitor_bar": '''    def _build_system_monitor_bar(self) -> None:
        """Build the system resource monitoring bar at top of main content."""
        self._sysmon = SystemMonitorBar(
            self._main_col,
            after=self.after,
        )
        self._sysmon_bar = self._sysmon.build()
        self._sysmon_running = True
''',
        "_update_system_monitor": '''    def _update_system_monitor(self) -> None:
        """Deprecated: updates are owned by SystemMonitorBar."""
        mon = getattr(self, "_sysmon", None)
        if mon is not None:
            mon._update()
''',
        "_draw_mini_graph": '''    def _draw_mini_graph(self, graph_frame, history, key) -> None:
        """Deprecated: drawing is owned by SystemMonitorBar."""
        mon = getattr(self, "_sysmon", None)
        if mon is not None:
            mon._draw_mini_graph(graph_frame, history, key)
''',
        "_status_text": '''    def _status_text(self) -> str:
        return build_status_text(
            task_status=getattr(self, "_task_status", "none"),
            llm_phase=getattr(self, "_llm_phase", "idle"),
        )
''',
        "set_status": '''    def set_status(self, text: str | None = None, *, toast: bool = False) -> None:
        msg = ensure_version_in_message(text or self._status_text())
        try:
            self.status.configure(text=msg)
        except Exception:  # noqa: BLE001
            pass
        if toast and text:
            self._toast(text, kind=toast_kind_from_text(text))
''',
        "_toast": '''    def _toast(self, message: str, *, kind: str = "info", ms: int = 3200) -> None:
        """Non-blocking toast in the top-right of the main window."""
        host = getattr(self, "_toast_host", None)
        if host is None:
            self._toast_host = ToastHost(self, self.after)
            host = self._toast_host
        host.show(message, kind=kind, ms=ms)
''',
        "_destroy_toast": '''    def _destroy_toast(self, fr: Any) -> None:
        host = getattr(self, "_toast_host", None)
        if host is not None:
            host._destroy(fr)
''',
        "_tooltip": '''    def _tooltip(self, widget: Any, text: str) -> None:
        """Attach a friendly hover tooltip to a widget (safe no-op on failure)."""
        attach_tooltip(widget, text)
''',
        "_start_status_refresh": '''    def _start_status_refresh(self) -> None:
        """Periodic status bar refresh with system metrics (every 3s)."""

        def tick() -> None:
            try:
                if self.winfo_exists():
                    self.set_status()
            except Exception:  # noqa: BLE001
                pass
            try:
                if self.winfo_exists():
                    self.after(3000, tick)
            except Exception:  # noqa: BLE001
                pass

        self.after(3000, tick)
''',
        "_nav_hubs": '''    def _nav_hubs(self) -> list[tuple[str, tuple[str, ...]]]:
        """Simple mode: 5 pages only. Full mode: Primary + Workspace + More."""
        return _nav_hubs_data(simple_ui=self._is_simple_ui())
''',
        "_nav_label_for": '''    def _nav_label_for(self, name: str) -> str:
        return _nav_label_for_data(
            name,
            simple_ui=self._is_simple_ui(),
            approval_count=self._approval_badge_count() if name == "Approvals" else 0,
            patches_count=self._patches_badge_count() if name == "Patches" else 0,
            work_running=self._work_running_count() if name == "Work" else 0,
        )
''',
    }

    lines = src.splitlines(keepends=True)
    for name, (start, end) in sorted(ranges.items(), key=lambda x: -x[1][0]):
        text = replacements[name]
        if not text.endswith("\n"):
            text += "\n"
        lines[start:end] = [text]

    new_src = "".join(lines)
    ast.parse(new_src)
    TARGET.write_text(new_src, encoding="utf-8")
    print(f"OK: wired {TARGET}")
    print(f"Lines: {src.count(chr(10))+1} -> {new_src.count(chr(10))+1}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
