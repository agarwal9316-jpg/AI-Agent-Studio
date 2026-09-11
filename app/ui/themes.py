"""Multi-theme colour UI presets — prioritise readable text contrast."""

from __future__ import annotations

from typing import Any

# name -> appearance mode + built-in CTK color theme
# CTK built-ins: "blue", "green", "dark-blue"
THEMES: dict[str, dict[str, Any]] = {
    "Readable Dark": {
        "mode": "Dark",
        "color": "blue",
        "desc": "High-contrast dark — light text on deep background (default)",
    },
    "Readable Light": {
        "mode": "Light",
        "color": "blue",
        "desc": "High-contrast light — dark text on white",
    },
    "Dark Blue": {"mode": "Dark", "color": "blue", "desc": "Dark with blue accents"},
    "Dark Green": {"mode": "Dark", "color": "green", "desc": "Dark with green accents"},
    "Dark Purple": {"mode": "Dark", "color": "dark-blue", "desc": "Deep purple-blue dark"},
    "Midnight": {"mode": "Dark", "color": "dark-blue", "desc": "Near-black with cool accents"},
    "Ocean": {"mode": "Dark", "color": "blue", "desc": "Ocean blue dark UI"},
    "Forest": {"mode": "Dark", "color": "green", "desc": "Forest green dark UI"},
    "Light Blue": {"mode": "Light", "color": "blue", "desc": "Bright light blue theme"},
    "Light Green": {"mode": "Light", "color": "green", "desc": "Soft light green theme"},
    "Daylight": {"mode": "Light", "color": "blue", "desc": "Clean daylight light UI"},
    "Slate": {"mode": "Dark", "color": "dark-blue", "desc": "Neutral slate dark"},
    "Mint": {"mode": "Light", "color": "green", "desc": "Mint light accents"},
    "System": {"mode": "System", "color": "blue", "desc": "Follow OS light/dark"},
}


def theme_names() -> list[str]:
    return list(THEMES.keys())


def theme_description(name: str) -> str:
    t = THEMES.get(name) or {}
    return str(t.get("desc") or "")


def apply_theme(name: str) -> dict[str, str]:
    import customtkinter as ctk

    t = THEMES.get(name) or THEMES["Readable Dark"]
    mode = t.get("mode") or "Dark"
    ctk.set_appearance_mode(mode)
    color = t.get("color") or "blue"
    if color not in ("blue", "green", "dark-blue"):
        color = "blue"
    ctk.set_default_color_theme(color)
    return {"name": name, "mode": mode, "color": color}


