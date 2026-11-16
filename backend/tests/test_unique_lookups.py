"""Rows the code treats as "the one" are backed by unique indexes, and the
writers keep within them (recurring cause: check-then-insert without a
constraint, then scalar_one_or_none() 500s once a duplicate exists)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError


async def _feed(db):
    from models.intel_feed import IntelFeed
    feed = IntelFeed(id=str(uuid.uuid4()), name="feed", url="https://x.invalid/rss", feed_type="RSS")
    db.add(feed)
    await db.flush()
    return feed


async def test_intel_store_skips_items_already_stored(db_session):
    from models.intel_item import IntelItem
    from utils.intel_refresh import store_entries
    feed = await _feed(db_session)
    entries = [{"title": "a", "source_url": "https://x.invalid/1", "cve_id": "CVE-" + "9" * 80},
               {"title": "b", "source_url": "https://x.invalid/2"}]
    assert await store_entries(db_session, feed, entries) == 2  # over-long cve_id is clipped, not fatal
    # Second pass (or a concurrent refresh on another worker): nothing new.
    assert await store_entries(db_session, feed, entries + [{"title": "c", "source_url": "https://x.invalid/3"}]) == 1
    urls = (await db_session.execute(select(IntelItem.source_url).where(IntelItem.feed_id == feed.id))).scalars().all()
    assert sorted(urls) == ["https://x.invalid/1", "https://x.invalid/2", "https://x.invalid/3"]


async def test_engagement_names_unique_ignoring_case_and_spaces(client, db_session, make_user, authenticate_as):
    from models.engagement import Engagement
    from tests.test_authz_boundaries import _make_engagement
    await _make_engagement(db_session, name="Op Nightfall")
    await db_session.flush()
    db_session.expunge_all()
    authenticate_as(await make_user(role="admin"))
    body = {"name": "  op NIGHTFALL ", "client_name": "c", "engagement_type": "Red Team",
            "start_date": datetime.utcnow().isoformat()}
    assert (await client.post("/engagements", json=body)).status_code == 409
    body["name"] = "  Op Dawn  "
    r = await client.post("/engagements", json=body)
    assert r.status_code in (200, 201), r.text
    assert (await db_session.execute(select(Engagement.name).where(Engagement.id == r.json()["id"]))).scalar_one() == "Op Dawn"


async def test_engagement_name_index_backstops_the_check(db_session):
    from tests.test_authz_boundaries import _make_engagement
    await _make_engagement(db_session, name="Same")
    await db_session.flush()
    try:
        async with db_session.begin_nested():
            await _make_engagement(db_session, name=" same ")
            await db_session.flush()
        raise AssertionError("duplicate name inserted")
    except IntegrityError as exc:
        assert "uq_engagements_name_ci" in str(exc.orig)


async def test_integrity_handler_maps_known_constraints_to_409():
    import pytest
    from main import _integrity_conflict
    exc = IntegrityError("INSERT", {}, Exception('duplicate key value violates unique constraint "uq_engagements_name_ci"'))
    r = await _integrity_conflict(None, exc)
    assert r.status_code == 409
    other = IntegrityError("INSERT", {}, Exception('violates foreign key constraint "fk_x"'))
    with pytest.raises(IntegrityError):
        await _integrity_conflict(None, other)


async def test_reimporting_an_archive_numbers_the_name(client, db_session, make_user, authenticate_as):
    from models.engagement import Engagement
    from tests.test_engagement_transfer_extras import _export, _import
    from tests.test_engagement_transfer_roundtrip import _seed
    admin = await make_user(role="admin")
    eng = await _seed(db_session, (await make_user(), await make_user()))
    eng_id, name = eng.id, eng.name
    db_session.expunge_all()
    authenticate_as(admin)
    blob = await _export(client, eng_id)
    ids = [await _import(client, blob), await _import(client, blob)]
    names = [(await db_session.execute(select(Engagement.name).where(Engagement.id == i))).scalar_one() for i in ids]
    assert names == [f"{name} (imported)", f"{name} (imported) (2)"]


async def test_switching_default_theme_keeps_one(client, db_session, make_user, authenticate_as):
    from models.report_theme import ReportTheme
    authenticate_as(await make_user(role="admin"))
    a = (await client.post("/report-themes", json={"name": "A", "is_default": True})).json()["id"]
    b = (await client.post("/report-themes", json={"name": "B"})).json()["id"]
    # Update path: unsetting A and setting B are both UPDATEs; the unset
    # has to reach the DB first or the one-default index rejects B.
    r = await client.put(f"/report-themes/{b}", json={"is_default": True})
    assert r.status_code == 200, r.text
    defaults = (await db_session.execute(select(ReportTheme.id).where(ReportTheme.is_default == True))).scalars().all()  # noqa: E712
    assert defaults == [b] and a != b


async def test_one_default_layout_per_engagement(client, db_session, make_user, authenticate_as):
    from models.report_layout import ReportLayout
    from tests.test_authz_boundaries import _make_engagement
    eng = await _make_engagement(db_session)
    other = await _make_engagement(db_session)
    await db_session.flush()
    eng_id, other_id = eng.id, other.id
    db_session.expunge_all()
    authenticate_as(await make_user(role="admin"))
    base = f"/engagements/{eng_id}/report-layouts"
    first = (await client.post(base, json={"name": "one", "is_default": True})).json()["id"]
    assert (await client.post(f"/engagements/{other_id}/report-layouts", json={"name": "x", "is_default": True})).status_code == 201
    second = (await client.post(base, json={"name": "two", "is_default": True})).json()["id"]
    assert (await client.put(f"{base}/{first}", json={"is_default": True})).status_code == 200
    rows = dict((await db_session.execute(
        select(ReportLayout.id, ReportLayout.is_default).where(ReportLayout.engagement_id == eng_id))).all())
    assert rows == {first: True, second: False}
