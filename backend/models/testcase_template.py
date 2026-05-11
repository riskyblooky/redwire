from sqlalchemy import Column, String, DateTime, Text, ForeignKey, Enum as SQLEnum, JSON
from sqlalchemy.orm import relationship
from database import Base, AuditMixin
from models.template_status import TemplateStatus
import uuid


class TestCaseTemplate(Base, AuditMixin):
    __tablename__ = "testcase_templates"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(500), nullable=False, index=True)
    category = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    steps = Column(Text)
    expected_result = Column(Text)
    # MITRE ATT&CK technique IDs (e.g. ["T1059.001"]). JSON array — see
    # rationale on FindingTemplate.attack_technique_ids.
    attack_technique_ids = Column(JSON, nullable=False, default=list, server_default='[]')

    status = Column(
        SQLEnum(TemplateStatus, name="templatestatus", create_type=False),
        nullable=False,
        default=TemplateStatus.DRAFT,
        server_default="PUBLISHED",
        index=True,
    )
    submitted_at = Column(DateTime, nullable=True)
    published_at = Column(DateTime, nullable=True)
    published_by = Column(String, ForeignKey("users.id"), nullable=True)
    review_note = Column(Text, nullable=True)

    # Relationships
    created_by_user = relationship("User", foreign_keys="TestCaseTemplate.created_by")
    updated_by_user = relationship("User", foreign_keys="TestCaseTemplate.updated_by")
    published_by_user = relationship("User", foreign_keys="TestCaseTemplate.published_by")
