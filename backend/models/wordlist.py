from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, Enum as SAEnum
from sqlalchemy.orm import relationship
from database import Base
import uuid
import enum
from datetime import datetime


class WordlistStatus(str, enum.Enum):
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"


class WordlistMeta(Base):
    """Tracks uploaded wordlist files and their processing status."""
    __tablename__ = "wordlist_meta"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    filename = Column(String(255), nullable=False)
    entry_count = Column(Integer, default=0)
    status = Column(String(20), default=WordlistStatus.PROCESSING.value, nullable=False)
    error_message = Column(Text, nullable=True)
    uploaded_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    uploaded_by_user = relationship("User", foreign_keys=[uploaded_by])


class WordlistEntry(Base):
    """Stores passwords and their precomputed hashes for fast lookup."""
    __tablename__ = "wordlist_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    password = Column(Text, nullable=False, index=True)
    ntlm = Column(String(32), nullable=True, index=True)
    md5 = Column(String(32), nullable=True, index=True)
    sha1 = Column(String(40), nullable=True, index=True)
    source = Column(String(255), nullable=True)  # wordlist_meta.id
