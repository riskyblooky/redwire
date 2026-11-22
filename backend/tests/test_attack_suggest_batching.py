"""ATT&CK auto-suggest can be walked in short batches (offset / limit over a
stable order, with the total reported), so a large engagement isn't one
request that outlives the proxy timeout and loses every result."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import routers.attack_techniques as at
from models.ai_settings import AiSetting
from models.finding import Finding, Severity
from tests.test_authz_boundaries import _make_engagement


async def _setup(db_session, make_user, monkeypatch, n=3):
    eng = await _make_engagement(db_session)
    t0 = datetime(2026, 1, 1)
    ids = []
    for i in range(n):
        f = Finding(id=str(uuid.uuid4()), engagement_id=eng.id, title=f"F{i}", description="d",
                    severity=Severity.HIGH, created_at=t0 + timedelta(minutes=i))
        db_session.add(f)
        ids.append(f.id)
    for k, v in (("ai_enabled", "true"), ("ai_api_key", "k")):
        if await db_session.get(AiSetting, k) is None:
            db_session.add(AiSetting(key=k, value=v))
        else:
            (await db_session.get(AiSetting, k)).value = v
    await db_session.flush()
    seen = []

    async def fake(client, entity, *a, **kw):
        seen.append(entity.id)
        return {"finding_id": entity.id, "techniques": [{"technique_id": "T1059"}]}
    monkeypatch.setattr(at, "_suggest_for_finding", fake)
    return eng, ids, seen


async def test_walks_in_batches_of_one(client, db_session, make_user, authenticate_as, monkeypatch):
    eng, ids, seen = await _setup(db_session, make_user, monkeypatch)
    authenticate_as(await make_user(role="admin"))
    offset, got = 0, []
    while offset is not None:
        r = await client.post(f"/attack/engagement/{eng.id}/suggest", json={"offset": offset, "limit": 1})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] == 3 and len(body["suggestions"]) == 1
        got += [s["finding_id"] for s in body["suggestions"]]
        offset = body["next_offset"]
    assert got == ids and seen == ids          # each once, in creation order


async def test_without_limit_processes_everything(client, db_session, make_user, authenticate_as, monkeypatch):
    eng, ids, seen = await _setup(db_session, make_user, monkeypatch)
    authenticate_as(await make_user(role="admin"))
    body = (await client.post(f"/attack/engagement/{eng.id}/suggest", json={})).json()
    assert body["total"] == 3 and body["next_offset"] is None and sorted(seen) == sorted(ids)
