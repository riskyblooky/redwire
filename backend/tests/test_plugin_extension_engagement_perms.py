"""Plugin extensions gated on an engagement-scoped permission show for
members holding it on the engagement the slot renders in."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from plugin_loader import plugin_registry
from tests.test_authz_boundaries import _assign, _make_engagement, _make_engagement_role


@pytest.fixture
def fake_plugin(monkeypatch):
    manifest = SimpleNamespace(
        enabled=True, required_permissions=[],
        extensions={"engagement.tabs": [{"component": "cmdb-tab", "label": "CMDB",
                                         "required_permissions": ["engagement_view"]}]},
    )
    plugin = SimpleNamespace(id="fake-plugin", slug="fake_plugin", manifest=manifest, error=None, is_active=True)
    monkeypatch.setattr(plugin_registry, "plugins", {"fake-plugin": plugin})


def _tabs(r):
    assert r.status_code == 200, r.text
    return [e["component"] for e in r.json()]


async def test_member_with_engagement_view_sees_the_tab(client, db_session, make_user, authenticate_as, fake_plugin):
    eng = await _make_engagement(db_session)
    member = await make_user(role="operator")
    await _assign(db_session, member, eng, await _make_engagement_role(db_session, ["engagement_view"]))
    authenticate_as(member)

    assert _tabs(await client.get("/plugins/extensions/engagement.tabs", params={"engagement_id": eng.id})) == ["cmdb-tab"]
    # Without the engagement, only global grants count (unchanged).
    assert _tabs(await client.get("/plugins/extensions/engagement.tabs")) == []


async def test_non_member_does_not(client, db_session, make_user, authenticate_as, fake_plugin):
    eng = await _make_engagement(db_session)
    outsider = await make_user(role="operator")
    authenticate_as(outsider)
    assert _tabs(await client.get("/plugins/extensions/engagement.tabs", params={"engagement_id": eng.id})) == []
