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


class YjsRoom:
    """
    A room represents a single Y.js document (one per note).

    The server acts as a pure relay: it forwards all binary messages
    (sync protocol + awareness) between connected clients. The CRDT
    merging and awareness protocol happen entirely in the clients.
    """

    def __init__(self, note_id: str):
        self.note_id = note_id
        self.clients: Set[WebSocket] = set()
        self.client_user_ids: Dict[WebSocket, str] = {}  # ws → user_id for save
        self.client_yjs_ids: Dict[WebSocket, int] = {}   # ws → Y.js clientID for awareness cleanup
        self.last_activity = time.time()
        self._save_task: Optional[asyncio.Task] = None

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
        self.last_activity = time.time()
        return yjs_id

    async def notify_peer_disconnected(self, yjs_client_id: int):
        """Tell remaining clients to remove a disconnected peer's awareness state."""
        if not self.clients or yjs_client_id is None:
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
        for d in dead:
            self.clients.discard(d)
            self.client_user_ids.pop(d, None)
            self.client_yjs_ids.pop(d, None)

    async def relay_binary(self, sender: WebSocket, data: bytes):
        """
        Relay a binary message to all clients EXCEPT the sender.

        Binary messages contain Y.js sync protocol (doc updates, sync steps)
        and awareness protocol data. The server does not interpret them —
        it simply forwards to all other connected peers.
        """
        self.last_activity = time.time()

        dead = []
        for client in self.clients:
            if client is sender:
                continue
            try:
                await client.send_bytes(data)
            except Exception:
                dead.append(client)

        for d in dead:
            self.clients.discard(d)
            self.client_user_ids.pop(d, None)

        # Schedule a debounced DB save
        self._schedule_save()

    def _schedule_save(self):
        """Schedule a debounced save to the database."""
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

        saver = next(iter(self.clients))
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

    def get_or_create_room(self, note_id: str) -> YjsRoom:
        if note_id not in self.rooms:
            self.rooms[note_id] = YjsRoom(note_id)
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


async def save_note_content(note_id: str, content: str, user_id: str):
    """Persist note content to the database."""
    try:
        from database import AsyncSessionLocal
        from models.note import Note
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Note).where(Note.id == note_id))
            note = result.scalar_one_or_none()
            if not note:
                return

            changed = (note.content or "") != content
            engagement_id = note.engagement_id
            note_title = note.title

            # A single collaborative edit session produces a stream of ~3s
            # autosaves. We coalesce that stream into one audit entry AND one
            # pre-edit version snapshot per NOTE_UPDATE_LOG_DEBOUNCE window,
            # keyed off whether a recent "updated_note" log already exists.
            # The same decision gates both so they stay correlated — the feed's
            # diff logic pairs a log with the snapshot taken just before it.
            starts_session = bool(
                changed and engagement_id and not await _recent_note_log_exists(db, note_id)
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
    except Exception as e:
        logger.warning(f"Y.js save_note_content error: {e}")


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
