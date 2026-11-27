"""/stats/time-on-task sessionises pings per (user, resource type): gaps up
to 10 minutes count as work, a longer gap starts a new session, and each
session adds a 60-second tail."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from tests.test_authz_boundaries import _assign, _make_engagement, _make_engagement_role


async def test_time_on_task_numbers(client, db_session, make_user, authenticate_as):
    from models.activity_ping import ActivityPing
    eng = await _make_engagement(db_session)
    other_eng = await _make_engagement(db_session)
    a = await make_user(role="operator")
    b = await make_user(role="operator")
    role = await _make_engagement_role(db_session, ["finding_view"])
    await _assign(db_session, a, eng, role)
    t0 = datetime.utcnow() - timedelta(days=1)

    def ping(user, rtype, minutes, e=eng):
        db_session.add(ActivityPing(id=str(uuid.uuid4()), user_id=user.id, engagement_id=e.id,
                                    resource_type=rtype, created_at=t0 + timedelta(minutes=minutes)))
    # a / finding: 0, 2, 5 (one session, 5 min) then 30, 31 (second session, 1 min)
    for m in (0, 2, 5, 30, 31):
        ping(a, "finding", m)
    # b / finding: 0, 10 (gap exactly 10 min stays in session) → 10 min, 1 session
    ping(b, "finding", 100)
    ping(b, "finding", 110)
    # a / note: a single ping → 1 session, tail only
    ping(a, "note", 50)
    # outside the window, and on another engagement: ignored
    db_session.add(ActivityPing(id=str(uuid.uuid4()), user_id=a.id, engagement_id=eng.id,
                                resource_type="finding", created_at=datetime.utcnow() - timedelta(days=40)))
    ping(a, "asset", 0, e=other_eng)
    await db_session.flush()

    authenticate_as(await make_user(role="admin"))
    r = await client.get("/stats/time-on-task", params={"engagement_id": eng.id, "days": 30})
    assert r.status_code == 200, r.text
    d = r.json()
    by = {x["resource_type"]: x for x in d["by_resource_type"]}
    assert list(by) == ["finding", "note"]
    # finding: a = 5 + 1 + 2 tails, b = 10 + 1 tail  → 19 min, 3 sessions
    assert by["finding"] == {"resource_type": "finding", "total_minutes": 19.0, "sessions": 3,
                             "contributors": 2, "pings": 7}
    assert by["note"] == {"resource_type": "note", "total_minutes": 1.0, "sessions": 1,
                          "contributors": 1, "pings": 1}
    assert d["total_minutes"] == 20.0 and d["days"] == 30
