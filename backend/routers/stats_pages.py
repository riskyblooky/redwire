"""
Stats Pages router — CRUD for the globally-shared, tabbed stats view.

A stats page is a tab on /stats. Every viewer sees the same page and the
same shared layout; only holders of MANAGE_STATS_PAGES can create pages or
change their layout. Widgets are the existing global DashboardWidget
definitions — a page's `layout` JSON references them by id, exactly like
the per-user dashboard layout, so the widget-data + query-builder plumbing
in dashboard_widgets.py is reused wholesale (see get_widget_data's
`?context=stats`).
"""

import logging
from typing import Optional, List
from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User
from models.stats_page import StatsPage
from models.permission import Permission
from auth.dependencies import get_current_user
from auth.permissions import has_global_permission
from utils.collaboration import create_activity_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stats-pages", tags=["stats-pages"])


# ── Schemas ──────────────────────────────────────────────────────────

class LayoutItem(BaseModel):
    widget_id: str
    x: int = 0
    y: int = 0
    w: int = 1
    h: int = 1


class StatsPageCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    icon: Optional[str] = Field(None, max_length=50)
    position: Optional[int] = Field(None, ge=0)


class StatsPageUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    icon: Optional[str] = Field(None, max_length=50)
    position: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None


class StatsPageLayoutUpdate(BaseModel):
    layout: List[LayoutItem]


class ReorderItem(BaseModel):
    id: str
    position: int = Field(..., ge=0)


class ReorderRequest(BaseModel):
    pages: List[ReorderItem] = Field(..., min_length=1)


# ── Helpers ──────────────────────────────────────────────────────────

def _page_to_dict(p: StatsPage) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "icon": p.icon,
        "position": p.position,
        "layout": p.layout or [],
        "is_system": p.is_system,
        "is_active": p.is_active,
    }


async def _require_manage(current_user: User, db: AsyncSession) -> None:
    if not await has_global_permission(current_user, Permission.MANAGE_STATS_PAGES, db):
        raise HTTPException(
            status_code=403,
            detail="Insufficient permissions. Required: manage_stats_pages",
        )


async def _get_page_or_404(page_id: str, db: AsyncSession) -> StatsPage:
    result = await db.execute(select(StatsPage).where(StatsPage.id == page_id))
    page = result.scalar_one_or_none()
    if not page:
        raise HTTPException(404, "Stats page not found")
    return page


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("")
async def list_stats_pages(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List active stats pages in tab order. Any authenticated user — the
    pages are global and shared; scoping of the DATA inside each widget is
    handled at the widget-data endpoint, not here."""
    result = await db.execute(
        select(StatsPage)
        .where(StatsPage.is_active == True)  # noqa: E712
        .order_by(StatsPage.position, StatsPage.created_at)
    )
    return [_page_to_dict(p) for p in result.scalars().all()]


@router.post("", status_code=201)
async def create_stats_page(
    data: StatsPageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new stats-page tab."""
    await _require_manage(current_user, db)

    position = data.position
    if position is None:
        # Append after the current last tab.
        result = await db.execute(select(StatsPage.position))
        positions = [p for p in result.scalars().all() if p is not None]
        position = (max(positions) + 1) if positions else 0

    page = StatsPage(
        name=data.name,
        icon=data.icon,
        position=position,
        layout=[],
        is_system=False,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(page)
    await db.commit()
    await db.refresh(page)

    await create_activity_log(
        db,
        engagement_id=None,
        user_id=current_user.id,
        action="created",
        resource_type="stats_page",
        resource_id=page.id,
        resource_name=page.name,
        details=f"Created stats page: {page.name}",
    )
    return _page_to_dict(page)


@router.put("/{page_id}")
async def update_stats_page(
    page_id: str,
    data: StatsPageUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a page's name / icon / order / active flag."""
    await _require_manage(current_user, db)
    page = await _get_page_or_404(page_id, db)

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(page, key, value)
    page.updated_by = current_user.id
    await db.commit()
    await db.refresh(page)

    await create_activity_log(
        db,
        engagement_id=None,
        user_id=current_user.id,
        action="updated",
        resource_type="stats_page",
        resource_id=page.id,
        resource_name=page.name,
        details=f"Updated stats page: {page.name}",
    )
    return _page_to_dict(page)


@router.put("/{page_id}/layout")
async def save_stats_page_layout(
    page_id: str,
    data: StatsPageLayoutUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Replace a page's shared widget layout. This is what every viewer
    sees — there is no per-user layout for stats pages."""
    await _require_manage(current_user, db)
    page = await _get_page_or_404(page_id, db)

    page.layout = [item.model_dump() for item in data.layout]
    page.updated_by = current_user.id
    await db.commit()
    await db.refresh(page)
    return _page_to_dict(page)


@router.post("/reorder")
async def reorder_stats_pages(
    data: ReorderRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Bulk-set tab order. Ignores ids that don't exist."""
    await _require_manage(current_user, db)

    result = await db.execute(select(StatsPage))
    by_id = {p.id: p for p in result.scalars().all()}
    for item in data.pages:
        page = by_id.get(item.id)
        if page:
            page.position = item.position
            page.updated_by = current_user.id
    await db.commit()

    result = await db.execute(
        select(StatsPage)
        .where(StatsPage.is_active == True)  # noqa: E712
        .order_by(StatsPage.position, StatsPage.created_at)
    )
    return [_page_to_dict(p) for p in result.scalars().all()]


@router.delete("/{page_id}")
async def delete_stats_page(
    page_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a page. System pages can't be deleted."""
    await _require_manage(current_user, db)
    page = await _get_page_or_404(page_id, db)
    if page.is_system:
        raise HTTPException(403, "Cannot delete system stats pages")

    name = page.name
    await db.delete(page)
    await db.commit()

    await create_activity_log(
        db,
        engagement_id=None,
        user_id=current_user.id,
        action="deleted",
        resource_type="stats_page",
        resource_id=page_id,
        resource_name=name,
        details=f"Deleted stats page: {name}",
    )
    return {"status": "deleted"}
