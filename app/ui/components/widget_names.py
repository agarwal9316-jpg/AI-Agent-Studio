"""Widget naming system for AI Agent Studio GUI.

Provides hierarchical, logical names for every GUI component to enable:
- Automated testing (Playwright, Selenium, etc.)
- Accessibility (screen readers)
- Debugging and development
- Programmatic interaction

Naming convention:
    <window>.<region>.<component_type>.<purpose>
    e.g., "app.sidebar.nav.primary.home_btn"
         "app.content.chat.composer.input"
         "app.status_bar.version_lbl"

Component type prefixes:
    btn_  = Button
    lbl_  = Label
    frm_  = Frame
    scr_  = ScrollableFrame/Scrollbar
    txt_  = Textbox/Entry
    pnl_  = Panel (Frame used as container)
    hdr_  = Header
    ftr_  = Footer
    bar_  = Bar (status, tool, save, etc.)
    mnu_  = Menu
    tab_  = Tab/TabView
    cvs_  = Canvas
    img_  = Image/Label with image
    sep_  = Separator
    dlg_  = Dialog/Toplevel
    pop_  = Popup/Menu
    spl_  = Splitter/PanedWindow
    grp_  = Group/LabelFrame
"""

from __future__ import annotations

import customtkinter as ctk
from typing import Any, Optional


# =============================================================================
# Naming Constants
# =============================================================================

# Root window
WINDOW_NAME = "app"

# Main regions
REGION_SIDEBAR = "sidebar"
REGION_CONTENT = "content"
REGION_STATUS_BAR = "status_bar"
REGION_SYSTEM_MONITOR = "system_monitor"
REGION_COMMAND_PALETTE = "command_palette"
REGION_SHORTCUTS_HELP = "shortcuts_help"

# Sidebar sub-regions
SIDEBAR_NAV = "nav"
SIDEBAR_FOOTER = "footer"
# =============================================================================
# Core Naming Functions
# =============================================================================

def build_name(*parts: str) -> str:
    """Build a hierarchical widget name from parts."""
    return ".".join(part for part in parts if part)


def set_widget_name(widget: Any, name: str) -> None:
    """Set a logical name on a widget for identification.
    
    Sets both tkinter's internal name (for winfo_name) and a custom attribute.
    """
    if widget is None:
        return
    try:
        # Set tkinter's internal name (used by winfo_name, winfo_pathname)
        widget._name = name
    except Exception:
        pass
    try:
        # Also set a custom attribute for easy access
        widget.widget_name = name
    except Exception:
        pass


def get_widget_name(widget: Any) -> Optional[str]:
    """Get the logical name of a widget."""
    try:
        return getattr(widget, "widget_name", None) or getattr(widget, "_name", None)
    except Exception:
        return None


def find_widget_by_name(root: Any, name: str) -> Optional[Any]:
    """Find a widget by its logical name (depth-first search)."""
    if get_widget_name(root) == name:
        return root
    try:
        for child in root.winfo_children():
            result = find_widget_by_name(child, name)
            if result:
                return result
    except Exception:
        pass
    return None


def find_widgets_by_prefix(root: Any, prefix: str) -> list[Any]:
    """Find all widgets whose name starts with prefix."""
    results = []
    def _search(widget: Any):
        wname = get_widget_name(widget)
        if wname and wname.startswith(prefix):
            results.append(widget)
        try:
            for child in widget.winfo_children():
                _search(child)
        except Exception:
            pass
    _search(root)
    return results

# Navigation hubs
HUB_PRIMARY = "primary"
HUB_WORKSPACE = "workspace"
HUB_MORE = "more"
HUB_SETTINGS = "settings"
# =============================================================================
# Convenience Functions for Common Patterns
# =============================================================================

def name_sidebar_nav_button(hub: str, page: str) -> str:
    """Name for a navigation button in sidebar."""
    return build_name(WINDOW_NAME, REGION_SIDEBAR, SIDEBAR_NAV, hub, f"{PREFIX_BUTTON}_{page}")


def name_sidebar_hub_header(hub: str) -> str:
    """Name for a sidebar hub header (collapsible section title)."""
    return build_name(WINDOW_NAME, REGION_SIDEBAR, SIDEBAR_NAV, hub, f"{PREFIX_HEADER}_{hub}")