# High-contrast palette used by chat (light_tuple, dark_tuple) where CTK accepts (light, dark)
# Prefer near-black on light surfaces / near-white on dark surfaces.
# All chrome text must meet ~WCAG AA on its bar background (never inherit low-contrast CTK defaults).
UI = {
    "sidebar_bg": ("#eef1f6", "#0e1016"),
    "sidebar_text": ("#0a0f1a", "#f9fafb"),
    # Muted still ≥ ~4.5:1 on sidebar/top surfaces (never pure gray)
    "sidebar_muted": ("#1f2937", "#e5e7eb"),
    "sidebar_hover": ("#dbe3f0", "#252a35"),
    "sidebar_active": ("#c7d7f5", "#1e3a5f"),
    "sidebar_active_text": ("#0b1f4a", "#f0f9ff"),
    # Left accent on active nav (Grok-like focus)
    "sidebar_active_accent": ("#2563eb", "#60a5fa"),
    # Chat top rows (tabs + provider + mode bars)
    "top_bg": ("#f3f4f6", "#121212"),
    "top_border": ("#d1d5db", "#2a2a2a"),
    "label": ("#0a0f1a", "#f9fafb"),
    # Secondary text — strong enough on light (#f*) and dark (#16*) surfaces
    "muted": ("#111827", "#e5e7eb"),
    # Grok.com / ChatGPT 2026 canvas: near-white light, true near-black dark
    "chat_bg": ("#f7f7f8", "#0a0a0a"),
    # In-chat history rail (ChatGPT-style left panel + Grok dark)
    "chat_rail_bg": ("#f0f0f0", "#0c0c0c"),
    "chat_rail_border": ("#e5e5e5", "#1a1a1a"),
    "chat_rail_active": ("#e8e8e8", "#1c1c1c"),
    "chat_rail_active_text": ("#0d0d0d", "#fafafa"),
    # Composer pill (calm default → tools behind +)
    "composer_bg": ("#ffffff", "#1a1a1a"),
    "composer_input": ("#ffffff", "#1a1a1a"),
    "composer_text": ("#0d0d0d", "#ececec"),
    "composer_border": ("#e5e5e5", "#2a2a2a"),
    "composer_handle": ("#d4d4d8", "#3f3f46"),
    "composer_handle_hover": ("#a1a1aa", "#52525b"),
    "user_bubble": ("#f4f4f5", "#2f2f2f"),
    "assistant_surface": ("transparent", "transparent"),
    # Buttons / menus sitting on top_bg — forced contrast (not theme default)
    "btn_bg": ("#e5e7eb", "#2a3140"),
    "btn_hover": ("#d1d5db", "#3a4356"),
    "btn_text": ("#0a0f1a", "#f9fafb"),
    "btn_primary_bg": ("#2563eb", "#3b82f6"),
    "btn_primary_hover": ("#1d4ed8", "#60a5fa"),
    "btn_primary_text": ("#ffffff", "#0a0f1a"),
    "btn_ghost_bg": ("transparent", "transparent"),
    "btn_ghost_hover": ("#e5e7eb", "#2a3140"),
    "btn_ghost_text": ("#0a0f1a", "#f9fafb"),
    "tab_active_bg": ("#bfdbfe", "#1e3a5f"),
    "tab_active_text": ("#0a1628", "#f0f9ff"),
    "tab_idle_bg": ("#e5e7eb", "#252b38"),
    "tab_idle_text": ("#0a0f1a", "#f3f4f6"),
    "menu_fg": ("#ffffff", "#1e2430"),
    "menu_btn": ("#dbeafe", "#334155"),
    "menu_btn_hover": ("#bfdbfe", "#475569"),
    "menu_text": ("#0a0f1a", "#f8fafc"),
    "menu_drop_fg": ("#ffffff", "#1e2430"),
    "menu_drop_hover": ("#e0e7ff", "#334155"),
    "menu_drop_text": ("#0a0f1a", "#f8fafc"),
    "entry_fg": ("#ffffff", "#0b0d12"),
    "entry_text": ("#0a0f1a", "#f9fafb"),
    "entry_border": ("#6b7280", "#64748b"),
    "entry_placeholder": ("#374151", "#cbd5e1"),
    # Segmented: one text_color for all segments → pick fills that contrast with that text
    "seg_fg": ("#d1d5db", "#1a1f2a"),
    "seg_selected": ("#93c5fd", "#2563eb"),  # light blue / blue (dark text / light text)
    "seg_selected_hover": ("#60a5fa", "#3b82f6"),
    "seg_unselected": ("#e5e7eb", "#2a3140"),
    "seg_unselected_hover": ("#d1d5db", "#3a4356"),
    "seg_text": ("#0a0f1a", "#f9fafb"),
    "switch_text": ("#0a0f1a", "#f3f4f6"),
    "switch_progress": ("#2563eb", "#3b82f6"),
    "switch_button": ("#f9fafb", "#e5e7eb"),
    # App shell / pages — align with SuperGrok canvas
    "content_bg": ("#fdfdfd", "#0a0a0a"),
    "card_bg": ("#ffffff", "#141414"),
    "card_border": ("#e2e8f0", "#27272a"),
    "accent": ("#2563eb", "#60a5fa"),
    "accent_soft": ("#dbeafe", "#1e293b"),
    "success": ("#059669", "#34d399"),
    "warning": ("#d97706", "#fbbf24"),
    "danger": ("#dc2626", "#f87171"),
    "status_bg": ("#e8ecf1", "#0c0c0c"),
    "status_text": ("#0f172a", "#e5e7eb"),
    "brand_bar": ("#2563eb", "#3b82f6"),
    "hub_header_bg": ("#e8ecf1", "#141414"),
    "bubble_shadow": ("#e2e8f0", "#0a0a0a"),
    # Shell chrome radii (visual system)
    "radius_shell": 10,
    "radius_card": 14,
    "radius_pill": 22,
}

