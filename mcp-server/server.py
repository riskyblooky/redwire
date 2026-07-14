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

# ── Enum mirrors ─────────────────────────────────────────────────────────────
#
# Hand-kept copies of the backend enums. The MCP server is a separate
# container and can't import backend models — if you change an enum in
# backend/models/, change it here too.
#
# These are advertised to the model in the tool schemas, so a wrong value
# here is not cosmetic: the model is *constrained* to whatever we list, and
# every value it picks then fails. Historically all of these were lowercase
# and/or invented ("active", "planned", "informational", "blog"), so any
# tool call carrying one of these filters failed 100% of the time — either
# a 422 from the backend's Pydantic layer, or (for list_engagements, which
# the in-app chatbot runs against the DB directly) an asyncpg
# InvalidTextRepresentationError. Postgres enum values are UPPERCASE.
ENGAGEMENT_STATUSES = (
    "PROPOSED",
    "SCOPING",
    "PLANNING",
    "IN_PROGRESS",
    "REPORTING",
    "COMPLETED",
    "ON_HOLD",
)
# models/finding.py :: Severity — note INFO, not "informational".
SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")
# models/finding.py :: FindingStatus
FINDING_STATUSES = ("OPEN", "IN_REVIEW", "VERIFIED", "REMEDIATED", "CLOSED")
# models/cleanup_artifact.py :: CleanupArtifactStatus — there is no "completed".
CLEANUP_STATUSES = ("PENDING", "CLEANED", "PARTIALLY_CLEANED", "NOT_APPLICABLE")
# models/intel_item.py :: IntelItemType — there is no "blog" or "news".
INTEL_ITEM_TYPES = ("CVE", "ADVISORY", "ARTICLE", "ZINE", "EXPLOIT", "OTHER")

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


# Fields whose legal values are NOT a Postgres enum but rows in the
# admin-editable `configurable_types` taxonomy (the same list the UI
# dropdowns are built from). Hardcoding these drifts the moment an admin
# edits the taxonomy — asset_type was advertised as IP_ADDRESS/DOMAIN
# while the taxonomy actually said "IP Address"/"Domain", so the model
# created assets whose type matched no dropdown option. Resolve them live
# instead.
_TAXONOMY_FIELDS: dict[tuple[str, str], str] = {
    ("create_asset", "asset_type"): "asset",
    ("update_asset", "asset_type"): "asset",
    ("create_vault_item", "item_type"): "vault",
    ("create_cleanup_artifact", "artifact_type"): "cleanup",
}


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


async def _apply_taxonomy_enums(tools: list[Tool]) -> None:
    """Overlay live taxonomy values onto the taxonomy-backed enum fields."""
    cache: dict[str, list[str] | None] = {}
    for tool in tools:
        props = (tool.inputSchema or {}).get("properties") or {}
        for field, spec in props.items():
            category = _TAXONOMY_FIELDS.get((tool.name, field))
            if not category:
                continue
            if category not in cache:
                cache[category] = await _taxonomy_values(category)
            values = cache[category]
            if values:
                spec["enum"] = values
            else:
                # Taxonomy unreadable — drop the stale hardcoded enum so the
                # model isn't forced to pick a value we can't vouch for.
                spec.pop("enum", None)


@mcp.list_tools()
async def list_tools() -> list[Tool]:
    """Return all available RedWire tools. Write tools are filtered out when
    the admin toggle ai_write_tools_enabled is off (the default)."""
    tools = _all_tools()
    if not await _write_tools_enabled():
        tools = [t for t in tools if not _is_write_tool(t.name)]
    await _apply_taxonomy_enums(tools)
    return tools


