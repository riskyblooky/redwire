from sqlalchemy import Column, String, DateTime, Text, ForeignKey, Enum as SQLEnum, JSON
from sqlalchemy.orm import relationship
from database import Base, AuditMixin
from models.template_status import TemplateStatus
import uuid


class FindingTemplate(Base, AuditMixin):
    __tablename__ = "finding_templates"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(500), nullable=False, index=True)
    category = Column(String(255), nullable=True, index=True)
    description = Column(Text, nullable=False)
    impact = Column(Text)
    mitigations = Column(Text)
    references = Column(Text)
    # MITRE ATT&CK technique IDs (e.g. ["T1059", "T1190.001"]). JSON array
    # rather than a join table — templates aren't engagement-scoped and we
    # don't query "which template uses technique X", so simpler wins.
    attack_technique_ids = Column(JSON, nullable=False, default=list, server_default='[]')

    status = Column(
        SQLEnum(TemplateStatus, name="templatestatus"),
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
    created_by_user = relationship("User", foreign_keys="FindingTemplate.created_by")
    updated_by_user = relationship("User", foreign_keys="FindingTemplate.updated_by")
    published_by_user = relationship("User", foreign_keys="FindingTemplate.published_by")
