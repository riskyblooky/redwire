"""
cluster.py — small Redis helpers for running more than one backend worker.

``claim(name, ttl)`` is a cluster-wide "only one worker does this" lock
(SET NX EX); ``sync_redis()`` / ``async_redis()`` return a shared client or
None when Redis is unreachable. Without Redis everything behaves as a single
process: ``claim`` always succeeds.
"""
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_RETRY_AFTER = 30  # seconds before retrying an unreachable Redis

_sync = None
_sync_failed_at = 0.0
_async = None
_async_failed_at = 0.0


def sync_redis():
    """Binary-safe sync client (decode_responses=False), or None."""
    global _sync, _sync_failed_at
    if _sync is not None:
        return _sync
    if time.monotonic() - _sync_failed_at < _RETRY_AFTER:
        return None
    try:
        import redis
        client = redis.from_url(REDIS_URL, socket_connect_timeout=2)
        client.ping()
        _sync = client
        return _sync
    except Exception as e:
        _sync_failed_at = time.monotonic()
        logger.warning("cluster: Redis unavailable (sync): %s", e)
        return None


async def async_redis():
    """Binary-safe asyncio client, or None."""
    global _async, _async_failed_at
    if _async is not None:
        return _async
    if time.monotonic() - _async_failed_at < _RETRY_AFTER:
        return None
    try:
        import redis.asyncio as aioredis
        client = aioredis.from_url(REDIS_URL, socket_connect_timeout=2)
        await client.ping()
        _async = client
        return _async
    except Exception as e:
        _async_failed_at = time.monotonic()
        logger.warning("cluster: Redis unavailable (async): %s", e)
        return None


def reset_clients() -> None:
    """Drop cached clients (tests; or after a fork)."""
    global _sync, _async, _sync_failed_at, _async_failed_at
    _sync = _async = None
    _sync_failed_at = _async_failed_at = 0.0


async def claim(name: str, ttl_seconds: int) -> bool:
    r = await async_redis()
    if r is None:
        return True
    try:
        return bool(await r.set(f"rw:claim:{name}", b"1", nx=True, ex=max(1, int(ttl_seconds))))
    except Exception:
        return True


# ── Startup serialisation ──────────────────────────────────────────────────
# Every worker runs the lifespan's one-time work (admin bootstrap, seeding,
# backfills). Each step is idempotent, but on a fresh database two workers
# can both see "missing" and collide on a unique insert. A Postgres advisory
# lock makes workers take turns; the later ones find the work already done.
# Held on a dedicated connection; released explicitly, or by Postgres if
# the worker dies.
_STARTUP_LOCK_KEY = 0x5277_5374  # "RwSt"


async def acquire_startup_lock():
    from sqlalchemy import text
    from database import engine
    conn = await engine.connect()
    conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
    await conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": _STARTUP_LOCK_KEY})
    return conn


async def release_startup_lock(conn) -> None:
    from sqlalchemy import text
    try:
        await conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _STARTUP_LOCK_KEY})
    finally:
        await conn.close()
