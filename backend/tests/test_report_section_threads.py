"""Review threads on report builder sections.

Covers: section ids surviving a layout save (so threads stay attached),
threads of removed sections being cleaned up, the report_section ownership
check on thread create, the `content` anchor field, and the deep link.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from models.discussion import Thread
from models.engagement import Engagement
from routers.discussions import _comment_deep_link


async def _setup(db, make_user, authenticate_as):
    admin = await make_user(role="admin", username=f"rs_admin_{uuid.uuid4().hex[:6]}")
    authenticate_as(admin)
    engs = []
    for name in ("Report Threads A", "Report Threads B"):
        eng = Engagement(id=str(uuid.uuid4()), name=f"{name} {uuid.uuid4().hex[:4]}", client_name="ACME",
                         engagement_type="external_pentest", created_by=admin.id)
        db.add(eng)
        engs.append(eng)
    await db.flush()
    return admin, engs


def _sections(*titles, ids=None):
    ids = ids or [None] * len(titles)
    return [{"id": i, "section_type": "text", "title": t, "content": f"{t} body", "sort_order": n}
            for n, (t, i) in enumerate(zip(titles, ids))]


async def _thread(client, eng_id, section_id, **extra):
    return await client.post("/discussions/threads", json={
        "engagement_id": eng_id, "resource_type": "report_section",
        "resource_id": section_id, "title": "Review", **extra})


async def test_section_ids_survive_save_and_removed_threads_are_deleted(client, db_session, make_user, authenticate_as):
    _, (eng, _) = await _setup(db_session, make_user, authenticate_as)
    created = await client.post(f"/engagements/{eng.id}/report-layouts",
                                json={"name": "Main", "sections": _sections("Intro", "Scope")})
    assert created.status_code == 201, created.text
    layout = created.json()
    intro, scope = sorted(layout["sections"], key=lambda s: s["sort_order"])

    keep = await _thread(client, eng.id, intro["id"])
    gone = await _thread(client, eng.id, scope["id"])
    assert keep.status_code == 201 and gone.status_code == 201, (keep.text, gone.text)

    # Reorder + edit Intro, drop Scope, add a new section.
    upd = await client.put(f"/engagements/{eng.id}/report-layouts/{layout['id']}", json={
        "sections": _sections("New", "Intro (edited)", ids=[None, intro["id"]])})
    assert upd.status_code == 200, upd.text
    secs = sorted(upd.json()["sections"], key=lambda s: s["sort_order"])
    assert secs[1]["id"] == intro["id"] and secs[1]["title"] == "Intro (edited)"
    assert secs[0]["id"] not in (intro["id"], scope["id"])

    remaining = {t.id for t in (await db_session.execute(
        select(Thread).where(Thread.resource_type == "report_section"))).scalars()}
    assert keep.json()["id"] in remaining
    assert gone.json()["id"] not in remaining


async def test_foreign_section_id_creates_new_section(client, db_session, make_user, authenticate_as):
    _, (eng_a, eng_b) = await _setup(db_session, make_user, authenticate_as)
    a = (await client.post(f"/engagements/{eng_a.id}/report-layouts",
                           json={"name": "A", "sections": _sections("A1")})).json()
    b = (await client.post(f"/engagements/{eng_b.id}/report-layouts",
                           json={"name": "B", "sections": _sections("B1")})).json()
    a_sec = a["sections"][0]["id"]

    # Sending another layout's section id must not move or modify it.
    upd = await client.put(f"/engagements/{eng_b.id}/report-layouts/{b['id']}",
                           json={"sections": _sections("Hijack", ids=[a_sec])})
    assert upd.status_code == 200, upd.text
    assert upd.json()["sections"][0]["id"] != a_sec
    a_after = (await client.get(f"/engagements/{eng_a.id}/report-layouts/{a['id']}")).json()
    assert a_after["sections"][0]["id"] == a_sec and a_after["sections"][0]["title"] == "A1"


async def test_thread_create_checks_section_engagement_and_anchor(client, db_session, make_user, authenticate_as):
    _, (eng_a, eng_b) = await _setup(db_session, make_user, authenticate_as)
    a = (await client.post(f"/engagements/{eng_a.id}/report-layouts",
                           json={"name": "A", "sections": _sections("A1")})).json()
    sec = a["sections"][0]["id"]

    cross = await _thread(client, eng_b.id, sec)
    assert cross.status_code == 400

    missing = await _thread(client, eng_a.id, str(uuid.uuid4()))
    assert missing.status_code == 404

    anchor = {"field": "content", "quote": "A1 body", "prefix": None, "suffix": None, "occurrence": 0}
    ok = await _thread(client, eng_a.id, sec, anchor=anchor)
    assert ok.status_code == 201, ok.text
    assert ok.json()["anchor"]["field"] == "content"

    bad = await _thread(client, eng_a.id, sec, anchor={**anchor, "field": "title"})
    assert bad.status_code == 400


def test_report_section_deep_link():
    t = Thread(resource_type="report_section", resource_id="sec-1", engagement_id="eng-1")
    assert _comment_deep_link(t, "c-1") == "/engagements/eng-1?tab=reporting&sectionId=sec-1&commentId=c-1"
