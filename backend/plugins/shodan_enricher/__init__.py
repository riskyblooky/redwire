"""
Shodan Enricher Plugin — Auto-enriches assets with Shodan host intelligence.

On setup, registers an event listener for 'asset.created' events.
When an asset with an IP address is created, it queries the Shodan API
for host data (open ports, services, vulnerabilities, geolocation)
and stores the results as enrichment metadata.
"""

from .enricher import ShodanEnricher

_enricher = None


def setup(app, event_bus, db_factory, manifest):
    """Called by the plugin loader on startup."""
    global _enricher
    _enricher = ShodanEnricher(db_factory=db_factory)

    # Register event listener for asset creation
    async def on_asset_created(event):
        await _enricher.handle_asset_event(event)

    event_bus.register("asset.created", on_asset_created, plugin_id=manifest.id)
    event_bus.register("asset.updated", on_asset_created, plugin_id=manifest.id)

    print(f"    → Shodan enricher ready (auto-enrich on asset.created)")
