"""An open live-edit socket re-checks access mid-session: losing edit makes
it read-only (no relayed content, no saves), losing view closes it, and a
deactivated user is cut off — not just at the next connect."""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest

import database
import routers.websocket as wsmod

UPDATE_FRAME = bytes([0, 2, 1, 2, 3])  # sync / update: document content


class FakeWS:
    def __init__(self, frames, hang_up=True):
        self.inbox = asyncio.Queue()
        for f in frames:
            self.inbox.put_nowait(f)
        if hang_up:
            self.inbox.put_nowait({"type": "websocket.disconnect", "code": 1000})
        self.sent: list[dict] = []
        self.closed_with = None

    async def receive(self):
        return await self.inbox.get()

    async def send_text(self, text):
        self.sent.append(json.loads(text))

    async def send_bytes(self, data):
        pass

    async def close(self, code=1000):
        self.closed_with = code
        while not self.inbox.empty():
            self.inbox.get_nowait()
        self.inbox.put_nowait({"type": "websocket.disconnect", "code": code})

    def types(self):
        return [m["type"] for m in self.sent]


@pytest.fixture
def harness(db_session, monkeypatch):
    class _Ctx:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, *exc):
            return False
    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: _Ctx())
    monkeypatch.setattr(wsmod, "_ACCESS_RECHECK_S", 0)  # re-check on every frame
    relayed = []

    from utils.yjs_server import YjsRoom
    async def spy_relay(self, ws, data, carries_update=True):
        relayed.append(data)
    monkeypatch.setattr(YjsRoom, "relay_binary", spy_relay)
    return relayed


async def _serve(ws, user, allowed, saves):
    async def on_save(content):
        saves.append(content)

    async def recheck(_db, _user):
        return allowed()
    await wsmod._serve_yjs_room(ws, f"test:{uuid.uuid4().hex}", user.id, True, initial_content="x",
                                persist=False, on_save=on_save, recheck=recheck)


async def test_edit_revoked_mid_session_goes_read_only(harness, make_user):
    user = await make_user(role="operator")
    state = {"edit": True}
    frames = [{"type": "websocket.receive", "bytes": UPDATE_FRAME},
              {"type": "websocket.receive", "text": json.dumps({"type": "save_content", "content": "a"})}]
    ws = FakeWS(frames)
    saves = []
    # Edit is revoked right after the first frame is relayed.
    orig_get = ws.inbox.get

    async def get_and_revoke():
        msg = await orig_get()
        if msg.get("text"):
            state["edit"] = False
        return msg
    ws.inbox.get = get_and_revoke
    await _serve(ws, user, lambda: state["edit"], saves)
    assert harness == [UPDATE_FRAME]
    assert saves == []
    assert {"type": "access_changed", "can_edit": False} in ws.sent
    assert {"type": "content_saved", "ok": False} in ws.sent


async def test_view_revoked_closes(harness, make_user):
    user = await make_user(role="operator")
    ws = FakeWS([{"type": "websocket.receive", "bytes": UPDATE_FRAME}])
    await _serve(ws, user, lambda: None, [])
    assert "access_revoked" in ws.types() and ws.closed_with == 1008 and harness == []


async def test_deactivated_user_cut_off(harness, db_session, make_user):
    user = await make_user(role="admin")
    user.is_active = False
    await db_session.flush()
    ws = FakeWS([{"type": "websocket.receive", "text": json.dumps({"type": "save_content", "content": "a"})}])
    saves = []
    await _serve(ws, user, lambda: True, saves)
    assert saves == [] and ws.closed_with == 1008


async def test_edit_granted_mid_session(harness, make_user):
    user = await make_user(role="operator")
    ws = FakeWS([{"type": "websocket.receive", "text": json.dumps({"type": "save_content", "content": "a"})}])
    saves = []
    # Starts as viewer (can_edit False passed below), recheck says editor now.
    async def on_save(content):
        saves.append(content)

    async def recheck(_db, _user):
        return True
    await wsmod._serve_yjs_room(ws, f"test:{uuid.uuid4().hex}", user.id, False, initial_content="x",
                                persist=False, on_save=on_save, recheck=recheck)
    assert {"type": "access_changed", "can_edit": True} in ws.sent and saves == ["a"]


