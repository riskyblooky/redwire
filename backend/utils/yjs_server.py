"""
yjs_server.py — Y.js Document Store & WebSocket Relay

Pure binary relay for Y.js CRDT collaboration. Each note gets a room
that relays binary messages (sync protocol + awareness) between all
connected clients. Persistence is handled by debounced save requests
sent to a connected client.

Architecture:
  Client A  ←→  WebSocket  ←→  YjsRoom (relay)  ←→  WebSocket  ←→  Client B
                                   ↓
                             DB (periodic save)

Across workers, relayed frames and peer-disconnect notices also go over the
Redis bus (utils/ws_bus.py) to the same note's room on other workers, room
membership is counted cluster-wide (the ``peers`` bootstrap hint), and the
debounced save is claimed by one worker at a time.
"""

import asyncio
import logging
import time
from typing import Dict, Set, Optional
from fastapi import WebSocket
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Live note content autosaves every few seconds while someone is typing
# (the Y.js room debounces DB writes to ~3s). Writing an activity-log row on
# every one of those would flood the engagement audit trail, which is why the
# content path was left un-logged. Instead we coalesce: at most one
# "updated_note" activity-log entry per note per this window. Title edits (via
# PATCH /notes/{id}) share the same action, so an active editing session
# produces a single rolling "edited note" entry rather than a stream.
NOTE_UPDATE_LOG_DEBOUNCE = timedelta(minutes=10)

# A sync step 2 (a peer's reply carrying the document a step 1 asked for) is
# only useful to whoever sent the step 1. Relayed to everyone, each join cost
# N-1 full documents sent to N-1 sockets. A client that sent a step 1 is
# "awaiting" for this long; step 2 frames go to awaiting clients only.
_STEP2_WINDOW_S = 5.0


def _sync_subtype(data: bytes) -> Optional[int]:
    """The y-protocols sync subtype (0 = step 1, 1 = step 2, 2 = update) of a
    MSG_SYNC frame, else None. Both varUints are one byte for these values."""
    if len(data) >= 2 and data[0] == 0:
        return data[1]
    return None


