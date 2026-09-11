"""Shared page layout: header + scroll body + sticky Save action bar.

Use this for every form/admin page so Save is never scrolled off-screen
and content has a single primary vertical scroll region.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import customtkinter as ctk

from app.ui.themes import UI as _UI
from app.ui.themes import style_chrome_button


@dataclass
class StickySaveBar:
    """Always-visible action bar with primary Save + status text."""

    frame: ctk.CTkFrame
    status_label: ctk.CTkLabel
    save_button: ctk.CTkButton
    dirty: bool = False
    on_save: Callable[[], None] | None = field(default=None, repr=False)

    def set_status(self, text: str, *, kind: str = "muted") -> None:
        colors = {
            "muted": _UI.get("muted", ("#6b7280", "#9ca3af")),
            "ok": _UI.get("success", ("#15803d", "#4ade80")),
            "error": ("#dc2626", "#f87171"),
            "warn": ("#b45309", "#fbbf24"),
        }
        self.status_label.configure(text=text, text_color=colors.get(kind, colors["muted"]))

    def mark_dirty(self, dirty: bool = True) -> None:
        self.dirty = dirty
        if dirty:
            self.set_status("Unsaved changes — click Save", kind="warn")
        else:
            self.set_status("No changes", kind="muted")

    def mark_saved(self, detail: str = "✓ Saved") -> None:
        self.dirty = False
        self.set_status(detail, kind="ok")

    def mark_error(self, msg: str) -> None:
        self.set_status(msg, kind="error")


@dataclass
class FormPageLayout:
    """Two-column (list + form) or single-column form page shell."""

    root: ctk.CTkFrame
    header_parent: ctk.CTkFrame
    body: ctk.CTkFrame
    save_bar: StickySaveBar | None = None
    list_panel: ctk.CTkFrame | None = None
    list_scroll: ctk.CTkScrollableFrame | None = None
    form_scroll: ctk.CTkScrollableFrame | None = None
    form_panel: ctk.CTkFrame | None = None


def make_sticky_save_bar(
    parent: Any,
    *,
    save_label: str = "💾  Save",
    on_save: Callable[[], None] | None = None,
    secondary: list[tuple[str, Callable[[], None], dict[str, Any]]] | None = None,
    hint: str = "Edit fields, then Save",
    row: int | None = None,
    pack: bool = False,
) -> StickySaveBar:
    """
    Build a sticky save bar.

    Prefer grid row placement (parent must grid_rowconfigure appropriately).
    If pack=True, packs at bottom of parent.
    """
    bar = ctk.CTkFrame(
        parent,
        fg_color=_UI.get("top_bg", ("#f3f4f6", "#161a22")),
        corner_radius=10,
        border_width=1,
        border_color=_UI.get("top_border", ("#6b7280", "#4b5563")),
    )
    if pack:
        bar.pack(fill="x", side="bottom", padx=0, pady=(8, 0))
    elif row is not None:
        bar.grid(row=row, column=0, sticky="ew", padx=0, pady=(8, 0))
    else:
        bar.pack(fill="x", padx=0, pady=(8, 0))

    save_btn = ctk.CTkButton(
        bar,
        text=save_label,
        width=140,
        height=36,
        command=on_save,
        **style_chrome_button(primary=True),
    )
    save_btn.pack(side="left", padx=10, pady=10)

    for lab, cmd, kwargs in secondary or []:
        kw = dict(kwargs or {})
        width = int(kw.pop("width", 90))
        height = int(kw.pop("height", 36))
        ctk.CTkButton(bar, text=lab, width=width, height=height, command=cmd, **kw).pack(
            side="left", padx=4, pady=10
        )

    status = ctk.CTkLabel(
        bar,
        text=hint,
        text_color=_UI.get("muted", ("#6b7280", "#9ca3af")),
        font=ctk.CTkFont(size=12),
    )
    status.pack(side="left", padx=12, pady=10)

    return StickySaveBar(frame=bar, status_label=status, save_button=save_btn, on_save=on_save)


def make_list_form_page(
    parent: Any,
    *,
    list_width: int = 260,
) -> FormPageLayout:
    """
    Layout:
      row0: (caller puts header)
      row1: body weight=1 — left list (expand) | right form (scroll + sticky save)

    Returns empty shell; caller attaches header, list items, form fields, save_bar.
    """
    root = ctk.CTkFrame(parent, fg_color="transparent")
    root.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
    root.grid_columnconfigure(0, weight=1)
    root.grid_rowconfigure(1, weight=1)
    if hasattr(parent, "grid_rowconfigure"):
        try:
            parent.grid_rowconfigure(0, weight=1)
            parent.grid_columnconfigure(0, weight=1)
        except Exception:  # noqa: BLE001
            pass

    body = ctk.CTkFrame(root, fg_color="transparent")
    body.grid(row=1, column=0, sticky="nsew")
    body.grid_columnconfigure(1, weight=1)
    body.grid_rowconfigure(0, weight=1)

    list_panel = ctk.CTkFrame(body)
    list_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
    list_panel.grid_rowconfigure(1, weight=1)
    list_panel.grid_columnconfigure(0, weight=1)

    list_scroll = ctk.CTkScrollableFrame(list_panel, width=list_width, fg_color="transparent")
    list_scroll.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)

    # Right: form area with scroll + sticky save
    form_panel = ctk.CTkFrame(body)
    form_panel.grid(row=0, column=1, sticky="nsew")
    form_panel.grid_rowconfigure(0, weight=1)
    form_panel.grid_columnconfigure(0, weight=1)

    form_scroll = ctk.CTkScrollableFrame(form_panel, fg_color="transparent")
    form_scroll.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)

    return FormPageLayout(
        root=root,
        header_parent=root,
        body=body,
        list_panel=list_panel,
        list_scroll=list_scroll,
        form_scroll=form_scroll,
        form_panel=form_panel,
    )


def make_single_scroll_page(parent: Any) -> FormPageLayout:
    """
    Layout:
      row0: header (caller)
      row1: sticky save (caller optional)
      row2: scroll body weight=1
    """
    root = ctk.CTkFrame(parent, fg_color="transparent")
    root.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
    root.grid_columnconfigure(0, weight=1)
    root.grid_rowconfigure(2, weight=1)
    if hasattr(parent, "grid_rowconfigure"):
        try:
            parent.grid_rowconfigure(0, weight=1)
            parent.grid_columnconfigure(0, weight=1)
        except Exception:  # noqa: BLE001
            pass

    body_scroll = ctk.CTkScrollableFrame(root, fg_color="transparent")
    body_scroll.grid(row=2, column=0, sticky="nsew")

    return FormPageLayout(
        root=root,
        header_parent=root,
        body=body_scroll,
        form_scroll=body_scroll,
    )


def attach_save_bar_to_form_panel(
    layout: FormPageLayout,
    *,
    save_label: str,
    on_save: Callable[[], None],
    secondary: list[tuple[str, Callable[[], None], dict[str, Any]]] | None = None,
    hint: str = "Edit fields above, then Save",
) -> StickySaveBar:
    """Put sticky Save under form_scroll inside form_panel (list+form pages)."""
    if layout.form_panel is None:
        raise ValueError("layout has no form_panel")
    bar = make_sticky_save_bar(
        layout.form_panel,
        save_label=save_label,
        on_save=on_save,
        secondary=secondary,
        hint=hint,
        row=1,
    )
    layout.save_bar = bar
    return bar
