"""Foreign keys enforce the same delete behaviour as the ORM cascades, so a
delete done outside the ORM (raw SQL, a bulk delete) agrees with the app."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, text

from tests.test_authz_boundaries import _make_engagement


def _u():
    return str(uuid.uuid4())


async def _tree(db, admin):
    from models.asset import Asset
    from models.evidence import Evidence
    from models.finding import Finding, Severity
    from models.testcase import TestCase
    eng = await _make_engagement(db)
    f = Finding(id=_u(), engagement_id=eng.id, title="f", description="d", severity=Severity.LOW,
                created_by=admin.id)
    tc = TestCase(id=_u(), engagement_id=eng.id, title="t", category="Recon", description="d", created_by=admin.id)
    db.add_all([f, tc, Asset(id=_u(), engagement_id=eng.id, name="h", identifier=f"10.0.0.{uuid.uuid4().int % 250}",
                             asset_type="host")])
    await db.flush()
    ev_tc = Evidence(id=_u(), engagement_id=eng.id, testcase_id=tc.id, filename="a", original_filename="a",
                     file_path="k/a", file_size=1)
    ev_f = Evidence(id=_u(), engagement_id=eng.id, finding_id=f.id, filename="b", original_filename="b",
                    file_path="k/b", file_size=1)
    db.add_all([ev_tc, ev_f])
    await db.flush()
    return eng, f, tc, ev_tc, ev_f


async def test_sql_engagement_delete_removes_children(db_session, make_user):
    from models.asset import Asset
    from models.evidence import Evidence
    from models.finding import Finding
    from models.testcase import TestCase
    eng, *_ = await _tree(db_session, await make_user(role="admin"))
    await db_session.execute(text("DELETE FROM engagements WHERE id = :id"), {"id": eng.id})
    for model in (Asset, Finding, TestCase, Evidence):
        n = (await db_session.execute(select(func.count()).select_from(model)
                                      .where(model.engagement_id == eng.id))).scalar()
        assert n == 0, model.__name__


async def test_sql_testcase_delete_unlinks_evidence_and_finding_delete_removes_it(db_session, make_user):
    from models.evidence import Evidence
    _eng, f, tc, ev_tc, ev_f = await _tree(db_session, await make_user(role="admin"))
    f_id, tc_id, ev_tc_id, ev_f_id = f.id, tc.id, ev_tc.id, ev_f.id
    await db_session.execute(text("DELETE FROM testcases WHERE id = :id"), {"id": tc_id})
    await db_session.execute(text("DELETE FROM findings WHERE id = :id"), {"id": f_id})
    db_session.expire_all()
    left = (await db_session.execute(select(Evidence.id, Evidence.testcase_id)
                                     .where(Evidence.id.in_([ev_tc_id, ev_f_id])))).all()
    assert left == [(ev_tc_id, None)]
