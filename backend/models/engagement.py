from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, Enum as SQLEnum, ForeignKey
from sqlalchemy.orm import relationship
from database import Base, AuditMixin
from models.associations import EngagementAssignment

from datetime import datetime
import uuid
import enum

class EngagementStatus(str, enum.Enum):
    PROPOSED = "PROPOSED"
    PLANNING = "PLANNING"
    IN_PROGRESS = "IN_PROGRESS"
    REPORTING = "REPORTING"
    COMPLETED = "COMPLETED"
    ON_HOLD = "ON_HOLD"

class Engagement(Base, AuditMixin):
    __tablename__ = "engagements"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False, index=True)
    client_name = Column(String(255), nullable=False)
    client_id = Column(String, ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True)
    engagement_type = Column(String(100), nullable=False)
    status = Column(SQLEnum(EngagementStatus), default=EngagementStatus.PLANNING, nullable=False)
    description = Column(Text)
    scope = Column(Text)
    objectives = Column(Text)
    start_date = Column(DateTime)
    end_date = Column(DateTime)

    # Relationships
    client = relationship("Client", back_populates="engagements")
    created_by_user = relationship("User", back_populates="created_engagements", foreign_keys="Engagement.created_by")
    updated_by_user = relationship("User", foreign_keys="Engagement.updated_by")
    assignment_details = relationship("EngagementAssignment", back_populates="engagement", cascade="all, delete-orphan")
    assigned_users = relationship(
        "User", 
        secondary="engagement_assignments", 
        primaryjoin="Engagement.id == EngagementAssignment.engagement_id",
        secondaryjoin="EngagementAssignment.user_id == User.id",
        back_populates="assigned_engagements", 
        viewonly=True
    )
    findings = relationship("Finding", back_populates="engagement", cascade="all, delete-orphan")
    assets = relationship("Asset", back_populates="engagement", cascade="all, delete-orphan")
    testcases = relationship("TestCase", back_populates="engagement", cascade="all, delete-orphan")
    evidence = relationship("Evidence", back_populates="engagement", cascade="all, delete-orphan")
    threads = relationship("Thread", back_populates="engagement", cascade="all, delete-orphan")
    # GHSA-9h56-fv6g-5x98: deliberately NOT cascade-deleted. Activity log rows
    # must outlive their parent engagement so an "engagement deleted by user X"
    # tombstone (and every prior action under that engagement) survives the
    # delete commit. FK is ON DELETE SET NULL — see ActivityLog.engagement_id.
    activity_logs = relationship("ActivityLog", back_populates="engagement", passive_deletes=True)
    vault_items = relationship("VaultItem", back_populates="engagement", cascade="all, delete-orphan")
    cleanup_artifacts = relationship("CleanupArtifact", back_populates="engagement", cascade="all, delete-orphan")
    phases = relationship("EngagementPhase", backref="engagement", cascade="all, delete-orphan", order_by="EngagementPhase.sort_order")
    required_skills = relationship("EngagementSkill", back_populates="engagement", cascade="all, delete-orphan")
