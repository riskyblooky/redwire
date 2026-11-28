"""Global search returns, per category, exactly what the caller could open
through that category's own GET: an outsider finds nothing of an
engagement; a member finds the categories their role can view; a view-all
user finds everything but the vault; a member with vault_view finds vault
items."""

from __future__ import annotations

import uuid

import pytest

from tests.test_authz_boundaries import _assign, _make_engagement, _make_engagement_role, _make_finding
from tests.test_view_all_engagements import _view_all_user


def _cats(r):
    assert r.status_code == 200, r.text
    return {c["category"]: {i["id"] for i in c["items"]} for c in r.json()["results"]}


@pytest.fixture
async def seeded(db_session):
    from models.asset import Asset
    from models.note import Note
    from models.testcase import TestCase
    from models.vault import VaultItem

    tag = "zq" + uuid.uuid4().hex[:10]
    eng = await _make_engagement(db_session, name=f"Op {tag}")
    f = await _make_finding(db_session, eng)
    f.title = f"{tag} finding"
    ids = {
        "engagements": eng.id,
        "findings": f.id,
        "assets": str(uuid.uuid4()),
        "testcases": str(uuid.uuid4()),
        "vault": str(uuid.uuid4()),
        "notes": str(uuid.uuid4()),
    }
    db_session.add_all([
        Asset(id=ids["assets"], engagement_id=eng.id, name=f"{tag}-host", identifier=f"{tag}.corp", asset_type="host"),
        TestCase(id=ids["testcases"], engagement_id=eng.id, title=f"{tag} case", category="Recon", description="d"),
        VaultItem(id=ids["vault"], engagement_id=eng.id, name=f"{tag} creds", item_type="CREDENTIAL"),
        Note(id=ids["notes"], engagement_id=eng.id, title=f"{tag} note", content="c"),
    ])
    await db_session.commit()
    return tag, eng, ids


async def _found(client, tag, ids):
    cats = _cats(await client.get("/search", params={"q": tag, "limit": 50}))
    return {c for c, wanted in ids.items() if wanted in cats.get(c, set())}


async def test_search_matches_what_each_caller_may_open(client, db_session, make_user, authenticate_as, seeded):
    tag, eng, ids = seeded
    every = set(ids)

    authenticate_as(await make_user(role="admin"))
    assert await _found(client, tag, ids) == every, "the fixture is searchable at all"

    authenticate_as(await make_user())
    assert await _found(client, tag, ids) == set(), "an outsider found engagement data"

    findings_only = await make_user()
    await _assign(db_session, findings_only, eng, await _make_engagement_role(db_session, ["engagement_view", "finding_view"]))
    vaulter = await make_user()
    await _assign(db_session, vaulter, eng, await _make_engagement_role(db_session, ["engagement_view", "vault_view"]))
    viewer = await _view_all_user(db_session, make_user)
    await db_session.commit()

    authenticate_as(findings_only)
    assert await _found(client, tag, ids) == {"engagements", "findings"}
    authenticate_as(vaulter)
    assert await _found(client, tag, ids) == {"engagements", "vault"}
    authenticate_as(viewer)
    assert await _found(client, tag, ids) == every - {"vault"}, "view-all: everything but the vault"
