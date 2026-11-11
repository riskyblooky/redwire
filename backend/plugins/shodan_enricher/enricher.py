"""
Shodan Enricher — Core enrichment logic.

Queries the Shodan API for host information and stores results.
Handles rate limiting and error recovery.
"""

import re
import time
import asyncio
import traceback
from datetime import datetime
from typing import Any


_CACHE_TTL_S = 24 * 3600
_CACHE_MAX = 1000


class ShodanEnricher:
    """Handles Shodan API lookups and enrichment storage."""

    def __init__(self, db_factory):
        self.db_factory = db_factory
        # ip -> (monotonic time, enrichment). Expires so a host's new ports /
        # vulns show up, and is capped so a long-lived worker doesn't hold
        # every IP it ever saw.
        self._cache: dict[str, tuple[float, dict]] = {}
        self._lock = asyncio.Lock()

    async def _get_api_key(self) -> str | None:
        """Fetch the Shodan API key from plugin settings."""
        from sqlalchemy import select

        async with self.db_factory() as db:
            # Import here to avoid circular imports at plugin load time
            from models.plugin import PluginSetting
            result = await db.execute(
                select(PluginSetting).where(
                    PluginSetting.plugin_id == "shodan_enricher",
                    PluginSetting.key == "SHODAN_API_KEY",
                )
            )
            setting = result.scalar_one_or_none()
            return setting.value if setting else None

    async def _is_auto_enrich_enabled(self) -> bool:
        """Check if auto-enrichment is enabled in settings."""
        from sqlalchemy import select

        async with self.db_factory() as db:
            from models.plugin import PluginSetting
            result = await db.execute(
                select(PluginSetting).where(
                    PluginSetting.plugin_id == "shodan_enricher",
                    PluginSetting.key == "AUTO_ENRICH",
                )
            )
            setting = result.scalar_one_or_none()
            if not setting:
                return True  # Default enabled
            return setting.value.lower() in ("true", "1", "yes")

    @staticmethod
    def _is_ip_address(value: str) -> bool:
        """Check if string looks like an IPv4 address."""
        pattern = r"^(\d{1,3}\.){3}\d{1,3}$"
        return bool(re.match(pattern, value.strip()))

    async def handle_asset_event(self, event: dict[str, Any]):
        """Handle asset.created/updated events — enrich if it's an IP."""
        resource_id = event.get("resource_id", "")
        # Events carry the display name; the IP is the asset's identifier.
        resource_name = await self.asset_ip(resource_id) if resource_id else None
        if not resource_name:
            return  # Not an IP address, skip

        if not await self._is_auto_enrich_enabled():
            return

        api_key = await self._get_api_key()
        if not api_key:
            print(f"[Shodan] No API key configured, skipping enrichment for {resource_name}")
            return

        try:
            data = await self.lookup(resource_name, api_key)
            if data:
                await self._store_enrichment(resource_id, resource_name, data)
                print(f"[Shodan] Enriched asset {resource_name}: "
                      f"{len(data.get('ports', []))} ports, "
                      f"{len(data.get('vulns', []))} vulns")
        except Exception as e:
            print(f"[Shodan] Error enriching {resource_name}: {e}")
            traceback.print_exc()

    async def asset_ip(self, asset_id: str) -> str | None:
        """The asset's identifier (or name) if it's an IPv4 address."""
        from sqlalchemy import select
        from models.asset import Asset

        async with self.db_factory() as db:
            asset = (await db.execute(select(Asset).where(Asset.id == asset_id))).scalar_one_or_none()
        if asset is None:
            return None
        for candidate in (asset.identifier, asset.name):
            if candidate and self._is_ip_address(candidate):
                return candidate.strip()
        return None

    async def lookup(self, ip: str, api_key: str) -> dict | None:
        """Query Shodan API for host information."""
        # Check cache first
        hit = self._cache.get(ip)
        if hit and time.monotonic() - hit[0] < _CACHE_TTL_S:
            return hit[1]

        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"https://api.shodan.io/shodan/host/{ip}",
                    params={"key": api_key, "minify": "true"},
                )

                if resp.status_code == 404:
                    return {"ip": ip, "ports": [], "vulns": [], "hostnames": [], "error": "No data"}
                if resp.status_code == 401:
                    print("[Shodan] Invalid API key")
                    return None
                if resp.status_code == 429:
                    print("[Shodan] Rate limited, backing off")
                    return None
                if resp.status_code != 200:
                    return None

                data = resp.json()
                result = {
                    "ip": ip,
                    "ports": data.get("ports", []),
                    "hostnames": data.get("hostnames", []),
                    "os": data.get("os"),
                    "org": data.get("org"),
                    "isp": data.get("isp"),
                    "country": data.get("country_name"),
                    "city": data.get("city"),
                    "vulns": data.get("vulns", []),
                    "last_update": data.get("last_update"),
                    "asn": data.get("asn"),
                    "enriched_at": datetime.utcnow().isoformat(),
                }

                if len(self._cache) >= _CACHE_MAX:
                    self._cache.pop(next(iter(self._cache)))  # oldest insertion
                self._cache[ip] = (time.monotonic(), result)
                return result

        except Exception as e:
            print(f"[Shodan] API error for {ip}: {e}")
            return None

    async def _store_enrichment(self, asset_id: str, ip: str, data: dict):
        """Store enrichment data in plugin_settings keyed by asset ID."""
        import json

        async with self.db_factory() as db:
            from models.plugin import upsert_plugin_setting
            await upsert_plugin_setting(db, "shodan_enricher", f"enrich:{asset_id}", json.dumps(data))
            await db.commit()

    async def get_enrichment(self, asset_id: str) -> dict | None:
        """Get stored enrichment data for an asset."""
        import json
        from sqlalchemy import select

        async with self.db_factory() as db:
            from models.plugin import PluginSetting
            result = await db.execute(
                select(PluginSetting).where(
                    PluginSetting.plugin_id == "shodan_enricher",
                    PluginSetting.key == f"enrich:{asset_id}",
                )
            )
            setting = result.scalar_one_or_none()
            if setting and setting.value:
                return json.loads(setting.value)
            return None

    async def get_stats(self) -> dict:
        """Get enrichment stats for the dashboard widget."""
        from sqlalchemy import select, func

        async with self.db_factory() as db:
            from models.plugin import PluginSetting
            from models.asset import Asset

            total_assets = (await db.execute(
                select(func.count(Asset.id))
            )).scalar() or 0

            enriched_assets = (await db.execute(
                select(func.count(PluginSetting.id)).where(
                    PluginSetting.plugin_id == "shodan_enricher",
                    PluginSetting.key.like("enrich:%"),
                )
            )).scalar() or 0

            return {
                "total_assets": total_assets,
                "enriched_assets": enriched_assets,
                "cache_size": len(self._cache),
            }
