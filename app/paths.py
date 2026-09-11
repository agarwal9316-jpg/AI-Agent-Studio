"""Portable path helpers — everything resolves next to the app root."""

from __future__ import annotations

import sys
from pathlib import Path


def app_root() -> Path:
    """Root folder that contains Launch.bat / data / app.

    Dev: parent of the ``app`` package.
    Frozen (PyInstaller): folder containing the executable.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    d = app_root() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def agents_dir() -> Path:
    d = data_dir() / "agents"
    d.mkdir(parents=True, exist_ok=True)
    return d


def tasks_dir() -> Path:
    d = data_dir() / "tasks"
    d.mkdir(parents=True, exist_ok=True)
    return d


def runs_dir() -> Path:
    d = data_dir() / "runs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_path() -> Path:
    return data_dir() / "config.json"


def chats_dir() -> Path:
    d = data_dir() / "chats"
    d.mkdir(parents=True, exist_ok=True)
    return d


def current_chat_path() -> Path:
    """Legacy single-file chat; multi-chat uses chats_dir()/<id>.json."""
    return chats_dir() / "current.json"


def memory_path() -> Path:
    d = data_dir() / "memory"
    d.mkdir(parents=True, exist_ok=True)
    return d / "memory.json"


def notes_dir() -> Path:
    """Markdown/plain notes workspace (OWUI-inspired P1.1)."""
    d = data_dir() / "notes"
    d.mkdir(parents=True, exist_ok=True)
    return d


def channels_dir() -> Path:
    """Workspace channels timeline (OWUI-inspired P1.2). Separate from team_channels."""
    d = data_dir() / "channels"
    d.mkdir(parents=True, exist_ok=True)
    return d


def projects_dir() -> Path:
    d = data_dir() / "projects"
    d.mkdir(parents=True, exist_ok=True)
    return d


def company_dir() -> Path:
    d = data_dir() / "company"
    d.mkdir(parents=True, exist_ok=True)
    return d


def team_channels_dir() -> Path:
    """Teams-style multi-agent goal channels."""
    d = data_dir() / "team_channels"
    d.mkdir(parents=True, exist_ok=True)
    return d


def models_dir() -> Path:
    d = data_dir() / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def model_profiles_dir() -> Path:
    d = models_dir() / "profiles"
    d.mkdir(parents=True, exist_ok=True)
    return d


def model_adapters_dir() -> Path:
    d = models_dir() / "adapters"
    d.mkdir(parents=True, exist_ok=True)
    return d


def model_datasets_dir() -> Path:
    d = models_dir() / "datasets"
    d.mkdir(parents=True, exist_ok=True)
    return d


def train_jobs_dir() -> Path:
    d = models_dir() / "train_jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ops_dir() -> Path:
    d = data_dir() / "ops"
    d.mkdir(parents=True, exist_ok=True)
    return d


def company_goals_dir() -> Path:
    d = company_dir() / "goals"
    d.mkdir(parents=True, exist_ok=True)
    return d


def company_work_tasks_dir() -> Path:
    d = company_dir() / "work_tasks"
    d.mkdir(parents=True, exist_ok=True)
    return d


def company_approvals_dir() -> Path:
    d = company_dir() / "approvals"
    d.mkdir(parents=True, exist_ok=True)
    return d


def company_org_path() -> Path:
    return company_dir() / "org.json"


def chat_index_path() -> Path:
    return chats_dir() / "index.json"


def automations_path() -> Path:
    """Workspace Automations index (OWUI-inspired P1.3). Separate from company schedules.json."""
    return data_dir() / "automations.json"
