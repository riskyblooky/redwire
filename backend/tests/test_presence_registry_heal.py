"""A worker re-asserts its own presence entries on every heartbeat, so a
live socket can't drop out of the registry for good (failed HSET, entry
pruned while the heartbeat lapsed, hash TTL expiry) — the "no peers" answer
that made a note joiner seed the DB copy over a live document."""

from __future__ import annotations

import os
import uuid

import pytest

from utils import ws_bus


@pytest.fixture
async def bus():
    b = ws_bus.WsBus()
    os.environ.setdefault("WS_FANOUT", "true")
    await b.start()
    if not b.active:
        pytest.skip("Redis not reachable")
    yield b
    await b.stop()


async def test_lost_entry_comes_back_on_the_next_heartbeat(bus):
    rt, rid = "yjs", uuid.uuid4().hex
    key = bus._presence_key(rt, rid)
    try:
        await bus.presence_add(rt, rid, "c1", {"id": "u1"})
        await bus._redis.delete(key)            # pruned / expired / never written
        assert await bus.presence_list(rt, rid) == []

        await bus._heartbeat_once()
        assert [u["id"] for u in await bus.presence_list(rt, rid)] == ["u1"]
    finally:
        await bus._redis.delete(key)


async def test_removed_entry_is_not_resurrected(bus):
    rt, rid = "yjs", uuid.uuid4().hex
    key = bus._presence_key(rt, rid)
    try:
        await bus.presence_add(rt, rid, "c1", {"id": "u1"})
        await bus.presence_remove(rt, rid, "c1")
        await bus._heartbeat_once()
        assert await bus.presence_list(rt, rid) == []
        assert key not in bus._local_presence
    finally:
        await bus._redis.delete(key)


async def test_add_while_redis_down_is_published_once_it_is_up(bus):
    rt, rid = "yjs", uuid.uuid4().hex
    key = bus._presence_key(rt, rid)
    redis, bus._redis = bus._redis, None
    try:
        await bus.presence_add(rt, rid, "c1", {"id": "u1"})
    finally:
        bus._redis = redis
    try:
        await bus._heartbeat_once()
        assert [u["id"] for u in await bus.presence_list(rt, rid)] == ["u1"]
    finally:
        await bus._redis.delete(key)


async def test_peer_count_counts_local_clients_the_registry_missed(monkeypatch):
    import routers.websocket as wsmod
    from utils import ws_bus as wb

    class EmptyRegistry:
        async def presence_list(self, *a):
            return []
    monkeypatch.setattr(wb, "bus", EmptyRegistry())

    class Room:
        clients = {"self": 1, "local-peer": 1}
    assert await wsmod._yjs_peer_count("n1", Room()) == 1
