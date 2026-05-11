from sqlalchemy import Column, String, Integer, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime
import uuid

class RegistrationCode(Base):
    __tablename__ = "registration_codes"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String(50), unique=True, nullable=False, index=True)
    label = Column(String(100), nullable=True)
    max_uses = Column(Integer, default=1, nullable=False)
    used_count = Column(Integer, default=0, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by = Column(String, ForeignKey("users.id"), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    # Relationships
    creator = relationship("User", foreign_keys=[created_by])
