"""Roadmap — Filesystem sandbox profiles (1.27.96).

Named profiles (id/label/allow_roots/deny_writes/allow_shell), enforcement on
file + shell tools, custom roots, Settings-selectable config keys.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.version import __version__  # noqa: E402
from app.services.agent_harness import sandbox as sbx  # noqa: E402


def test_version():
    assert __version__ == "1.27.96", __version__
    print("✓ version 1.27.96")


def test_builtin_profiles_shape():
    profiles = sbx.list_profiles()
    ids = [p["id"] for p in profiles]
    assert "read_only_workspace" in ids
    assert "project_only" in ids
    assert "full_ask" in ids
    for p in profiles:
        assert "id" in p and "label" in p
        assert "allow_roots" in p and isinstance(p["allow_roots"], list)
        assert "deny_writes" in p and isinstance(p["deny_writes"], bool)
        assert "allow_shell" in p and isinstance(p["allow_shell"], bool)
    # Friendly labels present
    labs = sbx.profile_labels()
    assert labs["read_only_workspace"] == "Read-only workspace"
    assert labs["project_only"] == "Project-only"
    assert labs["full_ask"] == "Full disk with ask"
    assert sbx.normalize_profile_id("read_only") == "read_only_workspace"
    assert sbx.normalize_profile_id("full") == "full_ask"
    print("✓ builtin profiles shape + aliases")


def _cfg(profile: str, *, enabled: bool = True, custom: list[str] | None = None):
    return {
        "agent_sandbox_enabled": enabled,
        "agent_sandbox_profile": profile,
        "agent_sandbox_custom_roots": list(custom or []),
        "agent_sandbox_extra_write": list(custom or []),
        "agent_sandbox_allow_secrets": False,
        "terminal_cwd": "",
        "agent_cwd": "",
    }


def test_read_only_workspace_denies_writes_and_shell():
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp).resolve()
        target = td / "note.txt"
        target.write_text("hi", encoding="utf-8")
        cfg = _cfg("read_only_workspace")
        with patch("app.services.agent_harness.sandbox.load_config", return_value=cfg):
            sbx.clear_chat_context()
            sbx.set_chat_context(chat_id="c1", cwd=str(td), cwd_lock=False)
            # read ok
            r = sbx.check_path_access(str(target), write=False)
            assert r.get("ok"), r
            # write denied
            w = sbx.check_path_access(str(target), write=True)
            assert not w.get("ok"), w
            assert "denies writes" in (w.get("error") or "").lower() or "read-only" in (
                w.get("error") or ""
            ).lower()
            # shell denied
            sh = sbx.check_shell_access(str(td))
            assert not sh.get("ok"), sh
            assert "denies shell" in (sh.get("error") or "").lower()
            sbx.clear_chat_context()
    print("✓ read_only_workspace denies writes + shell")


def test_project_only_blocks_outside_roots():
    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp).resolve() / "proj"
        proj.mkdir()
        outside = Path(tmp).resolve() / "outside.txt"
        outside.write_text("x", encoding="utf-8")
        inside = proj / "in.txt"
        inside.write_text("y", encoding="utf-8")
        cfg = _cfg("project_only")
        with patch("app.services.agent_harness.sandbox.load_config", return_value=cfg):
            with patch("app.services.agent_harness.sandbox.data_dir", return_value=proj / "_data"):
                (proj / "_data").mkdir(exist_ok=True)
                sbx.clear_chat_context()
                sbx.set_chat_context(chat_id="c2", cwd=str(proj), cwd_lock=False)
                ok = sbx.check_path_access(str(inside), write=True)
                assert ok.get("ok"), ok
                bad = sbx.check_path_access(str(outside), write=True)
                assert not bad.get("ok"), bad
                assert "outside allowed roots" in (bad.get("error") or "")
                # shell outside blocked
                sh_bad = sbx.check_shell_access(str(outside.parent))
                # outside.parent is tmp which is parent of proj — not under proj
                # Actually outside.parent == tmp, proj is under tmp, so tmp is NOT under proj roots
                assert not sh_bad.get("ok"), sh_bad
                sh_ok = sbx.check_shell_access(str(proj))
                assert sh_ok.get("ok"), sh_ok
                sbx.clear_chat_context()
    print("✓ project_only blocks outside roots")


def test_full_ask_allows_paths_and_shell():
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp).resolve()
        f = td / "anywhere.txt"
        f.write_text("z", encoding="utf-8")
        cfg = _cfg("full_ask")
        with patch("app.services.agent_harness.sandbox.load_config", return_value=cfg):
            sbx.clear_chat_context()
            r = sbx.check_path_access(str(f), write=True)
            assert r.get("ok"), r
            sh = sbx.check_shell_access(str(td))
            assert sh.get("ok"), sh
            st = sbx.status()
            assert st["profile"] == "full_ask"
            assert st["full_disk"] is True
            assert st["allow_shell"] is True
    print("✓ full_ask allows paths + shell")


def test_custom_roots_expand_allow_list():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp).resolve()
        proj = base / "proj"
        extra = base / "extra"
        proj.mkdir()
        extra.mkdir()
        f = extra / "e.txt"
        f.write_text("e", encoding="utf-8")
        cfg = _cfg("project_only", custom=[str(extra)])
        with patch("app.services.agent_harness.sandbox.load_config", return_value=cfg):
            with patch("app.services.agent_harness.sandbox.data_dir", return_value=proj / "_data"):
                (proj / "_data").mkdir(exist_ok=True)
                sbx.clear_chat_context()
                sbx.set_chat_context(chat_id="c3", cwd=str(proj), cwd_lock=False)
                ok = sbx.check_path_access(str(f), write=True)
                assert ok.get("ok"), ok
                roots, _ = sbx.resolve_allow_roots()
                assert any(str(extra.resolve()) == str(r) for r in roots)
                sbx.clear_chat_context()
    print("✓ custom roots expand allow list")


def test_file_tools_surface_deny_message():
    from app.services.agent_harness import file_tools

    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp).resolve()
        target = td / "a.txt"
        target.write_text("a", encoding="utf-8")
        cfg = _cfg("read_only_workspace")
        with patch("app.services.agent_harness.sandbox.load_config", return_value=cfg):
            sbx.clear_chat_context()
            sbx.set_chat_context(chat_id="c4", cwd=str(td), cwd_lock=False)
            res = file_tools.write_file(str(target), "nope")
            assert res.get("ok") is False
            assert res.get("error")
            assert "Sandbox" in res["error"] or "denies" in res["error"].lower()
            sbx.clear_chat_context()
    print("✓ file_tools surfaces deny message")


def test_terminal_run_command_respects_shell_deny():
    from app.core.services.system import terminal_tool as tt

    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp).resolve()
        cfg = _cfg("read_only_workspace")
        with patch("app.services.agent_harness.sandbox.load_config", return_value=cfg):
            sbx.clear_chat_context()
            sbx.set_chat_context(chat_id="c5", cwd=str(td), cwd_lock=False)
            res = tt.run_command("echo hi", cwd=str(td))
            assert res.get("ok") is False
            assert "denies shell" in (res.get("error") or "").lower()
            sbx.clear_chat_context()
    print("✓ terminal run_command respects shell deny")


def test_set_active_profile_persists():
    saved: dict = {}

    def _load():
        return dict(saved) if saved else _cfg("workspace")

    def _save(cfg):
        saved.clear()
        saved.update(cfg)

    with patch("app.services.agent_harness.sandbox.load_config", side_effect=_load):
        with patch("app.services.agent_harness.sandbox.save_config", side_effect=_save):
            st = sbx.set_active_profile(
                "project_only",
                custom_roots=["/tmp/studio-extra"],
                enabled=True,
            )
            assert st["profile"] == "project_only"
            assert saved.get("agent_sandbox_profile") == "project_only"
            assert "/tmp/studio-extra" in (saved.get("agent_sandbox_custom_roots") or [])
    print("✓ set_active_profile persists config")


def test_status_lists_profiles():
    cfg = _cfg("workspace", enabled=True)
    with patch("app.services.agent_harness.sandbox.load_config", return_value=cfg):
        st = sbx.status()
        assert isinstance(st.get("profiles"), list)
        assert len(st["profiles"]) >= 3
        assert st.get("profile_label")
    print("✓ status lists profiles")


def main() -> int:
    tests = [
        test_version,
        test_builtin_profiles_shape,
        test_read_only_workspace_denies_writes_and_shell,
        test_project_only_blocks_outside_roots,
        test_full_ask_allows_paths_and_shell,
        test_custom_roots_expand_allow_list,
        test_file_tools_surface_deny_message,
        test_terminal_run_command_respects_shell_deny,
        test_set_active_profile_persists,
        test_status_lists_profiles,
    ]
    fails = 0
    for t in tests:
        try:
            t()
        except Exception as e:  # noqa: BLE001
            fails += 1
            print(f"FAIL {t.__name__}: {e}")
    if fails:
        print(f"\n{fails} failed")
        return 1
    print("\nAll sandbox profile tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
