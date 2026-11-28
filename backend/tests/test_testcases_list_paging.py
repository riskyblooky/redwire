"""GET /testcases as a server-paged list: filters, ranked search, sorting,
the tree mode (pages of top-level test cases carrying their descendants),
and /testcases/facets."""

from __future__ import annotations

import uuid

import pytest

from models.testcase import TestCase
from tests.test_authz_boundaries import _make_engagement


def _titles(r):
    assert r.status_code == 200, r.text
    return [t["title"] for t in r.json()]


async def _tc(db, eng, title, *, parent=None, category="Recon", executed=False, ok=None, description="d"):
    tc = TestCase(id=str(uuid.uuid4()), engagement_id=eng.id, title=title, category=category,
                  description=description, parent_id=parent.id if parent else None,
                  is_executed=executed, is_successful=ok)
    db.add(tc)
    await db.flush()
    return tc


@pytest.fixture
async def eng(db_session):
    e = await _make_engagement(db_session)
    a = await _tc(db_session, e, "A root", category="Web")
    a1 = await _tc(db_session, e, "A child", parent=a, executed=True, ok=True)
    await _tc(db_session, e, "A grandchild", parent=a1, executed=True, ok=False)
    await _tc(db_session, e, "B root", description="kerberos roasting")
    await _tc(db_session, e, "C root", category="Web", executed=True)
    await db_session.commit()
    return e


async def test_tree_pages_roots_with_descendants(client, make_user, authenticate_as, eng):
    authenticate_as(await make_user(role="admin"))
    base = {"engagement_id": eng.id, "tree": "true", "sort_by": "title", "sort_order": "asc"}
    r = await client.get("/testcases", params={**base, "limit": 1})
    assert r.headers["X-Total-Count"] == "3", "the total counts roots"
    assert _titles(r) == ["A root", "A child", "A grandchild"]
    r = await client.get("/testcases", params={**base, "skip": 1, "limit": 2})
    assert _titles(r) == ["B root", "C root"]


async def test_filters_search_and_sort(client, make_user, authenticate_as, eng):
    authenticate_as(await make_user(role="admin"))
    base = {"engagement_id": eng.id}
    r = await client.get("/testcases", params=base)
    assert r.headers["X-Total-Count"] == "5"
    assert set(_titles(await client.get("/testcases", params={**base, "category": "Web"}))) == {"A root", "C root"}
    assert set(_titles(await client.get("/testcases", params={**base, "executed": "false"}))) == {"A root", "B root"}
    assert _titles(await client.get("/testcases", params={**base, "result": "failed"})) == ["A grandchild"]
    assert _titles(await client.get("/testcases", params={**base, "result": "passed"})) == ["A child"]
    # Title hits rank above a description hit; "root" is a whole word in all three.
    assert _titles(await client.get("/testcases", params={**base, "q": "kerberos"})) == ["B root"]
    assert _titles(await client.get("/testcases", params={**base, "q": "root", "sort_by": "title"})) == \
        ["A root", "B root", "C root"]
    # Not run < failed < passed.
    res = [(t["is_executed"], t["is_successful"]) for t in
           (await client.get("/testcases", params={**base, "sort_by": "result"})).json()]
    assert res[-1] == (True, True) and res[-2] == (True, None) and res[-3] == (True, False)
    assert (await client.get("/testcases", params={**base, "sort_by": "steps"})).status_code == 422


async def test_facets(client, make_user, authenticate_as, eng):
    authenticate_as(await make_user(role="admin"))
    assert (await client.get("/testcases/facets", params={"engagement_id": eng.id})).json() == \
        {"total": 5, "categories": ["Recon", "Web"]}
