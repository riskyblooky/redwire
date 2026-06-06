from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_
from sqlalchemy.orm import selectinload
from typing import List, Optional
from datetime import datetime
import logging
from database import get_db
import uuid

from models.user import User, UserRole
from models.template_status import TemplateStatus
from models.runbook import Runbook, RunbookItem
from models.testcase_template import TestCaseTemplate
from models.testcase import TestCase
from schemas.runbook import RunbookCreate, RunbookUpdate, RunbookResponse
from schemas.template_workflow import TemplateRejectRequest, TemplateApproveRequest
from utils.template_workflow import enforce_approve_workflow
from auth.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/runbooks", tags=["runbooks"])


def _can_manage(user: User) -> bool:
    return user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]


def _enforce_referenced_templates_published(
    runbook: Runbook, current_user: User, gate: str
) -> None:
    """GHSA-8357-pmf3-28f8: refuse approve/apply if any referenced
    testcase-template isn't PUBLISHED. Items with a missing template row
    are tolerated (apply skips them; approve doesn't materialize anything
    from them) so an orphaned reference doesn't block the workflow.

    Without this gate, a creator's never-reviewed DRAFT template would
    materialize into every engagement that applies the runbook (apply
    derefs ``item.template`` live), and a later unpublish-edit cycle on
    a previously-PUBLISHED template would push the new body into every
    apply that follows. The companion content-freeze hardening (snapshot
    template content into ``runbook_items`` at approve time) is tracked
    separately.
    """
    offenders = []
    for item in runbook.items or []:
        tmpl = item.template
        if tmpl is None:
            continue
        if tmpl.status != TemplateStatus.PUBLISHED:
            offenders.append(f"{tmpl.title!r} ({tmpl.status.value})")
    if offenders:
        logger.warning(
            "Blocked runbook %s on %s by user %s: %d non-PUBLISHED template(s): %s",
            gate, runbook.id, current_user.id, len(offenders), ", ".join(offenders[:5]),
        )
        plural = len(offenders) != 1
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Runbook references {len(offenders)} testcase-template"
                f"{'s' if plural else ''} that {'are' if plural else 'is'} "
                "not PUBLISHED. Every referenced template must be PUBLISHED "
                "before the runbook can be approved or applied."
            ),
        )


def _visibility_clause(current_user: User):
    """SQL OR-clause matching runbooks the user is allowed to see."""
    parts = [Runbook.status == TemplateStatus.PUBLISHED]
    parts.append(
        and_(
            Runbook.status == TemplateStatus.DRAFT,
            Runbook.created_by == current_user.id,
        )
    )
    if _can_manage(current_user):
        parts.append(Runbook.status == TemplateStatus.SUBMITTED)
    else:
        parts.append(
            and_(
                Runbook.status == TemplateStatus.SUBMITTED,
                Runbook.created_by == current_user.id,
            )
        )
    return or_(*parts)


async def _load_runbook(runbook_id: str, db: AsyncSession) -> Runbook | None:
    result = await db.execute(
        select(Runbook)
        .where(Runbook.id == runbook_id)
        .options(selectinload(Runbook.items).selectinload(RunbookItem.template))
    )
    return result.scalar_one_or_none()


def _is_visible(runbook: Runbook, current_user: User) -> bool:
    if runbook.status == TemplateStatus.PUBLISHED:
        return True
    if runbook.created_by == current_user.id:
        return True
    if runbook.status == TemplateStatus.SUBMITTED and _can_manage(current_user):
        return True
    return False


async def _ensure_template_visible(
    template_id: str | None, current_user: User, db: AsyncSession
) -> None:
    """GHSA-r9qx-3j9h-qx7f: refuse to link a runbook item to a template the
    caller can't see. Mirrors testcase_templates.py's read-time gate:
    PUBLISHED to all, otherwise creator-only (manage roles see all)."""
    if not template_id:
        return
    template = (
        await db.execute(select(TestCaseTemplate).where(TestCaseTemplate.id == template_id))
    ).scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=404, detail="Referenced template not found")
    if template.status == TemplateStatus.PUBLISHED:
        return
    if template.created_by == current_user.id:
        return
    if _can_manage(current_user):
        return
    raise HTTPException(
        status_code=403,
        detail="You do not have access to one of the referenced templates.",
    )


