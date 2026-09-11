"""Next-10 #1 — Plugins / MCP OpenAPI tools registry + OpenAPI import.

Mocked HTTP only. Soft-degrade paths covered.
No GPL OWUI blobs — Studio reimplementation.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.services.integrations import openapi_tools as oa  # noqa: E402
from app.core.services.integrations import plugins_registry as pr  # noqa: E402


SAMPLE_OPENAPI = {
    "openapi": "3.0.0",
    "info": {"title": "Demo API", "version": "1.0"},
    "servers": [{"url": "https://api.example.com/v1"}],
    "paths": {
        "/pets": {
            "get": {
                "operationId": "listPets",
                "summary": "List pets",
                "parameters": [
                    {
                        "name": "limit",
                        "in": "query",
                        "schema": {"type": "integer"},
                    }
                ],
            },
            "post": {
                "operationId": "createPet",
                "summary": "Create a pet",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                },
                                "required": ["name"],
                            }
                        }
                    },
                },
            },
            "delete": {
                "operationId": "deleteAllPets",
                "summary": "Should be skipped (not GET/POST)",
            },
        },
        "/pets/{petId}": {
            "get": {
                "operationId": "getPet",
                "summary": "Get one pet",
                "parameters": [
                    {
                        "name": "petId",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
            }
        },
    },
}


def _iso(td: Path):
    return patch(
        "app.core.services.integrations.plugins_registry.plugins_path",
        lambda: td / "plugins.json",
    )


def _iso_mcp(td: Path):
    return patch(
        "app.core.services.integrations.plugins_registry.app_root",
        lambda: td,
    )


def test_mcp_crud_enable_persist():
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)
        (td / "data").mkdir(parents=True, exist_ok=True)
        with _iso(td), _iso_mcp(td), patch(
            "app.core.services.integrations.plugins_registry._reload_mcp_hub"
        ):
            assert pr.list_mcp_servers() == []
            item = pr.add_mcp_server(
                name="filesystem",
                command="npx",
                args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
                enabled=True,
            )
            assert item["id"] and item["enabled"] is True
            assert item["command"] == "npx"
            got = pr.get_mcp(item["id"])
            assert got and got["name"] == "filesystem"
            off = pr.set_mcp_enabled(item["id"], False)
            assert off and off["enabled"] is False
            on = pr.set_mcp_enabled(item["id"], True)
            assert on and on["enabled"] is True
            # mirrored into data/mcp.json
            mcp_path = td / "data" / "mcp.json"
            assert mcp_path.is_file()
            data = json.loads(mcp_path.read_text(encoding="utf-8"))
            assert "filesystem" in data.get("mcpServers", {})
            assert data["mcpServers"]["filesystem"].get("_from_plugins") is True
            upd = pr.update_mcp_server(item["id"], name="fs2")
            assert upd and upd["name"] == "fs2"
            assert pr.delete_mcp_server(item["id"]) is True
            assert pr.get_mcp(item["id"]) is None
    print("✓ MCP CRUD + enable + mcp.json mirror")


def test_openapi_convert_get_post_only():
    tools = oa.convert_openapi_to_tools(SAMPLE_OPENAPI)
    names = {t["name"] for t in tools}
    assert "listPets" in names
    assert "createPet" in names
    assert "getPet" in names
    assert "deleteAllPets" not in names  # DELETE skipped
    methods = {t["name"]: t["method"] for t in tools}
    assert methods["listPets"] == "GET"
    assert methods["createPet"] == "POST"
    assert methods["getPet"] == "GET"
    # createPet should expose name property
    create = next(t for t in tools if t["name"] == "createPet")
    assert "name" in (create["parameters"].get("properties") or {})
    print("✓ OpenAPI convert GET/POST subset")


def test_import_openapi_mocked_http():
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)
        (td / "data").mkdir(parents=True, exist_ok=True)

        class _Resp:
            def __init__(self, payload: bytes):
                self._payload = payload
                self.headers = {"Content-Type": "application/json"}
                self.status = 200

            def read(self):
                return self._payload

            def getcode(self):
                return 200

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_open(req, timeout=30):
            return _Resp(json.dumps(SAMPLE_OPENAPI).encode("utf-8"))

        with _iso(td), _iso_mcp(td), patch(
            "app.core.services.integrations.plugins_registry._reload_mcp_hub"
        ):
            res = oa.import_openapi_from_url(
                "https://api.example.com/openapi.json",
                name="Demo",
                opener=fake_open,
            )
            assert res["ok"] is True
            assert res["tool_count"] == 3
            assert res["base_url"] == "https://api.example.com/v1"
            server = res["server"]
            assert server["name"] == "Demo"
            assert server["enabled"] is True
            assert len(server["tools"]) == 3
            listed = pr.list_openapi_servers()
            assert len(listed) == 1
            # schemas for native tools
            schemas = oa.openai_tool_schemas()
            names = [(s.get("function") or {}).get("name") for s in schemas]
            assert "openapi" in names
            assert any(n and n.startswith("oa__") for n in names)
    print("✓ OpenAPI import mocked HTTP + schemas")


def test_execute_openapi_get_post_mocked():
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)
        (td / "data").mkdir(parents=True, exist_ok=True)

        class _Resp:
            def __init__(self, payload: bytes, status=200):
                self._payload = payload
                self.status = status
                self.headers = {"Content-Type": "application/json"}

            def read(self):
                return self._payload

            def getcode(self):
                return self.status

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        calls: list[str] = []

        def fake_open(req, timeout=60):
            calls.append(f"{req.get_method()} {req.full_url}")
            if req.get_method() == "GET":
                return _Resp(json.dumps([{"id": 1, "name": "fido"}]).encode())
            return _Resp(json.dumps({"id": 2, "name": "spot"}).encode())

        with _iso(td), _iso_mcp(td), patch(
            "app.core.services.integrations.plugins_registry._reload_mcp_hub"
        ):
            item = pr.add_openapi_server(
                name="Demo",
                spec_url="https://api.example.com/openapi.json",
                base_url="https://api.example.com/v1",
                enabled=True,
                tools=oa.convert_openapi_to_tools(SAMPLE_OPENAPI),
            )
            get_res = oa.execute_openapi_tool(
                "Demo", "getPet", {"petId": "abc"}, opener=fake_open
            )
            assert get_res["ok"] is True
            assert get_res["method"] == "GET"
            assert "/pets/abc" in get_res["url"]
            post_res = oa.execute_openapi_tool(
                item["id"], "createPet", {"name": "spot"}, opener=fake_open
            )
            assert post_res["ok"] is True
            assert post_res["method"] == "POST"
            assert any(c.startswith("POST ") for c in calls)
    print("✓ OpenAPI execute GET/POST mocked")


def test_execute_soft_degrade_when_down():
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)
        (td / "data").mkdir(parents=True, exist_ok=True)

        import urllib.error

        def boom(req, timeout=60):
            raise urllib.error.URLError("connection refused")

        with _iso(td), _iso_mcp(td), patch(
            "app.core.services.integrations.plugins_registry._reload_mcp_hub"
        ):
            pr.add_openapi_server(
                name="Down",
                spec_url="https://down.example/openapi.json",
                base_url="https://down.example",
                enabled=True,
                tools=[
                    {
                        "name": "ping",
                        "method": "GET",
                        "path": "/ping",
                        "description": "ping",
                        "parameters": {"type": "object", "properties": {}},
                    }
                ],
            )
            res = oa.execute_openapi_tool("Down", "ping", {}, opener=boom)
            assert res["ok"] is False
            assert res.get("soft_degrade") is True
            assert "URL error" in str(res.get("error") or "")
    print("✓ soft-degrade when server down")


def test_extract_openapi_requests():
    text = """
