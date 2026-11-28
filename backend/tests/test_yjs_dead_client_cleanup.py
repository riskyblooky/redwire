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


class Rec(WS):
    def __init__(self):
        super().__init__()
        self.bytes = []

    async def send_bytes(self, b):
        self.bytes.append(b)


STEP1, STEP2, UPDATE, AWARENESS = b"\x00\x00sv", b"\x00\x01doc", b"\x00\x02u", b"\x01aw"


async def test_sync_step2_goes_only_to_whoever_asked(monkeypatch):
    async def publish(*a, **kw):
        return None
    monkeypatch.setattr(bus, "publish", publish)
    room = YjsRoom("k", persist=False)
    a, b, c, joiner = Rec(), Rec(), Rec(), Rec()
    for i, ws in enumerate((a, b, c)):
        await room.add_client(ws, f"u{i}")

    # A step 2 nobody asked for goes nowhere.
    await room._relay_local(a, STEP2)
    assert b.bytes == c.bytes == []

    await room.add_client(joiner, "u9")
    await room._relay_local(joiner, STEP1)          # everyone sees the query
    assert a.bytes == b.bytes == c.bytes == [STEP1]
    for peer in (a, b, c):                          # each replies
        await room._relay_local(peer, STEP2)
    assert joiner.bytes == [STEP2] * 3
    assert a.bytes == b.bytes == c.bytes == [STEP1], "peers don't get each other's replies"

    # Updates and awareness still reach everyone.
    await room._relay_local(a, UPDATE)
    await room._relay_local(a, AWARENESS)
    assert b.bytes[-2:] == [UPDATE, AWARENESS] and joiner.bytes[-2:] == [UPDATE, AWARENESS]

    # From another worker (sender None): delivered to local askers only.
    await room._relay_local(None, STEP2)
    assert joiner.bytes[-1] == STEP2 and b.bytes[-1] == AWARENESS

    # The window closes.
    room.awaiting_sync[joiner] = 0
    await room._relay_local(a, STEP2)
    assert joiner.bytes[-1] == STEP2 and len(joiner.bytes) == 6
    room.remove_client(joiner)
    assert joiner not in room.awaiting_sync
