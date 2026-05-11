from sqlalchemy import Column, String, Text, Integer, Boolean, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import relationship
from database import Base, AuditMixin
import uuid
import enum


class SectionType(str, enum.Enum):
    TEXT = "text"
    FINDINGS = "findings"
    TESTCASES = "testcases"
    CLEANUP_ARTIFACTS = "cleanup_artifacts"


class ReportLayout(Base, AuditMixin):
    __tablename__ = "report_layouts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(500), nullable=False, index=True)
    engagement_id = Column(String, ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False, index=True)
    is_default = Column(Boolean, default=False, nullable=False)

    # Relationships
    sections = relationship(
        "ReportSection",
        back_populates="report_layout",
        cascade="all, delete-orphan",
        order_by="ReportSection.sort_order",
    )
    engagement = relationship("Engagement")
    created_by_user = relationship("User", foreign_keys="ReportLayout.created_by")
    updated_by_user = relationship("User", foreign_keys="ReportLayout.updated_by")


class ReportSection(Base):
    __tablename__ = "report_sections"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    report_layout_id = Column(String, ForeignKey("report_layouts.id", ondelete="CASCADE"), nullable=False, index=True)
    section_type = Column(SAEnum(SectionType, values_callable=lambda e: [x.value for x in e]), nullable=False, default=SectionType.TEXT)
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=True, default="")
    sort_order = Column(Integer, default=0, nullable=False)

    # Relationships
    report_layout = relationship("ReportLayout", back_populates="sections")
