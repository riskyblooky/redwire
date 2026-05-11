from sqlalchemy import Column, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime
import uuid
import enum


class IntelItemType(str, enum.Enum):
    CVE = "CVE"
    ADVISORY = "ADVISORY"
    ARTICLE = "ARTICLE"
    ZINE = "ZINE"
    EXPLOIT = "EXPLOIT"
    OTHER = "OTHER"


class IntelSeverity(str, enum.Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class IntelItem(Base):
    __tablename__ = "intel_items"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(500), nullable=False, index=True)
    content = Column(Text, nullable=True)
    source = Column(String(255), nullable=True)  # "manual", feed name, etc.
    source_url = Column(Text, nullable=True)
    item_type = Column(String(20), default="OTHER", nullable=False)
    severity = Column(String(20), nullable=True)
    cve_id = Column(String(50), nullable=True, index=True)  # e.g. CVE-2024-1234
    published_at = Column(DateTime, nullable=True)
    feed_id = Column(String, ForeignKey("intel_feeds.id", ondelete="SET NULL"), nullable=True)
    created_by = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    author = relationship("User", foreign_keys=[created_by])
    feed = relationship("IntelFeed", back_populates="items")
    findings = relationship("Finding", secondary="intel_item_findings", lazy="selectin")
    testcases = relationship("TestCase", secondary="intel_item_testcases", lazy="selectin")
    notes = relationship("Note", secondary="intel_item_notes", lazy="selectin")
    attachments = relationship("IntelAttachment", back_populates="intel_item", cascade="all, delete-orphan", lazy="selectin")
