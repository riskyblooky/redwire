"""Every DELETE route, discovered from the app: unauthenticated callers get
401, and deleting something that doesn't exist never 5xxs and never reports
success for an object it couldn't have deleted. A new DELETE endpoint is
covered without editing this test."""

from __future__ import annotations

import uuid

import pytest
from fastapi.routing import APIRoute

# Deletes that are idempotent on purpose (removing "mine" / a link / a
# per-user setting that may not exist is a no-op, not an error).
IDEMPOTENT = {
    "/findings/{finding_id}/reviews/mine",
    "/engagements/{engagement_id}/attack-graph/layout",
}


def _delete_routes():
    import main
    out = []
    for r in main.app.routes:
        if isinstance(r, APIRoute) and "DELETE" in r.methods:
            out.append(r)
    return sorted(out, key=lambda r: r.path)


def _url(route):
    url = route.path
    for p in route.dependant.path_params:
        # Typed path params (e.g. an entity/category name) get a plausible
        # but nonexistent value; ids get a fresh uuid.
        url = url.replace("{" + p.name + "}", str(uuid.uuid4()) if p.name.endswith("id") else "nosuch")
    return url


def test_route_discovery_sees_the_deletes():
    assert len(_delete_routes()) > 60


async def test_every_delete_requires_auth(client):
    client.headers.pop("Authorization", None)
    bad = []
    for r in _delete_routes():
        resp = await client.delete(_url(r))
        if resp.status_code != 401:
            bad.append(f"{r.path}: {resp.status_code}")
    assert not bad, "DELETE reachable without a session:\n" + "\n".join(bad)


async def test_deleting_nothing_never_errors_or_succeeds(client, make_user, authenticate_as):
    authenticate_as(await make_user(role="admin"))
    errors, phantom = [], []
    for r in _delete_routes():
        resp = await client.delete(_url(r))
        if resp.status_code >= 500:
            errors.append(f"{r.path}: {resp.status_code} {resp.text[:120]}")
        elif resp.status_code < 300 and r.path not in IDEMPOTENT:
            phantom.append(f"{r.path}: {resp.status_code}")
    assert not errors, "5xx deleting a nonexistent object:\n" + "\n".join(errors)
    assert not phantom, "reported success deleting a nonexistent object:\n" + "\n".join(phantom)
