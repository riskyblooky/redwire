"""End-to-end tests for ``routers/findings.py`` core CRUD + validation.

Drives the real handlers through the httpx ``client`` fixture with a
``get_current_user`` override installed by ``authenticate_as``. Engagement,
engagement-role and assignment rows are built directly on ``db_session`` via
the local helpers below so the RBAC path (``check_engagement_permission``)
is exercised for real, not stubbed.

Coverage:
  * POST /findings — admin create (role bypass) → 201, then read-back via
    GET /findings/{id}; that a create writes an ``activity_logs`` row.
  * POST /findings — assigned operator whose engagement role carries
    ``finding_create`` → 201 (real permission grant), and an operator with
    no assignment → 403.
  * PUT /findings/{id} — admin update of severity/status → 200.
  * Validation — bad severity enum → 422; missing required title /
    description → 422; cvss_score out of [0,10] bounds → 422.
  * GET /findings/{id} — unknown id → 404.

The finding create path fans out into ``create_activity_log`` (which itself
commits, runs the automation engine, and broadcasts). The savepoint harness
in conftest tolerates those inner commits; no automation rules exist in the
fresh schema so ``evaluate_rules`` is a no-op.
"""

from __future__ import annotations

import uuid

import pytest

from sqlalchemy import func, select

from models.engagement import Engagement
from models.engagement_role import EngagementRole
from models.permission import EngagementRolePermissions
from models.associations import EngagementAssignment
from models.finding import Finding
from models.discussion import ActivityLog


# ── local setup helpers ──────────────────────────────────────────────


async def _make_engagement(db, name="Test Engagement") -> Engagement:
    eng = Engagement(
        id=str(uuid.uuid4()),
        name=name,
        client_name="ACME Corp",
        engagement_type="external_pentest",
    )
    db.add(eng)
    await db.flush()
    return eng


async def _assign_user(db, user, engagement, permissions: list[str]) -> EngagementRole:
    """Create an engagement role carrying ``permissions`` and assign ``user``
    to ``engagement`` under it — the shape ``check_engagement_permission``
    resolves through (assignment → role → permission set)."""
    role = EngagementRole(
        id=str(uuid.uuid4()),
        name=f"role_{uuid.uuid4().hex[:8]}",
        description="test role",
    )
    db.add(role)
    await db.flush()
    db.add(EngagementRolePermissions(role_id=role.id, permissions=list(permissions)))
    db.add(
        EngagementAssignment(
            user_id=user.id, engagement_id=engagement.id, role_id=role.id
        )
    )
    await db.flush()
    return role


def _finding_payload(engagement_id: str, **overrides) -> dict:
    payload = {
        "engagement_id": engagement_id,
        "title": "SQL Injection in login form",
        "description": "The username field is concatenated into a raw query.",
        "severity": "HIGH",
        "cvss_score": 8.6,
    }
    payload.update(overrides)
    return payload


# ── create: admin happy path + read-back + activity log ──────────────


async def test_admin_create_finding_then_read_back(
    client, db_session, make_user, authenticate_as
):
    admin = await make_user(role="admin", username="find_admin")
    eng = await _make_engagement(db_session)
    authenticate_as(admin)

    resp = await client.post("/findings", json=_finding_payload(eng.id))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["title"] == "SQL Injection in login form"
    assert body["severity"] == "HIGH"
    assert body["status"] == "OPEN"  # server default
    assert body["engagement_id"] == eng.id
    assert body["created_by"] == admin.id
    finding_id = body["id"]

    # Read it back through GET /findings/{id}
    got = await client.get(f"/findings/{finding_id}")
    assert got.status_code == 200, got.text
    assert got.json()["id"] == finding_id
    assert got.json()["cvss_score"] == 8.6