def name_sidebar_hub_items_frame(hub: str) -> str:
    """Name for the frame containing nav items in a hub."""
    return build_name(WINDOW_NAME, REGION_SIDEBAR, SIDEBAR_NAV, hub, f"{PREFIX_FRAME}_items")


def name_sidebar_footer_button(purpose: str) -> str:
    """Name for a footer button in sidebar (Easy menu, Key, Help)."""
    return build_name(WINDOW_NAME, REGION_SIDEBAR, SIDEBAR_FOOTER, f"{PREFIX_BUTTON}_{purpose}")


def name_page_root(page: str) -> str:
    """Name for the root frame of a page."""
    return build_name(WINDOW_NAME, REGION_CONTENT, page, f"{PREFIX_FRAME}_root")


def name_page_header(page: str) -> str:
    """Name for a page header bar."""
    return build_name(WINDOW_NAME, REGION_CONTENT, page, f"{PREFIX_HEADER}_bar")


def name_page_body(page: str, purpose: str = "body") -> str:
    """Name for a page body/content area (optional purpose, e.g. composer)."""
    suffix = purpose if purpose and purpose != "body" else "body"
    return build_name(WINDOW_NAME, REGION_CONTENT, page, f"{PREFIX_FRAME}_{suffix}")


def name_page_save_bar(page: str) -> str:
    """Name for a page's sticky save bar."""
    return build_name(WINDOW_NAME, REGION_CONTENT, page, f"{PREFIX_BAR}_save")


def name_chat_messages_scroll() -> str:
    """Name for the chat messages scrollable area."""
    return build_name(WINDOW_NAME, REGION_CONTENT, PAGE_CHAT, CHAT_MESSAGES, f"{PREFIX_SCROLL}_list")


def name_chat_message_bubble(msg_id: str, role: str) -> str:
    """Name for a single chat message bubble."""
    return build_name(WINDOW_NAME, REGION_CONTENT, PAGE_CHAT, CHAT_MESSAGES, f"{PREFIX_FRAME}_bubble_{role}_{msg_id}")


def name_chat_composer_input() -> str:
    """Name for the chat composer text input."""
    return build_name(WINDOW_NAME, REGION_CONTENT, PAGE_CHAT, CHAT_COMPOSER, f"{PREFIX_TEXTBOX}_input")


def name_chat_composer_send_btn() -> str:
    """Name for the chat composer send button."""
    return build_name(WINDOW_NAME, REGION_CONTENT, PAGE_CHAT, CHAT_COMPOSER, f"{PREFIX_BUTTON}_send")


def name_chat_composer_attach_btn() -> str:
    """Name for the chat composer attach button."""
    return build_name(WINDOW_NAME, REGION_CONTENT, PAGE_CHAT, CHAT_COMPOSER, f"{PREFIX_BUTTON}_attach")


def name_chat_composer_mic_btn() -> str:
    """Name for the chat composer microphone button."""
    return build_name(WINDOW_NAME, REGION_CONTENT, PAGE_CHAT, CHAT_COMPOSER, f"{PREFIX_BUTTON}_mic")


def name_chat_composer_mode_chip(mode: str = "current") -> str:
    """Name for a mode chip in chat composer (Plan/Action/etc)."""
    return build_name(WINDOW_NAME, REGION_CONTENT, PAGE_CHAT, CHAT_COMPOSER, f"{PREFIX_BUTTON}_chip_{mode or 'current'}")


def name_chat_toolbar_button(purpose: str) -> str:
    """Name for a button in chat toolbar (New, Branch, Pin, Export, Clear, Image)."""
    return build_name(WINDOW_NAME, REGION_CONTENT, PAGE_CHAT, CHAT_TOOLBAR, f"{PREFIX_BUTTON}_{purpose}")


def name_chat_toolbar_provider_menu() -> str:
    """Name for the provider OptionMenu on the chat toolbar."""
    return build_name(WINDOW_NAME, REGION_CONTENT, PAGE_CHAT, CHAT_TOOLBAR, f"{PREFIX_MENU}_provider")


def name_chat_toolbar_model_menu() -> str:
    """Name for the model OptionMenu on the chat toolbar."""
    return build_name(WINDOW_NAME, REGION_CONTENT, PAGE_CHAT, CHAT_TOOLBAR, f"{PREFIX_MENU}_model")


def name_chat_toolbar_model_search() -> str:
    """Name for the model-search entry on the chat toolbar."""
    return build_name(WINDOW_NAME, REGION_CONTENT, PAGE_CHAT, CHAT_TOOLBAR, f"{PREFIX_ENTRY}_model_search")


