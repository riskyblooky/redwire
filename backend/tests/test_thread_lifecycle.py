"""Discussion threads follow their entity: deleted with it, and carried
(highlight anchor included) through engagement export → import."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from models.discussion import Thread
from models.engagement import Engagement
from routers.engagements_transfer import _import_anchor

ANCHOR = {"field": "description", "quote": "the quote", "prefix": "before ", "suffix": " after", "occurrence": 1}


async def _setup(db, make_user, authenticate_as):
    admin = await make_user(role="admin", username=f"tl_admin_{uuid.uuid4().hex[:6]}")
    authenticate_as(admin)
    eng = Engagement(id=str(uuid.uuid4()), name=f"Thread Lifecycle {uuid.uuid4().hex[:6]}", client_name="ACME",
                     engagement_type="external_pentest", created_by=admin.id)
    db.add(eng)
    await db.flush()
    return admin, eng


async def _finding(client, eng_id, title):
    r = await client.post("/findings", json={"engagement_id": eng_id, "title": title,
                                             "description": "has the quote in it", "severity": "LOW"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _thread(client, eng_id, rtype, rid, **extra):
    r = await client.post("/discussions/threads", json={
        "engagement_id": eng_id, "resource_type": rtype, "resource_id": rid, "title": "T", **extra})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _thread_ids(db):
    return {t.id for t in (await db.execute(select(Thread))).scalars()}


async def test_deleting_finding_deletes_its_threads_only(client, db_session, make_user, authenticate_as):
    _, eng = await _setup(db_session, make_user, authenticate_as)
    doomed, kept = await _finding(client, eng.id, "Doomed"), await _finding(client, eng.id, "Kept")
    t_general = await _thread(client, eng.id, "finding", doomed)
    t_anchor = await _thread(client, eng.id, "finding", doomed, anchor=ANCHOR)
    t_remed = await _thread(client, eng.id, "finding_remediation", doomed)
    t_other = await _thread(client, eng.id, "finding", kept)
    c = await client.post("/discussions/comments", json={"thread_id": t_general, "content": "hi"})
    assert c.status_code == 201, c.text

    assert (await client.delete(f"/findings/{doomed}")).status_code == 204
    remaining = await _thread_ids(db_session)
    assert not {t_general, t_anchor, t_remed} & remaining
    assert t_other in remaining


async def test_deleting_testcase_deletes_its_threads(client, db_session, make_user, authenticate_as):
    _, eng = await _setup(db_session, make_user, authenticate_as)
    tc = await client.post("/testcases", json={"engagement_id": eng.id, "title": "TC", "category": "Recon", "description": "x"})
    assert tc.status_code in (200, 201), tc.text
    tid = await _thread(client, eng.id, "testcase", tc.json()["id"])
    assert (await client.delete(f"/testcases/{tc.json()['id']}")).status_code == 204
    assert tid not in await _thread_ids(db_session)


async def test_export_import_keeps_thread_anchor(client, db_session, make_user, authenticate_as):
    _, eng = await _setup(db_session, make_user, authenticate_as)
    fid = await _finding(client, eng.id, "Anchored")
    await _thread(client, eng.id, "finding", fid, anchor=ANCHOR)

    exp = await client.get(f"/engagements/{eng.id}/export")
    assert exp.status_code == 200, exp.text
    imp = await client.post("/engagements/import",
                            files={"file": ("e.zip", exp.content, "application/zip")})
    assert imp.status_code == 201, imp.text
    new_eng = imp.json().get("engagement_id") or imp.json().get("id")

    th = (await db_session.execute(select(Thread).where(Thread.engagement_id == new_eng))).scalars().all()
    assert len(th) == 1
    t = th[0]
    assert t.resource_id and t.resource_id != fid
    assert (t.anchor_field, t.anchor_quote, t.anchor_prefix, t.anchor_suffix, t.anchor_occurrence) == \
        ("description", "the quote", "before ", " after", 1)


def test_import_anchor_validation():
    row = {"anchor_field": "description", "anchor_quote": "q", "anchor_prefix": "p" * 500,
           "anchor_suffix": None, "anchor_occurrence": 2, "anchor_status": "orphaned"}
    got = _import_anchor(row, "finding")
    assert got["anchor_field"] == "description" and got["anchor_status"] == "orphaned"
    assert len(got["anchor_prefix"]) == 128 and got["anchor_occurrence"] == 2

    assert _import_anchor({**row, "anchor_field": "title"}, "finding") == {}       # not annotatable
    assert _import_anchor(row, "asset") == {}                                      # type has no anchors
    assert _import_anchor({**row, "anchor_quote": 5}, "finding") == {}             # wrong type
    assert _import_anchor({}, "finding") == {}                                     # plain thread
    bad = _import_anchor({**row, "anchor_occurrence": -3, "anchor_status": "x"}, "finding")
    assert bad["anchor_occurrence"] == 0 and bad["anchor_status"] == "active"
    assert _import_anchor({**row, "anchor_occurrence": True}, "finding")["anchor_occurrence"] == 0
