"""Edits can clear what they're allowed to clear: an explicit null (or an
empty port list) is applied, a field that's left out is unchanged, and a
null for a required field is a 422 rather than a 500."""

from __future__ import annotations

import json
import uuid
from datetime import datetime

from sqlalchemy import select

from models.asset import Asset
from models.asset_port import AssetPort
from models.associations import FindingAsset
from models.finding import Finding, Severity


def u():
    return str(uuid.uuid4())


async def _finding_with_port(db):
    from tests.test_authz_boundaries import _make_engagement
    eng = await _make_engagement(db)
    asset = Asset(id=u(), engagement_id=eng.id, name="dc01", asset_type="Server", identifier=f"10.0.0.{uuid.uuid4().int % 250}")
    db.add(asset)
    await db.flush()
    port = AssetPort(id=u(), asset_id=asset.id, port_number=445, protocol="TCP", state="OPEN")
    finding = Finding(id=u(), engagement_id=eng.id, title="t", description="d", severity=Severity.HIGH,
                      category="Web", impact="bad", cvss_vector="CVSS:3.1/AV:N")
    db.add_all([port, finding])
    await db.flush()
    await db.execute(FindingAsset.__table__.insert().values(
        finding_id=finding.id, asset_id=asset.id, port_ids=json.dumps([port.id])))
    await db.flush()
    return finding.id, asset.id


async def test_finding_edit_clears_ports_and_optional_text(client, db_session, make_user, authenticate_as):
    fid, aid = await _finding_with_port(db_session)
    db_session.expunge_all()
    authenticate_as(await make_user(role="admin"))
    r = await client.put(f"/findings/{fid}", json={
        "asset_ids": [aid], "asset_port_ids": {aid: []},
        "category": None, "impact": None, "cvss_vector": None,
    })
    assert r.status_code == 200, r.text
    port_ids = (await db_session.execute(select(FindingAsset.port_ids).where(
        FindingAsset.finding_id == fid, FindingAsset.asset_id == aid))).scalar_one()
    assert port_ids is None
    f = (await db_session.execute(select(Finding).where(Finding.id == fid))).scalar_one()
    assert (f.category, f.impact, f.cvss_vector, f.title) == (None, None, None, "t")


async def test_null_for_a_required_field_is_422(client, db_session, make_user, authenticate_as):
    fid, _ = await _finding_with_port(db_session)
    db_session.expunge_all()
    authenticate_as(await make_user(role="admin"))
    r = await client.put(f"/findings/{fid}", json={"title": None})
    assert r.status_code == 422, r.text
    assert "title" in r.json()["detail"]


async def test_phase_dates_can_be_cleared(client, db_session, make_user, authenticate_as):
    from models.engagement_phase import EngagementPhase
    from tests.test_authz_boundaries import _make_engagement
    eng = await _make_engagement(db_session)
    ph = EngagementPhase(id=u(), engagement_id=eng.id, phase_name="PLANNING",
                         planned_start=datetime(2026, 1, 1), planned_end=datetime(2026, 1, 9))
    db_session.add(ph)
    await db_session.flush()
    eng_id, ph_id = eng.id, ph.id
    db_session.expunge_all()
    authenticate_as(await make_user(role="admin"))
    r = await client.put(f"/engagements/{eng_id}/phases", json=[{"id": ph_id, "planned_end": None}])
    assert r.status_code == 200, r.text
    got = (await db_session.execute(select(EngagementPhase.planned_start, EngagementPhase.planned_end)
                                    .where(EngagementPhase.id == ph_id))).one()
    assert got == (datetime(2026, 1, 1), None)  # left-out start unchanged


async def test_runbook_type_can_be_cleared(client, db_session, make_user, authenticate_as):
    from models.runbook import Runbook
    admin = await make_user(role="admin")
    rb = Runbook(id=u(), name="rb", runbook_type="Recon", created_by=admin.id)
    db_session.add(rb)
    await db_session.flush()
    rb_id = rb.id
    db_session.expunge_all()
    authenticate_as(admin)
    assert (await client.put(f"/runbooks/{rb_id}", json={"name": "rb"})).status_code == 200
    assert (await db_session.execute(select(Runbook.runbook_type).where(Runbook.id == rb_id))).scalar_one() == "Recon"
    r = await client.put(f"/runbooks/{rb_id}", json={"runbook_type": None})
    assert r.status_code == 200, r.text
    assert (await db_session.execute(select(Runbook.runbook_type).where(Runbook.id == rb_id))).scalar_one() is None
