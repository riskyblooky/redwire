"""Review sweep: calendar findings."""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import update

from tests.test_authz_boundaries import _assign, _make_engagement, _make_engagement_role

_RANGE = {"start": "2026-03-01T00:00:00", "end": "2026-03-31T00:00:00", "count": 20}


@pytest.fixture
async def only_these_users(db_session):
    """Deactivate everyone else (rolled back with the test) so the
    suggestion list is just the users a test makes."""
    from models.user import User

    async def _only(*users):
        await db_session.execute(update(User).where(User.id.notin_([u.id for u in users]))
                                 .values(is_active=False))
    return _only


async def test_auto_assign_names_only_engagements_the_caller_can_see(client, db_session, make_user,
                                                                     authenticate_as, only_these_users,
                                                                     monkeypatch):
    import routers.calendar as cal
    from models.permission import Permission

    async def _perm(user, perm, db):  # calendar view, but not view-all
        return perm == Permission.CALENDAR_VIEW
    monkeypatch.setattr(cal, "has_global_permission", _perm)
    caller, busy = await make_user(), await make_user()
    await only_these_users(caller, busy)
    secret = await _make_engagement(db_session, name=f"Secret {uuid.uuid4().hex[:6]}",
                                    start_date=datetime(2026, 2, 1), end_date=datetime(2026, 4, 1))
    await _assign(db_session, busy, secret, await _make_engagement_role(db_session, []))
    authenticate_as(caller)

    r = await client.get("/calendar/auto-assign", params=_RANGE)

    assert r.status_code == 200, r.text
    assert secret.name not in r.text and secret.id not in r.text


async def test_auto_assign_does_not_count_completed_engagements(client, db_session, make_user,
                                                                authenticate_as, only_these_users):
    from models.engagement import EngagementStatus
    admin, lead = await make_user(role="admin"), await make_user()
    await only_these_users(admin, lead)
    done = await _make_engagement(db_session, status=EngagementStatus.COMPLETED,
                                  start_date=datetime(2026, 2, 1), end_date=datetime(2026, 4, 1))
    await _assign(db_session, lead, done, await _make_engagement_role(db_session, []))
    authenticate_as(admin)

    r = await client.get("/calendar/auto-assign", params=_RANGE)

    assert r.status_code == 200, r.text
    [row] = [s for s in r.json() if s["user"]["id"] == lead.id]
    assert row["overlapping_count"] == 0
