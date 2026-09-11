"""Memory, Projects, Company workflows, CEO dashboard pages."""

from __future__ import annotations

import tkinter.messagebox as messagebox
from typing import TYPE_CHECKING, Any

import customtkinter as ctk

from app.ui.themes import UI as _THEME_UI

_HC_MUTED = _THEME_UI["muted"]
_HC_LABEL = _THEME_UI["label"]

from app.services import company_store as company
from app.services import memory_store
from app.services import project_store
from app.services import workflow_graph as wfg
from app.core.services.chat.orchestrator import get_orchestrator

if TYPE_CHECKING:
    from app.ui.app_window import AppWindow


def page_memory(app: AppWindow) -> None:
    from app.ui.themes import style_chrome_button

    root = ctk.CTkFrame(app.content, fg_color="transparent")
    root.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
    root.grid_columnconfigure(0, weight=1)
    root.grid_rowconfigure(2, weight=1)

    app._page_header(
        root,
        "Memory",
        "Long-term facts for chat + company workers. Sticky Add bar stays fixed; list scrolls.",
    )

    # Sticky add bar (always visible)
    form = ctk.CTkFrame(
        root,
        fg_color=_THEME_UI.get("top_bg", ("#f3f4f6", "#161a22")),
        corner_radius=10,
        border_width=1,
        border_color=_THEME_UI.get("top_border", ("#6b7280", "#4b5563")),
    )
    form.grid(row=1, column=0, sticky="ew", pady=(0, 8))
    form.grid_columnconfigure(0, weight=1)
    entry = ctk.CTkTextbox(form, height=72)
    entry.grid(row=0, column=0, sticky="ew", padx=10, pady=10)

    scroll = ctk.CTkScrollableFrame(root, fg_color="transparent")
    scroll.grid(row=2, column=0, sticky="nsew")

    def refresh() -> None:
        for w in scroll.winfo_children():
            w.destroy()
        items = memory_store.list_items()
        if not items:
            ctk.CTkLabel(
                scroll,
                text="No memories yet. Type above and click Add memory.",
                text_color=_HC_MUTED,
            ).pack(padx=12, pady=20)
            return
        for item in items:
            row = ctk.CTkFrame(scroll)
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(
                row,
                text=item.get("content") or "",
                wraplength=700,
                justify="left",
                anchor="w",
            ).pack(side="left", fill="x", expand=True, padx=8, pady=6)
            ctk.CTkButton(
                row,
                text="Delete",
                width=70,
                fg_color="#a33",
                command=lambda i=item["id"]: (memory_store.delete_item(i), refresh()),
            ).pack(side="right", padx=6)

    def add() -> None:
        text = entry.get("1.0", "end").strip()
        if not text:
            status_l.configure(text="Type a memory first", text_color=("tomato", "#f87171"))
            return
        memory_store.add_item(
            text, project_id=project_store.get_active_project_id(), source="user"
        )
        entry.delete("1.0", "end")
        refresh()
        status_l.configure(text="✓ Memory saved", text_color=_THEME_UI.get("success", _HC_LABEL))
        app.set_status("Memory saved", toast=True)

    ctk.CTkButton(
        form,
        text="💾  Add memory",
        width=140,
        height=34,
        command=add,
        **style_chrome_button(primary=True),
    ).grid(row=0, column=1, padx=10, pady=10)
    status_l = ctk.CTkLabel(form, text="Write a fact, then Add (Ctrl+S)", text_color=_HC_MUTED)
    status_l.grid(row=1, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 8))
    app._page_save_handler = add
    refresh()


