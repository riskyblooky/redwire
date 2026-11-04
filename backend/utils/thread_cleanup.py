"""Delete the discussion threads that belong to a deleted entity.

Thread.resource_id is polymorphic (no DB FK), so deleting a finding, test
case, asset, etc. would otherwise leave its threads behind: they still list
under the engagement's discussions with a link to nothing.
"""
from __future__ import annotations

from sqlalchemy import delete as sa_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.discussion import Comment, Thread


async def sweep_threads(db: AsyncSession, resource_types, resource_ids) -> None:
    """Delete threads (and their comments) on any of ``resource_ids`` whose
    resource_type is in ``resource_types``. Either argument may be a single
    string. Does not commit — the caller's delete/commit covers it."""
    if isinstance(resource_types, str):
        resource_types = [resource_types]
    if isinstance(resource_ids, str):
        resource_ids = [resource_ids]
    ids = [i for i in resource_ids if i]
    if not ids:
        return
    where = (Thread.resource_type.in_(list(resource_types)), Thread.resource_id.in_(ids))
    await db.execute(sa_delete(Comment).where(Comment.thread_id.in_(select(Thread.id).where(*where))))
    await db.execute(sa_delete(Thread).where(*where))
