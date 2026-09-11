"""
Curated MCP "marketplace" — like VS Code / Open WebUI extension catalogs.
Adds server recipes into data/mcp.json (does not download binaries itself;
npx/uvx fetch packages when the MCP hub starts).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.paths import app_root
from app.core.services.integrations.mcp_client import load_mcp_config

# Recommended servers (stdio). User installs by enabling into mcp.json.
MARKETPLACE: list[dict[str, Any]] = [
    {
        "id": "filesystem",
        "name": "Filesystem",
        "description": "Read/write local files via MCP (scope a folder).",
        "requires": "Node.js + npx",
        "homepage": "https://github.com/modelcontextprotocol/servers",
        "config": {
            "command": "npx",
            "args": [
                "-y",
                "@modelcontextprotocol/server-filesystem",
                str(Path.home()),
            ],
        },
    },
    {
        "id": "github",
        "name": "GitHub",
        "description": "Repos, PRs, issues (needs GITHUB_PERSONAL_ACCESS_TOKEN).",
        "requires": "Node.js + GitHub PAT",
        "homepage": "https://github.com/modelcontextprotocol/servers",
        "config": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "YOUR_TOKEN_HERE"},
        },
    },
    {
        "id": "memory",
        "name": "Memory (knowledge graph)",
        "description": "Persistent memory graph for the agent.",
        "requires": "Node.js + npx",
        "homepage": "https://github.com/modelcontextprotocol/servers",
        "config": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-memory"],
        },
    },
    {
        "id": "puppeteer",
        "name": "Puppeteer (browser)",
        "description": "Browse pages, screenshots — web access for the LLM.",
        "requires": "Node.js + npx",
        "homepage": "https://github.com/modelcontextprotocol/servers",
        "config": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-puppeteer"],
        },
    },
    {
        "id": "sqlite",
        "name": "SQLite",
        "description": "Query a local SQLite database file.",
        "requires": "Node.js + npx",
        "homepage": "https://github.com/modelcontextprotocol/servers",
        "config": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-sqlite", "--db-path", "C:/data/app.db"],
        },
    },
    {
        "id": "fetch",
        "name": "Fetch (HTTP)",
        "description": "Fetch URL content for the model.",
        "requires": "Node.js + npx",
        "homepage": "https://github.com/modelcontextprotocol/servers",
        "config": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-fetch"],
        },
    },
    {
        "id": "git",
        "name": "Git",
        "description": "Git repository tools via MCP.",
        "requires": "Node.js + git",
        "homepage": "https://github.com/modelcontextprotocol/servers",
        "config": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-git", "--repository", str(Path.home())],
        },
    },
    {
        "id": "brave-search",
        "name": "Brave Search",
        "description": "Web search (needs BRAVE_API_KEY).",
        "requires": "Node.js + Brave API key",
        "homepage": "https://github.com/modelcontextprotocol/servers",
        "config": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-brave-search"],
            "env": {"BRAVE_API_KEY": "YOUR_KEY_HERE"},
        },
    },
]


def marketplace_path() -> Path:
    return app_root() / "data" / "mcp.json"


def list_marketplace() -> list[dict[str, Any]]:
    installed = load_mcp_config()
    out = []
    for item in MARKETPLACE:
        out.append(
            {
                **item,
                "installed": item["id"] in installed
                or item["name"].lower().replace(" ", "-") in installed
                or any(item["id"] in k for k in installed),
            }
        )
    return out


def enable_marketplace_item(item_id: str) -> dict[str, Any]:
    item = next((x for x in MARKETPLACE if x["id"] == item_id), None)
    if not item:
        return {"ok": False, "error": f"Unknown marketplace id: {item_id}"}

    path = marketplace_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {"mcpServers": {}}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {"mcpServers": {}}
    if "mcpServers" not in data or not isinstance(data["mcpServers"], dict):
        data["mcpServers"] = {}

    # Remove comment-only dummy keys that are not valid servers
    data["mcpServers"][item_id] = dict(item["config"])
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # Force MCP hub reload on next use
    try:
        from app.core.services.integrations.mcp_client import get_mcp_hub

        hub = get_mcp_hub()
        hub.close_all()
    except Exception:  # noqa: BLE001
        pass

    return {"ok": True, "path": str(path), "id": item_id}


def marketplace_prompt() -> str:
    lines = [
        "## MCP Marketplace (recommended extensions)",
        "User can install these into data/mcp.json via the Marketplace UI.",
        "Similar idea to VS Code extensions / Open WebUI tools catalog.",
        "",
    ]
    for m in MARKETPLACE:
        lines.append(
            f"- **{m['name']}** (`{m['id']}`): {m['description']} Requires: {m['requires']}"
        )
    return "\n".join(lines)
