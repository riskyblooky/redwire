"""Keep object storage in step with the database transaction.

MinIO writes aren't transactional, so two shapes went wrong:

- **upload, then commit**: when the commit (or anything between) failed,
  the object stayed in the bucket with no row pointing at it;
- **delete object, then row**: when the row delete failed, the row stayed
  and pointed at an object that was gone.

Use these instead of calling ``storage_service`` directly in a request:

- ``await upload(db, body, key, content_type)`` uploads now and records the
  key on the session. If the session's transaction ends without a commit,
  the object is deleted.
- ``delete_after_commit(db, key)`` queues a delete that runs only once the
  transaction that removes the row has committed.

The work runs in ``settle(db)``, which ``get_db`` awaits when the request's
session closes. Sessions opened by hand (background jobs) call it
themselves.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import event
from sqlalchemy.orm import Session

from utils.storage import storage_service

logger = logging.getLogger(__name__)

_KEY = "storage_tx"


def _state(sync_session: Session) -> dict:
    return sync_session.info.setdefault(_KEY, {"staged": [], "queued": [], "orphans": [], "ready": []})


def _sync(db) -> Session:
    return getattr(db, "sync_session", db)


async def upload(db, body: bytes, key: str, content_type: Optional[str] = None) -> str:
    """Upload ``body`` and tie the object to ``db``'s transaction."""
    result = await storage_service.upload_file(body, key, content_type)
    _state(_sync(db))["staged"].append(key)
    return result


def delete_after_commit(db, key: Optional[str]) -> None:
    """Delete ``key`` once the current transaction commits (never if it rolls back)."""
    if key:
        _state(_sync(db))["queued"].append(key)


# Savepoints (begin_nested) fire these events too: releasing one fires
# after_commit, rolling one back fires after_rollback. Only the outer
# transaction decides whether rows exist, so savepoint events are ignored
# (a failed audit-log savepoint must not delete the upload it sits beside).

@event.listens_for(Session, "after_commit")
def _after_commit(session: Session) -> None:
    st = session.info.get(_KEY)
    if st and not session.in_nested_transaction():
        st["staged"].clear()               # their rows are committed now
        st["ready"].extend(st["queued"])   # the rows are gone: delete the objects
        st["queued"].clear()


@event.listens_for(Session, "after_rollback")
def _after_rollback(session: Session) -> None:
    st = session.info.get(_KEY)
    if st and not session.in_nested_transaction():
        st["orphans"].extend(st["staged"])  # no row will point at these
        st["staged"].clear()
        st["queued"].clear()                # the rows are still there: keep the objects


async def _delete(key: str, why: str) -> None:
    try:
        await storage_service.delete_file(key)
    except Exception as exc:  # storage hiccup: log it, don't fail the request
        logger.warning("storage_tx: could not delete %s object %s: %s", why, key, exc)


async def settle(db) -> None:
    """Apply what the transaction decided. Uploads that were never committed
    are deleted too (the session is closing without having committed them)."""
    st = _sync(db).info.get(_KEY)
    if not st:
        return
    orphans = st["orphans"] + st["staged"]
    ready = st["ready"]
    st.update(staged=[], queued=[], orphans=[], ready=[])
    for key in orphans:
        await _delete(key, "uncommitted")
    for key in ready:
        await _delete(key, "deleted-row")
