"""
PluginSetting — Key-value storage for plugin configuration.

Each plugin can define settings in its plugin.yaml manifest.
Values are stored here, keyed by (plugin_id, key).

``value`` is Fernet-encrypted at rest via ``EncryptedText`` — every row,
not just ``type: secret`` settings (API keys, passwords), so plugin code
reading and writing through the ORM can't store a secret in plaintext by
mistake. Same model as ``AuthSetting``. Rows from before the switch are
re-encrypted at boot (utils/plugin_settings_field_migration.py).
"""

from sqlalchemy import Column, String, DateTime, Boolean, UniqueConstraint
from database import Base
from utils.encrypted_types import EncryptedText
from datetime import datetime
import uuid


class PluginSetting(Base):
    __tablename__ = "plugin_settings"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    plugin_id = Column(String(100), nullable=False, index=True)
    key = Column(String(100), nullable=False)
    value = Column(EncryptedText, nullable=True)
    is_secret = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("plugin_id", "key", name="uq_plugin_settings_plugin_key"),
    )


async def upsert_plugin_setting(db, plugin_id: str, key: str, value, is_secret: bool = False) -> None:
    """Insert or update one (plugin_id, key) row atomically. A select-then-
    insert raced across workers (double-submitted save, two asset events)
    and left duplicates. ``value`` still goes through EncryptedText. The
    caller commits."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    stmt = pg_insert(PluginSetting).values(
        id=str(uuid.uuid4()), plugin_id=plugin_id, key=key, value=value,
        is_secret=is_secret, updated_at=datetime.utcnow(),
    )
    await db.execute(stmt.on_conflict_do_update(
        constraint="uq_plugin_settings_plugin_key",
        set_={"value": stmt.excluded.value, "is_secret": stmt.excluded.is_secret,
              "updated_at": stmt.excluded.updated_at},
    ))


class PluginState(Base):
    """Tracks enabled/disabled state per plugin (overrides manifest default)."""
    __tablename__ = "plugin_states"

    plugin_id = Column(String(100), primary_key=True)
    enabled = Column(Boolean, default=True, nullable=False)
    installed_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
