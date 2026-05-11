from sqlalchemy import Column, String, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from database import Base, AuditMixin
from datetime import datetime
import uuid

class CalendarEvent(Base, AuditMixin):
    __tablename__ = "calendar_events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(255), nullable=False)
    description = Column(Text)
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime, nullable=False)
    location = Column(String(255))
    is_all_day = Column(Boolean, default=False)
    event_type = Column(String(20), default="EVENT", nullable=False)  # EVENT or OOO

    # Relationships
    created_by_user = relationship("User", back_populates="calendar_events", foreign_keys="[CalendarEvent.created_by]")
    updated_by_user = relationship("User", foreign_keys="[CalendarEvent.updated_by]")
