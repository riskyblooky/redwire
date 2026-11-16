"""A group-granted VIEW_ALL_ENGAGEMENTS reads every engagement's content
without an assignment, except the vault, and grants no writes. Before, it
could list findings/assets/test cases but 403'd opening the engagement,
its notes, report layouts and cleanup items, while /my-permissions claimed
vault access the API then refused."""

from __future__ import annotations

import uuid

from models.permission import Permission


async def _view_all_user(db_session, make_user):
    from models.group import Group, user_groups
    from models.permission import GroupPermissions
    u = await make_user()
    g = Group(id=str(uuid.uuid4()), name=f"view-all {uuid.uuid4().hex[:6]}")
    db_session.add(g)
    await db_session.flush()
    db_session.add(GroupPermissions(group_id=g.id, permissions=[Permission.VIEW_ALL_ENGAGEMENTS.value]))
    await db_session.execute(user_groups.insert().values(user_id=u.id, group_id=g.id))
    await db_session.flush()
    return u


async def test_view_all_reads_everything_but_the_vault(client, db_session, make_user, authenticate_as):
    from tests.test_authz_boundaries import _make_engagement
    eng = await _make_engagement(db_session)
    u = await _view_all_user(db_session, make_user)
    eid = eng.id
    db_session.expunge_all()
    authenticate_as(u)
    for path in (f"/engagements/{eid}", f"/engagements/{eid}/notes", f"/engagements/{eid}/report-layouts",
                 f"/cleanup-artifacts?engagement_id={eid}", f"/findings?engagement_id={eid}"):
        r = await client.get(path)
        assert r.status_code == 200, (path, r.text)
    assert (await client.get(f"/vault?engagement_id={eid}")).status_code == 403
    # No writes from a read grant.
    assert (await client.put(f"/engagements/{eid}", json={"description": "x"})).status_code == 403

    perms = set((await client.get(f"/engagements/{eid}/my-permissions")).json())
    assert {"engagement_view", "note_view", "cleanup_view"} <= perms
    assert "vault_view" not in perms and "finding_edit" not in perms


async def test_without_view_all_still_403(client, db_session, make_user, authenticate_as):
    from tests.test_authz_boundaries import _make_engagement
    eng = await _make_engagement(db_session)
    u = await make_user()
    eid = eng.id
    db_session.expunge_all()
    authenticate_as(u)
    assert (await client.get(f"/engagements/{eid}")).status_code == 403
    assert (await client.get(f"/engagements/{eid}/notes")).status_code == 403
