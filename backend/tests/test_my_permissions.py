"""The permission lists the UI gates buttons on (/users/me/permissions and
/engagements/{id}/my-permissions) report exactly what the API enforces:
read-only admins hold view permissions plus explicit grants, not every
write; team leads hold only group-granted global permissions."""

from __future__ import annotations

from tests.test_authz_boundaries import _assign, _make_engagement, _make_engagement_role
from tests.test_user_manager_ceiling import _group, _join


async def test_ro_admin_global_permissions_are_view_only(client, db_session, make_user, authenticate_as):
    ro = await make_user(role="read_only_admin")
    await _join(db_session, ro, await _group(db_session, "manage_tags"))
    authenticate_as(ro)
    perms = (await client.get("/users/me/permissions")).json()
    assert "view_all_users" in perms and "manage_tags" in perms
    assert "manage_users" not in perms and "manage_groups" not in perms


async def test_team_lead_global_permissions_are_group_grants(client, db_session, make_user, authenticate_as):
    authenticate_as(await make_user(role="team_lead"))
    assert (await client.get("/users/me/permissions")).json() == []


async def test_ro_admin_engagement_permissions(client, db_session, make_user, authenticate_as):
    ro = await make_user(role="read_only_admin")
    eng = await _make_engagement(db_session)
    await _assign(db_session, ro, eng, await _make_engagement_role(db_session, ["finding_edit"]))
    authenticate_as(ro)
    perms = (await client.get(f"/engagements/{eng.id}/my-permissions")).json()
    assert {"finding_view", "vault_view", "finding_edit"} <= set(perms)
    assert "finding_delete_any" not in perms and "engagement_delete" not in perms


async def test_team_lead_engagement_permissions_are_full(client, db_session, make_user, authenticate_as):
    eng = await _make_engagement(db_session)
    authenticate_as(await make_user(role="team_lead"))
    perms = set((await client.get(f"/engagements/{eng.id}/my-permissions")).json())
    assert {"engagement_delete", "finding_delete_any", "discussion_create"} <= perms
