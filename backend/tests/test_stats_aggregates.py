"""Stats aggregates: an operator with findings only outside the date range
is still listed (with 0); evidence not on a finding is counted; a
categorical model's nominal cvss_score stays out of the CVSS average."""

from __future__ import annotations

import uuid
from datetime import datetime

from models.evidence import Evidence
from models.finding import Finding, Severity
from tests.test_authz_boundaries import _make_engagement


async def test_stats_aggregates(client, db_session, make_user, authenticate_as):
    admin = await make_user(role="admin")
    op = await make_user(role="operator")
    authenticate_as(admin)
    eng = await _make_engagement(db_session)
    old = Finding(id=str(uuid.uuid4()), engagement_id=eng.id, title="old", description="d",
                  severity=Severity.LOW, created_by=op.id, created_at=datetime(2020, 1, 1),
                  cvss_score=4.0, score_model="cvss31")
    cat = Finding(id=str(uuid.uuid4()), engagement_id=eng.id, title="cat", description="d",
                  severity=Severity.CRITICAL, created_by=admin.id, cvss_score=9.9, score_model="usaf-rac")
    db_session.add_all([old, cat])
    await db_session.flush()
    db_session.add(Evidence(id=str(uuid.uuid4()), engagement_id=eng.id, filename="e", original_filename="e",
                            file_path="k/e", file_size=1, created_by=admin.id))
    await db_session.flush()

    perf = (await client.get("/stats/operator-performance",
                             params={"start_date": "2026-01-01", "end_date": "2026-12-31"})).json()
    mine = [o for o in perf["operators"] if o["user_id"] == op.id]
    assert mine and mine[0]["total_findings"] == 0

    ov = (await client.get("/stats/overview", params={"engagement_id": eng.id})).json()
    assert ov["total_evidence"] == 1
    assert ov["avg_cvss"] == 4.0, ov
