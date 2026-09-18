"""Knowledge page — extracted from AppWindow."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import customtkinter as ctk
import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox

if TYPE_CHECKING:
    from app.ui.app_window import AppWindow


def page_knowledge(app) -> None:
    from app.ui.themes import UI as _UI
    _HC_MUTED = _UI["muted"]
    _HC_LABEL = _UI.get("label", _UI["muted"])
    from app.services import rag_knowledge as rag
    from app.services import file_watcher, local_embeddings

    root = ctk.CTkFrame(app.content, fg_color="transparent")
    root.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
    root.grid_columnconfigure(0, weight=1)
    root.grid_rowconfigure(2, weight=1)

    try:
        health = rag.knowledge_health()
        hsub = (
            f"{health.get('documents', 0)} docs · {health.get('chunks', 0)} chunks · "
            f"{health.get('watches', 0)} watches"
        )
    except Exception:  # noqa: BLE001
        hsub = "Index PDFs/MD/code · hybrid BM25+embeddings+RRF · optional folder auto-watch."
    app._page_header(
        root,
        "Local Knowledge (RAG)",
        hsub,
        actions=[("Refresh", lambda: app.show_page("Knowledge"))],
    )

    bar = ctk.CTkFrame(root)
    bar.grid(row=1, column=0, sticky="ew", pady=4)

    def do_index_file() -> None:
        path = filedialog.askopenfilename(
            title="Index document",
            filetypes=[
                ("Documents", "*.pdf;*.md;*.txt;*.py;*.json;*.csv"),
                ("All", "*.*"),
            ],
        )
        if not path:
            return
        r = rag.index_file(path)
        if r.get("ok"):
            local_embeddings.index_embeddings_for_all()
            messagebox.showinfo(
                "Indexed", f"{r.get('title')}\n{r.get('chunks')} chunks", parent=app
            )
            refresh()
        else:
            messagebox.showerror("Index failed", str(r.get("error")), parent=app)

    def do_index_folder() -> None:
        path = filedialog.askdirectory(title="Index folder")
        if not path:
            return
        r = rag.index_folder(path)
        local_embeddings.index_embeddings_for_all()
        messagebox.showinfo(
            "Folder index",
            f"Indexed {r.get('indexed')} files · errors {r.get('errors')}",
            parent=app,
        )
        refresh()

    def do_watch() -> None:
        path = filedialog.askdirectory(title="Watch folder (auto-index)")
        if not path:
            return
        r = file_watcher.add_watch(path)
        messagebox.showinfo("Watch", str(r), parent=app)
        refresh_watch()

    def do_search() -> None:
        q = search_e.get().strip()
        if not q:
            return
        hits = local_embeddings.hybrid_search(q, limit=12)
        if not hits:
            hits = rag.search(q, limit=12)
        result_box.delete("1.0", "end")
        if not hits:
            result_box.insert("1.0", "No matches.")
            return
        lines = []
        for i, h in enumerate(hits, 1):
            sc = h.get("emb_score")
            lines.append(f"[{i}] {h.get('title')} — {h.get('path')}" + (f" score={sc}" if sc is not None else ""))
            lines.append((h.get("content") or "")[:500])
            lines.append("")
        result_box.insert("1.0", "\n".join(lines))

    ctk.CTkButton(bar, text="Index file…", command=do_index_file).pack(side="left", padx=4, pady=6)
    ctk.CTkButton(bar, text="Index folder…", command=do_index_folder).pack(
        side="left", padx=4, pady=6
    )
    ctk.CTkButton(bar, text="Watch folder…", command=do_watch).pack(side="left", padx=4, pady=6)
    ctk.CTkButton(
        bar,
        text="Rebuild embeddings",
        width=140,
        command=lambda: (
            messagebox.showinfo("Embeddings", str(local_embeddings.index_embeddings_for_all()), parent=app)
        ),
    ).pack(side="left", padx=4)
    search_e = ctk.CTkEntry(bar, placeholder_text="Search knowledge…", width=240)
    search_e.pack(side="left", padx=8, pady=6)
    ctk.CTkButton(bar, text="Search", width=80, command=do_search).pack(side="left", padx=2)
    ctk.CTkButton(
        bar,
        text="Clear all",
        width=80,
        fg_color="#a33",
        command=lambda: (rag.clear_all(), refresh()),
    ).pack(side="left", padx=8)

    body = ctk.CTkFrame(root)
    body.grid(row=2, column=0, sticky="nsew", pady=8)
    body.grid_columnconfigure(0, weight=1)
    body.grid_columnconfigure(1, weight=1)
    body.grid_rowconfigure(1, weight=1)

    ctk.CTkLabel(body, text="Indexed documents", font=ctk.CTkFont(weight="bold")).grid(
        row=0, column=0, sticky="w", padx=6
    )
    ctk.CTkLabel(body, text="Search results", font=ctk.CTkFont(weight="bold")).grid(
        row=0, column=1, sticky="w", padx=6
    )
    docs_box = ctk.CTkScrollableFrame(body)
    docs_box.grid(row=1, column=0, sticky="nsew", padx=6, pady=4)
    result_box = ctk.CTkTextbox(body, wrap="word")
    result_box.grid(row=1, column=1, sticky="nsew", padx=6, pady=4)

    watch_lbl = ctk.CTkLabel(root, text="", text_color=_HC_MUTED, anchor="w", justify="left")
    watch_lbl.grid(row=4, column=0, sticky="w", pady=4)

    def refresh_watch() -> None:
        ws = file_watcher.load_watches()
        if not ws:
            watch_lbl.configure(text="Watches: (none) — use Watch folder… for auto-index")
        else:
            lines = [f"Watches ({'running' if file_watcher.is_running() else 'idle'}):"]
            for w in ws:
                lines.append(f"  · {w.get('path')}  indexed+={w.get('indexed')}  last={w.get('last_scan') or '—'}")
            watch_lbl.configure(text="\n".join(lines))

    def refresh() -> None:
        for w in docs_box.winfo_children():
            w.destroy()
        docs = rag.list_documents()
        if not docs:
            ctk.CTkLabel(docs_box, text="No documents yet. Index a file or folder.").pack(
                anchor="w", padx=6, pady=8
            )
        for d in docs:
            row = ctk.CTkFrame(docs_box)
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(
                row,
                text=f"{d.get('title')}  ·  {d.get('chunk_count')} chunks\n{d.get('path')}",
                anchor="w",
                justify="left",
                wraplength=340,
            ).pack(side="left", fill="x", expand=True, padx=4)
            ctk.CTkButton(
                row,
                text="Delete",
                width=60,
                command=lambda i=d["id"]: (rag.delete_document(i), refresh()),
            ).pack(side="right", padx=4)
        refresh_watch()

    refresh()
