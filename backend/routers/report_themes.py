from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from database import get_db
from models.user import User, UserRole
from models.report_theme import ReportTheme
from schemas.report_theme import ReportThemeCreate, ReportThemeUpdate, ReportThemeResponse
from auth.dependencies import get_current_user

router = APIRouter(prefix="/report-themes", tags=["report-themes"])


def _check_manage_permission(user: User):
    """Check if user has permission to manage report themes (Admin/Team Lead)."""
    if user.role not in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]:
        raise HTTPException(status_code=403, detail="Insufficient permissions to manage report themes")


@router.get("", response_model=List[ReportThemeResponse])
async def list_report_themes(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all report themes."""
    result = await db.execute(
        select(ReportTheme).order_by(ReportTheme.name)
    )
    return result.scalars().all()


@router.get("/{theme_id}", response_model=ReportThemeResponse)
async def get_report_theme(
    theme_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific report theme."""
    result = await db.execute(
        select(ReportTheme).where(ReportTheme.id == theme_id)
    )
    theme = result.scalar_one_or_none()
    if not theme:
        raise HTTPException(status_code=404, detail="Report theme not found")
    return theme


@router.post("", response_model=ReportThemeResponse, status_code=status.HTTP_201_CREATED)
async def create_report_theme(
    data: ReportThemeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new report theme. Admin/Team Lead only."""
    _check_manage_permission(current_user)

    # If marking as default, unset other defaults
    if data.is_default:
        await _unset_defaults(db)

    theme = ReportTheme(
        **data.model_dump(),
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(theme)
    await db.commit()
    await db.refresh(theme)
    return theme


@router.put("/{theme_id}", response_model=ReportThemeResponse)
async def update_report_theme(
    theme_id: str,
    data: ReportThemeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a report theme. Admin/Team Lead only."""
    _check_manage_permission(current_user)

    result = await db.execute(
        select(ReportTheme).where(ReportTheme.id == theme_id)
    )
    theme = result.scalar_one_or_none()
    if not theme:
        raise HTTPException(status_code=404, detail="Report theme not found")

    update_data = data.model_dump(exclude_unset=True)

    # If marking as default, unset other defaults
    if update_data.get("is_default"):
        await _unset_defaults(db, exclude_id=theme_id)

    for key, value in update_data.items():
        setattr(theme, key, value)

    theme.updated_by = current_user.id
    await db.commit()
    await db.refresh(theme)
    return theme


@router.delete("/{theme_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report_theme(
    theme_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a report theme. Admin/Team Lead only."""
    _check_manage_permission(current_user)

    result = await db.execute(
        select(ReportTheme).where(ReportTheme.id == theme_id)
    )
    theme = result.scalar_one_or_none()
    if not theme:
        raise HTTPException(status_code=404, detail="Report theme not found")

    await db.delete(theme)
    await db.commit()
    return None


async def _unset_defaults(db: AsyncSession, exclude_id: str = None):
    """Unset is_default on all themes (optionally except one)."""
    query = select(ReportTheme).where(ReportTheme.is_default == True)
    if exclude_id:
        query = query.where(ReportTheme.id != exclude_id)
    result = await db.execute(query)
    for theme in result.scalars().all():
        theme.is_default = False
