from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from rate_limit import limiter
import os
import asyncio
from contextlib import asynccontextmanager

# Import database
from database import Base, engine

# Import routers
from routers import auth, engagements, engagements_transfer, findings, users, assets, testcases, calendar, analytics, reports, admin, websocket, stats, templates, discussions, evidence, vault, testcase_templates, permissions, notes, tags, runbooks, report_layouts, report_layout_templates, report_themes, clients, cleanup_artifacts, auth_settings, api_tokens, configurable_types, search, attack_graph, wordlist, notifications, automations, ai, intel, infra, skills, dashboard_widgets, plugins as plugins_router
from routers import imports as imports_router
from routers import spray as spray_router
from routers import attack_techniques as attack_techniques_router
from routers import markdown_images as markdown_images_router
from plugin_loader import plugin_registry
from utils.event_bus import event_bus

# OpenAPI tag descriptions for /docs
openapi_tags = [
    # ── Core ──────────────────────────────────────────────────────────
    {"name": "authentication", "description": "Login, registration, token refresh, logout, 2FA (TOTP), and SAML SSO"},
    {"name": "users", "description": "User profile and account management"},
    {"name": "admin", "description": "User administration, role management, registration codes"},
    {"name": "permissions", "description": "Groups, roles, and RBAC management"},
    {"name": "api-tokens", "description": "Long-lived API tokens for scripting and automation. Supports read-only (ro) and read-write (rw) permissions"},
    {"name": "admin-auth-settings", "description": "LDAP and SAML SSO configuration (admin only)"},

    # ── Engagements & Resources ──────────────────────────────────────
    {"name": "engagements", "description": "Penetration test engagements and operations"},
    {"name": "findings", "description": "Vulnerability findings within engagements"},
    {"name": "assets", "description": "Target assets and hosts"},
    {"name": "testcases", "description": "Test case management and execution tracking"},
    {"name": "notes", "description": "Engagement notes with real-time collaboration and linking"},
    {"name": "vault", "description": "Secure credential and secret storage within engagements"},
    {"name": "cleanup-artifacts", "description": "Post-engagement cleanup item tracking and remediation"},
    {"name": "evidence", "description": "Evidence file uploads and management for findings"},
    {"name": "discussions", "description": "Threaded discussions on findings and test cases"},
    {"name": "tags", "description": "Finding tags and categorization labels"},

    # ── Reporting ────────────────────────────────────────────────────
    {"name": "reports", "description": "Report generation and export (PDF, DOCX)"},
    {"name": "report-layouts", "description": "Per-engagement report section layouts and ordering"},
    {"name": "report-layout-templates", "description": "Reusable report layout templates"},
    {"name": "report-themes", "description": "Report visual themes and branding customization"},

    # ── Templates ────────────────────────────────────────────────────
    {"name": "templates", "description": "Finding templates for reusable vulnerability definitions"},
    {"name": "testcase-templates", "description": "Test case template library for repeatable test procedures"},
    {"name": "runbooks", "description": "Runbook templates and execution step tracking"},

    # ── Organization ─────────────────────────────────────────────────
    {"name": "clients", "description": "Client organization management"},
    {"name": "client-types", "description": "Client type definitions and customization"},
    {"name": "engagement-types", "description": "Engagement type definitions (admin only)"},
    {"name": "configurable-types", "description": "Custom type management for assets, engagements, clients, findings, and more"},

    # ── Intelligence & Search ────────────────────────────────────────
    {"name": "search", "description": "Global cross-resource search across engagements, findings, assets, and more"},
    {"name": "attack-graph", "description": "Attack path graph visualization data and MITRE ATT&CK mapping"},
    {"name": "wordlist", "description": "Password and wordlist management for credential testing"},
    {"name": "intelligence", "description": "Threat intelligence feeds, CVEs, advisories, and intel-to-engagement linking"},
    {"name": "infrastructure", "description": "Red team infrastructure and asset tracking for C2, VPS, redirectors, and point of presence"},
    {"name": "skills", "description": "Skill categories, individual skills, user proficiency, and engagement skill requirements"},
    {"name": "imports", "description": "Scanner and tool output import (Nessus, Burp Suite, Nuclei, Nmap) with preview and commit workflow"},

    # ── Analytics & Stats ────────────────────────────────────────────
    {"name": "analytics", "description": "Dashboard analytics, trends, and usage statistics"},
    {"name": "stats", "description": "Engagement-level and global statistics summaries"},
    {"name": "calendar", "description": "Engagement calendar and scheduling views"},
    {"name": "dashboard", "description": "Dashboard widget definitions and user layout customization"},

    # ── Automation & Notifications ───────────────────────────────────
    {"name": "automations", "description": "Automation rules, triggers, and event-driven actions"},
    {"name": "notifications", "description": "User notifications, preferences, and unread counts"},

    # ── AI ────────────────────────────────────────────────────────────
    {"name": "ai", "description": "AI assistant configuration, LLM chat proxy, and model management"},

    # ── Real-time ────────────────────────────────────────────────────
    {"name": "websocket", "description": "Real-time WebSocket connections for collaboration and live updates"},

    # ── Plugins ──────────────────────────────────────────────────────
    {"name": "plugins", "description": "Plugin management, settings, and extension point discovery"},
]


