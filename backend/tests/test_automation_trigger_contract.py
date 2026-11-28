"""The rule editor's trigger catalogue (models.automation.TRIGGER_TYPES) is a
contract with the code that logs activity: every trigger it offers must fire
when its action happens through the API, and every field it offers for
conditions must be in that trigger's context. A trigger nothing fires, or a
field that is never set, is a rule that silently never runs (several catalog
triggers were like that until 1.7/1.8).

evaluate_rules is replaced with a recorder, so this checks the names and
contexts handed to the engine, not rule matching (test_match_condition_*)."""

from __future__ import annotations

import pytest

from tests.test_authz_boundaries import _make_engagement_role


@pytest.fixture
def fired(monkeypatch):
    from utils import automation_engine
    seen: list[tuple[str, dict]] = []

    async def record(db, trigger_type, context):
        seen.append((trigger_type, dict(context)))
    monkeypatch.setattr(automation_engine, "evaluate_rules", record)
    return seen


@pytest.fixture
def no_minio(monkeypatch):
    from utils.storage import storage_service

    async def fake_upload(content, name, content_type=None):
        return name
    monkeypatch.setattr(storage_service, "upload_file", fake_upload)


def _ok(r):
    assert r.status_code in (200, 201), (r.request.method, str(r.request.url), r.status_code, r.text)
    return r.json()


async def _drive_every_action(client, db_session, make_user):
    """One of each action the catalogue names, through the API."""
    eng = _ok(await client.post("/engagements", json={
        "name": "Trigger contract", "client_name": "c", "engagement_type": "Red Team",
        "start_date": "2027-01-01T00:00:00"}))
    eid = eng["id"]
    _ok(await client.put(f"/engagements/{eid}", json={"description": "edited"}))
    _ok(await client.put(f"/engagements/{eid}", json={"status": "IN_PROGRESS"}))

    role = await _make_engagement_role(db_session, ["engagement_view"])
    member = await make_user()
    await db_session.commit()
    _ok(await client.put(f"/engagements/{eid}", json={"assignments": [{"user_id": member.id, "role_id": role.id}]}))
    _ok(await client.put(f"/engagements/{eid}", json={"assignments": []}))

    fid = _ok(await client.post("/findings", json={
        "engagement_id": eid, "title": "f", "severity": "HIGH", "description": "d", "cvss_score": 7.5}))["id"]
    _ok(await client.put(f"/findings/{fid}", json={"title": "f2"}))
    _ok(await client.put(f"/findings/{fid}", json={"status": "IN_REVIEW"}))
    _ok(await client.post(f"/findings/{fid}/evidence", files={"file": ("a.txt", b"x", "text/plain")}))

    tid = _ok(await client.post("/testcases", json={
        "engagement_id": eid, "title": "tc", "category": "Recon", "description": "d"}))["id"]
    _ok(await client.put(f"/testcases/{tid}", json={"title": "tc2"}))
    _ok(await client.put(f"/testcases/{tid}", json={"is_executed": True}))

    aid = _ok(await client.post("/assets", json={
        "engagement_id": eid, "name": "dc01", "asset_type": "Server", "identifier": "10.1.2.3"}))["id"]
    _ok(await client.put(f"/assets/{aid}", json={"description": "edited"}))

    _ok(await client.post(f"/engagements/{eid}/notes", json={"title": "n", "content": "x"}))
    _ok(await client.post("/vault", json={
        "engagement_id": eid, "name": "v", "item_type": "Credential", "username": "u", "password": "p"}))

    cid = _ok(await client.post("/cleanup-artifacts", json={"engagement_id": eid, "title": "c", "artifact_type": "FILE"}))["id"]
    _ok(await client.patch(f"/cleanup-artifacts/{cid}", json={"description": "edited"}))
    _ok(await client.patch(f"/cleanup-artifacts/{cid}", json={"status": "CLEANED"}))

    thread = _ok(await client.post("/discussions/threads", json={
        "engagement_id": eid, "resource_type": "finding", "resource_id": fid, "title": "t"}))
    _ok(await client.post("/discussions/comments", json={"thread_id": thread["id"], "content": "hello"}))


async def test_every_catalog_trigger_fires_with_its_fields(client, db_session, make_user, authenticate_as, fired, no_minio):
    from models.automation import TRIGGER_TYPES

    authenticate_as(await make_user(role="admin"))
    await _drive_every_action(client, db_session, make_user)

    by_trigger: dict[str, list[dict]] = {}
    for name, ctx in fired:
        by_trigger.setdefault(name, []).append(ctx)

    missing = sorted(t for t in TRIGGER_TYPES if t != "manual" and t not in by_trigger)
    assert not missing, f"catalog triggers that never fired: {missing}"

    # A field is available where _match_condition looks: a top-level key,
    # or the post-update value in context["changes"].
    def has(ctx, field):
        return field in ctx or isinstance((ctx.get("changes") or {}).get(field), dict)

    lacking = {}
    for trigger, spec in TRIGGER_TYPES.items():
        for field in spec["fields"]:
            if trigger in by_trigger and not any(has(ctx, field) for ctx in by_trigger[trigger]):
                lacking.setdefault(trigger, []).append(field)
    assert not lacking, f"condition fields offered but never in the context: {lacking}"

    # And the status triggers match on the status they moved to.
    from utils.automation_engine import _match_condition
    for trigger, new in (("finding_status_changed", "IN_REVIEW"), ("engagement_status_changed", "IN_PROGRESS"),
                         ("cleanup_status_changed", "CLEANED")):
        ctx = by_trigger[trigger][-1]
        assert _match_condition({"field": "status", "operator": "equals", "value": new}, ctx), (trigger, ctx)
    ctx = by_trigger["created_finding"][-1]
    assert _match_condition({"field": "cvss_score", "operator": "gte", "value": "7"}, ctx)
    assert _match_condition({"field": "severity", "operator": "equals", "value": "high"}, ctx)


async def test_status_triggers_fire_only_on_a_transition(client, db_session, make_user, authenticate_as, fired):
    """Creating a finding, or editing it without touching status, must not
    fire finding_status_changed (it did once, matching "when Verified"
    rules on brand-new findings)."""
    from tests.test_authz_boundaries import _make_engagement

    authenticate_as(await make_user(role="admin"))
    eng = await _make_engagement(db_session)
    await db_session.commit()
    fid = _ok(await client.post("/findings", json={"engagement_id": eng.id, "title": "f", "severity": "LOW", "description": "d"}))["id"]
    _ok(await client.put(f"/findings/{fid}", json={"title": "renamed"}))
    _ok(await client.put(f"/findings/{fid}", json={"status": "OPEN"}))  # unchanged
    assert "finding_status_changed" not in [t for t, _ in fired]
    _ok(await client.put(f"/findings/{fid}", json={"status": "IN_REVIEW"}))
    changed = [c for t, c in fired if t == "finding_status_changed"]
    assert len(changed) == 1 and changed[0]["changes"]["status"] == {"old": "OPEN", "new": "IN_REVIEW"}
