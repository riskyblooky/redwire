"""Presence `identify` frames can't change the server-side identity that
per-recipient delivery (dashboard:global) is authorized against, and the
cross-worker presence registry reflects the connection's current info."""

from __future__ import annotations

import json

from routers.websocket import _apply_identify
from utils import ws_bus
from utils.collaboration import ConnectionManager


def _info():
    return {"id": "u-low", "role": "operator", "username": "low", "full_name": "Low",
            "profile_photo": None, "mode": "view"}


def test_identify_cannot_spoof_id_or_role():
    info = _info()
    _apply_identify(info, {"id": "u-admin", "role": "admin", "username": "admin",
                           "full_name": "Admin", "profile_photo": "/x.png", "mode": "edit"})
    assert info == {**_info(), "mode": "edit"}


def test_identify_ignores_bad_frames():
    info = _info()
    for claimed in (None, "x", [], {"mode": "owner"}, {"mode": None}):
        _apply_identify(info, claimed)
    assert info == _info()


async def test_refresh_presence_republishes_current_info(monkeypatch):
    added = []

    class _Bus:
        async def presence_add(self, rt, rid, conn_id, info):
            added.append((rt, rid, conn_id, json.loads(json.dumps(info))))
    monkeypatch.setattr(ws_bus, "bus", _Bus())

    mgr = ConnectionManager()
    ws = object()
    info = _info()
    mgr.connection_info = {ws: info}
    mgr.connection_ids = {ws: "c1"}
    _apply_identify(info, {"mode": "edit"})
    await mgr.refresh_presence(ws, "finding", "f1")
    assert added == [("finding", "f1", "c1", {**_info(), "mode": "edit"})]


def test_viewer_binary_filter_blocks_document_content():
    """Read-only Y.js clients may query (sync step 1) and send presence, but
    not sync step 2 or update — both carry a document update an editor would
    merge and then autosave."""
    from routers.websocket import _is_viewer_safe_binary
    assert _is_viewer_safe_binary(bytes([1, 5, 0]))        # awareness
    assert _is_viewer_safe_binary(bytes([0, 0, 1, 0]))     # sync step 1
    assert not _is_viewer_safe_binary(bytes([0, 1, 3, 1, 2, 3]))  # sync step 2
    assert not _is_viewer_safe_binary(bytes([0, 2, 3, 1, 2, 3]))  # update
    assert not _is_viewer_safe_binary(b"")
    assert not _is_viewer_safe_binary(bytes([0]))
