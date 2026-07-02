from sqlalchemy import Column, String, DateTime, Integer, JSON, ForeignKey, UniqueConstraint
from database import Base
from datetime import datetime
import uuid


class VersionHistory(Base):
    """Polymorphic version history for findings and test cases.

    Each row stores a snapshot of the entity's state *before* an update was
    applied, along with which fields changed and who made the change.

    GHSA-7x2f-ff7r-h388 #12 (CWE-362): the composite unique index on
    (entity_type, entity_id, version) was accidentally dropped by
    Alembic revision 753bbc1309ea (2026-02-23) because the model
    didn't declare it. Concurrent writers reading `MAX(version)+1`
    both saw the same MAX and both wrote version N+1 — duplicates
    landed silently. Restored the constraint here so the DB enforces
    uniqueness; a companion Alembic revision creates the index and
    dedupes any legacy duplicates first. The versioning helper wraps
    its INSERT in a retry-on-IntegrityError loop so a losing writer
    re-reads MAX and picks the next slot cleanly rather than 500ing.
    """
    __tablename__ = "version_history"
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "version", name="uq_version_history_entity_version"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_type = Column(String(20), nullable=False, index=True)   # "finding" | "testcase"
    entity_id = Column(String, nullable=False, index=True)
    version = Column(Integer, nullable=False)  # auto-incremented per entity
    snapshot = Column(JSON, nullable=False)     # full field values at that point
    changed_fields = Column(JSON, nullable=False, default=list)  # ["description", "severity", ...]
    changed_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
