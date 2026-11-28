"""GET /findings as a server-paged list: X-Total-Count, the filters the
findings tab offers, ranked search (whole matches above partial ones),
sorting with a stable tiebreaker, and /findings/facets."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from models.finding import FindingStatus, Severity
from tests.test_authz_boundaries import _assign, _make_engagement, _make_engagement_role, _make_finding


def _titles(r):
    assert r.status_code == 200, r.text
    return [f["title"] for f in r.json()]


@pytest.fixture
async def eng(db_session):
    from models.associations import FindingTag
    from models.finding import Tag
    e = await _make_engagement(db_session)
    now = datetime.utcnow()
    specs = [
        ("Domain", Severity.LOW, FindingStatus.OPEN, "AD", 0),
        ("Weak domain policy", Severity.HIGH, FindingStatus.OPEN, "AD", 1),
        ("Domains enumerated", Severity.MEDIUM, FindingStatus.CLOSED, "Recon", 2),
        ("Subdomain takeover", Severity.CRITICAL, FindingStatus.OPEN, "Web", 3),
        ("Unrelated", Severity.INFO, FindingStatus.OPEN, None, 4),
    ]
    rows = {}
    for title, sev, st, cat, age in specs:
        rows[title] = await _make_finding(db_session, e, title=title, severity=sev, status=st, category=cat,
                                          description="desc", created_at=now - timedelta(days=age),
                                          custom_fields={"rank": str(age)})
    tag = Tag(id=str(uuid.uuid4()), name=f"t-{uuid.uuid4().hex[:6]}")
    db_session.add(tag)
    await db_session.flush()
    db_session.add(FindingTag(finding_id=rows["Unrelated"].id, tag_id=tag.id))
    await db_session.commit()
    return e, rows, tag


async def test_ranked_search_puts_whole_matches_first(client, make_user, authenticate_as, eng):
    e, *_ = eng
    authenticate_as(await make_user(role="admin"))
    r = await client.get("/findings", params={"engagement_id": e.id, "q": "domain"})
    assert _titles(r) == ["Domain", "Weak domain policy", "Domains enumerated", "Subdomain takeover"]
    assert r.headers["X-Total-Count"] == "4"
    # The sort orders within a rank, not across it.
    r = await client.get("/findings", params={"engagement_id": e.id, "q": "domain", "sort_by": "severity", "sort_order": "asc"})
    assert _titles(r)[0] == "Domain"
    # LIKE / regex metacharacters are literal.
    for term in ("%", "_", "(", "domain.*"):
        assert _titles(await client.get("/findings", params={"engagement_id": e.id, "q": term})) == [], term


async def test_filters_and_total(client, make_user, authenticate_as, eng):
    e, rows, tag = eng
    authenticate_as(await make_user(role="admin"))
    base = {"engagement_id": e.id}
    r = await client.get("/findings", params={**base, "severity": ["HIGH", "CRITICAL"]})
    assert set(_titles(r)) == {"Weak domain policy", "Subdomain takeover"} and r.headers["X-Total-Count"] == "2"
    assert _titles(await client.get("/findings", params={**base, "severity": "LOW"})) == ["Domain"], "single value still works"
    assert _titles(await client.get("/findings", params={**base, "status": "CLOSED"})) == ["Domains enumerated"]
    assert set(_titles(await client.get("/findings", params={**base, "category": ["AD"]}))) == {"Domain", "Weak domain policy"}
    assert _titles(await client.get("/findings", params={**base, "tag": tag.id})) == ["Unrelated"]
    after = (datetime.utcnow() - timedelta(days=1, hours=12)).date().isoformat()
    assert len(_titles(await client.get("/findings", params={**base, "created_after": after}))) in (2, 3)


async def test_paging_is_stable_and_totals_ignore_paging(client, make_user, authenticate_as, eng):
    e, *_ = eng
    authenticate_as(await make_user(role="admin"))
    seen = []
    for skip in range(0, 5, 2):
        r = await client.get("/findings", params={"engagement_id": e.id, "sort_by": "status", "skip": skip, "limit": 2})
        assert r.headers["X-Total-Count"] == "5"
        seen += _titles(r)
    assert len(seen) == 5 and len(set(seen)) == 5, "a row repeated or went missing across pages"
    assert _titles(await client.get("/findings", params={"engagement_id": e.id, "offset": 4, "limit": 2})) == \
        _titles(await client.get("/findings", params={"engagement_id": e.id, "skip": 4, "limit": 2})), "offset alias"


async def test_sorting(client, make_user, authenticate_as, eng):
    e, *_ = eng
    authenticate_as(await make_user(role="admin"))
    base = {"engagement_id": e.id}
    sev = [f["severity"] for f in (await client.get("/findings", params={**base, "sort_by": "severity", "sort_order": "asc"})).json()]
    assert sev == ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
    assert _titles(await client.get("/findings", params=base))[0] == "Domain", "default: newest first"
    assert _titles(await client.get("/findings", params={**base, "sort_by": "cf:rank", "sort_order": "desc"}))[0] == "Unrelated"
    r = await client.get("/findings", params={**base, "sort_by": "description; drop table"})
    assert r.status_code == 422 and "sort_by must be one of" in r.text
    assert (await client.get("/findings", params={**base, "skip": -1})).status_code == 422


async def test_facets_and_scope(client, db_session, make_user, authenticate_as, eng):
    e, *_ = eng
    authenticate_as(await make_user(role="admin"))
    facets = (await client.get("/findings/facets", params={"engagement_id": e.id})).json()
    assert facets == {"total": 5, "categories": ["AD", "Recon", "Web"]}

    viewer = await make_user()
    await _assign(db_session, viewer, e, await _make_engagement_role(db_session, ["engagement_view"]))
    await db_session.commit()
    authenticate_as(viewer)  # a member whose role can't view findings
    r = await client.get("/findings", params={"engagement_id": e.id, "q": "domain"})
    assert _titles(r) == [] and r.headers["X-Total-Count"] == "0"
    assert (await client.get("/findings/facets", params={"engagement_id": e.id})).json() == {"total": 0, "categories": []}
