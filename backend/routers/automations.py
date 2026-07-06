import os
import re

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from datetime import datetime

from database import get_db
from models.user import User, UserRole
from models.automation import AutomationRule, TRIGGER_TYPES
from models.permission import Permission
from auth.dependencies import get_current_user
from auth.permissions import has_global_permission
from auth.rbac import check_engagement_permission
from rate_limit import limiter
from utils.ssrf import validate_outbound_url_sync, OutboundURLError

# UUID-shape used by every PK in this codebase (`str(uuid.uuid4())`).
_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
# Pragmatic email-shape — strict enough to catch "I forgot the @" and
# "I pasted a username", loose enough not to litigate RFC 5322.
_EMAIL_RE = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")
_VALID_ROLES = {r.value for r in UserRole}


def _email_domain_allowlist() -> Optional[set[str]]:
    """Read AUTOMATION_EMAIL_DOMAIN_ALLOWLIST. Empty/unset = no restriction
    (preserves current behaviour). When set, only addresses whose
    lower-cased domain matches an entry are allowed."""
    raw = os.environ.get("AUTOMATION_EMAIL_DOMAIN_ALLOWLIST", "").strip()
    if not raw:
        return None
    return {d.strip().lower() for d in raw.split(",") if d.strip()}

router = APIRouter(prefix="/automations", tags=["automations"])


# ── schemas ───────────────────────────────────────────────────────────

class ConditionSchema(BaseModel):
    field: str = Field(..., max_length=64)
    operator: str = Field(..., max_length=32)  # equals, not_equals, contains, in
    value: str = Field(..., max_length=2048)

    @field_validator("field")
    @classmethod
    def _validate_field_name(cls, v: str) -> str:
        """GHSA-cjgm-6cr5-j3x2: ``field`` flows into a regex compiled and
        executed against every matching activity event's ``details``
        change-summary. Constrain it to a dotted-identifier charset so a
        rule author can't smuggle regex metacharacters (ReDoS) or anchors
        (match-bypass) into that pattern. Sink-side ``re.escape`` is the
        runtime defense for any pre-existing rule that landed before this
        validator went live.
        """
        import re as _re
        if not _re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]{0,63}", v):
            raise ValueError(
                "condition.field must be a dotted identifier "
                "(letters/digits/underscore/dot, 1-64 chars, no regex metacharacters)"
            )
        return v


class ActionSchema(BaseModel):
    type: str = Field(..., max_length=32)  # notify_users, notify_role, webhook, email, add_tags
    user_ids: Optional[List[str]] = None
    message: Optional[str] = Field(None, max_length=8192)
    role: Optional[str] = Field(None, max_length=32)
    url: Optional[str] = Field(None, max_length=2048)
    method: Optional[str] = Field("POST", max_length=8)
    headers: Optional[dict] = None
    body_template: Optional[str] = Field(None, max_length=65536)
    recipients: Optional[List[str]] = None
    subject: Optional[str] = Field(None, max_length=500)
    body: Optional[str] = Field(None, max_length=65536)
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

    @field_validator("user_ids", "tag_ids")
    @classmethod
    def _validate_id_shape(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Typo guard (GHSA-3ccf-qpj4-vpx8 follow-up): reject anything that
        isn't a UUID-shaped string. Existence-in-DB is checked separately at
        the route handler (Pydantic validators are sync, so a DB lookup
        belongs upstream of this). Recipient lists are intentionally not
        engagement-scoped — that's the documented feature, not a security
        boundary."""
        if v is None:
            return v
        for entry in v:
            if not isinstance(entry, str) or not _UUID_RE.match(entry):
                raise ValueError(f"not a UUID: {entry!r}")
        return v

    @field_validator("role")
    @classmethod
    def _validate_role(cls, v: Optional[str]) -> Optional[str]:
        """Reject role names that don't exist (catches `team-lead` /
        `TeamLead` / `lead` typos). GHSA-3ccf-qpj4-vpx8 follow-up."""
        if v is None:
            return v
        if v not in _VALID_ROLES:
            raise ValueError(
                f"unknown role {v!r}; must be one of {sorted(_VALID_ROLES)}"
            )
        return v

    @field_validator("recipients")
    @classmethod
    def _validate_recipients(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Reject malformed email addresses up front, and reject any address
        whose domain isn't on AUTOMATION_EMAIL_DOMAIN_ALLOWLIST when that
        env var is set. The fire-time check in `_execute_email` still applies
        because the allowlist can tighten after a rule is saved."""
        if v is None:
            return v
        allowlist = _email_domain_allowlist()
        for addr in v:
            if not isinstance(addr, str) or not _EMAIL_RE.match(addr):
                raise ValueError(f"not a valid email address: {addr!r}")
            if allowlist is not None:
                domain = addr.rsplit("@", 1)[1].lower()
                if domain not in allowlist:
                    raise ValueError(
                        f"email domain {domain!r} not on "
                        f"AUTOMATION_EMAIL_DOMAIN_ALLOWLIST"
                    )
        return v


