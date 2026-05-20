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
import logging
import contextvars
from typing import Any

import httpx
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent
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


@mcp.list_tools()
async def list_tools() -> list[Tool]:
    """Return all available RedWire tools."""
    return [
        # ── Engagements ──────────────────────────────────────────────
        Tool(
            name="list_engagements",
            description="List all penetration test engagements. Optionally filter by status (active, completed, planned, cancelled).",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "Filter by status: active, completed, planned, cancelled",
                        "enum": ["active", "completed", "planned", "cancelled"],
                    },
                },
            },
        ),
        Tool(
            name="get_engagement",
            description="Get detailed information about a specific engagement by its ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "engagement_id": {"type": "string", "description": "The engagement UUID"},
                },
                "required": ["engagement_id"],
            },
        ),

        # ── Findings ─────────────────────────────────────────────────
        Tool(
            name="list_findings",
            description="List vulnerability findings for a specific engagement. Returns title, severity, status, and category.",
            inputSchema={
                "type": "object",
                "properties": {
                    "engagement_id": {"type": "string", "description": "The engagement UUID"},
                },
                "required": ["engagement_id"],
            },
        ),
        Tool(
            name="get_finding",
            description="Get full details of a specific finding including description, impact, steps to reproduce, mitigations, and affected assets.",
            inputSchema={
                "type": "object",
                "properties": {
                    "finding_id": {"type": "string", "description": "The finding UUID"},
                    "engagement_id": {"type": "string", "description": "The engagement UUID"},
                },
                "required": ["finding_id", "engagement_id"],
            },
        ),
        Tool(
            name="create_finding",
            description="Create a new vulnerability finding in an engagement. Requires at least a title and severity.",
            inputSchema={
                "type": "object",
                "properties": {
                    "engagement_id": {"type": "string", "description": "The engagement UUID"},
                    "title": {"type": "string", "description": "Finding title"},
                    "severity": {
                        "type": "string",
                        "description": "Severity level",
                        "enum": ["critical", "high", "medium", "low", "informational"],
                    },
                    "description": {"type": "string", "description": "Detailed description (markdown)"},
                    "impact": {"type": "string", "description": "Business/technical impact (markdown)"},
                    "mitigations": {"type": "string", "description": "Recommended remediation (markdown)"},
                    "category": {"type": "string", "description": "Finding category"},
                },
                "required": ["engagement_id", "title", "severity"],
            },
        ),
        Tool(
            name="update_finding",
            description="Update fields on an existing finding. Only specified fields are changed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "finding_id": {"type": "string", "description": "The finding UUID"},
                    "engagement_id": {"type": "string", "description": "The engagement UUID"},
                    "title": {"type": "string", "description": "New title"},
                    "severity": {"type": "string", "enum": ["critical", "high", "medium", "low", "informational"]},
                    "status": {"type": "string", "description": "New status"},
                    "description": {"type": "string", "description": "Updated description (markdown)"},
                    "impact": {"type": "string", "description": "Updated impact (markdown)"},
                    "mitigations": {"type": "string", "description": "Updated mitigations (markdown)"},
                },
                "required": ["finding_id", "engagement_id"],
            },
        ),

        # ── Assets ───────────────────────────────────────────────────
        Tool(
            name="list_assets",
            description="List target assets for a specific engagement. Returns hostname/IP, type, and status.",
            inputSchema={
                "type": "object",
                "properties": {
                    "engagement_id": {"type": "string", "description": "The engagement UUID"},
                },
                "required": ["engagement_id"],
            },
        ),
        Tool(
            name="get_asset",
            description="Get full details of a specific asset including ports, linked findings, and metadata.",
            inputSchema={
                "type": "object",
                "properties": {
                    "asset_id": {"type": "string", "description": "The asset UUID"},
                    "engagement_id": {"type": "string", "description": "The engagement UUID"},
                },
                "required": ["asset_id", "engagement_id"],
            },
        ),
        Tool(
            name="create_asset",
            description="Create a new target asset in an engagement. Requires at least a name and asset_type.",
            inputSchema={
                "type": "object",
                "properties": {
                    "engagement_id": {"type": "string", "description": "The engagement UUID"},
                    "name": {"type": "string", "description": "Asset name (hostname, IP, URL, etc.)"},
                    "asset_type": {
                        "type": "string",
                        "description": "Type of asset",
                        "enum": ["IP_ADDRESS", "DOMAIN", "URL", "APPLICATION", "SERVER", "NETWORK", "OTHER"],
                    },
                    "description": {"type": "string", "description": "Optional description"},
                    "os": {"type": "string", "description": "Operating system"},
                    "in_scope": {"type": "boolean", "description": "Whether asset is in scope (default true)"},
                },
                "required": ["engagement_id", "name", "asset_type"],
            },
        ),
        Tool(
            name="update_asset",
            description="Update fields on an existing asset. Only specified fields are changed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "asset_id": {"type": "string", "description": "The asset UUID"},
                    "engagement_id": {"type": "string", "description": "The engagement UUID"},
                    "name": {"type": "string", "description": "Updated name"},
                    "asset_type": {"type": "string", "enum": ["IP_ADDRESS", "DOMAIN", "URL", "APPLICATION", "SERVER", "NETWORK", "OTHER"]},
                    "description": {"type": "string", "description": "Updated description"},
                    "os": {"type": "string", "description": "Updated OS"},
                    "in_scope": {"type": "boolean", "description": "Updated scope status"},
                },
                "required": ["asset_id", "engagement_id"],
            },
        ),

        # ── Test Cases ───────────────────────────────────────────────
        Tool(
            name="list_testcases",
            description="List test cases for a specific engagement. Returns title, category, status, and result.",
            inputSchema={
                "type": "object",
                "properties": {
                    "engagement_id": {"type": "string", "description": "The engagement UUID"},
                },
                "required": ["engagement_id"],
            },
        ),
        Tool(
            name="get_testcase",
            description="Get full details of a specific test case including steps, expected result, and linked findings.",
            inputSchema={
                "type": "object",
                "properties": {
                    "testcase_id": {"type": "string", "description": "The test case UUID"},
                    "engagement_id": {"type": "string", "description": "The engagement UUID"},
                },
                "required": ["testcase_id", "engagement_id"],
            },
        ),
        Tool(
            name="create_testcase",
            description="Create a new test case in an engagement. Requires at least a title.",
            inputSchema={
                "type": "object",
                "properties": {
                    "engagement_id": {"type": "string", "description": "The engagement UUID"},
                    "title": {"type": "string", "description": "Test case title"},
                    "category": {"type": "string", "description": "Category (e.g. Reconnaissance, Exploitation)"},
                    "description": {"type": "string", "description": "Detailed description (markdown)"},
                    "steps": {"type": "string", "description": "Test steps (markdown)"},
                    "expected_result": {"type": "string", "description": "Expected outcome (markdown)"},
                    "parent_id": {"type": "string", "description": "Parent test case UUID for nesting"},
                },
                "required": ["engagement_id", "title"],
            },
        ),
        Tool(
            name="update_testcase",
            description="Update fields on an existing test case. Only specified fields are changed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "testcase_id": {"type": "string", "description": "The test case UUID"},
                    "engagement_id": {"type": "string", "description": "The engagement UUID"},
                    "title": {"type": "string", "description": "Updated title"},
                    "category": {"type": "string", "description": "Updated category"},
                    "description": {"type": "string", "description": "Updated description (markdown)"},
                    "steps": {"type": "string", "description": "Updated steps (markdown)"},
                    "expected_result": {"type": "string", "description": "Updated expected result (markdown)"},
                    "status": {"type": "string", "description": "Updated status"},
                    "result": {"type": "string", "description": "Updated result"},
                },
                "required": ["testcase_id", "engagement_id"],
            },
        ),

        # ── Notes ────────────────────────────────────────────────────
        Tool(
            name="list_notes",
            description="List notes for a specific engagement.",
            inputSchema={
                "type": "object",
                "properties": {
                    "engagement_id": {"type": "string", "description": "The engagement UUID"},
                },
                "required": ["engagement_id"],
            },
        ),
        Tool(
            name="get_note",
            description="Get full details of a specific note including content and linked resources.",
            inputSchema={
                "type": "object",
                "properties": {
                    "note_id": {"type": "string", "description": "The note UUID"},
                },
                "required": ["note_id"],
            },
        ),
        Tool(
            name="create_note",
            description="Create a new note in an engagement.",
            inputSchema={
                "type": "object",
                "properties": {
                    "engagement_id": {"type": "string", "description": "The engagement UUID"},
                    "title": {"type": "string", "description": "Note title"},
                    "content": {"type": "string", "description": "Note content (markdown)"},
                },
                "required": ["engagement_id", "title"],
            },
        ),
        Tool(
            name="update_note",
            description="Update a note's title or content.",
            inputSchema={
                "type": "object",
                "properties": {
                    "note_id": {"type": "string", "description": "The note UUID"},
                    "title": {"type": "string", "description": "Updated title"},
                    "content": {"type": "string", "description": "Updated content (markdown)"},
                },
                "required": ["note_id"],
            },
        ),

        # ── Vault ────────────────────────────────────────────────────
        Tool(
            name="list_vault_items",
            description="List vault items (credentials, keys, secrets) for a specific engagement.",
            inputSchema={
                "type": "object",
                "properties": {
                    "engagement_id": {"type": "string", "description": "The engagement UUID"},
                },
                "required": ["engagement_id"],
            },
        ),
        Tool(
            name="create_vault_item",
            description="Create a new vault item (credential, key, or note) in an engagement.",
            inputSchema={
                "type": "object",
                "properties": {
                    "engagement_id": {"type": "string", "description": "The engagement UUID"},
                    "name": {"type": "string", "description": "Item name / label"},
                    "item_type": {
                        "type": "string",
                        "description": "Type of vault item",
                        "enum": ["Credential", "Key", "File", "Note"],
                    },
                    "username": {"type": "string", "description": "Username (for credentials)"},
                    "password": {"type": "string", "description": "Password (for credentials)"},
                    "url": {"type": "string", "description": "Associated URL"},
                    "notes": {"type": "string", "description": "Additional notes"},
                },
                "required": ["engagement_id", "name", "item_type"],
            },
        ),
        Tool(
            name="update_vault_item",
            description="Update fields on an existing vault item. Only specified fields are changed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "item_id": {"type": "string", "description": "The vault item UUID"},
                    "engagement_id": {"type": "string", "description": "The engagement UUID"},
                    "name": {"type": "string", "description": "Updated name"},
                    "username": {"type": "string", "description": "Updated username"},
                    "password": {"type": "string", "description": "Updated password"},
                    "url": {"type": "string", "description": "Updated URL"},
                    "notes": {"type": "string", "description": "Updated notes"},
                },
                "required": ["item_id", "engagement_id"],
            },
        ),

        # ── Cleanup Artifacts ────────────────────────────────────────
        Tool(
            name="list_cleanup_artifacts",
            description="List cleanup artifacts (files, accounts, backdoors to remove) for an engagement.",
            inputSchema={
                "type": "object",
                "properties": {
                    "engagement_id": {"type": "string", "description": "The engagement UUID"},
                },
                "required": ["engagement_id"],
            },
        ),
        Tool(
            name="get_cleanup_artifact",
            description="Get full details of a specific cleanup artifact.",
            inputSchema={
                "type": "object",
                "properties": {
                    "artifact_id": {"type": "string", "description": "The cleanup artifact UUID"},
                    "engagement_id": {"type": "string", "description": "The engagement UUID"},
                },
                "required": ["artifact_id", "engagement_id"],
            },
        ),
        Tool(
            name="create_cleanup_artifact",
            description="Create a new cleanup artifact in an engagement.",
            inputSchema={
                "type": "object",
                "properties": {
                    "engagement_id": {"type": "string", "description": "The engagement UUID"},
                    "title": {"type": "string", "description": "Artifact title"},
                    "artifact_type": {
                        "type": "string",
                        "description": "Type of cleanup item",
                        "enum": ["SSH Key", "File", "Account", "Permission", "Backdoor", "Implant", "Other"],
                    },
                    "location": {"type": "string", "description": "Where the artifact is located"},
                    "description": {"type": "string", "description": "Details about the artifact"},
                },
                "required": ["engagement_id", "title", "artifact_type"],
            },
        ),
        Tool(
            name="update_cleanup_artifact",
            description="Update fields on an existing cleanup artifact. Only specified fields are changed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "artifact_id": {"type": "string", "description": "The cleanup artifact UUID"},
                    "engagement_id": {"type": "string", "description": "The engagement UUID"},
                    "title": {"type": "string", "description": "Updated title"},
                    "location": {"type": "string", "description": "Updated location"},
                    "description": {"type": "string", "description": "Updated description"},
                    "status": {"type": "string", "description": "Updated status (pending, completed)"},
                },
                "required": ["artifact_id", "engagement_id"],
            },
        ),

        # ── Finding Templates ────────────────────────────────────────
        Tool(
            name="list_finding_templates",
            description="List all finding templates. These are reusable vulnerability definitions that can be applied to engagements.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="get_finding_template",
            description="Get full details of a specific finding template.",
            inputSchema={
                "type": "object",
                "properties": {
                    "template_id": {"type": "string", "description": "The template UUID"},
                },
                "required": ["template_id"],
            },
        ),
        Tool(
            name="create_finding_template",
            description="Create a new finding template for reuse across engagements.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Template title"},
                    "severity": {
                        "type": "string",
                        "description": "Default severity level",
                        "enum": ["critical", "high", "medium", "low", "informational"],
                    },
                    "description": {"type": "string", "description": "Description (markdown)"},
                    "impact": {"type": "string", "description": "Impact statement (markdown)"},
                    "mitigations": {"type": "string", "description": "Remediation steps (markdown)"},
                    "category": {"type": "string", "description": "Finding category"},
                },
                "required": ["title", "severity"],
            },
        ),
        Tool(
            name="update_finding_template",
            description="Update fields on an existing finding template.",
            inputSchema={
                "type": "object",
                "properties": {
                    "template_id": {"type": "string", "description": "The template UUID"},
                    "title": {"type": "string", "description": "Updated title"},
                    "severity": {"type": "string", "enum": ["critical", "high", "medium", "low", "informational"]},
                    "description": {"type": "string", "description": "Updated description (markdown)"},
                    "impact": {"type": "string", "description": "Updated impact (markdown)"},
                    "mitigations": {"type": "string", "description": "Updated mitigations (markdown)"},
                    "category": {"type": "string", "description": "Updated category"},
                },
                "required": ["template_id"],
            },
        ),

        # ── Test Case Templates ──────────────────────────────────────
        Tool(
            name="list_testcase_templates",
            description="List all test case templates. These are reusable test procedures for engagements.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="get_testcase_template",
            description="Get full details of a specific test case template.",
            inputSchema={
                "type": "object",
                "properties": {
                    "template_id": {"type": "string", "description": "The template UUID"},
                },
                "required": ["template_id"],
            },
        ),
        Tool(
            name="create_testcase_template",
            description="Create a new test case template for reuse across engagements.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Template title"},
                    "category": {"type": "string", "description": "Category (e.g. Reconnaissance, Exploitation)"},
                    "description": {"type": "string", "description": "Description (markdown)"},
                    "steps": {"type": "string", "description": "Test steps (markdown)"},
                    "expected_result": {"type": "string", "description": "Expected outcome (markdown)"},
                },
                "required": ["title"],
            },
        ),
        Tool(
            name="update_testcase_template",
            description="Update fields on an existing test case template.",
            inputSchema={
                "type": "object",
                "properties": {
                    "template_id": {"type": "string", "description": "The template UUID"},
                    "title": {"type": "string", "description": "Updated title"},
                    "category": {"type": "string", "description": "Updated category"},
                    "description": {"type": "string", "description": "Updated description (markdown)"},
                    "steps": {"type": "string", "description": "Updated steps (markdown)"},
                    "expected_result": {"type": "string", "description": "Updated expected result (markdown)"},
                },
                "required": ["template_id"],
            },
        ),

        # ── Search ───────────────────────────────────────────────────
        Tool(
            name="search",
            description="Global search across all resources (engagements, findings, assets, test cases, notes). Returns matching items with type, title, and context.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query string"},
                },
                "required": ["query"],
            },
        ),

        # ── Stats ────────────────────────────────────────────────────
        Tool(
            name="get_engagement_stats",
            description="Get statistics for a specific engagement: finding counts by severity, test case progress, asset count, and remediation status.",
            inputSchema={
                "type": "object",
                "properties": {
                    "engagement_id": {"type": "string", "description": "The engagement UUID"},
                },
                "required": ["engagement_id"],
            },
        ),
        Tool(
            name="get_global_stats",
            description="Get platform-wide statistics: total engagements, findings, assets, and severity breakdowns.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),

        # ── AI ────────────────────────────────────────────────────
        Tool(
            name="ai_chat",
            description="Send a message to the built-in AI assistant for cybersecurity advice. Provide context about what you're working on.",
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "The message/question to send"},
                    "editor_content": {"type": "string", "description": "Optional: current editor content for context"},
                    "field_context": {
                        "type": "object",
                        "description": "Optional: field context (resourceType, fieldName)",
                        "properties": {
                            "resourceType": {"type": "string"},
                            "fieldName": {"type": "string"},
                        },
                    },
                },
                "required": ["message"],
            },
        ),
    ]


