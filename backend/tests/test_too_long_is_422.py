"""A string longer than its column is a 422, not a 500; an over-long
evidence-upload description is refused before the blob is stored."""

from __future__ import annotations

import uuid

from models.evidence import Evidence
from models.finding import Finding, Severity
from tests.test_authz_boundaries import _make_engagement


async def test_too_long_is_422(client, db_session, make_user, authenticate_as, monkeypatch):
    admin = await make_user(role="admin")
    authenticate_as(admin)
    eng = await _make_engagement(db_session)
    f = Finding(id=str(uuid.uuid4()), engagement_id=eng.id, title="F", description="d", severity=Severity.LOW)
    db_session.add(f)
    await db_session.flush()
    ev = Evidence(id=str(uuid.uuid4()), finding_id=f.id, engagement_id=eng.id, filename="a.txt",
                  original_filename="a.txt", file_path="k/a.txt", file_size=1, created_by=admin.id)
    db_session.add(ev)
    await db_session.flush()

    r = await client.patch(f"/evidence/{ev.id}", json={"description": "x" * 600})
    assert r.status_code == 422, (r.status_code, r.text)

    from utils import storage_tx
    uploads = []

    async def upload(*a, **kw):
        uploads.append(a)
    monkeypatch.setattr(storage_tx, "upload", upload)
    r = await client.post(f"/findings/{f.id}/evidence", data={"description": "x" * 600},
                          files={"file": ("a.png", b"\\x89PNG\\r\\n\\x1a\\n", "image/png")})
    assert r.status_code == 422 and uploads == []