# ── Background Intel Feed Refresh ────────────────────────────────

async def _refresh_intel_feeds_background():
    """Periodically refresh intel feeds in the background."""
    from database import AsyncSessionLocal
    from models.intel_feed import IntelFeed
    from models.intel_item import IntelItem
    from sqlalchemy import select
    import httpx
    import defusedxml.ElementTree as ET
    import uuid
    import re
    from datetime import datetime
    from routers.intel import _get_text, _strip_html, _parse_date, _parse_rss_date

    interval = int(os.getenv("INTEL_REFRESH_INTERVAL", "7200"))  # Default: 2 hours
    print(f"[Intel] Background feed refresh enabled (every {interval}s)")

    # Wait 30s on startup before first refresh
    await asyncio.sleep(30)

    while True:
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(IntelFeed).where(IntelFeed.enabled == True))
                feeds = result.scalars().all()
                total_new = 0

                async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                    for feed in feeds:
                        try:
                            resp = await client.get(feed.url, headers={"User-Agent": "RedWire/1.0"})
                            if resp.status_code != 200:
                                continue

                            entries = []
                            if feed.feed_type == "JSON":
                                data = resp.json()
                                vulns = data.get("vulnerabilities", data if isinstance(data, list) else [])
                                for v in vulns[:30]:
                                    entries.append({
                                        "title": v.get("vulnerabilityName") or v.get("cveID", "Unknown"),
                                        "content": v.get("shortDescription", ""),
                                        "source_url": f"https://nvd.nist.gov/vuln/detail/{v.get('cveID', '')}",
                                        "cve_id": v.get("cveID"),
                                        "item_type": "CVE",
                                        "severity": "HIGH" if v.get("knownRansomwareCampaignUse") == "Known" else None,
                                        "published_at": _parse_date(v.get("dateAdded")),
                                    })
                            else:
                                try:
                                    root = ET.fromstring(resp.text)
                                except ET.ParseError:
                                    continue
                                items_el = root.findall(".//item")
                                if not items_el:
                                    ns = {"atom": "http://www.w3.org/2005/Atom"}
                                    items_el = root.findall(".//atom:entry", ns)
                                for el in items_el[:30]:
                                    title = _get_text(el, "title") or _get_text(el, "{http://www.w3.org/2005/Atom}title") or "Untitled"
                                    link = _get_text(el, "link") or ""
                                    if not link:
                                        link_el = el.find("{http://www.w3.org/2005/Atom}link")
                                        if link_el is not None:
                                            link = link_el.get("href", "")
                                    desc = _get_text(el, "description") or _get_text(el, "{http://www.w3.org/2005/Atom}summary") or ""
                                    pub_date = _get_text(el, "pubDate") or _get_text(el, "{http://www.w3.org/2005/Atom}updated") or ""
                                    cve_id = None
                                    cve_match = re.search(r"CVE-\d{4}-\d+", title)
                                    if cve_match:
                                        cve_id = cve_match.group(0)
                                    item_type = "CVE" if cve_id else "ARTICLE"
                                    if any(kw in title.lower() for kw in ["advisory", "alert", "bulletin"]):
                                        item_type = "ADVISORY"
                                    elif any(kw in title.lower() for kw in ["exploit", "poc", "proof of concept"]):
                                        item_type = "EXPLOIT"
                                    entries.append({
                                        "title": title[:500],
                                        "content": _strip_html(desc)[:2000] if desc else None,
                                        "source_url": link,
                                        "cve_id": cve_id,
                                        "item_type": item_type,
                                        "published_at": _parse_rss_date(pub_date),
                                    })

                            for entry in entries:
                                if entry.get("source_url"):
                                    existing = await db.execute(
                                        select(IntelItem).where(
                                            IntelItem.source_url == entry["source_url"],
                                            IntelItem.feed_id == feed.id,
                                        )
                                    )
                                    if existing.scalar_one_or_none():
                                        continue
                                item = IntelItem(
                                    id=str(uuid.uuid4()),
                                    title=entry["title"],
                                    content=entry.get("content"),
                                    source=feed.name,
                                    source_url=entry.get("source_url"),
                                    item_type=entry.get("item_type", "OTHER"),
                                    severity=entry.get("severity"),
                                    cve_id=entry.get("cve_id"),
                                    published_at=entry.get("published_at"),
                                    feed_id=feed.id,
                                    created_at=datetime.utcnow(),
                                    updated_at=datetime.utcnow(),
                                )
                                db.add(item)
                                total_new += 1
                            feed.last_fetched_at = datetime.utcnow()
                        except Exception as e:
                            print(f"[Intel] Error fetching {feed.name}: {e}")
                            continue

                await db.commit()
                print(f"[Intel] Auto-refresh complete: {total_new} new items from {len(feeds)} feeds")
        except Exception as e:
            print(f"[Intel] Background refresh error: {e}")

        await asyncio.sleep(interval)


