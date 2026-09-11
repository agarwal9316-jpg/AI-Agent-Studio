"""P1.3 — Automations: schedule prompts, ticker, soft-degrade, chat link.

CRUD under data/automations.json; mock clock / force due.
Separate from company scheduler_service.
No GPL OWUI blobs — Studio reimplementation.
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.services.chat import automations_store as aus  # noqa: E402


def _iso_path(td: Path):
    """Redirect automations.json into a temp dir."""
    return patch("app.core.services.chat.automations_store.automations_path", lambda: td / "automations.json")


def _reset_ticker():
    aus.stop()
    aus.set_clock(None)


def test_crud_enable_delete():
    _reset_ticker()
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)
        with _iso_path(td):
            assert aus.list_automations() == []
            a = aus.create_automation(
                name="Morning brief",
                prompt="Summarize my day",
                schedule_kind="daily",
                hour=8,
                minute=30,
            )
            assert a["id"] and a["name"] == "Morning brief"
            assert a["prompt"] == "Summarize my day"
            assert a["schedule_kind"] == "daily"
            assert a["hour"] == 8 and a["minute"] == 30
            assert a["enabled"] is True
            assert a["next_run"]
            assert a["last_run"] == ""
            got = aus.get_automation(a["id"])
            assert got and got["name"] == "Morning brief"
            upd = aus.update_automation(a["id"], name="Morning brief v2", prompt="Do X")
            assert upd and upd["name"] == "Morning brief v2"
            assert upd["prompt"] == "Do X"
            off = aus.set_enabled(a["id"], False)
            assert off and off["enabled"] is False
            on = aus.set_enabled(a["id"], True)
            assert on and on["enabled"] is True
            hits = aus.list_automations(query="morning")
            assert len(hits) == 1 and hits[0]["id"] == a["id"]
            assert aus.delete_automation(a["id"]) is True
            assert aus.get_automation(a["id"]) is None
            assert aus.delete_automation("missing") is False
            assert aus.list_automations() == []
    _reset_ticker()
    print("✓ CRUD + enable/disable + search")


def test_schedule_kinds_next_run():
    _reset_ticker()
    # Fixed reference: 2026-09-11 12:00:00 UTC (Friday)
    base = 1757592000.0  # approx; we compute from datetime for clarity
    from datetime import datetime, timezone

    base = datetime(2026, 9, 11, 12, 0, 0, tzinfo=timezone.utc).timestamp()

    nxt_h = aus.compute_next_run(schedule_kind="hourly", after_ts=base)
    from datetime import datetime as dt

    h = dt.fromisoformat(nxt_h)
    assert h.hour == 13 and h.minute == 0

    nxt_d = aus.compute_next_run(schedule_kind="daily", hour=9, minute=0, after_ts=base)
    d = dt.fromisoformat(nxt_d)
    # 9:00 already passed → next day
    assert d.day == 12 and d.hour == 9

    # Saturday after Friday noon → weekday should land Monday
    fri = base
    nxt_w = aus.compute_next_run(schedule_kind="weekday", hour=9, minute=0, after_ts=fri)
    w = dt.fromisoformat(nxt_w)
    assert w.weekday() < 5
    assert w.hour == 9

    nxt_i = aus.compute_next_run(schedule_kind="interval", interval_minutes=15, after_ts=base)
    i = dt.fromisoformat(nxt_i)
    assert abs(i.timestamp() - (base + 15 * 60)) < 1

    label = aus.schedule_label(
        {"schedule_kind": "weekday", "hour": 9, "minute": 30, "interval_minutes": 60}
    )
    assert "Weekday" in label or "weekday" in label.lower()
    print("✓ schedule kinds + next_run + label")


def test_is_due_with_mock_clock():
    _reset_ticker()
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)
        with _iso_path(td):
            # Clock frozen
            t0 = 1_700_000_000.0
            aus.set_clock(lambda: t0)
            a = aus.create_automation(
                name="Due check",
                prompt="ping",
                schedule_kind="interval",
                interval_minutes=10,
                enabled=True,
            )
            # next_run is t0+10min → not due yet
            assert aus.is_due(a, t0) is False
            assert aus.is_due(a, t0 + 9 * 60) is False
            # Force next_run into the past
            items = aus.load_automations()
            items[0]["next_run"] = aus._now_iso(t0 - 1)
            aus.save_automations(items)
            a2 = aus.get_automation(a["id"])
            assert aus.is_due(a2, t0) is True
            # Disabled never due
            aus.set_enabled(a["id"], False)
            a3 = aus.get_automation(a["id"])
            assert aus.is_due(a3, t0) is False
    _reset_ticker()
    print("✓ is_due + mock clock")


def test_run_soft_degrade_no_api_key():
    _reset_ticker()
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)
        chats = td / "chats"
        chats.mkdir()
        with _iso_path(td):
            with patch("app.core.services.chat.chat_store.chats_dir", lambda: chats), patch(
                "app.core.services.chat.chat_store.chat_index_path", lambda: chats / "index.json"
            ), patch(
                "app.core.services.chat.chat_store.current_chat_path", lambda: chats / "current.json"
            ), patch(
                "app.core.services.chat.automations_store._resolve_llm",
                return_value={
                    "ok": True,
                    "api_key": "",
                    "model": "gpt-4o-mini",
                    "base_url": "https://api.openai.com/v1",
                },
            ):
                # Avoid touching real config.json active_chat_id
                with patch("app.core.services.chat.chat_store.load_config", return_value={}), patch(
                    "app.core.services.chat.chat_store.save_config", lambda *_a, **_k: None
                ):
                    a = aus.create_automation(
                        name="No key",
                        prompt="Hello world",
                        schedule_kind="daily",
                    )
                    res = aus.run_automation(a["id"], force=True)
                    assert res["ok"] is False
                    assert res["status"] == "failed"
                    assert "API key" in (res.get("error") or "")
                    assert res.get("chat_id")
                    refreshed = aus.get_automation(a["id"])
                    assert refreshed
                    assert refreshed["last_status"] == "failed"
                    assert refreshed["last_chat_id"] == res["chat_id"]
                    assert refreshed["last_run"]
                    assert refreshed["run_count"] == 1
                    chat_path = chats / f"{res['chat_id']}.json"
                    assert chat_path.is_file()
                    import json

                    data = json.loads(chat_path.read_text(encoding="utf-8"))
                    assert any("API key" in str(m.get("content") or "") for m in data.get("messages") or [])
    _reset_ticker()
    print("✓ run soft-degrade no API key + linked chat")


def test_run_mock_llm_success_and_tick_force_due():
    _reset_ticker()
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)
        chats = td / "chats"
        chats.mkdir()
        with _iso_path(td):
            with patch("app.core.services.chat.chat_store.chats_dir", lambda: chats), patch(
                "app.core.services.chat.chat_store.chat_index_path", lambda: chats / "index.json"
            ), patch(
                "app.core.services.chat.chat_store.current_chat_path", lambda: chats / "current.json"
            ), patch(
                "app.core.services.chat.chat_store.load_config", return_value={}
            ), patch(
                "app.core.services.chat.chat_store.save_config", lambda *_a, **_k: None
            ), patch(
                "app.core.services.chat.automations_store._resolve_llm",
                return_value={
                    "ok": True,
                    "api_key": "sk-test",
                    "model": "test-model",
                    "base_url": "https://example.test/v1",
                },
            ):
                def fake_completion(**kwargs):
                    assert kwargs.get("api_key") == "sk-test"
                    msgs = kwargs.get("messages") or []
                    assert msgs and msgs[0]["role"] == "user"
                    return ("AUTOMATION_REPLY_OK", None)

                a = aus.create_automation(
                    name="Tick me",
                    prompt="Say hi",
                    schedule_kind="interval",
                    interval_minutes=5,
                )
                t0 = 1_700_000_100.0
                aus.set_clock(lambda: t0)
                items = aus.load_automations()
                items[0]["next_run"] = aus._now_iso(t0 - 60)
                aus.save_automations(items)

                res = aus.run_automation(a["id"], force=True, chat_completion_fn=fake_completion)
                assert res["ok"] is True
                assert res["status"] == "success"
                assert "AUTOMATION_REPLY_OK" in (res.get("reply") or "")
                assert res.get("chat_id")
                refreshed = aus.get_automation(a["id"])
                assert refreshed["last_status"] == "success"
                assert refreshed["last_chat_id"]
                assert refreshed["next_run"]

                chat_path = chats / f"{res['chat_id']}.json"
                assert chat_path.is_file()

                items = aus.load_automations()
                items[0]["next_run"] = aus._now_iso(t0 - 1)
                aus.save_automations(items)
                with patch("app.core.services.chat.automations_store.run_automation") as mocked:
                    mocked.return_value = {"ok": True, "status": "success"}
                    n = aus.tick()
                    assert n == 1
                    assert mocked.called
    _reset_ticker()
    print("✓ mock LLM success + tick force due")


def test_company_scheduler_untouched():
    """Automations must not write schedules.json or alter company scheduler API."""
    from app.core.services.system import scheduler_service as sched

    assert hasattr(sched, "load_schedules")
    assert hasattr(sched, "add_schedule")
    assert hasattr(sched, "tick")
    src = (ROOT / "app" / "core" / "services" / "chat" / "automations_store.py").read_text(
        encoding="utf-8"
    )
    # Mentions company schedules only as a "separate from" note — must not import/call them
    assert "from app.core.services.system import scheduler_service" not in src
    assert "scheduler_service." not in src
    assert "gpl" in src.lower()
    assert "separate from" in src.lower()
    print("✓ company scheduler untouched")


def test_version_and_wiring():
    from app.version import __version__

    assert __version__ == "1.27.92", f"expected 1.27.92 got {__version__}"
    from app.paths import automations_path

    assert automations_path().name == "automations.json"
    page_py = ROOT / "app" / "ui" / "pages" / "automations_page.py"
    assert page_py.is_file()
    page_src = page_py.read_text(encoding="utf-8")
    assert "def page_automations" in page_src
    aw_src = (ROOT / "app" / "ui" / "app_window.py").read_text(encoding="utf-8")
    assert "automations_page.page_automations" in aw_src
    assert '"Automations"' in aw_src
    assert "Automations" in (ROOT / "app" / "ui" / "themes.py").read_text(encoding="utf-8")
    store_src = (ROOT / "app" / "core" / "services" / "chat" / "automations_store.py").read_text(
        encoding="utf-8"
    )
    assert "run_automation" in store_src
    assert "soft-degrad" in store_src.lower() or "soft_degrad" in store_src.lower()
    print("✓ version + wiring")


if __name__ == "__main__":
    test_crud_enable_delete()
    test_schedule_kinds_next_run()
    test_is_due_with_mock_clock()
    test_run_soft_degrade_no_api_key()
    test_run_mock_llm_success_and_tick_force_due()
    test_company_scheduler_untouched()
    test_version_and_wiring()
    print("\nAll P1.3 automations tests passed.")
