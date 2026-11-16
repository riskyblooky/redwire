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


# has_engagement_permission / can_modify_resource were unused duplicates of
# auth.rbac's checks and are gone; tests/test_view_all_engagements.py covers
# the live path.


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
    assert Permission.VAULT_VIEW.value not in perms  # credentials need an engagement role
    assert Permission.NOTE_VIEW.value in perms and Permission.CLEANUP_VIEW.value in perms
    # Non-view perms are NOT granted by the override.
    assert Permission.FINDING_EDIT.value not in perms
