"""Per-asset plugin rows ("enrich:<id>", "cmdb:<id>") go with the asset."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from tests.test_authz_boundaries import _make_engagement


async def _asset_with_blobs(db):
    from models.asset import Asset
    from models.plugin import upsert_plugin_setting
    eng = await _make_engagement(db)
    a = Asset(id=str(uuid.uuid4()), engagement_id=eng.id, name="h",
              identifier=f"h-{uuid.uuid4().hex[:8]}", asset_type="host")
    db.add(a)
    await db.flush()
    await upsert_plugin_setting(db, "shodan_enricher", f"enrich:{a.id}", "{}")
    await upsert_plugin_setting(db, "servicenow_cmdb", f"cmdb:{a.id}", "{}")
    await upsert_plugin_setting(db, "shodan_enricher", "MAX_ENRICHMENTS_PER_MINUTE", "5")
    return eng, a.id


async def _keys(db):
    from models.plugin import PluginSetting
    return set((await db.execute(select(PluginSetting.key))).scalars())


async def test_asset_delete_drops_its_plugin_rows(client, db_session, make_user, authenticate_as):
    _eng, aid = await _asset_with_blobs(db_session)
    authenticate_as(await make_user(role="admin"))
    r = await client.delete(f"/assets/{aid}")
    assert r.status_code == 204, r.text
    keys = await _keys(db_session)
    assert f"enrich:{aid}" not in keys and f"cmdb:{aid}" not in keys
    assert "MAX_ENRICHMENTS_PER_MINUTE" in keys


async def test_engagement_delete_drops_its_assets_plugin_rows(client, db_session, make_user, authenticate_as):
    eng, aid = await _asset_with_blobs(db_session)
    authenticate_as(await make_user(role="admin"))
    r = await client.delete(f"/engagements/{eng.id}")
    assert r.status_code in (200, 204), r.text
    keys = await _keys(db_session)
    assert f"enrich:{aid}" not in keys and f"cmdb:{aid}" not in keys
    assert "MAX_ENRICHMENTS_PER_MINUTE" in keys
