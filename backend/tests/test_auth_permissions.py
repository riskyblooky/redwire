"""Permission-resolution tests for ``auth/permissions.py``.

This module (distinct from ``auth/rbac.py``) resolves RBAC decisions from a
user's role, their group grants, and their engagement-role assignment. The
helpers all read from the DB via ``AsyncSession.execute``, so we drive them
with the shared ``FakeDb`` fake and queue the exact scalar shapes each query
pulls — mirroring the ``test_stats_scope`` house style.

Contracts pinned:
  * role short-circuits: ADMIN bypasses everything; TEAM_LEAD bypasses
    engagement perms; READ_ONLY_ADMIN bypasses *read* perms only, and write
    perms still fall through to the grant lookup.
  * the "is this even a global/engagement permission" gate returns False for
    a permission of the wrong class before any grant is honoured.
  * group grants (global) and engagement-role grants are consulted correctly.
  * ``VIEW_ALL_ENGAGEMENTS`` acts as a global override for the view-style
    engagement permissions.
  * ``can_modify_resource`` ownership-vs-edit_any logic.
  * ``get_user_engagement_permissions`` aggregation.
"""

from __future__ import annotations

import pytest

from tests.conftest import FakeDb, FakeScalarResult, make_fake_user

from auth.permissions import (
    _is_read_permission,
    has_global_permission,
    has_engagement_permission,
    can_modify_resource,
    get_user_engagement_permissions,
)
from models.permission import Permission


# ── _is_read_permission ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "perm",
    [Permission.VIEW_ALL_USERS, Permission.FINDING_VIEW, Permission.ENGAGEMENT_VIEW],
)
def test_is_read_permission_true_for_view_shaped(perm):
    assert _is_read_permission(perm) is True


@pytest.mark.parametrize(
    "perm",
    [Permission.MANAGE_USERS, Permission.FINDING_EDIT, Permission.FINDING_DELETE_ANY],
)
def test_is_read_permission_false_for_write_shaped(perm):
    assert _is_read_permission(perm) is False


# ── has_global_permission ─────────────────────────────────────────────────


async def test_admin_has_every_global_permission():
    # ADMIN returns True with no DB lookup — queue nothing.
    db = FakeDb([])
    assert await has_global_permission(make_fake_user("admin"), Permission.MANAGE_USERS, db) is True


async def test_read_only_admin_gets_read_global_perm():
    db = FakeDb([])
    assert (
        await has_global_permission(
            make_fake_user("read_only_admin"), Permission.VIEW_ALL_USERS, db
        )
        is True
    )


async def test_read_only_admin_denied_write_global_perm_without_group_grant():
    # Write perm → falls through to the group query, which returns no rows.
    db = FakeDb([FakeScalarResult(many=[])])
    assert (
        await has_global_permission(
            make_fake_user("read_only_admin"), Permission.MANAGE_USERS, db
        )
        is False
    )


async def test_non_global_permission_is_rejected():
    """An engagement-class permission passed to the global checker returns
    False before any group grant can apply."""
    db = FakeDb([FakeScalarResult(many=[["finding_view"]])])
    assert (
        await has_global_permission(
            make_fake_user("operator"), Permission.FINDING_VIEW, db
        )
        is False
    )


async def test_group_grant_confers_global_permission():
    db = FakeDb([FakeScalarResult(many=[["manage_users", "view_all_users"]])])
    assert (
        await has_global_permission(make_fake_user("operator"), Permission.MANAGE_USERS, db)
        is True
    )


async def test_group_without_grant_denies_global_permission():
    db = FakeDb([FakeScalarResult(many=[["view_all_users"]])])
    assert (
        await has_global_permission(make_fake_user("operator"), Permission.MANAGE_USERS, db)
        is False
    )


# ── has_engagement_permission ─────────────────────────────────────────────


@pytest.mark.parametrize("role", ["admin", "team_lead"])
async def test_admin_and_team_lead_bypass_engagement_perms(role):
    db = FakeDb([])
    assert (
        await has_engagement_permission(
            make_fake_user(role), "eng-1", Permission.FINDING_DELETE, db
        )
        is True
    )


async def test_read_only_admin_gets_read_engagement_perm():
    db = FakeDb([])
    assert (
        await has_engagement_permission(
            make_fake_user("read_only_admin"), "eng-1", Permission.FINDING_VIEW, db
        )
        is True
    )


async def test_read_only_admin_denied_write_engagement_perm():
    # Write perm → role assignment lookup (scalar_one_or_none) returns nothing.
    db = FakeDb([FakeScalarResult(None)])
    assert (
        await has_engagement_permission(
            make_fake_user("read_only_admin"), "eng-1", Permission.FINDING_EDIT, db
        )
        is False
    )


async def test_non_engagement_permission_is_rejected():
    db = FakeDb([])
    assert (
        await has_engagement_permission(
            make_fake_user("operator"), "eng-1", Permission.MANAGE_USERS, db
        )
        is False
    )


async def test_engagement_role_grant_confers_permission():
    # Single query: the role-permissions lookup via scalar_one_or_none.
    db = FakeDb([FakeScalarResult(["finding_edit", "finding_create"])])
    assert (
        await has_engagement_permission(
            make_fake_user("operator"), "eng-1", Permission.FINDING_EDIT, db
        )
        is True
    )


async def test_engagement_role_without_grant_denies():
    db = FakeDb([FakeScalarResult(None)])
    assert (
        await has_engagement_permission(
            make_fake_user("operator"), "eng-1", Permission.FINDING_EDIT, db
        )
        is False
    )


