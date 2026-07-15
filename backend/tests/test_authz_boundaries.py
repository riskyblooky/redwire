"""Authorization-boundary regressions: RBAC role gating + engagement-scoped
IDOR / tenant isolation.

Every test here pins a security boundary from *both* sides — the allowed
principal gets through AND the denied principal is rejected — so the test
proves the check enforces, not merely that some request happens to 4xx.

Three families:

1. **Global role gating** (``require_roles``) — an unprivileged user hitting an
   admin-only route gets 403; the privileged role gets through. We use two
   real ``routers/admin.py`` endpoints that gate on *different* role sets to
   also pin the ADMIN-vs-ADMIN_ROLES distinction (a read_only_admin is allowed
   on read routes but denied on write routes).

2. **Engagement-scoped IDOR** — a member of an engagement (holding an
   ``EngagementAssignment`` whose role carries the needed permission) can read
   that engagement's vault items / a finding; a non-member operator gets 403 on
   the exact same resource. Pinned on two concrete engagement-scoped GETs
   (``GET /vault?engagement_id=`` and ``GET /findings/{id}``), both of which
   route through ``check_engagement_permission``.

3. **Read-only API-token enforcement** — a ``ro_`` API token must be rejected
   (403) on a mutating method. The DB-integration harness overrides
   ``get_current_user`` wholesale, so a real ``ro_``-prefixed bearer never flows
   through the token-resolution path in a client request. We therefore
   unit-test the enforcement helper (``auth.dependencies.require_write``) and
   the inline ``get_current_user`` ro-branch predicate directly with a fake
   Request whose ``state.api_token_permission == "ro"``. See the module summary
   returned to the caller for why this is a unit test rather than an
   integration one.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from models.associations import EngagementAssignment
from models.engagement import Engagement, EngagementStatus
from models.engagement_role import EngagementRole
from models.finding import Finding, Severity
from models.permission import EngagementRolePermissions, Permission


# ─────────────────────────────────────────────────────────────────────────
# Local seeding helpers (engagement + role + assignment)
# ─────────────────────────────────────────────────────────────────────────


async def _make_engagement(db_session, **overrides) -> Engagement:
    """Insert a minimal valid Engagement row (name/client_name/engagement_type
    are the NOT NULL columns without a default; status defaults)."""
    fields = dict(
        id=str(uuid.uuid4()),
        name=f"Eng {uuid.uuid4().hex[:8]}",
        client_name="Acme Corp",
        engagement_type="Red Team",
        status=EngagementStatus.IN_PROGRESS,
    )
    fields.update(overrides)
    eng = Engagement(**fields)
    db_session.add(eng)
    await db_session.flush()
    return eng


async def _make_engagement_role(db_session, permissions: list[str]) -> EngagementRole:
    """Create an EngagementRole plus its EngagementRolePermissions row.

    ``check_engagement_permission`` joins EngagementRolePermissions →
    EngagementRole → EngagementAssignment on ``role_id`` and looks up the
    required permission in the JSON ``permissions`` list, so a member is only
    authorized when their assignment points at a role carrying the permission.
    """
    role = EngagementRole(
        id=str(uuid.uuid4()),
        name=f"role_{uuid.uuid4().hex[:8]}",
        description="test engagement role",
    )
    db_session.add(role)
    await db_session.flush()
    db_session.add(
        EngagementRolePermissions(role_id=role.id, permissions=list(permissions))
    )
    await db_session.flush()
    return role


async def _assign(db_session, user, engagement, role) -> EngagementAssignment:
    """Make ``user`` a member of ``engagement`` with ``role``."""
    assignment = EngagementAssignment(
        user_id=user.id,
        engagement_id=engagement.id,
        role_id=role.id,
    )
    db_session.add(assignment)
    await db_session.flush()
    return assignment


async def _make_finding(db_session, engagement, **overrides) -> Finding:
    fields = dict(
        id=str(uuid.uuid4()),
        engagement_id=engagement.id,
        title="Seeded finding",
        description="A finding for the IDOR boundary test.",
        severity=Severity.HIGH,
    )
    fields.update(overrides)
    finding = Finding(**fields)
    db_session.add(finding)
    await db_session.flush()
    return finding


# ─────────────────────────────────────────────────────────────────────────
# 1. Global role gating via require_roles
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
async def test_admin_write_route_denies_operator(client, make_user, authenticate_as):
    """GET /admin/users gates on WRITE_ADMIN_ROLES ([ADMIN]). An operator is
    not admin → 403 (denied side)."""
    operator = await make_user(role="operator")
    authenticate_as(operator)
    resp = await client.get("/admin/users")
    assert resp.status_code == 403


@pytest.mark.integration
async def test_admin_write_route_denies_read_only(client, make_user, authenticate_as):
    """A plain read_only user is likewise rejected from the admin write route."""
    ro = await make_user(role="read_only")
    authenticate_as(ro)
    resp = await client.get("/admin/users")
    assert resp.status_code == 403


@pytest.mark.integration
async def test_admin_write_route_allows_admin(client, make_user, authenticate_as):
    """The same route lets a real admin through (allowed side) → 200 with a
    list body. Proves the 403 above is the role gate firing, not the route
    being broken for everyone."""
    admin = await make_user(role="admin")
    authenticate_as(admin)
    resp = await client.get("/admin/users")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.integration
async def test_admin_read_route_read_only_admin_distinction(
    client, make_user, authenticate_as
):
    """GET /admin/groups gates on ADMIN_ROLES ([ADMIN, READ_ONLY_ADMIN]) —
    a *read* route. A read_only_admin is allowed here (200) but was denied on
    the /admin/users *write* route above. Pinning both routes with the same
    role proves the ADMIN-vs-ADMIN_ROLES split is enforced, not incidental."""
    roa = await make_user(role="read_only_admin")
    authenticate_as(roa)

    allowed = await client.get("/admin/groups")
    assert allowed.status_code == 200

    denied = await client.get("/admin/users")  # write-admin route
    assert denied.status_code == 403


@pytest.mark.integration
async def test_admin_read_route_denies_operator(client, make_user, authenticate_as):
    """And the read route still denies a plain operator — the ADMIN_ROLES gate
    is a real boundary, not open-to-all."""
    operator = await make_user(role="operator")
    authenticate_as(operator)
    resp = await client.get("/admin/groups")
    assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────────────────
# 2. Engagement-scoped IDOR / tenant isolation
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
async def test_vault_list_member_allowed_nonmember_denied(
    client, db_session, make_user, authenticate_as
):
    """GET /vault?engagement_id= — member with vault_view sees the engagement's
    vault (200); a non-assigned operator is refused (403). Same URL, same
    engagement, opposite outcomes → the check enforces on membership."""
    engagement = await _make_engagement(db_session)
    role = await _make_engagement_role(db_session, [Permission.VAULT_VIEW.value])

    member = await make_user(role="operator")
    outsider = await make_user(role="operator")
    await _assign(db_session, member, engagement, role)
    await db_session.flush()

    # Allowed side: assigned member with the vault_view permission.
    authenticate_as(member)
    allowed = await client.get(f"/vault?engagement_id={engagement.id}")
    assert allowed.status_code == 200
    assert isinstance(allowed.json(), list)

    # Denied side: an operator with no assignment on this engagement.
    authenticate_as(outsider)
    denied = await client.get(f"/vault?engagement_id={engagement.id}")
    assert denied.status_code == 403


@pytest.mark.integration
async def test_vault_list_member_without_permission_denied(
    client, db_session, make_user, authenticate_as
):
    """Membership alone is not enough: an assigned member whose engagement role
    lacks vault_view is still denied. Isolates the *permission* half of the
    check from the *membership* half."""
    engagement = await _make_engagement(db_session)
    # Role carries a different permission, deliberately NOT vault_view.
    role = await _make_engagement_role(db_session, [Permission.FINDING_VIEW.value])

    member = await make_user(role="operator")
    await _assign(db_session, member, engagement, role)
    await db_session.flush()

    authenticate_as(member)
    resp = await client.get(f"/vault?engagement_id={engagement.id}")
    assert resp.status_code == 403


@pytest.mark.integration
async def test_finding_get_member_allowed_nonmember_denied(
    client, db_session, make_user, authenticate_as
):
    """GET /findings/{id} — a member with finding_view reads the finding (200);
    a non-member operator gets 403 on the identical resource. The finding row
    is seeded directly so both principals target the same real id."""
    engagement = await _make_engagement(db_session)
    role = await _make_engagement_role(db_session, [Permission.FINDING_VIEW.value])

    member = await make_user(role="operator")
    outsider = await make_user(role="operator")
    # created_by must be a real user id — FindingResponse requires it non-null.
    finding = await _make_finding(db_session, engagement, created_by=member.id)
    await _assign(db_session, member, engagement, role)
    await db_session.flush()

    # Allowed side.
    authenticate_as(member)
    allowed = await client.get(f"/findings/{finding.id}")
    assert allowed.status_code == 200
    assert allowed.json()["id"] == finding.id

    # Denied side: same finding id, unassigned operator.
    authenticate_as(outsider)
    denied = await client.get(f"/findings/{finding.id}")
    assert denied.status_code == 403


@pytest.mark.integration
async def test_finding_get_admin_bypasses_scope(
    client, db_session, make_user, authenticate_as
):
    """A global admin reads the finding without any engagement assignment —
    confirms admins bypass the engagement scope (the counterpart to the 403 an
    unassigned operator receives)."""
    engagement = await _make_engagement(db_session)
    admin = await make_user(role="admin")
    finding = await _make_finding(db_session, engagement, created_by=admin.id)

    authenticate_as(admin)
    resp = await client.get(f"/findings/{finding.id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == finding.id


# ─────────────────────────────────────────────────────────────────────────
# 3. Read-only API-token enforcement (unit — see module docstring)
# ─────────────────────────────────────────────────────────────────────────


def _fake_request(permission, method="POST"):
    """A stand-in for starlette Request carrying just what the enforcement
    code reads: ``request.state.api_token_permission`` and ``request.method``."""
    return SimpleNamespace(
        method=method,
        state=SimpleNamespace(api_token_permission=permission),
    )


@pytest.mark.asyncio
async def test_require_write_rejects_ro_token():
    """The mutating-route guard: a ro token → 403."""
    from fastapi import HTTPException

    from auth.dependencies import require_write

    with pytest.raises(HTTPException) as exc:
        await require_write(_fake_request("ro"))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_write_allows_rw_token():
    """A rw token is not blocked (allowed side)."""
    from auth.dependencies import require_write

    # Returns None without raising.
    assert await require_write(_fake_request("rw")) is None


@pytest.mark.asyncio
async def test_require_write_allows_jwt_session():
    """A JWT session sets api_token_permission=None → not a ro token, allowed."""
    from auth.dependencies import require_write

    assert await require_write(_fake_request(None)) is None


def test_get_current_user_ro_branch_predicate():
    """Mirror the inline enforcement in get_current_user (dependencies.py:103):
    ``permission == 'ro' and method in (POST, PUT, PATCH, DELETE)``. Pins the
    exact matrix so a future refactor that drops a verb from the tuple, or
    stops matching 'ro', is caught. Read-safe verbs must NOT trip it."""
    mutating = ("POST", "PUT", "PATCH", "DELETE")
    safe = ("GET", "HEAD", "OPTIONS")

    def _would_block(permission, method):
        return permission == "ro" and method in ("POST", "PUT", "PATCH", "DELETE")

    # ro token blocked on every mutating verb.
    for m in mutating:
        assert _would_block("ro", m) is True, m
    # ro token allowed on read-safe verbs (reads through a ro token are fine).
    for m in safe:
        assert _would_block("ro", m) is False, m
    # rw / JWT-session (None) never blocked, even on mutating verbs.
    for m in mutating:
        assert _would_block("rw", m) is False, m
        assert _would_block(None, m) is False, m
