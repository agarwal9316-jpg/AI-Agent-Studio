"""OpenAPI → Studio HTTP tools (GET/POST subset).

Clean reimplementation inspired by Open WebUI tool-server patterns —
no GPL code copied. Fetch openapi.json / swagger, register operations,
execute with urllib, expose OpenAI function schemas for native tool_calls.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

# Subset requested for Next-10 #1
_SUPPORTED_METHODS = frozenset({"get", "post"})


def _safe_tool_name(raw: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_]", "_", (raw or "").strip())
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        s = "op"
    if s[0].isdigit():
        s = "op_" + s
    return s[:64]


def fetch_openapi_spec(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
    opener: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """GET an OpenAPI/Swagger JSON document. Soft-degrades with ok=False."""
    u = (url or "").strip()
    if not u:
        return {"ok": False, "error": "Empty OpenAPI URL"}
    hdrs = {
        "Accept": "application/json, application/yaml, text/yaml, */*",
        "User-Agent": "AI-Agent-Studio/1.28 plugins-openapi",
    }
    if headers:
        hdrs.update({str(k): str(v) for k, v in headers.items()})
    req = urllib.request.Request(u, headers=hdrs, method="GET")
    open_fn = opener or urllib.request.urlopen
    try:
        with open_fn(req, timeout=timeout) as resp:
            raw = resp.read()
            ctype = ""
            try:
                ctype = (resp.headers.get("Content-Type") or "").lower()
            except Exception:  # noqa: BLE001
                pass
        text = raw.decode("utf-8", errors="replace")
        # YAML soft-degrade note — we only parse JSON for v1
        if "yaml" in ctype and not text.lstrip().startswith("{"):
            return {
                "ok": False,
                "error": "YAML OpenAPI not supported yet — paste JSON openapi.json URL",
            }
        try:
            spec = json.loads(text)
        except json.JSONDecodeError as e:
            return {"ok": False, "error": f"Invalid JSON OpenAPI: {e}"}
        if not isinstance(spec, dict):
            return {"ok": False, "error": "OpenAPI root must be an object"}
        return {"ok": True, "spec": spec, "url": u}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}: {e.reason}", "soft_degrade": True}
    except urllib.error.URLError as e:
        return {"ok": False, "error": f"URL error: {e.reason}", "soft_degrade": True}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "soft_degrade": True}


def infer_base_url(spec: dict[str, Any], spec_url: str = "") -> str:
    """Pick a usable HTTP base URL from servers[] or the spec URL origin."""
    servers = spec.get("servers")
    if isinstance(servers, list) and servers:
        first = servers[0]
        if isinstance(first, dict) and first.get("url"):
            return str(first["url"]).rstrip("/")
        if isinstance(first, str):
            return first.rstrip("/")
    # Swagger 2.0
    host = spec.get("host")
    base_path = spec.get("basePath") or ""
    schemes = spec.get("schemes") or ["https"]
    if host:
        scheme = schemes[0] if isinstance(schemes, list) and schemes else "https"
        return f"{scheme}://{host}{base_path}".rstrip("/")
    if spec_url:
        p = urllib.parse.urlparse(spec_url)
        if p.scheme and p.netloc:
            return f"{p.scheme}://{p.netloc}".rstrip("/")
    return ""


def _resolve_ref(ref: str, components: dict[str, Any], seen: set[str] | None = None) -> dict[str, Any]:
    seen = seen or set()
    if not ref or not ref.startswith("#/"):
        return {}
    if ref in seen:
        return {}
    seen.add(ref)
    parts = ref.lstrip("#/").split("/")
    cur: Any = {"components": components} if parts and parts[0] == "components" else components
    # Walk from document root-ish: components is passed separately
    if parts[0] == "components":
        cur = components
        parts = parts[1:]
    else:
        # e.g. #/definitions/Pet (swagger 2)
        cur = components
    for part in parts:
        if not isinstance(cur, dict):
            return {}
        cur = cur.get(part)
    if isinstance(cur, dict):
        if "$ref" in cur:
            return _resolve_ref(str(cur["$ref"]), components, seen)
        return dict(cur)
    return {}


def _schema_to_json_schema(schema: dict[str, Any], components: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return {"type": "string"}
    if "$ref" in schema:
        resolved = _resolve_ref(str(schema["$ref"]), components)
        return _schema_to_json_schema(resolved, components) if resolved else {"type": "object"}
    out: dict[str, Any] = {}
    for k in ("type", "description", "enum", "format", "default"):
        if k in schema:
            out[k] = schema[k]
    if "properties" in schema and isinstance(schema["properties"], dict):
        out["type"] = out.get("type") or "object"
        out["properties"] = {
            pk: _schema_to_json_schema(pv if isinstance(pv, dict) else {}, components)
            for pk, pv in schema["properties"].items()
        }
        if isinstance(schema.get("required"), list):
            out["required"] = [str(x) for x in schema["required"]]
    if schema.get("type") == "array" or "items" in schema:
        out["type"] = "array"
        items = schema.get("items")
        out["items"] = (
            _schema_to_json_schema(items, components) if isinstance(items, dict) else {"type": "string"}
        )
    if not out:
        out = {"type": "string"}
    return out


def convert_openapi_to_tools(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert OpenAPI paths → tool descriptors (GET/POST only)."""
    components: dict[str, Any] = {}
    if isinstance(spec.get("components"), dict):
        components = spec["components"]
    # Swagger 2 definitions → fake components.schemas
    if isinstance(spec.get("definitions"), dict):
        components = dict(components)
        components.setdefault("schemas", {})
        if isinstance(components["schemas"], dict):
            components["schemas"] = {**spec["definitions"], **components["schemas"]}

    tools: list[dict[str, Any]] = []
    paths = spec.get("paths")
    if not isinstance(paths, dict):
        return tools

    used_names: set[str] = set()
    for path, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        path_params = methods.get("parameters") if isinstance(methods.get("parameters"), list) else []
        for method, operation in methods.items():
            m = str(method).lower()
            if m not in _SUPPORTED_METHODS:
                continue
            if not isinstance(operation, dict):
                continue
            op_id = operation.get("operationId") or f"{m}_{path}"
            name = _safe_tool_name(str(op_id))
            base = name
            n = 2
            while name in used_names:
                name = f"{base}_{n}"
                n += 1
            used_names.add(name)

            desc = (
                operation.get("description")
                or operation.get("summary")
                or f"{m.upper()} {path}"
            )
            props: dict[str, Any] = {}
            required: list[str] = []

            merged: dict[tuple[str, str], dict[str, Any]] = {}
            for param in path_params:
                if isinstance(param, dict) and param.get("name"):
                    if "$ref" in param:
                        param = _resolve_ref(str(param["$ref"]), components) or param
                    merged[(str(param["name"]), str(param.get("in") or ""))] = param
            op_params = operation.get("parameters") if isinstance(operation.get("parameters"), list) else []
            for param in op_params:
                if isinstance(param, dict) and param.get("name"):
                    if "$ref" in param:
                        param = _resolve_ref(str(param["$ref"]), components) or param
                    merged[(str(param["name"]), str(param.get("in") or ""))] = param

            for param in merged.values():
                pname = str(param.get("name"))
                schema = param.get("schema") if isinstance(param.get("schema"), dict) else {}
                if not schema and param.get("type"):
                    schema = {"type": param.get("type"), "description": param.get("description")}
                js = _schema_to_json_schema(schema or {"type": "string"}, components)
                if param.get("description") and not js.get("description"):
                    js["description"] = param.get("description")
                js["description"] = (js.get("description") or "") + f" (in: {param.get('in', 'query')})"
                props[pname] = js
                if param.get("required"):
                    required.append(pname)

            # requestBody (OpenAPI 3) — flatten JSON properties into args
            body = operation.get("requestBody")
            if isinstance(body, dict):
                content = body.get("content") if isinstance(body.get("content"), dict) else {}
                json_body = None
                for ct in ("application/json", "application/x-www-form-urlencoded", "*/*"):
                    if ct in content and isinstance(content[ct], dict):
                        json_body = content[ct].get("schema")
                        break
                if not json_body and content:
                    first = next(iter(content.values()), None)
                    if isinstance(first, dict):
                        json_body = first.get("schema")
                if isinstance(json_body, dict):
                    resolved = _schema_to_json_schema(json_body, components)
                    if resolved.get("properties"):
                        props.update(resolved["properties"])
                        for r in resolved.get("required") or []:
                            if r not in required:
                                required.append(str(r))
                    else:
                        props["body"] = resolved
                        if body.get("required"):
                            required.append("body")

            tools.append(
                {
                    "name": name,
                    "method": m.upper(),
                    "path": str(path),
                    "description": str(desc)[:500],
                    "parameters": {
                        "type": "object",
                        "properties": props,
                        "required": required,
                    },
                }
            )
    return tools


