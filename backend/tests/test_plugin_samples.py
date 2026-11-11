"""Plugin CRUD events use the documented names, and the sample plugins
(shodan_enricher, servicenow_cmdb) actually work: they read the asset's
identifier, gate asset routes per engagement, and query safely."""

from __future__ import annotations

import uuid

import httpx
import pytest

import database
from models.asset import Asset
from models.engagement import Engagement
from utils.collaboration import plugin_event_name
from utils.event_bus import event_bus


@pytest.mark.parametrize("rtype,action,expected", [
    ("asset", "created_asset", "asset.created"),
    ("finding", "updated_finding", "finding.updated"),
    ("vault", "created_vault_item", "vault.created"),
    ("asset", "deleted_asset", "asset.deleted"),
    ("asset", "imported_assets", "asset.imported_assets"),
    ("asset", "restored_version", "asset.restored_version"),
])
def test_plugin_event_name(rtype, action, expected):
    assert plugin_event_name(rtype, action) == expected


@pytest.fixture
def shared_factory(db_session, monkeypatch):
    class _Ctx:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, *exc):
            return False
    factory = lambda: _Ctx()  # noqa: E731
    monkeypatch.setattr(database, "AsyncSessionLocal", factory)
    return factory


async def _asset(db, make_user, **kw):
    admin = await make_user(role="admin", username=f"pl_{uuid.uuid4().hex[:6]}")
    eng = Engagement(id=str(uuid.uuid4()), name="P", client_name="ACME",
                     engagement_type="external_pentest", created_by=admin.id)
    db.add(eng)
    await db.flush()
    a = Asset(id=str(uuid.uuid4()), engagement_id=eng.id, created_by=admin.id,
              **{"name": "web01", "asset_type": "Server", "identifier": "203.0.113.7", **kw})
    db.add(a)
    await db.flush()
    return admin, a


async def test_asset_created_reaches_plugins(client, db_session, make_user, authenticate_as):
    admin, a = await _asset(db_session, make_user)
    authenticate_as(admin)
    seen = []

    async def handler(evt):
        seen.append(evt)
    event_bus.register("asset.created", handler, plugin_id="__test_samples")
    try:
        r = await client.post("/assets", json={"engagement_id": a.engagement_id, "name": "db01",
                                               "asset_type": "Server", "identifier": "10.1.1.1"})
        assert r.status_code == 201, r.text
        await event_bus.drain(5)  # plugin handlers run as background tasks
    finally:
        event_bus.unregister_plugin("__test_samples")
    assert [e["resource_id"] for e in seen] == [r.json()["id"]]


async def test_shodan_enriches_by_identifier(db_session, make_user, shared_factory, monkeypatch):
    from plugins.shodan_enricher.enricher import ShodanEnricher
    _, a = await _asset(db_session, make_user)  # name "web01", identifier is the IP
    enr = ShodanEnricher(db_factory=shared_factory)
    calls = []

    async def fake_lookup(ip, key):
        calls.append(ip)
        return {"ip": ip, "ports": [443], "vulns": []}
    monkeypatch.setattr(enr, "lookup", fake_lookup)
    monkeypatch.setattr(enr, "_get_api_key", lambda: _const("k"))

    await enr.handle_asset_event({"resource_id": a.id, "resource_name": a.name})
    assert calls == ["203.0.113.7"]
    assert (await enr.get_enrichment(a.id))["ports"] == [443]


async def test_shodan_manual_enrich_route(db_session, make_user, shared_factory, monkeypatch):
    from models.plugin import PluginSetting
    from plugins.shodan_enricher import enricher as enr_mod, router as shodan_router
    admin, a = await _asset(db_session, make_user)
    db_session.add(PluginSetting(plugin_id="shodan_enricher", key="SHODAN_API_KEY", value="k", is_secret=True))
    await db_session.flush()
    monkeypatch.setattr(shodan_router, "AsyncSessionLocal", shared_factory)

    async def fake_lookup(self, ip, key):
        return {"ip": ip, "ports": [], "vulns": []}
    monkeypatch.setattr(enr_mod.ShodanEnricher, "lookup", fake_lookup)

    # __wrapped__: the handler behind the slowapi rate-limit decorator (which
    # insists on a real Request).
    enrich = shodan_router.manual_enrich.__wrapped__
    out = await enrich(None, a.id, current_user=admin)  # used to 500 on asset.hostname
    assert out["ip"] == "203.0.113.7"

    outsider = await make_user(role="operator", username=f"out_{uuid.uuid4().hex[:6]}")
    with pytest.raises(Exception) as exc:
        await enrich(None, a.id, current_user=outsider)
    assert getattr(exc.value, "status_code", None) == 404


async def test_servicenow_query_cannot_add_conditions(monkeypatch):
    from plugins.servicenow_cmdb.servicenow import ServiceNowClient
    seen = {}

    def handler(request: httpx.Request):
        seen["query"] = request.url.params["sysparm_query"]
        seen["verify"] = True
        return httpx.Response(200, json={"result": []})
    real = httpx.AsyncClient

    def client_factory(*args, **kw):
        assert kw.get("verify", True) is not False  # TLS verification stays on
        return real(transport=httpx.MockTransport(handler), timeout=kw.get("timeout"))
    monkeypatch.setattr(httpx, "AsyncClient", client_factory)

    res = await ServiceNowClient("https://x.service-now.com", "u", "p").lookup("web01^NQsys_idISNOTEMPTY")
    assert res["count"] == 0
    assert "^NQ" not in seen["query"] and seen["query"].startswith("nameLIKEweb01NQsys_idISNOTEMPTY^OR")


async def _const(v):
    return v
