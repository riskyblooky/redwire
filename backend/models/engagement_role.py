from sqlalchemy import Column, String
from sqlalchemy.orm import relationship
from database import Base
import uuid

class EngagementRole(Base):
    __tablename__ = "engagement_roles"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(String(500))

    # Relationships
    # Note: Assignments will be handled in the engagement_assignments table/model
    permission_set = relationship("EngagementRolePermissions", uselist=False, back_populates="role", cascade="all, delete-orphan")