def name_chat_sidebar_panel(panel: str) -> str:
    """Name for a panel in chat right sidebar (Context, Tools, Memory, etc)."""
    return build_name(WINDOW_NAME, REGION_CONTENT, PAGE_CHAT, CHAT_SIDEBAR, f"{PREFIX_PANEL}_{panel}")


def name_page_sidebar(page: str, purpose: str) -> str:
    """Name for a sidebar/rail on a page (e.g., chat history rail)."""
    return build_name(WINDOW_NAME, REGION_CONTENT, page, "sidebar", f"{PREFIX_PANEL}_{purpose}")


def name_chat_sidebar_button(purpose: str) -> str:
    """Name for a button in chat sidebar/history rail (new_chat, search, move, delete, etc)."""
    return build_name(WINDOW_NAME, REGION_CONTENT, PAGE_CHAT, CHAT_SIDEBAR, f"{PREFIX_BUTTON}_{purpose}")


def name_chat_topbar_title() -> str:
    """Name for the chat topbar title label."""
    return build_name(WINDOW_NAME, REGION_CONTENT, PAGE_CHAT, "topbar", f"{PREFIX_LABEL}_title")


def name_chat_topbar_mode_chip() -> str:
    """Name for the mode chip in chat topbar (Plan/Action)."""
    return build_name(WINDOW_NAME, REGION_CONTENT, PAGE_CHAT, "topbar", f"{PREFIX_BUTTON}_chip_mode")


def name_chat_topbar_tasks_chip() -> str:
    """Name for the tasks chip in chat topbar."""
    return build_name(WINDOW_NAME, REGION_CONTENT, PAGE_CHAT, "topbar", f"{PREFIX_BUTTON}_chip_tasks")


def name_chat_topbar_risk_chip() -> str:
    """Name for the risk chip in chat topbar."""
    return build_name(WINDOW_NAME, REGION_CONTENT, PAGE_CHAT, "topbar", f"{PREFIX_BUTTON}_chip_risk")


def name_chat_topbar_caps_chip() -> str:
    """Name for the capabilities chip in chat topbar."""
    return build_name(WINDOW_NAME, REGION_CONTENT, PAGE_CHAT, "topbar", f"{PREFIX_BUTTON}_chip_caps")


def name_chat_sidebar_search() -> str:
    """Name for the search entry in chat sidebar/history rail."""
    return build_name(WINDOW_NAME, REGION_CONTENT, PAGE_CHAT, CHAT_SIDEBAR, f"{PREFIX_ENTRY}_search")


def name_status_bar_label(purpose: str) -> str:
    """Name for a label in the status bar."""
    return build_name(WINDOW_NAME, REGION_STATUS_BAR, f"{PREFIX_LABEL}_{purpose}")


def name_system_monitor_metric(metric: str) -> str:
    """Name for a metric in the system monitor bar."""
    return build_name(WINDOW_NAME, REGION_SYSTEM_MONITOR, f"{PREFIX_LABEL}_{metric}")


def name_dialog(dialog_id: str) -> str:
    """Name for a dialog/toplevel window."""
    return build_name(WINDOW_NAME, REGION_COMMAND_PALETTE, f"{PREFIX_DIALOG}_{dialog_id}")


def name_component(parent_name: str, comp_type: str, purpose: str) -> str:
    """Generic component naming: parent.type.purpose"""
    return build_name(parent_name, f"{comp_type}_{purpose}")

# Page names (match NAV_ITEMS in app_window.py)
PAGE_HOME = "home"
PAGE_HELP = "help"
PAGE_CHAT = "chat"
PAGE_TEAM = "team"
PAGE_MODELS = "models"
PAGE_MONITOR = "monitor"
PAGE_CHATS = "chats"
PAGE_TRACK = "track"
PAGE_WORK = "work"
PAGE_APPROVALS = "approvals"
PAGE_PATCHES = "patches"
# =============================================================================
# Widget Wrapper for Automatic Naming
# =============================================================================

class NamedWidget:
    """Mixin to add automatic naming to CustomTkinter widgets."""
    
    def __init_named__(self, name: str, *args, **kwargs):
        """Initialize with automatic name setting."""
        # This is called by subclasses after super().__init__()
        set_widget_name(self, name)
    
    @property
    def widget_name(self) -> Optional[str]:
        return get_widget_name(self)


