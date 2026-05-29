from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, field_validator
from typing import List, Optional
from datetime import datetime

from database import get_db
from models.user import User, UserRole
from models.automation import AutomationRule, TRIGGER_TYPES
from models.permission import Permission
from auth.dependencies import get_current_user
from auth.permissions import has_global_permission
from utils.ssrf import validate_outbound_url_sync, OutboundURLError

router = APIRouter(prefix="/automations", tags=["automations"])


# ── schemas ───────────────────────────────────────────────────────────

class ConditionSchema(BaseModel):
    field: str
    operator: str  # equals, not_equals, contains, in
    value: str


class ActionSchema(BaseModel):
    type: str  # notify_users, notify_role, webhook, email, add_tags
    user_ids: Optional[List[str]] = None
    message: Optional[str] = None
    role: Optional[str] = None
    url: Optional[str] = None
    method: Optional[str] = "POST"
    headers: Optional[dict] = None
    body_template: Optional[str] = None
    recipients: Optional[List[str]] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    tag_ids: Optional[List[str]] = None

    @field_validator("url")
    @classmethod
    def _validate_url(cls, v: Optional[str]) -> Optional[str]:
        # SSRF guard (GHSA-7f74-569m-w73h): refuse to store a webhook URL that
        # points at a non-public address. Re-checked at fire time too.
        if v:
            try:
                validate_outbound_url_sync(v)
            except OutboundURLError as e:
                raise ValueError(str(e))
        return v


class AutomationCreate(BaseModel):
    name: str
    description: Optional[str] = None
    trigger_type: str
    conditions: List[ConditionSchema] = []
    actions: List[ActionSchema] = []
    is_enabled: bool = True


class AutomationUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    trigger_type: Optional[str] = None
    conditions: Optional[List[ConditionSchema]] = None
    actions: Optional[List[ActionSchema]] = None
    is_enabled: Optional[bool] = None


def _rule_to_dict(rule: AutomationRule) -> dict:
    return {
        "id": rule.id,
        "name": rule.name,
        "description": rule.description,
        "trigger_type": rule.trigger_type,
        "conditions": rule.conditions or [],
        "actions": rule.actions or [],
        "is_enabled": rule.is_enabled,
        "created_by": rule.created_by,
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
        "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
        "last_triggered_at": rule.last_triggered_at.isoformat() if rule.last_triggered_at else None,
        "trigger_count": rule.trigger_count or 0,
    }


# ── endpoints ─────────────────────────────────────────────────────────

@router.get("/trigger-types")
async def get_trigger_types(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all available trigger types with their filterable fields."""
    if not await has_global_permission(current_user, Permission.AUTOMATION_VIEW, db):
        raise HTTPException(403, "You don't have permission to view automations")
    return {
        "trigger_types": [
            {"value": key, **val}
            for key, val in TRIGGER_TYPES.items()
        ]
    }


@router.get("")
async def list_rules(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List automation rules. Admins/managers see all; others see own."""
    if not await has_global_permission(current_user, Permission.AUTOMATION_VIEW, db):
        raise HTTPException(403, "You don't have permission to view automations")

    query = select(AutomationRule).order_by(AutomationRule.created_at.desc())

    if current_user.role not in (UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD):
        query = query.where(AutomationRule.created_by == current_user.id)

    result = await db.execute(query)
    rules = result.scalars().all()
    return {"rules": [_rule_to_dict(r) for r in rules]}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_rule(
    data: AutomationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new automation rule."""
    if not await has_global_permission(current_user, Permission.AUTOMATION_CREATE, db):
        raise HTTPException(403, "You don't have permission to create automations")

    if data.trigger_type not in TRIGGER_TYPES:
        raise HTTPException(400, f"Unknown trigger type: {data.trigger_type}")

    rule = AutomationRule(
        name=data.name,
        description=data.description,
        trigger_type=data.trigger_type,
        conditions=[c.model_dump() for c in data.conditions],
        actions=[a.model_dump(exclude_none=True) for a in data.actions],
        is_enabled=data.is_enabled,
        created_by=current_user.id,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return _rule_to_dict(rule)


@router.get("/{rule_id}")
async def get_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single automation rule."""
    if not await has_global_permission(current_user, Permission.AUTOMATION_VIEW, db):
        raise HTTPException(403, "You don't have permission to view automations")

    result = await db.execute(select(AutomationRule).where(AutomationRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(404, "Rule not found")
    return _rule_to_dict(rule)


@router.put("/{rule_id}")
async def update_rule(
    rule_id: str,
    data: AutomationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update an automation rule."""
    if not await has_global_permission(current_user, Permission.AUTOMATION_EDIT, db):
        raise HTTPException(403, "You don't have permission to edit automations")

    result = await db.execute(select(AutomationRule).where(AutomationRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(404, "Rule not found")

    if data.name is not None:
        rule.name = data.name
    if data.description is not None:
        rule.description = data.description
    if data.trigger_type is not None:
        if data.trigger_type not in TRIGGER_TYPES:
            raise HTTPException(400, f"Unknown trigger type: {data.trigger_type}")
        rule.trigger_type = data.trigger_type
    if data.conditions is not None:
        rule.conditions = [c.model_dump() for c in data.conditions]
    if data.actions is not None:
        rule.actions = [a.model_dump(exclude_none=True) for a in data.actions]
    if data.is_enabled is not None:
        rule.is_enabled = data.is_enabled

    rule.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(rule)
    return _rule_to_dict(rule)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete an automation rule."""
    if not await has_global_permission(current_user, Permission.AUTOMATION_DELETE, db):
        raise HTTPException(403, "You don't have permission to delete automations")

    result = await db.execute(select(AutomationRule).where(AutomationRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(404, "Rule not found")
    await db.delete(rule)
    await db.commit()


@router.post("/{rule_id}/toggle")
async def toggle_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Toggle a rule's enabled state."""
    if not await has_global_permission(current_user, Permission.AUTOMATION_EDIT, db):
        raise HTTPException(403, "You don't have permission to edit automations")

    result = await db.execute(select(AutomationRule).where(AutomationRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(404, "Rule not found")

    rule.is_enabled = not rule.is_enabled
    rule.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(rule)
    return _rule_to_dict(rule)


@router.post("/{rule_id}/run")
async def run_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manually execute a rule's actions immediately, skipping condition evaluation."""
    if not await has_global_permission(current_user, Permission.AUTOMATION_EDIT, db):
        raise HTTPException(403, "You don't have permission to run automations")

    result = await db.execute(select(AutomationRule).where(AutomationRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(404, "Rule not found")

    from utils.automation_engine import execute_rule_actions

    context = {
        "action": "manual",
        "resource_type": "automation",
        "resource_name": rule.name,
        "resource_id": rule.id,
        "details": f"Manually triggered by {current_user.username}",
        "user_id": current_user.id,
        "engagement_id": None,
    }

    await execute_rule_actions(db, rule, context)
    await db.commit()
    await db.refresh(rule)
    return _rule_to_dict(rule)
