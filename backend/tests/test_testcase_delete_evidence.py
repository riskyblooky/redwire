"""Deleting a test case takes its evidence with it, as deleting a finding
does (rows and stored files); evidence also on a finding stays there."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from models.evidence import Evidence
from models.finding import Finding, Severity
from models.testcase import TestCase
from tests.test_authz_boundaries import _make_engagement
from utils.storage import storage_service


async def _ev(db, eng, tc_id, finding_id=None):
    key = f"test-tc-del/{uuid.uuid4()}.txt"
    await storage_service.upload_file(b"proof", key, "text/plain")
    ev = Evidence(id=str(uuid.uuid4()), engagement_id=eng.id, testcase_id=tc_id, finding_id=finding_id,
                  filename=key, original_filename="p.txt", file_path=key, file_size=5, mime_type="text/plain")
    db.add(ev)
    return ev.id, key


async def _exists(key):
    try:
        return await storage_service.download_file(key) is not None
    except Exception:
        return False


async def test_delete_takes_testcase_only_evidence(client, db_session, make_user, authenticate_as):
    eng = await _make_engagement(db_session)
    parent = TestCase(id=str(uuid.uuid4()), engagement_id=eng.id, title="P", category="c", description="d")
    child = TestCase(id=str(uuid.uuid4()), engagement_id=eng.id, title="C", category="c", description="d",
                     parent_id=parent.id)
    f = Finding(id=str(uuid.uuid4()), engagement_id=eng.id, title="F", description="d", severity=Severity.HIGH)
    db_session.add_all([parent, f])
    await db_session.flush()
    db_session.add(child)
    await db_session.flush()
    only_parent, k1 = await _ev(db_session, eng, parent.id)
    only_child, k2 = await _ev(db_session, eng, child.id)
    shared, k3 = await _ev(db_session, eng, parent.id, finding_id=f.id)
    await db_session.flush()
    authenticate_as(await make_user(role="admin"))

    r = await client.delete(f"/testcases/{parent.id}", params={"cascade": "true"})
    assert r.status_code == 204, r.text
    rows = {e.id: e for e in (await db_session.execute(
        select(Evidence).where(Evidence.id.in_([only_parent, only_child, shared]))
        .execution_options(populate_existing=True))).scalars().all()}
    assert set(rows) == {shared}
    assert rows[shared].finding_id == f.id and rows[shared].testcase_id is None
    assert not await _exists(k1) and not await _exists(k2) and await _exists(k3)