class AutomationCreate(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = Field(None, max_length=32768)
    trigger_type: str = Field(..., max_length=64)
    conditions: List[ConditionSchema] = []
    actions: List[ActionSchema] = []
    is_enabled: bool = True
    # GHSA-jvcx-44v2-gc9m: None = global rule (requires VIEW_ALL_ENGAGEMENTS);
    # a UUID scopes the rule to a single engagement (requires engagement_view
    # on that engagement). Enforced in the create handler.
    engagement_id: Optional[str] = Field(None, max_length=64)
    # Personal rule flag. When True, the rule is scoped to the requesting
    # user: owner_user_id is set to their id, actions are forced to
    # notify-self, and the engine only dispatches when the triggering event
    # was caused by the owner. AUTOMATION_CREATE is not required.
    is_personal: bool = False


class AutomationUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = Field(None, max_length=32768)
    trigger_type: Optional[str] = Field(None, max_length=64)
    conditions: Optional[List[ConditionSchema]] = None
    actions: Optional[List[ActionSchema]] = None
    is_enabled: Optional[bool] = None


async def _assert_user_ids_exist(actions: List[ActionSchema], db: AsyncSession) -> None:
    """Confirm every `user_ids` UUID across the action list points at a real
    User row. Typo guard at rule-save time — recipient lists themselves are
    intended by design, not a security boundary. GHSA-3ccf-qpj4-vpx8
    follow-up."""
    requested: set[str] = set()
    for a in actions:
        if a.user_ids:
            requested.update(a.user_ids)
    if not requested:
        return
    result = await db.execute(select(User.id).where(User.id.in_(requested)))
    found = {row[0] for row in result.all()}
    missing = sorted(requested - found)
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown user_id(s) in action recipients: {missing}",
        )


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
        "engagement_id": rule.engagement_id,
        "owner_user_id": rule.owner_user_id,
        "is_personal": rule.owner_user_id is not None,
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
        "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
        "last_triggered_at": rule.last_triggered_at.isoformat() if rule.last_triggered_at else None,
        "trigger_count": rule.trigger_count or 0,
    }


