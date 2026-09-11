"""Plugins / Connectors workspace — MCP servers + OpenAPI tool endpoints.

List / add / edit / enable / disable / test. Persists via plugins_registry
(data/plugins.json). Soft-degrades when servers are down.
"""

from __future__ import annotations

import json
import threading
import tkinter.messagebox as messagebox
from typing import TYPE_CHECKING, Any

import customtkinter as ctk

from app.ui.themes import UI as _THEME_UI

_HC_MUTED = _THEME_UI["muted"]
_HC_LABEL = _THEME_UI["label"]

if TYPE_CHECKING:
    from app.ui.app_window import AppWindow


def page_plugins(app: "AppWindow") -> None:
    from app.core.services.integrations import openapi_tools as oa
    from app.core.services.integrations import plugins_registry as pr
    from app.ui.themes import style_chrome_button, style_entry

    root = ctk.CTkFrame(app.content, fg_color="transparent")
    root.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
    root.grid_columnconfigure(0, weight=0, minsize=300)
    root.grid_columnconfigure(1, weight=1)
    root.grid_rowconfigure(1, weight=1)

    app._page_header(
        root,
        "Plugins / Connectors",
        "Add MCP servers and OpenAPI tool endpoints. Enabled tools appear for native "
        "tool_calls and the chat harness. Soft-degrades if a server is down.",
    )

    left = ctk.CTkFrame(
        root,
        fg_color=_THEME_UI.get("top_bg", ("#f3f4f6", "#161a22")),
        corner_radius=10,
        border_width=1,
        border_color=_THEME_UI.get("top_border", ("#6b7280", "#4b5563")),
        width=320,
    )
    left.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
    left.grid_propagate(False)
    left.grid_columnconfigure(0, weight=1)
    left.grid_rowconfigure(3, weight=1)

    kind_var = ctk.StringVar(value="MCP")
    kind_row = ctk.CTkFrame(left, fg_color="transparent")
    kind_row.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
    ctk.CTkSegmentedButton(
        kind_row,
        values=["MCP", "OpenAPI"],
        variable=kind_var,
        command=lambda _v=None: _refresh_list(),
    ).pack(fill="x")

    search_var = ctk.StringVar(value="")
    search_row = ctk.CTkFrame(left, fg_color="transparent")
    search_row.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
    search_row.grid_columnconfigure(0, weight=1)
    search_entry = ctk.CTkEntry(
        search_row,
        textvariable=search_var,
        placeholder_text="Search connectors…",
        **style_entry(),
    )
    search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 4))

    btn_row = ctk.CTkFrame(left, fg_color="transparent")
    btn_row.grid(row=2, column=0, sticky="ew", padx=8, pady=4)

    list_scroll = ctk.CTkScrollableFrame(left, fg_color="transparent")
    list_scroll.grid(row=3, column=0, sticky="nsew", padx=4, pady=(0, 8))

    right = ctk.CTkFrame(
        root,
        fg_color=_THEME_UI.get("top_bg", ("#f3f4f6", "#161a22")),
        corner_radius=10,
        border_width=1,
        border_color=_THEME_UI.get("top_border", ("#6b7280", "#4b5563")),
    )
    right.grid(row=1, column=1, sticky="nsew")
    right.grid_columnconfigure(0, weight=1)
    right.grid_rowconfigure(2, weight=1)

    title_l = ctk.CTkLabel(
        right,
        text="Select or add a connector",
        font=ctk.CTkFont(size=16, weight="bold"),
        text_color=_HC_LABEL,
        anchor="w",
    )
    title_l.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))

    toolbar = ctk.CTkFrame(right, fg_color="transparent")
    toolbar.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 6))

    form = ctk.CTkScrollableFrame(right, fg_color="transparent")
    form.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 4))
    form.grid_columnconfigure(1, weight=1)

    status_l = ctk.CTkLabel(right, text="", text_color=_HC_MUTED, anchor="w")
    status_l.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 10))

    state: dict[str, Any] = {"kind": "MCP", "id": None, "widgets": {}}

    def _set_status(msg: str, *, ok: bool = True) -> None:
        color = _THEME_UI.get("success", _HC_LABEL) if ok else ("tomato", "#f87171")
        status_l.configure(text=msg, text_color=color)

    def _clear_form() -> None:
        for child in form.winfo_children():
            child.destroy()
        state["widgets"] = {}

    def _add_field(row: int, label: str, key: str, *, placeholder: str = "", height: int = 32, multiline: bool = False) -> Any:
        ctk.CTkLabel(form, text=label, text_color=_HC_MUTED, anchor="w", width=110).grid(
            row=row, column=0, sticky="nw", padx=(4, 8), pady=4
        )
        if multiline:
            w = ctk.CTkTextbox(form, height=height, wrap="word")
            w.grid(row=row, column=1, sticky="ew", padx=(0, 8), pady=4)
        else:
            var = ctk.StringVar(value="")
            w = ctk.CTkEntry(form, textvariable=var, placeholder_text=placeholder, height=height, **style_entry())
            w.grid(row=row, column=1, sticky="ew", padx=(0, 8), pady=4)
            state["widgets"][key + "_var"] = var
        state["widgets"][key] = w
        return w

    def _get_entry(key: str) -> str:
        var = state["widgets"].get(key + "_var")
        if var is not None:
            return str(var.get() or "")
        w = state["widgets"].get(key)
        if w is None:
            return ""
        try:
            return w.get("1.0", "end").strip()
        except Exception:  # noqa: BLE001
            try:
                return str(w.get() or "")
            except Exception:  # noqa: BLE001
                return ""

    def _set_entry(key: str, value: str) -> None:
        var = state["widgets"].get(key + "_var")
        if var is not None:
            var.set(value or "")
            return
        w = state["widgets"].get(key)
        if w is None:
            return
        try:
            w.delete("1.0", "end")
            w.insert("1.0", value or "")
        except Exception:  # noqa: BLE001
            pass

    def _build_mcp_form(item: dict[str, Any] | None) -> None:
        _clear_form()
        title_l.configure(text=(item or {}).get("name") or "New MCP server")
        _add_field(0, "Name", "name", placeholder="filesystem")
        _add_field(1, "Command", "command", placeholder="npx")
        _add_field(2, "Args (JSON)", "args", placeholder='["-y","@modelcontextprotocol/server-filesystem","C:/"]')
        _add_field(3, "Env (JSON)", "env", placeholder='{"KEY":"value"}', height=80, multiline=True)
        _add_field(4, "URL (optional)", "url", placeholder="HTTP MCP not yet supported")
        en_var = ctk.BooleanVar(master=app, value=True if not item else bool(item.get("enabled", True)))
        state["widgets"]["enabled_var"] = en_var
        ctk.CTkCheckBox(form, text="Enabled", variable=en_var).grid(
            row=5, column=1, sticky="w", padx=(0, 8), pady=6
        )
        tools_box = ctk.CTkTextbox(form, height=140, wrap="word")
        tools_box.grid(row=6, column=0, columnspan=2, sticky="ew", padx=4, pady=6)
        state["widgets"]["tools_box"] = tools_box
        if item:
            _set_entry("name", item.get("name") or "")
            _set_entry("command", item.get("command") or "")
            _set_entry("args", json.dumps(item.get("args") or []))
            _set_entry("env", json.dumps(item.get("env") or {}, indent=2))
            _set_entry("url", item.get("url") or "")
            tools = item.get("discovered_tools") or []
            preview = "\n".join(
                f"- {t.get('name')}: {(t.get('description') or '')[:80]}"
                for t in tools
                if isinstance(t, dict)
            ) or "(no tools discovered yet — click Test)"
            if item.get("last_error"):
                preview = f"Last error: {item['last_error']}\n\n" + preview
            tools_box.insert("1.0", preview)
        else:
            tools_box.insert("1.0", "(save + Test to discover tools)")

    def _build_openapi_form(item: dict[str, Any] | None) -> None:
        _clear_form()
        title_l.configure(text=(item or {}).get("name") or "New OpenAPI server")
        _add_field(0, "Name", "name", placeholder="Petstore")
        _add_field(1, "Spec URL", "spec_url", placeholder="https://…/openapi.json")
        _add_field(2, "Base URL", "base_url", placeholder="https://api.example.com")
        _add_field(3, "Auth type", "auth_type", placeholder="none | bearer | api_key")
        _add_field(4, "Auth token", "auth_token", placeholder="optional")
        _add_field(5, "Headers (JSON)", "headers", placeholder="{}", height=70, multiline=True)
        en_var = ctk.BooleanVar(master=app, value=True if not item else bool(item.get("enabled", True)))
        state["widgets"]["enabled_var"] = en_var
        ctk.CTkCheckBox(form, text="Enabled", variable=en_var).grid(
            row=6, column=1, sticky="w", padx=(0, 8), pady=6
        )
        tools_box = ctk.CTkTextbox(form, height=160, wrap="word")
        tools_box.grid(row=7, column=0, columnspan=2, sticky="ew", padx=4, pady=6)
        state["widgets"]["tools_box"] = tools_box
        if item:
            _set_entry("name", item.get("name") or "")
            _set_entry("spec_url", item.get("spec_url") or "")
            _set_entry("base_url", item.get("base_url") or "")
            _set_entry("auth_type", item.get("auth_type") or "none")
            _set_entry("auth_token", item.get("auth_token") or "")
            _set_entry("headers", json.dumps(item.get("headers") or {}, indent=2))
            tools = item.get("tools") or []
            preview = "\n".join(
                f"- [{t.get('method')}] {t.get('name')} {t.get('path')}"
                for t in tools
                if isinstance(t, dict)
            ) or "(no tools — Import or Test)"
            if item.get("last_error"):
                preview = f"Last error: {item['last_error']}\n\n" + preview
            tools_box.insert("1.0", preview)
        else:
            tools_box.insert("1.0", "Paste Spec URL and click Import OpenAPI (or Save + Test).")

    def _select(kind: str, item: dict[str, Any] | None) -> None:
        state["kind"] = kind
        state["id"] = (item or {}).get("id")
        if kind == "MCP":
            _build_mcp_form(item)
        else:
            _build_openapi_form(item)
        _set_status("Editing " + ((item or {}).get("name") or "new connector"))

    def _refresh_list() -> None:
        for child in list_scroll.winfo_children():
            child.destroy()
        kind = kind_var.get()
        q = search_var.get()
        items = pr.list_mcp_servers(query=q) if kind == "MCP" else pr.list_openapi_servers(query=q)
        if not items:
            ctk.CTkLabel(
                list_scroll,
                text="No connectors yet.\nClick + Add.",
                text_color=_HC_MUTED,
                justify="left",
            ).pack(anchor="w", padx=8, pady=12)
            return
        for item in items:
            row = ctk.CTkFrame(list_scroll, fg_color="transparent")
            row.pack(fill="x", padx=4, pady=2)
            en = "●" if item.get("enabled") else "○"
            ntools = len(item.get("discovered_tools") or item.get("tools") or [])
            label = f"{en} {item.get('name')}  ({ntools})"
            ctk.CTkButton(
                row,
                text=label,
                anchor="w",
                fg_color="transparent",
                text_color=_HC_LABEL,
                hover_color=_THEME_UI.get("top_border", ("#e5e7eb", "#374151")),
                command=lambda it=item, k=kind: _select(k, it),
            ).pack(fill="x", side="left", expand=True)

    def _new() -> None:
        kind = kind_var.get()
        _select(kind, None)
        _set_status(f"New {kind} connector — fill fields and Save")

    def _parse_json_field(raw: str, default: Any) -> Any:
        raw = (raw or "").strip()
        if not raw:
            return default
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}") from e

    def _save() -> None:
        kind = state["kind"]
        name = _get_entry("name").strip()
        if not name:
            _set_status("Name is required", ok=False)
            return
        try:
            enabled = bool(state["widgets"].get("enabled_var").get())  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            enabled = True
        try:
            if kind == "MCP":
                args = _parse_json_field(_get_entry("args"), [])
                env = _parse_json_field(_get_entry("env"), {})
                if not isinstance(args, list):
                    raise ValueError("Args must be a JSON array")
                if not isinstance(env, dict):
                    raise ValueError("Env must be a JSON object")
                fields = {
                    "name": name,
                    "command": _get_entry("command").strip(),
                    "args": args,
                    "env": {str(k): str(v) for k, v in env.items()},
                    "url": _get_entry("url").strip(),
                    "enabled": enabled,
                }
                if state["id"]:
                    item = pr.update_mcp_server(state["id"], **fields)
                else:
                    item = pr.add_mcp_server(**fields)
            else:
                headers = _parse_json_field(_get_entry("headers"), {})
                if not isinstance(headers, dict):
                    raise ValueError("Headers must be a JSON object")
                fields = {
                    "name": name,
                    "spec_url": _get_entry("spec_url").strip(),
                    "base_url": _get_entry("base_url").strip(),
                    "auth_type": _get_entry("auth_type").strip() or "none",
                    "auth_token": _get_entry("auth_token").strip(),
                    "headers": {str(k): str(v) for k, v in headers.items()},
                    "enabled": enabled,
                }
                if state["id"]:
                    item = pr.update_openapi_server(state["id"], **fields)
                else:
                    item = pr.add_openapi_server(**fields)
        except ValueError as e:
            _set_status(str(e), ok=False)
            return
        except Exception as e:  # noqa: BLE001
            _set_status(f"Save failed: {e}", ok=False)
            return
        if not item:
            _set_status("Save failed", ok=False)
            return
        state["id"] = item["id"]
        _refresh_list()
        _select(kind, item)
        _set_status(f"Saved {item['name']} → data/plugins.json")

    def _delete() -> None:
        if not state["id"]:
            _set_status("Nothing selected", ok=False)
            return
        if not messagebox.askyesno("Delete connector", "Remove this connector?"):
            return
        kind = state["kind"]
        ok = (
            pr.delete_mcp_server(state["id"])
            if kind == "MCP"
            else pr.delete_openapi_server(state["id"])
        )
        if ok:
            state["id"] = None
            _refresh_list()
            _select(kind, None)
            _set_status("Deleted")
        else:
            _set_status("Delete failed", ok=False)

    def _toggle() -> None:
        if not state["id"]:
            _set_status("Nothing selected", ok=False)
            return
        kind = state["kind"]
        cur = pr.get_mcp(state["id"]) if kind == "MCP" else pr.get_openapi(state["id"])
        if not cur:
            _set_status("Not found", ok=False)
            return
        new_en = not bool(cur.get("enabled"))
        if kind == "MCP":
            item = pr.set_mcp_enabled(state["id"], new_en)
        else:
            item = pr.set_openapi_enabled(state["id"], new_en)
        _refresh_list()
        if item:
            _select(kind, item)
            _set_status(("Enabled" if new_en else "Disabled") + f" {item['name']}")

    def _run_test() -> None:
        if not state["id"]:
            _set_status("Save the connector first", ok=False)
            return
        kind = state["kind"]
        sid = state["id"]
        _set_status("Testing…")

        def work() -> None:
            try:
                if kind == "MCP":
                    res = pr.test_mcp_server(sid)
                else:
                    res = oa.test_openapi_server(sid)
            except Exception as e:  # noqa: BLE001
                res = {"ok": False, "error": str(e), "soft_degrade": True}

            def done() -> None:
                item = pr.get_mcp(sid) if kind == "MCP" else pr.get_openapi(sid)
                _refresh_list()
                if item:
                    _select(kind, item)
                if res.get("ok"):
                    n = res.get("count") or res.get("tool_count") or len(res.get("tools") or [])
                    _set_status(f"OK — {n} tools discovered")
                else:
                    _set_status(
                        f"Soft-degrade: {res.get('error') or 'failed'}",
                        ok=False,
                    )

            try:
                app.after(0, done)
            except Exception:  # noqa: BLE001
                done()

        threading.Thread(target=work, daemon=True).start()

    def _import_openapi() -> None:
        url = _get_entry("spec_url").strip() if state["kind"] == "OpenAPI" else ""
        if not url:
            # prompt via simple dialog
            dlg = ctk.CTkInputDialog(text="OpenAPI / swagger JSON URL:", title="Import OpenAPI")
            url = (dlg.get_input() or "").strip()
        if not url:
            _set_status("No URL", ok=False)
            return
        name = _get_entry("name").strip() if state["kind"] == "OpenAPI" else ""
        _set_status("Fetching OpenAPI…")

        def work() -> None:
            try:
                res = oa.import_openapi_from_url(url, name=name or "")
            except Exception as e:  # noqa: BLE001
                res = {"ok": False, "error": str(e)}

            def done() -> None:
                if not res.get("ok"):
                    _set_status(f"Import failed: {res.get('error')}", ok=False)
                    return
                kind_var.set("OpenAPI")
                item = res.get("server")
                _refresh_list()
                if item:
                    _select("OpenAPI", item)
                _set_status(f"Imported {res.get('tool_count', 0)} GET/POST tools")

            try:
                app.after(0, done)
            except Exception:  # noqa: BLE001
                done()

        threading.Thread(target=work, daemon=True).start()

    ctk.CTkButton(btn_row, text="+ Add", width=70, command=_new, **style_chrome_button(primary=True)).pack(
        side="left", padx=(0, 4)
    )
    ctk.CTkButton(btn_row, text="Refresh", width=70, command=_refresh_list, **style_chrome_button()).pack(
        side="left"
    )

    ctk.CTkButton(toolbar, text="Save", width=80, command=_save, **style_chrome_button(primary=True)).pack(
        side="left", padx=(0, 4)
    )
    ctk.CTkButton(toolbar, text="Enable/Disable", width=110, command=_toggle, **style_chrome_button()).pack(
        side="left", padx=(0, 4)
    )
    ctk.CTkButton(toolbar, text="Test", width=70, command=_run_test, **style_chrome_button()).pack(
        side="left", padx=(0, 4)
    )
    ctk.CTkButton(
        toolbar, text="Import OpenAPI", width=120, command=_import_openapi, **style_chrome_button()
    ).pack(side="left", padx=(0, 4))
    ctk.CTkButton(toolbar, text="Delete", width=70, command=_delete, **style_chrome_button()).pack(
        side="left", padx=(0, 4)
    )

    search_var.trace_add("write", lambda *_a: _refresh_list())
    _refresh_list()
    _select("MCP", None)
