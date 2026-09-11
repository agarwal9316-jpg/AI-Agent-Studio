"""Plain-English labels and tips for non-technical users.

Every string here should make sense to someone who never coded.
Technical jargon stays only in Expert mode.
"""

from __future__ import annotations

# Sidebar / page names shown in Easy mode (internal page id → friendly label)
FRIENDLY_PAGE: dict[str, str] = {
    "Home": "Start",
    "Chat": "Talk to AI",
    "Team": "AI Team",
    "Models": "My AIs",
    "Monitor": "Activity",
    "Help": "Help",
    "Settings": "Settings",
    "Org chart": "Team setup",
    "Knowledge": "My files",
    "Notes": "My notes",
    "Work": "Work list",
    "Approvals": "Approvals",
    "Chats": "Past chats",
    "Track": "Progress",
    "Patches": "Code review",
    "Memory": "Remembered notes",
    "Projects": "Projects",
    "Company": "Company",
    "CEO": "CEO desk",
    "Agents": "Helpers",
    "Tasks": "Tasks",
    "Runs": "Past runs",
    "Usage": "Usage",
    "Schedule": "Schedule",
    "About": "About",
}

# One-line tip under page title (Easy mode)
PAGE_BLURB: dict[str, str] = {
    "Home": "Choose one big button. You only need these four things.",
    "Chat": "Type below like a text message, then press Send. The AI can help with files and the web.",
    "Team": "Start a goal. Several AIs chat until they finish. Watch the messages appear.",
    "Models": "Create your own AI with the green button. No coding needed.",
    "Monitor": "See if the AI is busy, using the internet, or training. Refresh if unsure.",
    "Help": "Short guides in plain English. Or go back to Start.",
    "Notes": "Write notes. Attach them to chat so the AI reads the whole note.",
    "Settings": "Only change the connection key if the AI cannot answer. Leave other options alone.",
}

# Empty chat headline + steps (Easy mode) — matched to live grok.com copy
EMPTY_CHAT_TITLE = "What's on your mind?"
EMPTY_CHAT_WORDMARK = "Studio"  # app brand (not "Grok")

EMPTY_CHAT_STEPS_SIMPLE = (
    "1. Type your question in the big box at the bottom\n"
    "2. Press the green “Send message” button (or Enter)\n"
    "3. Wait a moment — the answer appears above\n"
    "4. Stuck? Click a yellow starter button below"
)

EMPTY_CHAT_STEPS_NO_KEY = (
    "0. First connect your AI account: go to Start → Connect now\n"
    "1. Then type your question in the box at the bottom\n"
    "2. Press “Send message”\n"
    "3. Wait for the answer above"
)

EMPTY_CHAT_STARTERS_HINT = "Click a starter to fill the box — then press Send message:"

EMPTY_CHAT = (
    "Write your question in the box at the bottom.\n"
    "Example: “What files are on my Desktop?”\n"
    "Then press Enter (or the Send message button)."
)

EMPTY_TEAM = (
    "No team goal yet.\n"
    "Click “New goal”, write what you want done in plain words, then Start."
)

# Composer — phrasing aligned with live grok.com (“Ask Grok anything” / “What's on your mind?”)
SEND_LABEL_SIMPLE = "Send message"
SEND_LABEL_EXPERT = "Send  ↵"
STOP_LABEL = "■  Stop"
COMPOSER_ASK_ANYTHING = "Ask anything…"
COMPOSER_WHATS_ON_MIND = "What's on your mind?"
COMPOSER_HINT_SIMPLE = (
    "Ask anything…  ·  #doc or #https://… injects into context  ·  Enter sends  ·  📎  ·  🎤"
)
COMPOSER_HINT_PLAN = (
    "Plan only — AI will outline steps, not run tools. Click the chip to allow tools again."
)
COMPOSER_PLACEHOLDER_EXAMPLES = (
    "Try: “What files are on my Desktop?” or “Search the web for today’s weather”"
)

# Side tool buttons (Easy mode — fewer, clearer)
TOOL_BTNS_SIMPLE: list[tuple[str, str]] = [
    ("+ More", "plus"),
    ("📎 Attach file", "file"),
    ("🔍 Search web", "search"),
    ("🖼 Make image", "image"),
    ("🎤 Speak", "mic"),
]

# Mode chip
MODE_TOOLS_ON = "Can use tools ✓"
MODE_PLAN_ONLY = "Plan only (no tools)"

# Window bar (keep short — long titles steal vertical space)
WINDOW_HINT = "Drag any outer edge or corner to resize the window"
WINDOW_TITLE = "AI Agent Studio"