class YjsRoom:
    """
    A room represents a single Y.js document: one per note, or one per
    collaborative record field (``persist=False`` — the page's Save persists
    those, so the room never asks a client for content).

    The server acts as a pure relay: it forwards all binary messages
    (sync protocol + awareness) between connected clients. The CRDT
    merging and awareness protocol happen entirely in the clients.
    """

    def __init__(self, note_id: str, persist: bool = True):
        self.note_id = note_id  # the room key (a note id, or collab_fields.room_key)
        self.persist = persist
        self.clients: Set[WebSocket] = set()
        self.client_user_ids: Dict[WebSocket, str] = {}  # ws → user_id for save
        self.client_yjs_ids: Dict[WebSocket, int] = {}   # ws → Y.js clientID for awareness cleanup
        self.awaiting_sync: Dict[WebSocket, float] = {}  # ws → step-2 window deadline (see _STEP2_WINDOW_S)
        self.last_activity = time.time()
        self._save_task: Optional[asyncio.Task] = None
        # The client that last sent content. Asked for the save: its doc is
        # known to hold the note (a client that just joined may still show
        # an empty placeholder), and the save is credited to whoever edited.
        self.last_editor: Optional[WebSocket] = None

    async def add_client(self, ws: WebSocket, user_id: str):
        """Add a client to this room."""
        self.clients.add(ws)
        self.client_user_ids[ws] = user_id
        self.last_activity = time.time()

    def set_client_yjs_id(self, ws: WebSocket, yjs_client_id: int):
        """Store the Y.js clientID for a WebSocket connection."""
        self.client_yjs_ids[ws] = yjs_client_id

    def remove_client(self, ws: WebSocket) -> Optional[int]:
        """Remove a client from this room. Returns the Y.js clientID if known."""
        self.clients.discard(ws)
        self.client_user_ids.pop(ws, None)
        yjs_id = self.client_yjs_ids.pop(ws, None)
        self.awaiting_sync.pop(ws, None)
        if self.last_editor is ws:
            self.last_editor = None
        self.last_activity = time.time()
        return yjs_id

    async def notify_peer_disconnected(self, yjs_client_id: int):
        """Tell remaining clients to remove a disconnected peer's awareness state."""
        if yjs_client_id is None:
            return
        from utils.ws_bus import bus
        await bus.publish("yjs_peer_gone", {"note": self.note_id, "client_id": yjs_client_id})
        await self._send_peer_gone_local(yjs_client_id)

    async def _send_peer_gone_local(self, yjs_client_id: int):
        if not self.clients:
            return
        import json
        msg = json.dumps({
            "type": "peer_disconnected",
            "client_id": yjs_client_id,
        })
        dead = []
        for client in self.clients:
            try:
                await client.send_text(msg)
            except Exception:
                dead.append(client)
        await self._drop_dead(dead)

    async def _drop_dead(self, dead) -> None:
        """Remove sockets a send failed on. Only ``clients`` /
        ``client_user_ids`` used to be cleared: the Y.js id stayed mapped,
        ``last_editor`` could stay a dead socket (so the save request went
        nowhere), and the peers kept its cursor. Now it's removed like a
        normal disconnect, its peers are told, and the socket is closed so
        its handler exits and drops its presence entry."""
        for d in dead:
            yjs_id = self.remove_client(d)
            try:
                await d.close(code=1011)
            except Exception:
                pass
            if yjs_id is not None:
                await self.notify_peer_disconnected(yjs_id)

    async def relay_binary(self, sender: WebSocket, data: bytes, carries_update: bool = True):
        """
        Relay a binary message to all clients EXCEPT the sender.

        Binary messages contain Y.js sync protocol (doc updates, sync steps)
        and awareness protocol data. The server does not interpret them —
        it simply forwards to all other connected peers. ``carries_update``
        is False for awareness and sync-step-1 frames, which change no
        content and so don't schedule a DB save.
        """
        await self._relay_local(sender, data)

        from utils.ws_bus import bus, b64
        await bus.publish("yjs_frame", {"note": self.note_id, "data": b64(data)})

        if carries_update:
            self.last_editor = sender
            self._schedule_save()

    async def _relay_local(self, sender: Optional[WebSocket], data: bytes):
        now = self.last_activity = time.time()

        # sender is None for a frame from another worker; that worker tracks
        # its own client's step 1, this one only its local clients'.
        subtype = _sync_subtype(data)
        if subtype == 0 and sender is not None:
            self.awaiting_sync[sender] = now + _STEP2_WINDOW_S
        elif subtype == 1:
            for ws, deadline in list(self.awaiting_sync.items()):
                if deadline < now:
                    del self.awaiting_sync[ws]

        dead = []
        for client in list(self.clients):
            if client is sender:
                continue
            if subtype == 1 and client not in self.awaiting_sync:
                continue
            try:
                await client.send_bytes(data)
            except Exception:
                dead.append(client)

        await self._drop_dead(dead)

    def _schedule_save(self):
        """Schedule a debounced save to the database."""
        if not self.persist:
            return
        if self._save_task and not self._save_task.done():
            self._save_task.cancel()
        self._save_task = asyncio.create_task(self._debounced_save())

    async def _debounced_save(self):
        """Wait for inactivity, then request content from a client."""
        try:
            await asyncio.sleep(3)
            await self._request_save()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning(f"Y.js save error for note {self.note_id}: {e}")

    async def _request_save(self):
        """Ask a connected client to send markdown content for DB persistence."""
        if not self.clients:
            return
        # One save per debounce window cluster-wide, not one per worker
        # that holds clients of this note.
        from utils.ws_bus import bus
        if not await bus.claim(f"yjs-save:{self.note_id}", 2):
            return

        saver = self.last_editor if self.last_editor in self.clients else next(iter(self.clients))
        try:
            import json
            await saver.send_text(json.dumps({
                "type": "request_save",
                "note_id": self.note_id,
            }))
        except Exception:
            pass

    @property
    def is_empty(self) -> bool:
        return len(self.clients) == 0

    @property
    def idle_seconds(self) -> float:
        return time.time() - self.last_activity


class YjsDocumentStore:
    """
    Manages all active Y.js rooms.

    Rooms are created on-demand when a client connects and evicted
    after a period of inactivity with no connections.
    """

    EVICTION_TIMEOUT = 300  # 5 minutes

    def __init__(self):
        self.rooms: Dict[str, YjsRoom] = {}
        self._cleanup_task: Optional[asyncio.Task] = None

    def get_or_create_room(self, note_id: str, persist: bool = True) -> YjsRoom:
        if note_id not in self.rooms:
            self.rooms[note_id] = YjsRoom(note_id, persist=persist)
        return self.rooms[note_id]

    def remove_room(self, note_id: str):
        self.rooms.pop(note_id, None)

    def start_cleanup_loop(self):
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self):
        while True:
            await asyncio.sleep(60)
            to_remove = []
            for note_id, room in self.rooms.items():
                if room.is_empty and room.idle_seconds > self.EVICTION_TIMEOUT:
                    to_remove.append(note_id)
            for nid in to_remove:
                logger.info(f"Evicting idle Y.js room: {nid}")
                self.rooms.pop(nid, None)


