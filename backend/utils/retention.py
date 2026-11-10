"""Periodic pruning of the append-only tables that otherwise grow forever.

Windows (days; 0 keeps everything):
  ACTIVITY_PING_RETENTION_DAYS   default 365 — effort-metric pings
  NOTIFICATION_RETENTION_DAYS    default 90  — *read* notifications only
  ACTIVITY_LOG_RETENTION_DAYS    default 0   — the audit trail: opt-in

Every worker runs the loop; the deletes are idempotent, so two workers
pruning the same day just find nothing the second time.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta

from sqlalchemy import delete

logger = logging.getLogger(__name__)

_FIRST_RUN_DELAY_S = 300
_INTERVAL_S = 24 * 3600


def _days(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, str(default))))
    except ValueError:
        return default


async def prune_once(db) -> dict:
    from models.activity_ping import ActivityPing
    from models.notification import Notification
    from models.discussion import ActivityLog

    now = datetime.utcnow()
    removed = {}
    plan = (
        ("activity_pings", ActivityPing, _days("ACTIVITY_PING_RETENTION_DAYS", 365), ()),
        ("notifications", Notification, _days("NOTIFICATION_RETENTION_DAYS", 90), (Notification.is_read.is_(True),)),
        ("activity_logs", ActivityLog, _days("ACTIVITY_LOG_RETENTION_DAYS", 0), ()),
    )
    for name, model, days, extra in plan:
        if not days:
            continue
        result = await db.execute(
            delete(model).where(model.created_at < now - timedelta(days=days), *extra)
        )
        removed[name] = result.rowcount or 0
    await db.commit()
    return removed


async def retention_loop(session_factory) -> None:
    await asyncio.sleep(_FIRST_RUN_DELAY_S)
    while True:
        try:
            async with session_factory() as db:
                removed = await prune_once(db)
            if any(removed.values()):
                logger.info("retention: pruned %s", removed)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("retention: prune failed: %s", e)
        await asyncio.sleep(_INTERVAL_S)


def evict_stale(cache: dict, now: float, max_age: float, max_size: int = 10_000) -> None:
    """Bound a {key: monotonic timestamp} throttle cache: once it passes
    max_size, drop entries older than max_age (they'd pass the throttle
    anyway, so dropping them changes nothing)."""
    if len(cache) <= max_size:
        return
    for k in [k for k, t in cache.items() if now - t >= max_age]:
        cache.pop(k, None)