async def test_view_all_engagements_overrides_view_permission():
    """A view-style engagement perm is granted when the user's group carries
    VIEW_ALL_ENGAGEMENTS — resolved via has_global_permission BEFORE the
    per-engagement role lookup. First query is the global-group scan."""
    db = FakeDb([FakeScalarResult(many=[["view_all_engagements"]])])
    assert (
        await has_engagement_permission(
            make_fake_user("operator"), "eng-1", Permission.FINDING_VIEW, db
        )
        is True
    )


async def test_view_all_engagements_does_not_override_write_permission():
    """The override only maps to view perms; a write perm ignores it and
    must resolve purely through the role assignment (here: none)."""
    # No admin_overrides entry matches FINDING_EDIT → only the role query runs.
    db = FakeDb([FakeScalarResult(None)])
    assert (
        await has_engagement_permission(
            make_fake_user("operator"), "eng-1", Permission.FINDING_EDIT, db
        )
        is False
    )


# ── can_modify_resource ───────────────────────────────────────────────────


async def test_owner_without_engagement_can_always_modify():
    user = make_fake_user("operator")
    db = FakeDb([])
    assert (
        await can_modify_resource(
            resource_owner_id=user.id,
            current_user=user,
            engagement_id=None,
            edit_permission=Permission.NOTE_EDIT,
            edit_any_permission=Permission.NOTE_EDIT_ANY,
            db=db,
        )
        is True
    )


async def test_owner_with_engagement_needs_edit_permission():
    user = make_fake_user("operator")
    # Owner path defers to has_engagement_permission(edit_permission).
    db = FakeDb([FakeScalarResult(["finding_edit"])])
    assert (
        await can_modify_resource(
            resource_owner_id=user.id,
            current_user=user,
            engagement_id="eng-1",
            edit_permission=Permission.FINDING_EDIT,
            edit_any_permission=Permission.FINDING_EDIT_ANY,
            db=db,
        )
        is True
    )


async def test_owner_with_engagement_denied_without_edit_permission():
    user = make_fake_user("operator")
    db = FakeDb([FakeScalarResult(None)])
    assert (
        await can_modify_resource(
            resource_owner_id=user.id,
            current_user=user,
            engagement_id="eng-1",
            edit_permission=Permission.FINDING_EDIT,
            edit_any_permission=Permission.FINDING_EDIT_ANY,
            db=db,
        )
        is False
    )


async def test_non_owner_needs_edit_any():
    user = make_fake_user("operator")
    db = FakeDb([FakeScalarResult(["finding_edit_any"])])
    assert (
        await can_modify_resource(
            resource_owner_id="someone-else",
            current_user=user,
            engagement_id="eng-1",
            edit_permission=Permission.FINDING_EDIT,
            edit_any_permission=Permission.FINDING_EDIT_ANY,
            db=db,
        )
        is True
    )


async def test_non_owner_without_edit_any_permission_denied():
    user = make_fake_user("operator")
    db = FakeDb([FakeScalarResult(None)])
    assert (
        await can_modify_resource(
            resource_owner_id="someone-else",
            current_user=user,
            engagement_id="eng-1",
            edit_permission=Permission.FINDING_EDIT,
            edit_any_permission=Permission.FINDING_EDIT_ANY,
            db=db,
        )
        is False
    )


async def test_non_owner_with_no_edit_any_declared_denied():
    """No edit_any permission passed → non-owner can never modify, no DB hit."""
    user = make_fake_user("operator")
    db = FakeDb([])
    assert (
        await can_modify_resource(
            resource_owner_id="someone-else",
            current_user=user,
            engagement_id="eng-1",
            edit_permission=Permission.FINDING_EDIT,
            edit_any_permission=None,
            db=db,
        )
        is False
    )


async def test_non_owner_edit_any_without_engagement_denied():
    """edit_any is only consulted when an engagement context exists."""
    user = make_fake_user("operator")
    db = FakeDb([])
    assert (
        await can_modify_resource(
            resource_owner_id="someone-else",
            current_user=user,
            engagement_id=None,
            edit_permission=Permission.NOTE_EDIT,
            edit_any_permission=Permission.NOTE_EDIT_ANY,
            db=db,
        )
        is False
    )


# ── get_user_engagement_permissions ───────────────────────────────────────


async def test_get_perms_returns_role_assignment_perms():
    # First query: role perms (scalar_one_or_none). Second: global groups (all()).
    db = FakeDb(
        [
            FakeScalarResult(["finding_edit", "finding_create"]),
            FakeScalarResult(many=[]),
        ]
    )
    perms = await get_user_engagement_permissions("u-1", "eng-1", db)
    assert set(perms) == {"finding_edit", "finding_create"}


async def test_get_perms_empty_when_no_grants():
    db = FakeDb([FakeScalarResult(None), FakeScalarResult(many=[])])
    perms = await get_user_engagement_permissions("u-1", "eng-1", db)
    assert perms == []


async def test_get_perms_view_all_engagements_adds_view_perms():
    """A group carrying VIEW_ALL_ENGAGEMENTS expands into the view-permission
    set even when the user has no engagement-role assignment."""
    db = FakeDb(
        [
            FakeScalarResult(None),  # no role assignment
            FakeScalarResult(many=[["view_all_engagements"]]),
        ]
    )
    perms = set(await get_user_engagement_permissions("u-1", "eng-1", db))
    assert Permission.ENGAGEMENT_VIEW.value in perms
    assert Permission.FINDING_VIEW.value in perms
    assert Permission.VAULT_VIEW.value in perms
    # Non-view perms are NOT granted by the override.
    assert Permission.FINDING_EDIT.value not in perms
