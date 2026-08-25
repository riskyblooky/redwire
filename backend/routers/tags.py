from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional
from database import get_db

from models.user import User, UserRole
from models.finding import Tag
from models.associations import FindingTag
from models.permission import Permission
from schemas.tag import TagCreate, TagUpdate, TagResponse
from auth.dependencies import get_current_user
from auth.permissions import has_global_permission


router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("", response_model=List[TagResponse])
async def get_tags(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    entity_type: Optional[str] = Query(None, description="Filter to one scope: finding | testcase | engagement"),
):
    """Get tags, optionally filtered to a single entity-type scope."""
    stmt = select(Tag)
    if entity_type:
        stmt = stmt.where(Tag.entity_type == entity_type)
    result = await db.execute(stmt.order_by(Tag.name))
    return result.scalars().all()


@router.post("", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
async def create_tag(
    tag_data: TagCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new tag. Requires manage_tags permission."""
    if not await has_global_permission(current_user, Permission.MANAGE_TAGS, db):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    # Uniqueness is per (name, entity_type) — the same name may exist for a
    # different scope (e.g. "critical" as both a finding and engagement tag).
    existing = await db.execute(
        select(Tag).where(Tag.name == tag_data.name, Tag.entity_type == tag_data.entity_type)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="A tag with this name already exists for this scope")

    new_tag = Tag(**tag_data.model_dump())
    db.add(new_tag)
    await db.commit()
    await db.refresh(new_tag)
    return new_tag


@router.put("/{tag_id}", response_model=TagResponse)
async def update_tag(
    tag_id: str,
    tag_data: TagUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a tag. Requires manage_tags permission."""
    if not await has_global_permission(current_user, Permission.MANAGE_TAGS, db):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    result = await db.execute(select(Tag).where(Tag.id == tag_id))
    tag = result.scalar_one_or_none()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")

    update_fields = tag_data.model_dump(exclude_unset=True)

    # If renaming, check uniqueness within the tag's own scope.
    if "name" in update_fields and update_fields["name"] != tag.name:
        existing = await db.execute(
            select(Tag).where(Tag.name == update_fields["name"], Tag.entity_type == tag.entity_type)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="A tag with this name already exists for this scope")

    for field, value in update_fields.items():
        setattr(tag, field, value)

    await db.commit()
    await db.refresh(tag)
    return tag


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(
    tag_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a tag. Requires manage_tags permission. Cascades removal from findings."""
    if not await has_global_permission(current_user, Permission.MANAGE_TAGS, db):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    result = await db.execute(select(Tag).where(Tag.id == tag_id))
    tag = result.scalar_one_or_none()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")

    await db.delete(tag)
    await db.commit()
    return None


@router.get("/can-manage", response_model=bool)
async def can_manage_tags(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Check if current user can manage tags."""
    return await has_global_permission(current_user, Permission.MANAGE_TAGS, db)