# Global singleton
yjs_store = YjsDocumentStore()


async def _on_remote_frame(payload: dict) -> None:
    room = yjs_store.rooms.get(payload.get("note") or "")
    if room is None or room.is_empty:
        return
    from utils.ws_bus import unb64
    try:
        data = unb64(payload.get("data") or "")
    except Exception:
        return
    await room._relay_local(None, data)


async def _on_remote_peer_gone(payload: dict) -> None:
    room = yjs_store.rooms.get(payload.get("note") or "")
    if room is None or payload.get("client_id") is None:
        return
    await room._send_peer_gone_local(payload["client_id"])


def _register_bus_handlers() -> None:
    from utils.ws_bus import bus
    bus.register("yjs_frame", _on_remote_frame)
    bus.register("yjs_peer_gone", _on_remote_peer_gone)


_register_bus_handlers()


async def save_note_content(note_id: str, content: str, user_id: str) -> bool:
    """Persist note content to the database. False if the note is gone or
    the write failed (the editor shows "Not saved"), like save_collab_field."""
    try:
        from database import AsyncSessionLocal
        from models.note import Note
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Note).where(Note.id == note_id))
            note = result.scalar_one_or_none()
            if not note:
                return False

            if (note.content or "") == content:
                # Opening a note, or a save request after cursor moves only,
                # sends back the content as it is: not an edit, so leave
                # updated_by / updated_at alone.
                return True
            engagement_id = note.engagement_id
            note_title = note.title

            # A single collaborative edit session produces a stream of ~3s
            # autosaves. We coalesce that stream into one audit entry AND one
            # pre-edit version snapshot per NOTE_UPDATE_LOG_DEBOUNCE window,
            # keyed off whether a recent "updated_note" log already exists.
            # The same decision gates both so they stay correlated — the feed's
            # diff logic pairs a log with the snapshot taken just before it.
            starts_session = bool(
                engagement_id and not await _recent_note_log_exists(db, note_id)
            )

            if starts_session:
                # Snapshot the PRE-edit state (note.content is still the old
                # value here) so the activity feed can diff session-start →
                # current content instead of showing a bare "edited note" line.
                # Passing the new content as update_data makes the snapshotter
                # record the old value and mark `content` as the changed field.
                from utils.versioning import create_version_snapshot
                await create_version_snapshot(db, note, "note", {"content": content}, user_id)

            note.content = content
            note.updated_by = user_id
            note.updated_at = datetime.utcnow()
            await db.commit()
            logger.debug(f"Y.js persisted note {note_id}")

            if starts_session:
                await _log_note_update(db, engagement_id, note_id, note_title, user_id)
            return True
    except Exception as e:
        logger.warning(f"Y.js save_note_content error: {e}")
        return False


async def _recent_note_log_exists(db, note_id: str) -> bool:
    """True if an 'updated_note' log for this note falls within the debounce
    window — i.e. an edit session is already underway."""
    from models.discussion import ActivityLog
    from sqlalchemy import select

    cutoff = datetime.utcnow() - NOTE_UPDATE_LOG_DEBOUNCE
    recent = await db.execute(
        select(ActivityLog.id)
        .where(
            ActivityLog.resource_type == "note",
            ActivityLog.resource_id == note_id,
            ActivityLog.action == "updated_note",
            ActivityLog.created_at >= cutoff,
        )
        .limit(1)
    )
    return recent.scalar_one_or_none() is not None


async def _log_note_update(db, engagement_id: str, note_id: str, note_title: str, user_id: str):
    """Write the one 'updated_note' activity log that opens an edit session."""
    try:
        from utils.collaboration import create_activity_log

        await create_activity_log(
            db,
            engagement_id=engagement_id,
            user_id=user_id,
            action="updated_note",
            resource_type="note",
            resource_id=note_id,
            resource_name=note_title,
            details="Edited note content",
        )
    except Exception as e:
        logger.warning(f"Y.js note-update activity log error: {e}")