async def test_idle_socket_is_cut_off_by_the_timer(harness, make_user, monkeypatch):
    """An idle client sends no frames, so only the server's timer notices."""
    monkeypatch.setattr(wsmod, "_ACCESS_RECHECK_S", 0.05)
    user = await make_user(role="operator")
    ws = FakeWS([], hang_up=False)
    state = {"view": True}

    async def revoke_soon():
        await asyncio.sleep(0.1)
        state["view"] = False
    asyncio.create_task(revoke_soon())
    await asyncio.wait_for(_serve(ws, user, lambda: True if state["view"] else None, []), timeout=5)
    assert "access_revoked" in ws.types() and ws.closed_with == 1008


async def test_field_sockets_share_one_check_per_record(harness, make_user, monkeypatch):
    """An edit page's field sockets (same user, same record) share one access
    check per interval; a save checks afresh; other users check on their own."""
    monkeypatch.setattr(wsmod, "_ACCESS_RECHECK_S", 30)
    a = await make_user(role="operator")
    b = await make_user(role="operator")
    calls = []

    async def recheck(_db, user):
        calls.append(user.id)
        await asyncio.sleep(0.01)
        return True
    rec = f"finding:{uuid.uuid4()}"
    results = await asyncio.gather(*(wsmod._shared_access_check((a.id, rec), a.id, recheck, False)
                                     for _ in range(6)))
    assert results == [True] * 6 and calls == [a.id]
    assert await wsmod._shared_access_check((a.id, rec), a.id, recheck, False) is True
    assert calls == [a.id]                       # cached within the interval
    assert await wsmod._shared_access_check((a.id, rec), a.id, recheck, True) is True
    assert calls == [a.id, a.id]                 # fresh (a save) always checks
    await wsmod._shared_access_check((b.id, rec), b.id, recheck, False)
    assert calls == [a.id, a.id, b.id]


async def test_shared_check_errors_are_not_cached(harness, make_user, monkeypatch):
    monkeypatch.setattr(wsmod, "_ACCESS_RECHECK_S", 30)
    u = await make_user(role="operator")
    state = {"fail": True}

    async def recheck(_db, _user):
        if state["fail"]:
            raise RuntimeError("db down")
        return False
    key = (u.id, f"note:{uuid.uuid4()}")
    with pytest.raises(RuntimeError):
        await wsmod._shared_access_check(key, u.id, recheck, False)
    state["fail"] = False
    assert await wsmod._shared_access_check(key, u.id, recheck, False) is False


async def test_revocation_reaches_every_socket_on_the_record(harness, make_user, monkeypatch):
    """Two idle field sockets on one record: one shared check revokes both."""
    monkeypatch.setattr(wsmod, "_ACCESS_RECHECK_S", 0.05)
    user = await make_user(role="operator")
    state = {"view": True}
    calls = []

    async def recheck(_db, _user):
        calls.append(1)
        return True if state["view"] else None
    share = f"finding:{uuid.uuid4()}"
    socks = [FakeWS([], hang_up=False) for _ in range(2)]

    async def serve(ws, field):
        await wsmod._serve_yjs_room(ws, f"{share}:{field}", user.id, True, initial_content="x",
                                    persist=False, on_save=None, recheck=recheck, share_key=share)

    async def revoke_soon():
        await asyncio.sleep(0.12)
        state["view"] = False
    asyncio.create_task(revoke_soon())
    await asyncio.wait_for(asyncio.gather(serve(socks[0], "description"), serve(socks[1], "impact")), timeout=5)
    assert all("access_revoked" in ws.types() and ws.closed_with == 1008 for ws in socks)
