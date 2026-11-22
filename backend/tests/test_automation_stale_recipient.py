"""A rule naming a deleted user doesn't roll back the event's other
notifications: unknown / inactive recipients are skipped."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from models.notification import Notification
from utils.automation_engine import _execute_notify_users


async def test_stale_recipient_skipped(db_session, make_user):
    alive = await make_user(role="operator")
    gone = str(uuid.uuid4())
    await _execute_notify_users(db_session, {"user_ids": [gone, alive.id], "message": "hi"},
                                {"action": "manual"}, "rule")
    await db_session.flush()           # used to fail the FK for `gone`
    rows = (await db_session.execute(select(Notification.user_id).where(
        Notification.user_id.in_([gone, alive.id])))).scalars().all()
    assert rows == [alive.id]