def _extract_personal_message(actions: List[ActionSchema]) -> Optional[str]:
    """Pull the operator-supplied ``message`` off a personal rule's action
    list, if any. Personal rules only support one implicit action (notify
    self); the caller may pass a custom message via the same
    :class:`ActionSchema` shape as an org rule."""
    for a in actions:
        if a.message:
            return a.message
    return None


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
    scope: str = "org",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List automation rules.

    ``scope=org`` (default): org-scope rules (owner_user_id IS NULL). Admins
    and TeamLeads see all; others see their own. Requires AUTOMATION_VIEW.

    ``scope=personal``: rules owned by the current user. No AUTOMATION_VIEW
    check — personal rules belong to their owner regardless of the org
    permission grid.
    """
    if scope == "personal":
        query = (
            select(AutomationRule)
            .where(AutomationRule.owner_user_id == current_user.id)
            .order_by(AutomationRule.created_at.desc())
        )
        result = await db.execute(query)
        rules = result.scalars().all()
        return {"rules": [_rule_to_dict(r) for r in rules]}

    if not await has_global_permission(current_user, Permission.AUTOMATION_VIEW, db):
        raise HTTPException(403, "You don't have permission to view automations")

    query = (
        select(AutomationRule)
        .where(AutomationRule.owner_user_id.is_(None))
        .order_by(AutomationRule.created_at.desc())
    )

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
    if data.trigger_type not in TRIGGER_TYPES:
        raise HTTPException(400, f"Unknown trigger type: {data.trigger_type}")

    # ── Personal rule path ────────────────────────────────────────────
    # Personal rules ignore AUTOMATION_CREATE (any user may subscribe
    # themselves to their own events). The action is forced to a single
    # notify-self so an operator can't set up broadcast / webhook / email
    # actions under the "personal" banner.
    if data.is_personal:
        if data.engagement_id is not None:
            raise HTTPException(
                400,
                "Personal rules must not set engagement_id; filter by "
                "engagement via a condition instead.",
            )

        message = _extract_personal_message(data.actions)
        forced_actions = [
            {
                "type": "notify_users",
                "user_ids": [current_user.id],
                **({"message": message} if message else {}),
            }
        ]

        rule = AutomationRule(
            name=data.name,
            description=data.description,
            trigger_type=data.trigger_type,
            conditions=[c.model_dump() for c in data.conditions],
            actions=forced_actions,
            is_enabled=data.is_enabled,
            created_by=current_user.id,
            engagement_id=None,
            owner_user_id=current_user.id,
        )
        db.add(rule)
        await db.commit()
        await db.refresh(rule)
        return _rule_to_dict(rule)

    # ── Org rule path (existing semantics) ────────────────────────────
    if not await has_global_permission(current_user, Permission.AUTOMATION_CREATE, db):
        raise HTTPException(403, "You don't have permission to create automations")

    # GHSA-jvcx-44v2-gc9m: gate the rule's scope.
    is_admin = current_user.role in (UserRole.ADMIN, UserRole.TEAM_LEAD)
    if data.engagement_id is None:
        # Global rule (fires on every engagement) — must be able to see all
        # engagements. Admin role passes via has_global_permission's bypass.
        if not await has_global_permission(current_user, Permission.VIEW_ALL_ENGAGEMENTS, db):
            raise HTTPException(
                403,
                "Creating a global automation rule requires the 'view_all_engagements' permission.",
            )
    else:
        # Engagement-scoped rule — caller must be able to see the target.
        # Admin/lead roles bypass per the codebase-wide pattern.
        if not is_admin and not await check_engagement_permission(
            current_user.id, data.engagement_id, Permission.ENGAGEMENT_VIEW.value, db
        ):
            raise HTTPException(
                403,
                "You do not have access to the engagement this rule would scope to.",
            )

    await _assert_user_ids_exist(data.actions, db)

    rule = AutomationRule(
        name=data.name,
        description=data.description,
        trigger_type=data.trigger_type,
        conditions=[c.model_dump() for c in data.conditions],
        actions=[a.model_dump(exclude_none=True) for a in data.actions],
        is_enabled=data.is_enabled,
        created_by=current_user.id,
        engagement_id=data.engagement_id,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return _rule_to_dict(rule)


async def _load_rule_for_action(
    rule_id: str,
    action_permission: Permission,
    db: AsyncSession,
    current_user: User,
) -> AutomationRule:
    """Resolve ``rule_id`` and enforce access for a mutating/read op.

    Personal rules (owner_user_id set) are only accessible to their owner —
    AUTOMATION_* permissions do not open them to admins, and their owner
    does not need AUTOMATION_* to touch them. Org rules use the existing
    global permission grid.
    """
    result = await db.execute(select(AutomationRule).where(AutomationRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(404, "Rule not found")

    if rule.owner_user_id is not None:
        if rule.owner_user_id != current_user.id:
            # Do not leak the personal rule's existence via a 403 that a 404
            # wouldn't also produce.
            raise HTTPException(404, "Rule not found")
        return rule

    if not await has_global_permission(current_user, action_permission, db):
        raise HTTPException(
            403, f"You don't have permission for {action_permission.value} on automations"
        )
    return rule


@router.get("/{rule_id}")
async def get_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single automation rule."""
    rule = await _load_rule_for_action(rule_id, Permission.AUTOMATION_VIEW, db, current_user)
    return _rule_to_dict(rule)


@router.put("/{rule_id}")
async def update_rule(
    rule_id: str,
    data: AutomationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update an automation rule."""
    rule = await _load_rule_for_action(rule_id, Permission.AUTOMATION_EDIT, db, current_user)

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
        if rule.owner_user_id is not None:
            # Personal rules keep the notify-self action shape regardless of
            # what the client sends. Pull only the optional message override.
            message = _extract_personal_message(data.actions)
            rule.actions = [
                {
                    "type": "notify_users",
                    "user_ids": [rule.owner_user_id],
                    **({"message": message} if message else {}),
                }
            ]
        else:
            await _assert_user_ids_exist(data.actions, db)
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
    rule = await _load_rule_for_action(rule_id, Permission.AUTOMATION_DELETE, db, current_user)
    await db.delete(rule)
    await db.commit()


@router.post("/{rule_id}/toggle")
async def toggle_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Toggle a rule's enabled state."""
    rule = await _load_rule_for_action(rule_id, Permission.AUTOMATION_EDIT, db, current_user)

    rule.is_enabled = not rule.is_enabled
    rule.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(rule)
    return _rule_to_dict(rule)


@router.post("/{rule_id}/run")
@limiter.limit("30/minute")
async def run_rule(
    request: Request,
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manually execute a rule's actions immediately, skipping condition
    evaluation. Rate-limited (GHSA-3ccf-qpj4-vpx8 follow-up) so an admin
    or TeamLead can't flood a victim's notification tray + WebSocket
    by hammering this endpoint."""
    rule = await _load_rule_for_action(rule_id, Permission.AUTOMATION_EDIT, db, current_user)

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
