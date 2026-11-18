from sqlalchemy import Column, String, DateTime, Text, ForeignKey, Index, text
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
    # Feed refresh dedupes on (feed, link); concurrent refreshes insert with
    # ON CONFLICT DO NOTHING against this index.
    __table_args__ = (Index("uq_intel_items_feed_source_url", "feed_id", "source_url", unique=True,
                            postgresql_where=text("feed_id IS NOT NULL AND source_url IS NOT NULL")),)

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
    created_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    author = relationship("User", foreign_keys=[created_by])
    feed = relationship("IntelFeed", back_populates="items")
    findings = relationship("Finding", secondary="intel_item_findings", lazy="raise")
    testcases = relationship("TestCase", secondary="intel_item_testcases", lazy="raise")
    notes = relationship("Note", secondary="intel_item_notes", lazy="raise")
    attachments = relationship("IntelAttachment", back_populates="intel_item", cascade="all, delete-orphan", lazy="raise")
