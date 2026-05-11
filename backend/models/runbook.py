from sqlalchemy import Column, String, Text, Integer, ForeignKey, DateTime, Enum as SQLEnum
from sqlalchemy.orm import relationship
from database import Base, AuditMixin
from models.template_status import TemplateStatus
import uuid


class Runbook(Base, AuditMixin):
    __tablename__ = "runbooks"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(500), nullable=False, index=True)
    description = Column(Text, nullable=True)
    runbook_type = Column(String(100), nullable=True, index=True)

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
    items = relationship("RunbookItem", back_populates="runbook", cascade="all, delete-orphan", order_by="RunbookItem.sort_order")
    created_by_user = relationship("User", foreign_keys="Runbook.created_by")
    updated_by_user = relationship("User", foreign_keys="Runbook.updated_by")
    published_by_user = relationship("User", foreign_keys="Runbook.published_by")


class RunbookItem(Base):
    __tablename__ = "runbook_items"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    runbook_id = Column(String, ForeignKey("runbooks.id", ondelete="CASCADE"), nullable=False, index=True)
    template_id = Column(String, ForeignKey("testcase_templates.id", ondelete="CASCADE"), nullable=False)
    parent_id = Column(String, ForeignKey("runbook_items.id", ondelete="SET NULL"), nullable=True, index=True)
    sort_order = Column(Integer, default=0, nullable=False)

    # Relationships
    runbook = relationship("Runbook", back_populates="items")
    template = relationship("TestCaseTemplate", lazy="selectin")
    parent = relationship("RunbookItem", remote_side=[id], backref="children")
