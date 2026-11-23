"""auth.rbac.engagement_permissions is the set form of has_engagement_perm:
for every kind of user it must name exactly the permissions the per-check
path grants. /my-permissions (which the UI uses to show actions) and the
markdown-image upload gate both read it; before, they used a second engine
in auth.permissions that could drift from the checks the API enforces."""

from __future__ import annotations

import pytest

from models.permission import ENGAGEMENT_PERMISSIONS, Permission
from auth.rbac import engagement_permissions, has_engagement_perm
from tests.test_authz_boundaries import _assign, _make_engagement, _make_engagement_role
from tests.test_view_all_engagements import _view_all_user


async def _expected(user, eid, db):
    return {p.value for p in ENGAGEMENT_PERMISSIONS if await has_engagement_perm(user, eid, p, db)}


@pytest.mark.parametrize("kind", ["member", "view_all", "view_all_member", "unassigned",
                                  "read_only_admin", "read_only_admin_member", "team_lead", "admin"])
async def test_set_matches_per_permission_checks(kind, db_session, make_user):
    eng = await _make_engagement(db_session)
    role = await _make_engagement_role(db_session, [Permission.FINDING_EDIT.value, Permission.FINDING_VIEW.value,
                                                    Permission.VAULT_VIEW.value])
    if kind.startswith("view_all"):
        user = await _view_all_user(db_session, make_user)
    elif kind.startswith("read_only_admin"):
        user = await make_user(role="read_only_admin")
    elif kind in ("team_lead", "admin"):
        user = await make_user(role=kind)
    else:
        user = await make_user()
    if kind.endswith("member"):
        await _assign(db_session, user, eng, role)

    got = await engagement_permissions(user, eng.id, db_session)
    assert got == await _expected(user, eng.id, db_session)

    if kind == "member":
        assert got == {"finding_edit", "finding_view", "vault_view"}
    if kind == "unassigned":
        assert got == set()
    if kind == "view_all":
        assert "engagement_view" in got and "vault_view" not in got and "finding_edit" not in got
    if kind == "read_only_admin_member":
        assert "finding_edit" in got and "finding_delete" not in got


async def test_markdown_image_gate_uses_the_same_set(db_session, make_user):
    """A view-only member can't upload; a member with any write can."""
    from fastapi import HTTPException
    from routers.markdown_images import _check_engagement_write
    eng = await _make_engagement(db_session)
    viewer, writer = await make_user(), await make_user()
    await _assign(db_session, viewer, eng, await _make_engagement_role(db_session, [Permission.FINDING_VIEW.value]))
    await _assign(db_session, writer, eng, await _make_engagement_role(db_session, [Permission.NOTE_CREATE.value]))
    with pytest.raises(HTTPException) as e:
        await _check_engagement_write(viewer, eng.id, db_session)
    assert e.value.status_code == 403
    await _check_engagement_write(writer, eng.id, db_session)
    await _check_engagement_write(await make_user(role="team_lead"), eng.id, db_session)
