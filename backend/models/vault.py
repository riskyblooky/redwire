from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Integer
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

    # Tracking flag for the MinIO blob's at-rest encryption state.
    # 0 = legacy plaintext (pre-RDW-057) — startup backfill will encrypt
    #     and re-upload it on next boot.
    # 1 = encrypted with the current VAULT_ENCRYPTION_KEY scheme (Fernet).
    # Future schemes bump the integer. Non-FILE rows stay at 1 (no
    # blob to worry about). GHSA-3r7j-7h5r-gxgx Issue 3 follow-up.
    encryption_version = Column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )

    # Relationships
    engagement = relationship("Engagement", back_populates="vault_items")
    created_by_user = relationship("User", foreign_keys="VaultItem.created_by")
    updated_by_user = relationship("User", foreign_keys="VaultItem.updated_by")
    findings = relationship("Finding", secondary="vault_item_findings", backref=backref("vault_items", lazy="selectin"), lazy="selectin")
    testcases = relationship("TestCase", secondary="vault_item_testcases", backref=backref("vault_items", lazy="selectin"), lazy="selectin")
    assets = relationship("Asset", secondary="vault_item_assets", backref=backref("vault_items", lazy="selectin"), lazy="selectin")
