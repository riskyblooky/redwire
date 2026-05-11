from sqlalchemy import Column, String, Text, ForeignKey, DateTime
from database import Base
from datetime import datetime
import uuid


class AttackerNode(Base):
    __tablename__ = "attacker_nodes"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    engagement_id = Column(String, ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False, default="Threat Actor")
    point_of_presence = Column(String(100), nullable=False, default="External")
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class AttackerNodeEdge(Base):
    __tablename__ = "attacker_node_edges"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    attacker_node_id = Column(String, ForeignKey("attacker_nodes.id", ondelete="CASCADE"), nullable=False, index=True)
    target_node_id = Column(String(255), nullable=False)  # e.g. "testcase-xxx"
    target_node_type = Column(String(50), nullable=False)  # "testcase", "asset", etc.
