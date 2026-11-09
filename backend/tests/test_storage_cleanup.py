"""Deleting an engagement or finding removes the MinIO objects behind the
evidence / vault / markdown-image rows it cascades away."""

from __future__ import annotations

import uuid

import pytest

from tests.test_authz_boundaries import _make_engagement, _make_finding


@pytest.fixture
def deleted_keys(monkeypatch):
    from utils.storage import storage_service
    keys = []

    async def fake_delete(key):
        keys.append(key)
    monkeypatch.setattr(storage_service, "delete_file", fake_delete)
    return keys


async def _evidence(db, eng, finding=None):
    from models.evidence import Evidence
    key = f"evidence/{uuid.uuid4().hex}.png"
    db.add(Evidence(id=str(uuid.uuid4()), engagement_id=eng.id, finding_id=finding.id if finding else None,
                    filename="a.png", original_filename="a.png", file_path=key, mime_type="image/png",
                    file_size=1))
    await db.flush()
    return key


async def test_engagement_delete_removes_objects(client, db_session, make_user, authenticate_as, deleted_keys):
    from models.markdown_image import MarkdownImage
    from models.vault import VaultItem
    eng = await _make_engagement(db_session)
    ev = await _evidence(db_session, eng, await _make_finding(db_session, eng))
    db_session.add(VaultItem(id=str(uuid.uuid4()), engagement_id=eng.id, name="f", item_type="FILE",
                             file_path="vault/x.bin"))
    db_session.add(MarkdownImage(id=str(uuid.uuid4()), engagement_id=eng.id, storage_key="markdown/y.png",
                                 content_type="image/png", size_bytes=1))
    await db_session.flush()
    authenticate_as(await make_user(role="admin"))
    assert (await client.delete(f"/engagements/{eng.id}")).status_code == 204
    assert sorted(deleted_keys) == sorted([ev, "vault/x.bin", "markdown/y.png"])


async def test_finding_delete_removes_its_evidence_objects(client, db_session, make_user, authenticate_as,
                                                           deleted_keys):
    eng = await _make_engagement(db_session)
    finding = await _make_finding(db_session, eng)
    mine, other = await _evidence(db_session, eng, finding), await _evidence(db_session, eng)
    authenticate_as(await make_user(role="admin"))
    assert (await client.delete(f"/findings/{finding.id}")).status_code == 204
    assert deleted_keys == [mine]
