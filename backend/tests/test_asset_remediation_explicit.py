"""Setting an asset's remediation state is idempotent: "Remediate all
assets" from a stale page no longer flips back an asset a colleague
already remediated (the endpoint used to only toggle)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select

from models.asset import Asset
from models.associations import FindingAsset
from models.finding import Finding, Severity
from tests.test_authz_boundaries import _make_engagement


async def _link(db_session, remediated):
    eng = await _make_engagement(db_session)
    f = Finding(id=str(uuid.uuid4()), engagement_id=eng.id, title="F", description="d", severity=Severity.HIGH)
    a = Asset(id=str(uuid.uuid4()), engagement_id=eng.id, name="web01", asset_type="Server",
              identifier=f"10.9.{uuid.uuid4().int % 250}.1")
    db_session.add_all([f, a])
    await db_session.flush()
    db_session.add(FindingAsset(finding_id=f.id, asset_id=a.id, remediated=remediated,
                                remediated_at=datetime(2026, 1, 2) if remediated else None))
    await db_session.flush()
    return f.id, a.id


async def _state(db_session, fid, aid):
    fa = (await db_session.execute(select(FindingAsset).where(
        FindingAsset.finding_id == fid, FindingAsset.asset_id == aid)
        .execution_options(populate_existing=True))).scalar_one()
    return fa.remediated, fa.remediated_at


async def test_setting_true_keeps_an_already_remediated_asset(client, db_session, make_user, authenticate_as):
    fid, aid = await _link(db_session, remediated=True)
    authenticate_as(await make_user(role="admin"))
    r = await client.patch(f"/findings/{fid}/assets/{aid}/remediate", params={"remediated": "true"})
    assert r.status_code == 200 and r.json()["remediated"] is True
    assert await _state(db_session, fid, aid) == (True, datetime(2026, 1, 2))   # untouched


async def test_explicit_false_and_plain_toggle(client, db_session, make_user, authenticate_as):
    fid, aid = await _link(db_session, remediated=True)
    authenticate_as(await make_user(role="admin"))
    await client.patch(f"/findings/{fid}/assets/{aid}/remediate", params={"remediated": "false"})
    assert (await _state(db_session, fid, aid))[0] is False
    await client.patch(f"/findings/{fid}/assets/{aid}/remediate", params={"remediated": "false"})
    assert (await _state(db_session, fid, aid))[0] is False
    await client.patch(f"/findings/{fid}/assets/{aid}/remediate")                 # no param: toggles
    assert (await _state(db_session, fid, aid))[0] is True
