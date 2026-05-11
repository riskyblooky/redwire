"""
API Token model for long-lived programmatic access.

Tokens are stored as SHA-256 hashes — the raw value is shown once at creation.
"""
from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime
import uuid


class ApiToken(Base):
    __tablename__ = "api_tokens"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    token_prefix = Column(String(12), nullable=False)  # e.g. "rw_a1b2c3d4"
    permission = Column(String(4), nullable=False, default="ro")  # "ro" or "rw"
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_by = Column(String, ForeignKey("users.id"), nullable=True)

    # Relationships
    user = relationship("User", foreign_keys=[user_id], backref="api_tokens")
    creator = relationship("User", foreign_keys=[created_by])
