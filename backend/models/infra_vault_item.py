from sqlalchemy import Column, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from database import Base, AuditMixin
from utils.encrypted_types import EncryptedText
import uuid


class InfraVaultItem(Base, AuditMixin):
    """Vault item scoped to an infrastructure item. Sensitive fields encrypted at rest."""
    __tablename__ = "infra_vault_items"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    # GHSA-jw3p-gjp8-2cf3: real FK with ondelete=CASCADE so a parent
    # InfraItem delete actually removes the child credential rows.
    # Without this, encrypted secrets persisted in the table indefinitely
    # after the parent was deleted and stayed API-readable via
    # GET /infra/items/{deleted_id}/vault.
    infra_item_id = Column(
        String,
        ForeignKey("infra_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(255), nullable=False)
    item_type = Column(String(100), nullable=False)  # CREDENTIAL, KEY, FILE, NOTE

    # Credential/Key fields — encrypted at rest via Fernet (handled
    # by the EncryptedText column type on bind/result).
    username = Column(EncryptedText, nullable=True)
    password = Column(EncryptedText, nullable=True)

    # Generic content / Note — encrypted at rest.
    note = Column(EncryptedText, nullable=True)

    # File fields (stored in MinIO)
    file_path = Column(String(500), nullable=True)
    filename = Column(String(255), nullable=True)

    description = Column(Text, nullable=True)
