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


# ── #6 lists / search / feed need the per-resource view permission ───────

@pytest.fixture
async def member_without_finding_view(db_session, make_user):
    eng = await _make_engagement(db_session)
    user = await make_user()
    await _assign(db_session, user, eng, await _make_engagement_role(db_session, ["engagement_view", "note_view"]))
    finding = await _make_finding(db_session, eng, title="ZZsecretADCS finding")
    return user, eng, finding


async def test_finding_list_and_search_need_finding_view(client, db_session, member_without_finding_view,
                                                         authenticate_as):
    user, eng, finding = member_without_finding_view
    authenticate_as(user)
    assert (await client.get("/findings", params={"engagement_id": eng.id})).json() == []
    assert (await client.get("/findings")).json() == []
    body = (await client.get("/search", params={"q": "ZZsecretADCS"})).json()
    assert finding.id not in str(body)


async def test_finding_list_allowed_with_finding_view(client, db_session, make_user, authenticate_as):
    eng = await _make_engagement(db_session)
    user = await make_user()
    await _assign(db_session, user, eng, await _make_engagement_role(db_session, ["finding_view"]))
    finding = await _make_finding(db_session, eng)
    authenticate_as(user)
    assert [f["id"] for f in (await client.get("/findings", params={"engagement_id": eng.id})).json()] == [finding.id]


async def test_activity_feed_drops_types_without_view(client, db_session, member_without_finding_view,
                                                      authenticate_as):
    from models.discussion import ActivityLog
    user, eng, finding = member_without_finding_view
    for rtype, rid in (("finding", finding.id), ("note", str(uuid.uuid4()))):
        db_session.add(ActivityLog(engagement_id=eng.id, user_id=user.id, action=f"created_{rtype}",
                                   resource_type=rtype, resource_id=rid, resource_name=rtype))
    await db_session.flush()
    authenticate_as(user)
    feed = (await client.get("/discussions/activity/feed", params={"engagement_id": eng.id})).json()
    assert [i["resource_type"] for i in feed["items"]] == ["note"] and feed["total"] == 1


async def test_engagement_evidence_list_needs_evidence_view(client, db_session, member_without_finding_view,
                                                            authenticate_as):
    user, eng, _ = member_without_finding_view
    authenticate_as(user)
    assert (await client.get(f"/engagements/{eng.id}/evidence")).status_code == 403


# ── #7 intel item linked entities ────────────────────────────────────────

async def test_intel_detail_hides_and_unlink_guards_other_engagements(client, db_session, make_user,
                                                                      authenticate_as):
    from models.associations import IntelItemFinding
    from models.group import Group, user_groups
    from models.intel_item import IntelItem
    from models.permission import GroupPermissions
    mine, theirs = await _make_engagement(db_session), await _make_engagement(db_session)
    user = await make_user()
    await _assign(db_session, user, mine, await _make_engagement_role(db_session, ["finding_view"]))
    g = Group(id=str(uuid.uuid4()), name=f"intel_{uuid.uuid4().hex[:6]}")
    db_session.add(g)
    await db_session.flush()
    db_session.add(GroupPermissions(group_id=g.id, permissions=["intel_view", "intel_edit"]))
    await db_session.execute(user_groups.insert().values(user_id=user.id, group_id=g.id))
    item = IntelItem(id=str(uuid.uuid4()), title="CVE-2099-0001")
    db_session.add(item)
    visible, hidden = await _make_finding(db_session, mine), await _make_finding(db_session, theirs, title="ACME DC01")
    await db_session.flush()
    for f in (visible, hidden):
        db_session.add(IntelItemFinding(intel_item_id=item.id, finding_id=f.id))
    await db_session.flush()

    authenticate_as(user)
    detail = (await client.get(f"/intel/items/{item.id}")).json()
    assert [f["id"] for f in detail["linked_findings"]] == [visible.id]
    r = await client.request("DELETE", f"/intel/items/{item.id}/link",
                             json={"entity_type": "finding", "entity_id": hidden.id})
    assert r.status_code == 403


# ── #9 attack-graph attacker edges ───────────────────────────────────────

async def test_attacker_edges_need_attacker_in_path_engagement(client, db_session, make_user, authenticate_as):
    from sqlalchemy import select
    from models.attacker_node import AttackerNode, AttackerNodeEdge
    mine, theirs = await _make_engagement(db_session), await _make_engagement(db_session)
    user = await make_user()
    await _assign(db_session, user, mine, await _make_engagement_role(db_session, ["engagement_view", "engagement_edit"]))
    foreign = AttackerNode(id=str(uuid.uuid4()), engagement_id=theirs.id)
    db_session.add(foreign)
    await db_session.flush()
    edge = AttackerNodeEdge(id=str(uuid.uuid4()), attacker_node_id=foreign.id,
                            target_node_id="testcase-x", target_node_type="testcase")
    db_session.add(edge)
    await db_session.flush()

    authenticate_as(user)
    base = f"/engagements/{mine.id}/attack-graph/attacker/{foreign.id}/edge"
    assert (await client.delete(f"{base}/{edge.id}")).status_code == 404
    assert (await client.post(base, json={"target_node_id": "testcase-x"})).status_code == 404
    assert (await db_session.execute(select(AttackerNodeEdge).where(AttackerNodeEdge.id == edge.id))).scalar_one_or_none()
