"""A delegated MANAGE_USERS holder (non-ADMIN) can't escalate through the
/admin/users endpoints: no assigning roles above their own, no acting on
accounts that hold more than they do, no joining groups whose permissions
they lack. The old unguarded /users write duplicates are gone."""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException


async def _group(db, *perms):
    from models.group import Group
    from models.permission import GroupPermissions
    g = Group(id=str(uuid.uuid4()), name=f"g_{uuid.uuid4().hex[:6]}")
    db.add(g)
    await db.flush()
    db.add(GroupPermissions(group_id=g.id, permissions=list(perms)))
    await db.flush()
    return g


async def _join(db, user, group):
    from models.group import user_groups
    await db.execute(user_groups.insert().values(user_id=user.id, group_id=group.id))
    await db.flush()


@pytest.fixture
async def manager(db_session, make_user):
    mgr = await make_user(role="operator")
    await _join(db_session, mgr, await _group(db_session, "manage_users", "view_all_users"))
    return mgr


async def test_cannot_self_promote(client, manager, authenticate_as):
    authenticate_as(manager)
    for role in ("admin", "read_only_admin", "team_lead"):
        r = await client.patch(f"/admin/users/{manager.id}", json={"role": role})
        assert r.status_code == 403, role


async def test_cannot_create_privileged_user(client, manager, authenticate_as):
    authenticate_as(manager)
    r = await client.post("/admin/users", json={
        "username": f"x{uuid.uuid4().hex[:6]}", "email": f"{uuid.uuid4().hex[:6]}@example.com",
        "password": "Sup3rSecret!pw", "role": "admin",
    })
    assert r.status_code == 403


async def test_cannot_touch_admin_or_richer_account(client, db_session, manager, make_user, authenticate_as):
    admin = await make_user(role="admin")
    richer = await make_user(role="operator")
    await _join(db_session, richer, await _group(db_session, "manage_groups"))
    authenticate_as(manager)
    for target in (admin, richer):
        assert (await client.post(f"/admin/users/{target.id}/reset-password")).status_code == 403
        assert (await client.delete(f"/admin/users/{target.id}")).status_code == 403
        assert (await client.patch(f"/admin/users/{target.id}", json={"is_active": False})).status_code == 403


async def test_cannot_join_richer_group(client, db_session, manager, authenticate_as):
    richer = await _group(db_session, "manage_users", "manage_groups")
    authenticate_as(manager)
    r = await client.patch(f"/admin/users/{manager.id}", json={"group_ids": [richer.id]})
    assert r.status_code == 403


async def test_unguarded_users_duplicates_removed(client, manager, make_user, authenticate_as):
    target = await make_user(role="operator")
    authenticate_as(manager)
    assert (await client.put(f"/users/{target.id}", json={"role": "admin"})).status_code == 405
    assert (await client.delete(f"/users/{target.id}")).status_code == 405


async def test_guard_allows_within_ceiling(db_session, manager, make_user):
    from models.user import UserRole
    from routers.admin import _guard_user_admin_action
    peer = await make_user(role="operator")
    same = await _group(db_session, "view_all_users")
    await _guard_user_admin_action(manager, db_session, target=peer, new_role=UserRole.READ_ONLY,
                                   added_group_ids={same.id})
    with pytest.raises(HTTPException):
        await _guard_user_admin_action(manager, db_session, target=peer, new_role=UserRole.TEAM_LEAD)


async def test_admin_unrestricted(db_session, make_user):
    from models.user import UserRole
    from routers.admin import _guard_user_admin_action
    admin = await make_user(role="admin")
    other = await make_user(role="admin")
    await _guard_user_admin_action(admin, db_session, target=other, new_role=UserRole.ADMIN,
                                   added_group_ids={(await _group(db_session, "manage_groups")).id})


async def test_unguarded_group_and_role_duplicates_removed(client, db_session, make_user, authenticate_as):
    from models.group import Group
    from sqlalchemy import select
    authenticate_as(await make_user(role="admin"))
    default = (await db_session.execute(select(Group).where(Group.is_default == True))).scalars().first()  # noqa: E712
    for method, path in (("post", "/admin/groups"), ("patch", "/admin/groups/x"), ("delete", "/admin/groups/x"),
                         ("post", "/admin/engagement-roles"), ("patch", "/admin/engagement-roles/x")):
        assert (await getattr(client, method)(path)).status_code in (404, 405), path
    if default:
        assert (await client.delete(f"/admin/permissions/groups/{default.id}")).status_code == 403
