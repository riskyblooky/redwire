"""Collaborative note persistence: only real edits touch the note, and only
frames that carry content schedule a save."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime

import pytest

from tests.test_authz_boundaries import _make_engagement


@pytest.fixture
def note_db(db_session, monkeypatch):
    """save_note_content opens its own session; hand it the test one."""
    import database
    from utils import yjs_server

    @asynccontextmanager
    async def _session():
        yield db_session

    monkeypatch.setattr(database, "AsyncSessionLocal", _session)

    async def _in_session(db, note_id):  # not a session start: no snapshot / log
        return True
    monkeypatch.setattr(yjs_server, "_recent_note_log_exists", _in_session)
    return db_session


async def _note(db, author):
    from models.note import Note

    eng = await _make_engagement(db)
    note = Note(id=str(uuid.uuid4()), engagement_id=eng.id, title="n", content="# hello",
                created_by=author.id, updated_by=author.id, updated_at=datetime(2026, 1, 1))
    db.add(note)
    await db.flush()
    return note


async def test_unchanged_content_is_not_an_edit(note_db, make_user):
    from utils.yjs_server import save_note_content

    author, reader = await make_user(), await make_user()
    note = await _note(note_db, author)

    await save_note_content(note.id, "# hello", reader.id)

    await note_db.refresh(note)
    assert note.updated_by == author.id
    assert note.updated_at == datetime(2026, 1, 1)


async def test_changed_content_is_saved(note_db, make_user):
    from utils.yjs_server import save_note_content

    author, editor = await make_user(), await make_user()
    note = await _note(note_db, author)

    await save_note_content(note.id, "# hello\n\nmore", editor.id)

    await note_db.refresh(note)
    assert note.content == "# hello\n\nmore"
    assert note.updated_by == editor.id
    assert note.updated_at > datetime(2026, 1, 1)


@pytest.mark.parametrize("carries_update, schedules", [(False, False), (True, True)])
async def test_only_content_frames_schedule_a_save(carries_update, schedules, monkeypatch):
    from utils import ws_bus, yjs_server
    from tests.test_ws_fanout import FakeWS, RecordingBus

    monkeypatch.setattr(ws_bus, "bus", RecordingBus())
    note = f"n-{uuid.uuid4().hex[:6]}"
    room = yjs_server.yjs_store.get_or_create_room(note)
    a, b = FakeWS(), FakeWS()
    await room.add_client(a, "u1")
    await room.add_client(b, "u2")
    try:
        await room.relay_binary(a, b"\x01\x00", carries_update=carries_update)
        assert b.bytes[-1] == b"\x01\x00"  # relayed either way
        assert (room._save_task is not None) is schedules
    finally:
        if room._save_task:
            room._save_task.cancel()
        yjs_server.yjs_store.remove_room(note)


async def test_save_is_requested_from_the_client_that_edited(monkeypatch):
    """Not from whichever client happens to be first: one that just joined
    may still hold an empty placeholder and send that back as the note."""
    import json
    from utils import ws_bus, yjs_server
    from tests.test_ws_fanout import FakeWS, RecordingBus

    bus = RecordingBus()

    async def _claim(*a, **k):
        return True
    bus.claim = _claim
    monkeypatch.setattr(ws_bus, "bus", bus)
    note = f"n-{uuid.uuid4().hex[:6]}"
    room = yjs_server.yjs_store.get_or_create_room(note)
    a, b = FakeWS(), FakeWS()
    await room.add_client(a, "u1")
    await room.add_client(b, "u2")
    # The editor is whichever one a plain "first client" pick would skip.
    newcomer = next(iter(room.clients))
    editor = b if newcomer is a else a
    try:
        await room.relay_binary(editor, b"\x00\x02", carries_update=True)
        room._save_task.cancel()
        await room._request_save()
        asked = [ws for ws in (newcomer, editor) if any("request_save" in t for t in ws.text)]
        assert asked == [editor]
    finally:
        yjs_server.yjs_store.remove_room(note)
