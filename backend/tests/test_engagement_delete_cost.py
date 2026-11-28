"""Deleting an engagement lets the database cascade its children instead of
the ORM loading every finding, asset, test case and their children first —
and still removes everything, including per-asset plugin data."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import event, func, select

from tests.test_authz_boundaries import _make_engagement

N = 15


def _u():
    return str(uuid.uuid4())


@pytest.fixture
def count_statements(db_session):
    engine = db_session.bind.sync_engine if hasattr(db_session.bind, "sync_engine") else db_session.bind.engine.sync_engine
    seen: list[str] = []

    def _on(conn, cursor, statement, *a):
        if not statement.lstrip().upper().startswith(("SAVEPOINT", "RELEASE", "ROLLBACK")):
            seen.append(statement)
    event.listen(engine, "before_cursor_execute", _on)
    yield seen
    event.remove(engine, "before_cursor_execute", _on)


async def _seed(db):
    from models.asset import Asset
    from models.asset_port import AssetPort
    from models.associations import FindingAsset
    from models.cleanup_artifact import CleanupArtifact
    from models.finding import Finding, Severity
    from models.plugin import upsert_plugin_setting
    from models.testcase import TestCase

    eng = await _make_engagement(db)
    assets = [Asset(id=_u(), engagement_id=eng.id, name=f"h{i}", identifier=f"10.0.0.{i}", asset_type="host")
              for i in range(N)]
    findings = [Finding(id=_u(), engagement_id=eng.id, title=f"f{i}", description="d", severity=Severity.HIGH)
                for i in range(N)]
    db.add_all(assets + findings)
    db.add_all([TestCase(id=_u(), engagement_id=eng.id, title=f"t{i}", category="c", description="d")
                for i in range(N)])
    db.add_all([CleanupArtifact(id=_u(), engagement_id=eng.id, title=f"c{i}", artifact_type="FILE", location="/tmp")
                for i in range(3)])
    await db.flush()
    db.add_all([AssetPort(id=_u(), asset_id=a.id, port_number=p) for a in assets for p in (22, 80)])
    db.add_all([FindingAsset(finding_id=f.id, asset_id=a.id) for f, a in zip(findings, assets)])
    await db.flush()
    await upsert_plugin_setting(db, "shodan_enricher", f"enrich:{assets[0].id}", "{}")
    await upsert_plugin_setting(db, "shodan_enricher", "MAX_ENRICHMENTS_PER_MINUTE", "5")
    await db.commit()
    return eng.id, assets[0].id


async def test_engagement_delete_cascades_in_the_database(client, db_session, make_user, authenticate_as,
                                                          count_statements):
    from models.asset import Asset
    from models.asset_port import AssetPort
    from models.associations import FindingAsset
    from models.finding import Finding
    from models.plugin import PluginSetting
    from models.testcase import TestCase

    eid, aid = await _seed(db_session)
    authenticate_as(await make_user(role="admin"))
    count_statements.clear()
    r = await client.delete(f"/engagements/{eid}")
    assert r.status_code == 204, r.text
    n = len(count_statements)

    for model, col in ((Finding, Finding.engagement_id), (Asset, Asset.engagement_id), (TestCase, TestCase.engagement_id)):
        assert await db_session.scalar(select(func.count()).select_from(model).where(col == eid)) == 0
    assert await db_session.scalar(select(func.count()).select_from(AssetPort).where(AssetPort.asset_id == aid)) == 0
    assert await db_session.scalar(select(func.count()).select_from(FindingAsset).where(FindingAsset.asset_id == aid)) == 0
    keys = set((await db_session.execute(select(PluginSetting.key))).scalars())
    assert f"enrich:{aid}" not in keys and "MAX_ENRICHMENTS_PER_MINUTE" in keys

    print(f"\n[delete statements: {n}]")
    # Independent of N (338 for N=15 when the ORM loaded and deleted each child).
    assert n <= 20, f"{n} statements for an engagement with {N} findings/assets/test cases"
