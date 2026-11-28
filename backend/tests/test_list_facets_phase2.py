"""The vault and cleanup facets (the type chips' and stat cards' counts,
independent of the list's page) and the filters those lists gained."""

from __future__ import annotations

import uuid

from models.cleanup_artifact import CleanupArtifact, CleanupArtifactStatus
from models.vault import VaultItem
from tests.test_authz_boundaries import _assign, _make_engagement, _make_engagement_role


async def _seed(db):
    e = await _make_engagement(db)
    for name, typ in [("Domain admin", "CREDENTIAL"), ("svc_backup", "CREDENTIAL"), ("id_rsa", "KEY")]:
        db.add(VaultItem(id=str(uuid.uuid4()), engagement_id=e.id, name=name, item_type=typ))
    for title, st in [("Implant on DC01", CleanupArtifactStatus.PENDING), ("Scheduled task", CleanupArtifactStatus.CLEANED),
                      ("Web shell", CleanupArtifactStatus.PENDING)]:
        db.add(CleanupArtifact(id=str(uuid.uuid4()), engagement_id=e.id, title=title, artifact_type="Other", status=st))
    await db.commit()
    return e


async def test_vault_facets_and_filters(client, db_session, make_user, authenticate_as):
    e = await _seed(db_session)
    authenticate_as(await make_user(role="admin"))
    assert (await client.get("/vault/facets", params={"engagement_id": e.id})).json() == \
        {"total": 3, "types": {"CREDENTIAL": 2, "KEY": 1}}
    r = await client.get("/vault", params={"engagement_id": e.id, "item_type": "CREDENTIAL", "sort_by": "name"})
    assert [i["name"] for i in r.json()] == ["Domain admin", "svc_backup"] and r.headers["X-Total-Count"] == "2"
    r = await client.get("/vault", params={"engagement_id": e.id})
    assert len(r.json()) == 3, "no limit: everything"


async def test_cleanup_facets_and_filters(client, db_session, make_user, authenticate_as):
    e = await _seed(db_session)
    authenticate_as(await make_user(role="admin"))
    assert (await client.get("/cleanup-artifacts/facets", params={"engagement_id": e.id})).json() == \
        {"total": 3, "statuses": {"PENDING": 2, "CLEANED": 1}}
    r = await client.get("/cleanup-artifacts", params={"engagement_id": e.id, "status": "PENDING", "q": "dc01"})
    assert [a["title"] for a in r.json()] == ["Implant on DC01"]


async def test_facets_need_the_view_permission(client, db_session, make_user, authenticate_as):
    e = await _seed(db_session)
    member = await make_user()
    await _assign(db_session, member, e, await _make_engagement_role(db_session, ["engagement_view"]))
    await db_session.commit()
    authenticate_as(member)
    assert (await client.get("/vault/facets", params={"engagement_id": e.id})).status_code == 403
    assert (await client.get("/cleanup-artifacts/facets", params={"engagement_id": e.id})).status_code == 403
