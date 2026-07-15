"""Smoke tests for the shared test harness itself (conftest.py).

If these fail, the DB-integration fixtures are broken and every integration
test built on them is suspect — so keep this file green first.
"""

from __future__ import annotations

import pytest

from tests.conftest import FakeDb, FakeScalarResult, make_fake_user


# ── pure-unit fakes ──────────────────────────────────────────────────────


async def test_fakedb_pops_queued_results_then_empties():
    db = FakeDb([FakeScalarResult("a"), FakeScalarResult(many=["x", "y"])])
    first = await db.execute("q1")
    assert first.scalar_one_or_none() == "a"
    second = await db.execute("q2")
    assert second.scalars().all() == ["x", "y"]
    # Drained → empty result, not an error.
    third = await db.execute("q3")
    assert third.scalar_one_or_none() is None


async def test_fakedb_records_writes():
    db = FakeDb()
    db.add(object())
    await db.commit()
    assert len(db.added) == 1
    assert db.commit_count == 1


def test_make_fake_user_uses_real_role_enum():
    from models.user import UserRole

    u = make_fake_user(role="admin")
    assert u.role is UserRole.ADMIN
    assert u.role.value == "admin"
    assert u.is_active is True


# ── DB-integration harness ───────────────────────────────────────────────


@pytest.mark.integration
async def test_db_session_roundtrips_a_user(db_session, make_user):
    from sqlalchemy import select

    from models.user import User

    user = await make_user(role="operator", username="roundtrip_alice")
    found = (
        await db_session.execute(select(User).where(User.username == "roundtrip_alice"))
    ).scalar_one_or_none()
    assert found is not None
    assert found.id == user.id


@pytest.mark.integration
async def test_transaction_rollback_isolates_tests(db_session):
    """This user must NOT leak into any other test — the outer transaction is
    rolled back on teardown. Paired with the test above, which uses the same
    username: if isolation were broken, one of them would hit a UNIQUE clash.
    """
    from models.user import User, UserRole
    import uuid

    db_session.add(
        User(
            id=str(uuid.uuid4()),
            username="roundtrip_alice",  # same name as the other test on purpose
            email="iso@test.local",
            hashed_password="x",
            role=UserRole.OPERATOR,
            is_active=True,
        )
    )
    await db_session.flush()


@pytest.mark.integration
async def test_health_endpoint_no_auth(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


@pytest.mark.integration
async def test_users_me_requires_auth(client):
    # No authenticate_as → HTTPBearer rejects with 403 (no credentials).
    resp = await client.get("/users/me")
    assert resp.status_code in (401, 403)


@pytest.mark.integration
async def test_users_me_returns_authenticated_user(client, make_user, authenticate_as):
    user = await make_user(role="admin", username="me_admin")
    authenticate_as(user)
    resp = await client.get("/users/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "me_admin"
    assert body["role"] == "admin"