def page_projects(app: AppWindow) -> None:
    from app.ui.components.page_layout import attach_save_bar_to_form_panel, make_list_form_page

    layout = make_list_form_page(app.content, list_width=260)
    app._page_form_layout = layout

    app._page_header(
        layout.header_parent,
        "Projects",
        "Group chats and outputs. Scroll the form if needed — Save stays on the bar below.",
        columnspan=1,
    )

    assert layout.list_panel is not None and layout.list_scroll is not None
    list_frame = layout.list_scroll
    form = layout.form_scroll
    assert form is not None

    name_e = ctk.CTkEntry(form, placeholder_text="Project name")
    name_e.pack(fill="x", padx=12, pady=(12, 6))
    desc_e = ctk.CTkTextbox(form, height=140)
    desc_e.pack(fill="x", padx=12, pady=6)
    status_l = ctk.CTkLabel(form, text="", text_color=_HC_MUTED)
    status_l.pack(anchor="w", padx=12, pady=(0, 12))

    selected: dict[str, Any] = {"id": ""}

    def refresh_list() -> None:
        for w in list_frame.winfo_children():
            w.destroy()
        active = project_store.get_active_project_id()
        for p in project_store.list_projects():
            label = p.get("name") or p["id"][:8]
            if p["id"] == active:
                label = "★ " + label
            ctk.CTkButton(
                list_frame,
                text=label,
                anchor="w",
                fg_color="transparent",
                command=lambda pid=p["id"]: select(pid),
            ).pack(fill="x", pady=2)

    def select(pid: str) -> None:
        p = project_store.load_project(pid)
        if not p:
            return
        selected["id"] = pid
        name_e.delete(0, "end")
        name_e.insert(0, p.get("name") or "")
        desc_e.delete("1.0", "end")
        desc_e.insert("1.0", p.get("description") or "")
        status_l.configure(text=f"id={pid[:8]}… status={p.get('status')}")
        try:
            save_bar.set_status("Edit fields, then Save", kind="muted")
        except Exception:  # noqa: BLE001
            pass

    def create() -> None:
        p = project_store.new_project(name_e.get() or "New project", desc_e.get("1.0", "end"))
        project_store.set_active_project_id(p["id"])
        refresh_list()
        select(p["id"])
        app.set_status(f"Project created: {p.get('name')}", toast=True)
        save_bar.mark_saved("✓ Project created")

    def save() -> None:
        if not selected["id"]:
            create()
            return
        p = project_store.load_project(selected["id"]) or {"id": selected["id"]}
        p["name"] = name_e.get().strip() or "Project"
        p["description"] = desc_e.get("1.0", "end").strip()
        project_store.save_project(p)
        refresh_list()
        app.set_status("Project saved", toast=True)
        save_bar.mark_saved("✓ Project saved")

    def activate() -> None:
        if selected["id"]:
            project_store.set_active_project_id(selected["id"])
            refresh_list()
            app.set_status("Active project set", toast=True)

    def delete() -> None:
        if not selected["id"]:
            return
        if messagebox.askyesno("Delete project", "Delete this project?"):
            project_store.delete_project(selected["id"])
            selected["id"] = ""
            name_e.delete(0, "end")
            desc_e.delete("1.0", "end")
            refresh_list()
            save_bar.set_status("Project deleted", kind="muted")

    save_bar = attach_save_bar_to_form_panel(
        layout,
        save_label="💾  Save project",
        on_save=save,
        secondary=[
            ("New", create, {"width": 70}),
            ("Set active", activate, {"width": 100}),
            ("Delete", delete, {"fg_color": "#a33", "hover_color": "#7f1d1d", "width": 80}),
        ],
        hint="Edit name/description, then Save (Ctrl+S)",
    )
    app._page_save_handler = save
    refresh_list()


