"""
Custom Field Definitions router — admin management of user-defined fields on
assets, testcases, findings, and clients.

Reads are open to any authenticated user (the entity forms/detail views need
the definitions to render). Writes are gated to WRITE_ADMIN_ROLES, matching
the sibling configurable-types taxonomy admin. Entity type is in the path and
whitelisted, same shape as /configurable-types/{category}.
"""
import re
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User
from models.custom_field_definition import (
    CustomFieldDefinition, ENTITY_VALUES, FIELD_TYPE_VALUES, OPTION_TYPES,
)
from schemas.custom_field import (
    CustomFieldDefinitionCreate, CustomFieldDefinitionUpdate,
    CustomFieldDefinitionResponse, ReorderRequest,
)
from auth.dependencies import get_current_user, require_roles, WRITE_ADMIN_ROLES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/custom-field-definitions", tags=["custom-fields"])


def _validate_entity(entity: str) -> str:
    if entity not in ENTITY_VALUES:
        raise HTTPException(
            400, f"Invalid entity '{entity}'. Must be one of: {', '.join(ENTITY_VALUES)}"
        )
    return entity


def _slugify_key(raw: str) -> str:
    """Normalize a field key: lowercase, non-alnum → underscore, collapse
    repeats, must start with a letter."""
    s = re.sub(r"[^a-z0-9]+", "_", raw.strip().lower()).strip("_")
    if not s or not s[0].isalpha():
        s = "f_" + s
    return s[:64]


async def _get_or_404(entity: str, field_id: str, db: AsyncSession) -> CustomFieldDefinition:
    result = await db.execute(
        select(CustomFieldDefinition).where(
            CustomFieldDefinition.id == field_id,
            CustomFieldDefinition.entity_type == entity,
        )
    )
    defn = result.scalar_one_or_none()
    if not defn:
        raise HTTPException(404, "Custom field definition not found")
    return defn


@router.get("/{entity}", response_model=List[CustomFieldDefinitionResponse])
async def list_definitions(
    entity: str,
    include_inactive: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List a entity's custom field definitions in display order. Active-only
    by default (what the forms render); admin UI passes include_inactive."""
    _validate_entity(entity)
    query = select(CustomFieldDefinition).where(CustomFieldDefinition.entity_type == entity)
    if not include_inactive:
        query = query.where(CustomFieldDefinition.is_active == True)  # noqa: E712
    query = query.order_by(CustomFieldDefinition.position, CustomFieldDefinition.created_at)
    result = await db.execute(query)
    return result.scalars().all()


@router.post(
    "/{entity}",
    response_model=CustomFieldDefinitionResponse,
    status_code=201,
    dependencies=[Depends(require_roles(WRITE_ADMIN_ROLES))],
)
async def create_definition(
    entity: str,
    data: CustomFieldDefinitionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _validate_entity(entity)
    if data.field_type not in FIELD_TYPE_VALUES:
        raise HTTPException(400, f"Invalid field_type. Allowed: {', '.join(FIELD_TYPE_VALUES)}")
    if data.field_type in OPTION_TYPES and not (data.options or []):
        raise HTTPException(400, f"'{data.field_type}' fields require at least one option.")

    field_key = _slugify_key(data.field_key or data.label)

    # Enforce key uniqueness within the entity type (also has a DB constraint).
    existing = await db.execute(
        select(CustomFieldDefinition).where(
            CustomFieldDefinition.entity_type == entity,
            CustomFieldDefinition.field_key == field_key,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"A field with key '{field_key}' already exists for {entity}.")

    position = data.position
    if position is None:
        result = await db.execute(
            select(CustomFieldDefinition.position).where(CustomFieldDefinition.entity_type == entity)
        )
        positions = [p for p in result.scalars().all() if p is not None]
        position = (max(positions) + 1) if positions else 0

    defn = CustomFieldDefinition(
        entity_type=entity,
        field_key=field_key,
        label=data.label,
        field_type=data.field_type,
        options=data.options or ([] if data.field_type in OPTION_TYPES else None),
        required=data.required,
        help_text=data.help_text,
        placeholder=data.placeholder,
        position=position,
        show_in_list=data.show_in_list,
        show_in_report=data.show_in_report,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(defn)
    await db.commit()
    await db.refresh(defn)
    return defn


@router.put(
    "/{entity}/{field_id}",
    response_model=CustomFieldDefinitionResponse,
    dependencies=[Depends(require_roles(WRITE_ADMIN_ROLES))],
)
async def update_definition(
    entity: str,
    field_id: str,
    data: CustomFieldDefinitionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _validate_entity(entity)
    defn = await _get_or_404(entity, field_id, db)

    update_data = data.model_dump(exclude_unset=True)
    if "field_type" in update_data and update_data["field_type"] not in FIELD_TYPE_VALUES:
        raise HTTPException(400, f"Invalid field_type. Allowed: {', '.join(FIELD_TYPE_VALUES)}")
    # The field key is immutable — stored values are keyed by it. (Not in the
    # update schema, but guard anyway.)
    update_data.pop("field_key", None)
    for key, value in update_data.items():
        setattr(defn, key, value)

    # If it's now an option type, it must have options.
    if defn.field_type in OPTION_TYPES and not (defn.options or []):
        raise HTTPException(400, f"'{defn.field_type}' fields require at least one option.")

    defn.updated_by = current_user.id
    await db.commit()
    await db.refresh(defn)
    return defn


@router.post(
    "/{entity}/reorder",
    response_model=List[CustomFieldDefinitionResponse],
    dependencies=[Depends(require_roles(WRITE_ADMIN_ROLES))],
)
async def reorder_definitions(
    entity: str,
    data: ReorderRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _validate_entity(entity)
    result = await db.execute(
        select(CustomFieldDefinition).where(CustomFieldDefinition.entity_type == entity)
    )
    by_id = {d.id: d for d in result.scalars().all()}
    for item in data.fields:
        defn = by_id.get(item.id)
        if defn:
            defn.position = item.position
            defn.updated_by = current_user.id
    await db.commit()

    result = await db.execute(
        select(CustomFieldDefinition)
        .where(CustomFieldDefinition.entity_type == entity)
        .order_by(CustomFieldDefinition.position, CustomFieldDefinition.created_at)
    )
    return result.scalars().all()


@router.delete(
    "/{entity}/{field_id}",
    dependencies=[Depends(require_roles(WRITE_ADMIN_ROLES))],
)
async def delete_definition(
    entity: str,
    field_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a definition. Existing values stored under its key in entity
    rows are left in place (harmless — nothing renders them) rather than
    rewriting every row."""
    _validate_entity(entity)
    defn = await _get_or_404(entity, field_id, db)
    await db.delete(defn)
    await db.commit()
    return {"status": "deleted"}
