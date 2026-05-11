from sqlalchemy import Column, String, DateTime, Integer, JSON, ForeignKey
from database import Base
from datetime import datetime
import uuid


class VersionHistory(Base):
    """Polymorphic version history for findings and test cases.

    Each row stores a snapshot of the entity's state *before* an update was
    applied, along with which fields changed and who made the change.
    """
    __tablename__ = "version_history"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_type = Column(String(20), nullable=False, index=True)   # "finding" | "testcase"
    entity_id = Column(String, nullable=False, index=True)
    version = Column(Integer, nullable=False)  # auto-incremented per entity
    snapshot = Column(JSON, nullable=False)     # full field values at that point
    changed_fields = Column(JSON, nullable=False, default=list)  # ["description", "severity", ...]
    changed_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
