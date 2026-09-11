"""
In-app user guide — plain English so a non-technical person can use the product.
"""

from __future__ import annotations

from typing import Any

# Ordered first-run checklist (Home + Help) — Easy mode language
QUICK_START: list[dict[str, str]] = [
    {
        "id": "api",
        "title": "1. Connect your AI account",
        "body": (
            "On Start, tap “Connect now” and paste the key you got from OpenRouter or OpenAI. "
            "Think of it as a password. You only do this once."
        ),
        "page": "Home",
    },
    {
        "id": "chat",
        "title": "2. Talk to the AI",
        "body": (
            "Open “Talk to AI” in the left menu. Type a normal question at the bottom "
            "and press “Send message” (or Enter)."
        ),
        "page": "Chat",
    },
    {
        "id": "ask",
        "title": "3. Try a simple question",
        "body": (
            'Try: “What can you do on this PC?” or “List files on my Desktop” '
            "or click a yellow starter button on an empty chat."
        ),
        "page": "Chat",
    },
    {
        "id": "team",
        "title": "4. Optional: use an AI team",
        "body": (
            "Open AI Team → New goal → write what you want in normal words → Start team. "
            "Read the green finished answer when it appears."
        ),
        "page": "Team",
    },
    {
        "id": "own",
        "title": "5. Optional: make your own AI",
        "body": (
            "Open My AIs → Make my AI now. Give a name and style. No coding. "
            "Then talk to it from Talk to AI."
        ),
        "page": "Models",
    },
    {
        "id": "activity",
        "title": "6. See if something is busy",
        "body": "Open Activity to see recent work and whether the computer is busy. Press Refresh if unsure.",
        "page": "Monitor",
    },
]

CHAT_COACH_LINES: list[str] = [
    "Type like a text message. Press Enter to send · Shift+Enter for a new line.",
    "Green “Send message” starts the AI. “Stop” cancels if it is taking too long.",
    "Attach a file with 📎 · Search the web with 🔍 · Make an image with 🖼.",
    "Type #filename or #https://… to inject a doc/URL into this turn.",
    "Chip “Can use tools ✓” means the AI can help with files and the web.",
    "Left menu: Start · Talk to AI · AI Team · My AIs · Activity.",
]

# Page-specific one-liners (status or coach)
PAGE_TIPS: dict[str, str] = {
    "Home": "Pick one big green button. Connect first if you see the yellow warning.",
    "Chat": "Type below and press Send. Use #filename or #https://… to pull docs/URLs into context.",
    "Team": "New goal → write what you want → Start team → read the finished answer.",
    "Models": "Tap Make my AI now. You do not need expert tools.",
    "Monitor": "Shows recent activity. Green / no warnings means things are fine.",
    "Work": "Jobs waiting for you appear here. Open Approvals if something is stuck.",
    "Approvals": "The AI is waiting for your Yes/No before a sensitive step.",
    "Knowledge": "Add your own files so the AI can answer from them.",
    "Settings": "Only paste your connection key if the AI cannot answer. Leave other options alone.",
    "CEO": "Create big goals for the multi-agent company.",
    "Company": "Roles and work queue for background jobs.",
    "Patches": "Review code changes before they apply.",
    "Agents": "Named helpers used in advanced runs.",
    "Help": "Short guides in plain English. Or go back to Start.",
    "Org chart": "Draw who is on the AI team (advanced).",
}

FEATURE_CARDS: list[dict[str, str]] = [
    {
        "title": "Talk to AI",
        "body": "Chat like WhatsApp. The AI can search the web, open files, and help on this PC.",
        "page": "Chat",
    },
    {
        "title": "AI Team",
        "body": "Several helpers work on one goal and write messages you can read. Green box = finished answer.",
        "page": "Team",
    },
    {
        "title": "My AIs",
        "body": "Make a personal helper with a name and style. No coding.",
        "page": "Models",
    },
    {
        "title": "Activity",
        "body": "See if the computer is busy and what happened recently.",
        "page": "Monitor",
    },
    {
        "title": "My files",
        "body": "Index your documents so answers can use your own files.",
        "page": "Knowledge",
    },
]

SHORTCUTS_FRIENDLY: str = """
Everyday
  Enter          Send message
  Shift+Enter    New line
  ■ Stop         Cancel / stop the AI
  F2             This Help guide

Window
  Hide window    Put the app in the taskbar
  Make bigger    Fill the screen
  Exit app       Close completely

Chat extras (optional)
  Ctrl+G         Make an image
  Ctrl+M         Microphone
  Ctrl+N         New chat
  Ctrl+K         Jump menu (expert)
  #doc / #url    Pull a knowledge file, path, or URL into this turn
"""


def quick_start_for_ui(*, simple: bool = True) -> list[dict[str, str]]:
    """Return checklist; same plain list for both modes for now."""
    return list(QUICK_START)


def page_tip(page: str) -> str:
    return PAGE_TIPS.get(page, "")


def coach_banner_text() -> str:
    """One multi-line tip block for the chat coach bar."""
    return "  ·  ".join(CHAT_COACH_LINES)


def help_sections() -> list[dict[str, Any]]:
    """Sections for the in-app Help page (plain English)."""
    return [
        {
            "title": "Start here (5 minutes)",
            "items": list(QUICK_START),
        },
        {
            "title": "What each menu item does",
            "items": [
                {
                    "title": "Start",
                    "body": "Home screen with four big buttons. Beginners should live here.",
                    "page": "Home",
                },
                {
                    "title": "Talk to AI",
                    "body": "Your main chat. Type at the bottom, press Send message. Use starters if stuck.",
                    "page": "Chat",
                },
                {
                    "title": "AI Team",
                    "body": "Several AIs work on one goal together. New goal → Start team → read the green finished answer.",
                    "page": "Team",
                },
                {
                    "title": "My AIs",
                    "body": "Create a personal helper with a name and style. Expert train tools stay hidden until you ask.",
                    "page": "Models",
                },
                {
                    "title": "Activity",
                    "body": "See recent work and whether the computer is busy. Press Refresh if something looks frozen.",
                    "page": "Monitor",
                },
            ],
        },
        {
            "title": "Features at a glance",
            "items": list(FEATURE_CARDS),
        },
        {
            "title": "If something goes wrong",
            "items": [
                {
                    "title": "AI will not answer",
                    "body": "Go to Start → Connect now (or Settings → paste your connection key). Then try Talk to AI again.",
                    "page": "Home",
                },
                {
                    "title": "Window is too small",
                    "body": "Top right: “Make bigger”. To put it away: “Hide window”. To quit: “Exit app”.",
                    "page": "Home",
                },
                {
                    "title": "Too many menus",
                    "body": "Bottom of the left menu: choose “Easy menu” so only the main steps show.",
                    "page": "Home",
                },
            ],
        },
    ]
