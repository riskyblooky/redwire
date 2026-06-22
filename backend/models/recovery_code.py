"""Recovery / backup codes for 2FA enrollment.

Follow-up to GHSA-vm6w-9wm5-q367. RedWire's pre-existing 2FA recovery
paths were (a) password-reset via email (requires inbox access) and
(b) admin-initiated password reset (requires admin contact). Neither
is a self-service recovery for a user who has lost their TOTP device
without losing access to email.

This table holds the bcrypt hashes of the 10 single-use codes issued
at successful ``/auth/totp/verify-setup``. Plaintext is shown to the
user exactly once in that response and is never stored. ``used_at``
flips to ``now()`` on consumption; the row stays around for forensic
value, and ``COUNT WHERE used_at IS NULL`` drives the
"remaining codes" UX.
"""

from sqlalchemy import Column, String, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime
import uuid


class RecoveryCode(Base):
    __tablename__ = "recovery_codes"

    id = Column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id = Column(
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # bcrypt hash (str-cost 12) — same shape as `users.hashed_password`.
    code_hash = Column(String(128), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    # NULL while unused; flips to consumption timestamp on first match.
    used_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="recovery_codes")

    __table_args__ = (
        # Common query: "fetch this user's unused codes, oldest first"
        # (the verify path scans them; the count-remaining query also
        # filters on this). Partial index keeps it cheap.
        Index(
            "ix_recovery_codes_user_unused",
            "user_id",
            postgresql_where=(used_at.is_(None)),
        ),
    )
