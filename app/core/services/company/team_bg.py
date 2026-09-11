"""App-level Team job — survives leaving the Team page (background work).

Why this exists:
  The Team UI is destroyed when you open Chat/Home/etc. If run state lived only
  on that page, the worker lost its stop flag, progress UI, and looked “dead”.
  Job state lives on the App window object and the worker only needs disk + API.
"""

from __future__ import annotations

import threading
from typing import Any, Callable


def job(app: Any) -> dict[str, Any]:
    """Return the singleton job dict attached to the app window."""
    j = getattr(app, "_team_job", None)
    if not isinstance(j, dict):
        j = {
            "running": False,
            "stop": False,
            "pause": False,
            "channel_id": "",
            "progress": "",
            "error": "",
            "cancelled": False,
            "ok": False,
            "thread": None,
        }
        app._team_job = j
    j.setdefault("pause", False)
    return j


def is_running(app: Any) -> bool:
    return bool(job(app).get("running"))


def channel_id(app: Any) -> str:
    return str(job(app).get("channel_id") or "")


def last_progress(app: Any) -> str:
    return str(job(app).get("progress") or "")


def request_stop(app: Any) -> None:
    j = job(app)
    j["stop"] = True
    j["pause"] = False  # stop clears pause wait
    try:
        from app.core.services.system.terminal_tool import kill_active_terminal

        kill_active_terminal()
    except Exception:  # noqa: BLE001
        pass
    try:
        if hasattr(app, "set_status"):
            app.set_status("Team stop requested — finishes current step, then stops", toast=True)
    except Exception:  # noqa: BLE001
        pass
    _notify_ui(app, "Stopping… (background)", busy=True)


def request_pause(app: Any) -> None:
    """Task #9: pause team between agent steps (does not kill current tool)."""
    j = job(app)
    if not j.get("running"):
        return
    j["pause"] = True
    try:
        if hasattr(app, "set_status"):
            app.set_status("Team paused — current step may finish, then waits", toast=True)
    except Exception:  # noqa: BLE001
        pass
    _notify_ui(app, "⏸ Team paused — press Resume", busy=True)


def request_resume(app: Any) -> None:
    j = job(app)
    j["pause"] = False
    try:
        if hasattr(app, "set_status"):
            app.set_status("Team resumed", toast=True)
    except Exception:  # noqa: BLE001
        pass
    _notify_ui(app, "▶ Team resumed", busy=True)


def toggle_pause(app: Any) -> bool:
    """Returns True if now paused."""
    j = job(app)
    if not j.get("running"):
        return False
    if j.get("pause"):
        request_resume(app)
        return False
    request_pause(app)
    return True


def is_paused(app: Any) -> bool:
    return bool(job(app).get("pause")) and bool(job(app).get("running"))


def should_stop(app: Any) -> bool:
    return bool(job(app).get("stop"))


def wait_if_paused(app: Any, *, on_progress: Callable[[str], None] | None = None) -> bool:
    """
    Block while paused. Returns True if stop was requested (caller should abort).
    """
    import time

    if not job(app).get("pause") or should_stop(app):
        return should_stop(app)
    if on_progress:
        try:
            on_progress("⏸ Paused — waiting for Resume…")
        except Exception:  # noqa: BLE001
            pass
    while job(app).get("pause") and not should_stop(app):
        time.sleep(0.3)
    return should_stop(app)


def set_progress(app: Any, msg: str) -> None:
    j = job(app)
    j["progress"] = (msg or "")[:400]
    # Status bar (throttled) — full feed refresh is handled by Team page soft-refresh
    import time as _time

    now = _time.time()
    last = float(j.get("_last_status_ts") or 0)
    if now - last >= 1.5:  # avoid flooding status / main thread
        j["_last_status_ts"] = now
        try:
            if hasattr(app, "set_status") and j.get("running"):
                app.set_status(f"Team working… {(msg or '')[:70]}")
        except Exception:  # noqa: BLE001
            pass
    _notify_ui(app, msg, busy=True)


def _notify_ui(app: Any, msg: str, *, busy: bool = False) -> None:
    """If Team page is open, refresh its live banner / feed. Never required for work."""

    def apply() -> None:
        try:
            if not app.winfo_exists():
                return
            # Only touch Team widgets when that page is visible
            if getattr(app, "_current_page", "") != "Team":
                return
            cb = getattr(app, "_team_ui_on_progress", None)
            if callable(cb):
                cb(msg, busy=busy)
        except Exception:  # noqa: BLE001
            pass

    try:
        app.after(0, apply)
    except Exception:  # noqa: BLE001
        pass


