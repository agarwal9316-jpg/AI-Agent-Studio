"""Page name → builder callables for AppWindow.show_page (extracted router)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from app.ui.app_window import AppWindow


def page_builders(app: "AppWindow") -> dict[str, Callable[[], None]]:
    """Return navigation name → zero-arg page builder."""
    from app.ui.pages import mgmt_pages
    from app.ui.pages import notes_page
    from app.ui.pages import channels_page
    from app.ui.pages import automations_page
    from app.ui.pages import plugins_page

    return {
        "Home": app._page_home,
        "Help": app._page_help,
        "Chat": app._page_chat,
        "Team": lambda: __import__(
            "app.ui.pages.team_page", fromlist=["page_team"]
        ).page_team(app),
        "Models": lambda: __import__(
            "app.ui.pages.models_page", fromlist=["page_models"]
        ).page_models(app),
        "Monitor": lambda: __import__(
            "app.ui.pages.monitor_page", fromlist=["page_monitor"]
        ).page_monitor(app),
        "Chats": lambda: __import__(
            "app.ui.pages.chats_page", fromlist=["page_chats"]
        ).page_chats(app),
        "Track": app._page_track,
        "Work": app._page_work_board,
        "Control plane": lambda: __import__(
            "app.ui.pages.control_plane_page", fromlist=["page_control_plane"]
        ).page_control_plane(app),
        "Approvals": app._page_approvals,
        "Patches": app._page_patches,
        "Knowledge": app._page_knowledge,
        "Notes": lambda: notes_page.page_notes(app),
        "Channels": lambda: channels_page.page_channels(app),
        "Automations": lambda: automations_page.page_automations(app),
        "Plugins": lambda: plugins_page.page_plugins(app),
        "Schedule": app._page_schedule,
        "Memory": lambda: mgmt_pages.page_memory(app),
        "Projects": lambda: mgmt_pages.page_projects(app),
        "Org chart": lambda: __import__(
            "app.ui.pages.org_page", fromlist=["page_workflow"]
        ).page_workflow(app),
        "Workflow": lambda: __import__(
            "app.ui.pages.org_page", fromlist=["page_workflow"]
        ).page_workflow(app),
        "Company": lambda: mgmt_pages.page_company(app),
        "CEO": lambda: mgmt_pages.page_ceo(app),
        "Agents": app._page_agents,
        "Tasks": app._page_tasks,
        "Runs": app._page_runs,
        "Usage": app._page_usage,
        "Settings": app._page_settings,
        "About": app._page_about,
    }