def create_named_button(parent: Any, name: str, **kwargs) -> ctk.CTkButton:
    """Create a CTkButton with a logical name."""
    btn = ctk.CTkButton(parent, **kwargs)
    set_widget_name(btn, name)
    return btn


def create_named_label(parent: Any, name: str, **kwargs) -> ctk.CTkLabel:
    """Create a CTkLabel with a logical name."""
    lbl = ctk.CTkLabel(parent, **kwargs)
    set_widget_name(lbl, name)
    return lbl


def create_named_frame(parent: Any, name: str, **kwargs) -> ctk.CTkFrame:
    """Create a CTkFrame with a logical name."""
    frm = ctk.CTkFrame(parent, **kwargs)
    set_widget_name(frm, name)
    return frm


def create_named_scrollable_frame(parent: Any, name: str, **kwargs) -> ctk.CTkScrollableFrame:
    """Create a CTkScrollableFrame with a logical name."""
    scr = ctk.CTkScrollableFrame(parent, **kwargs)
    set_widget_name(scr, name)
    return scr


def create_named_textbox(parent: Any, name: str, **kwargs) -> ctk.CTkTextbox:
    """Create a CTkTextbox with a logical name."""
    txt = ctk.CTkTextbox(parent, **kwargs)
    set_widget_name(txt, name)
    return txt


def create_named_entry(parent: Any, name: str, **kwargs) -> ctk.CTkEntry:
    """Create a CTkEntry with a logical name."""
    ent = ctk.CTkEntry(parent, **kwargs)
    set_widget_name(ent, name)
    return ent


def create_named_toplevel(parent: Any, name: str, **kwargs) -> ctk.CTkToplevel:
    """Create a CTkToplevel with a logical name."""
    dlg = ctk.CTkToplevel(parent, **kwargs)
    set_widget_name(dlg, name)
    return dlg
PAGE_KNOWLEDGE = "knowledge"
PAGE_SCHEDULE = "schedule"
PAGE_ORG_CHART = "org_chart"
PAGE_MEMORY = "memory"
PAGE_PROJECTS = "projects"
PAGE_COMPANY = "company"
PAGE_CEO = "ceo"
PAGE_AGENTS = "agents"
PAGE_TASKS = "tasks"
PAGE_RUNS = "runs"
PAGE_USAGE = "usage"
PAGE_SETTINGS = "settings"
PAGE_ABOUT = "about"

# Chat page sub-regions
CHAT_MESSAGES = "messages"
CHAT_COMPOSER = "composer"
CHAT_SIDEBAR = "sidebar"
CHAT_TOOLBAR = "toolbar"
CHAT_STATUS = "status"

# Component type prefixes
PREFIX_BUTTON = "btn"
PREFIX_LABEL = "lbl"
PREFIX_FRAME = "frm"
PREFIX_SCROLL = "scr"
PREFIX_TEXTBOX = "txt"
PREFIX_ENTRY = "ent"
PREFIX_PANEL = "pnl"
PREFIX_HEADER = "hdr"
PREFIX_FOOTER = "ftr"
PREFIX_BAR = "bar"
PREFIX_MENU = "mnu"
PREFIX_TAB = "tab"
PREFIX_CANVAS = "cvs"
PREFIX_IMAGE = "img"
# =============================================================================
# Registry for Global Widget Access
# =============================================================================

class WidgetRegistry:
    """Global registry for named widgets to enable easy lookup."""
    
    _instance: Optional["WidgetRegistry"] = None
    _widgets: dict[str, Any] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def register(self, name: str, widget: Any) -> None:
        """Register a widget by name."""
        self._widgets[name] = widget
        set_widget_name(widget, name)
    
    def get(self, name: str) -> Optional[Any]:
        """Get a widget by name."""
        return self._widgets.get(name)
    
    def find(self, prefix: str) -> list[Any]:
        """Find all widgets with name starting with prefix."""
        return [w for n, w in self._widgets.items() if n.startswith(prefix)]
    
    def unregister(self, name: str) -> None:
        """Unregister a widget."""
        self._widgets.pop(name, None)
    
    def clear(self) -> None:
        """Clear all registered widgets."""
        self._widgets.clear()
    
    def all_names(self) -> list[str]:
        """Get all registered widget names."""
        return list(self._widgets.keys())


