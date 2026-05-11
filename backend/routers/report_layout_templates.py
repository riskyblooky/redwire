from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List
from database import get_db

from models.user import User, UserRole
from models.report_layout import SectionType
from models.report_layout_template import ReportLayoutTemplate, ReportLayoutTemplateSection
from schemas.report_layout import (
    ReportLayoutTemplateCreate,
    ReportLayoutTemplateUpdate,
    ReportLayoutTemplateResponse,
)
from auth.dependencies import get_current_user
from models.permission import Permission

router = APIRouter(prefix="/report-layout-templates", tags=["report-layout-templates"])


def _check_manage_permission(user: User):
    if user.role not in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")


def _replace_template_sections(template: ReportLayoutTemplate, sections_data):
    """Delete existing sections and create new ones from the payload."""
    template.sections.clear()
    for s in sections_data:
        template.sections.append(ReportLayoutTemplateSection(
            section_type=SectionType(s.section_type.value),
            title=s.title,
            content=s.content or "",
            sort_order=s.sort_order,
        ))


@router.get("", response_model=List[ReportLayoutTemplateResponse])
async def list_report_layout_templates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all report layout templates."""
    result = await db.execute(
        select(ReportLayoutTemplate)
        .options(selectinload(ReportLayoutTemplate.sections))
        .order_by(ReportLayoutTemplate.name)
    )
    return result.scalars().all()


@router.get("/{template_id}", response_model=ReportLayoutTemplateResponse)
async def get_report_layout_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific report layout template."""
    result = await db.execute(
        select(ReportLayoutTemplate)
        .where(ReportLayoutTemplate.id == template_id)
        .options(selectinload(ReportLayoutTemplate.sections))
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Report layout template not found")
    return template


@router.post("", response_model=ReportLayoutTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_report_layout_template(
    data: ReportLayoutTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new report layout template. Admin/Team Lead only."""
    _check_manage_permission(current_user)

    template = ReportLayoutTemplate(
        name=data.name,
        description=data.description,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    for s in data.sections:
        template.sections.append(ReportLayoutTemplateSection(
            section_type=SectionType(s.section_type.value),
            title=s.title,
            content=s.content or "",
            sort_order=s.sort_order,
        ))

    db.add(template)
    await db.commit()
    await db.refresh(template)

    result = await db.execute(
        select(ReportLayoutTemplate)
        .where(ReportLayoutTemplate.id == template.id)
        .options(selectinload(ReportLayoutTemplate.sections))
    )
    return result.scalar_one()


@router.put("/{template_id}", response_model=ReportLayoutTemplateResponse)
async def update_report_layout_template(
    template_id: str,
    data: ReportLayoutTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a report layout template. Admin/Team Lead only."""
    _check_manage_permission(current_user)

    result = await db.execute(
        select(ReportLayoutTemplate)
        .where(ReportLayoutTemplate.id == template_id)
        .options(selectinload(ReportLayoutTemplate.sections))
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Report layout template not found")

    if data.name is not None:
        template.name = data.name
    if data.description is not None:
        template.description = data.description
    if data.sections is not None:
        _replace_template_sections(template, data.sections)

    template.updated_by = current_user.id
    await db.commit()
    await db.refresh(template)

    result = await db.execute(
        select(ReportLayoutTemplate)
        .where(ReportLayoutTemplate.id == template.id)
        .options(selectinload(ReportLayoutTemplate.sections))
    )
    return result.scalar_one()


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report_layout_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a report layout template. Admin/Team Lead only."""
    _check_manage_permission(current_user)

    result = await db.execute(
        select(ReportLayoutTemplate)
        .where(ReportLayoutTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Report layout template not found")

    await db.delete(template)
    await db.commit()
    return None
