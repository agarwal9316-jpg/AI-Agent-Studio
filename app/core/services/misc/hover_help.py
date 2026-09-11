"""
Centralised, plain-English hover help for the GUI (Phase 1 -- user-friendly).

Purpose:
  - Single source of truth for "hover shows what this does" tooltips.
  - Every page and every chat control gets a short, non-technical description
    so a new user never has to guess what a button/menu/icon does.

Used by:
  - Sidebar nav buttons  (app_window._build_sidebar)
  - Chat composer + top-bar controls (app_window._page_chat)
  - Help / feature directory

All text is written in the same easy voice as `user_guide.py`.
"""

from __future__ import annotations

from typing import Any

from app.core.services.misc.user_guide import PAGE_TIPS, page_tip


# ---- Pages ------------------------------------------------------------
# Reuse the friendly per-page tips and extend with pages that have none yet.
PAGE_DESCRIPTIONS: dict[str, str] = {
    "Home": PAGE_TIPS.get("Home", "Start here: connect your AI account and pick a main job."),
    "Chat": PAGE_TIPS.get("Chat", "Chat like WhatsApp. The AI can search the web, open files, and help on this PC."),
    "Help": PAGE_TIPS.get("Help", "Short guides in plain English. F2 opens this too."),
    "Chats": "Manage your saved conversations: rename, pin, delete, or start a new one.",
    "Knowledge": PAGE_TIPS.get(
        "Knowledge", "Add your own files so the AI can answer questions from them."
    ),
    "Track": "Follow long-running AI work in one place (advanced).",
    "Work": PAGE_TIPS.get("Work", "Jobs waiting for you appear here. Open Approvals if something is stuck."),
    "Company": PAGE_TIPS.get("Company", "Roles and work queue for background AI jobs."),
    "CEO": PAGE_TIPS.get("CEO", "Create big goals for the multi-agent company."),
    "Approvals": PAGE_TIPS.get(
        "Approvals", "The AI is waiting for your Yes/No before a sensitive step."
    ),
    "Schedule": "Set timed jobs that run automatically and queue their results here.",
    "Org chart": PAGE_TIPS.get("Org chart", "Draw who is on the AI team (advanced)."),
    "Patches": PAGE_TIPS.get("Patches", "Review AI-proposed code changes before they are applied."),
    "Agents": PAGE_TIPS.get("Agents", "Named AI helpers you can save and reuse in advanced runs."),
    "Tasks": "Define repeatable tasks that the AI can run in sequence.",
    "Runs": "Run one or many tasks together and watch the output step by step.",
    "Projects": "Group related work, chats, and files into one project.",
    "Memory": "Long-term facts the AI remembers across chats.",
    "Usage": "See how many tokens you have used and your budget at a glance.",
    "Settings": PAGE_TIPS.get(
        "Settings", "Only add your connection key here if the AI cannot answer. Leave other options alone."
    ),
    "About": "Version, what this software is, and how it is built.",
}


def page_description(page: str) -> str:
    """Return a friendly description for a nav page (fallback to page_tip)."""
    d = PAGE_DESCRIPTIONS.get(page)
    if d:
        return d
    return page_tip(page) or page