@mcp.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Dispatch tool calls to the appropriate handler."""
    try:
        result = await _dispatch(name, arguments)
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
    except httpx.HTTPStatusError as e:
        error_body = e.response.text
        return [TextContent(type="text", text=f"API Error {e.response.status_code}: {error_body}")]
    except Exception as e:
        logger.exception(f"Tool {name} failed")
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def _dispatch(name: str, args: dict[str, Any]) -> Any:
    """Route tool calls to RedWire API endpoints."""

    # ── Engagements ──────────────────────────────────────────────────
    if name == "list_engagements":
        params = {}
        if args.get("status"):
            params["status"] = args["status"]
        return await _api_get("/engagements", params=params)

    elif name == "get_engagement":
        return await _api_get(f"/engagements/{args['engagement_id']}")

    # ── Findings ─────────────────────────────────────────────────────
    elif name == "list_findings":
        return await _api_get("/findings", params={"engagement_id": args["engagement_id"]})

    elif name == "get_finding":
        return await _api_get(
            f"/findings/{args['finding_id']}",
            params={"engagement_id": args["engagement_id"]},
        )

    elif name == "create_finding":
        eid = args.pop("engagement_id")
        return await _api_post(f"/findings?engagement_id={eid}", data=args)

    elif name == "update_finding":
        fid = args.pop("finding_id")
        eid = args.pop("engagement_id")
        return await _api_put(f"/findings/{fid}?engagement_id={eid}", data=args)

    # ── Assets ───────────────────────────────────────────────────────
    elif name == "list_assets":
        return await _api_get("/assets", params={"engagement_id": args["engagement_id"]})

    elif name == "get_asset":
        return await _api_get(
            f"/assets/{args['asset_id']}",
            params={"engagement_id": args["engagement_id"]},
        )

    elif name == "create_asset":
        eid = args.pop("engagement_id")
        return await _api_post(f"/assets?engagement_id={eid}", data=args)

    elif name == "update_asset":
        aid = args.pop("asset_id")
        eid = args.pop("engagement_id")
        return await _api_put(f"/assets/{aid}?engagement_id={eid}", data=args)

    # ── Test Cases ───────────────────────────────────────────────────
    elif name == "list_testcases":
        return await _api_get("/testcases", params={"engagement_id": args["engagement_id"]})

    elif name == "get_testcase":
        return await _api_get(
            f"/testcases/{args['testcase_id']}",
            params={"engagement_id": args["engagement_id"]},
        )

    elif name == "create_testcase":
        eid = args.pop("engagement_id")
        return await _api_post(f"/testcases?engagement_id={eid}", data=args)

    elif name == "update_testcase":
        tid = args.pop("testcase_id")
        eid = args.pop("engagement_id")
        return await _api_put(f"/testcases/{tid}?engagement_id={eid}", data=args)

    # ── Notes ────────────────────────────────────────────────────────
    elif name == "list_notes":
        return await _api_get(f"/engagements/{args['engagement_id']}/notes")

    elif name == "get_note":
        return await _api_get(f"/notes/{args['note_id']}")

    elif name == "create_note":
        eid = args.pop("engagement_id")
        return await _api_post(f"/engagements/{eid}/notes", data=args)

    elif name == "update_note":
        nid = args.pop("note_id")
        return await _api_patch(f"/notes/{nid}", data=args)

    # ── Vault ────────────────────────────────────────────────────────
    elif name == "list_vault_items":
        return await _api_get("/vault", params={"engagement_id": args["engagement_id"]})

    elif name == "create_vault_item":
        eid = args.pop("engagement_id")
        return await _api_post(f"/vault?engagement_id={eid}", data=args)

    elif name == "update_vault_item":
        iid = args.pop("item_id")
        eid = args.pop("engagement_id")
        return await _api_patch(f"/vault/{iid}?engagement_id={eid}", data=args)

    # ── Cleanup Artifacts ────────────────────────────────────────────
    elif name == "list_cleanup_artifacts":
        return await _api_get("/cleanup-artifacts", params={"engagement_id": args["engagement_id"]})

    elif name == "get_cleanup_artifact":
        return await _api_get(
            f"/cleanup-artifacts/{args['artifact_id']}",
            params={"engagement_id": args["engagement_id"]},
        )

    elif name == "create_cleanup_artifact":
        eid = args.pop("engagement_id")
        return await _api_post(f"/cleanup-artifacts?engagement_id={eid}", data=args)

    elif name == "update_cleanup_artifact":
        aid = args.pop("artifact_id")
        eid = args.pop("engagement_id")
        return await _api_patch(f"/cleanup-artifacts/{aid}?engagement_id={eid}", data=args)

    # ── Finding Templates ────────────────────────────────────────────
    elif name == "list_finding_templates":
        return await _api_get("/templates")

    elif name == "get_finding_template":
        return await _api_get(f"/templates/{args['template_id']}")

    elif name == "create_finding_template":
        return await _api_post("/templates", data=args)

    elif name == "update_finding_template":
        tid = args.pop("template_id")
        return await _api_put(f"/templates/{tid}", data=args)

    # ── Test Case Templates ──────────────────────────────────────────
    elif name == "list_testcase_templates":
        return await _api_get("/testcase-templates")

    elif name == "get_testcase_template":
        return await _api_get(f"/testcase-templates/{args['template_id']}")

    elif name == "create_testcase_template":
        return await _api_post("/testcase-templates", data=args)

    elif name == "update_testcase_template":
        tid = args.pop("template_id")
        return await _api_put(f"/testcase-templates/{tid}", data=args)

    # ── Search ───────────────────────────────────────────────────────
    elif name == "search":
        return await _api_get("/search", params={"q": args["query"]})

    # ── Stats ────────────────────────────────────────────────────────
    elif name == "get_engagement_stats":
        return await _api_get(f"/stats/engagement/{args['engagement_id']}")

    elif name == "get_global_stats":
        return await _api_get("/stats/global")

    # ── AI ────────────────────────────────────────────────────────────
    elif name == "ai_chat":
        payload = {
            "messages": [{"role": "user", "content": args["message"]}],
        }
        if args.get("editor_content"):
            payload["editor_content"] = args["editor_content"]
        if args.get("field_context"):
            payload["field_context"] = args["field_context"]

        # Non-streaming for MCP — collect full response
        async with httpx.AsyncClient(base_url=REDWIRE_API_URL, timeout=120) as client:
            resp = await client.post("/ai/chat", headers=_headers(), json=payload)
            resp.raise_for_status()
            # Response is SSE stream, collect text
            full_text = ""
            for line in resp.text.split("\n"):
                if line.startswith("data: "):
                    chunk = line[6:]
                    if chunk == "[DONE]":
                        break
                    try:
                        data = json.loads(chunk)
                        delta = data.get("choices", [{}])[0].get("delta", {})
                        full_text += delta.get("content", "")
                    except json.JSONDecodeError:
                        continue
            return {"response": full_text}

    else:
        raise ValueError(f"Unknown tool: {name}")


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
