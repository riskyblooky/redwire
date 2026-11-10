"""Regression tests for the 11/8-review low-severity fixes: widget scoping of
child tables, notify_role visibility, plugin lookup gate, engagement-less
activity logs, read-only-admin reads, markdown upload write gate, evidence
replace/VERIFIED rules, chain-link audit entries, version restore of score
fields, SAML JIT usernames, retention pruning and the ws_bus reconnect."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from models.discussion import ActivityLog
from models.evidence import Evidence
from models.finding import FindingStatus
from tests.test_authz_boundaries import _assign, _make_engagement, _make_engagement_role, _make_finding


@pytest.fixture(autouse=True)
def _no_minio(monkeypatch):
    from utils.storage import storage_service
    uploaded = {}

    async def fake_upload(content, name, content_type=None):
        uploaded[name] = content_type
        return name
    monkeypatch.setattr(storage_service, "upload_file", fake_upload)
    return uploaded


@pytest.fixture
def shared_session(db_session):
    class _Ctx:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, *exc):
            return False
    return lambda: _Ctx()


# ── 1. widget scope on child tables ──────────────────────────────────────

@pytest.mark.parametrize("table,parent", [("spray_results", "spray_campaigns"), ("comments", "threads")])
def test_widget_scope_child_tables(table, parent):
    from routers.dashboard_widgets import _TABLE_MAP, _apply_assignment_scope
    q = _apply_assignment_scope(select(_TABLE_MAP[table]), SimpleNamespace(table=table), SimpleNamespace(id="u1"))
    sql = str(q)
    assert parent in sql and "engagement_assignments" in sql


# ── 2. notify_role honours engagement visibility ─────────────────────────

async def test_notify_role_skips_users_who_cannot_see(db_session, make_user, monkeypatch):
    from utils import automation_engine
    import utils.collaboration as collab
    sent = []

    async def fake_notify(db, user_id, **kw):
        sent.append(user_id)
    monkeypatch.setattr(collab, "create_notification", fake_notify)
    eng = await _make_engagement(db_session)
    member = await make_user(role="operator")
    outsider = await make_user(role="operator")
    await _assign(db_session, member, eng, await _make_engagement_role(db_session, ["engagement_view"]))
    await automation_engine._execute_notify_role(
        db_session, {"role": "operator"}, {"engagement_id": eng.id}, "r")
    assert member.id in sent and outsider.id not in sent


# ── 3. plugin free-text lookups need asset_create somewhere ──────────────

@pytest.mark.parametrize("module", ["plugins.servicenow_cmdb.router", "plugins.shodan_enricher.router"])
async def test_plugin_lookup_gate(module, db_session, make_user, shared_session, monkeypatch):
    import importlib
    from fastapi import HTTPException
    mod = importlib.import_module(module)
    monkeypatch.setattr(mod, "AsyncSessionLocal", shared_session)
    viewer = await make_user(role="operator")
    await _assign(db_session, viewer, await _make_engagement(db_session),
                  await _make_engagement_role(db_session, ["asset_view"]))
    with pytest.raises(HTTPException) as e:
        await mod.require_lookup_access(viewer)
    assert e.value.status_code == 403
    doer = await make_user(role="operator")
    await _assign(db_session, doer, await _make_engagement(db_session),
                  await _make_engagement_role(db_session, ["asset_create"]))
    await mod.require_lookup_access(doer)  # no raise


# ── 4. engagement-less activity logs aren't broadcast ────────────────────

async def test_activity_log_without_engagement_not_broadcast(db_session, make_user, monkeypatch):
    from utils import collaboration
    calls = []

    async def fake_broadcast(*a, **kw):
        calls.append(a)
    monkeypatch.setattr(collaboration.manager, "broadcast_to_resource", fake_broadcast)
    u = await make_user()
    await collaboration.create_activity_log(db_session, engagement_id=None, user_id=u.id,
                                            action="regenerated_recovery_codes", resource_type="user",
                                            resource_id=u.id)
    assert calls == []
    rows = (await db_session.execute(select(ActivityLog).where(ActivityLog.user_id == u.id))).scalars().all()
    assert len(rows) == 1  # still audited


# ── 5. read-only admin can use the read routes ───────────────────────────

async def test_ro_admin_reads(client, db_session, make_user, authenticate_as):
    eng = await _make_engagement(db_session)
    f = await _make_finding(db_session, eng)
    ev = Evidence(id=str(uuid.uuid4()), finding_id=f.id, engagement_id=eng.id, filename="x.png",
                  original_filename="x.png", file_path="x.png", file_size=1, mime_type="image/png")
    db_session.add(ev)
    await db_session.flush()
    authenticate_as(await make_user(role="read_only_admin"))
    assert (await client.post(f"/evidence/{ev.id}/download-token")).status_code == 200
    assert (await client.get("/imports/scans", params={"engagement_id": eng.id})).status_code == 200


# ── 6. markdown image upload needs a write permission ────────────────────

async def test_markdown_upload_needs_write(client, db_session, make_user, authenticate_as):
    eng = await _make_engagement(db_session)
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    for perms, ok in ((["engagement_view", "finding_view"], False), (["engagement_view", "finding_edit"], True)):
        u = await make_user(role="operator")
        await _assign(db_session, u, eng, await _make_engagement_role(db_session, perms))
        authenticate_as(u)
        r = await client.post("/markdown-images", data={"engagement_id": eng.id},
                              files={"file": ("a.png", png, "image/png")})
        assert (r.status_code == 403) is (not ok), (perms, r.status_code, r.text)


# ── 7/8. evidence replace-file + VERIFIED findings ───────────────────────

async def _evidence(db, finding, eng, name="shot.png"):
    ev = Evidence(id=str(uuid.uuid4()), finding_id=finding.id if finding else None, engagement_id=eng.id,
                  filename=name, original_filename=name, file_path=name, file_size=1, mime_type="image/png")
    db.add(ev)
    await db.flush()
    return ev


async def test_replace_file_ignores_client_mime(client, db_session, make_user, authenticate_as, _no_minio):
    eng = await _make_engagement(db_session)
    ev = await _evidence(db_session, await _make_finding(db_session, eng), eng, f"{uuid.uuid4()}.png")
    authenticate_as(await make_user(role="admin"))
    r = await client.put(f"/evidence/{ev.id}/replace-file",
                         files={"file": ("x.png", b"<script>alert(1)</script>", "text/html")})
    assert r.status_code == 200, r.text
    assert r.json()["mime_type"] == "image/png" and _no_minio[ev.filename] == "image/png"


async def test_no_new_evidence_on_verified_finding(client, db_session, make_user, authenticate_as):
    eng = await _make_engagement(db_session)
    f = await _make_finding(db_session, eng, status=FindingStatus.VERIFIED)
    authenticate_as(await make_user(role="admin"))
    r = await client.post(f"/findings/{f.id}/evidence", files={"file": ("a.txt", b"x", "text/plain")})
    assert r.status_code == 409


async def test_no_relink_into_verified_finding(client, db_session, make_user, authenticate_as):
    eng = await _make_engagement(db_session)
    verified = await _make_finding(db_session, eng, status=FindingStatus.VERIFIED)
    ev = await _evidence(db_session, None, eng)
    authenticate_as(await make_user(role="admin"))
    r = await client.patch(f"/evidence/{ev.id}", json={"finding_id": verified.id})
    assert r.status_code == 409, r.text


async def test_evidence_change_details_include_link(client, db_session, make_user, authenticate_as):
    eng = await _make_engagement(db_session)
    f = await _make_finding(db_session, eng)
    ev = await _evidence(db_session, None, eng)
    authenticate_as(await make_user(role="admin"))
    r = await client.patch(f"/evidence/{ev.id}", json={"finding_id": f.id, "classification_level": "CUI"})
    assert r.status_code == 200, r.text
    log = (await db_session.execute(select(ActivityLog).where(
        ActivityLog.resource_id == ev.id, ActivityLog.action == "updated_evidence"))).scalars().one()
    assert "link" in log.details and "classification" in log.details


# ── 9. chain-link edits and removals are audited ─────────────────────────

async def test_chain_link_update_and_delete_logged(client, db_session, make_user, authenticate_as):
    from tests.test_router_chain_links import _make_testcase
    authenticate_as(await make_user(role="admin"))
    eng = await _make_engagement(db_session)
    f = await _make_finding(db_session, eng)
    tc = await _make_testcase(db_session, eng.id)
    r = await client.post(f"/engagements/{eng.id}/chain-links", json={
        "source_type": "finding", "source_id": f.id, "target_type": "testcase", "target_id": tc.id})
    link_id = r.json()["id"]
    r = await client.patch(f"/engagements/{eng.id}/chain-links/{link_id}", json={"note": "n2"})
    assert r.status_code == 200 and r.json()["note"] == "n2", r.text
    assert (await client.delete(f"/engagements/{eng.id}/chain-links/{link_id}")).status_code == 204
    actions = set((await db_session.execute(select(ActivityLog.action).where(
        ActivityLog.engagement_id == eng.id))).scalars().all())
    assert {"linked_chain", "updated_chain", "unlinked_chain"} <= actions


# ── 10. version restore keeps score inputs consistent ────────────────────

def test_score_fields_are_versioned():
    from utils.versioning import FINDING_VERSIONED_FIELDS
    assert {"score_model", "score_inputs"} <= set(FINDING_VERSIONED_FIELDS)


async def test_legacy_snapshot_restore_drops_stale_inputs(client, db_session, make_user, authenticate_as):
    from models.version_history import VersionHistory
    eng = await _make_engagement(db_session)
    f = await _make_finding(db_session, eng, cvss_vector="NEW", cvss_score=9.0,
                            score_model="cvss31", score_inputs={"AV": "N"})
    v = VersionHistory(id=str(uuid.uuid4()), entity_type="finding", entity_id=f.id, version=1,
                       snapshot={"cvss_vector": "OLD", "cvss_score": 3.0}, changed_fields=["cvss_vector"])
    db_session.add(v)
    await db_session.flush()
    authenticate_as(await make_user(role="admin"))
    r = await client.post(f"/findings/{f.id}/versions/{v.id}/restore")
    assert r.status_code == 200, r.text
    await db_session.refresh(f)
    assert f.cvss_vector == "OLD" and f.score_model is None and f.score_inputs is None


# ── 14. SAML JIT usernames ───────────────────────────────────────────────

async def test_saml_jit_username(db_session, make_user):
    from routers.auth import _saml_jit_username
    await make_user(username="jane.doe")
    assert await _saml_jit_username(db_session, "Jane.Doe") == "jane.doe-2"
    assert await _saml_jit_username(db_session, "ａｌｉｃｅ") == "alice"
    assert await _saml_jit_username(db_session, "bob smith/../x") == "bob-smith-..-x"
    assert await _saml_jit_username(db_session, "!!") == "saml-user"


# ── 18. retention ────────────────────────────────────────────────────────

async def test_retention_prunes_old_rows_only(db_session, make_user, monkeypatch):
    from models.activity_ping import ActivityPing
    from models.notification import Notification
    from utils.retention import prune_once
    monkeypatch.delenv("ACTIVITY_LOG_RETENTION_DAYS", raising=False)
    u = await make_user()
    old = datetime.utcnow() - timedelta(days=400)
    db_session.add_all([
        ActivityPing(user_id=u.id, resource_type="finding", resource_id="r", created_at=old),
        ActivityPing(user_id=u.id, resource_type="finding", resource_id="r"),
        Notification(user_id=u.id, event_type="x", title="read-old", is_read=True, created_at=old),
        Notification(user_id=u.id, event_type="x", title="unread-old", is_read=False, created_at=old),
        ActivityLog(user_id=u.id, action="a", resource_type="user", resource_id=u.id, created_at=old),
    ])
    await db_session.flush()
    await prune_once(db_session)
    pings = (await db_session.execute(select(ActivityPing).where(ActivityPing.user_id == u.id))).scalars().all()
    notes = (await db_session.execute(select(Notification.title).where(Notification.user_id == u.id))).scalars().all()
    logs = (await db_session.execute(select(ActivityLog).where(ActivityLog.user_id == u.id))).scalars().all()
    assert len(pings) == 1 and notes == ["unread-old"] and len(logs) == 1


def test_evict_stale():
    from utils.retention import evict_stale
    cache = {f"k{i}": 0.0 for i in range(20)} | {"fresh": 99.0}
    evict_stale(cache, now=100.0, max_age=30.0, max_size=10)
    assert cache == {"fresh": 99.0}


# ── 16. ws_bus retries Redis ─────────────────────────────────────────────

async def test_ws_bus_retries_until_redis_is_up(monkeypatch):
    from utils import ws_bus as wb
    monkeypatch.setenv("WS_FANOUT", "true")
    bus = wb.WsBus()
    attempts = []
    activated = asyncio.Event()

    async def fake_connect():
        attempts.append(1)
        return object() if len(attempts) >= 3 else None

    async def fake_activate(client):
        bus._redis = client
        activated.set()

    monkeypatch.setattr(bus, "_connect", fake_connect)
    monkeypatch.setattr(bus, "_activate", fake_activate)
    monkeypatch.setattr(wb, "_RETRY_BASE_S", 0.0)
    await bus.start()
    await asyncio.wait_for(activated.wait(), 2)
    assert len(attempts) == 3 and bus.active
    bus._tasks = []
