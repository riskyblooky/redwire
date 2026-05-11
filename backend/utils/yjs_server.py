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
from datetime import datetime

logger = logging.getLogger(__name__)


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
            if note:
                note.content = content
                note.updated_by = user_id
                note.updated_at = datetime.utcnow()
                await db.commit()
                logger.debug(f"Y.js persisted note {note_id}")
    except Exception as e:
        logger.warning(f"Y.js save_note_content error: {e}")
