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
    from models.evidence import Evidence
    from models.markdown_image import MarkdownImage
    from models.vault import VaultItem
    keys: list[str] = []
    for col, where in (
        (Evidence.file_path, Evidence.engagement_id == engagement_id),
        (VaultItem.file_path, VaultItem.engagement_id == engagement_id),
        (MarkdownImage.storage_key, MarkdownImage.engagement_id == engagement_id),
    ):
        keys += [k for k in (await db.execute(select(col).where(where))).scalars().all() if k]
    return keys


async def finding_object_keys(db: AsyncSession, finding_id: str) -> list[str]:
    from models.evidence import Evidence
    rows = await db.execute(select(Evidence.file_path).where(Evidence.finding_id == finding_id))
    return [k for k in rows.scalars().all() if k]


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
