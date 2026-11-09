"""Engagement-scoping regressions from the 2026-11-08 review: links and
restores that skipped the checks their sibling endpoints already make."""

from __future__ import annotations

import uuid

import pytest

from tests.test_authz_boundaries import _assign, _make_engagement, _make_engagement_role, _make_finding


async def _artifact(db, engagement, created_by=None):
    from models.cleanup_artifact import CleanupArtifact
    a = CleanupArtifact(id=str(uuid.uuid4()), engagement_id=engagement.id, title="dropper.exe",
                        artifact_type="file", created_by=created_by)
    db.add(a)
    await db.flush()
    return a


async def _asset(db, engagement):
    from models.asset import Asset
    a = Asset(id=str(uuid.uuid4()), engagement_id=engagement.id, name="dc01", identifier="10.0.0.5",
              asset_type="host")
    db.add(a)
    await db.flush()
    return a


# ── #3 cleanup artifact links ────────────────────────────────────────────

async def test_cleanup_link_rejects_other_engagement(client, db_session, make_user, authenticate_as):
    mine, theirs = await _make_engagement(db_session), await _make_engagement(db_session)
    authenticate_as(await make_user(role="admin"))
    art = await _artifact(db_session, mine)
    other_finding = await _make_finding(db_session, theirs)
    other_asset = await _asset(db_session, theirs)
    r = await client.post(f"/cleanup-artifacts/{art.id}/findings/{other_finding.id}")
    assert r.status_code == 400
    r = await client.post(f"/cleanup-artifacts/{art.id}/assets/{other_asset.id}")
    assert r.status_code == 400
    own = await _make_finding(db_session, mine)
    assert (await client.post(f"/cleanup-artifacts/{art.id}/findings/{own.id}")).status_code == 201


# ── #4 finding version restore ───────────────────────────────────────────

async def _version(db, finding, **snap):
    from models.version_history import VersionHistory
    v = VersionHistory(id=str(uuid.uuid4()), entity_type="finding", entity_id=finding.id, version=1,
                       snapshot={"title": "old title", **snap}, changed_fields=["title"])
    db.add(v)
    await db.flush()
    return v


async def test_restore_needs_edit_any_on_others_finding(client, db_session, make_user, authenticate_as):
    eng = await _make_engagement(db_session)
    author, other = await make_user(), await make_user()
    role = await _make_engagement_role(db_session, ["finding_view", "finding_edit"])
    await _assign(db_session, other, eng, role)
    f = await _make_finding(db_session, eng, created_by=author.id)
    v = await _version(db_session, f)
    authenticate_as(other)
    r = await client.post(f"/findings/{f.id}/versions/{v.id}/restore")
    assert r.status_code == 403 and "finding_edit_any" in r.json()["detail"]


async def test_author_cannot_restore_to_verified(client, db_session, make_user, authenticate_as):
    from models.finding import FindingStatus
    eng = await _make_engagement(db_session)
    author = await make_user()
    await _assign(db_session, author, eng, await _make_engagement_role(db_session, ["finding_view", "finding_edit"]))
    f = await _make_finding(db_session, eng, created_by=author.id, status=FindingStatus.OPEN)
    authenticate_as(author)
    verified = await _version(db_session, f, status="VERIFIED")
    r = await client.post(f"/findings/{f.id}/versions/{verified.id}/restore")
    assert r.status_code == 403 and "VERIFIED" in r.json()["detail"]
