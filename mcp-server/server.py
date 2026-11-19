"""
RedWire MCP Server
==================
Exposes RedWire platform operations as MCP tools for LLM integration.
Uses SSE transport so both external clients and the webapp can connect.

Security: Per-session auth — the client must send `Authorization: Bearer`
on the SSE request. The bearer is validated against the backend at connect
time and then forwarded on every backend API call, so the backend's existing
RBAC enforces permissions. There is no ambient/service token; an
unauthenticated `/sse` is refused.
"""

import os
import json
import re
import logging
import contextvars
from typing import Any

import httpx
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent
import mcp.types as types
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("redwire-mcp")

# ── Configuration ────────────────────────────────────────────────────────────

REDWIRE_API_URL = os.getenv("REDWIRE_API_URL", "http://backend:8000")
MCP_PORT = int(os.getenv("MCP_PORT", "3001"))
CORS_ORIGINS = [o for o in os.getenv("CORS_ORIGINS", "").split(",") if o]

# ── Per-Session Auth ─────────────────────────────────────────────────────────
# Each SSE connection MUST present its own bearer (JWT or API token) in the
# Authorization header. It's validated at connect time and stored per-session;
# every backend call forwards it. There is no shared/service token — an MCP
# session has exactly the authority of whoever opened it.

_session_token: contextvars.ContextVar[str] = contextvars.ContextVar(
    "session_token", default=""
)


def _headers() -> dict:
    """Build auth headers from the per-session bearer set at SSE connect."""
    h = {"Content-Type": "application/json"}
    token = _session_token.get("")
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _bearer_from(request: Request) -> str:
    """Extract a Bearer token from the Authorization header. Query-string
    tokens are deliberately NOT accepted — a long-lived bearer in the URL ends
    up in access logs, browser history and Referer (CWE-598)."""
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


async def _validate_bearer(token: str) -> bool:
    """Confirm the bearer is currently valid by asking the backend who it
    belongs to. We don't decode the JWT locally because the backend is the
    authority on revocation, expiry and `ro_`/`rw_` API-token resolution."""
    if not token:
        return False
    try:
        async with httpx.AsyncClient(base_url=REDWIRE_API_URL,
                                     timeout=10) as client:
            resp = await client.get(
                "/users/me",
                headers={"Authorization": f"Bearer {token}"},
            )
            return resp.status_code == 200
    except httpx.HTTPError:
        return False


# ── HTTP Client ──────────────────────────────────────────────────────────────

async def _api_get(path: str, params: dict | None = None) -> dict | list:
    """GET request to RedWire API."""
    async with httpx.AsyncClient(base_url=REDWIRE_API_URL, timeout=30) as client:
        resp = await client.get(path, headers=_headers(), params=params)
        resp.raise_for_status()
        return resp.json()


async def _api_post(path: str, data: dict | None = None) -> dict | list:
    """POST request to RedWire API."""
    async with httpx.AsyncClient(base_url=REDWIRE_API_URL, timeout=30) as client:
        resp = await client.post(path, headers=_headers(), json=data or {})
        resp.raise_for_status()
        return resp.json()


async def _api_put(path: str, data: dict) -> dict:
    """PUT request to RedWire API."""
    async with httpx.AsyncClient(base_url=REDWIRE_API_URL, timeout=30) as client:
        resp = await client.put(path, headers=_headers(), json=data)
        resp.raise_for_status()
        return resp.json()


async def _api_patch(path: str, data: dict) -> dict:
    """PATCH request to RedWire API."""
    async with httpx.AsyncClient(base_url=REDWIRE_API_URL, timeout=30) as client:
        resp = await client.patch(path, headers=_headers(), json=data)
        resp.raise_for_status()
        return resp.json()


async def _api_delete(path: str) -> dict | None:
    """DELETE request to RedWire API."""
    async with httpx.AsyncClient(base_url=REDWIRE_API_URL, timeout=30) as client:
        resp = await client.delete(path, headers=_headers())
        resp.raise_for_status()
        if resp.status_code == 204:
            return {"status": "deleted"}
        return resp.json()


# ── MCP Server ───────────────────────────────────────────────────────────────

mcp = Server("redwire")


# GHSA-q4x9-5gmc-fxh5 (a2): write-capable MCP tools are gated by an admin
# toggle (ai_write_tools_enabled, default false). When off, write tools are
# stripped from the catalog the agent sees AND refused at call_tool time.
_WRITE_TOOL_PREFIXES = ("create_", "update_", "delete_")


def _is_write_tool(name: str) -> bool:
    return any(name.startswith(p) for p in _WRITE_TOOL_PREFIXES)