def page_company(app: AppWindow) -> None:
    root = ctk.CTkFrame(app.content, fg_color="transparent")
    root.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
    root.grid_columnconfigure(0, weight=1)
    root.grid_rowconfigure(2, weight=1)

    ctk.CTkLabel(
        root,
        text="Company workflows",
        font=ctk.CTkFont(size=22, weight="bold"),
        text_color=_HC_LABEL,
    ).grid(row=0, column=0, sticky="w")
    ctk.CTkLabel(
        root,
        text="Background multi-AI structure (PM / Engineer / QA…). Chat stays free while workers run.",
        text_color=_HC_MUTED,
    ).grid(row=1, column=0, sticky="w", pady=(0, 8))

    body = ctk.CTkFrame(root)
    body.grid(row=2, column=0, sticky="nsew")
    body.grid_columnconfigure(0, weight=1)
    body.grid_columnconfigure(1, weight=1)
    body.grid_rowconfigure(1, weight=1)

    # Roles
    ctk.CTkLabel(
        body, text="Roles (AI employees)", font=ctk.CTkFont(weight="bold"), text_color=_HC_LABEL
    ).grid(
        row=0, column=0, sticky="w", padx=8, pady=4
    )
    roles_f = ctk.CTkScrollableFrame(body, height=200)
    roles_f.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)

    def refresh_roles() -> None:
        for w in roles_f.winfo_children():
            w.destroy()
        for r in company.list_roles():
            ctk.CTkLabel(
                roles_f,
                text=f"{r.get('title')}  [{r.get('id')}]\n{r.get('description') or ''}",
                justify="left",
                anchor="w",
            ).pack(fill="x", pady=4)

    role_name = ctk.CTkEntry(body, placeholder_text="New role title")
    role_name.grid(row=2, column=0, sticky="ew", padx=8, pady=4)

    def add_role() -> None:
        if role_name.get().strip():
            company.add_role(role_name.get().strip())
            role_name.delete(0, "end")
            refresh_roles()

    ctk.CTkButton(body, text="Add AI role", command=add_role).grid(
        row=3, column=0, sticky="w", padx=8, pady=4
    )

    # Tasks queue
    ctk.CTkLabel(
        body, text="Work queue", font=ctk.CTkFont(weight="bold"), text_color=_HC_LABEL
    ).grid(
        row=0, column=1, sticky="w", padx=8, pady=4
    )
    tasks_f = ctk.CTkScrollableFrame(body, height=280)
    tasks_f.grid(row=1, column=1, rowspan=3, sticky="nsew", padx=8, pady=4)

    def refresh_tasks() -> None:
        for w in tasks_f.winfo_children():
            w.destroy()
        for t in company.list_work_tasks()[:40]:
            ctk.CTkLabel(
                tasks_f,
                text=(
                    f"[{t.get('status')}] {t.get('title')}\n"
                    f"role={t.get('role_id')} goal={str(t.get('goal_id') or '')[:8]}"
                ),
                justify="left",
                anchor="w",
            ).pack(fill="x", pady=4)

    def manual_task() -> None:
        title = role_name.get().strip() or "Ad-hoc task"
        # reuse entry as title for quick add
        t = company.new_work_task(title, role_id="engineer", description=title)
        if company.get_approval_mode() == "auto":
            t["auto_approved"] = True
            company.save_work_task(t)
        get_orchestrator().kick()
        refresh_tasks()
        app.set_status("Task queued for background AI")

    ctk.CTkButton(body, text="Queue engineer task (title above)", command=manual_task).grid(
        row=4, column=0, sticky="w", padx=8, pady=8
    )
    ctk.CTkButton(body, text="Refresh queue", command=refresh_tasks).grid(
        row=4, column=1, sticky="w", padx=8, pady=8
    )

    orch = get_orchestrator()
    ctk.CTkLabel(body, text=f"Worker: {orch.status}", text_color=_HC_MUTED).grid(
        row=5, column=0, columnspan=2, sticky="w", padx=8
    )

    refresh_roles()
    refresh_tasks()