def start_on_channel(
    app: Any,
    channel_id: str,
    *,
    reset_if_done: bool = True,
    on_done: Callable[[dict[str, Any]], None] | None = None,
) -> bool:
    """
    Start pipeline/coordinate for an existing channel in a background thread.
    Returns False if already running or channel missing.
    """
    from app.services import team_channel as tc
    from app.services import workflow_graph as wfg

    j = job(app)
    if j.get("running"):
        try:
            app.set_status("Team already running in background — open AI Team or press Stop", toast=True)
        except Exception:  # noqa: BLE001
            pass
        return False

    ch0 = tc.load_channel(channel_id)
    if not ch0:
        return False

    j["running"] = True
    j["stop"] = False
    j["pause"] = False
    j["channel_id"] = channel_id
    j["progress"] = "Starting team in background…"
    j["error"] = ""
    j["cancelled"] = False
    j["ok"] = False
    tc.set_active_channel_id(channel_id)

    try:
        app.set_status("Team running in background — you can switch tabs", toast=True)
    except Exception:  # noqa: BLE001
        pass
    _notify_ui(app, "Team is working in background… you can open other pages.", busy=True)

    def worker() -> None:
        from app.core.services.company.team_coordinator import (
            run_coordinate_mode,
            run_pipeline_into_channel,
        )

        err = ""
        cancelled = False
        ok = False
        try:
            g = wfg.resolve_graph(graph_id=str(ch0.get("org_graph_id") or "") or None)

            def prog(msg: str) -> None:
                set_progress(app, msg)
                # Honor pause between progress ticks (agent steps)
                wait_if_paused(app, on_progress=lambda m: set_progress(app, m))

            def stop_fn() -> bool:
                # Block while paused; return True only when stop requested
                if wait_if_paused(app, on_progress=lambda m: set_progress(app, m)):
                    return True
                return should_stop(app)

            ch = tc.load_channel(channel_id) or ch0
            st0 = str(ch.get("status") or "")
            if reset_if_done and (
                st0 in ("done", "failed", "cancelled")
                or (st0 == "running" and ch.get("final_text"))
            ):
                # Clean re-run: clear stale finished answer so status cannot stay half-done
                prepared = tc.prepare_rerun(channel_id)
                ch = prepared or tc.load_channel(channel_id) or ch0
            else:
                if st0 not in ("running",):
                    tc.set_channel_status(ch, "running")
                    ch = tc.load_channel(channel_id) or ch

            if ch.get("mode") == "coordinate":
                res = run_coordinate_mode(
                    ch, graph=g, on_progress=prog, should_stop=stop_fn
                )
            else:
                res = run_pipeline_into_channel(
                    ch, graph=g, on_progress=prog, should_stop=stop_fn
                )
            cancelled = bool(res.get("cancelled") or should_stop(app))
            ok = bool(res.get("ok")) and not cancelled
            if not res.get("ok") and res.get("error"):
                err = str(res.get("error"))
        except Exception as e:  # noqa: BLE001
            err = str(e)

        def finish() -> None:
            j2 = job(app)
            j2["running"] = False
            j2["stop"] = False
            j2["error"] = err
            j2["cancelled"] = cancelled
            j2["ok"] = ok
            j2["thread"] = None
            if cancelled:
                j2["progress"] = "Stopped."
                try:
                    app.set_status("Team stopped", toast=True)
                except Exception:  # noqa: BLE001
                    pass
                _notify_ui(app, "Stopped. You can Start team again.", busy=False)
            elif err:
                j2["progress"] = f"Error: {err[:120]}"
                try:
                    app.set_status(f"Team error: {err[:80]}", toast=True)
                except Exception:  # noqa: BLE001
                    pass
                _notify_ui(app, f"Error: {err[:120]}", busy=False)
            else:
                j2["progress"] = "Done ✓"
                try:
                    app.set_status("Team finished — open AI Team for the answer", toast=True)
                except Exception:  # noqa: BLE001
                    pass
                _notify_ui(app, "Done ✓ — scroll for the green finished answer.", busy=False)
            if on_done:
                try:
                    on_done(
                        {
                            "ok": ok,
                            "cancelled": cancelled,
                            "error": err,
                            "channel_id": channel_id,
                        }
                    )
                except Exception:  # noqa: BLE001
                    pass

        try:
            app.after(0, finish)
        except Exception:  # noqa: BLE001
            # App closing — still clear flags
            j["running"] = False
            j["stop"] = False

    t = threading.Thread(target=worker, daemon=True, name="team-bg")
    j["thread"] = t
    t.start()
    return True


def bind_page_progress(app: Any, callback: Callable[..., None] | None) -> None:
    """Team page registers this so progress can refresh the feed when visible."""
    app._team_ui_on_progress = callback


def unbind_page_progress(app: Any) -> None:
    app._team_ui_on_progress = None