async def _write_tools_enabled() -> bool:
    """Read the admin toggle. Fail closed on any error."""
    try:
        s = await _api_get("/ai/settings/status")
        return bool(s.get("write_tools_enabled", False)) if isinstance(s, dict) else False
    except Exception:
        return False


# Fields whose legal values aren't an enum but rows of the admin-editable
# configurable_types taxonomy (the UI dropdowns' source) are flagged in the
# registry (``taxonomy``) and resolved live, so an admin edit can't leave the
# model pinned to stale names.


async def _taxonomy_values(category: str) -> list[str] | None:
    """Live names from the configurable-types taxonomy, or None if it can't
    be read — in which case the caller leaves the field unconstrained rather
    than pinning the model to a stale list."""
    try:
        rows = await _api_get(f"/configurable-types/{category}")
    except Exception as e:
        logger.warning("taxonomy fetch failed for %r: %s", category, e)
        return None
    if not isinstance(rows, list):
        return None
    names = [r["name"] for r in rows if isinstance(r, dict) and r.get("name")]
    return names or None


# ── Tool registry ────────────────────────────────────────────────────────────
# The catalog and how each tool calls the API live in the backend
# (backend/utils/ai_tool_registry.py, served at GET /ai/tool-registry), so
# they're checked against the real routes and schemas there. This server
# keeps the security envelope: the write-tool gate, UUID / pattern checks on
# arguments that land in URL paths, vault-secret redaction and the
# untrusted-data wrapper.

_REGISTRY_TTL = 60.0
_registry_cache: dict[str, Any] = {"at": 0.0, "tools": None}


async def _registry() -> dict[str, dict]:
    """name -> spec, fetched with the session's bearer and cached briefly
    (the registry is the same for every caller)."""
    import time
    now = time.monotonic()
    if _registry_cache["tools"] is None or now - _registry_cache["at"] > _REGISTRY_TTL:
        data = await _api_get("/ai/tool-registry")
        _registry_cache["tools"] = {t["name"]: t for t in data["tools"]}
        _registry_cache["at"] = now
    return _registry_cache["tools"]


async def _apply_taxonomy_enums(tools: list[Tool], specs: dict[str, dict]) -> None:
    """Overlay live taxonomy values onto the taxonomy-backed enum fields."""
    cache: dict[str, list[str] | None] = {}
    for tool in tools:
        props = (tool.input_schema or {}).get("properties") or {}
        for field, category in (specs[tool.name].get("taxonomy") or {}).items():
            spec = props.get(field)
            if spec is None:
                continue
            if category not in cache:
                cache[category] = await _taxonomy_values(category)
            values = cache[category]
            if values:
                spec["enum"] = values
            else:
                # Taxonomy unreadable — drop any enum so the model isn't
                # forced to pick a value we can't vouch for.
                spec.pop("enum", None)


async def list_tools() -> list[Tool]:
    """Return all available RedWire tools. Write tools are filtered out when
    the admin toggle ai_write_tools_enabled is off (the default)."""
    import copy
    specs = await _registry()
    writes_on = await _write_tools_enabled()
    tools = [
        Tool(name=s["name"], description=s["description"], input_schema=copy.deepcopy(s["input_schema"]))
        for s in specs.values()
        if writes_on or not _is_write_tool(s["name"])
    ]
    await _apply_taxonomy_enums(tools, specs)
    return tools


_TOOL_DATA_BEGIN = "<<<REDWIRE_UNTRUSTED_TOOL_DATA_BEGIN>>>"
_TOOL_DATA_END = "<<<REDWIRE_UNTRUSTED_TOOL_DATA_END>>>"


def _wrap_untrusted(payload: str) -> str:
    safe = (payload or "").replace(_TOOL_DATA_BEGIN, "").replace(_TOOL_DATA_END, "")
    return f"{_TOOL_DATA_BEGIN}\n{safe}\n{_TOOL_DATA_END}"


