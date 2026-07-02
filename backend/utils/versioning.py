"""Versioning utilities for snapshotting entity state on updates."""
import logging
from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# GHSA-7x2f-ff7r-h388 #12 (CWE-362): retry cap on the read-MAX +
# insert path. The composite unique index on VersionHistory
# (entity_type, entity_id, version) — restored by the 199be698dd4a
# Alembic revision — will reject an INSERT that collides with a
# concurrent writer that beat us to version N+1. On collision we
# re-read MAX and try again; five attempts is well past any
# realistic concurrent-write burst (auto-save + explicit save on
# the same finding would produce at most two contenders).
_VERSION_INSERT_MAX_RETRIES = 5

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

    # GHSA-7x2f-ff7r-h388 #12: retry-on-collision loop. Read MAX,
    # attempt INSERT; if the DB's unique constraint rejects, another
    # writer beat us to that slot — refresh MAX and try again. Uses
    # a nested SAVEPOINT (`db.begin_nested()`) so a rejected INSERT
    # only rolls back the version-history write, not the caller's
    # main entity update in the outer transaction.
    for attempt in range(_VERSION_INSERT_MAX_RETRIES):
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
        try:
            async with db.begin_nested():
                db.add(version)
            # Nested commit worked — the row is in and the unique
            # constraint accepted it. Done.
            logger.info(
                "Created %s version %d for %s (attempt %d)",
                entity_type, next_version, entity.id, attempt + 1,
            )
            return
        except IntegrityError:
            # Another writer got there first. `begin_nested()` already
            # rolled back the SAVEPOINT so the outer transaction is
            # unaffected — just loop and re-read MAX.
            logger.info(
                "Version-history collision for %s %s at version %d; retrying "
                "(attempt %d of %d)",
                entity_type, entity.id, next_version,
                attempt + 1, _VERSION_INSERT_MAX_RETRIES,
            )

    # If we exhausted the retry budget, something unusual is going
    # on (write storm on a single entity). Log and give up on the
    # version snapshot rather than fail the caller's main update —
    # the audit trail loses one entry, the operator keeps their
    # update.
    logger.warning(
        "Version-history INSERT for %s %s failed after %d retries; "
        "dropping the snapshot but continuing the update.",
        entity_type, entity.id, _VERSION_INSERT_MAX_RETRIES,
    )
