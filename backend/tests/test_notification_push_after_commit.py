"""A notification's live push waits for the commit, carries the row's id,
and is dropped when the transaction rolls back."""

from __future__ import annotations

import asyncio

from utils import collaboration


def _capture(monkeypatch):
    sent = []

    async def _fake(resource_type, resource_id, message, *a, **kw):
        sent.append((resource_type, resource_id, message))
    monkeypatch.setattr(collaboration.manager, "broadcast_to_resource", _fake)
    return sent


async def test_push_waits_for_commit_and_carries_the_id(db_session, make_user, monkeypatch):
    sent = _capture(monkeypatch)
    user = await make_user()
    notif = await collaboration.create_notification(db_session, user.id, "mention", "You were mentioned")
    await asyncio.sleep(0)
    assert sent == []

    await db_session.commit()
    await asyncio.sleep(0.05)
    assert len(sent) == 1
    rtype, rid, msg = sent[0]
    assert (rtype, rid) == ("user", user.id)
    assert msg["notification"]["id"] == notif.id and notif.id
    assert msg["notification"]["created_at"]


async def test_push_is_dropped_on_rollback(db_session, make_user, monkeypatch):
    sent = _capture(monkeypatch)
    user = await make_user()
    await db_session.flush()
    await collaboration.create_notification(db_session, user.id, "mention", "Never committed")
    await db_session.rollback()
    await asyncio.sleep(0.05)
    assert sent == []
