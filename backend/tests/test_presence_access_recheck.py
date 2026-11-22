"""Presence / engagement / user sockets re-check access while open, like
the live-edit sockets: losing engagement view or being deactivated closes
the socket (1008) instead of leaving it receiving events."""

from __future__ import annotations

import asyncio

import pytest

import database
import routers.websocket as wsmod
from auth.permissions import Permission
from tests.test_authz_boundaries import _assign, _make_engagement, _make_engagement_role


class FakeWS:
    def __init__(self):
        self.sent, self.closed_with = [], None

    async def send_json(self, payload):
        self.sent.append(payload)

    async def close(self, code=1000):
        self.closed_with = code


@pytest.fixture
def same_session(db_session, monkeypatch):
    class _Ctx:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, *exc):
            return False
    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: _Ctx())
    monkeypatch.setattr(wsmod, "_ACCESS_RECHECK_S", 0.02)


async def test_still_allowed_follows_membership_and_activity(same_session, db_session, make_user):
    eng = await _make_engagement(db_session)
    member = await make_user(role="operator")
    assignment = await _assign(db_session, member, eng,
                               await _make_engagement_role(db_session, [Permission.ENGAGEMENT_VIEW.value]))
    assert await wsmod._presence_still_allowed(member.id, eng.id)
    assert await wsmod._presence_still_allowed(member.id, None)        # dashboard / own user channel

    await db_session.delete(assignment)
    await db_session.flush()
    assert not await wsmod._presence_still_allowed(member.id, eng.id)  # removed from the team

    member.is_active = False
    await db_session.flush()
    assert not await wsmod._presence_still_allowed(member.id, None)    # deactivated


async def test_admin_bypass_matches_the_connect_gate(same_session, db_session, make_user):
    eng = await _make_engagement(db_session)
    admin = await make_user(role="admin")
    assert await wsmod._presence_still_allowed(admin.id, eng.id)


async def test_loop_closes_the_socket_once_access_is_gone(same_session, db_session, make_user):
    eng = await _make_engagement(db_session)
    user = await make_user(role="operator")
    await _assign(db_session, user, eng, await _make_engagement_role(db_session, [Permission.ENGAGEMENT_VIEW.value]))
    ws = FakeWS()
    task = asyncio.create_task(wsmod._presence_recheck_loop(ws, user.id, eng.id))
    await asyncio.sleep(0.1)
    assert ws.closed_with is None and not task.done()          # still allowed: stays open

    user.is_active = False
    await db_session.flush()
    await asyncio.wait_for(task, timeout=5)
    assert ws.sent == [{"type": "access_revoked"}] and ws.closed_with == 1008
