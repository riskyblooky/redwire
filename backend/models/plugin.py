"""
PluginSetting — Key-value storage for plugin configuration.

Each plugin can define settings in its plugin.yaml manifest.
Values are stored here, keyed by (plugin_id, key).
"""

from sqlalchemy import Column, String, Text, DateTime, Boolean
from database import Base
from datetime import datetime
import uuid


class PluginSetting(Base):
    __tablename__ = "plugin_settings"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    plugin_id = Column(String(100), nullable=False, index=True)
    key = Column(String(100), nullable=False)
    value = Column(Text, nullable=True)
    is_secret = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Composite unique constraint handled by unique_together
    __table_args__ = (
        # Ensure (plugin_id, key) is unique
        {"sqlite_autoincrement": False},
    )


class PluginState(Base):
    """Tracks enabled/disabled state per plugin (overrides manifest default)."""
    __tablename__ = "plugin_states"

    plugin_id = Column(String(100), primary_key=True)
    enabled = Column(Boolean, default=True, nullable=False)
    installed_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