def _all_tools() -> list[Tool]:
    return [
        # ── Engagements ──────────────────────────────────────────────
        Tool(
            name="list_engagements",
            description=(
                "List all penetration test engagements. Optionally filter by status. "
                f"Valid statuses: {', '.join(ENGAGEMENT_STATUSES)}."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": (
                            "Filter by engagement status. Must be one of: "
                            f"{', '.join(ENGAGEMENT_STATUSES)}."
                        ),
                        "enum": list(ENGAGEMENT_STATUSES),
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
                        "enum": list(SEVERITIES),
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
                    "severity": {"type": "string", "enum": list(SEVERITIES)},
                    "status": {"type": "string", "description": "New finding status", "enum": list(FINDING_STATUSES)},
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
                    "status": {"type": "string", "description": "Updated cleanup status", "enum": list(CLEANUP_STATUSES)},
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
                        "enum": list(SEVERITIES),
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
                    "severity": {"type": "string", "enum": list(SEVERITIES)},
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

        # ── Delete Operations ────────────────────────────────────────
        Tool(
            name="delete_finding",
            description="Permanently delete a finding from an engagement. Irreversible.",
            inputSchema={
                "type": "object",
                "properties": {
                    "finding_id": {"type": "string", "description": "The finding UUID"},
                    "engagement_id": {"type": "string", "description": "The engagement UUID (scope confirmation)"},
                },
                "required": ["finding_id", "engagement_id"],
            },
        ),
        Tool(
            name="delete_asset",
            description="Permanently delete an asset from an engagement. Irreversible.",
            inputSchema={
                "type": "object",
                "properties": {
                    "asset_id": {"type": "string", "description": "The asset UUID"},
                    "engagement_id": {"type": "string", "description": "The engagement UUID (scope confirmation)"},
                },
                "required": ["asset_id", "engagement_id"],
            },
        ),
        Tool(
            name="delete_testcase",
            description="Permanently delete a test case from an engagement. Optionally cascade to child test cases.",
            inputSchema={
                "type": "object",
                "properties": {
                    "testcase_id": {"type": "string", "description": "The test case UUID"},
                    "engagement_id": {"type": "string", "description": "The engagement UUID (scope confirmation)"},
                    "cascade": {"type": "boolean", "description": "If true, also delete all child test cases recursively (default false)"},
                },
                "required": ["testcase_id", "engagement_id"],
            },
        ),
        Tool(
            name="delete_note",
            description="Permanently delete a note. Irreversible.",
            inputSchema={
                "type": "object",
                "properties": {
                    "note_id": {"type": "string", "description": "The note UUID"},
                },
                "required": ["note_id"],
            },
        ),
        Tool(
            name="get_vault_item",
            description="Get a single vault item by ID. Returns metadata only (no plaintext credentials); call the reveal endpoint via the UI to fetch decrypted secrets with audit logging.",
            inputSchema={
                "type": "object",
                "properties": {
                    "item_id": {"type": "string", "description": "The vault item UUID"},
                },
                "required": ["item_id"],
            },
        ),
        Tool(
            name="delete_vault_item",
            description="Permanently delete a vault item from an engagement. Irreversible — credential cannot be recovered.",
            inputSchema={
                "type": "object",
                "properties": {
                    "item_id": {"type": "string", "description": "The vault item UUID"},
                    "engagement_id": {"type": "string", "description": "The engagement UUID (scope confirmation)"},
                },
                "required": ["item_id", "engagement_id"],
            },
        ),
        Tool(
            name="delete_cleanup_artifact",
            description="Permanently delete a cleanup artifact from an engagement. Irreversible.",
            inputSchema={
                "type": "object",
                "properties": {
                    "artifact_id": {"type": "string", "description": "The cleanup artifact UUID"},
                    "engagement_id": {"type": "string", "description": "The engagement UUID (scope confirmation)"},
                },
                "required": ["artifact_id", "engagement_id"],
            },
        ),

        # ── Threat Intelligence (read-only) ──────────────────────────
        Tool(
            name="list_intel_items",
            description="List threat intelligence items (CVEs, advisories, blog posts, news). Supports search across title/CVE/content, type and severity filters, sorting, and pagination.",
            inputSchema={
                "type": "object",
                "properties": {
                    "search": {"type": "string", "description": "Search across title, CVE ID, and content"},
                    "item_type": {"type": "string", "description": "Filter by intel item type", "enum": list(INTEL_ITEM_TYPES)},
                    "severity": {"type": "string", "description": "Filter by severity", "enum": list(SEVERITIES)},
                    "sort_by": {
                        "type": "string",
                        "enum": ["title", "created_at", "published_at", "item_type", "severity", "source"],
                        "description": "Sort column (default created_at)",
                    },
                    "sort_dir": {"type": "string", "enum": ["asc", "desc"], "description": "Sort direction (default desc)"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 500, "description": "Page size (default 50, max 500)"},
                    "offset": {"type": "integer", "minimum": 0, "description": "Page offset (default 0)"},
                },
            },
        ),
        Tool(
            name="get_intel_item",
            description="Get full details of a single threat-intel item, including attachments and linked findings/assets/test cases.",
            inputSchema={
                "type": "object",
                "properties": {
                    "item_id": {"type": "string", "description": "The intel item UUID"},
                },
                "required": ["item_id"],
            },
        ),
        Tool(
            name="list_intel_for_entity",
            description="List all threat-intel items that have been linked to a specific finding, test case, or note in RedWire. For free-form lookups like 'is there intel about CVE-2023-12345?' use list_intel_items with a search query instead.",
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_type": {
                        "type": "string",
                        "enum": ["finding", "testcase", "note"],
                        "description": "Which kind of RedWire resource the intel is linked to",
                    },
                    "entity_id": {"type": "string", "description": "The UUID of the finding / test case / note"},
                },
                "required": ["entity_type", "entity_id"],
            },
        ),
        Tool(
            name="list_intel_feeds",
            description="List configured threat-intel feed sources (RSS, CVE feeds, etc.) with their refresh status.",
            inputSchema={"type": "object", "properties": {}},
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


# GHSA-q4x9-5gmc-fxh5: untrusted-data envelope mirrors the in-backend ai.py
# loop so an MCP client agent sees the same sentinels and can apply the same
# system-prompt instruction to ignore embedded commands.
_TOOL_DATA_BEGIN = "<<<REDWIRE_UNTRUSTED_TOOL_DATA_BEGIN>>>"
_TOOL_DATA_END = "<<<REDWIRE_UNTRUSTED_TOOL_DATA_END>>>"


def _wrap_untrusted(payload: str) -> str:
    safe = (payload or "").replace(_TOOL_DATA_BEGIN, "").replace(_TOOL_DATA_END, "")
    return f"{_TOOL_DATA_BEGIN}\n{safe}\n{_TOOL_DATA_END}"


@mcp.call_tool()
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


_UUID_ARG_KEYS = (
    "engagement_id", "finding_id", "asset_id", "testcase_id", "note_id",
    "vault_item_id", "cleanup_artifact_id", "template_id", "user_id",
)


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


def _validate_uuid_args(args: dict[str, Any]) -> None:
    """GHSA-q4x9-5gmc-fxh5: every *_id argument is interpolated into a backend
    URL path. A model-supplied value containing '..' (or just a non-UUID path
    fragment) would traverse to unintended routes. Validate as UUID before
    any URL interpolation."""
    import uuid as _uuid
    for k in _UUID_ARG_KEYS:
        v = args.get(k)
        if v is None or v == "":
            continue
        if not isinstance(v, str):
            raise ValueError(f"argument {k!r} must be a UUID string")
        try:
            _uuid.UUID(v)
        except (ValueError, AttributeError):
            raise ValueError(f"argument {k!r}={v!r} is not a valid UUID")


async def _dispatch(name: str, args: dict[str, Any]) -> Any:
    """Route tool calls to RedWire API endpoints."""
    _validate_uuid_args(args)

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
        items = await _api_get("/vault", params={"engagement_id": args["engagement_id"]})
        # GHSA-q4x9-5gmc-fxh5 (b1): never return plaintext secrets to the
        # LLM. An injected description that drove a vault read could otherwise
        # exfiltrate credentials to the model context.
        return _redact_vault_secrets(items)

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

    # ── Delete Operations ────────────────────────────────────────────
    # The DELETE endpoints don't read engagement_id from the URL — the
    # row's own engagement_id drives the backend's permission check — but
    # we keep it in the tool schema as scope confirmation for the LLM.
    elif name == "delete_finding":
        return await _api_delete(f"/findings/{args['finding_id']}")

    elif name == "delete_asset":
        return await _api_delete(f"/assets/{args['asset_id']}")

    elif name == "delete_testcase":
        path = f"/testcases/{args['testcase_id']}"
        if args.get("cascade"):
            path += "?cascade=true"
        return await _api_delete(path)

    elif name == "delete_note":
        return await _api_delete(f"/notes/{args['note_id']}")

    elif name == "get_vault_item":
        return await _api_get(f"/vault/{args['item_id']}")

    elif name == "delete_vault_item":
        return await _api_delete(f"/vault/{args['item_id']}")

    elif name == "delete_cleanup_artifact":
        return await _api_delete(f"/cleanup-artifacts/{args['artifact_id']}")

    # ── Threat Intelligence (read-only) ──────────────────────────────
    elif name == "list_intel_items":
        params = {k: v for k, v in args.items() if v is not None}
        return await _api_get("/intel/items", params=params)

    elif name == "get_intel_item":
        return await _api_get(f"/intel/items/{args['item_id']}")

    elif name == "list_intel_for_entity":
        return await _api_get(
            "/intel/by-entity",
            params={"entity_type": args["entity_type"], "entity_id": args["entity_id"]},
        )

    elif name == "list_intel_feeds":
        return await _api_get("/intel/feeds")

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