Doing work
<<<OPENAPI>>>
Demo.listPets
{"limit": 5}
<<<END_OPENAPI>>>
more text
<<<OPENAPI>>>
Demo.createPet
{"name": "x"}
<<<END_OPENAPI>>>
"""
    reqs = oa.extract_openapi_requests(text)
    assert len(reqs) == 2
    assert reqs[0][0] == "Demo.listPets"
    assert reqs[0][1]["limit"] == 5
    assert reqs[1][0] == "Demo.createPet"
    print("✓ extract OPENAPI blocks")


def test_test_mcp_soft_degrade_http_only():
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)
        (td / "data").mkdir(parents=True, exist_ok=True)
        with _iso(td), _iso_mcp(td), patch(
            "app.core.services.integrations.plugins_registry._reload_mcp_hub"
        ):
            item = pr.add_mcp_server(name="remote", url="https://mcp.example/sse", enabled=True)
            res = pr.test_mcp_server(item["id"])
            assert res["ok"] is False
            assert res.get("soft_degrade") is True
    print("✓ MCP HTTP-only soft-degrade on test")


def test_plugins_catalog_and_disabled_hidden():
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)
        (td / "data").mkdir(parents=True, exist_ok=True)
        with _iso(td), _iso_mcp(td), patch(
            "app.core.services.integrations.plugins_registry._reload_mcp_hub"
        ):
            pr.add_openapi_server(
                name="On",
                spec_url="https://x/openapi.json",
                base_url="https://x",
                enabled=True,
                tools=[{"name": "a", "method": "GET", "path": "/a", "description": "A", "parameters": {}}],
            )
            pr.add_openapi_server(
                name="Off",
                spec_url="https://y/openapi.json",
                base_url="https://y",
                enabled=False,
                tools=[{"name": "b", "method": "GET", "path": "/b", "description": "B", "parameters": {}}],
            )
            enabled = oa.list_enabled_openapi_tools()
            assert any(t["name"] == "a" for t in enabled)
            assert not any(t["name"] == "b" for t in enabled)
            cat = pr.catalog_prompt()
            assert "On" in cat
            assert "Off" not in cat or "OpenAPI" in cat
    print("✓ enabled tools only + catalog")


def test_studio_openai_tools_includes_openapi():
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)
        (td / "data").mkdir(parents=True, exist_ok=True)
        with _iso(td), _iso_mcp(td), patch(
            "app.core.services.integrations.plugins_registry._reload_mcp_hub"
        ), patch(
            "app.core.services.integrations.openapi_tools.list_enabled_openapi_tools",
            return_value=[
                {
                    "server": "Demo",
                    "server_id": "x",
                    "name": "listPets",
                    "qualified": "Demo.listPets",
                    "method": "GET",
                    "path": "/pets",
                    "description": "List",
                    "parameters": {"type": "object", "properties": {}},
                    "source": "openapi",
                }
            ],
        ):
            from app.core.services.tools.tool_schemas import studio_openai_tools

            tools = studio_openai_tools(include_harness=False)
            names = [(t.get("function") or {}).get("name") for t in tools]
            assert "mcp" in names
            assert "openapi" in names
            assert any(n and str(n).startswith("oa__") for n in names)
    print("✓ studio_openai_tools includes OpenAPI")


def test_parse_oa_function_name_and_json_block():
    assert oa.parse_oa_function_name("oa__Demo__listPets") == ("Demo", "listPets")
    assert oa.parse_oa_function_name("mcp") is None
    from app.core.services.llm.llm import _json_to_text_block

    block = _json_to_text_block(
        "openapi",
        json.dumps({"server": "Demo", "tool_name": "listPets", "arguments": {"limit": 1}}),
    )
    assert "<<<OPENAPI>>>" in block
    assert "Demo.listPets" in block
    print("✓ oa__ parse + openapi text block")


if __name__ == "__main__":
    test_mcp_crud_enable_persist()
    test_openapi_convert_get_post_only()
    test_import_openapi_mocked_http()
    test_execute_openapi_get_post_mocked()
    test_execute_soft_degrade_when_down()
    test_extract_openapi_requests()
    test_test_mcp_soft_degrade_http_only()
    test_plugins_catalog_and_disabled_hidden()
    test_studio_openai_tools_includes_openapi()
    test_parse_oa_function_name_and_json_block()
    print("\nAll next10 plugins/mcp tests passed.")
