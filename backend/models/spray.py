from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from database import Base, AuditMixin
import uuid


class SprayCampaign(Base, AuditMixin):
    """A password-spray campaign — typically one nxc run."""
    __tablename__ = "spray_campaigns"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    engagement_id = Column(String, ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)

    # Target info (extracted from nxc output)
    protocol = Column(String(20), nullable=True)          # SMB, LDAP, RDP, MSSQL, WINRM, SSH, FTP
    target_host = Column(String(255), nullable=True)       # IP address
    target_port = Column(Integer, nullable=True)           # Port number
    target_hostname = Column(String(255), nullable=True)   # NetBIOS / DNS name
    domain = Column(String(255), nullable=True)            # AD domain

    # The password sprayed — encrypted at rest via Fernet (same as vault)
    password_used = Column(Text, nullable=True)

    # Aggregate stats
    total_attempts = Column(Integer, default=0)
    successful = Column(Integer, default=0)
    locked_out = Column(Integer, default=0)
    failed = Column(Integer, default=0)

    # Meta
    status = Column(String(50), default="imported")  # imported / manual
    notes = Column(Text, nullable=True)
    imported_from = Column(String(255), nullable=True)  # original filename

    # Relationships
    engagement = relationship("Engagement", backref="spray_campaigns")
    results = relationship("SprayResult", back_populates="campaign", cascade="all, delete-orphan", lazy="selectin")
    created_by_user = relationship("User", foreign_keys="SprayCampaign.created_by")


class SprayResult(Base):
    """A single spray attempt result — one line from nxc output."""
    __tablename__ = "spray_results"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    campaign_id = Column(String, ForeignKey("spray_campaigns.id", ondelete="CASCADE"), nullable=False)

    username = Column(String(255), nullable=False)
    domain = Column(String(255), nullable=True)
    result = Column(String(50), nullable=False)         # success, success_admin, failed, locked, disabled
    status_code = Column(String(255), nullable=True)    # raw nxc status e.g. STATUS_LOGON_FAILURE
    is_admin = Column(Boolean, default=False)           # True if (Pwn3d!)
    vault_item_id = Column(String, ForeignKey("vault_items.id", ondelete="SET NULL"), nullable=True)
    # Optional FK to the engagement's asset inventory — set on commit when
    # target_host matches an Asset.identifier. Lets users jump from a spray
    # result row to the full asset detail.
    asset_id = Column(String, ForeignKey("assets.id", ondelete="SET NULL"), nullable=True, index=True)

    # Per-result target and credential — populated for runs that span
    # multiple hosts and/or use user/password wordlists. Source of truth for
    # auto-vault when the campaign-level password_used is null.
    target_host = Column(String(255), nullable=True)
    target_port = Column(Integer, nullable=True)
    password = Column(Text, nullable=True)              # Fernet-encrypted

    created_at = Column(DateTime, server_default="now()")

    # Relationships
    campaign = relationship("SprayCampaign", back_populates="results")
    vault_item = relationship("VaultItem", foreign_keys=[vault_item_id])
    asset = relationship("Asset", foreign_keys=[asset_id])
