"""The ATT&CK Navigator layer includes techniques mapped on test cases, not
only on findings."""

from __future__ import annotations

import uuid

from models.associations import FindingAttackTechnique, TestCaseAttackTechnique
from models.finding import Finding, Severity
from models.testcase import TestCase
from tests.test_authz_boundaries import _make_engagement


async def test_layer_has_testcase_techniques(client, db_session, make_user, authenticate_as):
    eng = await _make_engagement(db_session)
    f = Finding(id=str(uuid.uuid4()), engagement_id=eng.id, title="F", description="d", severity=Severity.HIGH)
    tc = TestCase(id=str(uuid.uuid4()), engagement_id=eng.id, title="TC", category="Execution", description="d")
    db_session.add_all([f, tc])
    await db_session.flush()
    db_session.add_all([FindingAttackTechnique(finding_id=f.id, technique_id="T1059.001"),
                        TestCaseAttackTechnique(testcase_id=tc.id, technique_id="T1059.001"),
                        TestCaseAttackTechnique(testcase_id=tc.id, technique_id="T1003")])
    await db_session.flush()
    authenticate_as(await make_user(role="admin"))

    layer = (await client.get(f"/attack/engagement/{eng.id}/navigator")).json()
    by_id = {t["techniqueID"]: t for t in layer["techniques"]}
    assert set(by_id) == {"T1059.001", "T1003"}
    assert by_id["T1003"]["comment"] == "1 test case" and by_id["T1003"]["color"] == "#22c55e"
    assert by_id["T1059.001"]["comment"] == "1 finding: max severity HIGH; 1 test case"
    assert by_id["T1059.001"]["color"] == "#ff6600"
