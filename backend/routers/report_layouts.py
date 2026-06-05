from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List
from database import get_db

from models.user import User, UserRole
from models.report_layout import ReportLayout, ReportSection, SectionType
from models.report_layout_template import ReportLayoutTemplate, ReportLayoutTemplateSection
from schemas.report_layout import (
    ReportLayoutCreate,
    ReportLayoutUpdate,
    ReportLayoutResponse,
    ReportSectionCreate,
)
from auth.dependencies import get_current_user
from auth.rbac import check_engagement_permission
from models.permission import Permission

router = APIRouter(prefix="/engagements", tags=["report-layouts"])


async def _check_report_read(user: User, engagement_id: str, db: AsyncSession):
    is_admin = user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_perm = await check_engagement_permission(user.id, engagement_id, Permission.REPORT_VIEW.value, db)
        if not has_perm:
            raise HTTPException(status_code=403, detail="Insufficient permissions")


async def _check_report_write(user: User, engagement_id: str, db: AsyncSession):
    is_admin = user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_perm = await check_engagement_permission(user.id, engagement_id, Permission.REPORT_GENERATE.value, db)
        if not has_perm:
            raise HTTPException(status_code=403, detail="Insufficient permissions")


def _replace_sections(layout: ReportLayout, sections_data: List[ReportSectionCreate]):
    """Delete existing sections and create new ones from the payload."""
    layout.sections.clear()
    for s in sections_data:
        layout.sections.append(ReportSection(
            section_type=SectionType(s.section_type.value),
            title=s.title,
            content=s.content or "",
            sort_order=s.sort_order,
            classification_level=getattr(s, "classification_level", None),
            classification_suffix=getattr(s, "classification_suffix", None),
            page_break_before=getattr(s, "page_break_before", None),
        ))


# ── List layouts for an engagement ──
@router.get("/{engagement_id}/report-layouts", response_model=List[ReportLayoutResponse])
async def list_report_layouts(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all report layouts for an engagement, ordered by name."""
    await _check_report_read(current_user, engagement_id, db)
    result = await db.execute(
        select(ReportLayout)
        .where(ReportLayout.engagement_id == engagement_id)
        .options(selectinload(ReportLayout.sections))
        .order_by(ReportLayout.name)
    )
    return result.scalars().all()


# ── Get a single layout ──
@router.get("/{engagement_id}/report-layouts/{layout_id}", response_model=ReportLayoutResponse)
async def get_report_layout(
    engagement_id: str,
    layout_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single report layout by ID, including its sections."""
    await _check_report_read(current_user, engagement_id, db)
    result = await db.execute(
        select(ReportLayout)
        .where(ReportLayout.id == layout_id, ReportLayout.engagement_id == engagement_id)
        .options(selectinload(ReportLayout.sections))
    )
    layout = result.scalar_one_or_none()
    if not layout:
        raise HTTPException(status_code=404, detail="Report layout not found")
    return layout


# ── Create a new layout ──
@router.post("/{engagement_id}/report-layouts", response_model=ReportLayoutResponse, status_code=status.HTTP_201_CREATED)
async def create_report_layout(
    engagement_id: str,
    data: ReportLayoutCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new report layout with ordered sections for an engagement."""
    await _check_report_write(current_user, engagement_id, db)

    layout = ReportLayout(
        name=data.name,
        engagement_id=engagement_id,
        is_default=data.is_default,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    for s in data.sections:
        layout.sections.append(ReportSection(
            section_type=SectionType(s.section_type.value),
            title=s.title,
            content=s.content or "",
            sort_order=s.sort_order,
            classification_level=getattr(s, "classification_level", None),
            classification_suffix=getattr(s, "classification_suffix", None),
            page_break_before=getattr(s, "page_break_before", None),
        ))

    db.add(layout)
    await db.commit()
    await db.refresh(layout)
    # Reload with sections
    result = await db.execute(
        select(ReportLayout)
        .where(ReportLayout.id == layout.id)
        .options(selectinload(ReportLayout.sections))
    )
    return result.scalar_one()


# ── Update a layout (full section replace) ──
@router.put("/{engagement_id}/report-layouts/{layout_id}", response_model=ReportLayoutResponse)
async def update_report_layout(
    engagement_id: str,
    layout_id: str,
    data: ReportLayoutUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a report layout's name, default flag, and/or replace its sections."""
    await _check_report_write(current_user, engagement_id, db)

    result = await db.execute(
        select(ReportLayout)
        .where(ReportLayout.id == layout_id, ReportLayout.engagement_id == engagement_id)
        .options(selectinload(ReportLayout.sections))
    )
    layout = result.scalar_one_or_none()
    if not layout:
        raise HTTPException(status_code=404, detail="Report layout not found")

    if data.name is not None:
        layout.name = data.name
    if data.is_default is not None:
        layout.is_default = data.is_default
    if data.sections is not None:
        _replace_sections(layout, data.sections)

    layout.updated_by = current_user.id
    await db.commit()
    await db.refresh(layout)

    result = await db.execute(
        select(ReportLayout)
        .where(ReportLayout.id == layout.id)
        .options(selectinload(ReportLayout.sections))
    )
    return result.scalar_one()


# ── Delete a layout ──
@router.delete("/{engagement_id}/report-layouts/{layout_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report_layout(
    engagement_id: str,
    layout_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a report layout and its sections."""
    await _check_report_write(current_user, engagement_id, db)

    result = await db.execute(
        select(ReportLayout)
        .where(ReportLayout.id == layout_id, ReportLayout.engagement_id == engagement_id)
    )
    layout = result.scalar_one_or_none()
    if not layout:
        raise HTTPException(status_code=404, detail="Report layout not found")

    await db.delete(layout)
    await db.commit()
    return None


# ── Import layout from a template ──
@router.post("/{engagement_id}/report-layouts/from-template/{template_id}", response_model=ReportLayoutResponse, status_code=status.HTTP_201_CREATED)
async def import_layout_from_template(
    engagement_id: str,
    template_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new report layout by importing sections from a layout template."""
    await _check_report_write(current_user, engagement_id, db)

    # Fetch template
    tmpl_result = await db.execute(
        select(ReportLayoutTemplate)
        .where(ReportLayoutTemplate.id == template_id)
        .options(selectinload(ReportLayoutTemplate.sections))
    )
    template = tmpl_result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Report layout template not found")

    # Create layout from template
    layout = ReportLayout(
        name=template.name,
        engagement_id=engagement_id,
        is_default=False,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    for ts in template.sections:
        layout.sections.append(ReportSection(
            section_type=ts.section_type,
            title=ts.title,
            content=ts.content or "",
            sort_order=ts.sort_order,
        ))

    db.add(layout)
    await db.commit()
    await db.refresh(layout)

    result = await db.execute(
        select(ReportLayout)
        .where(ReportLayout.id == layout.id)
        .options(selectinload(ReportLayout.sections))
    )
    return result.scalar_one()
