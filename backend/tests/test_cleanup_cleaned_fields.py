"""cleaned_at / cleaned_by follow the CLEANED status: set when created as
CLEANED, cleared when it moves out of CLEANED."""

from __future__ import annotations

from tests.test_authz_boundaries import _make_engagement


async def test_cleaned_fields_track_status(client, db_session, make_user, authenticate_as):
    admin = await make_user(role="admin")
    authenticate_as(admin)
    eng = await _make_engagement(db_session)
    r = await client.post("/cleanup-artifacts", json={
        "engagement_id": eng.id, "title": "implant", "artifact_type": "file", "status": "CLEANED"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["cleaned_at"] and body["cleaned_by"] == admin.id

    r = await client.patch(f"/cleanup-artifacts/{body['id']}", json={"status": "PENDING"})
    assert r.status_code == 200, r.text
    assert r.json()["cleaned_at"] is None and r.json()["cleaned_by"] is None
