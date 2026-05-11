"""
Dashboard Widget model — defines reusable widget templates for the dashboard.
Admins create widget definitions; users place them on their personal dashboard.
"""

from sqlalchemy import Column, String, Boolean, Text, JSON, ForeignKey, DateTime
from sqlalchemy.sql import func
from database import Base
import uuid
import enum


class WidgetType(str, enum.Enum):
    STAT_CARD = "stat_card"
    BAR_CHART = "bar_chart"
    PIE_CHART = "pie_chart"
    AREA_CHART = "area_chart"
    STACKED_BAR = "stacked_bar"
    GAUGE = "gauge"
    TABLE = "table"
    LIST = "list"


class WidgetSize(str, enum.Enum):
    SMALL = "small"      # 1 col
    MEDIUM = "medium"    # 2 cols
    LARGE = "large"      # 2 cols, 2 rows
    WIDE = "wide"        # 3 cols
    FULL = "full"        # 4 cols (full width)


class WidgetCategory(str, enum.Enum):
    OVERVIEW = "overview"
    FINDINGS = "findings"
    ENGAGEMENTS = "engagements"
    OPERATORS = "operators"
    CLIENTS = "clients"
    CUSTOM = "custom"


class DashboardWidget(Base):
    __tablename__ = "dashboard_widgets"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    widget_type = Column(String(50), nullable=False)  # WidgetType enum value
    data_source = Column(String(100), nullable=False)  # API data source key
    size = Column(String(20), nullable=False, default="medium")  # WidgetSize
    category = Column(String(50), nullable=False, default="custom")  # WidgetCategory
    icon = Column(String(50), nullable=True)  # lucide icon name
    config = Column(JSON, nullable=True, default=dict)  # Chart-specific config
    is_system = Column(Boolean, default=False)  # Built-in widgets can't be deleted
    is_active = Column(Boolean, default=True)
    created_by = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
