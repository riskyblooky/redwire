from sqlalchemy import Column, String, Text, Integer, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from database import Base, AuditMixin
import uuid


class Client(Base, AuditMixin):
    """Hierarchical client entity with tree structure."""
    __tablename__ = "clients"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    client_type_id = Column(String, ForeignKey("configurable_types.id", ondelete="SET NULL"), nullable=True)
    parent_id = Column(String, ForeignKey("clients.id", ondelete="SET NULL"), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)

    # Contact info
    contact_name = Column(String(255), nullable=True)
    contact_email = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)

    # Relationships
    client_type = relationship("ConfigurableType", foreign_keys=[client_type_id])
    parent = relationship("Client", remote_side=[id], back_populates="children")
    children = relationship("Client", back_populates="parent", cascade="all, delete-orphan",
                            order_by="Client.sort_order")
    engagements = relationship("Engagement", back_populates="client")
    access_grants = relationship("ClientUserAccess", cascade="all, delete-orphan", foreign_keys="ClientUserAccess.client_id")
