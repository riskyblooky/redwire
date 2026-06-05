from sqlalchemy import Column, String, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.orm import relationship, backref
from database import Base, AuditMixin
from datetime import datetime
import uuid


class TestCase(Base, AuditMixin):
    __tablename__ = "testcases"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    engagement_id = Column(String, ForeignKey("engagements.id"))
    parent_id = Column(String, ForeignKey("testcases.id", ondelete="SET NULL"), nullable=True, index=True)
    title = Column(String(500), nullable=False, index=True)
    category = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    steps = Column(Text)  # Step-by-step instructions
    expected_result = Column(Text)
    actual_result = Column(Text)
    is_executed = Column(Boolean, default=False)
    is_successful = Column(Boolean)
    notes = Column(Text)

    # Portion marking — null level means inherit (report/engagement default).
    classification_level = Column(String(20), nullable=True)
    classification_suffix = Column(String(120), nullable=True)

    # Relationships
    engagement = relationship("Engagement", back_populates="testcases")
    parent = relationship("TestCase", remote_side=[id], backref="children")
    assets = relationship("Asset", secondary="testcase_assets", backref=backref("testcases", lazy="selectin"), lazy="selectin")
    tags = relationship("Tag", secondary="testcase_tags", backref=backref("testcases", lazy="selectin"), lazy="selectin")
    evidence = relationship("Evidence", back_populates="testcase", lazy="selectin")
    attack_techniques = relationship("TestCaseAttackTechnique", cascade="all, delete-orphan", lazy="selectin")
    created_by_user = relationship("User", foreign_keys="TestCase.created_by")
    updated_by_user = relationship("User", foreign_keys="TestCase.updated_by")
