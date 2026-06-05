from sqlalchemy import Column, String, DateTime, Integer, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from database import Base, AuditMixin
from datetime import datetime
import uuid

class Evidence(Base, AuditMixin):
    __tablename__ = "evidence"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    finding_id = Column(String, ForeignKey("findings.id"), nullable=True)
    testcase_id = Column(String, ForeignKey("testcases.id"), nullable=True)
    engagement_id = Column(String, ForeignKey("engagements.id"), nullable=True)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)  # Path/key in MinIO
    file_size = Column(Integer, nullable=False)  # Size in bytes
    mime_type = Column(String(100))
    description = Column(String(500))
    include_in_report = Column(Boolean, default=True)

    # Portion marking — null level means inherit from the owning finding /
    # engagement default. suffix is a free-text caveat, e.g. "//SAR/123".
    classification_level = Column(String(20), nullable=True)
    classification_suffix = Column(String(120), nullable=True)

    # Relationships
    finding = relationship("Finding", back_populates="evidence")
    testcase = relationship("TestCase", back_populates="evidence")
    engagement = relationship("Engagement", back_populates="evidence", foreign_keys="Evidence.engagement_id")
    created_by_user = relationship("User", foreign_keys="Evidence.created_by")
    updated_by_user = relationship("User", foreign_keys="Evidence.updated_by")

