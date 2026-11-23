"""Undated engagements sort last in both directions; Postgres puts NULLs
first under DESC, so the default start_date-desc list opened on them."""

from __future__ import annotations

import uuid
from datetime import datetime

from models.engagement import Engagement


async def test_undated_engagements_sort_last(client, db_session, make_user, authenticate_as):
    admin = await make_user(role="admin")
    authenticate_as(admin)
    tag = uuid.uuid4().hex[:8]
    for name, start in (("dated-old", datetime(2025, 1, 1)), ("undated", None), ("dated-new", datetime(2026, 1, 1))):
        db_session.add(Engagement(id=str(uuid.uuid4()), name=f"{tag}-{name}", client_name="ACME",
                                  engagement_type="external_pentest", created_by=admin.id, start_date=start))
    await db_session.flush()
    for order, expected in (("desc", ["dated-new", "dated-old", "undated"]),
                            ("asc", ["dated-old", "dated-new", "undated"])):
        r = await client.get("/engagements", params={"q": tag, "sort_by": "start_date", "sort_order": order})
        assert r.status_code == 200, r.text
        assert [e["name"].split("-", 1)[1] for e in r.json()] == expected, order
