"""Cross-worker WebSocket fan-out (utils/ws_bus.py) — bus dispatch, remote
delivery incl. the dashboard:global membership gate, cluster-wide presence,
and Y.js frame relay."""

from __future__ import annotations

import json
import os
import uuid

import pytest

from utils import ws_bus
from utils.collaboration import ConnectionManager


class FakeWS:
    def __init__(self):
        self.text: list[str] = []
        self.bytes: list[bytes] = []

    async def send_text(self, m):
        self.text.append(m)

    async def send_bytes(self, b):
        self.bytes.append(b)


class RecordingBus:
    """Stands in for the Redis bus: records publishes, serves presence."""
    active = True

    def __init__(self, presence=None):
        self.published = []
        self.presence = presence

    async def publish(self, kind, payload):
        self.published.append((kind, json.loads(json.dumps(payload))))

    async def presence_add(self, *a):
        pass

    async def presence_remove(self, *a):
        pass

    async def presence_list(self, *a):
        return self.presence

    async def claim(self, *a):
        return True


async def test_dispatch_ignores_own_worker_and_routes_by_kind():
    bus = ws_bus.WsBus()
    seen = []

    async def handler(p):
        seen.append(p)
    bus.register("resource", handler)

    await bus._dispatch(json.dumps({"o": ws_bus.WORKER_ID, "k": "resource", "p": {"x": 1}}))
    await bus._dispatch(json.dumps({"o": "other", "k": "unknown", "p": {"x": 2}}))
    await bus._dispatch("not json")
    await bus._dispatch(json.dumps({"o": "other", "k": "resource", "p": {"x": 3}}))
    assert seen == [{"x": 3}]


async def test_broadcast_delivers_locally_and_publishes(monkeypatch):
    fake = RecordingBus(presence=[{"id": "u2", "username": "remote"}, {"id": "u1"}])
    monkeypatch.setattr(ws_bus, "bus", fake)
    mgr = ConnectionManager()
    ws = FakeWS()
    mgr.active_connections = {"engagement": {"e1": [ws]}}
    mgr.connection_info = {ws: {"id": "u1"}}

    await mgr.broadcast_to_resource("engagement", "e1", {"type": "presence_update", "action": "joined"})

    sent = json.loads(ws.text[0])
    # active_users comes from the cluster-wide registry, not just local sockets
    assert [u["id"] for u in sent["active_users"]] == ["u1", "u2"]
    kind, payload = fake.published[0]
    assert kind == "resource" and payload["rt"] == "engagement" and payload["rid"] == "e1"
    assert [u["id"] for u in payload["m"]["active_users"]] == ["u1", "u2"]


async def test_remote_global_message_is_gated_per_recipient(monkeypatch):
    import auth.rbac as rbac
    import database

    class _Session:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: _Session())

    async def _perm(user_id, engagement_id, db):
        return user_id == "member"
    monkeypatch.setattr(rbac, "can_view_engagement", _perm)

    mgr = ConnectionManager()
    member, outsider = FakeWS(), FakeWS()
    mgr.active_connections = {"dashboard": {"global": [member, outsider]}}
    mgr.connection_info = {member: {"id": "member"}, outsider: {"id": "outsider"}}

    await mgr._deliver_from_bus({"rt": "dashboard", "rid": "global",
                                 "m": {"type": "activity_log", "engagement_id": "e1"}})
    assert len(member.text) == 1
    assert outsider.text == []


async def test_remote_message_for_channel_without_local_sockets_is_dropped():
    mgr = ConnectionManager()
    await mgr._deliver_from_bus({"rt": "engagement", "rid": "nobody-here", "m": {"type": "x"}})
    await mgr._deliver_from_bus({"rt": "engagement"})  # malformed: no crash


async def test_yjs_remote_frame_relayed_to_all_local_clients(monkeypatch):
    from utils import yjs_server

    monkeypatch.setattr(ws_bus, "bus", RecordingBus())
    note = f"n-{uuid.uuid4().hex[:6]}"
    room = yjs_server.yjs_store.get_or_create_room(note)
    a, b = FakeWS(), FakeWS()
    await room.add_client(a, "u1")
    await room.add_client(b, "u2")
    try:
        await yjs_server._on_remote_frame({"note": note, "data": ws_bus.b64(b"\x00\x01")})
        assert a.bytes == [b"\x00\x01"] and b.bytes == [b"\x00\x01"]

        # A local frame goes to the other local client and onto the bus.
        await room.relay_binary(a, b"\x02")
        assert b.bytes[-1] == b"\x02" and a.bytes == [b"\x00\x01"]
        assert ws_bus.bus.published[-1][0] == "yjs_frame"
    finally:
        if room._save_task:
            room._save_task.cancel()
        yjs_server.yjs_store.remove_room(note)


async def test_presence_registry_prunes_dead_workers():
    """Real Redis (the dev container's); skipped where none is reachable."""
    bus = ws_bus.WsBus()
    os.environ.setdefault("WS_FANOUT", "true")
    await bus.start()
    if not bus.active:
        pytest.skip("Redis not reachable")
    rt, rid = "test", uuid.uuid4().hex
    key = bus._presence_key(rt, rid)
    try:
        await bus.presence_add(rt, rid, "c1", {"id": "alive"})
        # An entry left behind by a worker that died (no liveness key).
        await bus._redis.hset(key, "deadworker:c9", json.dumps({"id": "ghost"}))
        users = await bus.presence_list(rt, rid)
        assert [u["id"] for u in users] == ["alive"]
        assert not await bus._redis.hexists(key, "deadworker:c9")

        await bus.presence_remove(rt, rid, "c1")
        assert await bus.presence_list(rt, rid) == []
    finally:
        await bus._redis.delete(key)
        await bus.stop()
