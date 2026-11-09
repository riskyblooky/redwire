"""ENGAGEMENT_MANAGE_MEMBERS may hand out any engagement role — including
to yourself — but only within that engagement; bad user / role ids and
duplicate entries are a 400, not a 500."""

from __future__ import annotations

from sqlalchemy import select

from tests.test_authz_boundaries import _assign, _make_engagement, _make_engagement_role


async def _setup(db, make_user):
    eng = await _make_engagement(db)
    manager = await make_user(role="operator")
    await _assign(db, manager, eng, await _make_engagement_role(db, ["engagement_view", "engagement_edit",
                                                                    "engagement_manage_members"]))
    return eng, manager


async def test_member_manager_can_assign_any_role_in_their_engagement(client, db_session, make_user,
                                                                      authenticate_as):
    from models.associations import EngagementAssignment
    eng, manager = await _setup(db_session, make_user)
    lead = await _make_engagement_role(db_session, ["engagement_view", "engagement_delete", "finding_delete_any"])
    peer = await make_user(role="operator")
    authenticate_as(manager)
    r = await client.put(f"/engagements/{eng.id}", json={"assignments": [
        {"user_id": manager.id, "role_id": lead.id}, {"user_id": peer.id, "role_id": lead.id}]})
    assert r.status_code == 200, r.text
    rows = (await db_session.execute(select(EngagementAssignment.user_id, EngagementAssignment.role_id)
                                     .where(EngagementAssignment.engagement_id == eng.id))).all()
    assert sorted(rows) == sorted([(manager.id, lead.id), (peer.id, lead.id)])


async def test_bad_assignments_are_400(client, db_session, make_user, authenticate_as):
    eng, manager = await _setup(db_session, make_user)
    role = await _make_engagement_role(db_session, [])
    authenticate_as(manager)
    for assignments, needle in (
        ([{"user_id": manager.id, "role_id": "no-such-role"}], "role"),
        ([{"user_id": "no-such-user", "role_id": role.id}], "user"),
        ([{"user_id": manager.id, "role_id": role.id}, {"user_id": manager.id, "role_id": None}], "more than once"),
    ):
        r = await client.put(f"/engagements/{eng.id}", json={"assignments": assignments})
        assert r.status_code == 400 and needle in r.json()["detail"], (assignments, r.text)


async def test_member_manager_cannot_touch_other_engagements(client, db_session, make_user, authenticate_as):
    _eng, manager = await _setup(db_session, make_user)
    other = await _make_engagement(db_session)
    role = await _make_engagement_role(db_session, [])
    authenticate_as(manager)
    r = await client.put(f"/engagements/{other.id}", json={"assignments": [{"user_id": manager.id, "role_id": role.id}]})
    assert r.status_code == 403
