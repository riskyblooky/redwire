from sqlalchemy import Column, String, DateTime, Text, ForeignKey, Boolean, JSON
from sqlalchemy.orm import relationship, backref
from database import Base, AuditMixin
from datetime import datetime
import uuid


class Asset(Base, AuditMixin):
    __tablename__ = "assets"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    engagement_id = Column(String, ForeignKey("engagements.id"), nullable=False)
    name = Column(String(255), nullable=False, index=True)
    asset_type = Column(String(100), nullable=False)

    identifier = Column(String(500), nullable=False)  # IP, domain, URL, etc.
    description = Column(Text)
    notes = Column(Text)
    is_pwned = Column(Boolean, default=False, nullable=False)
    is_scanned = Column(Boolean, default=False, nullable=False)
    in_scope = Column(Boolean, default=True, nullable=False)

    # Admin-defined custom field values, keyed by CustomFieldDefinition.field_key.
    custom_fields = Column(JSON, nullable=True, default=dict)

    # Relationships
    engagement = relationship("Engagement", back_populates="assets")
    ports = relationship("AssetPort", back_populates="asset", cascade="all, delete-orphan", lazy="selectin")
    created_by_user = relationship("User", foreign_keys="Asset.created_by")
    updated_by_user = relationship("User", foreign_keys="Asset.updated_by")
    # Explicit lazy=selectin for findings (Finding.assets back_populates="findings")
    # vault_items, testcases, cleanup_artifacts already provided by their model backrefs with lazy=selectin
    findings = relationship("Finding", secondary="finding_assets", back_populates="assets", lazy="selectin")
