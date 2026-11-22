"""A Yjs peer whose send fails is removed completely: Y.js id unmapped,
not left as last_editor, socket closed, and the others told it's gone."""

from __future__ import annotations

import json

from utils.ws_bus import bus
from utils.yjs_server import YjsRoom


class WS:
    def __init__(self, broken=False):
        self.broken, self.text, self.closed = broken, [], None

    async def send_bytes(self, b):
        if self.broken:
            raise RuntimeError("gone")

    async def send_text(self, t):
        if self.broken:
            raise RuntimeError("gone")
        self.text.append(json.loads(t))

    async def close(self, code=1000):
        self.closed = code


async def test_dead_peer_fully_dropped(monkeypatch):
    async def publish(*a, **kw):
        return None
    monkeypatch.setattr(bus, "publish", publish)
    room = YjsRoom("k", persist=False)
    sender, live, dead = WS(), WS(), WS(broken=True)
    for i, ws in enumerate((sender, live, dead)):
        await room.add_client(ws, f"u{i}")
        room.set_client_yjs_id(ws, 100 + i)
    room.last_editor = dead

    await room._relay_local(sender, b"x")

    assert dead not in room.clients and dead not in room.client_yjs_ids
    assert room.last_editor is None and dead.closed == 1011
    assert {"type": "peer_disconnected", "client_id": 102} in live.text
