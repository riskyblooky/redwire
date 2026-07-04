from sqlalchemy import Column, String, DateTime, Text, Enum as SAEnum, ForeignKey
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime
import uuid
import enum


class InfraType(str, enum.Enum):
    VPS = "VPS"
    C2 = "C2"
    REDIRECTOR = "REDIRECTOR"
    PROXY = "PROXY"
    PHISHING = "PHISHING"
    JUMPBOX = "JUMPBOX"
    OTHER = "OTHER"


class InfraStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    DECOMMISSIONED = "DECOMMISSIONED"
    STANDBY = "STANDBY"


class InfraItem(Base):
    __tablename__ = "infra_items"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False, index=True)
    infra_type = Column(String(20), default=InfraType.OTHER.value, nullable=False)
    status = Column(String(20), default=InfraStatus.ACTIVE.value, nullable=False)
    ip_address = Column(String(45), nullable=True)
    internal_ip = Column(String(45), nullable=True)
    hostname = Column(String(255), nullable=True)
    provider = Column(String(100), nullable=True)
    region = Column(String(100), nullable=True)
    os = Column(String(100), nullable=True)
    point_of_presence = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    # Real FK to users.id — was a bare string before (GHSA-jw3p follow-up).
    # SET NULL on user delete: the infra item survives the operator leaving,
    # attribution becomes anonymous — matches how wordlist_meta.uploaded_by
    # and every AuditMixin-based model handle the same shape.
    created_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships via association tables
    findings = relationship("Finding", secondary="infra_item_findings", lazy="selectin")
    testcases = relationship("TestCase", secondary="infra_item_testcases", lazy="selectin")
    notes_rel = relationship("Note", secondary="infra_item_notes", lazy="selectin")
