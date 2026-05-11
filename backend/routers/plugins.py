"""
Plugins Router — Admin endpoints for managing plugins + settings.

GET    /plugins/              — List all discovered plugins
GET    /plugins/{id}          — Get single plugin details
PUT    /plugins/{id}/toggle   — Enable/disable a plugin
GET    /plugins/{id}/settings — Get plugin settings
PUT    /plugins/{id}/settings — Update plugin settings
GET    /plugins/nav-items     — Get all nav items from active plugins
GET    /plugins/widgets       — Get all widget defs from active plugins
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from pydantic import BaseModel
from typing import Optional

from database import get_db
from auth.dependencies import get_current_user
from models.user import User
from models.plugin import PluginSetting, PluginState
from plugin_loader import plugin_registry

router = APIRouter(prefix="/plugins", tags=["plugins"])


# ── Schemas ──────────────────────────────────────────────────────────

class PluginToggle(BaseModel):
    enabled: bool

class PluginSettingUpdate(BaseModel):
    key: str
    value: Optional[str] = None

class PluginSettingsUpdate(BaseModel):
    settings: list[PluginSettingUpdate]


# ── List all plugins ─────────────────────────────────────────────────

@router.get("/")
async def list_plugins(current_user: User = Depends(get_current_user)):
    """List all discovered plugins with their status."""
    return [p.to_dict() for p in plugin_registry.plugins.values()]


@router.get("/nav-items")
async def get_plugin_nav_items(current_user: User = Depends(get_current_user)):
    """Get sidebar nav items from all active plugins."""
    return plugin_registry.get_all_nav_items()


@router.get("/widgets")
async def get_plugin_widgets(current_user: User = Depends(get_current_user)):
    """Get dashboard widget definitions from all active plugins."""
    return plugin_registry.get_all_widgets()


# ── Plugin details ───────────────────────────────────────────────────

@router.get("/{plugin_id}")
async def get_plugin(
    plugin_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get details for a specific plugin."""
    plugin = plugin_registry.plugins.get(plugin_id)
    if not plugin:
        raise HTTPException(404, f"Plugin '{plugin_id}' not found")
    return plugin.to_dict()


# ── Toggle plugin ────────────────────────────────────────────────────

@router.put("/{plugin_id}/toggle")
async def toggle_plugin(
    plugin_id: str,
    body: PluginToggle,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Enable or disable a plugin. Requires admin."""
    if current_user.role != "admin":
        raise HTTPException(403, "Admin only")

    plugin = plugin_registry.plugins.get(plugin_id)
    if not plugin:
        raise HTTPException(404, f"Plugin '{plugin_id}' not found")

    # Persist state
    result = await db.execute(
        select(PluginState).where(PluginState.plugin_id == plugin_id)
    )
    state = result.scalar_one_or_none()
    if state:
        state.enabled = body.enabled
    else:
        state = PluginState(plugin_id=plugin_id, enabled=body.enabled)
        db.add(state)

    plugin.manifest.enabled = body.enabled
    await db.commit()

    return {"plugin_id": plugin_id, "enabled": body.enabled}


# ── Plugin settings ──────────────────────────────────────────────────

@router.get("/{plugin_id}/settings")
async def get_plugin_settings(
    plugin_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get settings for a plugin. Secrets are masked."""
    plugin = plugin_registry.plugins.get(plugin_id)
    if not plugin:
        raise HTTPException(404, f"Plugin '{plugin_id}' not found")

    if current_user.role != "admin":
        raise HTTPException(403, "Admin only")

    # Get saved values
    result = await db.execute(
        select(PluginSetting).where(PluginSetting.plugin_id == plugin_id)
    )
    saved = {s.key: s for s in result.scalars().all()}

    # Merge with schema from manifest
    settings = []
    for schema in plugin.manifest.settings:
        key = schema["key"]
        saved_setting = saved.get(key)
        value = saved_setting.value if saved_setting else schema.get("default")

        # Mask secrets
        if schema.get("type") == "secret" and value:
            display_value = "••••••••" + (value[-4:] if len(value) > 4 else "")
        else:
            display_value = value

        settings.append({
            **schema,
            "value": display_value,
            "has_value": value is not None and value != "",
        })

    return {"plugin_id": plugin_id, "settings": settings}


@router.put("/{plugin_id}/settings")
async def update_plugin_settings(
    plugin_id: str,
    body: PluginSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update settings for a plugin. Admin only."""
    plugin = plugin_registry.plugins.get(plugin_id)
    if not plugin:
        raise HTTPException(404, f"Plugin '{plugin_id}' not found")

    if current_user.role != "admin":
        raise HTTPException(403, "Admin only")

    # Build schema lookup
    schema_map = {s["key"]: s for s in plugin.manifest.settings}

    for setting in body.settings:
        if setting.key not in schema_map:
            continue

        # Skip masked secret values (user didn't change it)
        if setting.value and setting.value.startswith("••••"):
            continue

        is_secret = schema_map[setting.key].get("type") == "secret"

        # Upsert
        result = await db.execute(
            select(PluginSetting).where(
                PluginSetting.plugin_id == plugin_id,
                PluginSetting.key == setting.key,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.value = setting.value
            existing.is_secret = is_secret
        else:
            db.add(PluginSetting(
                plugin_id=plugin_id,
                key=setting.key,
                value=setting.value,
                is_secret=is_secret,
            ))

    await db.commit()
    return {"status": "saved", "plugin_id": plugin_id}
