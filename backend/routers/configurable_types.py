from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List

from database import get_db
from models.configurable_type import ConfigurableType
from models.user import User, UserRole
from schemas.configurable_type import (
    ConfigurableTypeResponse, ConfigurableTypeCreate, ConfigurableTypeUpdate
)
from auth.dependencies import get_current_user, require_roles, WRITE_ADMIN_ROLES

VALID_CATEGORIES = {"asset", "testcase", "finding", "vault", "cleanup", "intel", "infra", "runbook"}

router = APIRouter(
    prefix="/configurable-types",
    tags=["configurable-types"],
)


def _validate_category(category: str) -> str:
    if category not in VALID_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category '{category}'. Must be one of: {', '.join(sorted(VALID_CATEGORIES))}"
        )
    return category


@router.get("/{category}", response_model=List[ConfigurableTypeResponse])
async def list_types(
    category: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all configurable types for a given category, ordered by sort_order."""
    _validate_category(category)
    result = await db.execute(
        select(ConfigurableType)
        .where(ConfigurableType.category == category)
        .order_by(ConfigurableType.sort_order)
    )
    return result.scalars().all()


@router.post(
    "/{category}",
    response_model=ConfigurableTypeResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(WRITE_ADMIN_ROLES))],
)
async def create_type(
    category: str,
    data: ConfigurableTypeCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new configurable type."""
    _validate_category(category)

    # Get max sort_order for this category
    max_result = await db.execute(
        select(func.max(ConfigurableType.sort_order))
        .where(ConfigurableType.category == category)
    )
    max_order = max_result.scalar() or 0

    new_type = ConfigurableType(
        category=category,
        name=data.name,
        description=data.description,
        color=data.color or "#6366f1",
        sort_order=max_order + 1,
    )
    db.add(new_type)
    try:
        await db.commit()
        await db.refresh(new_type)
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=400, detail=f"Type name '{data.name}' already exists in category '{category}'")
    return new_type


@router.put(
    "/{category}/{type_id}",
    response_model=ConfigurableTypeResponse,
    dependencies=[Depends(require_roles(WRITE_ADMIN_ROLES))],
)
async def update_type(
    category: str,
    type_id: str,
    data: ConfigurableTypeUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a configurable type."""
    _validate_category(category)
    result = await db.execute(
        select(ConfigurableType)
        .where(ConfigurableType.id == type_id, ConfigurableType.category == category)
    )
    ct = result.scalar_one_or_none()
    if not ct:
        raise HTTPException(status_code=404, detail="Type not found")

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(ct, key, value)

    try:
        await db.commit()
        await db.refresh(ct)
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Type name must be unique within category")
    return ct


@router.delete(
    "/{category}/{type_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles(WRITE_ADMIN_ROLES))],
)
async def delete_type(
    category: str,
    type_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete a configurable type (blocked if system type or in use)."""
    _validate_category(category)
    result = await db.execute(
        select(ConfigurableType)
        .where(ConfigurableType.id == type_id, ConfigurableType.category == category)
    )
    ct = result.scalar_one_or_none()
    if not ct:
        raise HTTPException(status_code=404, detail="Type not found")

    if ct.is_system:
        raise HTTPException(status_code=400, detail="Cannot delete a system type")

    # Check if any entities reference this type
    usage_check = await _check_usage(db, category, ct.name)
    if usage_check:
        raise HTTPException(status_code=400, detail=f"Cannot delete — {usage_check}")

    await db.delete(ct)
    await db.commit()
    return None


async def _check_usage(db: AsyncSession, category: str, name: str) -> str | None:
    """Check if a type name is in use by any entity. Returns an error message or None."""
    if category == "asset":
        from models.asset import Asset
        result = await db.execute(select(Asset).where(Asset.asset_type == name).limit(1))
        if result.scalar_one_or_none():
            return "assets are using this type"
    elif category == "testcase":
        from models.testcase import TestCase
        result = await db.execute(select(TestCase).where(TestCase.category == name).limit(1))
        if result.scalar_one_or_none():
            return "test cases are using this category"
    elif category == "finding":
        from models.finding import Finding
        result = await db.execute(select(Finding).where(Finding.category == name).limit(1))
        if result.scalar_one_or_none():
            return "findings are using this category"
    elif category == "vault":
        from models.vault import VaultItem
        result = await db.execute(select(VaultItem).where(VaultItem.item_type == name).limit(1))
        if result.scalar_one_or_none():
            return "vault items are using this type"
    elif category == "cleanup":
        from models.cleanup_artifact import CleanupArtifact
        result = await db.execute(select(CleanupArtifact).where(CleanupArtifact.artifact_type == name).limit(1))
        if result.scalar_one_or_none():
            return "cleanup items are using this type"
    elif category == "runbook":
        from models.runbook import Runbook
        result = await db.execute(select(Runbook).where(Runbook.runbook_type == name).limit(1))
        if result.scalar_one_or_none():
            return "runbooks are using this type"
    return None
