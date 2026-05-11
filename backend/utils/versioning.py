"""Versioning utilities for snapshotting entity state on updates."""
import logging
from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Fields tracked per entity type
FINDING_VERSIONED_FIELDS = [
    "title", "category", "description", "severity", "status",
    "cvss_score", "cvss_vector", "impact", "technical_details",
    "steps_to_reproduce", "mitigations", "references",
]

TESTCASE_VERSIONED_FIELDS = [
    "title", "category", "description", "steps", "expected_result",
    "actual_result", "is_executed", "is_successful", "notes",
]


def _snapshot_entity(entity, fields: list[str]) -> dict:
    """Build a JSON-serialisable dict of the entity's current field values."""
    snap = {}
    for f in fields:
        val = getattr(entity, f, None)
        # Enums → their string value
        if hasattr(val, "value"):
            val = val.value
        snap[f] = val
    return snap


def _detect_changed_fields(snapshot: dict, update_data: dict) -> list[str]:
    """Return list of field names whose value will change."""
    changed = []
    for field, new_val in update_data.items():
        if field not in snapshot:
            continue
        old_val = snapshot[field]
        # Normalise enum values for comparison
        if hasattr(new_val, "value"):
            new_val = new_val.value
        if old_val != new_val:
            changed.append(field)
    return changed


async def create_version_snapshot(
    db: AsyncSession,
    entity,
    entity_type: str,
    update_data: dict,
    changed_by: str | None,
) -> None:
    """Snapshot current state of *entity* before an update is applied.

    Parameters
    ----------
    db : AsyncSession
    entity : Finding | TestCase  (the SQLAlchemy model instance)
    entity_type : "finding" | "testcase"
    update_data : dict of field→new_value that will be applied
    changed_by : user id
    """
    from models.version_history import VersionHistory

    fields = (
        FINDING_VERSIONED_FIELDS if entity_type == "finding"
        else TESTCASE_VERSIONED_FIELDS
    )

    snapshot = _snapshot_entity(entity, fields)
    changed = _detect_changed_fields(snapshot, update_data)

    if not changed:
        return  # nothing actually changed — skip

    # Determine next version number
    result = await db.execute(
        select(func.coalesce(func.max(VersionHistory.version), 0))
        .where(VersionHistory.entity_type == entity_type)
        .where(VersionHistory.entity_id == entity.id)
    )
    next_version = result.scalar() + 1

    version = VersionHistory(
        entity_type=entity_type,
        entity_id=entity.id,
        version=next_version,
        snapshot=snapshot,
        changed_fields=changed,
        changed_by=changed_by,
        created_at=datetime.utcnow(),
    )
    db.add(version)
    logger.info("Created %s version %d for %s", entity_type, next_version, entity.id)
