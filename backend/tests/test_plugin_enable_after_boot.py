"""Plugin enable/disable at runtime. A plugin loaded at boot toggles live:
its routes 503 while off and serve again when back on. A plugin disabled at
boot was never loaded, so enabling it reports requires_restart and it stays
inactive (no routes, widgets or nav items) until a restart."""

from __future__ import annotations

import uuid

import pytest
from fastapi import APIRouter
from sqlalchemy import select


def _plugin(enabled: bool, loaded: bool):
    from plugin_loader import LoadedPlugin, PluginManifest

    pid = f"t_plugin_{uuid.uuid4().hex[:8]}"
    router = APIRouter()

    @router.get("/ping")
    async def ping():
        return {"pong": True}

    manifest = PluginManifest(
        id=pid, name=pid, provides={"routes": True, "widgets": True, "nav_items": True},
        widgets=[{"id": "w"}], nav_items=[{"label": "T"}], enabled=enabled,
    )
    return LoadedPlugin(manifest=manifest, router=router if loaded else None, loaded=loaded)


@pytest.fixture
def registry(monkeypatch):
    """The live registry holding only the given plugins; their routes are
    mounted on the app the way startup does it."""
    import main
    from plugin_loader import plugin_registry

    def install(*plugins):
        monkeypatch.setattr(plugin_registry, "plugins", {p.id: p for p in plugins})
        plugin_registry.mount_routes(main.app)
        return plugin_registry
    return install


@pytest.fixture
def quiet_bus(monkeypatch):
    from utils import ws_bus
    sent = []

    async def publish(kind, payload):
        sent.append((kind, payload))
    monkeypatch.setattr(ws_bus.bus, "publish", publish)
    return sent


async def test_loaded_plugin_toggles_live(client, db_session, make_user, authenticate_as, registry, quiet_bus):
    from models.plugin import PluginState

    p = _plugin(enabled=True, loaded=True)
    reg = registry(p)
    authenticate_as(await make_user(role="admin"))
    url = f"/plugins/{p.slug}/ping"
    assert (await client.get(url)).json() == {"pong": True}

    off = await client.put(f"/plugins/{p.id}/toggle", json={"enabled": False})
    assert off.status_code == 200 and off.json()["requires_restart"] is False
    assert (await client.get(url)).status_code == 503
    assert reg.get_all_widgets() == [] and await reg.get_all_nav_items() == []
    assert quiet_bus[-1] == ("plugin_toggle", {"id": p.id, "enabled": False}), "other workers are told"

    on = await client.put(f"/plugins/{p.id}/toggle", json={"enabled": True})
    assert on.json() == {"plugin_id": p.id, "enabled": True, "requires_restart": False}
    assert (await client.get(url)).status_code == 200
    assert [w["plugin_id"] for w in reg.get_all_widgets()] == [p.id]

    state = (await db_session.execute(select(PluginState).where(PluginState.plugin_id == p.id))).scalar_one()
    assert state.enabled is True


async def test_plugin_disabled_at_boot_needs_restart(client, make_user, authenticate_as, registry, quiet_bus):
    p = _plugin(enabled=False, loaded=False)
    reg = registry(p)
    authenticate_as(await make_user(role="admin"))

    r = await client.put(f"/plugins/{p.id}/toggle", json={"enabled": True})
    assert r.status_code == 200 and r.json()["requires_restart"] is True
    # Enabled, but its code never ran: nothing of it is offered or served.
    assert p.manifest.enabled and not p.is_active
    assert reg.get_all_widgets() == [] and await reg.get_all_nav_items() == []
    assert await reg.get_extensions("engagement.tabs") == []
    assert (await client.get(f"/plugins/{p.slug}/ping")).status_code == 404
    listed = {x["id"]: x for x in (await client.get("/plugins/")).json()}
    assert listed[p.id]["requires_restart"] is True and listed[p.id]["loaded"] is False


async def test_only_admins_toggle(client, make_user, authenticate_as, registry, quiet_bus):
    p = _plugin(enabled=True, loaded=True)
    registry(p)
    authenticate_as(await make_user(role="operator"))
    r = await client.put(f"/plugins/{p.id}/toggle", json={"enabled": False})
    assert r.status_code == 403 and p.manifest.enabled is True and quiet_bus == []
