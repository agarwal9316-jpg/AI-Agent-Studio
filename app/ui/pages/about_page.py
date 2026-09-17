"""About page — extracted from AppWindow."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import customtkinter as ctk

from app.version import __version__, APP_NAME

if TYPE_CHECKING:
    from app.ui.app_window import AppWindow


def page_about(app) -> None:
    from app.ui.themes import style_card, style_chrome_button, UI as _UI
    from app.core.services.misc.version_check import install_summary, check_for_updates

    frame = ctk.CTkFrame(app.content, fg_color="transparent")
    frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
    frame.grid_columnconfigure(0, weight=1)

    app._page_header(
        frame,
        "About",
        f"{APP_NAME} v{__version__} — portable multi-agent studio",
        actions=[
            ("Check updates", app._run_update_check_dialog),
            ("Docs", lambda: app.set_status("See docs/ folder next to the app", toast=True)),
        ],
    )
    try:
        info = install_summary()
    except Exception:  # noqa: BLE001
        info = {
            "version": __version__,
            "mode_label": "unknown",
            "app_root": "",
            "data_dir": "",
            "launch": "Launch.bat",
            "python": "",
        }

    card = ctk.CTkFrame(frame, **style_card())
    card.grid(row=1, column=0, sticky="ew", pady=8)
    try:
        from app.core.services.system import branding as _branding

        _about_logo = _branding.ctk_brand_image(64)
        if _about_logo is not None:
            app._about_brand_image = _about_logo
            ctk.CTkLabel(card, text="", image=_about_logo).pack(
                anchor="w", padx=16, pady=(16, 4)
            )
    except Exception:  # noqa: BLE001
        pass
    ctk.CTkLabel(
        card,
        justify="left",
        text_color=_UI["label"],
        font=ctk.CTkFont(size=16, weight="bold"),
        text=f"{APP_NAME}  v{info.get('version') or __version__}",
    ).pack(anchor="w", padx=16, pady=(16, 4))
    ctk.CTkLabel(
        card,
        justify="left",
        text_color=_UI["muted"],
        text=(
            f"Install mode: {info.get('mode_label')}\n"
            f"Start with: {info.get('launch')}\n"
            f"App folder:\n  {info.get('app_root')}\n"
            f"Your data (chats, keys):\n  {info.get('data_dir')}\n"
            f"Python: {info.get('python') or 'bundled'}\n\n"
            "Chat · multi-chat · memory · projects · Team · tools · Knowledge RAG\n"
            "Ctrl+K palette · Ctrl+\\ focus · F1 shortcuts · License: MIT (original code)"
        ),
    ).pack(anchor="w", padx=16, pady=(0, 8))

    bundle = ctk.CTkFrame(frame, **style_card())
    bundle.grid(row=2, column=0, sticky="ew", pady=8)
    ctk.CTkLabel(
        bundle,
        text="Studio bundle",
        font=ctk.CTkFont(size=14, weight="bold"),
        text_color=_UI["label"],
    ).pack(anchor="w", padx=16, pady=(12, 4))
    ctk.CTkLabel(
        bundle,
        text=(
            "Export a portable .zip of settings, knowledge, notes, channels,\n"
            "automations, chat list metadata, and the artifacts index.\n"
            "API keys are redacted by default (optional include-secrets on export)."
        ),
        text_color=_UI["muted"],
        justify="left",
        anchor="w",
    ).pack(anchor="w", padx=16, pady=(0, 8))
    brow = ctk.CTkFrame(bundle, fg_color="transparent")
    brow.pack(fill="x", padx=12, pady=(0, 12))
    ctk.CTkButton(
        brow,
        text="Export studio bundle",
        width=170,
        command=app._export_studio_bundle_dialog,
        **style_chrome_button(primary=True),
    ).pack(side="left", padx=4)
    ctk.CTkButton(
        brow,
        text="Import studio bundle",
        width=170,
        command=app._import_studio_bundle_dialog,
        **style_chrome_button(),
    ).pack(side="left", padx=4)

    upd = ctk.CTkFrame(frame, **style_card())
    upd.grid(row=3, column=0, sticky="ew", pady=8)
    ctk.CTkLabel(
        upd,
        text="Updates",
        font=ctk.CTkFont(size=14, weight="bold"),
        text_color=_UI["label"],
    ).pack(anchor="w", padx=16, pady=(12, 4))
    status_lbl = ctk.CTkLabel(
        upd,
        text="Click Check for updates to compare this build with VERSION / optional URL.",
        text_color=_UI["muted"],
        justify="left",
        wraplength=640,
        anchor="w",
    )
    status_lbl.pack(anchor="w", padx=16, pady=(0, 8))

    def do_check() -> None:
        status_lbl.configure(text="Checking…")
        try:
            r = check_for_updates(force_remote=True)
            status_lbl.configure(text=str(r.get("message") or ""))
            app.set_status(f"v{r.get('current')} · {r.get('status')}", toast=True)
        except Exception as e:  # noqa: BLE001
            status_lbl.configure(text=str(e))

    bar = ctk.CTkFrame(upd, fg_color="transparent")
    bar.pack(fill="x", padx=12, pady=(0, 12))
    ctk.CTkButton(
        bar,
        text="Check for updates",
        width=160,
        command=do_check,
        **style_chrome_button(primary=True),
    ).pack(side="left", padx=4)
    ctk.CTkButton(
        bar,
        text="Open app folder",
        width=140,
        command=lambda: app._open_path_in_os(str(info.get("app_root") or "")),
        **style_chrome_button(),
    ).pack(side="left", padx=4)
    ctk.CTkButton(
        bar,
        text="Open data folder",
        width=140,
        command=lambda: app._open_path_in_os(str(info.get("data_dir") or "")),
        **style_chrome_button(),
    ).pack(side="left", padx=4)
