"""Work Board page — extracted from AppWindow."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import customtkinter as ctk

if TYPE_CHECKING:
    from app.ui.app_window import AppWindow


def page_work_board(app) -> None:
    """Unified work board: company tasks by status + approvals badge."""
    from app.services import company_store as company
    from app.ui.themes import UI as _UI, style_chrome_button

    root = ctk.CTkFrame(app.content, fg_color="transparent")
    root.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
    root.grid_columnconfigure((0, 1, 2, 3), weight=1)
    root.grid_rowconfigure(1, weight=1)

    app._page_header(
        root,
        "Work board",
        "Company tasks by status — Chat stays free while workers run.",
        columnspan=4,
        actions=[
            ("Refresh", lambda: app.show_page("Work")),
            ("Approvals", lambda: app.show_page("Approvals")),
            ("CEO", lambda: app.show_page("CEO")),
        ],
    )

    tasks: list[dict] = []
    try:
        if hasattr(company, "list_work_tasks"):
            tasks = list(company.list_work_tasks() or [])
    except Exception:  # noqa: BLE001
        tasks = []
    if not tasks:
        try:
            from app.paths import data_dir
            import json as _json

            wdir = data_dir() / "company" / "work_tasks"
            for p in sorted(wdir.glob("*.json"), reverse=True)[:80]:
                try:
                    tasks.append(_json.loads(p.read_text(encoding="utf-8")))
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            tasks = []

    cols = {
        "queued": ("Todo / queued", []),
        "running": ("Running", []),
        "waiting": ("Waiting approval", []),
        "done": ("Done", []),
    }
    for t in tasks:
        st = str(t.get("status") or "queued").lower()
        if st in ("pending_approval", "waiting", "needs_approval"):
            cols["waiting"][1].append(t)
        elif st in ("running", "in_progress", "active"):
            cols["running"][1].append(t)
        elif st in ("done", "completed", "success", "failed", "error"):
            cols["done"][1].append(t)
        else:
            cols["queued"][1].append(t)

    try:
        for ap in company.list_approvals(status="pending") or []:
            cols["waiting"][1].append(
                {
                    "title": f"Approval: {ap.get('title') or ap.get('id', '')[:8]}",
                    "status": "pending_approval",
                    "description": str(ap.get("summary") or ap.get("description") or "")[:200],
                }
            )
    except Exception:  # noqa: BLE001
        pass

    for i, key in enumerate(("queued", "running", "waiting", "done")):
        title, items = cols[key]
        col = ctk.CTkScrollableFrame(root, fg_color=_UI["top_bg"], corner_radius=10)
        col.grid(row=1, column=i, sticky="nsew", padx=4, pady=8)
        ctk.CTkLabel(
            col, text=f"{title} ({len(items)})", font=ctk.CTkFont(weight="bold"), text_color=_UI["label"]
        ).pack(anchor="w", padx=8, pady=8)
        if not items:
            ctk.CTkLabel(col, text="—", text_color=_UI["muted"]).pack(anchor="w", padx=8, pady=4)
        for t in items[:40]:
            card = ctk.CTkFrame(col, corner_radius=8)
            card.pack(fill="x", padx=6, pady=4)
            ctk.CTkLabel(
                card,
                text=(t.get("title") or t.get("name") or t.get("id") or "task")[:60],
                font=ctk.CTkFont(size=12, weight="bold"),
                anchor="w",
                text_color=_UI["label"],
            ).pack(anchor="w", padx=8, pady=(6, 2))
            ctk.CTkLabel(
                card,
                text=f"{t.get('status') or ''} · {t.get('role_id') or t.get('role') or ''}",
                text_color=_UI["muted"],
                font=ctk.CTkFont(size=11),
                anchor="w",
            ).pack(anchor="w", padx=8, pady=(0, 6))

    bar = ctk.CTkFrame(root, fg_color="transparent")
    bar.grid(row=2, column=0, columnspan=4, sticky="ew", pady=8)
    ctk.CTkButton(bar, text="CEO", command=lambda: app.show_page("CEO"), **style_chrome_button()).pack(
        side="left", padx=4
    )
    ctk.CTkButton(
        bar, text="Approvals", command=lambda: app.show_page("Approvals"), **style_chrome_button(primary=True)
    ).pack(side="left", padx=4)
    ctk.CTkButton(
        bar, text="Schedule", command=lambda: app.show_page("Schedule"), **style_chrome_button()
    ).pack(side="left", padx=4)