@router.get("", response_model=List[RunbookResponse])
async def get_runbooks(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List runbooks visible to the user (PUBLISHED to all; DRAFT/SUBMITTED scoped per workflow rules)."""
    result = await db.execute(
        select(Runbook)
        .where(_visibility_clause(current_user))
        .options(selectinload(Runbook.items).selectinload(RunbookItem.template))
        .order_by(Runbook.name.asc())
    )
    return result.scalars().all()


@router.get("/{runbook_id}", response_model=RunbookResponse)
async def get_runbook(
    runbook_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific runbook with its items."""
    runbook = await _load_runbook(runbook_id, db)
    if not runbook or not _is_visible(runbook, current_user):
        raise HTTPException(status_code=404, detail="Runbook not found")
    return runbook


@router.post("", response_model=RunbookResponse, status_code=status.HTTP_201_CREATED)
async def create_runbook(
    data: RunbookCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new runbook. Any authenticated user — starts as DRAFT."""
    runbook = Runbook(
        id=str(uuid.uuid4()),
        name=data.name,
        description=data.description,
        runbook_type=data.runbook_type,
        status=TemplateStatus.DRAFT,
        created_by=current_user.id,
    )
    db.add(runbook)
    await db.flush()

    temp_to_id = {}
    for item_data in data.items:
        item_id = str(uuid.uuid4())
        temp_to_id[item_data.temp_key] = item_id

        parent_id = None
        if item_data.parent_temp_key:
            parent_id = temp_to_id.get(item_data.parent_temp_key)
            if not parent_id:
                raise HTTPException(status_code=400, detail=f"Invalid parent_temp_key: {item_data.parent_temp_key}")

        await _ensure_template_visible(item_data.template_id, current_user, db)
        item = RunbookItem(
            id=item_id,
            runbook_id=runbook.id,
            template_id=item_data.template_id,
            parent_id=parent_id,
            sort_order=item_data.sort_order,
        )
        db.add(item)

    await db.commit()

    return await _load_runbook(runbook.id, db)


@router.put("/{runbook_id}", response_model=RunbookResponse)
async def update_runbook(
    runbook_id: str,
    data: RunbookUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a runbook.

    - DRAFT: editable by creator (or manage roles).
    - SUBMITTED: locked. Withdraw or reject before editing.
    - PUBLISHED: editable only by manage roles.
    """
    result = await db.execute(
        select(Runbook).where(Runbook.id == runbook_id).options(selectinload(Runbook.items))
    )
    runbook = result.scalar_one_or_none()
    if not runbook:
        raise HTTPException(status_code=404, detail="Runbook not found")

    if runbook.status == TemplateStatus.SUBMITTED:
        raise HTTPException(
            status_code=409,
            detail="Submitted runbooks are locked. Withdraw or reject the submission to edit.",
        )

    if runbook.status == TemplateStatus.DRAFT:
        if runbook.created_by != current_user.id and not _can_manage(current_user):
            raise HTTPException(status_code=403, detail="Only the creator can edit a draft")
    else:  # PUBLISHED
        if not _can_manage(current_user):
            raise HTTPException(status_code=403, detail="Insufficient permissions")

    if data.name is not None:
        runbook.name = data.name
    if data.description is not None:
        runbook.description = data.description
    if data.runbook_type is not None:
        runbook.runbook_type = data.runbook_type
    runbook.updated_by = current_user.id

    if data.items is not None:
        for old_item in runbook.items:
            await db.delete(old_item)
        await db.flush()

        temp_to_id = {}
        for item_data in data.items:
            item_id = str(uuid.uuid4())
            temp_to_id[item_data.temp_key] = item_id

            parent_id = None
            if item_data.parent_temp_key:
                parent_id = temp_to_id.get(item_data.parent_temp_key)
                if not parent_id:
                    raise HTTPException(status_code=400, detail=f"Invalid parent_temp_key: {item_data.parent_temp_key}")

            await _ensure_template_visible(item_data.template_id, current_user, db)
            item = RunbookItem(
                id=item_id,
                runbook_id=runbook.id,
                template_id=item_data.template_id,
                parent_id=parent_id,
                sort_order=item_data.sort_order,
            )
            db.add(item)

    await db.commit()

    return await _load_runbook(runbook.id, db)


@router.delete("/{runbook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_runbook(
    runbook_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a runbook. SUBMITTED is blocked."""
    result = await db.execute(select(Runbook).where(Runbook.id == runbook_id))
    runbook = result.scalar_one_or_none()
    if not runbook:
        raise HTTPException(status_code=404, detail="Runbook not found")

    if runbook.status == TemplateStatus.SUBMITTED:
        raise HTTPException(
            status_code=409,
            detail="Submitted runbooks cannot be deleted. Withdraw or reject the submission first.",
        )

    if runbook.status == TemplateStatus.DRAFT:
        if runbook.created_by != current_user.id and current_user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Only the creator can delete a draft")
    else:  # PUBLISHED
        if not _can_manage(current_user):
            raise HTTPException(status_code=403, detail="Insufficient permissions")

    await db.delete(runbook)
    await db.commit()
    return None


# ── Workflow transitions ──────────────────────────────────────────────────

@router.post("/{runbook_id}/submit", response_model=RunbookResponse)
async def submit_runbook(
    runbook_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Submit a draft for review (DRAFT → SUBMITTED). Creator only."""
    result = await db.execute(select(Runbook).where(Runbook.id == runbook_id))
    runbook = result.scalar_one_or_none()
    if not runbook:
        raise HTTPException(status_code=404, detail="Runbook not found")
    if runbook.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Only the creator can submit a draft")
    if runbook.status != TemplateStatus.DRAFT:
        raise HTTPException(status_code=409, detail=f"Cannot submit a runbook in {runbook.status.value} state")

    runbook.status = TemplateStatus.SUBMITTED
    runbook.submitted_at = datetime.utcnow()
    runbook.review_note = None
    runbook.updated_by = current_user.id

    await db.commit()
    return await _load_runbook(runbook.id, db)


@router.post("/{runbook_id}/withdraw", response_model=RunbookResponse)
async def withdraw_runbook(
    runbook_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Withdraw a submission back to draft (SUBMITTED → DRAFT). Creator only."""
    result = await db.execute(select(Runbook).where(Runbook.id == runbook_id))
    runbook = result.scalar_one_or_none()
    if not runbook:
        raise HTTPException(status_code=404, detail="Runbook not found")
    if runbook.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Only the creator can withdraw a submission")
    if runbook.status != TemplateStatus.SUBMITTED:
        raise HTTPException(status_code=409, detail=f"Cannot withdraw a runbook in {runbook.status.value} state")

    runbook.status = TemplateStatus.DRAFT
    runbook.submitted_at = None
    runbook.updated_by = current_user.id

    await db.commit()
    return await _load_runbook(runbook.id, db)


@router.post("/{runbook_id}/approve", response_model=RunbookResponse)
async def approve_runbook(
    runbook_id: str,
    payload: Optional[TemplateApproveRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Approve and publish (DRAFT or SUBMITTED → PUBLISHED). Manage roles only."""
    if not _can_manage(current_user):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    runbook = await _load_runbook(runbook_id, db)
    if not runbook:
        raise HTTPException(status_code=404, detail="Runbook not found")
    enforce_approve_workflow(runbook, current_user, payload, "runbook")
    if runbook.status not in (TemplateStatus.DRAFT, TemplateStatus.SUBMITTED):
        raise HTTPException(status_code=409, detail=f"Cannot publish a runbook in {runbook.status.value} state")

    # GHSA-8357-pmf3-28f8: every referenced template must be PUBLISHED.
    _enforce_referenced_templates_published(runbook, current_user, "approve")

    runbook.status = TemplateStatus.PUBLISHED
    runbook.published_at = datetime.utcnow()
    runbook.published_by = current_user.id
    runbook.review_note = None
    runbook.updated_by = current_user.id

    await db.commit()
    return await _load_runbook(runbook.id, db)


@router.post("/{runbook_id}/reject", response_model=RunbookResponse)
async def reject_runbook(
    runbook_id: str,
    payload: TemplateRejectRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reject a submission with feedback (SUBMITTED → DRAFT). Manage roles only."""
    if not _can_manage(current_user):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    result = await db.execute(select(Runbook).where(Runbook.id == runbook_id))
    runbook = result.scalar_one_or_none()
    if not runbook:
        raise HTTPException(status_code=404, detail="Runbook not found")
    if runbook.status != TemplateStatus.SUBMITTED:
        raise HTTPException(status_code=409, detail="Only submitted runbooks can be rejected")

    runbook.status = TemplateStatus.DRAFT
    runbook.submitted_at = None
    runbook.review_note = payload.review_note
    runbook.updated_by = current_user.id

    await db.commit()
    return await _load_runbook(runbook.id, db)


@router.post("/{runbook_id}/unpublish", response_model=RunbookResponse)
async def unpublish_runbook(
    runbook_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Move a published runbook back to draft (PUBLISHED → DRAFT). Manage roles only."""
    if not _can_manage(current_user):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    result = await db.execute(select(Runbook).where(Runbook.id == runbook_id))
    runbook = result.scalar_one_or_none()
    if not runbook:
        raise HTTPException(status_code=404, detail="Runbook not found")
    if runbook.status != TemplateStatus.PUBLISHED:
        raise HTTPException(status_code=409, detail="Only published runbooks can be unpublished")

    runbook.status = TemplateStatus.DRAFT
    runbook.published_at = None
    runbook.published_by = None
    runbook.updated_by = current_user.id

    await db.commit()
    return await _load_runbook(runbook.id, db)


@router.post("/{runbook_id}/apply/{engagement_id}", status_code=status.HTTP_201_CREATED)
async def apply_runbook_to_engagement(
    runbook_id: str,
    engagement_id: str,
    parent_testcase_id: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Apply a runbook to an engagement — creates real TestCase records
    from the runbook's template tree. Optionally nest under an existing
    test case via parent_testcase_id query param.

    The runbook must be visible to the user (PUBLISHED, or their own DRAFT/SUBMITTED).
    """
    from auth.rbac import check_engagement_permission
    from models.permission import Permission
    from utils.collaboration import create_activity_log

    runbook = await _load_runbook(runbook_id, db)
    if not runbook or not _is_visible(runbook, current_user):
        raise HTTPException(status_code=404, detail="Runbook not found")

    # GHSA-8357-pmf3-28f8: refuse the materialization if any referenced
    # template has drifted off PUBLISHED since approval (or was never
    # PUBLISHED in the first place — apply doesn't require approve).
    _enforce_referenced_templates_published(runbook, current_user, "apply")

    # Check engagement-scoped testcase create permission
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_permission = await check_engagement_permission(
            current_user.id, engagement_id, Permission.TESTCASE_CREATE.value, db
        )
        if not has_permission:
            raise HTTPException(status_code=403, detail="Insufficient permissions to create test cases")

    # If nesting under an existing test case, verify it belongs to the
    # target engagement. Otherwise an attacker could parent the new test
    # cases under a foreign engagement's testcase tree.
    if parent_testcase_id:
        parent_tc = (await db.execute(
            select(TestCase).where(TestCase.id == parent_testcase_id)
        )).scalar_one_or_none()
        if not parent_tc:
            raise HTTPException(status_code=404, detail="Parent test case not found")
        if parent_tc.engagement_id != engagement_id:
            raise HTTPException(status_code=400, detail="Parent test case belongs to a different engagement")

    # Build test cases from runbook items, preserving tree structure
    runbook_item_id_to_testcase_id = {}
    created_testcases = []

    items_by_parent = {}
    for item in runbook.items:
        key = item.parent_id or "__root__"
        items_by_parent.setdefault(key, []).append(item)

    for key in items_by_parent:
        items_by_parent[key].sort(key=lambda x: x.sort_order)

    queue = list(items_by_parent.get("__root__", []))
    ordered_items = []
    while queue:
        current = queue.pop(0)
        ordered_items.append(current)
        children = items_by_parent.get(current.id, [])
        queue.extend(children)

    for item in ordered_items:
        template = item.template
        if not template:
            continue

        tc_parent_id = None
        if item.parent_id:
            tc_parent_id = runbook_item_id_to_testcase_id.get(item.parent_id)
        elif parent_testcase_id:
            tc_parent_id = parent_testcase_id

        testcase_id = str(uuid.uuid4())
        testcase = TestCase(
            id=testcase_id,
            engagement_id=engagement_id,
            parent_id=tc_parent_id,
            title=template.title,
            category=template.category,
            description=template.description,
            steps=template.steps,
            expected_result=template.expected_result,
            created_by=current_user.id,
        )
        db.add(testcase)
        runbook_item_id_to_testcase_id[item.id] = testcase_id
        created_testcases.append(testcase)

    await create_activity_log(
        db,
        engagement_id=engagement_id,
        user_id=current_user.id,
        action="applied_runbook",
        resource_type="testcase",
        resource_id=runbook.id,
        resource_name=runbook.name,
        details=f"Applied runbook '{runbook.name}' — created {len(created_testcases)} test cases",
    )

    return {
        "message": f"Runbook '{runbook.name}' applied successfully",
        "testcases_created": len(created_testcases),
    }
