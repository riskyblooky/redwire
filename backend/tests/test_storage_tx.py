"""Storage stays in step with the transaction: uncommitted uploads are
removed, deletes wait for the row's delete to commit, and savepoints (the
activity log's, for one) don't decide anything."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from utils import storage_tx
from utils.storage import storage_service


async def _exists(key: str) -> bool:
    try:
        await storage_service.download_file(key)
        return True
    except Exception:
        return False


def _key():
    return f"test-storage-tx/{uuid.uuid4()}.bin"


async def test_upload_rolled_back_is_deleted(db_session):
    key = _key()
    await storage_tx.upload(db_session, b"x", key)
    await db_session.rollback()
    await storage_tx.settle(db_session)
    assert not await _exists(key)


async def test_upload_never_committed_is_deleted(db_session):
    """An HTTPException before the commit: the session just closes."""
    key = _key()
    await storage_tx.upload(db_session, b"x", key)
    await storage_tx.settle(db_session)
    assert not await _exists(key)


async def test_committed_upload_stays(db_session):
    key = _key()
    await storage_tx.upload(db_session, b"x", key)
    await db_session.commit()
    await storage_tx.settle(db_session)
    assert await _exists(key)
    await storage_service.delete_file(key)


async def test_failed_savepoint_keeps_the_upload(db_session):
    key = _key()
    await storage_tx.upload(db_session, b"x", key)
    with pytest.raises(Exception):
        async with db_session.begin_nested():
            await db_session.execute(text("select 1/0"))
    await db_session.commit()
    await storage_tx.settle(db_session)
    assert await _exists(key)
    await storage_service.delete_file(key)


async def test_delete_waits_for_commit(db_session):
    key = _key()
    await storage_service.upload_file(b"x", key)
    storage_tx.delete_after_commit(db_session, key)
    await db_session.rollback()            # the row delete failed
    await storage_tx.settle(db_session)
    assert await _exists(key)

    storage_tx.delete_after_commit(db_session, key)
    await db_session.commit()
    await storage_tx.settle(db_session)
    assert not await _exists(key)


async def test_evidence_delete_that_fails_keeps_the_file(client, db_session, make_user, authenticate_as, monkeypatch):
    from models.evidence import Evidence
    from tests.test_authz_boundaries import _make_engagement
    eng = await _make_engagement(db_session)
    key = _key()
    await storage_service.upload_file(b"evidence", key)
    ev = Evidence(id=str(uuid.uuid4()), engagement_id=eng.id, filename=key, original_filename="e.bin",
                  file_path=key, file_size=8)
    db_session.add(ev)
    await db_session.commit()  # survives the failed delete's rollback below
    ev_id = ev.id
    db_session.expunge_all()
    authenticate_as(await make_user(role="admin"))

    real_commit = db_session.commit

    async def failing_commit():
        raise RuntimeError("commit failed")
    monkeypatch.setattr(db_session, "commit", failing_commit)
    with pytest.raises(RuntimeError):
        await client.delete(f"/evidence/{ev_id}")
    monkeypatch.setattr(db_session, "commit", real_commit)
    await db_session.rollback()
    await storage_tx.settle(db_session)
    assert await _exists(key)  # used to be deleted before the row

    assert (await client.delete(f"/evidence/{ev_id}")).status_code in (200, 204)
    await storage_tx.settle(db_session)
    assert not await _exists(key)
