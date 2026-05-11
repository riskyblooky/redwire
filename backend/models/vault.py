from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship, backref
from database import Base, AuditMixin
import uuid

class VaultItem(Base, AuditMixin):
    __tablename__ = "vault_items"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    engagement_id = Column(String, ForeignKey("engagements.id"), nullable=False)
    name = Column(String(255), nullable=False)
    item_type = Column(String(100), nullable=False)
    
    # Credential/Key fields — encrypted at rest via Fernet
    username = Column(Text, nullable=True)
    password = Column(Text, nullable=True)
    
    # Generic content/Note
    note = Column(Text, nullable=True)
    
    # File fields
    file_path = Column(String(500), nullable=True)
    filename = Column(String(255), nullable=True)
    
    description = Column(Text, nullable=True)

    # Relationships
    engagement = relationship("Engagement", back_populates="vault_items")
    created_by_user = relationship("User", foreign_keys="VaultItem.created_by")
    updated_by_user = relationship("User", foreign_keys="VaultItem.updated_by")
    findings = relationship("Finding", secondary="vault_item_findings", backref=backref("vault_items", lazy="selectin"), lazy="selectin")
    testcases = relationship("TestCase", secondary="vault_item_testcases", backref=backref("vault_items", lazy="selectin"), lazy="selectin")
    assets = relationship("Asset", secondary="vault_item_assets", backref=backref("vault_items", lazy="selectin"), lazy="selectin")
