"""Automations run off the request path: create_activity_log returns before
a slow rule finishes, the rule gets its own session, and a hung rule is cut
off by the timeout."""

from __future__ import annotations

import asyncio

from utils import collaboration


class _Db:
    def __init__(self):
        self.commits = 0
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass

    async def execute(self, *_a, **_k):
        raise RuntimeError("not used")


class _SessionCtx:
    def __init__(self, sink):
        self.db = _Db()
        sink.append(self.db)

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *exc):
        return False


def _quiet(monkeypatch):
    from utils.event_bus import event_bus

    async def _nop(*_a, **_k):
        return None
    monkeypatch.setattr(collaboration.manager, "broadcast_to_resource", _nop)
    monkeypatch.setattr(event_bus, "emit", _nop)


async def test_slow_rule_does_not_block_the_request(monkeypatch):
    import database
    import utils.automation_engine as ae
    _quiet(monkeypatch)
    monkeypatch.setattr(collaboration, "AUTOMATION_INLINE", False)
    sessions = []
    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: _SessionCtx(sessions))

    started, release, seen = asyncio.Event(), asyncio.Event(), []

    async def slow_rule(db, trigger, context):
        seen.append((db, trigger))
        started.set()
        await release.wait()
    monkeypatch.setattr(ae, "evaluate_rules", slow_rule)

    caller = _Db()
    await asyncio.wait_for(
        collaboration.create_activity_log(caller, "eng-1", "user-1", "created", "finding", "f-1"), 2)
    assert caller.commits == 1  # its own log row only — no automation commit on the caller's session

    await asyncio.wait_for(started.wait(), 2)
    assert seen[0][0] is sessions[0] and seen[0][1] == "created"
    release.set()
    await collaboration.drain_automations(timeout=2)
    assert sessions[0].commits == 1


async def test_hung_rule_times_out(monkeypatch):
    import database
    import utils.automation_engine as ae
    _quiet(monkeypatch)
    monkeypatch.setattr(collaboration, "AUTOMATION_INLINE", False)
    monkeypatch.setattr(collaboration, "AUTOMATION_TIMEOUT_S", 0.05)
    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: _SessionCtx([]))

    async def hang(db, trigger, context):
        await asyncio.sleep(30)
    monkeypatch.setattr(ae, "evaluate_rules", hang)

    await collaboration.create_activity_log(_Db(), "eng-1", "user-1", "created", "finding", "f-1")
    await asyncio.wait_for(collaboration.drain_automations(), 2)
    assert not collaboration._automation_tasks
