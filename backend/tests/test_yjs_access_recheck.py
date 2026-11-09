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
    async def spy_relay(self, ws, data):
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
