"""Group create/update responses carry the real member count and the
system/default flags (they reported member_count=0 and dropped both)."""

from __future__ import annotations


async def test_group_update_reports_members(client, db_session, make_user, authenticate_as):
    from tests.test_user_manager_ceiling import _group, _join
    admin = await make_user(role="admin")
    g = await _group(db_session)
    for _ in range(2):
        await _join(db_session, await make_user(), g)
    authenticate_as(admin)
    r = await client.put(f"/admin/permissions/groups/{g.id}", json={"name": g.name + "x", "description": "d"})
    assert r.status_code == 200, r.text
    assert r.json()["member_count"] == 2 and r.json()["is_default"] is False
    r = await client.put(f"/admin/permissions/groups/{g.id}/permissions", json={"permissions": ["stats_view"]})
    assert r.status_code == 200, r.text
    assert r.json()["member_count"] == 2 and r.json()["permissions"] == ["stats_view"]
    listed = {x["id"]: x for x in (await client.get("/admin/permissions/groups")).json()}
    assert listed[g.id]["member_count"] == 2
