"""Every list endpoint built on utils.listing.list_params keeps the same
contract: skip/limit (and the offset alias) are accepted, bad paging and
an unknown sort_by are a 422, and the total is in X-Total-Count.

Endpoints are found from the app's routes, so a new paged list is
covered the day it uses list_params."""

from __future__ import annotations

import pytest
from fastapi.routing import APIRoute

from main import app


def _uses_list_params(dependant) -> bool:
    return any(getattr(d.call, "is_list_params", False) or _uses_list_params(d) for d in dependant.dependencies)


def _required_query(dependant) -> bool:
    if any(p.field_info.is_required() for p in dependant.query_params):
        return True
    return any(_required_query(d) for d in dependant.dependencies)


PAGED = sorted(
    r.path for r in app.routes
    if isinstance(r, APIRoute) and "GET" in r.methods and "{" not in r.path
    and _uses_list_params(r.dependant) and not _required_query(r.dependant)
)


def test_the_core_lists_are_discovered():
    assert {"/findings", "/testcases", "/assets"} <= set(PAGED), PAGED


@pytest.mark.parametrize("path", PAGED)
async def test_list_contract(path, client, make_user, authenticate_as):
    authenticate_as(await make_user(role="admin"))
    r = await client.get(path, params={"skip": 0, "limit": 1})
    assert r.status_code == 200, r.text
    total = r.headers.get("X-Total-Count")
    assert total is not None and total.isdigit(), "X-Total-Count missing"
    body = r.json()
    rows = body["items"] if isinstance(body, dict) else body
    assert len(rows) <= 1
    assert (await client.get(path, params={"offset": 0, "limit": 1})).status_code == 200
    for bad in ({"skip": -1}, {"limit": 0}, {"sort_by": "no_such_column"}, {"sort_order": "sideways"}):
        assert (await client.get(path, params=bad)).status_code == 422, bad