async def test_create_finding_writes_activity_log(
    client, db_session, make_user, authenticate_as
):
    admin = await make_user(role="admin", username="find_admin_log")
    eng = await _make_engagement(db_session)
    authenticate_as(admin)

    resp = await client.post(
        "/findings", json=_finding_payload(eng.id, title="Audit-me finding")
    )
    assert resp.status_code == 201, resp.text
    finding_id = resp.json()["id"]

    row = (
        await db_session.execute(
            select(ActivityLog).where(
                ActivityLog.resource_type == "finding",
                ActivityLog.resource_id == finding_id,
                ActivityLog.action == "created_finding",
            )
        )
    ).scalar_one_or_none()
    assert row is not None, "create_finding should persist a created_finding activity log"
    assert row.user_id == admin.id
    assert row.engagement_id == eng.id
    assert row.resource_name == "Audit-me finding"


# ── create: RBAC via engagement assignment ───────────────────────────


async def test_assigned_operator_with_permission_can_create(
    client, db_session, make_user, authenticate_as
):
    op = await make_user(role="operator", username="find_op_ok")
    eng = await _make_engagement(db_session)
    await _assign_user(db_session, op, eng, permissions=["finding_create"])
    authenticate_as(op)

    resp = await client.post("/findings", json=_finding_payload(eng.id))
    assert resp.status_code == 201, resp.text
    assert resp.json()["created_by"] == op.id


async def test_operator_without_assignment_forbidden(
    client, db_session, make_user, authenticate_as
):
    op = await make_user(role="operator", username="find_op_denied")
    eng = await _make_engagement(db_session)
    # No assignment → check_engagement_permission returns False.
    authenticate_as(op)

    resp = await client.post("/findings", json=_finding_payload(eng.id))
    assert resp.status_code == 403
    assert "finding_create" in resp.json()["detail"]


async def test_assigned_operator_without_create_perm_forbidden(
    client, db_session, make_user, authenticate_as
):
    # Assigned, but the role only grants view — create must still 403.
    op = await make_user(role="operator", username="find_op_viewonly")
    eng = await _make_engagement(db_session)
    await _assign_user(db_session, op, eng, permissions=["finding_view"])
    authenticate_as(op)

    resp = await client.post("/findings", json=_finding_payload(eng.id))
    assert resp.status_code == 403


# ── update ───────────────────────────────────────────────────────────


async def test_admin_update_finding_severity_and_status(
    client, db_session, make_user, authenticate_as
):
    admin = await make_user(role="admin", username="find_admin_upd")
    eng = await _make_engagement(db_session)
    authenticate_as(admin)

    created = await client.post("/findings", json=_finding_payload(eng.id))
    assert created.status_code == 201, created.text
    finding_id = created.json()["id"]

    resp = await client.put(
        f"/findings/{finding_id}",
        json={"severity": "CRITICAL", "status": "VERIFIED"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["severity"] == "CRITICAL"
    assert body["status"] == "VERIFIED"


# ── validation ───────────────────────────────────────────────────────


async def test_create_finding_bad_severity_422(
    client, db_session, make_user, authenticate_as
):
    admin = await make_user(role="admin", username="find_admin_badsev")
    eng = await _make_engagement(db_session)
    authenticate_as(admin)

    resp = await client.post(
        "/findings", json=_finding_payload(eng.id, severity="SUPER_BAD")
    )
    assert resp.status_code == 422


async def test_create_finding_missing_required_fields_422(
    client, db_session, make_user, authenticate_as
):
    admin = await make_user(role="admin", username="find_admin_missing")
    eng = await _make_engagement(db_session)
    authenticate_as(admin)

    # Missing title and description (both required, min_length=1).
    resp = await client.post(
        "/findings",
        json={"engagement_id": eng.id, "severity": "LOW"},
    )
    assert resp.status_code == 422


async def test_create_finding_cvss_out_of_bounds_422(
    client, db_session, make_user, authenticate_as
):
    admin = await make_user(role="admin", username="find_admin_cvss")
    eng = await _make_engagement(db_session)
    authenticate_as(admin)

    resp = await client.post(
        "/findings", json=_finding_payload(eng.id, cvss_score=42.0)
    )
    assert resp.status_code == 422


# ── not found ────────────────────────────────────────────────────────


async def test_get_finding_not_found_404(client, make_user, authenticate_as):
    admin = await make_user(role="admin", username="find_admin_404")
    authenticate_as(admin)

    resp = await client.get(f"/findings/{uuid.uuid4()}")
    assert resp.status_code == 404
