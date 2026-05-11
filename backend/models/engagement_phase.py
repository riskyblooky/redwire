from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from database import Base
from datetime import datetime
import uuid


class EngagementPhase(Base):
    __tablename__ = "engagement_phases"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    engagement_id = Column(String, ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False, index=True)
    phase_name = Column(String(50), nullable=False)  # SCOPING, PLANNING, IN_PROGRESS, REPORTING
    sort_order = Column(Integer, nullable=False, default=0)
    planned_start = Column(DateTime, nullable=True)
    planned_end = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Phase name constants
    SCOPING = "SCOPING"
    PLANNING = "PLANNING"
    IN_PROGRESS = "IN_PROGRESS"
    REPORTING = "REPORTING"

    DEFAULT_PHASES = [
        (SCOPING, 0),
        (PLANNING, 1),
        (IN_PROGRESS, 2),
        (REPORTING, 3),
    ]
