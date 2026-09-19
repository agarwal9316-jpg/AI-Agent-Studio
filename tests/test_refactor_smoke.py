"""Smoke tests for AppWindow split + materialize path (no GUI required)."""
from __future__ import annotations

import ast
import unittest
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
    "app/ui/page_router.py",
]

SYMBOLS = {
    "app/ui/pages/mgmt_pages.py": ["page_memory", "page_projects", "page_company", "page_ceo"],
    "app/ui/pages/models_page.py": ["page_models"],
    "app/ui/pages/models_advanced.py": ["_build_advanced_models"],
    "app/ui/pages/chats_page.py": ["page_chats"],
    "app/ui/page_router.py": ["page_builders"],
}

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
            text = path.read_text(encoding="utf-8")
            for name in names:
                with self.subTest(rel=rel, name=name):
                    self.assertIn(f"def {name}", text)


if __name__ == "__main__":
    unittest.main()
