"""
Shodan Enricher Plugin — API Routes

Provides:
  GET  /plugins/shodan-enricher/lookup/{ip}  — Manual Shodan lookup
  GET  /plugins/shodan-enricher/stats        — Enrichment statistics
  POST /plugins/shodan-enricher/enrich/{asset_id} — Manually trigger enrichment
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from auth.dependencies import get_current_user
from models.user import User
from database import AsyncSessionLocal
from rate_limit import limiter

router = APIRouter()

# Each call spends Shodan API quota (the plugin's MAX_ENRICHMENTS_PER_MINUTE
# setting governs the auto-enricher; this caps the manual routes).
_SHODAN_RATE = "10/minute"


async def require_lookup_access(user: User) -> None:
    """A free-text lookup spends Shodan quota with no asset (so no
    engagement) to check: allow it for anyone who can create assets in some
    engagement, refuse view-only accounts. (Kept local — plugins are
    drop-in and must not import each other.)"""
    from auth.permissions import engagement_permission_ceiling
    from models.permission import Permission
    async with AsyncSessionLocal() as db:
        if Permission.ASSET_CREATE.value in await engagement_permission_ceiling(user, db):
            return
    raise HTTPException(403, "Lookups require the asset_create permission in an engagement.")


@router.get("/lookup/{ip}")
@limiter.limit(_SHODAN_RATE)
async def shodan_lookup(
    request: Request,
    ip: str,
    current_user: User = Depends(get_current_user),
):
    """Look up an IP address on Shodan. Returns host data."""
    await require_lookup_access(current_user)
    from models.plugin import PluginSetting
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(PluginSetting).where(
                PluginSetting.plugin_id == "shodan_enricher",
                PluginSetting.key == "SHODAN_API_KEY",
            )
        )
        setting = result.scalar_one_or_none()
        if not setting or not setting.value:
            raise HTTPException(400, "Shodan API key not configured. Set it in Admin → Plugins.")

    from .enricher import ShodanEnricher
    enricher = ShodanEnricher(db_factory=AsyncSessionLocal)
    data = await enricher.lookup(ip, setting.value)

    if data is None:
        raise HTTPException(502, f"Failed to query Shodan for {ip}")

    return data


@router.get("/stats")
async def enrichment_stats(
    current_user: User = Depends(get_current_user),
):
    """Get Shodan enrichment statistics."""
    from .enricher import ShodanEnricher
    enricher = ShodanEnricher(db_factory=AsyncSessionLocal)
    return await enricher.get_stats()


@router.post("/enrich/{asset_id}")
@limiter.limit(_SHODAN_RATE)
async def manual_enrich(
    request: Request,
    asset_id: str,
    current_user: User = Depends(get_current_user),
):
    """Manually trigger Shodan enrichment for a specific asset."""
    from sqlalchemy import select
    from models.asset import Asset
    from models.plugin import PluginSetting

    async with AsyncSessionLocal() as db:
        # Get API key
        result = await db.execute(
            select(PluginSetting).where(
                PluginSetting.plugin_id == "shodan_enricher",
                PluginSetting.key == "SHODAN_API_KEY",
            )
        )
        key_setting = result.scalar_one_or_none()
        if not key_setting or not key_setting.value:
            raise HTTPException(400, "Shodan API key not configured")

        # Get asset — and only one the caller may view.
        from auth.rbac import check_engagement_permission
        from models.permission import Permission
        from models.user import UserRole
        asset_result = await db.execute(select(Asset).where(Asset.id == asset_id))
        asset = asset_result.scalar_one_or_none()
        if not asset or not (
            current_user.role in (UserRole.ADMIN, UserRole.TEAM_LEAD)
            or await check_engagement_permission(current_user.id, asset.engagement_id, Permission.ASSET_EDIT.value, db)
        ):
            raise HTTPException(404, "Asset not found")

    from .enricher import ShodanEnricher
    enricher = ShodanEnricher(db_factory=AsyncSessionLocal)

    ip = await enricher.asset_ip(asset_id)
    if not ip:
        raise HTTPException(400, "Asset has no IPv4 identifier to look up")
    data = await enricher.lookup(ip, key_setting.value)
    if data:
        await enricher._store_enrichment(asset_id, ip, data)
        return {"status": "enriched", "ip": ip, "data": data}

    raise HTTPException(502, f"Failed to enrich {ip}")