# Global registry instance
widget_registry = WidgetRegistry()


# =============================================================================
# Decorator for Auto-Registering Page Build Methods
# =============================================================================

def register_page_widgets(page_name: str):
    """Decorator to auto-register widgets created in a page build method."""
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            result = func(self, *args, **kwargs)
            # The page build method should call register_widget() for key components
            return result
        return wrapper
    return decorator


def register_widget(name: str, widget: Any) -> Any:
    """Register a widget in the global registry and return it."""
    widget_registry.register(name, widget)
    return widget


# =============================================================================
# Export all public names
# =============================================================================

__all__ = [
    # Constants
    "WINDOW_NAME",
    "REGION_SIDEBAR", "REGION_CONTENT", "REGION_STATUS_BAR", 
    "REGION_SYSTEM_MONITOR", "REGION_COMMAND_PALETTE", "REGION_SHORTCUTS_HELP",
    "SIDEBAR_NAV", "SIDEBAR_FOOTER",
    "HUB_PRIMARY", "HUB_WORKSPACE", "HUB_MORE", "HUB_SETTINGS",
    # Page names
    "PAGE_HOME", "PAGE_HELP", "PAGE_CHAT", "PAGE_TEAM", "PAGE_MODELS",
    "PAGE_MONITOR", "PAGE_CHATS", "PAGE_TRACK", "PAGE_WORK",
    "PAGE_APPROVALS", "PAGE_PATCHES", "PAGE_KNOWLEDGE", "PAGE_SCHEDULE",
    "PAGE_ORG_CHART", "PAGE_MEMORY", "PAGE_PROJECTS", "PAGE_COMPANY",
    "PAGE_CEO", "PAGE_AGENTS", "PAGE_TASKS", "PAGE_RUNS", "PAGE_USAGE",
    "PAGE_SETTINGS", "PAGE_ABOUT",
    # Chat regions
    "CHAT_MESSAGES", "CHAT_COMPOSER", "CHAT_SIDEBAR", "CHAT_TOOLBAR", "CHAT_STATUS",
    # Prefixes
    "PREFIX_BUTTON", "PREFIX_LABEL", "PREFIX_FRAME", "PREFIX_SCROLL",
    "PREFIX_TEXTBOX", "PREFIX_ENTRY", "PREFIX_PANEL", "PREFIX_HEADER",
    "PREFIX_FOOTER", "PREFIX_BAR", "PREFIX_MENU", "PREFIX_TAB",
    "PREFIX_CANVAS", "PREFIX_IMAGE", "PREFIX_SEPARATOR", "PREFIX_DIALOG",
    "PREFIX_POPUP", "PREFIX_SPLITTER", "PREFIX_GROUP",
    # Functions
    "build_name", "set_widget_name", "get_widget_name",
    "find_widget_by_name", "find_widgets_by_prefix",
    "name_sidebar_nav_button", "name_sidebar_hub_header", "name_sidebar_hub_items_frame",
    "name_sidebar_footer_button", "name_page_root", "name_page_header",
    "name_page_body", "name_page_save_bar",
    "name_chat_messages_scroll", "name_chat_message_bubble",
    "name_chat_composer_input", "name_chat_composer_send_btn",
    "name_chat_composer_attach_btn", "name_chat_composer_mic_btn",
    "name_chat_composer_mode_chip", "name_chat_toolbar_button",
    "name_chat_toolbar_provider_menu", "name_chat_toolbar_model_menu",
    "name_chat_toolbar_model_search",
    "name_chat_sidebar_panel", "name_page_sidebar", "name_chat_sidebar_button",
    "name_chat_topbar_title", "name_chat_topbar_mode_chip",
    "name_chat_topbar_tasks_chip", "name_chat_topbar_risk_chip",
    "name_chat_topbar_caps_chip", "name_chat_sidebar_search",
    "name_status_bar_label", "name_system_monitor_metric", "name_dialog", "name_component",
    # Creator functions
    "create_named_button", "create_named_label", "create_named_frame",
    "create_named_scrollable_frame", "create_named_textbox",
    "create_named_entry", "create_named_toplevel",
    # Registry
    "WidgetRegistry", "widget_registry", "register_widget",
]
PREFIX_SEPARATOR = "sep"
PREFIX_DIALOG = "dlg"
PREFIX_POPUP = "pop"
PREFIX_SPLITTER = "spl"
PREFIX_GROUP = "grp"