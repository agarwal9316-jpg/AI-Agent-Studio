"""Settings helpers — extracted from AppWindow."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import customtkinter as ctk
import threading
import tkinter.messagebox as messagebox

if TYPE_CHECKING:
    from app.ui.app_window import AppWindow


def test_active_llm_connection(app) -> None:
    """Task #2: Health-check active provider/model with clear next actions."""
    from app.services import providers as prov
    from app.core.services.llm.llm import LLMError, chat_completion, format_llm_error_message

    try:
        active = prov.resolve_active_llm()
    except Exception as e:  # noqa: BLE001
        messagebox.showerror("Test connection", str(e), parent=app)
        return
    key = (active.get("api_key") or "").strip()
    model = (active.get("model") or "").strip()
    base = (active.get("base_url") or "").strip()
    pid = active.get("provider_id") or "?"
    if not key:
        if str(pid) == "ollama" or "ollama" in (active.get("provider_name") or "").lower():
            messagebox.showwarning(
                "Test connection",
                "Offline · Ollama (local) needs a key field (use “ollama”) and a running daemon.\n\n"
                "Next:\n"
                "• Install from https://ollama.com if needed\n"
                "• Start Ollama (ollama serve)\n"
                "• Settings → Offline · Ollama (local) → base http://127.0.0.1:11434/v1\n"
                "• Add key labeled ollama, Fetch models, Set active",
                parent=app,
            )
            return
        messagebox.showwarning(
            "Test connection",
            f"No API key for provider “{active.get('provider_name') or pid}”.\n\n"
            "Next: Settings → select provider → Add key\n"
            "Or Home → ✦ Connect Grok (xAI key from console.x.ai)",
            parent=app,
        )
        return
    app.set_status(f"Testing {pid} / {model}…")
    try:
        out = chat_completion(
            api_key=key,
            messages=[{"role": "user", "content": "Reply with exactly: OK"}],
            model=model,
            base_url=base,
            timeout=45.0,
            max_tokens=16,
            temperature=0,
            tools=None,
            normalize_tools=False,
            _transient_retry=False,
        )
        snippet = (out or "").strip()[:120]
        messagebox.showinfo(
            "Connection OK",
            f"Provider: {active.get('provider_name')}\n"
            f"Base: {base}\n"
            f"Model: {model}\n\n"
            f"Reply: {snippet or '(empty)'}",
            parent=app,
        )
        app.set_status(f"Test OK · {model}", toast=True)
    except LLMError as e:
        err = format_llm_error_message(e)
        low = err.lower()
        actions = []
        if "402" in err or "credit" in low or "payment" in low:
            actions.append("• Add OpenRouter credits OR switch to xAI (console.x.ai key)")
        if "400" in err or "model not found" in low or "invalid" in low:
            actions.append("• Use Grok button (fixes host/model mismatch)")
            actions.append("• Or Fetch models and pick a valid id")
        if "401" in err or "403" in err or "key" in low:
            actions.append("• Paste a valid key for this provider in Settings")
        if str(pid) == "ollama" or "11434" in (base or ""):
            actions = [
                "• Offline · Ollama (local) — install from https://ollama.com if needed",
                "• Start Ollama (app or: ollama serve)",
                "• Confirm base URL http://127.0.0.1:11434/v1 and Fetch models",
            ]
        if not actions:
            actions.append("• Check base URL, model name, and network")
        messagebox.showerror(
            "Connection failed",
            f"{err}\n\nWhat to do next:\n" + "\n".join(actions),
            parent=app,
        )
        app.set_status("Test failed", toast=True)
    except Exception as e:  # noqa: BLE001
        messagebox.showerror("Test connection", str(e), parent=app)
        app.set_status(f"Test error: {e}")


