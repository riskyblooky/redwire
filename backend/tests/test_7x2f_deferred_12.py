"""GHSA-7x2f-ff7r-h388 deferred #12 — version-history race.

Two layers: the (entity_type, entity_id, version) unique constraint
refuses a losing concurrent writer, and create_version_snapshot retries
inside a SAVEPOINT, re-reading MAX, so the caller's update survives and
its snapshot lands on the next free version.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError

from tests.test_authz_boundaries import _make_engagement, _make_finding


def _row(entity_id, version, **kw):
    return dict(id=str(uuid.uuid4()), entity_type="finding", entity_id=entity_id,
                version=version, snapshot={}, changed_fields=[], **kw)


async def test_duplicate_version_is_refused_by_the_database(db_session):
    from models.version_history import VersionHistory

    eid = str(uuid.uuid4())
    await db_session.execute(insert(VersionHistory).values(**_row(eid, 1)))
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await db_session.execute(insert(VersionHistory).values(**_row(eid, 1)))


async def test_snapshot_retries_past_a_concurrent_writer(db_session, make_user, monkeypatch):
    from models.version_history import VersionHistory
    from utils.versioning import create_version_snapshot

    user = await make_user()
    eng = await _make_engagement(db_session)
    finding = await _make_finding(db_session, eng, created_by=user.id)

    # Another writer takes version 1 between our MAX read and our INSERT.
    real_execute = db_session.execute
    raced = []

    async def racing_execute(stmt, *a, **k):
        result = await real_execute(stmt, *a, **k)
        if not raced and "max(version_history.version)" in str(stmt).lower():
            raced.append(True)
            await real_execute(insert(VersionHistory).values(**_row(finding.id, 1)))
        return result
    monkeypatch.setattr(db_session, "execute", racing_execute)

    await create_version_snapshot(db_session, finding, "finding", {"title": "new title"}, user.id)

    monkeypatch.setattr(db_session, "execute", real_execute)
    rows = (await db_session.execute(
        select(VersionHistory.version, VersionHistory.changed_by)
        .where(VersionHistory.entity_id == finding.id).order_by(VersionHistory.version)
    )).all()
    assert raced
    assert [r.version for r in rows] == [1, 2]
    assert rows[1].changed_by == user.id  # ours, on the retry
