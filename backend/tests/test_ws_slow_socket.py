"""One client that stops reading can't stall a broadcast: sends go out
concurrently, each bounded, and a socket that times out is dropped and
closed while everyone else still gets the message promptly."""

from __future__ import annotations

import asyncio
import json
import time

from utils import collaboration, ws_bus
from utils.collaboration import ConnectionManager
from tests.test_ws_fanout import FakeWS, RecordingBus


class StuckWS(FakeWS):
    """A peer whose TCP buffer is full: send never completes."""
    def __init__(self):
        super().__init__()
        self.closed_with = None

    async def send_text(self, m):
        await asyncio.Event().wait()

    async def close(self, code=1000):
        self.closed_with = code


async def test_stuck_socket_does_not_stall_the_others(monkeypatch):
    monkeypatch.setattr(ws_bus, "bus", RecordingBus())
    monkeypatch.setattr(collaboration, "_SEND_TIMEOUT_S", 0.2)
    mgr = ConnectionManager()
    stuck, after = StuckWS(), FakeWS()
    mgr.active_connections = {"engagement": {"e1": [stuck, after], "e2": [stuck]}}
    mgr.connection_info = {stuck: {"id": "u1"}, after: {"id": "u2"}}

    t0 = time.monotonic()
    await asyncio.wait_for(mgr.broadcast_to_resource("engagement", "e1", {"type": "finding_updated"}), timeout=3)
    assert time.monotonic() - t0 < 1.5
    assert json.loads(after.text[0])["type"] == "finding_updated"

    # Dropped from every channel and closed, so it reconnects rather than
    # silently missing events.
    assert stuck not in mgr.active_connections["engagement"].get("e1", [])
    assert "e2" not in mgr.active_connections["engagement"]
    await asyncio.sleep(0.05)
    assert stuck.closed_with == 1013


async def test_sends_go_out_concurrently(monkeypatch):
    monkeypatch.setattr(ws_bus, "bus", RecordingBus())

    class SlowWS(FakeWS):
        async def send_text(self, m):
            await asyncio.sleep(0.3)
            self.text.append(m)
    mgr = ConnectionManager()
    socks = [SlowWS() for _ in range(5)]
    mgr.active_connections = {"engagement": {"e1": socks}}
    mgr.connection_info = {s: {"id": f"u{i}"} for i, s in enumerate(socks)}
    t0 = time.monotonic()
    await mgr.broadcast_to_resource("engagement", "e1", {"type": "x"})
    assert time.monotonic() - t0 < 1.0          # 5 x 0.3s sequentially would be 1.5s
    assert all(s.text for s in socks)
