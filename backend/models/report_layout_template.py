from sqlalchemy import Column, String, Text, Integer, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import relationship
from database import Base, AuditMixin
from models.report_layout import SectionType
import uuid


class ReportLayoutTemplate(Base, AuditMixin):
    __tablename__ = "report_layout_templates"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(500), nullable=False, index=True)
    description = Column(Text, nullable=True)

    # Relationships
    sections = relationship(
        "ReportLayoutTemplateSection",
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="ReportLayoutTemplateSection.sort_order",
    )
    created_by_user = relationship("User", foreign_keys="ReportLayoutTemplate.created_by")
    updated_by_user = relationship("User", foreign_keys="ReportLayoutTemplate.updated_by")


class ReportLayoutTemplateSection(Base):
    __tablename__ = "report_layout_template_sections"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    template_id = Column(String, ForeignKey("report_layout_templates.id", ondelete="CASCADE"), nullable=False, index=True)
    section_type = Column(SAEnum(SectionType, values_callable=lambda e: [x.value for x in e]), nullable=False, default=SectionType.TEXT)
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=True, default="")
    sort_order = Column(Integer, default=0, nullable=False)

    # Relationships
    template = relationship("ReportLayoutTemplate", back_populates="sections")
