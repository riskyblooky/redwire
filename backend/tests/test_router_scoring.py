"""Integration tests for scoring on the findings + scoring routers.

Covers the server being authoritative over the computed rating, the
scoring-model policy (site-wide lock, per-engagement allow-list) being
enforced on create/update with a 422, and the computed ``score_outcome``.
"""

from __future__ import annotations

import uuid

from models.engagement import Engagement
from utils.scoring_policy import set_site_policy

USAF_TOP = {"sev": "catastrophic", "prob": "frequent"}


async def _make_engagement(db, **kw) -> Engagement:
    eng = Engagement(id=str(uuid.uuid4()), name="Scoring Test", client_name="ACME",
                     engagement_type="external_pentest", **kw)
    db.add(eng)
    await db.flush()
    return eng


def _payload(engagement_id: str, **overrides) -> dict:
    payload = {"engagement_id": engagement_id, "title": "Scored finding",
               "description": "x", "severity": "LOW"}
    payload.update(overrides)
    return payload


async def _admin(make_user, authenticate_as):
    admin = await make_user(role="admin", username=f"score_admin_{uuid.uuid4().hex[:6]}")
    authenticate_as(admin)
    return admin


async def test_server_recomputes_rating_from_inputs(client, db_session, make_user, authenticate_as):
    await _admin(make_user, authenticate_as)
    eng = await _make_engagement(db_session)

    # Client claims LOW / 1.0, but the inputs score CRITICAL — inputs win.
    resp = await client.post("/findings", json=_payload(
        eng.id, cvss_score=1.0, score_model="cvss31",
        score_inputs={"AV": "N", "AC": "L", "PR": "N", "UI": "N", "S": "U", "C": "H", "I": "H", "A": "H"},
    ))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["severity"] == "CRITICAL"
    assert body["cvss_score"] == 9.8
    assert body["cvss_vector"] == "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"
    assert body["score_outcome"] is None  # numeric model


async def test_categorical_finding_exposes_outcome(client, db_session, make_user, authenticate_as):
    await _admin(make_user, authenticate_as)
    eng = await _make_engagement(db_session)

    resp = await client.post("/findings", json=_payload(eng.id, score_model="usaf-rac", score_inputs=USAF_TOP))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["severity"] == "CRITICAL"
    assert body["score_outcome"] == "Extremely High"

    got = await client.get(f"/findings/{body['id']}")
    assert got.json()["score_outcome"] == "Extremely High"


async def test_inputs_without_model_rejected(client, db_session, make_user, authenticate_as):
    await _admin(make_user, authenticate_as)
    eng = await _make_engagement(db_session)
    resp = await client.post("/findings", json=_payload(eng.id, score_inputs=USAF_TOP))
    assert resp.status_code == 422


async def test_invalid_inputs_rejected(client, db_session, make_user, authenticate_as):
    await _admin(make_user, authenticate_as)
    eng = await _make_engagement(db_session)
    resp = await client.post("/findings", json=_payload(
        eng.id, score_model="usaf-rac", score_inputs={"sev": "catastrophic", "prob": "never"}))
    assert resp.status_code == 422


async def test_site_lock_rejects_other_models(client, db_session, make_user, authenticate_as):
    admin = await _admin(make_user, authenticate_as)
    eng = await _make_engagement(db_session)
    await set_site_policy(db_session, enabled_models=None, default_model=None,
                          locked_model="usaf-rac", user_id=admin.id)

    bad = await client.post("/findings", json=_payload(
        eng.id, score_model="dread", score_inputs={k: 5 for k in ("D", "R", "E", "A", "Di")}))
    assert bad.status_code == 422
    assert "not permitted" in bad.json()["detail"]

    ok = await client.post("/findings", json=_payload(eng.id, score_model="usaf-rac", score_inputs=USAF_TOP))
    assert ok.status_code == 201, ok.text

    pol = await client.get("/scoring/effective-policy", params={"engagement_id": eng.id})
    assert pol.status_code == 200
    assert pol.json()["locked"] is True
    assert [m["id"] for m in pol.json()["allowed"]] == ["usaf-rac"]


async def test_engagement_allow_list_enforced_on_update(client, db_session, make_user, authenticate_as):
    await _admin(make_user, authenticate_as)
    eng = await _make_engagement(db_session, allowed_score_models=["cvss31", "usaf-rac"])

    created = await client.post("/findings", json=_payload(eng.id, score_model="usaf-rac", score_inputs=USAF_TOP))
    assert created.status_code == 201, created.text
    fid = created.json()["id"]

    bad = await client.put(f"/findings/{fid}", json={
        "score_model": "dread", "score_inputs": {k: 5 for k in ("D", "R", "E", "A", "Di")}})
    assert bad.status_code == 422

    # Tweaking inputs without resending the model rescores under the stored model.
    ok = await client.put(f"/findings/{fid}", json={"score_inputs": {"sev": "negligible", "prob": "rarely"}})
    assert ok.status_code == 200, ok.text
    assert ok.json()["severity"] == "LOW"
    assert ok.json()["score_outcome"] == "Low"
