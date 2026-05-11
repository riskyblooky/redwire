"""
AuthSettings model — stores LDAP/SSO configuration as key-value pairs.
Sensitive values (passwords, certificates) are flagged via is_encrypted
so they can be masked in API responses.
"""
from sqlalchemy import Column, String, Boolean, DateTime, Text
from datetime import datetime
from database import Base


class AuthSetting(Base):
    __tablename__ = "auth_settings"

    key = Column(String(128), primary_key=True)
    value = Column(Text, nullable=True)
    is_encrypted = Column(Boolean, default=False, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(String, nullable=True)

    def __repr__(self):
        return f"<AuthSetting key={self.key}>"
