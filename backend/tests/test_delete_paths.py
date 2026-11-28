"""Delete paths for the engagement-scoped resources and every unlink route
between them. For each one, an outsider (no assignment) and a member whose
role only views are refused and nothing changes; an admin's delete removes
exactly the target: the row, or for an unlink the association row while both
entities stay. Entity deletes leave an audit entry."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from tests.test_authz_boundaries import _assign, _make_engagement, _make_engagement_role, _make_finding


def _id():
    return str(uuid.uuid4())


@pytest.fixture
async def world(db_session, make_user):
    from auth.permissions import _is_read_permission
    from models.asset import Asset
    from models.cleanup_artifact import CleanupArtifact
    from models.note import Note
    from models.permission import ENGAGEMENT_PERMISSIONS
    from models.testcase import TestCase
    from models.vault import VaultItem

    eng = await _make_engagement(db_session)
    f = await _make_finding(db_session, eng)
    objs = {
        "f": f,
        "a": Asset(id=_id(), engagement_id=eng.id, name="dc01", identifier=f"10.0.{uuid.uuid4().int % 250}.1", asset_type="host"),
        "t": TestCase(id=_id(), engagement_id=eng.id, title="tc", category="Recon", description="d"),
        "v": VaultItem(id=_id(), engagement_id=eng.id, name="creds", item_type="CREDENTIAL"),
        "c": CleanupArtifact(id=_id(), engagement_id=eng.id, title="implant", artifact_type="FILE"),
        "n": Note(id=_id(), engagement_id=eng.id, title="n", content="c"),
    }
    db_session.add_all([o for k, o in objs.items() if k != "f"])
    viewer_role = await _make_engagement_role(db_session, sorted(p.value for p in ENGAGEMENT_PERMISSIONS if _is_read_permission(p)))
    viewer, outsider, admin = await make_user(), await make_user(), await make_user(role="admin")
    await _assign(db_session, viewer, eng, viewer_role)
    await db_session.commit()
    return SimpleWorld(eng=eng, objs=objs, viewer=viewer, outsider=outsider, admin=admin)


class SimpleWorld:
    def __init__(self, **kw):
        self.__dict__.update(kw)

    def id(self, kind):
        return self.objs[kind].id


def _model(kind):
    from models.asset import Asset
    from models.cleanup_artifact import CleanupArtifact
    from models.finding import Finding
    from models.note import Note
    from models.testcase import TestCase
    from models.vault import VaultItem
    return {"f": Finding, "a": Asset, "t": TestCase, "v": VaultItem, "c": CleanupArtifact, "n": Note}[kind]


async def _exists(db, model, **where):
    db.expunge_all()
    return (await db.execute(select(model).filter_by(**where))).first() is not None


async def _refused(client, authenticate_as, w, url):
    for who in (w.outsider, w.viewer):
        authenticate_as(who)
        r = await client.delete(url)
        assert r.status_code in (403, 404), (who is w.viewer and "viewer" or "outsider", url, r.status_code, r.text)


ENTITY_DELETES = [
    ("f", "/findings/{f}"), ("a", "/assets/{a}"), ("t", "/testcases/{t}"),
    ("v", "/vault/{v}"), ("c", "/cleanup-artifacts/{c}"), ("n", "/notes/{n}"),
]


@pytest.mark.parametrize("kind,path", ENTITY_DELETES, ids=[p for _, p in ENTITY_DELETES])
async def test_entity_delete(client, db_session, authenticate_as, world, kind, path):
    from models.discussion import ActivityLog
    w, model = world, _model(kind)
    url = path.format(**{k: o.id for k, o in w.objs.items()})
    await _refused(client, authenticate_as, w, url)
    assert await _exists(db_session, model, id=w.id(kind)), "a refused delete removed the row"

    authenticate_as(w.admin)
    r = await client.delete(url)
    assert r.status_code in (200, 204), (url, r.status_code, r.text)
    assert not await _exists(db_session, model, id=w.id(kind))
    others = [k for k in w.objs if k != kind]
    for k in others:
        assert await _exists(db_session, _model(k), id=w.id(k)), f"deleting {kind} removed {k}"
    actions = (await db_session.execute(select(ActivityLog.action).where(ActivityLog.resource_id == w.id(kind)))).scalars().all()
    assert any(a.startswith("deleted") for a in actions), f"no audit entry for {url}: {actions}"
    assert (await client.delete(url)).status_code == 404, "a second delete is a 404"


def _links():
    from models import associations as A
    rows = [
        ("/findings/{f}/testcases/{t}", A.FindingTestCase, {"finding_id": "f", "testcase_id": "t"}),
        ("/findings/{f}/vault-items/{v}", A.VaultItemFinding, {"finding_id": "f", "vault_item_id": "v"}),
        ("/findings/{f}/cleanup-artifacts/{c}", A.CleanupArtifactFinding, {"finding_id": "f", "cleanup_artifact_id": "c"}),
        ("/assets/{a}/findings/{f}", A.FindingAsset, {"asset_id": "a", "finding_id": "f"}),
        ("/assets/{a}/testcases/{t}", A.TestCaseAsset, {"asset_id": "a", "testcase_id": "t"}),
        ("/assets/{a}/vault-items/{v}", A.VaultItemAsset, {"asset_id": "a", "vault_item_id": "v"}),
        ("/assets/{a}/cleanup-artifacts/{c}", A.CleanupArtifactAsset, {"asset_id": "a", "cleanup_artifact_id": "c"}),
        ("/testcases/{t}/findings/{f}", A.FindingTestCase, {"testcase_id": "t", "finding_id": "f"}),
        ("/testcases/{t}/assets/{a}", A.TestCaseAsset, {"testcase_id": "t", "asset_id": "a"}),
        ("/testcases/{t}/vault-items/{v}", A.VaultItemTestCase, {"testcase_id": "t", "vault_item_id": "v"}),
        ("/testcases/{t}/cleanup-artifacts/{c}", A.CleanupArtifactTestCase, {"testcase_id": "t", "cleanup_artifact_id": "c"}),
        ("/vault/{v}/findings/{f}", A.VaultItemFinding, {"vault_item_id": "v", "finding_id": "f"}),
        ("/vault/{v}/testcases/{t}", A.VaultItemTestCase, {"vault_item_id": "v", "testcase_id": "t"}),
        ("/vault/{v}/assets/{a}", A.VaultItemAsset, {"vault_item_id": "v", "asset_id": "a"}),
        ("/cleanup-artifacts/{c}/findings/{f}", A.CleanupArtifactFinding, {"cleanup_artifact_id": "c", "finding_id": "f"}),
        ("/cleanup-artifacts/{c}/testcases/{t}", A.CleanupArtifactTestCase, {"cleanup_artifact_id": "c", "testcase_id": "t"}),
        ("/cleanup-artifacts/{c}/assets/{a}", A.CleanupArtifactAsset, {"cleanup_artifact_id": "c", "asset_id": "a"}),
        ("/notes/{n}/findings/{f}", A.NoteFinding, {"note_id": "n", "finding_id": "f"}),
        ("/notes/{n}/testcases/{t}", A.NoteTestCase, {"note_id": "n", "testcase_id": "t"}),
        ("/notes/{n}/assets/{a}", A.NoteAsset, {"note_id": "n", "asset_id": "a"}),
        ("/notes/{n}/vault-items/{v}", A.NoteVaultItem, {"note_id": "n", "vault_item_id": "v"}),
        ("/notes/{n}/cleanup-artifacts/{c}", A.NoteCleanupArtifact, {"note_id": "n", "cleanup_artifact_id": "c"}),
    ]
    return rows


LINK_PATHS = [p for p, _, _ in _links()]


def test_every_unlink_route_is_listed():
    """A new unlink route between these resources must be added above."""
    import re
    import main
    from fastapi.routing import APIRoute
    shape = r"/(findings|assets|testcases|vault|cleanup-artifacts|notes)/\{\w+\}/(findings|assets|testcases|vault-items|cleanup-artifacts)/\{\w+\}$"
    letter = {"finding": "f", "asset": "a", "testcase": "t", "vault": "v", "item": "v",
              "cleanup": "c", "artifact": "c", "note": "n"}
    live = {re.sub(r"\{([a-z]+)_?\w*\}", lambda m: "{" + letter[m.group(1)] + "}", r.path)
            for r in main.app.routes
            if isinstance(r, APIRoute) and "DELETE" in r.methods and re.match(shape, r.path)}
    assert live == set(LINK_PATHS), sorted(live ^ set(LINK_PATHS))


@pytest.mark.parametrize("path", LINK_PATHS)
async def test_unlink(client, db_session, authenticate_as, world, path):
    model, cols = next((m, c) for p, m, c in _links() if p == path)
    w = world
    key = {col: w.id(kind) for col, kind in cols.items()}
    db_session.add(model(**key))
    await db_session.commit()
    url = path.format(**{k: o.id for k, o in w.objs.items()})

    await _refused(client, authenticate_as, w, url)
    assert await _exists(db_session, model, **key), "a refused unlink removed the link"

    authenticate_as(w.admin)
    r = await client.delete(url)
    assert r.status_code in (200, 204), (url, r.status_code, r.text)
    assert not await _exists(db_session, model, **key), "the link is still there"
    for kind in cols.values():
        assert await _exists(db_session, _model(kind), id=w.id(kind)), f"unlinking removed the {kind} itself"
