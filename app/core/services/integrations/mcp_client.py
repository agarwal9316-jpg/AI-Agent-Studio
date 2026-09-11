"""Minimal MCP (Model Context Protocol) stdio client for chat tools."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

# Default config locations (user can also set in app Settings)
DEFAULT_MCP_CONFIG_PATHS = [
    Path.home() / ".grok" / "mcp.json",
    Path.home() / ".grok" / "mcp_servers.json",
    Path.home() / ".cursor" / "mcp.json",
    Path.home() / "AppData" / "Roaming" / "Cursor" / "User" / "globalStorage" / "mcp.json",
]


def load_mcp_config(extra_paths: list[str | Path] | None = None) -> dict[str, Any]:
    """
    Load MCP server definitions.
    Supported shapes:
      { "mcpServers": { "name": { "command": "...", "args": [], "env": {} } } }
      { "servers": { ... } }
    Also merges [mcp_servers.*] from a simple sidecar if present as JSON.
    """
    servers: dict[str, Any] = {}
    paths = list(DEFAULT_MCP_CONFIG_PATHS)
    # Project-local
    try:
        from app.paths import app_root

        paths.insert(0, app_root() / "mcp.json")
        paths.insert(0, app_root() / "data" / "mcp.json")
    except Exception:  # noqa: BLE001
        pass
    for ep in extra_paths or []:
        paths.insert(0, Path(ep))

    # Also merge enabled MCP entries from data/plugins.json (Plugins UI)
    try:
        from app.core.services.integrations import plugins_registry as _pr

        for item in _pr.list_mcp_servers():
            if not item.get("enabled"):
                continue
            name = str(item.get("name") or item.get("id") or "").strip()
            if not name:
                continue
            cfg: dict[str, Any] = {}
            if item.get("command"):
                cfg["command"] = item["command"]
                cfg["args"] = list(item.get("args") or [])
                cfg["env"] = dict(item.get("env") or {})
            if item.get("url"):
                cfg["url"] = item["url"]
            if cfg.get("command") or cfg.get("url"):
                cfg["_config_path"] = "data/plugins.json"
                cfg["_plugin_id"] = item.get("id")
                servers[name] = cfg
    except Exception:  # noqa: BLE001
        pass

    for p in paths:
        p = Path(p)
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        block = data.get("mcpServers") or data.get("servers") or data
        if isinstance(block, dict):
            for name, cfg in block.items():
                if isinstance(cfg, dict) and (cfg.get("command") or cfg.get("url")):
                    servers[name] = {**cfg, "_config_path": str(p)}
    return servers


class McpStdioSession:
    """One stdio MCP server process."""

    def __init__(self, name: str, command: str, args: list[str] | None = None, env: dict | None = None):
        self.name = name
        self.command = command
        self.args = list(args or [])
        self.env = env or {}
        self._proc: subprocess.Popen[str] | None = None
        self._id = 0
        self._lock = threading.Lock()
        self._reader: threading.Thread | None = None
        self._pending: dict[int, dict[str, Any]] = {}
        self._events = threading.Event()
        self._stdout_buffer = ""
        self.tools: list[dict[str, Any]] = []
        self.last_error: str | None = None

    def start(self, timeout: float = 20.0) -> bool:
        try:
            env = os.environ.copy()
            env.update({str(k): str(v) for k, v in self.env.items()})
            creation = 0
            if os.name == "nt":
                creation = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
            self._proc = subprocess.Popen(
                [self.command, *self.args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                bufsize=1,
                creationflags=creation if os.name == "nt" else 0,
            )
        except OSError as e:
            self.last_error = str(e)
            return False

        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

        # initialize
        init = self.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "AI-Agent-Studio", "version": "0.5.0"},
            },
            timeout=timeout,
        )
        if not init.get("ok"):
            self.last_error = init.get("error") or "initialize failed"
            self.close()
            return False

        # notifications/initialized
        self.notify("notifications/initialized", {})
        listed = self.request("tools/list", {}, timeout=timeout)
        if listed.get("ok"):
            result = listed.get("result") or {}
            self.tools = list(result.get("tools") or [])
        else:
            self.tools = []
            self.last_error = listed.get("error")
        return True

    def _read_loop(self) -> None:
        assert self._proc and self._proc.stdout
        while self._proc.poll() is None:
            line = self._proc.stdout.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "id" in msg and ("result" in msg or "error" in msg):
                with self._lock:
                    self._pending[int(msg["id"])] = msg
                self._events.set()

    def _next_id(self) -> int:
        with self._lock:
            self._id += 1
            return self._id

    def notify(self, method: str, params: dict[str, Any]) -> None:
        if not self._proc or not self._proc.stdin:
            return
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        try:
            self._proc.stdin.write(json.dumps(payload) + "\n")
            self._proc.stdin.flush()
        except OSError:
            pass

    def request(self, method: str, params: dict[str, Any], timeout: float = 60.0) -> dict[str, Any]:
        if not self._proc or not self._proc.stdin:
            return {"ok": False, "error": "Process not running"}
        rid = self._next_id()
        payload = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params}
        try:
            self._proc.stdin.write(json.dumps(payload) + "\n")
            self._proc.stdin.flush()
        except OSError as e:
            return {"ok": False, "error": str(e)}

        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                if rid in self._pending:
                    msg = self._pending.pop(rid)
                    if "error" in msg:
                        return {"ok": False, "error": msg["error"]}
                    return {"ok": True, "result": msg.get("result")}
            self._events.wait(0.1)
            self._events.clear()
        return {"ok": False, "error": f"Timeout calling {method}"}

    def call_tool(self, tool_name: str, arguments: dict[str, Any] | None = None, timeout: float = 120.0) -> dict[str, Any]:
        return self.request(
            "tools/call",
            {"name": tool_name, "arguments": arguments or {}},
            timeout=timeout,
        )

    def close(self) -> None:
        if self._proc:
            try:
                self._proc.terminate()
            except OSError:
                pass
            self._proc = None


class McpHub:
    """Lazy multi-server hub."""

    def __init__(self) -> None:
        self._sessions: dict[str, McpStdioSession] = {}
        self._configs: dict[str, Any] = {}
        self._started = False

    def reload_config(self) -> dict[str, Any]:
        self._configs = load_mcp_config()
        return self._configs

    def ensure_started(self) -> None:
        if self._started:
            return
        self.reload_config()
        for name, cfg in self._configs.items():
            # Skip docs / placeholders so chat send is never blocked by example MCP entries
            nlow = str(name or "").lower()
            if nlow.startswith("_") or "example" in nlow or "comment" in nlow:
                continue
            if cfg.get("url"):
                # HTTP MCP not implemented in v0.5; skip with note
                continue
            cmd = cfg.get("command")
            if not cmd:
                continue
            env = dict(cfg.get("env") or {})
            # Skip servers that need an API key the user never set (e.g. empty FIRECRAWL_API_KEY)
            missing_key = False
            for ek, ev in env.items():
                if "key" in str(ek).lower() and not str(ev or "").strip():
                    missing_key = True
                    break
            if missing_key:
                continue
            sess = McpStdioSession(
                name=name,
                command=cmd,
                args=list(cfg.get("args") or []),
                env=env,
            )
            # Short timeout — never freeze Chat “Thinking…” for 40s+ on broken npx servers
            if sess.start(timeout=8.0):
                self._sessions[name] = sess
        self._started = True

    def list_tools(self) -> list[dict[str, Any]]:
        self.ensure_started()
        out: list[dict[str, Any]] = []
        for sname, sess in self._sessions.items():
            for t in sess.tools:
                out.append(
                    {
                        "server": sname,
                        "name": t.get("name"),
                        "qualified": f"{sname}.{t.get('name')}",
                        "description": t.get("description") or "",
                        "inputSchema": t.get("inputSchema") or {},
                    }
                )
        # also list configured but failed
        for name, cfg in self._configs.items():
            if name not in self._sessions:
                out.append(
                    {
                        "server": name,
                        "name": None,
                        "qualified": name,
                        "description": f"(not connected) {cfg.get('command', cfg.get('url', ''))}",
                        "error": True,
                    }
                )
        return out

    def call(self, qualified: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        self.ensure_started()
        if "." not in qualified:
            return {"ok": False, "error": "Use server.tool_name form"}
        server, tool = qualified.split(".", 1)
        sess = self._sessions.get(server)
        if not sess:
            return {"ok": False, "error": f"MCP server not connected: {server}"}
        return sess.call_tool(tool, arguments)

    def catalog_prompt(self) -> str:
        tools = self.list_tools()
        lines = [
            "### MCP tools",
            f"Connected tool entries: {len([t for t in tools if not t.get('error')])}",
            "Config files searched: ~/.grok/mcp.json, app mcp.json, data/mcp.json, etc.",
            "",
        ]
        if not tools:
            lines.append(
                "No MCP servers configured. Add `mcp.json` next to the app or in `data/mcp.json`:\n"
                '```json\n{\n  "mcpServers": {\n    "example": {\n      "command": "npx",\n'
                '      "args": ["-y", "@modelcontextprotocol/server-filesystem", "C:/"]\n    }\n  }\n}\n```'
            )
        else:
            for t in tools:
                if t.get("error"):
                    lines.append(f"- `{t['server']}` — not connected")
                else:
                    lines.append(
                        f"- **{t['qualified']}** — {(t.get('description') or '')[:140]}"
                    )
            lines.append("")
            lines.append(
                "To call an MCP tool, emit:\n"
                "<<<MCP>>>\n"
                "server.tool_name\n"
                '{"arg": "value"}\n'
                "<<<END_MCP>>>\n"
            )
        return "\n".join(lines)

    def close_all(self) -> None:
        for s in self._sessions.values():
            s.close()
        self._sessions.clear()
        self._started = False


_hub: McpHub | None = None


def get_mcp_hub() -> McpHub:
    global _hub
    if _hub is None:
        _hub = McpHub()
    return _hub


def extract_mcp_requests(text: str) -> list[tuple[str, dict[str, Any]]]:
    """Parse <<<MCP>>> server.tool \\n {json} <<<END_MCP>>> blocks."""
    import re

    pat = re.compile(
        r"<<<MCP>>>\s*(.*?)\s*<<<END_MCP>>>",
        re.DOTALL | re.IGNORECASE,
    )
    out: list[tuple[str, dict[str, Any]]] = []
    for m in pat.finditer(text or ""):
        body = (m.group(1) or "").strip()
        if not body:
            continue
        lines = body.splitlines()
        qual = lines[0].strip()
        args: dict[str, Any] = {}
        rest = "\n".join(lines[1:]).strip()
        if rest:
            try:
                args = json.loads(rest)
                if not isinstance(args, dict):
                    args = {"value": args}
            except json.JSONDecodeError:
                args = {"raw": rest}
        out.append((qual, args))
    return out
