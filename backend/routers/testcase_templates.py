from fastapi import APIRouter, Depends, HTTPException, status, Query
from schemas._field_limits import MAX_LIST_LIMIT
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_
from typing import List, Optional
from datetime import datetime
from database import get_db

from models.user import User, UserRole
from models.template_status import TemplateStatus
from models.testcase_template import TestCaseTemplate
from schemas.testcase_template import (
    TestCaseTemplateCreate,
    TestCaseTemplateUpdate,
    TestCaseTemplateResponse,
)
from schemas.template_workflow import TemplateRejectRequest, TemplateApproveRequest
from utils.template_workflow import enforce_approve_workflow
from auth.dependencies import get_current_user

router = APIRouter(prefix="/testcase-templates", tags=["testcase-templates"])


def _can_manage(user: User) -> bool:
    return user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]


@router.get("", response_model=List[TestCaseTemplateResponse])
async def get_testcase_templates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    category: Optional[str] = Query(None),
    status_filter: Optional[TemplateStatus] = Query(None, alias="status"),
    skip: int = 0,
    limit: int = Query(100, ge=1, le=MAX_LIST_LIMIT),
):
    """List test case templates the user is allowed to see.

    Visibility:
      - PUBLISHED: everyone
      - DRAFT: only the creator
      - SUBMITTED: creator + manage roles (ADMIN, TEAM_LEAD)
    """
    visibility = [TestCaseTemplate.status == TemplateStatus.PUBLISHED]
    visibility.append(
        and_(
            TestCaseTemplate.status == TemplateStatus.DRAFT,
            TestCaseTemplate.created_by == current_user.id,
        )
    )
    if _can_manage(current_user):
        visibility.append(TestCaseTemplate.status == TemplateStatus.SUBMITTED)
    else:
        visibility.append(
            and_(
                TestCaseTemplate.status == TemplateStatus.SUBMITTED,
                TestCaseTemplate.created_by == current_user.id,
            )
        )

    query = select(TestCaseTemplate).where(or_(*visibility))
    if category:
        query = query.where(TestCaseTemplate.category == category)
    if status_filter:
        query = query.where(TestCaseTemplate.status == status_filter)

    query = query.offset(skip).limit(limit).order_by(TestCaseTemplate.title.asc())
    result = await db.execute(query)
    return result.scalars().all()


