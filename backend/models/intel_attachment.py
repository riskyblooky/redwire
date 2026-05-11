from sqlalchemy import Column, String, DateTime, Integer, ForeignKey
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime
import uuid


class IntelAttachment(Base):
    __tablename__ = "intel_attachments"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    intel_item_id = Column(String, ForeignKey("intel_items.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(500), nullable=False)  # Storage key in MinIO
    original_filename = Column(String(255), nullable=False)
    file_size = Column(Integer, nullable=False)  # Size in bytes
    mime_type = Column(String(100), nullable=True)
    created_by = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    intel_item = relationship("IntelItem", back_populates="attachments")
    uploader = relationship("User", foreign_keys=[created_by])
