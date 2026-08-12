from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime
import uuid


class IntelFeed(Base):
    __tablename__ = "intel_feeds"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    url = Column(String(1000), nullable=False)
    feed_type = Column(String(20), default="RSS")  # RSS, ATOM, JSON
    enabled = Column(Boolean, default=True, nullable=False)
    # Per-feed TLS cert verification. Default on; an admin can turn it off for a
    # single internal / self-signed feed without weakening the rest (mirrors the
    # LDAP/SMTP tls_verify escape hatch). SSRF validation still runs regardless.
    verify_tls = Column(Boolean, default=True, nullable=False)
    last_fetched_at = Column(DateTime, nullable=True)
    created_by = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    author = relationship("User", foreign_keys=[created_by])
    items = relationship("IntelItem", back_populates="feed", cascade="all, delete-orphan")
