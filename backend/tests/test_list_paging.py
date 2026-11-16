"""List endpoints page stably: with many rows sharing the sort key, walking
skip/limit returns every row exactly once (the frontend's fetchAllPages
relies on it to load complete lists instead of the first page)."""

from __future__ import annotations

import uuid
from datetime import datetime

from models.finding import Finding, Severity


async def _walk(client, url, params, page=2, unwrap=lambda d: d):
    seen = []
    for skip in range(0, 1000, page):
        r = await client.get(url, params={**params, "skip": skip, "limit": page})
        assert r.status_code == 200, r.text
        rows = unwrap(r.json())
        seen += [x["id"] for x in rows]
        if len(rows) < page:
            return seen
    raise AssertionError("never reached the last page")


async def test_engagements_findings_assets_page_without_gaps(client, db_session, make_user, authenticate_as):
    from models.asset import Asset
    from tests.test_authz_boundaries import _make_engagement
    same = datetime(2026, 3, 1)
    engs = [await _make_engagement(db_session, name=f"tie {uuid.uuid4().hex[:6]}", start_date=same) for _ in range(7)]
    eng = engs[0]
    for i in range(7):
        db_session.add(Finding(id=str(uuid.uuid4()), engagement_id=eng.id, title=f"f{i}", description="d",
                               severity=Severity.LOW, created_at=same, updated_at=same))
        db_session.add(Asset(id=str(uuid.uuid4()), engagement_id=eng.id, name="same", asset_type="Server",
                             identifier=f"10.9.9.{i}"))
    await db_session.flush()
    eng_ids = {e.id for e in engs}
    eng_id = eng.id
    db_session.expunge_all()
    authenticate_as(await make_user(role="admin"))

    got = await _walk(client, "/engagements", {"sort_by": "start_date"})
    tied = [i for i in got if i in eng_ids]
    assert sorted(tied) == sorted(eng_ids) and len(got) == len(set(got))

    got = await _walk(client, "/findings", {"engagement_id": eng_id})
    assert len(got) == 7 == len(set(got))

    got = await _walk(client, "/assets", {"engagement_id": eng_id, "sort_by": "name"}, unwrap=lambda d: d["items"])
    assert len(got) == 7 == len(set(got))


async def test_users_page_without_gaps(client, db_session, make_user, authenticate_as):
    users = [await make_user() for _ in range(5)]
    authenticate_as(users[0])
    got = await _walk(client, "/users", {})
    assert {u.id for u in users} <= set(got) and len(got) == len(set(got))


async def test_engagements_with_proposed_lists(client, db_session, make_user, authenticate_as):
    """include_proposed=true always 500'd: a function-local import of
    has_global_permission further down made the name local to the whole
    function (UnboundLocalError). The Planning chart uses this call."""
    from models.engagement import EngagementStatus
    from tests.test_authz_boundaries import _make_engagement
    eng = await _make_engagement(db_session, status=EngagementStatus.PROPOSED)
    await db_session.flush()
    eng_id = eng.id
    db_session.expunge_all()
    authenticate_as(await make_user(role="admin"))
    r = await client.get("/engagements", params={"include_proposed": "true", "limit": 500})
    assert r.status_code == 200, r.text
    assert eng_id in {e["id"] for e in r.json()}
