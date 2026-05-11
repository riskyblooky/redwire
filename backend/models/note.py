from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime
import uuid


class Note(Base):
    __tablename__ = "notes"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    engagement_id = Column(String, ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_id = Column(String, ForeignKey("notes.id", ondelete="SET NULL"), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=True, default="")
    created_by = Column(String, ForeignKey("users.id"), nullable=False)
    updated_by = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    engagement = relationship("Engagement", foreign_keys="Note.engagement_id")
    author = relationship("User", foreign_keys="Note.created_by")
    last_editor = relationship("User", foreign_keys="Note.updated_by")
    parent = relationship("Note", remote_side="Note.id", foreign_keys="Note.parent_id", back_populates="children")
    children = relationship("Note", back_populates="parent", foreign_keys="Note.parent_id")

    # Linked resources
    findings = relationship("Finding", secondary="note_findings", lazy="selectin")
    testcases = relationship("TestCase", secondary="note_testcases", lazy="selectin")
    assets = relationship("Asset", secondary="note_assets", lazy="selectin")
    vault_items = relationship("VaultItem", secondary="note_vault_items", lazy="selectin")
    cleanup_artifacts = relationship("CleanupArtifact", secondary="note_cleanup_artifacts", lazy="selectin")
