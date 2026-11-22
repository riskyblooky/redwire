"""Evidence with no engagement_id (finding-attached legacy rows) was logged
under engagement_id="global" — not an engagement, so the foreign key
rejected the entry and the audit trail silently lost the change."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from models.discussion import ActivityLog
from models.evidence import Evidence
from models.finding import Finding, Severity
from tests.test_authz_boundaries import _make_engagement


async def test_metadata_edit_is_logged(client, db_session, make_user, authenticate_as):
    admin = await make_user(role="admin")
    authenticate_as(admin)
    eng = await _make_engagement(db_session)
    f = Finding(id=str(uuid.uuid4()), engagement_id=eng.id, title="F", description="d", severity=Severity.LOW)
    db_session.add(f)
    await db_session.flush()
    ev = Evidence(id=str(uuid.uuid4()), finding_id=f.id, engagement_id=None, filename="a.txt",
                  original_filename="a.txt", file_path="k/a.txt", file_size=1, created_by=admin.id)
    db_session.add(ev)
    await db_session.flush()

    r = await client.patch(f"/evidence/{ev.id}", json={"description": "new caption"})
    assert r.status_code == 200, r.text
    logs = (await db_session.execute(select(ActivityLog).where(ActivityLog.resource_id == ev.id))).scalars().all()
    assert logs and logs[0].engagement_id is None
