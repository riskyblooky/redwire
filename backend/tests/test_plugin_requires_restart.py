"""A plugin disabled at boot (never loaded) that is enabled at runtime is
reported as needing a restart, and offers no nav items or tabs until then."""

from __future__ import annotations

import pytest

from plugin_loader import LoadedPlugin, PluginManifest, plugin_registry


def _plugin(loaded: bool) -> LoadedPlugin:
    m = PluginManifest(
        id="late_plugin", name="Late", enabled=True,
        nav_items=[{"label": "Late", "href": "/plugins/late-plugin"}],
        extensions={"engagement.tabs": [{"component": "late-tab", "label": "Late"}]},
    )
    return LoadedPlugin(manifest=m, loaded=loaded)


@pytest.mark.parametrize("loaded", [False, True])
async def test_unloaded_plugin_is_not_offered(client, make_user, authenticate_as, monkeypatch, loaded):
    monkeypatch.setattr(plugin_registry, "plugins", {"late_plugin": _plugin(loaded)})
    authenticate_as(await make_user(role="admin"))
    nav = (await client.get("/plugins/nav-items")).json()
    tabs = (await client.get("/plugins/extensions/engagement.tabs")).json()
    assert bool(nav) is loaded and bool(tabs) is loaded
    listed = next(p for p in (await client.get("/plugins/")).json() if p["id"] == "late_plugin")
    assert listed["requires_restart"] is (not loaded)


async def test_enabling_an_unloaded_plugin_says_restart(client, make_user, authenticate_as, monkeypatch):
    p = _plugin(loaded=False)
    p.manifest.enabled = False
    monkeypatch.setattr(plugin_registry, "plugins", {"late_plugin": p})
    authenticate_as(await make_user(role="admin"))
    r = await client.put("/plugins/late_plugin/toggle", json={"enabled": True})
    assert r.status_code == 200, r.text
    assert r.json()["requires_restart"] is True
