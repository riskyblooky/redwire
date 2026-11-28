"""The ``authenticate_as`` override (used by most of the suite) must refuse
and accept exactly as the real JWT path does, or a route could pass its
tests and fail for real users. Each case runs both ways and the outcomes
must match."""

from __future__ import annotations

import pytest


@pytest.fixture
def via(client, authenticate_as, monkeypatch):
    import auth.dependencies as deps
    import main
    from auth.jwt import create_access_token
    monkeypatch.setattr(deps, "is_token_blacklisted", lambda _t: False)

    async def _call(how, user, method, url):
        if how == "override":
            authenticate_as(user)
            return await client.request(method, url)
        main.app.dependency_overrides.pop(deps.get_current_user, None)
        token = create_access_token({"sub": user.id})
        return await client.request(method, url, headers={"Authorization": f"Bearer {token}"})
    return _call


@pytest.mark.parametrize("state,method,url", [
    ({}, "GET", "/users/me"),
    ({"is_active": False}, "GET", "/users/me"),
    ({"must_change_password": True}, "GET", "/users/me"),          # on the allowlist
    ({"must_change_password": True}, "GET", "/engagements"),        # refused until changed
    ({"must_change_password": True}, "POST", "/notifications/mark-all-read"),
])
async def test_override_matches_the_real_path(db_session, make_user, via, state, method, url):
    user = await make_user()
    for k, v in state.items():
        setattr(user, k, v)
    await db_session.commit()
    real = await via("jwt", user, method, url)
    over = await via("override", user, method, url)
    assert (over.status_code, over.json().get("detail") if over.status_code >= 400 else None) == \
           (real.status_code, real.json().get("detail") if real.status_code >= 400 else None)
