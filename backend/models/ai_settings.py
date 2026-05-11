"""
AiSetting model — stores AI/LLM configuration as key-value pairs.
Sensitive values (API keys) are flagged via is_encrypted
so they can be masked in API responses.
"""
from sqlalchemy import Column, String, Boolean, DateTime, Text
from datetime import datetime
from database import Base


class AiSetting(Base):
    __tablename__ = "ai_settings"

    key = Column(String(128), primary_key=True)
    value = Column(Text, nullable=True)
    is_encrypted = Column(Boolean, default=False, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(String, nullable=True)

    def __repr__(self):
        return f"<AiSetting key={self.key}>"
