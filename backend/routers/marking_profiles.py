from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from database import get_db
from models.user import User, UserRole
from models.marking_profile import MarkingProfile
from schemas.marking_profile import (
    MarkingProfileCreate,
    MarkingProfileUpdate,
    MarkingProfileResponse,
)
from auth.dependencies import get_current_user

router = APIRouter(prefix="/marking-profiles", tags=["marking-profiles"])


def _check_manage_permission(user: User):
    """Only Admin / Team Lead may manage marking profiles."""
    if user.role not in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]:
        raise HTTPException(status_code=403, detail="Insufficient permissions to manage marking profiles")


async def _unset_defaults(db: AsyncSession, exclude_id: str = None):
    query = select(MarkingProfile).where(MarkingProfile.is_default == True)
    if exclude_id:
        query = query.where(MarkingProfile.id != exclude_id)
    result = await db.execute(query)
    for profile in result.scalars().all():
        profile.is_default = False


@router.get("", response_model=List[MarkingProfileResponse])
async def list_marking_profiles(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(MarkingProfile).order_by(MarkingProfile.name))
    return result.scalars().all()


@router.get("/{profile_id}", response_model=MarkingProfileResponse)
async def get_marking_profile(
    profile_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(MarkingProfile).where(MarkingProfile.id == profile_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Marking profile not found")
    return profile


@router.post("", response_model=MarkingProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_marking_profile(
    data: MarkingProfileCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _check_manage_permission(current_user)

    if data.is_default:
        await _unset_defaults(db)

    payload = data.model_dump()
    # Pydantic nested models → plain dicts for the JSON column.
    payload["levels"] = [lvl for lvl in payload.get("levels", [])]

    profile = MarkingProfile(
        **payload,
        is_builtin=False,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


@router.put("/{profile_id}", response_model=MarkingProfileResponse)
async def update_marking_profile(
    profile_id: str,
    data: MarkingProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _check_manage_permission(current_user)

    result = await db.execute(select(MarkingProfile).where(MarkingProfile.id == profile_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Marking profile not found")
    if profile.is_builtin:
        raise HTTPException(status_code=403, detail="Built-in marking profiles cannot be edited. Duplicate it to customize.")

    update_data = data.model_dump(exclude_unset=True)

    if update_data.get("is_default"):
        await _unset_defaults(db, exclude_id=profile_id)

    for key, value in update_data.items():
        setattr(profile, key, value)

    profile.updated_by = current_user.id
    await db.commit()
    await db.refresh(profile)
    return profile


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_marking_profile(
    profile_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _check_manage_permission(current_user)

    result = await db.execute(select(MarkingProfile).where(MarkingProfile.id == profile_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Marking profile not found")
    if profile.is_builtin:
        raise HTTPException(status_code=403, detail="Built-in marking profiles cannot be deleted.")

    await db.delete(profile)
    await db.commit()
    return None
