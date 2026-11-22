"""Version-restore guard: read-only viewers don't block a restore; the
caller's editor in another tab does; the restoring tab's own doesn't."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from utils import collab_fields
from utils.collab_fields import COLLAB_FIELDS, assert_no_other_live_editors, room_key
from utils.ws_bus import bus


@pytest.fixture
def presence(monkeypatch):
    rooms: dict[str, list[dict]] = {}

    async def plist(rt, key):
        return rooms.get(key, [])
    monkeypatch.setattr(bus, "presence_list", plist)
    field = next(iter(COLLAB_FIELDS["finding"]))
    return lambda *members: rooms.__setitem__(room_key("finding", "f1", field), list(members))


async def _blocked(user, tab):
    try:
        await assert_no_other_live_editors("finding", "f1", user, tab_id=tab)
        return False
    except HTTPException as e:
        assert e.status_code == 409
        return True


async def test_guard(presence):
    presence({"id": "bob", "tab": "b1", "can_edit": False})               # viewer only
    assert not await _blocked("me", "t1")
    presence({"id": "bob", "tab": "b1", "can_edit": True})                # another editor
    assert await _blocked("me", "t1")
    presence({"id": "me", "tab": "t1", "can_edit": True})                 # my own tab
    assert not await _blocked("me", "t1")
    presence({"id": "me", "tab": "t2", "can_edit": True})                 # my other tab
    assert await _blocked("me", "t1")
    assert not await _blocked("me", None)                                 # no tab id: old rule
