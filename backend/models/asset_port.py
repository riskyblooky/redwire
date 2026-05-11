from sqlalchemy import Column, String, Integer, ForeignKey, UniqueConstraint, Enum as SQLEnum
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime
import uuid
import enum


class PortProtocol(str, enum.Enum):
    TCP = "TCP"
    UDP = "UDP"


class PortState(str, enum.Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    FILTERED = "FILTERED"


class AssetPort(Base):
    __tablename__ = "asset_ports"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    asset_id = Column(String, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True)
    port_number = Column(Integer, nullable=False)
    protocol = Column(SQLEnum(PortProtocol), nullable=False, default=PortProtocol.TCP)
    service_name = Column(String(255), nullable=True)
    state = Column(SQLEnum(PortState), nullable=False, default=PortState.OPEN)
    version = Column(String(500), nullable=True)

    # Relationships
    asset = relationship("Asset", back_populates="ports")

    __table_args__ = (
        UniqueConstraint("asset_id", "port_number", "protocol", name="uq_asset_port_protocol"),
    )
