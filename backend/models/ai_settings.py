"""
AiSetting model — stores AI/LLM configuration as key-value pairs.
Values are Fernet-encrypted at rest (EncryptedText, as auth_settings);
``is_encrypted`` marks the secret ones (the API key) for masking in
API responses.
"""
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from datetime import datetime
from database import Base
from utils.encrypted_types import EncryptedText


class AiSetting(Base):
    __tablename__ = "ai_settings"

    key = Column(String(128), primary_key=True)
    value = Column(EncryptedText, nullable=True)
    is_encrypted = Column(Boolean, default=False, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # Real FK to users.id — was a bare string before (GHSA-jw3p follow-up).
    # SET NULL on user delete so the setting survives operator departure.
    updated_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    def __repr__(self):
        return f"<AiSetting key={self.key}>"