# ---- Chat controls (top bar + composer) -------------------------------
# keyed by a logical id; each entry carries the on-screen label + friendly help.
CHAT_CONTROLS: dict[str, dict[str, str]] = {
    "plus": {"label": "＋", "help": "Add more: attach a file, make an image, search the web, read a screenshot, or use a tool."},
    "attach": {"label": "📎 Attach", "help": "Add a file (or drag one in) so the AI can read it as part of your question."},
    "folder": {"label": "📁 Folder", "help": "Point the AI at a folder. It can read that folder so answers use your files."},
    "search": {"label": "🔍 Search", "help": "Ask the AI to search the web for current information."},
    "image": {"label": "🖼 Image", "help": "Ask the AI to make an image from your words (requires an image model)."},
    "mic": {"label": "🎤 Mic", "help": "Speak instead of typing. Your voice is turned into text."},
    "speak": {"label": "🔊 Speak", "help": "Read the last assistant reply aloud (Settings → Voice)."},
    "send": {"label": "↑ Send", "help": "Send your message to the AI and start a reply. (Enter key does the same.)"},
    "stop": {"label": "■ Stop", "help": "Ask the AI to stop what it is doing right now."},
    "pause": {"label": "⏸ Pause", "help": "Pause a long run and continue from where it left off later."},
    "agent": {"label": "Agent…", "help": "Choose which AI persona answers in this chat."},
    "context": {"label": "Context…", "help": "Choose what the AI can see: which tools, files, and knowledge are active."},
    "more": {"label": "More…", "help": "Every extra power option: recipes, marketplace, system prompt, export and more."},
    "models": {"label": "Model", "help": "Choose which AI model answers. Bigger is often smarter; smaller is faster and cheaper."},
    "live": {"label": "Live", "help": "Show a side panel with the AI's thinking, tool activity, and finished files."},
    "setup": {
        "label": "Setup",
        "help": "Expand or collapse the right Setup panel: system prompt, model parameters, context size, and tool switches.",
    },
    "search_chats": {"label": "🔍 (chats)", "help": "Find something you said before, in this chat or across all chats."},
    "mode_plan": {"label": "Plan", "help": "Plan first, ask before acting. The AI shows you its plan and waits."},
    "mode_action": {"label": "Action", "help": "Act directly: the AI can use its tools (files, terminal, web) to do the job."},
    "cwd_lock": {"label": "🔒 lock", "help": "Lock the working folder so the AI can only touch files inside this folder."},
    "rename": {"label": "title", "help": "Give this chat a name you recognise."},
    "new_chat": {"label": "+", "help": "Start a brand-new empty chat."},
    "branch": {"label": "branch", "help": "Copy this chat from here so you can continue two ways at once."},
    "pin": {"label": "pin", "help": "Keep this chat at the top of your history list."},
    "export": {"label": "export", "help": "Save this conversation to a file to share or keep."},
    "overflow": {"label": "⋯", "help": "All extra chat options: export, branch, image, OCR, skills, marketplace and more."},
    "provider": {"label": "Provider", "help": "Which AI service powers the answers (for example OpenRouter or xAI Grok)."},
    "density": {"label": "Comfort / Compact", "help": "Switch how much spacing the reply area uses. Compact shows more at once."},
    "one_screen": {
        "label": "One screen",
        "help": "Hide the left menu, chat list, and CPU bar so the conversation fills the window. Esc or this button brings them back.",
    },
    "collapse_menu": {
        "label": "Menu",
        "help": "Hide or show the left page menu (Home, Chat, Team…).",
    },
    "collapse_chats": {
        "label": "Chats",
        "help": "Hide or show the chat list so replies get more width.",
    },
    "collapse_cpu": {
        "label": "CPU bar",
        "help": "Hide or show the CPU / GPU / disk bar at the top.",
    },
    "grok": {"label": "✦ Grok", "help": "One click: set Grok as your AI. No command line needed."},
    "search_internal": {"label": "🔍 (top bar)", "help": "Search inside your past chats and messages."},
    "mode": {"label": "Act / Plan", "help": "How the AI behaves: Action uses its tools to do the job now; Plan shows its plan and asks before acting."},
}

# Hubs shown in the sidebar.
HUB_DESCRIPTIONS: dict[str, str] = {
    "START HERE": "The most important places to get going.",
    "PRIMARY": "Your main daily screens: Home, Chat, Help.",
    "WORKSPACE": "Where AI does work and where you approve it.",
    "MORE": "Every other screen, grouped for when you need them.",
    "MENU": "The friendly menu with the everyday screens.",
    "CHAT": "Everything about talking to the AI.",
    "WORK": "Hands-on AI work, approvals, and automatic jobs.",
    "LIBRARY": "Your saved helpers, tasks, projects, and memory.",
    "SYSTEM": "Usage, settings, and about.",
}


def chat_control_help(key: str) -> str:
    """Return friendly hover help for a chat control id (fallback = empty)."""
    return str((CHAT_CONTROLS.get(key) or {}).get("help") or "")


def chat_control_label(key: str) -> str:
    """Return the on-screen label for a chat control id (for reference/docs)."""
    return str((CHAT_CONTROLS.get(key) or {}).get("label") or "")


def hub_description(title: str) -> str:
    """Return a friendly hover description for a sidebar hub header."""
    return HUB_DESCRIPTIONS.get(title, "A group of screens.")


def build_control_directory() -> list[dict[str, str]]:
    """All chat controls as [{id,label,help}] for the Help feature directory."""
    return [
        {"id": k, "label": v.get("label", ""), "help": v.get("help", "")}
        for k, v in CHAT_CONTROLS.items()
    ]