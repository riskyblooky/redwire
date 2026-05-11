from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, Text, UniqueConstraint
from database import Base
from datetime import datetime
import uuid


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(64), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=True)
    link = Column(String(512), nullable=True)  # e.g. /engagements/abc
    is_read = Column(Boolean, default=False, nullable=False)
    actor_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    engagement_id = Column(String, ForeignKey("engagements.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(64), nullable=False)
    site_muted = Column(Boolean, default=False, nullable=False)
    email_muted = Column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "event_type", name="uq_notification_pref_user_event"),
    )


# All supported event types
EVENT_TYPES = {
    "engagement_assigned": "Added to an engagement",
    "engagement_removed": "Removed from an engagement",
    "finding_created": "New finding in your engagement",
    "finding_status_changed": "Finding status changed",
    "engagement_status_changed": "Engagement status changed",
    "password_reset": "Admin reset your password",
    "mention": "Mentioned in a note or thread",
    "automation": "Automation rule triggered",
}
