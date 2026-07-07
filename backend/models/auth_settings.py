"""
AuthSettings model — stores LDAP/SSO configuration as key-value pairs.

Every ``value`` cell is Fernet-encrypted at rest via ``EncryptedText`` —
encrypt-on-bind, decrypt-on-read, no router code involved. Previously
only ``is_encrypted=True`` rows were meant to be encrypted, but the
column type was plain ``Text`` and the flag was only used for
API-response masking, so LDAP bind passwords / SMTP passwords / SAML
IdP certs sat in the DB as plaintext. Flipping the whole column to
``EncryptedText`` closes that gap and makes the bug shape impossible
to repeat — a router can't "forget to encrypt" because the type does
it. ``is_encrypted`` is retained purely as an API-mask hint.
"""
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from datetime import datetime
from database import Base
from utils.encrypted_types import EncryptedText


class AuthSetting(Base):
    __tablename__ = "auth_settings"

    key = Column(String(128), primary_key=True)
    value = Column(EncryptedText, nullable=True)
    is_encrypted = Column(Boolean, default=False, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # Real FK to users.id — was a bare string before (GHSA-jw3p follow-up).
    # SET NULL on user delete so the setting survives operator departure.
    updated_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    def __repr__(self):
        return f"<AuthSetting key={self.key}>"
