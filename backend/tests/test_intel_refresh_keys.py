"""Intel refresh: a linkless RSS entry gets a stable key (guid, else a
hash) so it isn't re-inserted every cycle; a top-level-list JSON feed
parses; the item list counts links without a query per item."""

from __future__ import annotations

import uuid

import httpx
from sqlalchemy import func, select

from models.intel_feed import IntelFeed
from models.intel_item import IntelItem
from utils.intel_refresh import parse_entries, store_entries

RSS = """<?xml version="1.0"?><rss><channel>
<item><title>No link, has guid</title><guid isPermaLink="false">abc-123</guid></item>
<item><title>No link, no guid</title><pubDate>Mon, 02 Nov 2026 10:00:00 GMT</pubDate></item>
</channel></rss>"""


def _resp(body, ctype="application/rss+xml"):
    return httpx.Response(200, content=body.encode() if isinstance(body, str) else body,
                          headers={"content-type": ctype}, request=httpx.Request("GET", "https://x.invalid"))


async def test_linkless_entries_are_stored_once(db_session):
    feed = IntelFeed(id=str(uuid.uuid4()), name="f", url="https://x.invalid/rss", feed_type="RSS")
    db_session.add(feed)
    await db_session.flush()
    entries = parse_entries("RSS", _resp(RSS))
    assert entries[0]["source_url"] == "abc-123"
    assert entries[1]["source_url"].startswith("urn:redwire:intel:")
    assert entries[1]["source_url"] == parse_entries("RSS", _resp(RSS))[1]["source_url"]   # stable
    assert await store_entries(db_session, feed, entries) == 2
    assert await store_entries(db_session, feed, parse_entries("RSS", _resp(RSS))) == 0   # next cycle
    n = (await db_session.execute(select(func.count()).select_from(IntelItem).where(IntelItem.feed_id == feed.id))).scalar()
    assert n == 2


def test_list_shaped_json_feed_parses():
    body = '[{"cveID": "CVE-2026-0001", "vulnerabilityName": "A"}, {"vulnerabilityName": "no id"}]'
    entries = parse_entries("JSON", _resp(body, "application/json"))
    assert [e["cve_id"] for e in entries] == ["CVE-2026-0001", None]
    assert entries[0]["source_url"].endswith("CVE-2026-0001")
    assert entries[1]["source_url"].startswith("urn:redwire:intel:")


async def test_item_list_link_counts(client, db_session, make_user, authenticate_as):
    from models.associations import IntelItemFinding
    from models.finding import Finding, Severity
    from tests.test_authz_boundaries import _make_engagement
    eng = await _make_engagement(db_session)
    tag = uuid.uuid4().hex
    a = IntelItem(id=str(uuid.uuid4()), title=f"A {tag}", item_type="OTHER")
    b = IntelItem(id=str(uuid.uuid4()), title=f"B {tag}", item_type="OTHER")
    f1 = Finding(id=str(uuid.uuid4()), engagement_id=eng.id, title="F1", description="d", severity=Severity.LOW)
    f2 = Finding(id=str(uuid.uuid4()), engagement_id=eng.id, title="F2", description="d", severity=Severity.LOW)
    db_session.add_all([a, b, f1, f2])
    await db_session.flush()
    db_session.add_all([IntelItemFinding(intel_item_id=a.id, finding_id=f1.id),
                        IntelItemFinding(intel_item_id=a.id, finding_id=f2.id)])
    await db_session.flush()
    authenticate_as(await make_user(role="admin"))
    body = (await client.get("/intel/items", params={"search": tag})).json()
    assert {i["title"][0]: i["linked_count"] for i in body["items"]} == {"A": 2, "B": 0}
