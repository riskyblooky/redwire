"""Engagement delete removes the object of legacy evidence that has no
engagement_id (only a finding / test case)."""

from __future__ import annotations

import uuid

from models.evidence import Evidence
from models.finding import Finding, Severity
from models.testcase import TestCase
from tests.test_authz_boundaries import _make_engagement
from utils.storage_cleanup import engagement_object_keys


async def test_legacy_evidence_keys_included(db_session, make_user):
    admin = await make_user(role="admin")
    eng = await _make_engagement(db_session)
    other = await _make_engagement(db_session)
    f = Finding(id=str(uuid.uuid4()), engagement_id=eng.id, title="F", description="d", severity=Severity.LOW)
    tc = TestCase(id=str(uuid.uuid4()), engagement_id=eng.id, title="T", category="c", description="d")
    fo = Finding(id=str(uuid.uuid4()), engagement_id=other.id, title="O", description="d", severity=Severity.LOW)
    db_session.add_all([f, tc, fo])
    await db_session.flush()

    def ev(key, **kw):
        return Evidence(id=str(uuid.uuid4()), filename="e", original_filename="e", file_path=key,
                        file_size=1, created_by=admin.id, **kw)
    db_session.add_all([ev("k/own", engagement_id=eng.id), ev("k/legacy-f", finding_id=f.id),
                        ev("k/legacy-tc", testcase_id=tc.id), ev("k/other", finding_id=fo.id)])
    await db_session.flush()
    assert sorted(await engagement_object_keys(db_session, eng.id)) == ["k/legacy-f", "k/legacy-tc", "k/own"]