def page_ceo(app: AppWindow) -> None:
    root = ctk.CTkFrame(app.content, fg_color="transparent")
    root.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
    root.grid_columnconfigure(0, weight=1)
    root.grid_rowconfigure(3, weight=1)

    ctk.CTkLabel(
        root, text="CEO", font=ctk.CTkFont(size=22, weight="bold"), text_color=_HC_LABEL
    ).grid(
        row=0, column=0, sticky="w"
    )
    ctk.CTkLabel(
        root,
        text="Set goals, assign multi-AI plans, approve work. Background workers do not block Chat.",
        text_color=_HC_MUTED,
    ).grid(row=1, column=0, sticky="w", pady=(0, 8))

    # Approval mode
    top = ctk.CTkFrame(root)
    top.grid(row=2, column=0, sticky="ew", pady=(0, 8))
    mode = company.get_approval_mode()
    mode_var = ctk.StringVar(master=top, value=mode)

    def set_mode(v: str) -> None:
        company.set_approval_mode(v)
        app.set_status(f"Approval mode: {v}")

    ctk.CTkLabel(top, text="Approval mode:", text_color=_HC_LABEL).pack(side="left", padx=8, pady=8)
    ctk.CTkSegmentedButton(
        top, values=["manual", "auto"], variable=mode_var, command=set_mode, width=180
    ).pack(side="left", padx=8)
    ctk.CTkLabel(
        top,
        text="manual = CEO approves each task · auto = run immediately",
        text_color=_HC_MUTED,
    ).pack(side="left", padx=8)

    body = ctk.CTkFrame(root)
    body.grid(row=3, column=0, sticky="nsew")
    body.grid_columnconfigure(0, weight=1)
    body.grid_columnconfigure(1, weight=1)
    body.grid_rowconfigure(1, weight=1)

    # Goals
    ctk.CTkLabel(
        body, text="Goals", font=ctk.CTkFont(weight="bold"), text_color=_HC_LABEL
    ).grid(
        row=0, column=0, sticky="w", padx=8
    )
    goals_f = ctk.CTkScrollableFrame(body)
    goals_f.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)

    goal_title = ctk.CTkEntry(body, placeholder_text="New goal title")
    goal_title.grid(row=2, column=0, sticky="ew", padx=8, pady=4)
    goal_desc = ctk.CTkTextbox(body, height=60)
    goal_desc.grid(row=3, column=0, sticky="ew", padx=8, pady=4)

    def refresh_goals() -> None:
        for w in goals_f.winfo_children():
            w.destroy()
        for g in company.list_goals()[:30]:
            row = ctk.CTkFrame(goals_f)
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(
                row,
                text=f"[{g.get('status')}] {g.get('title')}",
                anchor="w",
            ).pack(side="left", fill="x", expand=True, padx=6)
            ctk.CTkButton(
                row,
                text="Run plan",
                width=80,
                command=lambda gid=g["id"]: run_plan(gid),
            ).pack(side="right", padx=4)

    def create_goal() -> None:
        t = goal_title.get().strip()
        if not t:
            return
        g = company.new_goal(
            t,
            goal_desc.get("1.0", "end").strip(),
            project_id=project_store.get_active_project_id(),
        )
        goal_title.delete(0, "end")
        refresh_goals()
        app.set_status(f"Goal created: {g.get('title')}")

    def run_plan(gid: str) -> None:
        res = get_orchestrator().ceo_create_plan(gid)
        if res.get("ok"):
            messagebox.showinfo(
                "Plan queued",
                f"Created {len(res.get('task_ids') or [])} org-tree tasks "
                f"(agents + blocked CEO synthesis).\n"
                f"Source={res.get('source') or 'org'} · Approval={company.get_approval_mode()}",
                parent=app,
            )
            refresh_goals()
            refresh_approvals()
            get_orchestrator().kick()
        else:
            messagebox.showerror("Error", str(res.get("error")), parent=app)

    ctk.CTkButton(body, text="Create goal", command=create_goal).grid(
        row=4, column=0, sticky="w", padx=8, pady=4
    )

    # Approvals
    ctk.CTkLabel(
        body, text="Approvals", font=ctk.CTkFont(weight="bold"), text_color=_HC_LABEL
    ).grid(
        row=0, column=1, sticky="w", padx=8
    )
    ap_f = ctk.CTkScrollableFrame(body)
    ap_f.grid(row=1, column=1, rowspan=3, sticky="nsew", padx=8, pady=4)

    def refresh_approvals() -> None:
        for w in ap_f.winfo_children():
            w.destroy()
        pending = company.list_approvals(status="pending")
        if not pending:
            ctk.CTkLabel(ap_f, text="No pending approvals").pack(anchor="w", padx=6, pady=6)
        for ap in pending:
            row = ctk.CTkFrame(ap_f)
            row.pack(fill="x", pady=4)
            ctk.CTkLabel(
                row,
                text=(ap.get("summary") or "")[:200],
                wraplength=320,
                justify="left",
                anchor="w",
            ).pack(anchor="w", padx=6, pady=4)
            bar = ctk.CTkFrame(row, fg_color="transparent")
            bar.pack(fill="x", padx=6, pady=4)
            ctk.CTkButton(
                bar,
                text="Approve",
                width=80,
                command=lambda i=ap["id"]: (
                    get_orchestrator().approve(i),
                    refresh_approvals(),
                    app.set_status("Approved"),
                ),
            ).pack(side="left", padx=2)
            ctk.CTkButton(
                bar,
                text="Reject",
                width=80,
                fg_color="#a33",
                command=lambda i=ap["id"]: (
                    get_orchestrator().reject(i),
                    refresh_approvals(),
                    app.set_status("Rejected"),
                ),
            ).pack(side="left", padx=2)

    orch = get_orchestrator()
    ctk.CTkLabel(
        body,
        text=f"Background worker: {orch.status}",
        text_color=_HC_MUTED,
    ).grid(row=4, column=1, sticky="w", padx=8)

    ctk.CTkButton(body, text="Refresh", command=lambda: (refresh_goals(), refresh_approvals())).grid(
        row=5, column=0, columnspan=2, sticky="w", padx=8, pady=8
    )

    refresh_goals()
    refresh_approvals()


