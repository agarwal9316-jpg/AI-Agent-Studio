"""Sidebar navigation structure and label helpers.

Extracted from AppWindow — pure data + light helpers so the god class
does not own the hub layout definition.
"""

from __future__ import annotations

from typing import Callable, Sequence


Hub = tuple[str, tuple[str, ...]]


def nav_hubs(*, simple_ui: bool) -> list[Hub]:
    """Return sidebar hub sections for simple or full UI mode."""
    if simple_ui:
        return [
            (
                "MENU",
                ("Home", "Chat", "Team", "Models", "Monitor"),
            ),
        ]
    return [
        ("PRIMARY", ("Home", "Chat", "Team", "Models", "Monitor", "Help")),
        (
            "WORKSPACE",
            (
                "Work",
                "Approvals",
                "Knowledge",
                "Notes",
                "Channels",
                "Automations",
                "Plugins",
                "Org chart",
            ),
        ),
        (
            "MORE",
            (
                "Chats",
                "Track",
                "Company",
                "CEO",
                "Schedule",
                "Patches",
                "Agents",
                "Tasks",
                "Runs",
                "Projects",
                "Memory",
                "Usage",
                "Settings",
                "About",
            ),
        ),
    ]


def default_hub_expanded(*, simple_ui: bool) -> dict[str, bool]:
    """Default expand/collapse state for each hub header."""
    if simple_ui:
        return {"MENU": True, "START HERE": True, "PRIMARY": True, "CHAT": True, "WORK": True}
    return {
        "START HERE": True,
        "PRIMARY": True,
        "WORKSPACE": True,
        "MORE": False,
        "CHAT": True,
        "WORK": True,
        "MENU": True,
    }


def nav_label_for(
    name: str,
    *,
    simple_ui: bool,
    approval_count: int = 0,
    patches_count: int = 0,
    work_running: int = 0,
) -> str:
    """Build display label with icon + optional badge counts."""
    from app.ui.themes import nav_icon
    from app.ui.components.layman_copy import friendly_name

    icon = nav_icon(name)
    label = friendly_name(name, simple=simple_ui)
    if name == "Approvals":
        return f" {icon}  {label}  ({approval_count})" if approval_count else f" {icon}  {label}"
    if name == "Patches":
        return f" {icon}  {label}  ({patches_count})" if patches_count else f" {icon}  {label}"
    if name == "Work":
        return f" {icon}  {label}  ({work_running} run)" if work_running else f" {icon}  {label}"
    return f" {icon}  {label}"


def all_nav_page_names(*, simple_ui: bool) -> list[str]:
    """Flat list of page names in sidebar order."""
    names: list[str] = []
    for _, pages in nav_hubs(simple_ui=simple_ui):
        names.extend(pages)
    return names
