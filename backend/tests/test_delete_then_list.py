"""Delete-then-list, per resource: once DELETE succeeds the item is gone
from its list endpoint and its detail endpoint 404s. Everything goes
through the API, as an admin, in a fresh engagement."""

from __future__ import annotations

import uuid

import pytest


def _name(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _ids(body) -> set[str]:
    """Ids in a list response, whether it's a bare list or a page object."""
    if isinstance(body, dict):
        for key in ("items", "results", "data", "engagements"):
            if isinstance(body.get(key), list):
                body = body[key]
                break
    assert isinstance(body, list), f"unrecognised list shape: {str(body)[:200]}"
    return {row["id"] for row in body if isinstance(row, dict) and "id" in row}


# (name, create path, create body, list path, detail/delete path). "{eid}" is
# the engagement, "{id}" the created item.
CASES = [
    ("finding", "/findings", lambda eid: {"engagement_id": eid, "title": _name("f"), "severity": "LOW",
                                          "description": "d"},
     "/findings?engagement_id={eid}", "/findings/{id}"),
    ("asset", "/assets", lambda eid: {"engagement_id": eid, "name": _name("a"), "asset_type": "Other",
                                      "identifier": _name("10.0.0")},
     "/assets?engagement_id={eid}", "/assets/{id}"),
    ("testcase", "/testcases", lambda eid: {"engagement_id": eid, "title": _name("t"), "category": "Recon",
                                            "description": "d"},
     "/testcases?engagement_id={eid}", "/testcases/{id}"),
    ("note", "/engagements/{eid}/notes", lambda eid: {"title": _name("n"), "content": "x"},
     "/engagements/{eid}/notes", "/notes/{id}"),
    ("vault", "/vault", lambda eid: {"engagement_id": eid, "name": _name("v"), "item_type": "CREDENTIAL",
                                     "username": "u", "password": "p"},
     "/vault?engagement_id={eid}", "/vault/{id}"),
    ("cleanup", "/cleanup-artifacts", lambda eid: {"engagement_id": eid, "title": _name("c"),
                                                   "artifact_type": "FILE", "status": "PENDING"},
     "/cleanup-artifacts?engagement_id={eid}", "/cleanup-artifacts/{id}"),
    ("thread", "/discussions/threads", lambda eid: {"engagement_id": eid, "resource_type": "engagement",
                                                    "title": _name("th"), "content": "first"},
     "/discussions/threads?engagement_id={eid}", "/discussions/threads/{id}"),
    ("finding-template", "/templates", lambda eid: {"title": _name("ft"), "description": "d",
                                                    "severity": "LOW", "category": "Web"},
     "/templates?limit=500", "/templates/{id}"),
    ("testcase-template", "/testcase-templates", lambda eid: {"title": _name("tt"), "category": "Recon",
                                                              "description": "d"},
     "/testcase-templates?limit=500", "/testcase-templates/{id}"),
    ("runbook", "/runbooks", lambda eid: {"name": _name("rb"), "items": []},
     "/runbooks?limit=500", "/runbooks/{id}"),
    ("client", "/clients", lambda eid: {"name": _name("cl")},
     "/clients", "/clients/{id}"),
    ("tag", "/tags", lambda eid: {"name": _name("tag"), "color": "#ff0000", "entity_type": "finding"},
     "/tags", "/tags/{id}"),
    ("engagement", "/engagements", lambda eid: {"name": _name("e"), "client_name": "Acme Corp",
                                           "engagement_type": "Red Team", "start_date": "2026-01-01T00:00:00"},
     "/engagements?limit=500", "/engagements/{id}"),
]


@pytest.mark.parametrize("name, create, body, listing, item", CASES, ids=[c[0] for c in CASES])
async def test_deleted_item_leaves_the_list(name, create, body, listing, item,
                                            client, db_session, make_user, authenticate_as, monkeypatch):
    from tests.test_authz_boundaries import _make_engagement

    admin = await make_user(role="admin")
    eng = await _make_engagement(db_session, created_by=admin.id)
    authenticate_as(admin)
    fmt = lambda p, **kw: p.format(eid=eng.id, **kw)

    r = await client.post(fmt(create), json=body(eng.id))
    assert r.status_code in (200, 201), f"create {name}: {r.status_code} {r.text}"
    new_id = r.json()["id"]

    listed = await client.get(fmt(listing))
    assert listed.status_code == 200, listed.text
    assert new_id in _ids(listed.json()), f"{name} missing from its list before delete"

    d = await client.delete(fmt(item, id=new_id))
    assert d.status_code in (200, 204), f"delete {name}: {d.status_code} {d.text}"

    listed = await client.get(fmt(listing))
    assert listed.status_code == 200, listed.text
    assert new_id not in _ids(listed.json()), f"deleted {name} still listed"
    if name != "tag":  # no detail endpoint
        assert (await client.get(fmt(item, id=new_id))).status_code == 404