def page_workflow(app: AppWindow) -> None:
    """Org chart: CEO -> Departments -> Agents."""
    from app.ui.pages.org_page import page_workflow as _org_page

    _org_page(app)


def page_chats(app: AppWindow) -> None:  # noqa: C901 (intentionally long, UI-only)
    """Redesigned Chat Management page — card layout with search, sections & icon actions."""
    from datetime import datetime, timezone

    from app.services import chat_store
    from app.core.services.chat.chat_export import export_chat
    from app.ui.themes import UI as _UI, style_chrome_button, style_entry, style_option_menu

    # ── colour aliases ────────────────────────────────────────────────────────
    _CARD_BG     = _UI.get("card_bg",      ("white", "#141414"))
    _CARD_BORDER = _UI.get("card_border",  ("white", "#27272a"))
    _ACCENT      = _UI.get("accent",       ("#2563eb", "#60a5fa"))
    _ACCENT_SOFT = _UI.get("accent_soft",  ("#dbeafe", "#1e293b"))
    _DANGER      = _UI.get("danger",       ("#dc2626", "#f87171"))
    _DANGER_SOFT = ("#fef2f2", "#450a0a")
    _SUCCESS     = _UI.get("success",      ("#059669", "#34d399"))
    _MUTED       = _UI.get("muted",        ("#111827", "#e5e7eb"))
    _LABEL       = _UI.get("label",        ("#0a0f1a", "#f9fafb"))

    def _rel_time(iso: str | None) -> str:
        """Return a human-readable relative timestamp."""
        if not iso:
            return ""
        try:
            ts = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            delta = now - ts
            s = int(delta.total_seconds())
            if s < 60:
                return "just now"
            if s < 3600:
                return f"{s // 60}m ago"
            if s < 86400:
                return f"{s // 3600}h ago"
            if s < 604800:
                return f"{s // 86400}d ago"
            return ts.strftime("%b %-d") if hasattr(ts, "strftime") else iso[:10]
        except Exception:  # noqa: BLE001
            return ""

    # ── project look-up ───────────────────────────────────────────────────────
    projects = project_store.list_projects()
    proj_map: dict[str, str] = {"(all projects)": "", "(ungrouped)": "__none__"}
    for p in projects:
        proj_map[p.get("name") or p["id"][:8]] = p["id"]

    # ── root layout ───────────────────────────────────────────────────────────
    root = ctk.CTkFrame(app.content, fg_color="transparent")
    root.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
    root.grid_columnconfigure(0, weight=1)
    root.grid_rowconfigure(3, weight=1)

    # ── header ────────────────────────────────────────────────────────────────
    header = ctk.CTkFrame(root, fg_color="transparent")
    header.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 0))
    header.grid_columnconfigure(1, weight=1)

    title_col = ctk.CTkFrame(header, fg_color="transparent")
    title_col.grid(row=0, column=0, sticky="w")
    ctk.CTkLabel(
        title_col,
        text="💬  Chat Management",
        font=ctk.CTkFont(size=24, weight="bold"),
        text_color=_LABEL,
    ).pack(anchor="w")
    ctk.CTkLabel(
        title_col,
        text="Browse, search and manage every conversation — open, pin, branch, export or delete.",
        text_color=_MUTED,
        font=ctk.CTkFont(size=12),
    ).pack(anchor="w", pady=(2, 0))

    # Action buttons (top-right)
    actions = ctk.CTkFrame(header, fg_color="transparent")
    actions.grid(row=0, column=2, sticky="e")

    # ── toolbar (search + filter) ──────────────────────────────────────────────
    toolbar = ctk.CTkFrame(
        root,
        fg_color=_UI.get("top_bg", ("white", "#121212")),
        corner_radius=12,
        border_width=1,
        border_color=_UI.get("top_border", ("#d1d5db", "#2a2a2a")),
    )
    toolbar.grid(row=1, column=0, sticky="ew", padx=20, pady=(14, 0))
    toolbar.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(
        toolbar, text="🔍", font=ctk.CTkFont(size=16), text_color=_MUTED, width=28
    ).grid(row=0, column=0, padx=(14, 2), pady=10)
    search_var = ctk.StringVar(master=toolbar)
    search_entry = ctk.CTkEntry(
        toolbar,
        textvariable=search_var,
        placeholder_text="Search chats by title…",
        height=36,
        border_width=0,
        fg_color="transparent",
        **{k: v for k, v in style_entry().items() if k not in ("fg_color", "border_width", "border_color")},
    )
    search_entry.grid(row=0, column=1, sticky="ew", padx=4, pady=8)

    ctk.CTkLabel(toolbar, text="Project:", text_color=_MUTED, font=ctk.CTkFont(size=12)).grid(
        row=0, column=2, padx=(8, 2), pady=10
    )
    filter_var = ctk.StringVar(master=toolbar, value="(all projects)")
    ctk.CTkOptionMenu(
        toolbar,
        values=list(proj_map.keys()),
        variable=filter_var,
        command=lambda _v: render(),
        width=155,
        height=34,
        **style_option_menu(),
    ).grid(row=0, column=3, padx=(0, 14), pady=8)

    # ── stats bar ─────────────────────────────────────────────────────────────
    stats_bar = ctk.CTkFrame(root, fg_color="transparent")
    stats_bar.grid(row=2, column=0, sticky="ew", padx=20, pady=(10, 4))
    stats_label = ctk.CTkLabel(stats_bar, text="", text_color=_MUTED, font=ctk.CTkFont(size=12))
    stats_label.pack(side="left")

    # ── scrollable list ────────────────────────────────────────────────────────
    scroll = ctk.CTkScrollableFrame(root, fg_color="transparent", corner_radius=0)
    scroll.grid(row=3, column=0, sticky="nsew", padx=12, pady=(0, 8))
    scroll.grid_columnconfigure(0, weight=1)

    # ── cached project names ───────────────────────────────────────────────────
    _proj_name_cache: dict[str, str] = {}

    def _pname(pid: str) -> str:
        if not pid:
            return ""
        if pid not in _proj_name_cache:
            pr = project_store.load_project(pid)
            _proj_name_cache[pid] = (pr or {}).get("name") or pid[:8]
        return _proj_name_cache[pid]

    # ── helpers ────────────────────────────────────────────────────────────────
    active_id: str = chat_store.get_active_chat_id() or ""

    def open_chat(cid: str) -> None:
        chat_store.set_active_chat_id(cid)
        app._chat_state = app._load_active_chat()  # type: ignore[attr-defined]
        app.show_page("Chat")
        app.set_status("Chat opened")

    def new_c() -> None:
        c = chat_store.new_chat("New chat", project_id=project_store.get_active_project_id())
        open_chat(c["id"])

    def do_export(cid: str) -> None:
        chat = chat_store.load_chat(cid)
        path = export_chat(chat, fmt="md")
        messagebox.showinfo("Export", f"Exported:\n{path}", parent=app)

    def do_move(cid: str) -> None:
        targets = [n for n in proj_map if n != "(all projects)"]
        if not targets:
            messagebox.showinfo("Move", "Create a project first in Projects tab.", parent=app)
            return
        import tkinter.simpledialog as sd
        choice = sd.askstring(
            "Move chat to project",
            "Type project name exactly:\n" + "\n".join(targets),
            parent=app,
        )
        if choice is None:
            return
        if choice == "(ungrouped)":
            chat_store.move_chat_to_project(cid, "")
        elif choice in proj_map:
            chat_store.move_chat_to_project(cid, proj_map[choice])
        else:
            messagebox.showerror("Move", "Unknown project name", parent=app)
            return
        render()
        app.set_status("Chat moved")

    def _icon_btn(
        parent: Any,
        text: str,
        tip: str,
        cmd: Any,
        *,
        danger: bool = False,
        primary: bool = False,
        width: int = 72,
    ) -> ctk.CTkButton:
        """Compact labelled icon button for the card action row."""
        if danger:
            kw = {
                "fg_color": _DANGER_SOFT,
                "hover_color": _DANGER,
                "text_color": _DANGER,
                "border_width": 1,
                "border_color": _DANGER,
            }
        elif primary:
            kw = {
                "fg_color": _ACCENT,
                "hover_color": _UI.get("btn_primary_hover", ("#1d4ed8", "#60a5fa")),
                "text_color": ("white", "#0a0f1a"),
                "border_width": 0,
            }
        else:
            kw = {
                "fg_color": _UI.get("btn_bg", ("#e5e7eb", "#2a3140")),
                "hover_color": _UI.get("btn_hover", ("#d1d5db", "#3a4356")),
                "text_color": _LABEL,
                "border_width": 1,
                "border_color": _UI.get("top_border", ("#d1d5db", "#2a2a2a")),
            }
        btn = ctk.CTkButton(
            parent,
            text=text,
            width=width,
            height=28,
            corner_radius=8,
            font=ctk.CTkFont(size=11),
            command=cmd,
            **kw,
        )
        try:
            app._tooltip(btn, tip)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
        return btn

    def _section_label(parent: Any, text: str) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=4, pady=(10, 4))
        ctk.CTkLabel(
            row,
            text=text,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=_MUTED,
        ).pack(side="left")
        sep = ctk.CTkFrame(row, height=1, fg_color=_UI.get("card_border", ("#e2e8f0", "#27272a")))
        sep.pack(side="left", fill="x", expand=True, padx=(8, 0), pady=1)

    def _build_card(parent: Any, meta: dict, full: dict, pid: str, pname: str) -> None:
        """Build one chat card."""
        cid = meta["id"]
        is_active = cid == active_id
        is_pinned = bool(full.get("pinned") or meta.get("pinned"))
        is_branch = bool(full.get("parent_chat_id"))
        msg_count = len(full.get("messages") or [])
        updated = meta.get("updated_at") or full.get("updated_at") or ""
        title = (meta.get("title") or cid[:8] or "Untitled").strip()

        # Card frame
        card = ctk.CTkFrame(
            parent,
            fg_color=_ACCENT_SOFT if is_active else _CARD_BG,
            corner_radius=12,
            border_width=1,
            border_color=_ACCENT if is_active else _CARD_BORDER,
        )
        card.pack(fill="x", padx=4, pady=3)
        card.grid_columnconfigure(0, weight=1)

        # ── top row: title + badges ──
        top_row = ctk.CTkFrame(card, fg_color="transparent")
        top_row.grid(row=0, column=0, columnspan=2, sticky="ew", padx=14, pady=(10, 2))
        top_row.grid_columnconfigure(1, weight=1)

        # Active indicator dot
        if is_active:
            ctk.CTkLabel(
                top_row,
                text="●",
                font=ctk.CTkFont(size=12),
                text_color=_ACCENT,
                width=16,
            ).grid(row=0, column=0, sticky="w", padx=(0, 4))

        title_font_weight = "bold" if is_active else "normal"
        ctk.CTkLabel(
            top_row,
            text=title,
            font=ctk.CTkFont(size=13, weight=title_font_weight),
            text_color=_LABEL,
            anchor="w",
        ).grid(row=0, column=1 if is_active else 0, columnspan=1, sticky="w")

        # Badges (pin / branch / project)
        badges = ctk.CTkFrame(top_row, fg_color="transparent")
        badges.grid(row=0, column=2, sticky="e", padx=(8, 0))

        if is_pinned:
            ctk.CTkLabel(
                badges,
                text="📌 Pinned",
                font=ctk.CTkFont(size=10),
                fg_color=("#fef9c3", "#422006"),
                text_color=("#92400e", "#fbbf24"),
                corner_radius=6,
                padx=6,
                pady=2,
            ).pack(side="left", padx=2)

        if is_branch:
            ctk.CTkLabel(
                badges,
                text="⎇ Branch",
                font=ctk.CTkFont(size=10),
                fg_color=("#ede9fe", "#2e1065"),
                text_color=("#6d28d9", "#c4b5fd"),
                corner_radius=6,
                padx=6,
                pady=2,
            ).pack(side="left", padx=2)

        if pname:
            ctk.CTkLabel(
                badges,
                text=f"◫ {pname}",
                font=ctk.CTkFont(size=10),
                fg_color=_ACCENT_SOFT,
                text_color=_ACCENT,
                corner_radius=6,
                padx=6,
                pady=2,
            ).pack(side="left", padx=2)

        # ── meta row: msg count + timestamp ──
        meta_row = ctk.CTkFrame(card, fg_color="transparent")
        meta_row.grid(row=1, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 6))

        msg_txt = f"{msg_count} message{'s' if msg_count != 1 else ''}"
        ctk.CTkLabel(
            meta_row,
            text=msg_txt,
            font=ctk.CTkFont(size=11),
            text_color=_MUTED,
        ).pack(side="left")

        if updated:
            rel = _rel_time(updated)
            ctk.CTkLabel(
                meta_row,
                text=f"  ·  {rel}",
                font=ctk.CTkFont(size=11),
                text_color=_MUTED,
            ).pack(side="left")

        # ── action row ──
        action_row = ctk.CTkFrame(card, fg_color="transparent")
        action_row.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=(2, 10))

        _icon_btn(
            action_row, "▶ Open", "Open this chat", lambda i=cid: open_chat(i), primary=True, width=78
        ).pack(side="left", padx=3)

        pin_label = "📌 Unpin" if is_pinned else "📌 Pin"
        pin_tip = "Remove pin from this chat" if is_pinned else "Keep this chat at the top"
        _icon_btn(
            action_row, pin_label, pin_tip,
            lambda i=cid: (chat_store.toggle_pin(i), render()), width=78
        ).pack(side="left", padx=3)

        _icon_btn(
            action_row, "⎇ Branch", "Fork a copy of this chat",
            lambda i=cid: (chat_store.branch_chat(i), open_chat(chat_store.get_active_chat_id())),
            width=82,
        ).pack(side="left", padx=3)

        _icon_btn(
            action_row, "⬆ Export", "Export chat to Markdown",
            lambda i=cid: do_export(i), width=80
        ).pack(side="left", padx=3)

        _icon_btn(
            action_row, "↪ Move", "Move to a different project",
            lambda i=cid: do_move(i), width=72
        ).pack(side="left", padx=3)

        _icon_btn(
            action_row, "🗑 Delete", "Permanently delete this chat",
            lambda i=cid: (chat_store.delete_chat(i), render()),
            danger=True, width=80,
        ).pack(side="right", padx=3)

    # ── main render ────────────────────────────────────────────────────────────
    def render() -> None:
        for w in scroll.winfo_children():
            try:
                w.destroy()
            except Exception:  # noqa: BLE001
                pass
        _proj_name_cache.clear()

        f = proj_map.get(filter_var.get(), "")
        q = search_var.get().strip().lower()

        chats = chat_store.list_chats()
        pinned_items: list[tuple[dict, dict, str, str]] = []
        recent_items: list[tuple[dict, dict, str, str]] = []

        for meta in chats:
            full = chat_store.load_chat(meta["id"])
            pid = full.get("project_id") or ""

            # Project filter
            if f == "__none__" and pid:
                continue
            if f and f != "__none__" and pid != f:
                continue

            # Search filter
            title = (meta.get("title") or meta["id"]).lower()
            if q and q not in title and q not in meta["id"].lower():
                continue

            pname = _pname(pid)
            item = (meta, full, pid, pname)
            if full.get("pinned") or meta.get("pinned"):
                pinned_items.append(item)
            else:
                recent_items.append(item)

        total = len(pinned_items) + len(recent_items)
        stats_label.configure(
            text=f"{total} chat{'s' if total != 1 else ''}  ·  {len(pinned_items)} pinned"
        )

        if not pinned_items and not recent_items:
            empty = ctk.CTkFrame(scroll, fg_color="transparent")
            empty.pack(fill="both", expand=True, pady=60)
            ctk.CTkLabel(
                empty,
                text="💬",
                font=ctk.CTkFont(size=48),
            ).pack()
            ctk.CTkLabel(
                empty,
                text="No chats found" if q else "No chats yet",
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color=_LABEL,
            ).pack(pady=(8, 4))
            ctk.CTkLabel(
                empty,
                text='Try a different search term.' if q else 'Click "＋ New chat" to get started.',
                font=ctk.CTkFont(size=12),
                text_color=_MUTED,
            ).pack()
            return

        if pinned_items:
            _section_label(scroll, "📌  PINNED")
            for (meta, full, pid, pname) in pinned_items:
                _build_card(scroll, meta, full, pid, pname)

        if recent_items:
            _section_label(scroll, "🕐  RECENT")
            for (meta, full, pid, pname) in recent_items:
                _build_card(scroll, meta, full, pid, pname)

    # Wire search
    search_var.trace_add("write", lambda *_: render())

    # ── bottom action bar ──────────────────────────────────────────────────────
    bar = ctk.CTkFrame(root, fg_color="transparent")
    bar.grid(row=4, column=0, sticky="ew", padx=20, pady=(4, 16))

    ctk.CTkButton(
        bar,
        text="＋  New chat",
        height=36,
        corner_radius=10,
        command=new_c,
        **style_chrome_button(primary=True),
    ).pack(side="left", padx=(0, 8))

    ctk.CTkButton(
        bar,
        text="↺  Refresh",
        height=36,
        corner_radius=10,
        command=render,
        **style_chrome_button(),
    ).pack(side="left")

    render()
