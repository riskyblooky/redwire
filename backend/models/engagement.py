from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, Enum as SQLEnum, ForeignKey, JSON, Index, text
from sqlalchemy.orm import relationship
from database import Base, AuditMixin
from models.associations import EngagementAssignment

from datetime import datetime
import uuid
import enum

class EngagementStatus(str, enum.Enum):
    PROPOSED = "PROPOSED"
    SCOPING = "SCOPING"
    PLANNING = "PLANNING"
    IN_PROGRESS = "IN_PROGRESS"
    REPORTING = "REPORTING"
    COMPLETED = "COMPLETED"
    ON_HOLD = "ON_HOLD"

class Engagement(Base, AuditMixin):
    __tablename__ = "engagements"
    # Names are unique ignoring case and surrounding spaces.
    __table_args__ = (Index("uq_engagements_name_ci", text("lower(btrim(name))"), unique=True),)

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

    # Portion marking — the engagement supplies the document-wide *default*
    # (what unmarked portions inherit) and a *ceiling* (the max any portion may
    # be set to). The banner is computed from effective portion marks, not set
    # here. marking_profile_id picks the ladder/idiom (TLP vs IC vs custom).
    marking_profile_id = Column(String, ForeignKey("marking_profiles.id", ondelete="SET NULL"), nullable=True, index=True)
    default_classification_level = Column(String(20), nullable=True)
    default_classification_suffix = Column(String(120), nullable=True)
    ceiling_classification_level = Column(String(20), nullable=True)

    # Admin-defined custom field values, keyed by CustomFieldDefinition.field_key.
    custom_fields = Column(JSON, nullable=True, default=dict)

    # Scoring policy: which finding scoring models this engagement permits
    # (JSON list of model ids; null ⇒ inherit the site policy / all enabled) and
    # the default model for new findings (null ⇒ inherit). See utils/scoring_policy.
    allowed_score_models = Column(JSON, nullable=True)
    default_score_model = Column(String(64), nullable=True)

    # Relationships
    marking_profile = relationship("MarkingProfile")
    client = relationship("Client", back_populates="engagements")
    created_by_user = relationship("User", back_populates="created_engagements", foreign_keys="Engagement.created_by")
    updated_by_user = relationship("User", foreign_keys="Engagement.updated_by")
    assignment_details = relationship("EngagementAssignment", back_populates="engagement", cascade="all, delete-orphan", passive_deletes=True)
    assigned_users = relationship(
        "User", 
        secondary="engagement_assignments", 
        primaryjoin="Engagement.id == EngagementAssignment.engagement_id",
        secondaryjoin="EngagementAssignment.user_id == User.id",
        back_populates="assigned_engagements", 
        viewonly=True
    )
    # passive_deletes: every child FK cascades in the database (ondelete=CASCADE
    # down the whole tree), so deleting an engagement doesn't load its children.
    # Anything that has to happen per child on delete — object storage, version
    # history, plugin data (models/plugin.py) — is done explicitly, not by the ORM.
    findings = relationship("Finding", back_populates="engagement", cascade="all, delete-orphan", passive_deletes=True)
    assets = relationship("Asset", back_populates="engagement", cascade="all, delete-orphan", passive_deletes=True)
    testcases = relationship("TestCase", back_populates="engagement", cascade="all, delete-orphan", passive_deletes=True)
    evidence = relationship("Evidence", back_populates="engagement", cascade="all, delete-orphan", passive_deletes=True)
    threads = relationship("Thread", back_populates="engagement", cascade="all, delete-orphan", passive_deletes=True)
    # GHSA-9h56-fv6g-5x98: deliberately NOT cascade-deleted. Activity log rows
    # must outlive their parent engagement so an "engagement deleted by user X"
    # tombstone (and every prior action under that engagement) survives the
    # delete commit. FK is ON DELETE SET NULL — see ActivityLog.engagement_id.
    activity_logs = relationship("ActivityLog", back_populates="engagement", passive_deletes=True)
    vault_items = relationship("VaultItem", back_populates="engagement", cascade="all, delete-orphan", passive_deletes=True)
    cleanup_artifacts = relationship("CleanupArtifact", back_populates="engagement", cascade="all, delete-orphan", passive_deletes=True)
    phases = relationship("EngagementPhase", backref="engagement", cascade="all, delete-orphan", passive_deletes=True, order_by="EngagementPhase.sort_order")
    required_skills = relationship("EngagementSkill", back_populates="engagement", cascade="all, delete-orphan", passive_deletes=True)
    # Global tag pool shared with findings + testcases.
    tags = relationship("Tag", secondary="engagement_tags", backref="engagements", lazy="raise")
