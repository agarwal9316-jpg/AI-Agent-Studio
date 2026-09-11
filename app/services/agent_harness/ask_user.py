"""Structured ask-user questions queued for the GUI."""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from app.paths import data_dir

_lock = threading.Lock()
_pending: dict[str, dict[str, Any]] = {}
_answers: dict[str, Any] = {}


def queue_path() -> Path:
    return data_dir() / "pending_questions.json"


def ask_question(
    question: str,
    options: list[str] | None = None,
    *,
    multi: bool = False,
    timeout: float = 300,
) -> dict[str, Any]:
    """
    Queue a question for the UI. Blocks until answered or timeout.
    In headless/no-UI, returns timeout with options listed.
    """
    qid = uuid.uuid4().hex[:10]
    item = {
        "id": qid,
        "question": question,
        "options": list(options or []),
        "multi": multi,
        "created": time.time(),
        "status": "pending",
    }
    with _lock:
        _pending[qid] = item
        _persist()
    deadline = time.time() + max(5.0, float(timeout))
    while time.time() < deadline:
        with _lock:
            if qid in _answers:
                ans = _answers.pop(qid)
                _pending.pop(qid, None)
                _persist()
                return {"ok": True, "id": qid, "answer": ans, "question": question}
        time.sleep(0.25)
    with _lock:
        _pending.pop(qid, None)
        _persist()
    return {
        "ok": False,
        "error": "timeout waiting for user answer",
        "id": qid,
        "question": question,
        "options": options or [],
    }


def answer(qid: str, answer: Any) -> dict[str, Any]:
    with _lock:
        if qid not in _pending and qid not in _answers:
            # still accept late answers
            pass
        _answers[qid] = answer
        if qid in _pending:
            _pending[qid]["status"] = "answered"
        _persist()
    return {"ok": True, "id": qid}


def list_pending() -> list[dict[str, Any]]:
    with _lock:
        _load()
        return [dict(v) for v in _pending.values() if v.get("status") == "pending"]


def _persist() -> None:
    try:
        queue_path().write_text(
            json.dumps({"pending": list(_pending.values())}, indent=2),
            encoding="utf-8",
        )
    except Exception:  # noqa: BLE001
        pass


def _load() -> None:
    p = queue_path()
    if not p.exists():
        return
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        for it in data.get("pending") or []:
            if it.get("id") and it["id"] not in _pending:
                _pending[it["id"]] = it
    except Exception:  # noqa: BLE001
        pass
