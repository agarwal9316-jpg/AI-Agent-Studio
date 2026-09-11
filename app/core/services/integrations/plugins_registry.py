"""Plugins / Connectors registry — MCP servers + OpenAPI tool servers.

First-class store for Next-10 #1. Persists under ``data/plugins.json``.
Enabled MCP entries are mirrored into ``data/mcp.json`` so the existing
``McpHub`` keeps working. OpenAPI servers are discovered/executed via
``openapi_tools``. Soft-degrades when a server is down.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.paths import app_root, data_dir

PLUGINS_VERSION = 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def plugins_path() -> Path:
    return data_dir() / "plugins.json"


def _empty() -> dict[str, Any]:
    return {
        "version": PLUGINS_VERSION,
        "mcp_servers": [],
        "openapi_servers": [],
        "updated_at": _now(),
    }


def _safe_id(raw: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "", (raw or "").strip())[:64]


def _safe_name(raw: str, fallback: str = "untitled") -> str:
    s = (raw or "").strip() or fallback
    return s[:80]


def load_plugins() -> dict[str, Any]:
    path = plugins_path()
    if not path.is_file():
        return _empty()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty()
    if not isinstance(data, dict):
        return _empty()
    out = _empty()
    out["version"] = int(data.get("version") or PLUGINS_VERSION)
    mcp = data.get("mcp_servers")
    oa = data.get("openapi_servers")
    if isinstance(mcp, list):
        out["mcp_servers"] = [_normalize_mcp(x) for x in mcp if isinstance(x, dict)]
    if isinstance(oa, list):
        out["openapi_servers"] = [_normalize_openapi(x) for x in oa if isinstance(x, dict)]
    out["updated_at"] = str(data.get("updated_at") or out["updated_at"])
    return out


def save_plugins(data: dict[str, Any]) -> Path:
    path = plugins_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": PLUGINS_VERSION,
        "mcp_servers": [
            _normalize_mcp(x) for x in (data.get("mcp_servers") or []) if isinstance(x, dict)
        ],
        "openapi_servers": [
            _normalize_openapi(x)
            for x in (data.get("openapi_servers") or [])
            if isinstance(x, dict)
        ],
        "updated_at": _now(),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    # Keep McpHub config in sync for enabled stdio MCP servers
    try:
        sync_mcp_json(payload)
    except Exception:  # noqa: BLE001
        pass
    return path


def _normalize_mcp(item: dict[str, Any]) -> dict[str, Any]:
    sid = _safe_id(str(item.get("id") or "")) or str(uuid.uuid4())
    name = _safe_name(str(item.get("name") or sid), sid)
    env = item.get("env") if isinstance(item.get("env"), dict) else {}
    args = item.get("args") if isinstance(item.get("args"), list) else []
    tools = item.get("discovered_tools") if isinstance(item.get("discovered_tools"), list) else []
    return {
        "id": sid,
        "name": name,
        "enabled": bool(item.get("enabled", True)),
        "transport": str(item.get("transport") or ("url" if item.get("url") else "stdio")),
        "command": str(item.get("command") or ""),
        "args": [str(a) for a in args],
        "env": {str(k): str(v) for k, v in env.items()},
        "url": str(item.get("url") or ""),
        "last_test": str(item.get("last_test") or ""),
        "last_error": str(item.get("last_error") or ""),
        "discovered_tools": tools,
        "created_at": str(item.get("created_at") or _now()),
        "updated_at": str(item.get("updated_at") or _now()),
    }


def _normalize_openapi(item: dict[str, Any]) -> dict[str, Any]:
    sid = _safe_id(str(item.get("id") or "")) or str(uuid.uuid4())
    name = _safe_name(str(item.get("name") or sid), sid)
    headers = item.get("headers") if isinstance(item.get("headers"), dict) else {}
    tools = item.get("tools") if isinstance(item.get("tools"), list) else []
    return {
        "id": sid,
        "name": name,
        "enabled": bool(item.get("enabled", True)),
        "spec_url": str(item.get("spec_url") or ""),
        "base_url": str(item.get("base_url") or ""),
        "headers": {str(k): str(v) for k, v in headers.items()},
        "auth_type": str(item.get("auth_type") or "none"),
        "auth_token": str(item.get("auth_token") or ""),
        "last_test": str(item.get("last_test") or ""),
        "last_error": str(item.get("last_error") or ""),
        "tools": tools,
        "created_at": str(item.get("created_at") or _now()),
        "updated_at": str(item.get("updated_at") or _now()),
    }


def list_mcp_servers(*, query: str = "") -> list[dict[str, Any]]:
    items = load_plugins()["mcp_servers"]
    q = (query or "").strip().lower()
    if not q:
        return list(items)
    return [x for x in items if q in (x.get("name") or "").lower() or q in (x.get("id") or "").lower()]


def list_openapi_servers(*, query: str = "") -> list[dict[str, Any]]:
    items = load_plugins()["openapi_servers"]
    q = (query or "").strip().lower()
    if not q:
        return list(items)
    return [
        x
        for x in items
        if q in (x.get("name") or "").lower()
        or q in (x.get("spec_url") or "").lower()
        or q in (x.get("id") or "").lower()
    ]


def get_mcp(server_id: str) -> dict[str, Any] | None:
    sid = _safe_id(server_id)
    for x in load_plugins()["mcp_servers"]:
        if x["id"] == sid or x["name"] == server_id:
            return x
    return None


def get_openapi(server_id: str) -> dict[str, Any] | None:
    sid = _safe_id(server_id)
    for x in load_plugins()["openapi_servers"]:
        if x["id"] == sid or x["name"] == server_id:
            return x
    return None


def add_mcp_server(
    *,
    name: str,
    command: str = "",
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
    url: str = "",
    enabled: bool = True,
    transport: str = "",
) -> dict[str, Any]:
    data = load_plugins()
    item = _normalize_mcp(
        {
            "id": str(uuid.uuid4()),
            "name": name,
            "command": command,
            "args": list(args or []),
            "env": dict(env or {}),
            "url": url,
            "enabled": enabled,
            "transport": transport or ("url" if url else "stdio"),
            "created_at": _now(),
            "updated_at": _now(),
        }
    )
    # Unique name among MCP entries
    names = {x["name"] for x in data["mcp_servers"]}
    if item["name"] in names:
        item["name"] = f"{item['name']}-{item['id'][:6]}"
    data["mcp_servers"].append(item)
    save_plugins(data)
    _reload_mcp_hub()
    return item


def update_mcp_server(server_id: str, **fields: Any) -> dict[str, Any] | None:
    data = load_plugins()
    sid = _safe_id(server_id)
    for i, x in enumerate(data["mcp_servers"]):
        if x["id"] != sid and x["name"] != server_id:
            continue
        merged = {**x, **fields, "id": x["id"], "updated_at": _now()}
        data["mcp_servers"][i] = _normalize_mcp(merged)
        save_plugins(data)
        _reload_mcp_hub()
        return data["mcp_servers"][i]
    return None


def set_mcp_enabled(server_id: str, enabled: bool) -> dict[str, Any] | None:
    return update_mcp_server(server_id, enabled=bool(enabled))


def delete_mcp_server(server_id: str) -> bool:
    data = load_plugins()
    sid = _safe_id(server_id)
    before = len(data["mcp_servers"])
    data["mcp_servers"] = [
        x for x in data["mcp_servers"] if x["id"] != sid and x["name"] != server_id
    ]
    if len(data["mcp_servers"]) == before:
        return False
    save_plugins(data)
    _reload_mcp_hub()
    return True


def add_openapi_server(
    *,
    name: str,
    spec_url: str,
    base_url: str = "",
    headers: dict[str, str] | None = None,
    auth_type: str = "none",
    auth_token: str = "",
    enabled: bool = True,
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    data = load_plugins()
    item = _normalize_openapi(
        {
            "id": str(uuid.uuid4()),
            "name": name,
            "spec_url": spec_url,
            "base_url": base_url,
            "headers": dict(headers or {}),
            "auth_type": auth_type,
            "auth_token": auth_token,
            "enabled": enabled,
            "tools": list(tools or []),
            "created_at": _now(),
            "updated_at": _now(),
        }
    )
    names = {x["name"] for x in data["openapi_servers"]}
    if item["name"] in names:
        item["name"] = f"{item['name']}-{item['id'][:6]}"
    data["openapi_servers"].append(item)
    save_plugins(data)
    return item


def update_openapi_server(server_id: str, **fields: Any) -> dict[str, Any] | None:
    data = load_plugins()
    sid = _safe_id(server_id)
    for i, x in enumerate(data["openapi_servers"]):
        if x["id"] != sid and x["name"] != server_id:
            continue
        merged = {**x, **fields, "id": x["id"], "updated_at": _now()}
        data["openapi_servers"][i] = _normalize_openapi(merged)
        save_plugins(data)
        return data["openapi_servers"][i]
    return None


def set_openapi_enabled(server_id: str, enabled: bool) -> dict[str, Any] | None:
    return update_openapi_server(server_id, enabled=bool(enabled))


def delete_openapi_server(server_id: str) -> bool:
    data = load_plugins()
    sid = _safe_id(server_id)
    before = len(data["openapi_servers"])
    data["openapi_servers"] = [
        x for x in data["openapi_servers"] if x["id"] != sid and x["name"] != server_id
    ]
    if len(data["openapi_servers"]) == before:
        return False
    save_plugins(data)
    return True


def sync_mcp_json(data: dict[str, Any] | None = None) -> Path:
    """Mirror enabled stdio MCP plugins into data/mcp.json for McpHub."""
    data = data or load_plugins()
    mcp_path = app_root() / "data" / "mcp.json"
    mcp_path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {"mcpServers": {}}
    if mcp_path.is_file():
        try:
            existing = json.loads(mcp_path.read_text(encoding="utf-8"))
            if not isinstance(existing, dict):
                existing = {"mcpServers": {}}
        except (OSError, json.JSONDecodeError):
            existing = {"mcpServers": {}}
    block = existing.get("mcpServers")
    if not isinstance(block, dict):
        block = {}

    # Drop previous plugin-managed keys (marked) then re-add enabled ones
    managed_keys = [k for k, v in block.items() if isinstance(v, dict) and v.get("_from_plugins")]
    for k in managed_keys:
        block.pop(k, None)

    for item in data.get("mcp_servers") or []:
        if not item.get("enabled"):
            continue
        if item.get("url") and not item.get("command"):
            # HTTP MCP not in McpHub yet — skip mirror
            continue
        if not item.get("command"):
            continue
        key = _safe_id(item.get("name") or item.get("id") or "mcp") or item["id"]
        block[key] = {
            "command": item.get("command"),
            "args": list(item.get("args") or []),
            "env": dict(item.get("env") or {}),
            "_from_plugins": True,
            "_plugin_id": item.get("id"),
        }
    existing["mcpServers"] = block
    mcp_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    return mcp_path


def _reload_mcp_hub() -> None:
    try:
        from app.core.services.integrations.mcp_client import get_mcp_hub

        hub = get_mcp_hub()
        hub.close_all()
    except Exception:  # noqa: BLE001
        pass


def test_mcp_server(server_id: str, *, timeout: float = 8.0) -> dict[str, Any]:
    """Try starting an MCP stdio session, list tools; soft-degrade on failure."""
    item = get_mcp(server_id)
    if not item:
        return {"ok": False, "error": f"Unknown MCP server: {server_id}"}
    if item.get("url") and not item.get("command"):
        err = "HTTP MCP transport not yet supported — use stdio command/args"
        update_mcp_server(server_id, last_test=_now(), last_error=err, discovered_tools=[])
        return {"ok": False, "error": err, "soft_degrade": True}
    cmd = (item.get("command") or "").strip()
    if not cmd:
        err = "No command configured"
        update_mcp_server(server_id, last_test=_now(), last_error=err)
        return {"ok": False, "error": err}

    from app.core.services.integrations.mcp_client import McpStdioSession

    sess = McpStdioSession(
        name=item["name"],
        command=cmd,
        args=list(item.get("args") or []),
        env=dict(item.get("env") or {}),
    )
    try:
        ok = sess.start(timeout=timeout)
        if not ok:
            err = sess.last_error or "initialize failed"
            update_mcp_server(server_id, last_test=_now(), last_error=err, discovered_tools=[])
            return {"ok": False, "error": err, "soft_degrade": True}
        tools = [
            {
                "name": t.get("name"),
                "description": t.get("description") or "",
                "inputSchema": t.get("inputSchema") or {},
            }
            for t in (sess.tools or [])
        ]
        update_mcp_server(
            server_id,
            last_test=_now(),
            last_error="",
            discovered_tools=tools,
        )
        return {"ok": True, "tools": tools, "count": len(tools)}
    except Exception as e:  # noqa: BLE001
        err = str(e)
        update_mcp_server(server_id, last_test=_now(), last_error=err, discovered_tools=[])
        return {"ok": False, "error": err, "soft_degrade": True}
    finally:
        try:
            sess.close()
        except Exception:  # noqa: BLE001
            pass


def discover_enabled_mcp_tools() -> list[dict[str, Any]]:
    """Return cached discovered tools for enabled MCP plugins (no spawn)."""
    out: list[dict[str, Any]] = []
    for s in list_mcp_servers():
        if not s.get("enabled"):
            continue
        for t in s.get("discovered_tools") or []:
            if not isinstance(t, dict) or not t.get("name"):
                continue
            out.append(
                {
                    "server": s["name"],
                    "server_id": s["id"],
                    "name": t.get("name"),
                    "qualified": f"{s['name']}.{t.get('name')}",
                    "description": t.get("description") or "",
                    "inputSchema": t.get("inputSchema") or {},
                    "source": "plugins",
                }
            )
    return out


def catalog_prompt() -> str:
    """Short system-prompt add-on listing enabled connectors."""
    lines = [
        "### Plugins / Connectors",
        "MCP stdio servers + OpenAPI HTTP tools (Settings/Workspace → Plugins).",
        "",
    ]
    mcp = [s for s in list_mcp_servers() if s.get("enabled")]
    oa = [s for s in list_openapi_servers() if s.get("enabled")]
    if not mcp and not oa:
        lines.append("No connectors enabled. Add them under **Plugins**.")
        return "\n".join(lines)
    if mcp:
        lines.append("**MCP servers:**")
        for s in mcp:
            ntools = len(s.get("discovered_tools") or [])
            err = s.get("last_error") or ""
            status = f"{ntools} tools" if ntools else ("error: " + err if err else "enabled (not tested)")
            lines.append(f"- `{s['name']}` — {status}")
            for t in (s.get("discovered_tools") or [])[:12]:
                if isinstance(t, dict) and t.get("name"):
                    lines.append(f"  - `{s['name']}.{t['name']}` — {(t.get('description') or '')[:100]}")
        lines.append("")
        lines.append(
            "Call MCP via <<<MCP>>>\\nserver.tool\\n{json}\\n<<<END_MCP>>> or native `mcp` tool."
        )
    if oa:
        lines.append("")
        lines.append("**OpenAPI tool servers:**")
        for s in oa:
            tools = s.get("tools") or []
            lines.append(f"- `{s['name']}` — {len(tools)} HTTP tools (GET/POST)")
            for t in tools[:16]:
                if isinstance(t, dict) and t.get("name"):
                    lines.append(
                        f"  - `{s['name']}.{t['name']}` [{t.get('method', '?')}] "
                        f"{(t.get('description') or '')[:90]}"
                    )
        lines.append("")
        lines.append(
            "Call OpenAPI via <<<OPENAPI>>>\\nserver.tool\\n{json}\\n<<<END_OPENAPI>>> "
            "or native `openapi` / `oa__…` tools."
        )
    return "\n".join(lines)
