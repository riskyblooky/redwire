"""Group and engagement-role permission edits are held to a ceiling in both
directions: a non-admin manager may only add or remove permissions they
hold, and only delete a group / role whose permissions they all hold.
TEAM_LEAD holds every engagement permission."""

from __future__ import annotations

from tests.test_authz_boundaries import _assign, _make_engagement, _make_engagement_role
from tests.test_user_manager_ceiling import _group, _join


async def _group_manager(db, make_user, *extra):
    mgr = await make_user(role="operator")
    await _join(db, mgr, await _group(db, "manage_groups", *extra))
    return mgr


async def test_group_removal_needs_the_permission(client, db_session, make_user, authenticate_as):
    target = await _group(db_session, "manage_users", "view_all_users")
    authenticate_as(await _group_manager(db_session, make_user, "view_all_users"))
    url = f"/admin/permissions/groups/{target.id}/permissions"
    r = await client.put(url, json={"permissions": ["view_all_users"]})  # strips manage_users
    assert r.status_code == 403 and "manage_users" in r.json()["detail"]
    r = await client.put(url, json={"permissions": ["manage_users"]})  # strips only view_all_users: held
    assert r.status_code == 200, r.text


async def test_group_delete_needs_its_permissions(client, db_session, make_user, authenticate_as):
    richer = await _group(db_session, "manage_users")
    mine = await _group(db_session, "view_all_users")
    authenticate_as(await _group_manager(db_session, make_user, "view_all_users"))
    assert (await client.delete(f"/admin/permissions/groups/{richer.id}")).status_code == 403
    assert (await client.delete(f"/admin/permissions/groups/{mine.id}")).status_code == 204


async def _role_manager(db, make_user, role="operator", eng_perms=()):
    mgr = await make_user(role=role)
    await _join(db, mgr, await _group(db, "manage_engagement_roles"))
    if eng_perms:
        await _assign(db, mgr, await _make_engagement(db), await _make_engagement_role(db, list(eng_perms)))
    return mgr


async def test_engagement_role_ceiling(client, db_session, make_user, authenticate_as):
    role = await _make_engagement_role(db_session, ["finding_view", "finding_delete_any"])
    authenticate_as(await _role_manager(db_session, make_user, eng_perms=["finding_view", "finding_edit"]))
    url = f"/admin/permissions/engagement-roles/{role.id}/permissions"
    for perms, bad in ((["finding_view", "finding_delete_any", "vault_view"], "vault_view"),  # add unheld
                       (["finding_view"], "finding_delete_any")):                              # remove unheld
        r = await client.put(url, json={"permissions": perms})
        assert r.status_code == 403 and bad in r.json()["detail"], perms
    r = await client.put(url, json={"permissions": ["finding_delete_any", "finding_edit"]})  # held changes only
    assert r.status_code == 200, r.text
    assert (await client.delete(f"/admin/permissions/engagement-roles/{role.id}")).status_code == 403


async def test_team_lead_has_full_engagement_ceiling(client, db_session, make_user, authenticate_as):
    role = await _make_engagement_role(db_session, ["finding_view"])
    authenticate_as(await _role_manager(db_session, make_user, role="team_lead"))
    r = await client.put(f"/admin/permissions/engagement-roles/{role.id}/permissions",
                         json={"permissions": ["engagement_delete", "vault_view", "finding_delete_any"]})
    assert r.status_code == 200, r.text
    assert (await client.delete(f"/admin/permissions/engagement-roles/{role.id}")).status_code == 204


async def test_team_lead_without_grant_cannot_edit_roles(client, db_session, make_user, authenticate_as):
    role = await _make_engagement_role(db_session, ["finding_view"])
    authenticate_as(await make_user(role="team_lead"))
    r = await client.put(f"/admin/permissions/engagement-roles/{role.id}/permissions", json={"permissions": []})
    assert r.status_code == 403
