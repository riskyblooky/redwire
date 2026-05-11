from sqlalchemy import Column, String, DateTime, Text
from sqlalchemy.orm import relationship
from database import Base, AuditMixin
import uuid


class InfraVaultItem(Base, AuditMixin):
    """Vault item scoped to an infrastructure item. Sensitive fields encrypted at rest."""
    __tablename__ = "infra_vault_items"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    infra_item_id = Column(String, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    item_type = Column(String(100), nullable=False)  # CREDENTIAL, KEY, FILE, NOTE

    # Credential/Key fields — encrypted at rest via Fernet
    username = Column(Text, nullable=True)
    password = Column(Text, nullable=True)

    # Generic content / Note — encrypted at rest
    note = Column(Text, nullable=True)

    # File fields (stored in MinIO)
    file_path = Column(String(500), nullable=True)
    filename = Column(String(255), nullable=True)

    description = Column(Text, nullable=True)