# Status / toasts
STATUS_SIMPLE_ON = "Easy menu ON — only the main steps are shown"
STATUS_EXPERT_ON = "Expert menu ON — all pages are in the sidebar"
STATUS_STARTER = "Starter loaded — press Send message (or Enter)"
STATUS_SENDING = "AI is thinking…"
STATUS_DONE = "Answer ready"

# Team
TEAM_CHANNELS = "Your goals"
TEAM_ROSTER = "Team members"
TEAM_FINAL = "✓ Finished answer"
TEAM_EMPTY = "No goal yet. Click “+ New goal” and write what you want in normal words."
TEAM_SEND = "Send note"
TEAM_RUN = "▶ Start team"
TEAM_NEW_TITLE = "New team goal"
TEAM_NEW_HINT = (
    "Write what you want done, like messaging a helper.\n"
    "Example: “Research my competitors and write a short plan.”"
)
TEAM_ORG_LABEL = "Who works on it"
TEAM_ORG_AUTO = "✨ Auto-pick a team for me (recommended)"
TEAM_MODE_LABEL = "How they work"
TEAM_MODE_PIPELINE = "One by one (faster)"
TEAM_MODE_COORDINATE = "Discuss together (slower)"
TEAM_MODE_HINT = (
    "“One by one” is best for most people. “Discuss together” lets helpers reply to each other."
)

# Models
MODELS_SAVED = "Your saved AIs"
MODELS_ADVANCED_TOGGLE = "Show expert tools (train / advanced)"
MODELS_ADVANCED_HIDE = "Hide expert tools"
MODELS_EASY_BANNER = "Easiest way — make an AI in under a minute"
MODELS_EASY_NOTE = (
    "You do not need the sections below. Only open expert tools if someone technical asked you to."
)

# Monitor
MONITOR_EVENTS = "What happened recently"
MONITOR_SYSTEM = "This computer"
MONITOR_ALERTS = "Warnings"
MONITOR_JOBS = "Background jobs"
MONITOR_NO_EVENTS = "Nothing yet. Open Talk to AI or AI Team, then come back here."
MONITOR_NO_JOBS = "No background jobs yet."
MONITOR_KPI_FRIENDLY = True  # use softer KPI labels when painting

# Wizard
WIZARD_WHERE_CLOUD = "Internet AI (recommended) — uses the key you already added"
WIZARD_WHERE_LOCAL = "Offline · Ollama (local) — this computer only; needs free Ollama software"
WIZARD_RUNS_CLOUD = "Internet (cloud)"
WIZARD_RUNS_LOCAL = "This computer"
WIZARD_SUCCESS_HINT = "Your AI was saved under My AIs. You can chat with it now."

# First-run / Settings
SETTINGS_KEY_HINT = (
    "This is like a password for the AI service. Paste it once. You do not need the other options."
)

# Quick start (Easy)
QUICK_START_SIMPLE: list[dict[str, str]] = [
    {
        "id": "connect",
        "title": "1. Connect your AI account",
        "body": "On Start, tap Connect now and paste the key you got from OpenRouter or OpenAI. Like a password.",
        "page": "Home",
    },
    {
        "id": "talk",
        "title": "2. Talk to the AI",
        "body": "Open Talk to AI. Type a normal question at the bottom and press Send message.",
        "page": "Chat",
    },
    {
        "id": "team",
        "title": "3. Optional: use an AI team",
        "body": "Open AI Team → New goal → write what you want → Start team. Read the finished answer at the bottom.",
        "page": "Team",
    },
    {
        "id": "own",
        "title": "4. Optional: make your own AI",
        "body": "Open My AIs → Make my AI now. Give a name and style. Then chat with it.",
        "page": "Models",
    },
]


def friendly_name(page: str, *, simple: bool = True) -> str:
    if not simple:
        return page
    return FRIENDLY_PAGE.get(page, page)


def page_blurb(page: str) -> str:
    return PAGE_BLURB.get(page, "")


def send_label(*, simple: bool = True) -> str:
    return SEND_LABEL_SIMPLE if simple else SEND_LABEL_EXPERT


def composer_hint(*, simple: bool = True, mode: str = "action") -> str:
    if not simple:
        if (mode or "action").lower() == "plan":
            return "Plan mode — tools off · /action to switch · /image · /search · Ctrl+K palette"
        return f"{COMPOSER_ASK_ANYTHING}  ·  Action · #doc/#url · /plan · /image · /search · /stop · Ctrl+K"
    if (mode or "action").lower() == "plan":
        return COMPOSER_HINT_PLAN
    return COMPOSER_HINT_SIMPLE