async def _get_visible_template(
    template_id: str, db: AsyncSession, current_user: User
) -> TestCaseTemplate:
    result = await db.execute(select(TestCaseTemplate).where(TestCaseTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    if template.status == TemplateStatus.PUBLISHED:
        return template
    if template.created_by == current_user.id:
        return template
    if template.status == TemplateStatus.SUBMITTED and _can_manage(current_user):
        return template
    raise HTTPException(status_code=404, detail="Template not found")


@router.get("/{template_id}", response_model=TestCaseTemplateResponse)
async def get_testcase_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _get_visible_template(template_id, db, current_user)


@router.post("", response_model=TestCaseTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_testcase_template(
    template_data: TestCaseTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new test case template. Any authenticated user — starts as DRAFT."""
    new_template = TestCaseTemplate(
        **template_data.model_dump(),
        created_by=current_user.id,
        status=TemplateStatus.DRAFT,
    )
    db.add(new_template)
    await db.commit()
    await db.refresh(new_template)
    return new_template


@router.put("/{template_id}", response_model=TestCaseTemplateResponse)
async def update_testcase_template(
    template_id: str,
    template_data: TestCaseTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a test case template. SUBMITTED is locked. DRAFT: creator+manage. PUBLISHED: manage only."""
    result = await db.execute(select(TestCaseTemplate).where(TestCaseTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    if template.status == TemplateStatus.SUBMITTED:
        raise HTTPException(
            status_code=409,
            detail="Submitted templates are locked. Withdraw or reject the submission to edit.",
        )

    if template.status == TemplateStatus.DRAFT:
        if template.created_by != current_user.id and not _can_manage(current_user):
            raise HTTPException(status_code=403, detail="Only the creator can edit a draft")
    else:  # PUBLISHED
        if not _can_manage(current_user):
            raise HTTPException(status_code=403, detail="Insufficient permissions")

    for field, value in template_data.model_dump(exclude_unset=True).items():
        setattr(template, field, value)

    template.updated_by = current_user.id

    await db.commit()
    await db.refresh(template)
    return template


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_testcase_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a test case template. SUBMITTED is blocked."""
    result = await db.execute(select(TestCaseTemplate).where(TestCaseTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    if template.status == TemplateStatus.SUBMITTED:
        raise HTTPException(
            status_code=409,
            detail="Submitted templates cannot be deleted. Withdraw or reject the submission first.",
        )

    if template.status == TemplateStatus.DRAFT:
        if template.created_by != current_user.id and current_user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Only the creator can delete a draft")
    else:  # PUBLISHED
        if not _can_manage(current_user):
            raise HTTPException(status_code=403, detail="Insufficient permissions")

    await db.delete(template)
    await db.commit()
    return None


# ── Workflow transitions ──────────────────────────────────────────────────

@router.post("/{template_id}/submit", response_model=TestCaseTemplateResponse)
async def submit_testcase_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Submit a draft for review (DRAFT → SUBMITTED). Creator only."""
    result = await db.execute(select(TestCaseTemplate).where(TestCaseTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    if template.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Only the creator can submit a draft")
    if template.status != TemplateStatus.DRAFT:
        raise HTTPException(status_code=409, detail=f"Cannot submit a template in {template.status.value} state")

    template.status = TemplateStatus.SUBMITTED
    template.submitted_at = datetime.utcnow()
    template.review_note = None
    template.updated_by = current_user.id

    await db.commit()
    await db.refresh(template)
    return template


@router.post("/{template_id}/withdraw", response_model=TestCaseTemplateResponse)
async def withdraw_testcase_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Withdraw a submission back to draft (SUBMITTED → DRAFT). Creator only."""
    result = await db.execute(select(TestCaseTemplate).where(TestCaseTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    if template.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Only the creator can withdraw a submission")
    if template.status != TemplateStatus.SUBMITTED:
        raise HTTPException(status_code=409, detail=f"Cannot withdraw a template in {template.status.value} state")

    template.status = TemplateStatus.DRAFT
    template.submitted_at = None
    template.updated_by = current_user.id

    await db.commit()
    await db.refresh(template)
    return template


@router.post("/{template_id}/approve", response_model=TestCaseTemplateResponse)
async def approve_testcase_template(
    template_id: str,
    payload: Optional[TemplateApproveRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Approve and publish (DRAFT or SUBMITTED → PUBLISHED). Manage roles only."""
    if not _can_manage(current_user):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    result = await db.execute(select(TestCaseTemplate).where(TestCaseTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    enforce_approve_workflow(template, current_user, payload, "testcase-template")
    if template.status not in (TemplateStatus.DRAFT, TemplateStatus.SUBMITTED):
        raise HTTPException(status_code=409, detail=f"Cannot publish a template in {template.status.value} state")

    template.status = TemplateStatus.PUBLISHED
    template.published_at = datetime.utcnow()
    template.published_by = current_user.id
    template.review_note = None
    template.updated_by = current_user.id

    await db.commit()
    await db.refresh(template)
    return template


@router.post("/{template_id}/reject", response_model=TestCaseTemplateResponse)
async def reject_testcase_template(
    template_id: str,
    payload: TemplateRejectRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reject a submission with feedback (SUBMITTED → DRAFT). Manage roles only."""
    if not _can_manage(current_user):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    result = await db.execute(select(TestCaseTemplate).where(TestCaseTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    if template.status != TemplateStatus.SUBMITTED:
        raise HTTPException(status_code=409, detail="Only submitted templates can be rejected")

    template.status = TemplateStatus.DRAFT
    template.submitted_at = None
    template.review_note = payload.review_note
    template.updated_by = current_user.id

    await db.commit()
    await db.refresh(template)
    return template


@router.post("/{template_id}/unpublish", response_model=TestCaseTemplateResponse)
async def unpublish_testcase_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Move a published template back to draft (PUBLISHED → DRAFT). Manage roles only."""
    if not _can_manage(current_user):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    result = await db.execute(select(TestCaseTemplate).where(TestCaseTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    if template.status != TemplateStatus.PUBLISHED:
        raise HTTPException(status_code=409, detail="Only published templates can be unpublished")

    template.status = TemplateStatus.DRAFT
    template.published_at = None
    template.published_by = None
    template.updated_by = current_user.id

    await db.commit()
    await db.refresh(template)
    return template
