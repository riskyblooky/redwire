"""
ServiceNow CMDB Plugin — API Routes

Provides:
  GET /plugins/servicenow-cmdb/lookup/{query}         — Search CMDB by name/IP/FQDN
  GET /plugins/servicenow-cmdb/asset/{asset_id}        — Lookup using a RedWire asset's identifier
  GET /plugins/servicenow-cmdb/enrichment/{asset_id}   — Get stored enrichment data for an asset
"""

from fastapi import APIRouter, Depends, HTTPException
from auth.dependencies import get_current_user
from models.user import User
from database import AsyncSessionLocal

router = APIRouter()


async def _get_client():
    """Build a ServiceNowClient from stored plugin settings."""
    from sqlalchemy import select
    from models.plugin import PluginSetting

    keys_needed = ["INSTANCE_URL", "USERNAME", "PASSWORD", "CMDB_TABLE"]
    settings = {}

    async with AsyncSessionLocal() as db:
        for key in keys_needed:
            result = await db.execute(
                select(PluginSetting).where(
                    PluginSetting.plugin_id == "servicenow_cmdb",
                    PluginSetting.key == key,
                )
            )
            setting = result.scalar_one_or_none()
            settings[key] = setting.value if setting else None

    instance_url = settings.get("INSTANCE_URL")
    username = settings.get("USERNAME")
    password = settings.get("PASSWORD")
    table = settings.get("CMDB_TABLE") or "cmdb_ci"

    if not instance_url or not username or not password:
        raise HTTPException(
            400,
            "ServiceNow plugin not fully configured. "
            "Set Instance URL, Username, and Password in Admin → Plugins.",
        )

    from .servicenow import ServiceNowClient
    return ServiceNowClient(
        instance_url=instance_url,
        username=username,
        password=password,
        table=table,
    )


@router.get("/lookup/{query}")
async def lookup_cmdb(
    query: str,
    limit: int = 10,
    current_user: User = Depends(get_current_user),
):
    """Search ServiceNow CMDB for Configuration Items matching the query."""
    client = await _get_client()
    result = await client.lookup(query, limit=min(limit, 50))

    if result.get("error"):
        raise HTTPException(502, result["error"])

    return result


@router.get("/asset/{asset_id}")
async def lookup_asset(
    asset_id: str,
    current_user: User = Depends(get_current_user),
):
    """Look up a RedWire asset in ServiceNow CMDB using its identifier."""
    from sqlalchemy import select
    from models.asset import Asset

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Asset).where(Asset.id == asset_id))
        asset = result.scalar_one_or_none()
        if not asset:
            raise HTTPException(404, "Asset not found")

    # Use the asset's identifier (IP, domain, hostname, etc.)
    query = asset.identifier or asset.name
    client = await _get_client()
    result = await client.lookup(query)

    if result.get("error"):
        raise HTTPException(502, result["error"])

    return {
        "asset_id": asset_id,
        "asset_name": asset.name,
        "asset_identifier": asset.identifier,
        **result,
    }


@router.get("/enrichment/{asset_id}")
async def get_enrichment(
    asset_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get stored ServiceNow CMDB enrichment data for an asset (from auto-lookup)."""
    import json
    from sqlalchemy import select
    from models.plugin import PluginSetting

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(PluginSetting).where(
                PluginSetting.plugin_id == "servicenow_cmdb",
                PluginSetting.key == f"cmdb:{asset_id}",
            )
        )
        setting = result.scalar_one_or_none()

    if not setting or not setting.value:
        return {"asset_id": asset_id, "enrichment": None}

    return {"asset_id": asset_id, "enrichment": json.loads(setting.value)}
