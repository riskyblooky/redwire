from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Boolean, Index
from database import Base
from datetime import datetime
import uuid


class AttackGraphLayout(Base):
    __tablename__ = "attack_graph_layouts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    engagement_id = Column(String, ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False, default="Default")
    positions = Column(Text, nullable=False)  # JSON string: { "node-id": { "x": number, "y": number } }
    is_active = Column(Boolean, nullable=False, default=False)
    pinned_by = Column(String, ForeignKey("users.id"), nullable=False)
    pinned_at = Column(DateTime, default=datetime.utcnow, nullable=False)
