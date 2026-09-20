"""Sidebar navigation structure and label helpers.

Extracted from AppWindow — pure data + light helpers so the god class
does not own the hub layout definition.
"""

from __future__ import annotations

from typing import Callable, Sequence


Hub = tuple[str, tuple[str, ...]]

# Canonical page names (sidebar + router must agree)
NAV_ITEMS: tuple[str, ...] = (
    "Home",
    "Help",
    "Chat",
    "Team",
    "Models",
    "Monitor",
    "Chats",
    "Track",
    "Control plane",
    "Work",
    "Approvals",
    "Patches",
    "Knowledge",
    "Notes",
    "Channels",
    "Automations",
    "Plugins",
    "Schedule",
    "Org chart",
    "Memory",
    "Projects",
    "Company",
    "CEO",
    "Agents",
    "Tasks",
    "Runs",
    "Usage",
    "Settings",
    "About",
)


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
                "Control plane",
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


def hub_description(title: str) -> str:
    """Short tooltip for hub section headers."""
    return {
        "MENU": "Everyday screens",
        "PRIMARY": "Main workspace",
        "WORKSPACE": "Team work, approvals, knowledge",
        "MORE": "Advanced tools and settings",
        "START HERE": "Getting started",
        "CHAT": "Conversations",
        "WORK": "Tasks and runs",
    }.get(title, title)


def page_description(name: str) -> str:
    """Short tooltip for a nav page button."""
    return {
        "Home": "Start here — guided steps",
        "Chat": "Talk to AI",
        "Team": "Multi-agent team runs",
        "Control plane": "Paperclip-style company OS — hire agents, tasks, budgets, heartbeats",
        "Work": "Work board by status",
        "Approvals": "Tool and board approvals",
        "Org chart": "Company org structure",
        "Models": "LLM providers and models",
        "Monitor": "Live activity",
        "Usage": "Token and cost usage",
        "Settings": "API keys and preferences",
        "Help": "Guides in plain English",
    }.get(name, name)
