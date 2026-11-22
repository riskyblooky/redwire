"""View-all holders' engagement-role ceiling is the canonical view-all set:
no vault_view (credentials need an engagement role), notes/cleanup included."""

from __future__ import annotations

from auth.permissions import engagement_permission_ceiling
from models.permission import VIEW_ALL_ENGAGEMENT_GRANTS
from tests.test_security_center import _grant


async def test_view_all_ceiling_matches_the_canonical_grants(db_session, make_user):
    mgr = await make_user(role="operator")
    await _grant(db_session, mgr, "view_all_engagements", "manage_engagement_roles")
    ceiling = await engagement_permission_ceiling(mgr, db_session)
    assert "vault_view" not in ceiling
    assert {"note_view", "cleanup_view"} <= ceiling
    assert ceiling == set(VIEW_ALL_ENGAGEMENT_GRANTS)
