from sqlalchemy import Column, String, DateTime, Text, Enum as SQLEnum, ForeignKey, Float, Integer, JSON
from sqlalchemy.orm import relationship, backref
from database import Base, AuditMixin
from datetime import datetime
import uuid
import enum

class Severity(str, enum.Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"

class FindingStatus(str, enum.Enum):
    OPEN = "OPEN"
    IN_REVIEW = "IN_REVIEW"
    VERIFIED = "VERIFIED"
    REMEDIATED = "REMEDIATED"
    CLOSED = "CLOSED"




class Tag(Base):
    __tablename__ = "tags"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(50), nullable=False, unique=True, index=True)
    color = Column(String(20), nullable=True) # Hex color or tailwind class
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class Finding(Base, AuditMixin):
    __tablename__ = "findings"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    engagement_id = Column(String, ForeignKey("engagements.id"), nullable=False)
    title = Column(String(500), nullable=False, index=True)
    category = Column(String(255), nullable=True, index=True)
    description = Column(Text, nullable=False)
    severity = Column(SQLEnum(Severity), nullable=False, index=True)
    status = Column(SQLEnum(FindingStatus), default=FindingStatus.OPEN, nullable=False)
    
    # CVSS Scoring
    cvss_score = Column(Float)
    cvss_vector = Column(String(100))
    
    # Technical Details
    impact = Column(Text)
    technical_details = Column(Text)
    steps_to_reproduce = Column(Text)
    mitigations = Column(Text)
    references = Column(Text)

    # Portion marking — null level means inherit (report default → engagement
    # default → clamp to ceiling). suffix is free-text caveat, e.g. "//SAR/123".
    classification_level = Column(String(20), nullable=True)
    classification_suffix = Column(String(120), nullable=True)

    # Admin-defined custom field values, keyed by CustomFieldDefinition.field_key.
    custom_fields = Column(JSON, nullable=True, default=dict)

    # Relationships
    engagement = relationship("Engagement", back_populates="findings")
    created_by_user = relationship("User", back_populates="findings", foreign_keys="Finding.created_by")
    updated_by_user = relationship("User", foreign_keys="Finding.updated_by")
    evidence = relationship("Evidence", back_populates="finding", cascade="all, delete-orphan")
    assets = relationship("Asset", secondary="finding_assets", back_populates="findings", lazy="selectin")
    tags = relationship("Tag", secondary="finding_tags", backref="findings", lazy="selectin")
    testcases = relationship("TestCase", secondary="finding_testcases", backref=backref("findings", lazy="selectin"), lazy="selectin")
    attack_techniques = relationship("FindingAttackTechnique", cascade="all, delete-orphan", lazy="selectin")
