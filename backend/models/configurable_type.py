from sqlalchemy import Column, String, Text, Integer, Boolean, UniqueConstraint
from database import Base
import uuid


class ConfigurableType(Base):
    """Generic configurable type for all entity categories (client, engagement, asset, testcase, finding, vault, cleanup)."""
    __tablename__ = "configurable_types"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    category = Column(String(50), nullable=False, index=True)  # "client", "engagement", "asset", "testcase", "finding", "vault", "cleanup"
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    color = Column(String(7), nullable=True, default="#6366f1")
    is_system = Column(Boolean, nullable=False, default=False)
    sort_order = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint('category', 'name', name='uq_configurable_type_category_name'),
    )
