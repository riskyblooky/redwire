from sqlalchemy import Column, String, DateTime, Text, Enum as SQLEnum, ForeignKey
from sqlalchemy.orm import relationship, backref
from database import Base, AuditMixin
import enum
import uuid


class CleanupArtifactStatus(str, enum.Enum):
    PENDING = "PENDING"
    CLEANED = "CLEANED"
    PARTIALLY_CLEANED = "PARTIALLY_CLEANED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class CleanupArtifact(Base, AuditMixin):
    __tablename__ = "cleanup_artifacts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    engagement_id = Column(String, ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(500), nullable=False, index=True)
    artifact_type = Column(String(100), nullable=False)
    status = Column(SQLEnum(CleanupArtifactStatus), default=CleanupArtifactStatus.PENDING, nullable=False)
    location = Column(String(500), nullable=True)
    description = Column(Text, nullable=True)
    cleanup_notes = Column(Text, nullable=True)
    cleaned_at = Column(DateTime, nullable=True)
    cleaned_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    engagement = relationship("Engagement", back_populates="cleanup_artifacts")
    cleaned_by_user = relationship("User", foreign_keys=[cleaned_by])
    created_by_user = relationship("User", foreign_keys="CleanupArtifact.created_by")
    updated_by_user = relationship("User", foreign_keys="CleanupArtifact.updated_by")
    findings = relationship(
        "Finding",
        secondary="cleanup_artifact_findings",
        backref=backref("cleanup_artifacts", lazy="selectin"),
        lazy="selectin",
    )
    testcases = relationship(
        "TestCase",
        secondary="cleanup_artifact_testcases",
        backref=backref("cleanup_artifacts", lazy="selectin"),
        lazy="selectin",
    )
    assets = relationship(
        "Asset",
        secondary="cleanup_artifact_assets",
        backref=backref("cleanup_artifacts", lazy="selectin"),
        lazy="selectin",
    )
