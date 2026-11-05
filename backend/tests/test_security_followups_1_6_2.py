"""1.6.2 security follow-ups: engagement status transitions, deleted-engagement
audit logs, seed-revision watermark, runbook content freeze."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from models.auth_settings import AuthSetting
from models.discussion import ActivityLog
from models.engagement import Engagement, EngagementStatus
from models.engagement_role import EngagementRole
from models.group import Group
from models.permission import EngagementRolePermissions, GroupPermissions
from models.template_status import TemplateStatus
from models.testcase_template import TestCaseTemplate
from utils.engagement_status import transition_allowed

S = EngagementStatus


# ── Status transitions ─────────────────────────────────────────────────────

def test_transition_matrix():
    assert transition_allowed(S.PROPOSED, S.REPORTING)          # forward, any distance
    assert not transition_allowed(S.PROPOSED, S.COMPLETED)      # COMPLETED only from REPORTING
    assert transition_allowed(S.REPORTING, S.COMPLETED)
    assert transition_allowed(S.REPORTING, S.IN_PROGRESS)       # back one
    assert not transition_allowed(S.REPORTING, S.PLANNING)      # back two
    assert transition_allowed(S.SCOPING, S.ON_HOLD)
    assert transition_allowed(S.ON_HOLD, S.PROPOSED)
    assert not transition_allowed(S.ON_HOLD, S.COMPLETED)
    assert not transition_allowed(S.COMPLETED, S.REPORTING)
    assert transition_allowed(S.PLANNING, S.PLANNING)


async def _engagement(db, owner, status=S.IN_PROGRESS):
    eng = Engagement(id=str(uuid.uuid4()), name="Status Test", client_name="ACME",
                     engagement_type="external_pentest", status=status, created_by=owner.id)
    db.add(eng)
    await db.flush()
    return eng


async def test_non_admin_cannot_skip_to_completed(client, db_session, make_user, authenticate_as, monkeypatch):
    import auth.rbac as rbac
    import routers.engagements as eng_router

    async def _allow(*_a, **_k):
        return True
    monkeypatch.setattr(rbac, "check_engagement_permission", _allow)
    monkeypatch.setattr(eng_router, "check_engagement_permission", _allow, raising=False)

    op = await make_user(role="operator", username=f"st_op_{uuid.uuid4().hex[:6]}")
    eng = await _engagement(db_session, op, S.IN_PROGRESS)
    authenticate_as(op)

    bad = await client.put(f"/engagements/{eng.id}", json={"status": "COMPLETED"})
    assert bad.status_code == 409, bad.text
    assert "REPORTING" in bad.json()["detail"]

    ok = await client.put(f"/engagements/{eng.id}", json={"status": "REPORTING"})
    assert ok.status_code == 200, ok.text


async def test_admin_bypasses_transition_rules(client, db_session, make_user, authenticate_as):
    admin = await make_user(role="admin", username=f"st_ad_{uuid.uuid4().hex[:6]}")
    eng = await _engagement(db_session, admin, S.PROPOSED)
    authenticate_as(admin)
    resp = await client.put(f"/engagements/{eng.id}", json={"status": "COMPLETED"})
    assert resp.status_code == 200, resp.text


# ── Deleted-engagement audit logs ─────────────────────────────────────────

async def test_deleted_engagement_logs_survive_and_group(client, db_session, make_user, authenticate_as):
    admin = await make_user(role="admin", username=f"dl_ad_{uuid.uuid4().hex[:6]}")
    authenticate_as(admin)
    eng = await _engagement(db_session, admin)
    db_session.add(ActivityLog(engagement_id=eng.id, user_id=admin.id, action="created",
                               resource_type="finding", resource_id="f1", resource_name="SQLi"))
    await db_session.flush()

    resp = await client.delete(f"/engagements/{eng.id}")
    assert resp.status_code == 204, resp.text

    groups = (await client.get("/admin/deleted-engagement-logs")).json()
    mine = next(g for g in groups if g["engagement_id"] == eng.id)
    assert mine["engagement_name"] == "Status Test"
    assert mine["deleted_by"] == admin.username
    assert mine["log_count"] == 2

    rows = (await client.get(f"/admin/deleted-engagement-logs/{eng.id}")).json()
    assert [r["action"] for r in rows] == ["created", "deleted_engagement"]


async def test_deleted_engagement_logs_forbidden_for_operator(client, make_user, authenticate_as):
    op = await make_user(role="operator", username=f"dl_op_{uuid.uuid4().hex[:6]}")
    authenticate_as(op)
    assert (await client.get("/admin/deleted-engagement-logs")).status_code == 403


# ── Seed-revision watermark ───────────────────────────────────────────────

async def test_seed_revisions_apply_once_and_additively(db_session):
    from seed_permissions import SEED_REVISION_KEY, SEED_REVISIONS, apply_seed_revisions

    for name in ("Team Leads",):
        if not (await db_session.execute(select(Group).where(Group.name == name))).scalar_one_or_none():
            g = Group(name=name, description="t")
            db_session.add(g)
            await db_session.flush()
            db_session.add(GroupPermissions(group_id=g.id, permissions=["manage_users"]))
    role = (await db_session.execute(select(EngagementRole).where(EngagementRole.name == "Operator"))).scalar_one_or_none()
    if role is None:
        role = EngagementRole(name="Operator", description="t")
        db_session.add(role)
        await db_session.flush()
        db_session.add(EngagementRolePermissions(role_id=role.id, permissions=["finding_view"]))
    existing = await db_session.get(AuthSetting, SEED_REVISION_KEY)
    if existing:
        await db_session.delete(existing)
    await db_session.flush()

    latest = max(r["revision"] for r in SEED_REVISIONS)
    assert await apply_seed_revisions(db_session) == latest
    await db_session.flush()

    tl = (await db_session.execute(select(Group).where(Group.name == "Team Leads"))).scalar_one()
    tl_perms = (await db_session.execute(select(GroupPermissions).where(GroupPermissions.group_id == tl.id))).scalar_one()
    assert "manage_marking_profiles" in tl_perms.permissions
    assert "manage_users" in tl_perms.permissions  # untouched
    op_perms = (await db_session.execute(
        select(EngagementRolePermissions).where(EngagementRolePermissions.role_id == role.id))).scalar_one()
    assert "evidence_edit" in op_perms.permissions

    # An admin revokes it afterwards: a later boot must not re-grant it.
    tl_perms.permissions = [p for p in tl_perms.permissions if p != "manage_marking_profiles"]
    await db_session.flush()
    assert await apply_seed_revisions(db_session) == latest
    await db_session.flush()
    assert "manage_marking_profiles" not in tl_perms.permissions


# ── Runbook content freeze ────────────────────────────────────────────────

async def test_approved_runbook_applies_frozen_content(client, db_session, make_user, authenticate_as):
    from models.testcase import TestCase

    admin = await make_user(role="admin", username=f"rb_ad_{uuid.uuid4().hex[:6]}")
    authenticate_as(admin)
    tmpl = TestCaseTemplate(id=str(uuid.uuid4()), title="Kerberoast", category="Exploitation",
                            description="original body", steps="1. GetUserSPNs",
                            status=TemplateStatus.PUBLISHED, created_by=admin.id)
    db_session.add(tmpl)
    await db_session.flush()

    rb = await client.post("/runbooks", json={"name": "AD sweep", "items": [
        {"temp_key": "a", "template_id": tmpl.id, "sort_order": 0}]})
    assert rb.status_code == 201, rb.text
    rid = rb.json()["id"]
    appr = await client.post(f"/runbooks/{rid}/approve", json={})
    assert appr.status_code == 200, appr.text
    assert appr.json()["items"][0]["frozen_at"] is not None

    # Template is later unpublished and edited — the approved runbook is unaffected.
    tmpl.status = TemplateStatus.DRAFT
    tmpl.description = "tampered body"
    await db_session.flush()

    eng = await _engagement(db_session, admin)
    applied = await client.post(f"/runbooks/{rid}/apply/{eng.id}")
    assert applied.status_code == 201, applied.text
    tc = (await db_session.execute(select(TestCase).where(TestCase.engagement_id == eng.id))).scalar_one()
    assert tc.description == "original body"
