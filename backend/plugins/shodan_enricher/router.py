"""
Shodan Enricher Plugin — API Routes

Provides:
  GET  /plugins/shodan-enricher/lookup/{ip}  — Manual Shodan lookup
  GET  /plugins/shodan-enricher/stats        — Enrichment statistics
  POST /plugins/shodan-enricher/enrich/{asset_id} — Manually trigger enrichment
"""

from fastapi import APIRouter, Depends, HTTPException
from auth.dependencies import get_current_user
from models.user import User
from database import AsyncSessionLocal

router = APIRouter()


@router.get("/lookup/{ip}")
async def shodan_lookup(
    ip: str,
    current_user: User = Depends(get_current_user),
):
    """Look up an IP address on Shodan. Returns host data."""
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
async def manual_enrich(
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

        # Get asset
        asset_result = await db.execute(select(Asset).where(Asset.id == asset_id))
        asset = asset_result.scalar_one_or_none()
        if not asset:
            raise HTTPException(404, "Asset not found")

    from .enricher import ShodanEnricher
    enricher = ShodanEnricher(db_factory=AsyncSessionLocal)

    ip = asset.hostname or asset.name
    data = await enricher.lookup(ip, key_setting.value)
    if data:
        await enricher._store_enrichment(asset_id, ip, data)
        return {"status": "enriched", "ip": ip, "data": data}

    raise HTTPException(502, f"Failed to enrich {ip}")
