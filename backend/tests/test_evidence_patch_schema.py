"""PATCH /evidence/{id} takes a typed body: wrong types are a 422 instead
of being written as-is, unknown keys are ignored, and a partial body
changes only what it names."""

from __future__ import annotations

import uuid


async def test_evidence_patch_is_typed(client, db_session, make_user, authenticate_as):
    from models.evidence import Evidence
    from tests.test_authz_boundaries import _make_engagement
    admin = await make_user(role="admin")
    eng = await _make_engagement(db_session, created_by=admin.id)
    ev = Evidence(id=str(uuid.uuid4()), engagement_id=eng.id, filename="a.txt", original_filename="a.txt",
                  file_path="k/a.txt", file_size=1, created_by=admin.id, description="keep")
    db_session.add(ev)
    await db_session.flush()
    authenticate_as(admin)
    for bad in ({"include_in_report": {"x": 1}}, {"description": ["a"]}, {"classification_level": "X" * 21},
                {"finding_id": 5}):
        r = await client.patch(f"/evidence/{ev.id}", json=bad)
        assert r.status_code == 422, (bad, r.status_code, r.text)
    r = await client.patch(f"/evidence/{ev.id}", json={"include_in_report": False, "bogus": 1})
    assert r.status_code == 200, r.text
    assert r.json()["include_in_report"] is False and r.json()["description"] == "keep"
    r = await client.patch(f"/evidence/{ev.id}", json={"include_in_report": None, "classification_level": "S"})
    assert r.status_code == 200 and r.json()["include_in_report"] is False and r.json()["classification_level"] == "S"
