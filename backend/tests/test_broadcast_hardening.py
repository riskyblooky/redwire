"""ConnectionManager.broadcast_to_resource hardening regressions.

Two properties this file pins:

  (a) ``broadcast_to_resource("dashboard", "global", ..., db=None)`` is a
      programming error and raises ``ValueError`` rather than silently
      delivering the event to every subscriber. The per-recipient
      engagement-membership filter only engages when ``db`` is supplied
      (it needs a session for the rbac check), so falling through with
      ``db=None`` is the exact disclosure shape the gate was added to
      prevent. GHSA-pqj4-49q4-rw4f follow-up.

  (b) When a recipient's ``send_text`` raises, the dead socket gets
      purged from *every* channel it's registered in, not just the
      channel the broadcast was iterating. Previously the cleanup was
      per-channel and a dead socket lingered in any other channel it
      had joined until that channel's next broadcast. GHSA-c96m-c63f-3f2c
      follow-up.
"""

from __future__ import annotations

import asyncio

import pytest

from utils.collaboration import ConnectionManager


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class _LiveSocket:
    """Stand-in for ``starlette.websockets.WebSocket``. ``send_text``
    succeeds; broadcasts to a manager holding one of these will deliver
    cleanly."""

    def __init__(self):
        self.sent: list[str] = []

    async def send_text(self, payload: str) -> None:
        self.sent.append(payload)


class _DeadSocket:
    """Send raises — modelling a client that disconnected without the
    handler running ``manager.disconnect`` for it."""

    async def send_text(self, payload: str) -> None:
        raise RuntimeError("socket closed")


def test_dashboard_global_with_engagement_id_but_no_db_raises():
    """Engagement-scoped event on dashboard:global without ``db`` is the
    exact disclosure shape the fail-closed guard exists to prevent — the
    filter would have run, but can't, so the loop must not silently
    fall through to all subscribers."""
    mgr = ConnectionManager()
    ws = _LiveSocket()
    mgr.active_connections["dashboard"] = {"global": [ws]}
    mgr.connection_info[ws] = {"id": "u1"}

    with pytest.raises(ValueError) as exc:
        _run(mgr.broadcast_to_resource(
            "dashboard", "global", {"type": "activity_log", "engagement_id": "eng-A"},
        ))
    assert "requires a db session" in str(exc.value)
    # Subscriber must not have received the message.
    assert ws.sent == []


def test_dashboard_global_without_engagement_id_does_not_need_db():
    """Messages without ``engagement_id`` are intentionally fanned out
    to every subscriber and don't need filtering. This is the shape
    that ``ConnectionManager.connect()`` itself produces (the join
    presence_update has no engagement payload) — the previous version
    of the guard fired on every dashboard:global subscribe and killed
    the channel."""
    mgr = ConnectionManager()
    ws = _LiveSocket()
    mgr.active_connections["dashboard"] = {"global": [ws]}
    mgr.connection_info[ws] = {"id": "u1"}

    # No exception, no db, no engagement_id → broadcast freely.
    _run(mgr.broadcast_to_resource(
        "dashboard", "global", {"type": "presence_update", "action": "joined"},
    ))
    assert len(ws.sent) == 1


def test_dashboard_global_connect_succeeds_without_db():
    """Regression: ``connect()`` calls broadcast_to_resource for a
    presence_update without db. Before the guard tightening, that
    raised ValueError mid-connect and killed every dashboard:global
    subscription. Pin the fix."""
    mgr = ConnectionManager()
    ws = _LiveSocket()
    # connect() itself triggers a presence_update broadcast; if the
    # guard regresses this raises and the test fails.
    _run(mgr.connect(ws, "dashboard", "global", {"id": "u1"}))
    # The join broadcast was delivered to the new subscriber.
    assert len(ws.sent) == 1


def test_dashboard_engagement_scope_does_not_need_db():
    """The fail-closed guard is specifically ``dashboard:global`` — other
    channels are subscribe-time scoped and broadcast cleanly without db."""
    mgr = ConnectionManager()
    ws = _LiveSocket()
    _run(mgr.connect(ws, "dashboard", "eng-A", {"id": "u1"}))
    # First broadcast was the `joined` presence_update from connect();
    # clear and broadcast our own event.
    ws.sent.clear()
    _run(mgr.broadcast_to_resource(
        "dashboard", "eng-A", {"type": "hello"},
    ))
    assert len(ws.sent) == 1


def test_dead_socket_is_purged_from_every_channel():
    mgr = ConnectionManager()
    dead = _DeadSocket()
    live = _LiveSocket()

    # Same socket subscribes to three channels. (`connect` itself
    # broadcasts a presence_update which triggers our send and finds
    # the dead socket — so the purge runs during connect already. To
    # make the test deterministic we register the dead socket via
    # direct manager-state manipulation, bypassing the connect-time
    # presence broadcast.)
    for resource_id in ("eng-A", "eng-B", "eng-C"):
        mgr.active_connections.setdefault("engagement", {}).setdefault(resource_id, []).append(dead)
        mgr.active_connections["engagement"][resource_id].append(live)
    mgr.connection_info[dead] = {"id": "dead-user"}
    mgr.connection_info[live] = {"id": "live-user"}

    # Broadcast to one channel — that's enough to discover ``dead`` is dead.
    _run(mgr.broadcast_to_resource(
        "engagement", "eng-A", {"type": "hello"},
    ))

    # ``dead`` must be gone from every channel it was in, not just eng-A.
    for resource_id in ("eng-A", "eng-B", "eng-C"):
        sockets = mgr.active_connections.get("engagement", {}).get(resource_id, [])
        assert dead not in sockets, (
            f"dead socket still in engagement:{resource_id} — purge was "
            f"per-channel instead of global (GHSA-c96m follow-up regressed)"
        )
    assert dead not in mgr.connection_info
    # ``live`` is untouched.
    assert mgr.connection_info[live] == {"id": "live-user"}


def test_purge_collapses_empty_channels():
    """After a purge, channels with no subscribers should be deleted so
    the manager state doesn't grow unbounded keys."""
    mgr = ConnectionManager()
    dead = _DeadSocket()
    mgr.active_connections.setdefault("note", {}).setdefault("n-1", []).append(dead)
    mgr.connection_info[dead] = {"id": "u"}

    _run(mgr.broadcast_to_resource("note", "n-1", {"type": "hello"}))

    assert "n-1" not in mgr.active_connections.get("note", {})
    # And since "note" had only n-1, the whole resource_type should be gone too.
    assert "note" not in mgr.active_connections
