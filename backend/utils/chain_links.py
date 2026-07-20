"""Helpers for keeping chain_links referentially consistent.

chain_links endpoints are polymorphic (type, id) pairs with no DB-level
foreign key to the entity tables, so when a testcase / finding / vault item
is deleted we sweep the edges it participated in here. Call this BEFORE the
entity row is deleted and committed.
"""
from sqlalchemy import or_, and_, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from models.chain_link import ChainLink


async def sweep_chain_links(db: AsyncSession, entity_type: str, entity_ids):
    """Delete every chain edge in which any of ``entity_ids`` appears as
    source or target. Does not commit — the caller's delete/commit covers it.

    ``entity_ids`` may be a single id or an iterable of ids (for cascade
    deletes). No-op on an empty set.
    """
    if isinstance(entity_ids, str):
        entity_ids = [entity_ids]
    ids = [i for i in entity_ids if i]
    if not ids:
        return
    await db.execute(
        sa_delete(ChainLink).where(
            or_(
                and_(ChainLink.source_type == entity_type, ChainLink.source_id.in_(ids)),
                and_(ChainLink.target_type == entity_type, ChainLink.target_id.in_(ids)),
            )
        )
    )