def settings_test_search(app) -> None:
    """Phase 2: one-click internet/search health check."""
    app.set_status("Testing internet / search…")

    def worker() -> None:
        try:
            from app.core.services.web.web_search import connectivity_check

            res = connectivity_check()
            sample = res.get("web_search_sample") or {}
            news = res.get("web_search_news") or {}
            ok = bool(sample.get("ok") or news.get("ok"))
            lines = []
            for name in ("wikipedia", "ddg_html", "ddg_api", "brave", "google_news"):
                c = res.get(name) or {}
                if not isinstance(c, dict):
                    continue
                if c.get("ok"):
                    flag = " · CAPTCHA" if c.get("challenge") else ""
                    lines.append(f"• {name}: ok ({c.get('bytes')} bytes){flag}")
                else:
                    lines.append(f"• {name}: FAIL {c.get('error')}")
            lines.append(
                f"• sample search: {sample.get('count')} via {sample.get('backends')}"
            )
            lines.append(
                f"• news search: {news.get('count')} via {news.get('backends')}"
            )
            if sample.get("warnings") or news.get("warnings"):
                w = list(sample.get("warnings") or []) + list(news.get("warnings") or [])
                lines.append("warnings: " + "; ".join(w)[:300])
            msg = ("Search OK\n" if ok else "Search weak/failed\n") + "\n".join(lines)
        except Exception as e:  # noqa: BLE001
            ok = False
            msg = f"Connectivity test error: {e}"

        def ui() -> None:
            if ok:
                messagebox.showinfo("Internet / search", msg, parent=app)
                app.set_status(msg, toast=True)
            else:
                messagebox.showerror("Internet / search", msg, parent=app)
                app.set_status(msg, toast=True)

        app.after(0, ui)

    threading.Thread(target=worker, daemon=True).start()


def export_studio_bundle_dialog(app) -> None:
    """Export selected data/ into a portable studio bundle zip."""
    from datetime import datetime, timezone
    from tkinter import filedialog

    try:
        from app.core.services.misc import studio_bundle as sb
    except Exception as e:  # noqa: BLE001
        messagebox.showerror("Export studio bundle", str(e), parent=app)
        return

    include_secrets = messagebox.askyesno(
        "Export studio bundle",
        "Include API keys and secrets in the zip?\n\n"
        "Choose No (recommended) to redact keys.\n"
        "Choose Yes only if you will keep the zip private.",
        parent=app,
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = filedialog.asksaveasfilename(
        parent=app,
        title="Export studio bundle",
        defaultextension=".zip",
        initialfile=f"studio-bundle-{stamp}.zip",
        filetypes=[("Studio bundle zip", "*.zip"), ("All files", "*.*")],
    )
    if not path:
        return
    try:
        result = sb.export_studio_bundle(path, include_secrets=bool(include_secrets))
    except Exception as e:  # noqa: BLE001
        messagebox.showerror("Export studio bundle", str(e), parent=app)
        return
    if not result.get("ok"):
        messagebox.showerror(
            "Export studio bundle",
            str(result.get("error") or "Export failed"),
            parent=app,
        )
        return
    n = int(result.get("file_count") or 0)
    secrets = "with secrets" if include_secrets else "secrets redacted"
    app.set_status(f"Exported studio bundle ({n} files, {secrets})", toast=True)
    messagebox.showinfo(
        "Export studio bundle",
        f"Saved {n} files to:\n{result.get('path')}\n\n({secrets})",
        parent=app,
    )


def import_studio_bundle_dialog(app) -> None:
    """Import a studio bundle zip with merge or replace choice."""
    from tkinter import filedialog

    try:
        from app.core.services.misc import studio_bundle as sb
    except Exception as e:  # noqa: BLE001
        messagebox.showerror("Import studio bundle", str(e), parent=app)
        return

    path = filedialog.askopenfilename(
        parent=app,
        title="Import studio bundle",
        filetypes=[("Studio bundle zip", "*.zip"), ("All files", "*.*")],
    )
    if not path:
        return
    try:
        peek = sb.describe_bundle(path)
    except Exception:  # noqa: BLE001
        peek = {"ok": False}
    if not peek.get("ok"):
        messagebox.showerror(
            "Import studio bundle",
            str(peek.get("error") or "Not a readable studio bundle zip"),
            parent=app,
        )
        return

    do_merge = messagebox.askyesno(
        "Import studio bundle",
        "Merge into existing data?\n\n"
        "Yes = Merge (keep local items; incoming wins on same id)\n"
        "No = Replace included categories from the zip\n\n"
        f"Files in zip: {peek.get('file_count', '?')}",
        parent=app,
    )
    mode = "merge" if do_merge else "replace"
    try:
        result = sb.import_studio_bundle(path, mode=mode)
    except Exception as e:  # noqa: BLE001
        messagebox.showerror("Import studio bundle", str(e), parent=app)
        return
    if not result.get("ok"):
        messagebox.showerror(
            "Import studio bundle",
            str(result.get("error") or "Import failed"),
            parent=app,
        )
        return
    n = int(result.get("restored_count") or len(result.get("restored") or []))
    warn = result.get("warnings") or []
    extra = f"\nWarnings: {len(warn)}" if warn else ""
    app.set_status(f"Imported studio bundle ({mode}, {n} files)", toast=True)
    messagebox.showinfo(
        "Import studio bundle",
        f"Restored {n} files ({mode}).{extra}\n\n"
        "Restart or reopen pages if lists look stale.",
        parent=app,
    )
