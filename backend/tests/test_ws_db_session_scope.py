"""A WebSocket must not hold a pooled DB connection for its lifetime: the
setup session is closed before the receive loop starts."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi import WebSocketDisconnect

import routers.websocket as wsmod


class _Ctx:
    def __init__(self, log):
        self.log = log

    async def __aenter__(self):
        self.log.append("session-open")
        return SimpleNamespace()

    async def __aexit__(self, *exc):
        self.log.append("session-closed")
        return False


class _WS:
    def __init__(self, log):
        self.log = log

    async def accept(self):
        self.log.append("accept")

    async def receive_json(self):
        self.log.append("receive")
        raise WebSocketDisconnect(1000)

    async def close(self, code=1000):
        self.log.append(f"close:{code}")


async def test_presence_socket_releases_db_before_receive_loop(monkeypatch):
    import database
    log = []
    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: _Ctx(log))
    user = SimpleNamespace(id="u1", username="u", full_name="U", profile_photo=None)

    async def _auth(ws, db):
        return user, "admin"
    monkeypatch.setattr(wsmod, "_auth_via_first_frame", _auth)

    async def _nop(*_a, **_k):
        return None
    for name in ("connect", "leave", "broadcast_to_resource", "refresh_presence"):
        monkeypatch.setattr(wsmod.manager, name, _nop)

    await wsmod.websocket_endpoint(_WS(log), "dashboard", "global")
    assert log.index("session-closed") < log.index("receive"), log