async def _seed_admin_user(session_factory):
    """Ensure an admin user exists with credentials from env vars."""
    from sqlalchemy import select
    from models.user import User, UserRole
    from auth.password import get_password_hash
    import uuid

    admin_email = os.getenv("ADMIN_EMAIL")
    admin_password = os.getenv("ADMIN_PASSWORD")
    admin_username = os.getenv("ADMIN_USERNAME", "admin")

    if not admin_email or not admin_password:
        print("[Admin] ADMIN_EMAIL/ADMIN_PASSWORD not set, skipping admin seed")
        return

    async with session_factory() as db:
        # Check if any admin user exists
        result = await db.execute(
            select(User).where(User.username == admin_username)
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Admin already exists — do NOT overwrite password (it may have been
            # changed via the UI). Only ensure the account is active and has admin role.
            if existing.role != UserRole.ADMIN:
                existing.role = UserRole.ADMIN
                await db.commit()
                print(f"[Admin] ✅ Admin user '{admin_username}' role restored to ADMIN")
            else:
                print(f"[Admin] ✅ Admin user '{admin_username}' already exists, skipping")
        else:
            new_admin = User(
                id=str(uuid.uuid4()),
                username=admin_username,
                email=admin_email,
                hashed_password=get_password_hash(admin_password),
                full_name="System Administrator",
                role=UserRole.ADMIN,
                is_active=True,
                must_change_password=True,
            )
            db.add(new_admin)
            await db.commit()
            print(f"[Admin] ✅ Admin user '{admin_username}' created")


@asynccontextmanager
async def lifespan(app):
    """Manage background tasks on startup/shutdown."""
    # ── Validate at-rest encryption keys (fail closed, GHSA-pg99-33rm-7wgq) ──
    # Refuse to start unless VAULT_ENCRYPTION_KEY and TOTP_ENCRYPTION_KEY are
    # set and valid Fernet keys. Never silently derive them from JWT_SECRET.
    from utils import vault_crypto
    from auth import crypto as totp_crypto
    vault_crypto.validate_key()
    totp_crypto.validate_key()

    # Load Bloom filter in background (it loads millions of rows, don't block startup)
    from utils.hash_utils import bloom_service
    from database import AsyncSessionLocal

    async def _load_bloom():
        try:
            await bloom_service.load_from_db(AsyncSessionLocal)
            print("[Bloom] Bloom filter loaded successfully")
        except Exception as e:
            print(f"[Bloom] ERROR loading bloom filter: {e}")

    # ── Plugin Discovery ──
    print("\n🔌 Discovering plugins...")
    plugin_registry.discover("plugins")
    plugin_registry.load_all(app=app, event_bus=event_bus, db_factory=AsyncSessionLocal)
    plugin_registry.mount_routes(app)
    print(f"🔌 {len(plugin_registry.plugins)} plugin(s) loaded\n")

    # ── Seed admin user from env vars ──
    await _seed_admin_user(AsyncSessionLocal)

    # ── Seed default groups and roles ──
    from seed_permissions import seed_default_groups_and_roles
    await seed_default_groups_and_roles()

    # ── Seed everything else (tags, types, skills, templates, etc.) ──
    try:
        from seed_defaults import seed_all_defaults
        await seed_all_defaults()
    except Exception as e:
        # Never block startup on a seed failure — log and continue.
        print(f"[seed] WARN: seed_all_defaults failed: {e}")

    bloom_task = asyncio.create_task(_load_bloom())
    intel_task = asyncio.create_task(_refresh_intel_feeds_background())
    yield
    bloom_task.cancel()
    intel_task.cancel()
    for task in (bloom_task, intel_task):
        try:
            await task
        except asyncio.CancelledError:
            pass


# Create FastAPI app
app = FastAPI(
    title="RedWire - Red Team Reporting Platform",
    description="Secure platform for red team reporting and operations management",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=openapi_tags,
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Create uploads directory if it doesn't exist
os.makedirs("uploads/profile_photos", exist_ok=True)

# Mount static files
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Configure CORS
origins_raw = os.getenv("CORS_ORIGINS", "")
if not origins_raw:
    print("[CORS] ⚠️  CORS_ORIGINS not set — defaulting to localhost only")
    origins = ["http://localhost:3000", "https://localhost:8443"]
else:
    origins = [o.strip() for o in origins_raw.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
)

# Activity Middleware to update last_active (throttled)
from datetime import datetime, timezone
from fastapi import Request
from sqlalchemy import update
from database import AsyncSessionLocal
from models.user import User
import time

# In-memory cache: user_id -> last_update_epoch
_last_active_cache: dict[str, float] = {}
_LAST_ACTIVE_INTERVAL = 60  # Only update DB once per 60 seconds per user

# Paths to skip — no need to track activity on these
_SKIP_PREFIXES = ("/health", "/docs", "/redoc", "/openapi.json", "/uploads/", "/ws")

@app.middleware("http")
async def update_last_active_middleware(request: Request, call_next):
    path = request.url.path
    auth_header = request.headers.get("Authorization")

    # Only process Bearer-authenticated API requests
    if auth_header and auth_header.startswith("Bearer ") and not any(path.startswith(p) for p in _SKIP_PREFIXES):
        try:
            token = auth_header.split(" ")[1]
            from auth.jwt import decode_token
            payload = decode_token(token)
            if payload and "sub" in payload:
                user_id = payload["sub"]
                now = time.monotonic()
                last = _last_active_cache.get(user_id, 0)
                if now - last >= _LAST_ACTIVE_INTERVAL:
                    _last_active_cache[user_id] = now
                    async with AsyncSessionLocal() as db:
                        await db.execute(
                            update(User)
                            .where(User.id == user_id)
                            .values(last_active=datetime.utcnow())
                        )
                        await db.commit()
        except Exception:
            pass  # Don't fail the request if middleware fails

    response = await call_next(request)
    return response


# Include routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(admin.router)
app.include_router(permissions.router)
app.include_router(engagements.router)
app.include_router(engagements_transfer.router)
app.include_router(findings.router)
app.include_router(assets.router)
app.include_router(websocket.router)
app.include_router(testcases.router)
app.include_router(calendar.router)
app.include_router(analytics.router)
app.include_router(reports.router)
app.include_router(stats.router)
app.include_router(templates.router)
app.include_router(discussions.router)
app.include_router(evidence.router)
app.include_router(vault.router)
app.include_router(testcase_templates.router)
app.include_router(notes.router)
app.include_router(tags.router)
app.include_router(runbooks.router)
app.include_router(search.router)
app.include_router(attack_graph.router)
app.include_router(report_layouts.router)
app.include_router(report_layout_templates.router)
app.include_router(report_themes.router)
app.include_router(clients.router)
app.include_router(clients.client_type_router)
app.include_router(cleanup_artifacts.router)
app.include_router(admin.engagement_type_router)
app.include_router(auth_settings.router)
app.include_router(api_tokens.router)
app.include_router(configurable_types.router)
app.include_router(wordlist.router)
app.include_router(notifications.router)
app.include_router(automations.router)
app.include_router(ai.router)
app.include_router(intel.router)
app.include_router(infra.router)
app.include_router(skills.router)
app.include_router(dashboard_widgets.router)
app.include_router(imports_router.router)
app.include_router(plugins_router.router)
app.include_router(spray_router.router)
app.include_router(attack_techniques_router.router)
app.include_router(markdown_images_router.router)



@app.get("/", tags=["root"])
async def root():
    """Root endpoint."""
    return {
        "message": "RedWire API",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "redwire-api"
    }

@app.on_event("startup")
async def startup():
    """Legacy startup banner. Real seeding now happens in lifespan via
    seed_defaults.seed_all_defaults() — see lines above."""
    print("🚀 RedWire API starting up...")
    print(f"📝 API documentation available at /docs")


@app.on_event("shutdown")
async def shutdown():
    """Shutdown event handler."""
    print("👋 RedWire API shutting down...")