async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Dispatch tool calls to the appropriate handler."""
    # GHSA-q4x9-5gmc-fxh5 (a2): refuse write tools when the admin toggle is
    # off, even if a client somehow asks for one not in list_tools.
    if _is_write_tool(name) and not await _write_tools_enabled():
        return [TextContent(type="text", text=_wrap_untrusted(
            f"Tool {name!r} requires ai_write_tools_enabled=true. "
            "An administrator must enable this in the AI settings; doing so "
            "while indirect prompt-injection mitigations are not in place can "
            "be unsafe. Refusing."))]
    try:
        result = await _dispatch(name, arguments)
        text = json.dumps(result, indent=2, default=str)
        return [TextContent(type="text", text=_wrap_untrusted(text))]
    except httpx.HTTPStatusError as e:
        # GHSA-q4x9-5gmc-fxh5: truncate the backend response body so a
        # validation-error echo of attacker-supplied fields can't smuggle
        # large instruction payloads through the error channel.
        raw_body = e.response.text or ""
        body = raw_body[:200] + ("…" if len(raw_body) > 200 else "")
        text = f"API Error {e.response.status_code}: {body}"
        return [TextContent(type="text", text=_wrap_untrusted(text))]
    except Exception as e:
        logger.exception(f"Tool {name} failed")
        return [TextContent(type="text", text=_wrap_untrusted(f"Error: {str(e)}"))]


# Every ``*_id`` argument must be a UUID unless its schema gives a pattern
# (e.g. scoring ``model_id``), which is checked instead. Either way nothing
# unchecked is interpolated into a URL path.

_VAULT_SECRET_FIELDS = ("username", "password", "note")


def _redact_vault_secrets(items):
    """GHSA-q4x9-5gmc-fxh5 (b1): never hand plaintext credentials to the LLM.
    Returns the input with `username` / `password` / `note` stripped from
    each vault item dict (recursing into a list of items)."""
    def _strip(it):
        if not isinstance(it, dict):
            return it
        out = {k: v for k, v in it.items() if k not in _VAULT_SECRET_FIELDS}
        out["_redacted"] = "secret fields hidden from AI assistant; view in UI"
        return out
    if isinstance(items, list):
        return [_strip(i) for i in items]
    return _strip(items)


def _validate_uuid_args(args: dict[str, Any], schema: dict | None = None) -> None:
    """GHSA-q4x9-5gmc-fxh5: every *_id argument is interpolated into a backend
    URL path. A model-supplied value containing '..' (or just a non-UUID path
    fragment) would traverse to unintended routes. Validate as UUID (or the
    schema's pattern) before any URL interpolation."""
    import uuid as _uuid
    props = (schema or {}).get("properties") or {}
    for k, v in args.items():
        pattern = (props.get(k) or {}).get("pattern")
        if pattern:
            if v is not None and not (isinstance(v, str) and re.fullmatch(pattern, v)):
                raise ValueError(f"argument {k!r}={v!r} doesn't match {pattern}")
            continue
        if not k.endswith("_id"):
            continue
        if v is None or v == "":
            continue
        if not isinstance(v, str):
            raise ValueError(f"argument {k!r} must be a UUID string")
        try:
            _uuid.UUID(v)
        except (ValueError, AttributeError):
            raise ValueError(f"argument {k!r}={v!r} is not a valid UUID")


async def _call_route(spec: dict, args: dict[str, Any]) -> Any:
    """One tool call from its registry entry: path placeholders, query
    arguments and (for POST/PUT/PATCH) a JSON body of the rest."""
    method, path = spec["method"], spec["path"]
    path_args = set(re.findall(r"{(\w+)}", path))
    for name in path_args:
        if not args.get(name):
            raise ValueError(f"argument {name!r} is required")
        path = path.replace("{" + name + "}", str(args[name]))
    props = (spec.get("input_schema") or {}).get("properties") or {}
    query_args = set(props) if spec.get("query") == "*" else set(spec.get("query") or ())
    rename = spec.get("query_rename") or {}
    params = {rename.get(a, a): args[a] for a in query_args if args.get(a) is not None}
    if method in ("GET", "DELETE"):
        if method == "GET":
            return await _api_get(path, params=params or None)
        return await _api_delete(path + ("?" + str(httpx.QueryParams(params)) if params else ""))
    skip = (path_args | query_args | set(spec.get("scope_args") or ())) - set(spec.get("body_keeps") or ())
    body = {k: v for k, v in args.items() if k not in skip}
    if params:
        path += "?" + str(httpx.QueryParams(params))
    send = {"POST": _api_post, "PUT": _api_put, "PATCH": _api_patch}[method]
    return await send(path, body)


async def _engagement_stats(args: dict[str, Any]) -> Any:
    # There is no /stats/engagement/{id} route; build the answer from the
    # per-engagement endpoints.
    eid = args["engagement_id"]
    return {
        "counts": await _api_get(f"/engagements/{eid}/counts"),
        "overview": await _api_get("/stats/overview", params={"engagement_id": eid}),
        "severity_distribution": await _api_get("/stats/severity-distribution", params={"engagement_id": eid}),
        "findings_by_status": await _api_get("/stats/findings-by-status", params={"engagement_id": eid}),
    }


async def _global_stats(args: dict[str, Any]) -> Any:
    # Likewise no /stats/global: the overview without an engagement is it.
    return {
        "overview": await _api_get("/stats/overview"),
        "severity_distribution": await _api_get("/stats/severity-distribution"),
    }


async def _ai_chat(args: dict[str, Any]) -> Any:
    payload = {"messages": [{"role": "user", "content": args["message"]}]}
    if args.get("editor_content"):
        payload["editor_content"] = args["editor_content"]
    if args.get("field_context"):
        payload["field_context"] = args["field_context"]
    # Non-streaming for MCP — collect the SSE stream into one answer.
    async with httpx.AsyncClient(base_url=REDWIRE_API_URL, timeout=120) as client:
        resp = await client.post("/ai/chat", headers=_headers(), json=payload)
        resp.raise_for_status()
        full_text = ""
        for line in resp.text.split("\n"):
            if line.startswith("data: "):
                chunk = line[6:]
                if chunk == "[DONE]":
                    break
                try:
                    data = json.loads(chunk)
                    full_text += data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                except json.JSONDecodeError:
                    continue
        return {"response": full_text}


# Named special cases a registry entry can point at with ``handler``.
_HANDLERS = {
    "engagement_stats": _engagement_stats,
    "global_stats": _global_stats,
    "ai_chat": _ai_chat,
}


async def _dispatch(name: str, args: dict[str, Any]) -> Any:
    """Route a tool call to the RedWire API as its registry entry says."""
    spec = (await _registry()).get(name)
    if spec is None:
        raise ValueError(f"Unknown tool: {name}")
    _validate_uuid_args(args, spec.get("input_schema"))
    if spec.get("handler"):
        result = await _HANDLERS[spec["handler"]](args)
    else:
        result = await _call_route(spec, dict(args))
    if spec.get("redact_vault_secrets"):
        # GHSA-q4x9-5gmc-fxh5 (b1): never return plaintext secrets to the LLM.
        result = _redact_vault_secrets(result)
    return result


# ── MCP 2.x handler registration ─────────────────────────────────────────────
# mcp 2.0 replaced the @mcp.list_tools()/@mcp.call_tool() decorators with
# (context, params) request handlers that return Result wrappers. These thin
# adapters keep list_tools()/call_tool() — and the dispatch, write-tool
# filtering, and live-taxonomy overlay underneath them — completely unchanged.

async def _on_list_tools(context, params):
    return types.ListToolsResult(tools=await list_tools())


async def _on_call_tool(context, params):
    content = await call_tool(params.name, params.arguments or {})
    return types.CallToolResult(content=content)


mcp.add_request_handler("tools/list", types.PaginatedRequestParams, _on_list_tools)
mcp.add_request_handler("tools/call", types.CallToolRequestParams, _on_call_tool)


# ── SSE Transport & ASGI App ─────────────────────────────────────────────────

sse = SseServerTransport("/messages/")


async def handle_sse(request: Request):
    """Handle SSE connection from MCP clients.

    The client MUST send `Authorization: Bearer <jwt-or-api-token>`. The
    bearer is validated against the backend at connect time; an absent or
    invalid bearer is a 401 before the SSE stream opens. The validated
    bearer is forwarded on every backend call for the life of the session.
    """
    token = _bearer_from(request)
    if not token or not await _validate_bearer(token):
        logger.warning(
            "SSE connect refused: %s bearer (remote=%s)",
            "missing" if not token else "invalid",
            request.client.host if request.client else "?",
        )
        return Response(
            '{"detail":"Missing or invalid Authorization bearer"}',
            status_code=401,
            media_type="application/json",
            headers={"WWW-Authenticate": "Bearer"},
        )

    _session_token.set(token)
    logger.info("SSE session connected (remote=%s)",
                request.client.host if request.client else "?")

    async with sse.connect_sse(
        request.scope, request.receive, request._send
    ) as streams:
        await mcp.run(
            streams[0], streams[1], mcp.create_initialization_options()
        )


async def handle_health(request: Request):
    """Health check endpoint."""
    return JSONResponse({"status": "healthy", "service": "redwire-mcp"})


app = Starlette(
    debug=False,
    routes=[
        Route("/health", handle_health),
        Route("/sse", handle_sse),
        Mount("/messages/", app=sse.handle_post_message),
    ],
    middleware=[
        Middleware(
            CORSMiddleware,
            # Never reflect "*" — that plus allow_credentials lets any web
            # page drive this server from a victim's browser. If CORS_ORIGINS
            # is unset, no cross-origin browser access is granted.
            allow_origins=CORS_ORIGINS,
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type"],
        ),
    ],
)


if __name__ == "__main__":
    import uvicorn

    logger.info(f"🚀 RedWire MCP Server starting on port {MCP_PORT}")
    logger.info(f"   API URL: {REDWIRE_API_URL}")
    logger.info(f"   SSE endpoint: http://0.0.0.0:{MCP_PORT}/sse")
    logger.info("   Auth: every client must send Authorization: Bearer "
                "<jwt-or-api-token>")

    uvicorn.run(app, host="0.0.0.0", port=MCP_PORT)
