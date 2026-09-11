"""Reusable chat-style message boxes: select, copy, click links, expand, maximize.

Used by Team feed (and available for other pages). Designed for layman UX —
plain CTkLabel text cannot be selected or clicked; this uses read-only Textboxes.
"""

from __future__ import annotations

import re
import webbrowser
from typing import Any, Callable

import customtkinter as ctk

from app.ui.themes import UI as _UI
from app.ui.themes import style_chrome_button

_HC_MUTED = _UI["muted"]
_HC_LABEL = _UI["label"]

# Collapsed preview ~ this many characters (then Expand)
_COLLAPSE_CHARS = 900
# http(s) + file:// (RAG citations) — Task #7 clickable sources
_URL_RE = re.compile(
    r"(?:https?://|file:///)[^\s<>\"'\]\)]+",
    re.IGNORECASE,
)


def extract_urls(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for m in _URL_RE.finditer(text or ""):
        url = m.group(0).rstrip(".,;:)]}>\"'")
        if len(url) >= 8 and url not in seen:
            seen.add(url)
            found.append(url)
    return found


def open_url_or_path(url: str) -> bool:
    """Open http(s) in browser; file:// / local paths with OS handler."""
    u = (url or "").strip()
    if not u:
        return False
    try:
        if u.lower().startswith("file:"):
            from pathlib import Path
            from urllib.parse import unquote, urlparse
            import os
            import sys

            parsed = urlparse(u)
            path = unquote(parsed.path or "")
            # Windows: /C:/Users/... → C:/Users/...
            if sys.platform.startswith("win") and re.match(r"^/[A-Za-z]:", path):
                path = path[1:]
            path = path.replace("/", "\\") if sys.platform.startswith("win") else path
            p = Path(path)
            if p.exists():
                os.startfile(str(p))  # type: ignore[attr-defined]
                return True
            # fallback webbrowser
            webbrowser.open(u)
            return True
        webbrowser.open(u)
        return True
    except Exception:  # noqa: BLE001
        try:
            webbrowser.open(u)
            return True
        except Exception:  # noqa: BLE001
            return False


def estimate_text_height(text: str, wrap: int = 560, font_size: int = 14) -> int:
    cpl = max(28, int(wrap / max(5.5, font_size * 0.52)))
    lines = 0
    for ln in (text or "").split("\n"):
        lines += max(1, (len(ln) + cpl - 1) // cpl) if ln else 1
    return min(720, max(48, 14 + lines * (font_size + 6)))


def copy_text(app: Any, text: str) -> None:
    try:
        root = app if hasattr(app, "clipboard_clear") else None
        if root is None:
            return
        root.clipboard_clear()
        root.clipboard_append(text or "")
        if hasattr(app, "set_status"):
            app.set_status("Copied to clipboard", toast=True)
    except Exception:  # noqa: BLE001
        pass


def linkify_and_lock_textbox(
    tb: ctk.CTkTextbox,
    *,
    linkify: bool = True,
    on_open: Callable[[str], None] | None = None,
) -> None:
    """Read-only textbox + optional blue clickable http(s) links."""
    try:
        tw = tb._textbox  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        return

    if linkify:
        try:
            tw.tag_configure("hyper", foreground="#2563eb", underline=True)
        except Exception:  # noqa: BLE001
            try:
                tw.tag_configure("hyper", foreground="blue", underline=True)
            except Exception:  # noqa: BLE001
                pass

        content = tw.get("1.0", "end-1c")
        url_map: dict[str, str] = {}
        n = 0
        for m in _URL_RE.finditer(content):
            raw = m.group(0)
            url = raw.rstrip(".,;:)]}>\"'")
            if len(url) < 8:
                continue
            tag = f"hyper_{n}"
            n += 1
            start = f"1.0+{m.start()}c"
            end = f"1.0+{m.start() + len(url)}c"
            try:
                tw.tag_add(tag, start, end)
                tw.tag_add("hyper", start, end)
                url_map[tag] = url
            except Exception:  # noqa: BLE001
                continue

        def on_click(event: Any) -> str | None:
            try:
                idx = tw.index(f"@{event.x},{event.y}")
                for tag in tw.tag_names(idx):
                    if tag in url_map:
                        u = url_map[tag]
                        open_url_or_path(u)
                        if on_open:
                            on_open(u)
                        return "break"
            except Exception:  # noqa: BLE001
                pass
            return None

        def on_motion(event: Any) -> None:
            try:
                idx = tw.index(f"@{event.x},{event.y}")
                if any(t in url_map for t in tw.tag_names(idx)):
                    tw.configure(cursor="hand2")
                else:
                    tw.configure(cursor="xterm")
            except Exception:  # noqa: BLE001
                pass

        try:
            tw.tag_bind("hyper", "<Button-1>", on_click)
            tw.bind("<Motion>", on_motion, add="+")
        except Exception:  # noqa: BLE001
            pass

    def block_edit(event: Any) -> str | None:
        if event.state & 0x4:  # Control
            if event.keysym.lower() in ("c", "a", "insert"):
                return None
        if event.keysym in (
            "Left",
            "Right",
            "Up",
            "Down",
            "Home",
            "End",
            "Prior",
            "Next",
            "Shift_L",
            "Shift_R",
            "Control_L",
            "Control_R",
            "Alt_L",
            "Alt_R",
        ):
            return None
        return "break"

    try:
        tw.bind("<Key>", block_edit)
        tw.bind("<<Paste>>", lambda _e: "break")
        tw.bind("<<Cut>>", lambda _e: "break")
        tw.bind("<Control-a>", lambda e: (tw.tag_add("sel", "1.0", "end-1c"), "break"))
        tw.bind("<Control-A>", lambda e: (tw.tag_add("sel", "1.0", "end-1c"), "break"))
    except Exception:  # noqa: BLE001
        pass


def chat_wrap_width(app: Any | None = None, default: int = 640) -> int:
    """Wrap width that grows when the user widens the window."""
    try:
        if app is not None and hasattr(app, "winfo_width"):
            w = int(app.winfo_width() or 0)
            if w > 200:
                # Leave room for sidebar + side panels; chat gets the rest
                return max(360, min(1100, w - 420))
    except Exception:  # noqa: BLE001
        pass
    return default


def make_selectable_box(
    parent: Any,
    text: str,
    *,
    text_color: Any = None,
    fg_color: Any = "transparent",
    wrap: int = 560,
    font_size: int = 14,
    max_height: int = 360,
    linkify: bool = True,
    on_open: Callable[[str], None] | None = None,
    fill: bool = True,
) -> ctk.CTkTextbox:
    h = estimate_text_height(text or "", wrap, font_size)
    h = min(max_height, max(56, h))
    tb = ctk.CTkTextbox(
        parent,
        height=h,
        font=ctk.CTkFont(size=font_size),
        text_color=text_color or _HC_LABEL,
        fg_color=fg_color,
        border_width=0,
        wrap="word",
        activate_scrollbars=h >= max_height - 20,
        corner_radius=8,
    )
    tb.pack(fill="both" if fill else "x", expand=fill, padx=4, pady=2)
    tb.insert("1.0", text or "")
    linkify_and_lock_textbox(tb, linkify=linkify, on_open=on_open)
    return tb


def open_maximized_message(
    app: Any,
    *,
    title: str,
    body: str,
    subtitle: str = "",
) -> None:
    """Large resizable popup: select, copy, click links, drag edges to resize."""
    win = ctk.CTkToplevel(app)
    win.title(title[:80] or "Message")
    win.geometry("900x700")
    win.minsize(480, 360)
    try:
        win.resizable(True, True)
        win.wm_resizable(True, True)
        win.transient(app)
        # Start large but NOT forced fullscreen — user can drag edges freely
        try:
            win.state("zoomed")
        except Exception:  # noqa: BLE001
            pass
    except Exception:  # noqa: BLE001
        pass

    head = ctk.CTkFrame(win, fg_color="transparent")
    head.pack(fill="x", padx=16, pady=(14, 4))
    ctk.CTkLabel(
        head,
        text=title,
        font=ctk.CTkFont(size=18, weight="bold"),
        text_color=_HC_LABEL,
        anchor="w",
    ).pack(anchor="w")
    if subtitle:
        ctk.CTkLabel(head, text=subtitle, text_color=_HC_MUTED, anchor="w").pack(anchor="w")

    tip = ctk.CTkLabel(
        win,
        text="Select text · Ctrl+C to copy · blue links open in browser · Close when done",
        text_color=_HC_MUTED,
        font=ctk.CTkFont(size=12),
    )
    tip.pack(anchor="w", padx=16, pady=(0, 6))

    box = ctk.CTkTextbox(
        win,
        wrap="word",
        font=ctk.CTkFont(size=15),
        text_color=_HC_LABEL,
    )
    box.pack(fill="both", expand=True, padx=16, pady=8)
    box.insert("1.0", body or "")
    def _opened(u: str) -> None:
        if hasattr(app, "set_status"):
            try:
                app.set_status(f"Opened: {u[:50]}", toast=True)
            except Exception:  # noqa: BLE001
                pass

    linkify_and_lock_textbox(box, linkify=True, on_open=_opened)

    bar = ctk.CTkFrame(win, fg_color="transparent")
    bar.pack(fill="x", padx=16, pady=12)
    urls = extract_urls(body or "")

    def do_copy() -> None:
        copy_text(app, body or "")

    def copy_links() -> None:
        if not urls:
            if hasattr(app, "set_status"):
                app.set_status("No links in this message", toast=True)
            return
        copy_text(app, "\n".join(urls))

    def open_all_links() -> None:
        for u in urls[:25]:
            try:
                open_url_or_path(u)
            except Exception:  # noqa: BLE001
                pass
        if hasattr(app, "set_status"):
            app.set_status(f"Opened {min(len(urls), 25)} link(s)", toast=True)

    ctk.CTkButton(bar, text="📋 Copy all", width=110, command=do_copy, **style_chrome_button(primary=True)).pack(
        side="left", padx=4
    )
    if urls:
        ctk.CTkButton(bar, text=f"🔗 Copy {len(urls)} link(s)", width=140, command=copy_links, **style_chrome_button()).pack(
            side="left", padx=4
        )
        ctk.CTkButton(bar, text="Open links", width=100, command=open_all_links, **style_chrome_button()).pack(
            side="left", padx=4
        )
    ctk.CTkButton(bar, text="Close", width=90, command=win.destroy, **style_chrome_button()).pack(
        side="right", padx=4
    )


def render_chat_message_card(
    parent: Any,
    *,
    app: Any,
    name: str,
    role: str = "",
    body: str = "",
    at: str = "",
    avatar_color: str | tuple = "#6366f1",
    kind: str = "agent",  # agent | ceo | user | system | final
    default_expanded: bool | None = None,
) -> ctk.CTkFrame:
    """
    Full chat-style card:
      avatar · name · time
      selectable body (links clickable)
      Expand/Collapse · Maximize · Copy · Open links
    """
    body = body or ""
    long_msg = len(body) > _COLLAPSE_CHARS
    # Final answers default open; system short; long agent msgs collapsed
    if default_expanded is None:
        if kind in ("final", "user"):
            expanded0 = True
        elif kind == "system":
            expanded0 = len(body) < 400
        else:
            expanded0 = not long_msg
    else:
        expanded0 = default_expanded

    # Bubble colors by kind
    if kind == "user":
        card_bg = ("#e8eefc", "#243044")
    elif kind == "final":
        card_bg = ("#dcfce7", "#14532d")
    elif kind == "system":
        card_bg = ("#f4f4f5", "#1c1f26")
    elif kind == "ceo":
        card_bg = ("#faf5ff", "#2e1065")
    else:
        card_bg = ("#f8fafc", "#12141a")

    card = ctk.CTkFrame(parent, fg_color=card_bg, corner_radius=12)
    card.pack(fill="x", pady=6, padx=4)

    top = ctk.CTkFrame(card, fg_color="transparent")
    top.pack(fill="x", padx=10, pady=(10, 4))

    av = ctk.CTkLabel(
        top,
        text=(name[:1] or "?").upper(),
        width=36,
        height=36,
        corner_radius=18,
        fg_color=avatar_color,
        text_color=("#fff", "#fff"),
        font=ctk.CTkFont(size=14, weight="bold"),
    )
    av.pack(side="left", padx=(0, 10))

    meta = ctk.CTkFrame(top, fg_color="transparent")
    meta.pack(side="left", fill="x", expand=True)
    title_bits = name
    if role:
        title_bits += f"  ·  {role}"
    if at:
        title_bits += f"  ·  {at}"
    if kind == "final":
        title_bits = "✓ Finished answer  ·  " + title_bits
    ctk.CTkLabel(
        meta,
        text=title_bits,
        text_color=_HC_MUTED if kind != "final" else ("#166534", "#bbf7d0"),
        font=ctk.CTkFont(size=12, weight="bold"),
        anchor="w",
    ).pack(anchor="w")

    # Action buttons (always visible — what users need)
    actions = ctk.CTkFrame(top, fg_color="transparent")
    actions.pack(side="right")

    state = {"expanded": expanded0, "body_host": None}

    body_host = ctk.CTkFrame(card, fg_color="transparent")
    body_host.pack(fill="x", padx=10, pady=(0, 4))
    state["body_host"] = body_host

    def paint_body() -> None:
        for w in body_host.winfo_children():
            w.destroy()
        show = body
        if long_msg and not state["expanded"]:
            show = body[:_COLLAPSE_CHARS].rstrip() + "\n\n… (message shortened — press Expand)"
        max_h = 640 if state["expanded"] else 240
        wrap = chat_wrap_width(app, 640)
        make_selectable_box(
            body_host,
            show,
            text_color=_HC_LABEL,
            fg_color="transparent",
            wrap=wrap,
            font_size=14,
            max_height=max_h,
            linkify=True,
            on_open=lambda u: (
                hasattr(app, "set_status")
                and app.set_status(f"Opened link: {u[:50]}", toast=True)
            ),
            fill=True,
        )
        if long_msg and not state["expanded"]:
            ctk.CTkLabel(
                body_host,
                text=f"Full message: {len(body):,} characters · {len(body.splitlines())} lines",
                text_color=_HC_MUTED,
                font=ctk.CTkFont(size=11),
            ).pack(anchor="w", padx=6, pady=(0, 4))

    def toggle_expand() -> None:
        state["expanded"] = not state["expanded"]
        try:
            expand_btn.configure(text="▲ Smaller" if state["expanded"] else "▼ Expand")
        except Exception:  # noqa: BLE001
            pass
        paint_body()

    def do_maximize() -> None:
        open_maximized_message(
            app,
            title=name or "Message",
            body=body,
            subtitle=f"{role}  ·  {at}".strip(" ·"),
        )

    def do_copy() -> None:
        copy_text(app, body)

    urls = extract_urls(body)

    def open_links() -> None:
        for u in urls[:20]:
            try:
                open_url_or_path(u)
            except Exception:  # noqa: BLE001
                pass
        if hasattr(app, "set_status"):
            app.set_status(f"Opened {min(len(urls), 20)} link(s)", toast=True)

    def copy_links() -> None:
        if urls:
            copy_text(app, "\n".join(urls))
        elif hasattr(app, "set_status"):
            app.set_status("No links in this message", toast=True)

    # Build action buttons
    if long_msg:
        expand_btn = ctk.CTkButton(
            actions,
            text="▲ Smaller" if expanded0 else "▼ Expand",
            width=90,
            height=26,
            command=toggle_expand,
            **style_chrome_button(),
        )
        expand_btn.pack(side="left", padx=2)
    else:
        expand_btn = None  # type: ignore

    ctk.CTkButton(
        actions,
        text="⛶ Big",
        width=60,
        height=26,
        command=do_maximize,
        **style_chrome_button(),
    ).pack(side="left", padx=2)
    ctk.CTkButton(
        actions,
        text="📋 Copy",
        width=70,
        height=26,
        command=do_copy,
        **style_chrome_button(primary=True),
    ).pack(side="left", padx=2)
    if urls:
        ctk.CTkButton(
            actions,
            text=f"🔗 {len(urls)}",
            width=56,
            height=26,
            command=open_links,
            **style_chrome_button(),
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            actions,
            text="Copy links",
            width=80,
            height=26,
            command=copy_links,
            **style_chrome_button(),
        ).pack(side="left", padx=2)

    paint_body()

    # Footer hint for laymen
    foot = ctk.CTkLabel(
        card,
        text="Tip: drag to select text · Ctrl+C copy · click blue links · ⛶ Big = full window",
        text_color=_HC_MUTED,
        font=ctk.CTkFont(size=10),
        anchor="w",
    )
    foot.pack(fill="x", padx=14, pady=(0, 8))

    return card


def render_final_answer_card(parent: Any, *, app: Any, text: str, title: str = "✓ Finished answer") -> None:
    render_chat_message_card(
        parent,
        app=app,
        name=title or "✓ Finished answer",
        role="CEO",
        body=text or "",
        at="",
        avatar_color="#22c55e",
        kind="final",
        default_expanded=True,
    )
