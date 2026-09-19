"""Smoke tests for AppWindow split + materialize path (no GUI required)."""
from __future__ import annotations

import ast
import base64
import re
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MODULES = [
    "app/ui/app_window.py",
    "app/ui/components/chat_thinking.py",
    "app/ui/components/chat_rail.py",
    "app/ui/components/chat_send.py",
    "app/ui/components/chat_dialogs.py",
    "app/ui/components/chat_render.py",
    "app/ui/components/chat_misc.py",
    "app/ui/pages/chat_page.py",
    "app/ui/pages/settings_page.py",
]

LARGE_PAGES = [
    "app/ui/pages/org_page.py",
    "app/ui/pages/org_page_ai.py",
    "app/ui/pages/team_page.py",
    "app/ui/pages/team_dialogs.py",
    "app/ui/pages/org_chart_view.py",
    "app/ui/pages/org_chart_widgets.py",
    "app/ui/pages/mgmt_pages.py",
    "app/ui/pages/models_page.py",
    "app/ui/pages/models_advanced.py",
    "app/ui/pages/chats_page.py",
]

SYMBOLS = {
    "app/ui/pages/team_page.py": ["page_team"],
    "app/ui/pages/team_dialogs.py": ["_render_message_card", "_open_new_goal_dialog"],
    "app/ui/pages/org_chart_view.py": ["OrgChartPanel"],
    "app/ui/pages/mgmt_pages.py": ["page_memory", "page_projects"],
    "app/ui/pages/models_page.py": ["page_models"],
    "app/ui/pages/models_advanced.py": ["_build_advanced_models"],
    "app/ui/pages/chats_page.py": ["page_chats"],
    "app/ui/page_router.py": ["page_builders"],
}

PAYLOAD_PREFIXES = [
    ("team_page.z", 10000),
    ("team_dialogs.z", 2000),
    ("org_chart_widgets.z", 2000),
    ("org_chart_view.z", 5000),
    ("mgmt_pages.z", 5000),
    ("models_page.z", 2000),
    ("models_advanced.z", 5000),
    ("chats_page.z", 5000),
    ("chat_thinking_v2.z", 5000),
    ("chat_rail_v2.z", 5000),
    ("chat_send_v2.z", 5000),
    ("app_window_v2.z", 20000),
]

BANNED_ROOT = {
    "check_chat.py",
    "check_chat2.py",
    "check_file.py",
    "check_runs.py",
    "check_runs2.py",
    "check_runs3.py",
    "find_naming.py",
    "fix_part1.py",
    "fix_part2.py",
    "fix_sysmon_ui.py",
    "fix_terminal.py",
    "fix_terminal2.py",
    "browser.py",
    "test_run.py",
}


def _decompress_prefix(prefix: str) -> bytes:
    payload_dir = ROOT / "scripts" / "refactor_payload"
    parts = sorted(
        p
        for p in payload_dir.glob(f"{prefix}*.b64")
        if re.search(r"\.z\d+\.b64$", p.name)
    )
    if not parts:
        raise FileNotFoundError(f"No chunks for {prefix}")
    padded = [p for p in parts if re.search(r"\.z\d{2}\.b64$", p.name)]
    use = padded if padded else parts
    b64 = "".join(re.sub(r"\s+", "", p.read_text(encoding="ascii")) for p in use)
    return zlib.decompress(base64.b64decode(b64))


class RefactorSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from app._ensure_refactor_modules import ensure_refactor_modules, needs_materialize

        ensure_refactor_modules(quiet=True)
        cls.needs = needs_materialize()

    def test_modules_materialized(self) -> None:
        self.assertFalse(self.needs, "modules still need materialize after ensure")

    def test_each_module_full_and_parses(self) -> None:
        for rel in MODULES:
            with self.subTest(rel=rel):
                path = ROOT / rel
                self.assertTrue(path.is_file(), f"missing {rel}")
                text = path.read_text(encoding="utf-8")
                self.assertGreaterEqual(path.stat().st_size, 5000, f"{rel} still stub-sized")
                self.assertNotIn("Bootstrap — auto-materializes", text[:120])
                ast.parse(text)

    def test_app_window_has_run_app_and_class(self) -> None:
        text = (ROOT / "app/ui/app_window.py").read_text(encoding="utf-8")
        self.assertIn("def run_app", text)
        self.assertIn("class AppWindow", text)
        self.assertIn("page_builders", text)

    def test_no_temp_root_scripts(self) -> None:
        present = {p.name for p in ROOT.glob("*.py")}
        leftover = BANNED_ROOT & present
        self.assertFalse(leftover, f"temp scripts still present: {leftover}")

    def test_large_pages_parse(self) -> None:
        for rel in LARGE_PAGES:
            with self.subTest(rel=rel):
                path = ROOT / rel
                self.assertTrue(path.is_file(), f"missing {rel}")
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("Bootstrap — auto-materializes", text[:120])
                ast.parse(text)

    def test_key_symbols_present(self) -> None:
        for rel, names in SYMBOLS.items():
            path = ROOT / rel
            if not path.is_file():
                self.fail(f"missing {rel}")
            text = path.read_text(encoding="utf-8")
            for name in names:
                with self.subTest(rel=rel, name=name):
                    self.assertTrue(
                        f"def {name}" in text or f"class {name}" in text,
                        f"missing {name}",
                    )

    def test_payloads_decompress(self) -> None:
        """Integrity: every primary payload set must decompress cleanly."""
        payload_dir = ROOT / "scripts" / "refactor_payload"
        if not payload_dir.is_dir():
            self.skipTest("no scripts/refactor_payload directory")
        for prefix, min_size in PAYLOAD_PREFIXES:
            with self.subTest(prefix=prefix):
                parts = list(payload_dir.glob(f"{prefix}*.b64"))
                if not parts:
                    continue
                try:
                    raw = _decompress_prefix(prefix)
                except Exception as exc:  # noqa: BLE001
                    self.fail(f"{prefix}: decompress failed: {exc}")
                self.assertGreaterEqual(
                    len(raw),
                    min_size,
                    f"{prefix}: decompressed only {len(raw)} bytes (min {min_size})",
                )
                text = raw.decode("utf-8")
                self.assertTrue(
                    "def " in text or "class " in text,
                    f"{prefix}: decompressed content looks empty of defs",
                )

    def test_ensure_health_file_api(self) -> None:
        from app._ensure_refactor_modules import materialize_status

        status = materialize_status()
        self.assertIsInstance(status, dict)
        self.assertGreaterEqual(len(status), 10)


if __name__ == "__main__":
    unittest.main()
