"""
ServiceNow CMDB Plugin — Looks up assets in ServiceNow's CMDB.

Registers an event listener for asset.created events to automatically
query ServiceNow CMDB and store matching CI data + link.
"""

from .servicenow import ServiceNowClient

_db_factory = None


def setup(app, event_bus, db_factory, manifest):
    """Called by the plugin loader on startup."""
    global _db_factory
    _db_factory = db_factory

    async def on_asset_created(event):
        await _handle_asset_event(event)

    event_bus.register("asset.created", on_asset_created, plugin_id=manifest.id)

    print(f"    → ServiceNow CMDB plugin ready (auto-lookup on asset.created)")


async def _get_setting(key: str) -> str | None:
    """Fetch a plugin setting value."""
    from sqlalchemy import select
    from models.plugin import PluginSetting

    async with _db_factory() as db:
        result = await db.execute(
            select(PluginSetting).where(
                PluginSetting.plugin_id == "servicenow_cmdb",
                PluginSetting.key == key,
            )
        )
        setting = result.scalar_one_or_none()
        return setting.value if setting else None


async def _handle_asset_event(event: dict):
    """Handle asset.created — look up the asset in ServiceNow CMDB."""
    import json
    import traceback

    resource_name = event.get("resource_name", "")
    resource_id = event.get("resource_id", "")

    if not resource_name:
        return

    # Check if auto-lookup is enabled
    auto_lookup = await _get_setting("AUTO_LOOKUP")
    if auto_lookup and auto_lookup.lower() in ("false", "0", "no"):
        return

    # Get credentials
    instance_url = await _get_setting("INSTANCE_URL")
    username = await _get_setting("USERNAME")
    password = await _get_setting("PASSWORD")
    table = (await _get_setting("CMDB_TABLE")) or "cmdb_ci"

    if not instance_url or not username or not password:
        return  # Not configured, skip silently

    try:
        client = ServiceNowClient(
            instance_url=instance_url,
            username=username,
            password=password,
            table=table,
        )
        result = await client.lookup(resource_name, limit=5)

        if result.get("error") or not result.get("results"):
            return

        # Store the result as enrichment data
        from sqlalchemy import select
        from models.plugin import PluginSetting

        async with _db_factory() as db:
            key = f"cmdb:{resource_id}"
            existing = (await db.execute(
                select(PluginSetting).where(
                    PluginSetting.plugin_id == "servicenow_cmdb",
                    PluginSetting.key == key,
                )
            )).scalar_one_or_none()

            data = json.dumps(result)
            if existing:
                existing.value = data
            else:
                db.add(PluginSetting(
                    plugin_id="servicenow_cmdb",
                    key=key,
                    value=data,
                    is_secret=False,
                ))
            await db.commit()

        count = result.get("count", 0)
        print(f"[ServiceNow] Auto-lookup for '{resource_name}': {count} CI(s) found")

    except Exception as e:
        print(f"[ServiceNow] Error during auto-lookup for '{resource_name}': {e}")
        traceback.print_exc()
