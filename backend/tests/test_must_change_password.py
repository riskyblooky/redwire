"""must_change_password is enforced by the backend, not just the UI modal:
a flagged user's token reaches only /auth/me, /users/me, force-change and
logout."""

from __future__ import annotations

import pytest

from auth.jwt import create_access_token


@pytest.fixture
def bearer(monkeypatch):
    import auth.dependencies as deps
    monkeypatch.setattr(deps, "is_token_blacklisted", lambda _t: False)
    return lambda user: {"Authorization": f"Bearer {create_access_token({'sub': user.id})}"}


async def test_flagged_user_is_limited(client, db_session, make_user, bearer):
    user = await make_user(role="admin")
    user.must_change_password = True
    await db_session.flush()
    h = bearer(user)
    assert (await client.get("/auth/me", headers=h)).status_code == 200
    assert (await client.get("/users/me", headers=h)).status_code == 200
    for method, path in (("get", "/engagements"), ("get", "/admin/users"), ("get", "/findings")):
        r = await getattr(client, method)(path, headers=h)
        assert r.status_code == 403 and r.json()["detail"] == "Password change required", path
    # force-change is reachable (wrong current password → its own 401, not the gate's 403)
    r = await client.post("/auth/force-change-password", headers=h,
                          json={"current_password": "wrong-password", "new_password": "N3w-Passw0rd!x"})
    assert r.status_code == 401


async def test_unflagged_user_unaffected(client, make_user, bearer):
    user = await make_user(role="admin")
    assert (await client.get("/engagements", headers=bearer(user))).status_code == 200
