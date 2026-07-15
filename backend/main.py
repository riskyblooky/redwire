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
from routers import auth, engagements, engagements_transfer, findings, users, assets, testcases, calendar, analytics, reports, admin, websocket, stats, templates, discussions, evidence, vault, testcase_templates, permissions, notes, tags, runbooks, report_layouts, report_layout_templates, report_themes, marking_profiles, clients, cleanup_artifacts, auth_settings, api_tokens, configurable_types, search, attack_graph, wordlist, notifications, automations, ai, intel, infra, skills, dashboard_widgets, stats_pages, custom_fields, plugins as plugins_router
from routers import imports as imports_router
from routers import spray as spray_router
from routers import attack_techniques as attack_techniques_router
from routers import markdown_images as markdown_images_router
from plugin_loader import plugin_registry
from utils.event_bus import event_bus

# OpenAPI tag descriptions for /docs
openapi_tags = [
    # ── Meta ──────────────────────────────────────────────────────────
    {"name": "root", "description": "Service root — returns basic identity information for the running instance"},
    {"name": "health", "description": "Liveness probe reporting version, git commit, and build time from the deployed image"},

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
    {"name": "markdown-images", "description": "Inline image uploads for markdown-embedded images in notes, findings, and test cases"},
    {"name": "discussions", "description": "Threaded discussions on findings and test cases"},
    {"name": "tags", "description": "Finding tags and categorization labels"},

    # ── Reporting ────────────────────────────────────────────────────
    {"name": "reports", "description": "Report generation and export (PDF, JSON archive)"},
    {"name": "report-layouts", "description": "Per-engagement report section layouts and ordering"},
    {"name": "report-layout-templates", "description": "Reusable report layout templates"},
    {"name": "report-themes", "description": "Report visual themes and branding customization"},
    {"name": "marking-profiles", "description": "Classification / portion-marking policies (TLP, IC/DoD, custom)"},

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
    {"name": "attack", "description": "MITRE ATT&CK technique catalog lookup and enumeration"},
    {"name": "wordlist", "description": "Password and wordlist management for credential testing"},
    {"name": "spray", "description": "Password-spraying job orchestration and results tracking"},
    {"name": "intelligence", "description": "Threat intelligence feeds, CVEs, advisories, and intel-to-engagement linking"},
    {"name": "infrastructure", "description": "Red team infrastructure and asset tracking for C2, VPS, redirectors, and point of presence"},
    {"name": "skills", "description": "Skill categories, individual skills, user proficiency, and engagement skill requirements"},
    {"name": "imports", "description": "Scanner and tool output import (Nessus, Burp Suite, Nuclei, Nmap) with preview and commit workflow"},

    # ── Analytics & Stats ────────────────────────────────────────────
    {"name": "analytics", "description": "Dashboard analytics, trends, and usage statistics"},
    {"name": "stats", "description": "Engagement-level and global statistics summaries"},
    {"name": "calendar", "description": "Engagement calendar and scheduling views"},
    {"name": "dashboard", "description": "Dashboard widget definitions and user layout customization"},
    {"name": "stats-pages", "description": "Global, shared, tabbed stats pages (admin/curator-managed)"},
    {"name": "custom-fields", "description": "Admin-defined custom fields on assets, testcases, findings, and clients"},

    # ── Automation & Notifications ───────────────────────────────────
    {"name": "automations", "description": "Automation rules and event-driven actions. Two scopes: org-wide rules (admin-curated) and per-user personal rules (owner-scoped, notify-self only)"},
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
    from utils.ssrf import validate_outbound_url, OutboundURLError

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

                async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
                    for feed in feeds:
                        try:
                            # SSRF guard (GHSA-f33c-g6w5-6xm6): validate before
                            # the unattended fetch; redirects disabled above.
                            try:
                                await validate_outbound_url(feed.url)
                            except OutboundURLError as exc:
                                print(f"[Intel] Skipping feed {feed.url!r}: {exc}")
                                continue
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
    """Ensure an admin user exists with credentials from env vars.

    GHSA-28f5-4wcg-9pwv: this is a *bootstrap* function — its only job is
    to make sure a fresh database has at least one administrator. The
    previous shape looked the bootstrap user up by username and force-set
    ``role = ADMIN`` if they were anything else, which silently undid
    deliberate demotions (and, if the bootstrap row had been deleted,
    promoted whichever self-registered user happened to claim the
    configured ``ADMIN_USERNAME``). Switch the gate to "does any user
    with ``role == ADMIN`` exist?" — if yes, do nothing. The existing
    administrator population (be it the original bootstrap, a
    deliberately-promoted operator, or admin2 in dev) is the only thing
    the seeder cares about, and no row is ever rewritten.
    """
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
        # If any administrator already exists, leave the database alone.
        # The bootstrap user can be deliberately demoted, deleted, or
        # never have existed in the first place — that's an admin
        # decision and the seeder will not second-guess it.
        any_admin = await db.execute(
            select(User.id).where(User.role == UserRole.ADMIN).limit(1)
        )
        if any_admin.scalar_one_or_none():
            print("[Admin] ✅ Existing administrator detected, skipping bootstrap seed")
            return

        # No admin at all — refuse to create the bootstrap row if the
        # configured username is already in use (it would be a
        # self-registered account that should never silently be
        # promoted; the operator must resolve the conflict deliberately).
        result = await db.execute(
            select(User).where(User.username == admin_username)
        )
        existing = result.scalar_one_or_none()
        if existing:
            print(
                f"[Admin] ⚠ No administrator exists, but username "
                f"'{admin_username}' is taken by a non-admin user. Refusing "
                f"to auto-promote — resolve manually and restart."
            )
            return

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
        print(f"[Admin] ✅ Admin user '{admin_username}' created (no prior admin existed)")


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
    # Wire the event-bus enabled-gate before plugins register their
    # subscribers so the predicate is in place from the very first
    # emit(). Closes over the live registry so a runtime toggle
    # takes effect immediately. GHSA-4jrh-3m3r-p448 follow-up.
    def _plugin_enabled(pid: str) -> bool:
        p = plugin_registry.plugins.get(pid)
        return bool(p and p.manifest.enabled and not p.error)
    event_bus.set_plugin_enabled_check(_plugin_enabled)
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

    # ── One-shot vault-file at-rest encryption backfill ──
    # GHSA-3r7j-7h5r-gxgx Issue 3 follow-up. Walk any vault FILE rows
    # that were uploaded before RDW-057 (still plaintext in MinIO) and
    # encrypt them in place. Idempotent — once all rows are at
    # encryption_version=1, the helper exits before doing any I/O. Wrap
    # in a broad except so a stuck MinIO doesn't block the boot loop.
    try:
        from utils.vault_migration import count_legacy_blobs, backfill_legacy_vault_blobs
        async with AsyncSessionLocal() as _db:
            pending = await count_legacy_blobs(_db)
            if pending:
                print(f"[vault-encryption] backfilling {pending} legacy vault file(s)...")
                stats = await backfill_legacy_vault_blobs(_db)
                print(
                    f"[vault-encryption] done: checked={stats['checked']} "
                    f"already_encrypted={stats['already_encrypted']} "
                    f"encrypted_now={stats['encrypted_now']} "
                    f"skipped={stats['skipped']}"
                )
    except Exception as e:
        print(f"[vault-encryption] WARN: backfill failed: {e}")

    # ── One-shot vault-COLUMN at-rest encryption backfill ──
    # GHSA-3r7j-7h5r-gxgx follow-up — prerequisite for flipping
    # decrypt_field to fail-closed. Walks vault_items / infra_vault_items /
    # spray_campaigns / spray_results, encrypts any column that doesn't
    # decrypt under the current key (legacy plaintext from an early
    # write-path bug), skips wrong-keyed Fernet tokens. Idempotent +
    # cheap when nothing's pending. Boot-safe via the same broad except
    # as the blob backfill above.
    try:
        from utils.vault_field_migration import (
            count_legacy_field_rows,
            backfill_legacy_vault_fields,
            unwrap_double_encrypted_fields,
        )
        async with AsyncSessionLocal() as _db:
            # First: undo any double-Fernet wrap from an earlier dev
            # transient state (EncryptedText was introduced while routers
            # still called encrypt_field explicitly — that combo produced
            # double-wrapped rows). Idempotent: once data is clean the
            # helper no-ops on subsequent boots.
            unwrap_stats = await unwrap_double_encrypted_fields(_db)
            if unwrap_stats["unwrapped"]:
                print(
                    f"[vault-fields] unwrapped {unwrap_stats['unwrapped']} "
                    f"double-encrypted field(s) across "
                    f"{unwrap_stats['rows_checked']} row(s)."
                )

            # Then: encrypt any remaining legacy-plaintext rows in place
            # so the fail-closed decrypt_field flip is safe.
            pending = await count_legacy_field_rows(_db)
            if pending:
                print(f"[vault-fields] backfilling {pending} row(s) with unencrypted secret columns...")
                stats = await backfill_legacy_vault_fields(_db)
                print(
                    f"[vault-fields] done: rows_checked={stats['rows_checked']} "
                    f"already_encrypted={stats['fields_already_encrypted']} "
                    f"re_encrypted={stats['fields_re_encrypted']} "
                    f"skipped={stats['skipped']}"
                )
    except Exception as e:
        print(f"[vault-fields] WARN: backfill failed: {e}")

    # ── One-shot TOTP-secret at-rest encryption backfill ──
    # GHSA-rp23-74j3-mqmq follow-up (TOTP half) — prerequisite for
    # the fail-closed flip on decrypt_totp_secret. Alembic revision
    # d7e8f9a0b1c2 (2026-02-20) widened users.totp_secret for Fernet
    # ciphertext but did not touch existing rows, so any user that
    # enrolled 2FA before that revision still holds plaintext base32
    # in the column. Idempotent + cheap when nothing's pending; boot-
    # safe via the same broad except pattern as the vault backfill.
    try:
        from utils.totp_field_migration import (
            count_legacy_totp_rows,
            backfill_legacy_totp_secrets,
        )
        async with AsyncSessionLocal() as _db:
            pending = await count_legacy_totp_rows(_db)
            if pending:
                print(f"[totp-secrets] backfilling {pending} user(s) with unencrypted totp_secret...")
                stats = await backfill_legacy_totp_secrets(_db)
                print(
                    f"[totp-secrets] done: rows_checked={stats['rows_checked']} "
                    f"already_encrypted={stats['fields_already_encrypted']} "
                    f"re_encrypted={stats['fields_re_encrypted']} "
                    f"skipped={stats['skipped']}"
                )
    except Exception as e:
        print(f"[totp-secrets] WARN: backfill failed: {e}")

    # ── One-shot auth_settings at-rest encryption backfill ──
    # Companion to the AuthSetting.value → EncryptedText flip. Before
    # that change, LDAP bind passwords / SMTP passwords / SAML IdP certs
    # sat plaintext in auth_settings.value even though the row was
    # flagged is_encrypted=True (the flag was only used to mask API
    # responses, not to actually encrypt). Encrypted-at-rest via the
    # column type from now on; this pass re-encrypts any legacy rows
    # so the fail-closed decrypt path doesn't nuke live LDAP config on
    # first upgrade. Idempotent + cheap once complete.
    try:
        from utils.auth_settings_field_migration import (
            count_legacy_auth_settings_rows,
            backfill_legacy_auth_settings,
        )
        async with AsyncSessionLocal() as _db:
            pending = await count_legacy_auth_settings_rows(_db)
            if pending:
                print(f"[auth-settings] backfilling {pending} row(s) with unencrypted value...")
                stats = await backfill_legacy_auth_settings(_db)
                print(
                    f"[auth-settings] done: rows_checked={stats['rows_checked']} "
                    f"already_encrypted={stats['already_encrypted']} "
                    f"re_encrypted={stats['re_encrypted']} "
                    f"skipped={stats['skipped']}"
                )
    except Exception as e:
        print(f"[auth-settings] WARN: backfill failed: {e}")

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
from version import VERSION as _PLATFORM_VERSION
app = FastAPI(
    title="RedWire - Red Team Reporting Platform",
    description="Secure platform for red team reporting and operations management",
    version=_PLATFORM_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=openapi_tags,
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Create uploads directory if it doesn't exist
os.makedirs("uploads/profile_photos", exist_ok=True)

# GHSA-h77m-pjqc-5cm3: replace the StaticFiles mount (served pre-auth, with
# Content-Type derived from extension → stored XSS) with an authenticated
# FastAPI route. Every fetch requires get_current_user; the resolved path
# must stay inside the uploads root; Content-Disposition is always
# 'attachment' (browsers ignore that for <img> tags so legitimate profile
# photos still render in the UI). Content-Type is from a small allow-list
# of image MIMEs; everything else gets application/octet-stream so a legacy
# .html upload cannot execute even when an authenticated user fetches it.
from fastapi import Depends as _h77m_Depends, HTTPException as _h77m_HTTPException
from fastapi.responses import FileResponse as _h77m_FileResponse
from auth.dependencies import get_current_user as _h77m_get_current_user
from models.user import UserRole as _h77m_UserRole

_UPLOADS_ROOT = os.path.realpath("uploads")
_UPLOADS_MIME_BY_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


@app.get("/uploads/{path:path}", include_in_schema=False)
async def _serve_upload(path: str, _user=_h77m_Depends(_h77m_get_current_user)):
    """Authenticated, traversal-safe upload server with attachment disposition.

    GHSA-h77m-pjqc-5cm3 landed the authentication gate. This block adds
    per-subdirectory authorization on top so a leaked URL from one
    subsystem doesn't grant cross-subsystem read to any authenticated
    caller:

      uploads/wordlists/*      — admin / read-only-admin / team-lead only.
                                 The wordlist router gates *upload* on the
                                 same triplet; matching *fetch* to that
                                 keeps the surface consistent.
      uploads/profile_photos/* — any authenticated user. The team picker
                                 renders every user's avatar, so this
                                 stays open to any signed-in caller.
      uploads/<other>          — any authenticated user (unchanged
                                 default). Add a subdir-specific rule
                                 here when a new upload category ships.
    """
    target = os.path.realpath(os.path.join(_UPLOADS_ROOT, path))
    if not (target == _UPLOADS_ROOT or target.startswith(_UPLOADS_ROOT + os.sep)):
        raise _h77m_HTTPException(status_code=404, detail="Not found")

    # First path segment inside uploads/ selects the policy. Realpath
    # already blocked traversal; here we're just categorizing.
    # Order matters: role check runs BEFORE the file-exists check so an
    # unauthorized caller can't probe filenames by observing the
    # 404-vs-403 difference.
    rel = os.path.relpath(target, _UPLOADS_ROOT).replace(os.sep, "/")
    first_segment = rel.split("/", 1)[0] if "/" in rel else rel
    if first_segment == "wordlists":
        if _user.role not in (_h77m_UserRole.ADMIN, _h77m_UserRole.READ_ONLY_ADMIN, _h77m_UserRole.TEAM_LEAD):
            raise _h77m_HTTPException(status_code=403, detail="Wordlists are admin-only")

    if not os.path.isfile(target):
        raise _h77m_HTTPException(status_code=404, detail="Not found")

    ext = os.path.splitext(target)[1].lower()
    media_type = _UPLOADS_MIME_BY_EXT.get(ext, "application/octet-stream")
    return _h77m_FileResponse(
        target,
        media_type=media_type,
        filename=os.path.basename(target),
        headers={"X-Content-Type-Options": "nosniff"},
    )

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
    expose_headers=["Content-Disposition", "X-Marking-Warnings", "X-Archive-Root-Digest", "X-Total-Count"],
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
app.include_router(marking_profiles.router)
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
app.include_router(stats_pages.router)
app.include_router(custom_fields.router)
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


# Build info computed once at boot. Version comes from backend/version.py;
# git commit and build time come from Docker build args (set in
# scripts/deploy_server.sh). In dev — where the args aren't set — we
# fall back to running `git rev-parse HEAD` against the mounted source.
def _resolve_build_info() -> dict:
    import subprocess
    from version import VERSION as _VER

    commit = os.getenv("GIT_COMMIT") or ""
    if not commit:
        # Best-effort dev fallback. Runs once, in the container's mounted
        # source tree if the repo is bind-mounted (dev compose). Failures
        # are silent — "unknown" is a fine sentinel.
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short=12", "HEAD"],
                capture_output=True, text=True, timeout=2, cwd="/app",
            )
            if result.returncode == 0:
                commit = result.stdout.strip()
        except Exception:
            pass
    return {
        "version": _VER,
        "commit": commit or "unknown",
        "build_time": os.getenv("BUILD_TIME") or "unknown",
    }


_BUILD_INFO = _resolve_build_info()


@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint.

    Returns platform + build metadata so an operator (or the admin
    About page) can confirm exactly what's live: semantic version from
    ``version.py``, git commit short SHA from the build args
    (``GIT_COMMIT`` / ``BUILD_TIME`` set in
    ``scripts/deploy_server.sh``), or ``"unknown"`` when the args
    weren't passed (dev without a bind-mounted repo, unusual builds).
    """
    return {
        "status": "healthy",
        "service": "redwire-api",
        **_BUILD_INFO,
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