# Short icons for sidebar labels (ASCII-safe where possible)
NAV_ICONS: dict[str, str] = {
    "Home": "⌂",
    "Help": "?",
    "Chat": "◉",
    "Team": "⧉",
    "Models": "🧠",
    "Monitor": "📊",
    "Chats": "☰",
    "Track": "◎",
    "Work": "▣",
    "Approvals": "✓",
    "Patches": "✎",
    "Knowledge": "◈",
    "Notes": "✎",
    "Channels": "💬",
    "Automations": "⏰",
    "Schedule": "◷",
    "Org chart": "⎇",
    "Memory": "◉",
    "Projects": "◫",
    "Company": "⌂",
    "CEO": "★",
    "Agents": "♟",
    "Tasks": "☑",
    "Runs": "▶",
    "Usage": "▤",
    "Settings": "⚙",
    "About": "ℹ",
}


def nav_icon(name: str) -> str:
    return NAV_ICONS.get(name, "·")


def style_card() -> dict:
    r = int(UI.get("radius_card") or 14)
    return {
        "fg_color": UI["card_bg"],
        "corner_radius": r,
        "border_width": 1,
        "border_color": UI["card_border"],
    }


def style_pill_frame() -> dict:
    """Rounded surface for composers / chips (Grok-like)."""
    r = int(UI.get("radius_pill") or 22)
    return {
        "fg_color": UI.get("composer_bg", UI["card_bg"]),
        "corner_radius": r,
        "border_width": 1,
        "border_color": UI.get("chat_rail_border", UI["card_border"]),
    }


def style_label(*, muted: bool = False) -> dict:
    """Readable label colors — use instead of text_color='gray'."""
    return {"text_color": UI["muted"] if muted else UI["label"]}


def style_textbox() -> dict:
    """High-contrast textboxes (activity logs, forms)."""
    return {
        "fg_color": UI["entry_fg"],
        "text_color": UI["entry_text"],
        "border_color": UI["entry_border"],
        "border_width": 1,
    }


def style_ghost_button(kwargs: dict | None = None) -> dict:
    """CTkButton kwargs: readable text on top bar (ghost / secondary)."""
    base = {
        "fg_color": UI["btn_bg"],
        "hover_color": UI["btn_hover"],
        "text_color": UI["btn_text"],
        "border_width": 1,
        "border_color": UI["top_border"],
    }
    if kwargs:
        base.update(kwargs)
    return base


def style_option_menu() -> dict:
    return {
        "fg_color": UI["menu_fg"],
        "button_color": UI["menu_btn"],
        "button_hover_color": UI["menu_btn_hover"],
        "text_color": UI["menu_text"],
        "dropdown_fg_color": UI["menu_drop_fg"],
        "dropdown_hover_color": UI["menu_drop_hover"],
        "dropdown_text_color": UI["menu_drop_text"],
    }


def style_entry() -> dict:
    return {
        "fg_color": UI["entry_fg"],
        "text_color": UI["entry_text"],
        "border_color": UI["entry_border"],
        "border_width": 1,
        "placeholder_text_color": UI["entry_placeholder"],
    }


def style_segmented() -> dict:
    return {
        "fg_color": UI["seg_fg"],
        "selected_color": UI["seg_selected"],
        "selected_hover_color": UI["seg_selected_hover"],
        "unselected_color": UI["seg_unselected"],
        "unselected_hover_color": UI["seg_unselected_hover"],
        "text_color": UI["seg_text"],
        "text_color_disabled": UI["muted"],
    }


def style_switch() -> dict:
    return {
        "text_color": UI["switch_text"],
        "progress_color": UI["switch_progress"],
        "button_color": UI["switch_button"],
        "button_hover_color": UI["btn_hover"],
    }


def style_chrome_button(*, primary: bool = False, active: bool = False) -> dict:
    if primary:
        return {
            "fg_color": UI["btn_primary_bg"],
            "hover_color": UI["btn_primary_hover"],
            "text_color": UI["btn_primary_text"],
        }
    if active:
        return {
            "fg_color": UI["tab_active_bg"],
            "hover_color": UI["menu_btn_hover"],
            "text_color": UI["tab_active_text"],
            "border_width": 1,
            "border_color": UI["top_border"],
        }
    return {
        "fg_color": UI["btn_bg"],
        "hover_color": UI["btn_hover"],
        "text_color": UI["btn_text"],
        "border_width": 1,
        "border_color": UI["top_border"],
    }
