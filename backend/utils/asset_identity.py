"""Matching assets by identifier.

An asset's identifier (IP, hostname, URL) is unique within its engagement,
ignoring case and surrounding whitespace — the database enforces it with
uq_assets_engagement_identifier_ci on (engagement_id, lower(btrim(identifier))).
Every place that creates or looks up an asset by identifier goes through
these helpers so they agree on what "the same host" means (imports matched
case-insensitively, spray case-sensitively, single create not at all).
"""
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.asset import Asset


def normalize_identifier(raw: str) -> str:
    """The stored form: surrounding whitespace removed, case kept."""
    return (raw or "").strip()


def identifier_key(raw: str) -> str:
    """The comparison form, matching the unique index."""
    return normalize_identifier(raw).lower()


async def load_assets_by_key(db: AsyncSession, engagement_id: str, *, with_ports: bool = False) -> dict[str, Asset]:
    """Every asset in the engagement keyed by identifier_key — for imports,
    which match many rows against the existing set in memory."""
    q = select(Asset).where(Asset.engagement_id == engagement_id)
    if with_ports:
        q = q.options(selectinload(Asset.ports))
    return {identifier_key(a.identifier): a for a in (await db.execute(q)).scalars().all()}


async def find_asset(db: AsyncSession, engagement_id: str, identifier: str,
                     *, exclude_id: Optional[str] = None) -> Optional[Asset]:
    """The engagement's asset with this identifier, if any."""
    q = select(Asset).where(
        Asset.engagement_id == engagement_id,
        func.lower(func.btrim(Asset.identifier)) == identifier_key(identifier),
    )
    if exclude_id:
        q = q.where(Asset.id != exclude_id)
    return (await db.execute(q.limit(1))).scalars().first()
