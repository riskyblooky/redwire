from sqlalchemy import Column, String, Boolean, ForeignKey, Table
from sqlalchemy.orm import relationship
from database import Base
import uuid

user_groups = Table(
    "user_groups",
    Base.metadata,
    Column("user_id", String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("group_id", String, ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True)
)

class Group(Base):
    __tablename__ = "groups"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(String(500))
    is_system = Column(Boolean, default=False, nullable=False, server_default="false")
    is_default = Column(Boolean, default=False, nullable=False, server_default="false")

    # Relationships
    users = relationship("User", secondary=user_groups, back_populates="groups")
    permission_set = relationship("GroupPermissions", uselist=False, back_populates="group", cascade="all, delete-orphan")
