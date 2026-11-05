"""
ws_bus.py — Redis pub/sub fan-out for WebSocket broadcasts across workers.

``ConnectionManager`` and the Y.js rooms hold sockets in process memory, so a
broadcast only reaches sockets on the worker that made it. This bus makes
multi-worker / multi-replica deployments safe:

  broadcast on worker A  →  deliver to A's local sockets
                         →  PUBLISH rw:ws:bus {origin: A, ...}
  subscriber on worker B →  ignore if origin == B, else deliver to B's sockets

Presence (who is viewing a resource) lives in a Redis hash per channel so the
``active_users`` list covers every worker. Each worker refreshes a liveness
key; presence entries of a worker whose key has expired (crash, OOM kill)
are pruned when read.

Redis being unreachable degrades to the old single-process behaviour: local
delivery still happens, publish is skipped, presence falls back to local
sockets. Set ``WS_FANOUT=false`` to disable the bus entirely.
"""

import asyncio
import base64
import json
import logging
import os
import uuid
from typing import Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

WORKER_ID = uuid.uuid4().hex[:12]
BUS_CHANNEL = "rw:ws:bus"
_PRESENCE_PREFIX = "rw:ws:presence:"
_WORKER_PREFIX = "rw:ws:worker:"
_WORKER_TTL = 30          # seconds; refreshed every _WORKER_TTL / 3
_PRESENCE_TTL = 24 * 3600  # safety net so an abandoned hash can't live forever

Handler = Callable[[dict], Awaitable[None]]


def _enabled() -> bool:
    return os.getenv("WS_FANOUT", "true").strip().lower() not in ("0", "false", "no", "off")


class WsBus:
    def __init__(self) -> None:
        self._redis = None
        self._tasks: List[asyncio.Task] = []
        self._handlers: Dict[str, Handler] = {}
        self._warned = False

    # ── lifecycle ──────────────────────────────────────────────────────────
    @property
    def active(self) -> bool:
        return self._redis is not None

    def register(self, kind: str, handler: Handler) -> None:
        """Handle bus messages of ``kind`` published by *other* workers."""
        self._handlers[kind] = handler

    async def start(self) -> None:
        if not _enabled() or self._redis is not None:
            return
        try:
            import redis.asyncio as aioredis
            client = aioredis.from_url(
                os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True,
            )
            await client.ping()
        except Exception as e:
            logger.warning("ws_bus: Redis unavailable, WebSocket fan-out disabled (single-process mode): %s", e)
            return
        self._redis = client
        await self._heartbeat_once()
        self._tasks = [
            asyncio.create_task(self._listen()),
            asyncio.create_task(self._heartbeat()),
        ]
        logger.info("ws_bus: fan-out active (worker %s)", WORKER_ID)

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        self._tasks = []
        if self._redis is not None:
            try:
                await self._redis.delete(_WORKER_PREFIX + WORKER_ID)
                await self._redis.aclose()
            except Exception:
                pass
        self._redis = None

    # ── publish / subscribe ────────────────────────────────────────────────
    async def publish(self, kind: str, payload: dict) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.publish(BUS_CHANNEL, json.dumps({"o": WORKER_ID, "k": kind, "p": payload}))
            self._warned = False
        except Exception as e:
            if not self._warned:
                logger.warning("ws_bus: publish failed, other workers miss this event: %s", e)
                self._warned = True

    async def _listen(self) -> None:
        backoff = 1
        while True:
            pubsub = None
            try:
                pubsub = self._redis.pubsub()
                await pubsub.subscribe(BUS_CHANNEL)
                backoff = 1
                async for raw in pubsub.listen():
                    if raw.get("type") != "message":
                        continue
                    await self._dispatch(raw.get("data"))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("ws_bus: subscriber error, reconnecting in %ss: %s", backoff, e)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)
            finally:
                if pubsub is not None:
                    try:
                        await pubsub.aclose()
                    except Exception:
                        pass

    async def _dispatch(self, data) -> None:
        try:
            msg = json.loads(data)
        except (TypeError, ValueError):
            return
        if msg.get("o") == WORKER_ID:
            return
        handler = self._handlers.get(msg.get("k"))
        if handler is None:
            return
        try:
            await handler(msg.get("p") or {})
        except Exception as e:
            logger.warning("ws_bus: handler for %r failed: %s", msg.get("k"), e)

    # ── worker liveness ────────────────────────────────────────────────────
    async def _heartbeat_once(self) -> None:
        await self._redis.set(_WORKER_PREFIX + WORKER_ID, "1", ex=_WORKER_TTL)

    async def _heartbeat(self) -> None:
        while True:
            await asyncio.sleep(_WORKER_TTL / 3)
            try:
                await self._heartbeat_once()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.debug("ws_bus: heartbeat failed: %s", e)

    # ── presence registry ──────────────────────────────────────────────────
    @staticmethod
    def _presence_key(resource_type: str, resource_id: str) -> str:
        return f"{_PRESENCE_PREFIX}{resource_type}:{resource_id}"

    async def presence_add(self, resource_type: str, resource_id: str, conn_id: str, user_info: dict) -> None:
        if self._redis is None:
            return
        key = self._presence_key(resource_type, resource_id)
        try:
            await self._redis.hset(key, f"{WORKER_ID}:{conn_id}", json.dumps(user_info))
            await self._redis.expire(key, _PRESENCE_TTL)
        except Exception as e:
            logger.debug("ws_bus: presence_add failed: %s", e)

    async def presence_remove(self, resource_type: str, resource_id: str, conn_id: str) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.hdel(self._presence_key(resource_type, resource_id), f"{WORKER_ID}:{conn_id}")
        except Exception as e:
            logger.debug("ws_bus: presence_remove failed: %s", e)

    async def presence_list(self, resource_type: str, resource_id: str) -> Optional[List[dict]]:
        """User infos connected to the channel on any live worker, or None if
        the registry is unavailable (caller falls back to local sockets)."""
        if self._redis is None:
            return None
        key = self._presence_key(resource_type, resource_id)
        try:
            entries = await self._redis.hgetall(key)
            workers = {f.split(":", 1)[0] for f in entries}
            alive = {}
            for w in workers:
                alive[w] = w == WORKER_ID or bool(await self._redis.exists(_WORKER_PREFIX + w))
            stale = [f for f in entries if not alive[f.split(":", 1)[0]]]
            if stale:
                await self._redis.hdel(key, *stale)
            out = []
            for f, v in entries.items():
                if f in stale:
                    continue
                try:
                    out.append(json.loads(v))
                except ValueError:
                    continue
            return out
        except Exception as e:
            logger.debug("ws_bus: presence_list failed: %s", e)
            return None

    # ── misc ───────────────────────────────────────────────────────────────
    async def claim(self, key: str, ttl_seconds: int) -> bool:
        """Cluster-wide 'only one worker does this' lock (SET NX EX). Always
        True without Redis, so single-process behaviour is unchanged."""
        if self._redis is None:
            return True
        try:
            return bool(await self._redis.set(f"rw:ws:claim:{key}", WORKER_ID, nx=True, ex=ttl_seconds))
        except Exception:
            return True


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def unb64(data: str) -> bytes:
    return base64.b64decode(data)


bus = WsBus()