def import_openapi_from_url(
    url: str,
    *,
    name: str = "",
    headers: dict[str, str] | None = None,
    auth_type: str = "none",
    auth_token: str = "",
    enabled: bool = True,
    opener: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Fetch + convert + register into plugins registry."""
    from app.core.services.integrations import plugins_registry as pr

    fetched = fetch_openapi_spec(url, headers=headers, opener=opener)
    if not fetched.get("ok"):
        return fetched
    spec = fetched["spec"]
    tools = convert_openapi_to_tools(spec)
    base = infer_base_url(spec, url)
    title = name or (spec.get("info") or {}).get("title") if isinstance(spec.get("info"), dict) else ""
    title = (title or "OpenAPI").strip()
    item = pr.add_openapi_server(
        name=str(title),
        spec_url=url,
        base_url=base,
        headers=headers,
        auth_type=auth_type,
        auth_token=auth_token,
        enabled=enabled,
        tools=tools,
    )
    return {
        "ok": True,
        "server": item,
        "tool_count": len(tools),
        "base_url": base,
    }


def refresh_openapi_server(
    server_id: str,
    *,
    opener: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Re-fetch spec for an existing OpenAPI connector."""
    from app.core.services.integrations import plugins_registry as pr

    item = pr.get_openapi(server_id)
    if not item:
        return {"ok": False, "error": f"Unknown OpenAPI server: {server_id}"}
    url = item.get("spec_url") or ""
    fetched = fetch_openapi_spec(url, headers=item.get("headers") or {}, opener=opener)
    if not fetched.get("ok"):
        pr.update_openapi_server(
            server_id,
            last_test=pr._now(),
            last_error=str(fetched.get("error") or "fetch failed"),
        )
        return {**fetched, "soft_degrade": True}
    tools = convert_openapi_to_tools(fetched["spec"])
    base = item.get("base_url") or infer_base_url(fetched["spec"], url)
    updated = pr.update_openapi_server(
        server_id,
        tools=tools,
        base_url=base,
        last_test=pr._now(),
        last_error="",
    )
    return {"ok": True, "server": updated, "tool_count": len(tools)}


def test_openapi_server(server_id: str, *, opener: Callable[..., Any] | None = None) -> dict[str, Any]:
    """Connectivity/test = refresh spec; soft-degrade on failure."""
    return refresh_openapi_server(server_id, opener=opener)


def _auth_headers(server: dict[str, Any]) -> dict[str, str]:
    hdrs = {str(k): str(v) for k, v in (server.get("headers") or {}).items()}
    auth = (server.get("auth_type") or "none").lower()
    token = (server.get("auth_token") or "").strip()
    if auth in ("bearer", "token") and token:
        hdrs.setdefault("Authorization", f"Bearer {token}")
    elif auth == "header" and token and ":" in token:
        k, v = token.split(":", 1)
        hdrs.setdefault(k.strip(), v.strip())
    elif auth == "api_key" and token:
        hdrs.setdefault("X-API-Key", token)
    return hdrs


def _find_tool(server: dict[str, Any], tool_name: str) -> dict[str, Any] | None:
    for t in server.get("tools") or []:
        if isinstance(t, dict) and t.get("name") == tool_name:
            return t
    return None


def execute_openapi_tool(
    server_name_or_id: str,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    *,
    timeout: float = 60.0,
    opener: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Execute a registered GET/POST tool. Soft-degrade on network errors."""
    from app.core.services.integrations import plugins_registry as pr

    server = pr.get_openapi(server_name_or_id)
    if not server:
        # also match by name
        for s in pr.list_openapi_servers():
            if s.get("name") == server_name_or_id:
                server = s
                break
    if not server:
        return {"ok": False, "error": f"OpenAPI server not found: {server_name_or_id}"}
    if not server.get("enabled"):
        return {"ok": False, "error": f"OpenAPI server disabled: {server.get('name')}"}

    tool = _find_tool(server, tool_name)
    if not tool:
        return {"ok": False, "error": f"Unknown tool {tool_name} on {server.get('name')}"}

    method = str(tool.get("method") or "GET").upper()
    if method.lower() not in _SUPPORTED_METHODS:
        return {"ok": False, "error": f"Method {method} not supported (GET/POST only)"}

    args = dict(arguments or {})
    path_tmpl = str(tool.get("path") or "/")
    path = path_tmpl
    # Substitute path params
    for m in re.finditer(r"\{([^}]+)\}", path_tmpl):
        key = m.group(1)
        if key in args:
            path = path.replace("{" + key + "}", urllib.parse.quote(str(args.pop(key)), safe=""))
        else:
            return {"ok": False, "error": f"Missing path parameter: {key}"}

    base = (server.get("base_url") or "").rstrip("/")
    if not base:
        return {"ok": False, "error": "No base_url configured for OpenAPI server"}

    url = base + (path if path.startswith("/") else "/" + path)
    hdrs = _auth_headers(server)
    hdrs.setdefault("Accept", "application/json, text/plain, */*")
    open_fn = opener or urllib.request.urlopen
    body_bytes: bytes | None = None

    try:
        if method == "GET":
            if args:
                q = urllib.parse.urlencode({k: str(v) for k, v in args.items()}, doseq=True)
                url = url + ("&" if "?" in url else "?") + q
            req = urllib.request.Request(url, headers=hdrs, method="GET")
        else:
            # POST — prefer JSON body
            payload = args.pop("body", None)
            if payload is None:
                payload = args
            elif args:
                # leftover query-ish keys become query string
                q = urllib.parse.urlencode({k: str(v) for k, v in args.items()}, doseq=True)
                url = url + ("&" if "?" in url else "?") + q
            body_bytes = json.dumps(payload).encode("utf-8")
            hdrs.setdefault("Content-Type", "application/json")
            req = urllib.request.Request(url, data=body_bytes, headers=hdrs, method="POST")

        with open_fn(req, timeout=timeout) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None) or resp.getcode()
            text = raw.decode("utf-8", errors="replace")
        parsed: Any
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = text[:8000]
        return {
            "ok": True,
            "status": status,
            "url": url,
            "method": method,
            "result": parsed,
        }
    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8", errors="replace")[:2000]
        except Exception:  # noqa: BLE001
            pass
        return {
            "ok": False,
            "error": f"HTTP {e.code}: {e.reason}",
            "body": err_body,
            "soft_degrade": True,
            "url": url,
            "method": method,
        }
    except urllib.error.URLError as e:
        return {
            "ok": False,
            "error": f"URL error: {e.reason}",
            "soft_degrade": True,
            "url": url,
            "method": method,
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "soft_degrade": True, "url": url, "method": method}


def list_enabled_openapi_tools() -> list[dict[str, Any]]:
    from app.core.services.integrations import plugins_registry as pr

    out: list[dict[str, Any]] = []
    for s in pr.list_openapi_servers():
        if not s.get("enabled"):
            continue
        for t in s.get("tools") or []:
            if not isinstance(t, dict) or not t.get("name"):
                continue
            out.append(
                {
                    "server": s["name"],
                    "server_id": s["id"],
                    "name": t["name"],
                    "qualified": f"{s['name']}.{t['name']}",
                    "method": t.get("method"),
                    "path": t.get("path"),
                    "description": t.get("description") or "",
                    "parameters": t.get("parameters") or {"type": "object", "properties": {}},
                    "source": "openapi",
                }
            )
    return out


def openai_tool_schemas() -> list[dict[str, Any]]:
    """OpenAI function schemas for enabled OpenAPI tools + generic `openapi`."""
    tools: list[dict[str, Any]] = [
        {
            "type": "function",
            "function": {
                "name": "openapi",
                "description": "Call an OpenAPI HTTP tool (server.tool from Plugins)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "server": {"type": "string", "description": "OpenAPI server name"},
                        "tool_name": {"type": "string"},
                        "arguments": {"type": "object"},
                    },
                    "required": ["server", "tool_name"],
                },
            },
        }
    ]
    for t in list_enabled_openapi_tools():
        safe_server = _safe_tool_name(t["server"])
        fname = f"oa__{safe_server}__{t['name']}"[:64]
        params = t.get("parameters") if isinstance(t.get("parameters"), dict) else {
            "type": "object",
            "properties": {},
        }
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": fname,
                    "description": (
                        f"[OpenAPI {t.get('method')} {t.get('path')}] "
                        f"{t.get('description') or t['qualified']}"
                    )[:400],
                    "parameters": params,
                },
            }
        )
    return tools


def extract_openapi_requests(text: str) -> list[tuple[str, dict[str, Any]]]:
    """Parse <<<OPENAPI>>> server.tool \\n {json} <<<END_OPENAPI>>> blocks."""
    pat = re.compile(
        r"<<<OPENAPI>>>\s*(.*?)\s*<<<END_OPENAPI>>>",
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
                parsed = json.loads(rest)
                if isinstance(parsed, dict):
                    args = parsed
                else:
                    args = {"value": parsed}
            except json.JSONDecodeError:
                args = {"raw": rest}
        out.append((qual, args))
    return out


def call_qualified(qualified: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    if "." not in qualified:
        return {"ok": False, "error": "Use server.tool_name form"}
    server, tool = qualified.split(".", 1)
    return execute_openapi_tool(server, tool, arguments)


def parse_oa_function_name(fname: str) -> tuple[str, str] | None:
    """Map oa__Server__tool → (server_approx, tool)."""
    if not fname.startswith("oa__"):
        return None
    rest = fname[4:]
    if "__" not in rest:
        return None
    server, tool = rest.split("__", 1)
    return server, tool
