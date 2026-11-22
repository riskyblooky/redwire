"""Remove the MinIO objects behind rows a delete is about to cascade away.

Deleting an engagement or finding removes the Evidence / VaultItem /
MarkdownImage rows through ORM or FK cascades, but the stored objects
themselves aren't touched by either, so they stayed in the bucket with
nothing pointing at them. Collect the keys before the delete, then remove
them once it has committed (a failed delete must not lose files).
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def engagement_object_keys(db: AsyncSession, engagement_id: str) -> list[str]:
    from sqlalchemy import or_
    from models.evidence import Evidence
    from models.finding import Finding
    from models.markdown_image import MarkdownImage
    from models.testcase import TestCase
    from models.vault import VaultItem
    keys: list[str] = []
    # Legacy evidence rows may have no engagement_id, only a finding or test
    # case; matching on engagement_id alone left their objects behind.
    evidence_in_engagement = or_(
        Evidence.engagement_id == engagement_id,
        Evidence.finding_id.in_(select(Finding.id).where(Finding.engagement_id == engagement_id)),
        Evidence.testcase_id.in_(select(TestCase.id).where(TestCase.engagement_id == engagement_id)),
    )
    for col, where in (
        (Evidence.file_path, evidence_in_engagement),
        (VaultItem.file_path, VaultItem.engagement_id == engagement_id),
        (MarkdownImage.storage_key, MarkdownImage.engagement_id == engagement_id),
    ):
        keys += [k for k in (await db.execute(select(col).where(where))).scalars().all() if k]
    return list(dict.fromkeys(keys))


async def finding_object_keys(db: AsyncSession, finding_id: str) -> list[str]:
    from models.evidence import Evidence
    rows = await db.execute(select(Evidence.file_path).where(Evidence.finding_id == finding_id))
    return [k for k in rows.scalars().all() if k]


async def drop_testcase_evidence(db: AsyncSession, testcase_ids: list[str]) -> list[str]:
    """Evidence of test cases about to be deleted, handled like a finding's.

    The FK has no delete rule, so the ORM used to null ``testcase_id`` and
    leave the files as loose engagement evidence nobody had uploaded as
    such. Evidence that belongs only to these test cases is deleted (its
    object keys are returned for removal after the commit); evidence that
    is also on a finding stays with the finding, just detached."""
    from models.evidence import Evidence
    if not testcase_ids:
        return []
    rows = (await db.execute(select(Evidence).where(Evidence.testcase_id.in_(testcase_ids)))).scalars().all()
    keys: list[str] = []
    for ev in rows:
        if ev.finding_id:
            ev.testcase_id = None
        else:
            if ev.file_path:
                keys.append(ev.file_path)
            await db.delete(ev)
    await db.flush()
    return keys


async def delete_objects(keys: list[str]) -> int:
    """Best effort: a missing or undeletable object is logged, not raised —
    the rows are already gone, so there's nothing to roll back to."""
    from utils.storage import storage_service
    removed = 0
    for key in dict.fromkeys(keys):
        try:
            await storage_service.delete_file(key)
            removed += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("storage cleanup: could not delete %s: %s", key, e)
    return removed
