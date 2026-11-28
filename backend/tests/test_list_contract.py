"""Every list endpoint built on utils.listing.list_params keeps the same
contract: skip/limit (and the offset alias) are accepted, bad paging and
an unknown sort_by are a 422, and the total is in X-Total-Count.

Endpoints are found from the app's routes, so a new paged list is
covered the day it uses list_params."""

from __future__ import annotations

import uuid

import pytest
from fastapi.routing import APIRoute

from main import app


def _uses_list_params(dependant) -> bool:
    return any(getattr(d.call, "is_list_params", False) or _uses_list_params(d) for d in dependant.dependencies)


# Required parameters the test knows how to fill; a route needing any
# other is left out.
FILLABLE = {"engagement_id", "thread_id"}


def _required(dependant) -> set[str]:
    names = {p.name for p in dependant.query_params + dependant.path_params if p.field_info.is_required()}
    for d in dependant.dependencies:
        names |= _required(d)
    return names


PAGED = sorted(
    r.path for r in app.routes
    if isinstance(r, APIRoute) and "GET" in r.methods
    and _uses_list_params(r.dependant) and _required(r.dependant) <= FILLABLE
)


def test_the_core_lists_are_discovered():
    assert {"/findings", "/testcases", "/assets", "/vault", "/cleanup-artifacts", "/engagements/{engagement_id}/notes",
            "/engagements/{engagement_id}/evidence", "/discussions/threads", "/discussions/comments",
            "/spray/campaigns", "/imports/scans"} <= set(PAGED), PAGED


@pytest.fixture
async def ids(db_session):
    from models.discussion import Thread
    from tests.test_authz_boundaries import _make_engagement
    eng = await _make_engagement(db_session)
    thread = Thread(id=str(uuid.uuid4()), engagement_id=eng.id, resource_type="engagement",
                    resource_id=eng.id, title="t")
    db_session.add(thread)
    await db_session.commit()
    return {"engagement_id": eng.id, "thread_id": thread.id}


def _target(path, ids, route_required):
    url = path
    params = {}
    for name in route_required:
        if "{" + name + "}" in url:
            url = url.replace("{" + name + "}", ids[name])
        else:
            params[name] = ids[name]
    return url, params


@pytest.mark.parametrize("path", PAGED)
async def test_list_contract(path, client, make_user, authenticate_as, ids):
    route = next(r for r in app.routes if isinstance(r, APIRoute) and r.path == path and "GET" in r.methods)
    url, base = _target(path, ids, _required(route.dependant))
    authenticate_as(await make_user(role="admin"))
    r = await client.get(url, params={**base, "skip": 0, "limit": 1})
    assert r.status_code == 200, r.text
    total = r.headers.get("X-Total-Count")
    assert total is not None and total.isdigit(), "X-Total-Count missing"
    body = r.json()
    rows = body["items"] if isinstance(body, dict) else body
    assert len(rows) <= 1
    assert (await client.get(url, params={**base, "offset": 0, "limit": 1})).status_code == 200
    for bad in ({"skip": -1}, {"limit": 0}, {"sort_by": "no_such_column"}, {"sort_order": "sideways"}):
        assert (await client.get(url, params={**base, **bad})).status_code == 422, bad
