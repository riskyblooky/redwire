from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from datetime import datetime

from database import get_db
from models.user import User, UserRole
from models.cleanup_artifact import CleanupArtifact, CleanupArtifactStatus
from models.finding import Finding
from models.testcase import TestCase
from models.asset import Asset
from schemas.cleanup_artifact import CleanupArtifactCreate, CleanupArtifactUpdate, CleanupArtifactResponse
from auth.dependencies import get_current_user
from auth.rbac import check_engagement_permission
from models.permission import Permission
from utils.collaboration import create_activity_log, build_change_summary
from sqlalchemy.orm import selectinload

router = APIRouter(prefix="/cleanup-artifacts", tags=["cleanup-artifacts"])


# ── Engagement-scoping guards (GHSA-6r9w-whxr-3gvr) ─────────────────────

def _is_admin(user: User) -> bool:
    return user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]


async def _require_artifact_view(
    artifact: CleanupArtifact, current_user: User, db: AsyncSession
) -> None:
    if _is_admin(current_user):
        return
    if not await check_engagement_permission(
        current_user.id, artifact.engagement_id, Permission.CLEANUP_VIEW.value, db
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions. You need the 'cleanup_view' permission.",
        )


async def _require_artifact_edit(
    artifact: CleanupArtifact, current_user: User, db: AsyncSession
) -> None:
    """Owner -> CLEANUP_EDIT, otherwise CLEANUP_EDIT_ANY (matches PATCH/DELETE)."""
    if _is_admin(current_user):
        return
    perm = (
        Permission.CLEANUP_EDIT.value
        if artifact.created_by == current_user.id
        else Permission.CLEANUP_EDIT_ANY.value
    )
    if not await check_engagement_permission(
        current_user.id, artifact.engagement_id, perm, db
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions. You need the '{perm}' permission.",
        )


# ============ CRUD ============

@router.get("", response_model=List[CleanupArtifactResponse])
async def get_cleanup_artifacts(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all cleanup artifacts for an engagement."""
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_permission = await check_engagement_permission(
            current_user.id, engagement_id, Permission.CLEANUP_VIEW.value, db
        )
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. You need the 'cleanup_view' permission.",
            )

    result = await db.execute(
        select(CleanupArtifact, User.username.label("creator_username"), User.profile_photo.label("creator_profile_photo"))
        .outerjoin(User, CleanupArtifact.created_by == User.id)
        .options(
            selectinload(CleanupArtifact.findings),
            selectinload(CleanupArtifact.testcases),
            selectinload(CleanupArtifact.assets),
            selectinload(CleanupArtifact.cleaned_by_user),
        )
        .where(CleanupArtifact.engagement_id == engagement_id)
        .order_by(CleanupArtifact.created_at.desc())
    )

    items = []
    for artifact, creator_username, creator_profile_photo in result.all():
        item_dict = CleanupArtifactResponse.model_validate(artifact).model_dump()
        item_dict["created_by_username"] = creator_username
        item_dict["created_by_profile_photo"] = creator_profile_photo
        if artifact.cleaned_by_user:
            item_dict["cleaned_by_username"] = artifact.cleaned_by_user.username
        items.append(CleanupArtifactResponse(**item_dict))

    return items


@router.get("/{artifact_id}", response_model=CleanupArtifactResponse)
async def get_cleanup_artifact(
    artifact_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single cleanup artifact by ID."""
    result = await db.execute(
        select(CleanupArtifact, User.username.label("creator_username"), User.profile_photo.label("creator_profile_photo"))
        .outerjoin(User, CleanupArtifact.created_by == User.id)
        .options(
            selectinload(CleanupArtifact.findings),
            selectinload(CleanupArtifact.testcases),
            selectinload(CleanupArtifact.assets),
            selectinload(CleanupArtifact.cleaned_by_user),
        )
        .where(CleanupArtifact.id == artifact_id)
    )

    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Cleanup artifact not found")

    artifact, creator_username, creator_profile_photo = row
    await _require_artifact_view(artifact, current_user, db)
    item_dict = CleanupArtifactResponse.model_validate(artifact).model_dump()
    item_dict["created_by_username"] = creator_username
    item_dict["created_by_profile_photo"] = creator_profile_photo
    if artifact.cleaned_by_user:
        item_dict["cleaned_by_username"] = artifact.cleaned_by_user.username
    return CleanupArtifactResponse(**item_dict)


@router.post("", response_model=CleanupArtifactResponse, status_code=status.HTTP_201_CREATED)
async def create_cleanup_artifact(
    data: CleanupArtifactCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new cleanup artifact."""
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_permission = await check_engagement_permission(
            current_user.id, data.engagement_id, Permission.CLEANUP_CREATE.value, db
        )
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. You need the 'cleanup_create' permission.",
            )

    db_item = CleanupArtifact(
        **data.model_dump(),
        created_by=current_user.id,
    )
    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)

    await create_activity_log(
        db,
        engagement_id=db_item.engagement_id,
        user_id=current_user.id,
        action="created_cleanup_artifact",
        resource_type="cleanup_artifact",
        resource_id=db_item.id,
        resource_name=db_item.title,
        details=f"Created cleanup artifact: {db_item.title} ({db_item.artifact_type})",
    )

    return db_item


@router.patch("/{artifact_id}", response_model=CleanupArtifactResponse)
async def update_cleanup_artifact(
    artifact_id: str,
    data: CleanupArtifactUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a cleanup artifact."""
    result = await db.execute(
        select(CleanupArtifact)
        .options(selectinload(CleanupArtifact.findings), selectinload(CleanupArtifact.testcases), selectinload(CleanupArtifact.assets))
        .where(CleanupArtifact.id == artifact_id)
    )
    artifact = result.scalar_one_or_none()
    if not artifact:
        raise HTTPException(status_code=404, detail="Cleanup artifact not found")

    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    is_owner = artifact.created_by == current_user.id

    if not is_admin:
        perm = Permission.CLEANUP_EDIT.value if is_owner else Permission.CLEANUP_EDIT_ANY.value
        has_permission = await check_engagement_permission(current_user.id, artifact.engagement_id, perm, db)
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. You need the '{perm}' permission.",
            )

    update_data = data.model_dump(exclude_unset=True)

    # Auto-set cleaned_at / cleaned_by when status transitions to CLEANED
    if "status" in update_data and update_data["status"] == CleanupArtifactStatus.CLEANED:
        if artifact.status != CleanupArtifactStatus.CLEANED:
            update_data["cleaned_at"] = datetime.utcnow()
            update_data["cleaned_by"] = current_user.id

    change_details = build_change_summary(artifact, update_data, label=f"Updated cleanup artifact '{artifact.title}'")

    for key, value in update_data.items():
        setattr(artifact, key, value)

    artifact.updated_by = current_user.id
    await db.commit()
    await db.refresh(artifact)

    await create_activity_log(
        db,
        engagement_id=artifact.engagement_id,
        user_id=current_user.id,
        action="updated_cleanup_artifact",
        resource_type="cleanup_artifact",
        resource_id=artifact.id,
        resource_name=artifact.title,
        details=change_details,
        extra_context={
            "status": artifact.status.value.lower() if artifact.status else None,
        },
    )

    return artifact


@router.delete("/{artifact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cleanup_artifact(
    artifact_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a cleanup artifact."""
    result = await db.execute(select(CleanupArtifact).where(CleanupArtifact.id == artifact_id))
    artifact = result.scalar_one_or_none()
    if not artifact:
        raise HTTPException(status_code=404, detail="Cleanup artifact not found")

    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    is_owner = artifact.created_by == current_user.id

    if not is_admin:
        perm = Permission.CLEANUP_DELETE.value if is_owner else Permission.CLEANUP_DELETE_ANY.value
        has_permission = await check_engagement_permission(current_user.id, artifact.engagement_id, perm, db)
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. You need the '{perm}' permission.",
            )

    await create_activity_log(
        db,
        engagement_id=artifact.engagement_id,
        user_id=current_user.id,
        action="deleted_cleanup_artifact",
        resource_type="cleanup_artifact",
        resource_id=artifact.id,
        resource_name=artifact.title,
        details=f"Deleted cleanup artifact: {artifact.title}",
    )

    await db.delete(artifact)
    await db.commit()
    return None


# ============ Link / Unlink ============

@router.post("/{artifact_id}/findings/{finding_id}", status_code=status.HTTP_201_CREATED)
async def link_cleanup_to_finding(
    artifact_id: str,
    finding_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Link a cleanup artifact to a finding."""
    result = await db.execute(
        select(CleanupArtifact).options(selectinload(CleanupArtifact.findings)).where(CleanupArtifact.id == artifact_id)
    )
    artifact = result.scalar_one_or_none()
    if not artifact:
        raise HTTPException(status_code=404, detail="Cleanup artifact not found")
    await _require_artifact_edit(artifact, current_user, db)

    result = await db.execute(select(Finding).where(Finding.id == finding_id))
    finding = result.scalar_one_or_none()
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    if finding not in artifact.findings:
        artifact.findings.append(finding)
        await db.commit()

        await create_activity_log(
            db,
            engagement_id=artifact.engagement_id,
            user_id=current_user.id,
            action="linked_cleanup_artifact",
            resource_type="cleanup_artifact",
            resource_id=artifact.id,
            resource_name=artifact.title,
            details=f"Linked cleanup artifact '{artifact.title}' to finding '{finding.title}'",
        )

    return {"status": "linked"}


@router.delete("/{artifact_id}/findings/{finding_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_cleanup_from_finding(
    artifact_id: str,
    finding_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Unlink a cleanup artifact from a finding."""
    result = await db.execute(
        select(CleanupArtifact).options(selectinload(CleanupArtifact.findings)).where(CleanupArtifact.id == artifact_id)
    )
    artifact = result.scalar_one_or_none()
    if not artifact:
        raise HTTPException(status_code=404, detail="Cleanup artifact not found")
    await _require_artifact_edit(artifact, current_user, db)

    result = await db.execute(select(Finding).where(Finding.id == finding_id))
    finding = result.scalar_one_or_none()
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    if finding in artifact.findings:
        artifact.findings.remove(finding)
        await db.commit()

        await create_activity_log(
            db,
            engagement_id=artifact.engagement_id,
            user_id=current_user.id,
            action="unlinked_cleanup_artifact",
            resource_type="cleanup_artifact",
            resource_id=artifact.id,
            resource_name=artifact.title,
            details=f"Unlinked cleanup artifact '{artifact.title}' from finding '{finding.title}'",
        )

    return None


@router.post("/{artifact_id}/testcases/{testcase_id}", status_code=status.HTTP_201_CREATED)
async def link_cleanup_to_testcase(
    artifact_id: str,
    testcase_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Link a cleanup artifact to a test case."""
    result = await db.execute(
        select(CleanupArtifact).options(selectinload(CleanupArtifact.testcases)).where(CleanupArtifact.id == artifact_id)
    )
    artifact = result.scalar_one_or_none()
    if not artifact:
        raise HTTPException(status_code=404, detail="Cleanup artifact not found")
    await _require_artifact_edit(artifact, current_user, db)

    result = await db.execute(select(TestCase).where(TestCase.id == testcase_id))
    testcase = result.scalar_one_or_none()
    if not testcase:
        raise HTTPException(status_code=404, detail="Test case not found")

    if testcase not in artifact.testcases:
        artifact.testcases.append(testcase)
        await db.commit()

        await create_activity_log(
            db,
            engagement_id=artifact.engagement_id,
            user_id=current_user.id,
            action="linked_cleanup_artifact",
            resource_type="cleanup_artifact",
            resource_id=artifact.id,
            resource_name=artifact.title,
            details=f"Linked cleanup artifact '{artifact.title}' to test case '{testcase.title}'",
        )

    return {"status": "linked"}


@router.delete("/{artifact_id}/testcases/{testcase_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_cleanup_from_testcase(
    artifact_id: str,
    testcase_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Unlink a cleanup artifact from a test case."""
    result = await db.execute(
        select(CleanupArtifact).options(selectinload(CleanupArtifact.testcases)).where(CleanupArtifact.id == artifact_id)
    )
    artifact = result.scalar_one_or_none()
    if not artifact:
        raise HTTPException(status_code=404, detail="Cleanup artifact not found")
    await _require_artifact_edit(artifact, current_user, db)

    result = await db.execute(select(TestCase).where(TestCase.id == testcase_id))
    testcase = result.scalar_one_or_none()
    if not testcase:
        raise HTTPException(status_code=404, detail="Test case not found")

    if testcase in artifact.testcases:
        artifact.testcases.remove(testcase)
        await db.commit()

        await create_activity_log(
            db,
            engagement_id=artifact.engagement_id,
            user_id=current_user.id,
            action="unlinked_cleanup_artifact",
            resource_type="cleanup_artifact",
            resource_id=artifact.id,
            resource_name=artifact.title,
            details=f"Unlinked cleanup artifact '{artifact.title}' from test case '{testcase.title}'",
        )

    return None


@router.post("/{artifact_id}/assets/{asset_id}", status_code=status.HTTP_201_CREATED)
async def link_cleanup_to_asset(
    artifact_id: str,
    asset_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Link a cleanup artifact to an asset."""
    result = await db.execute(
        select(CleanupArtifact).options(selectinload(CleanupArtifact.assets)).where(CleanupArtifact.id == artifact_id)
    )
    artifact = result.scalar_one_or_none()
    if not artifact:
        raise HTTPException(status_code=404, detail="Cleanup artifact not found")
    await _require_artifact_edit(artifact, current_user, db)

    result = await db.execute(select(Asset).where(Asset.id == asset_id))
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    if asset not in artifact.assets:
        artifact.assets.append(asset)
        await db.commit()

        await create_activity_log(
            db,
            engagement_id=artifact.engagement_id,
            user_id=current_user.id,
            action="linked_cleanup_artifact",
            resource_type="cleanup_artifact",
            resource_id=artifact.id,
            resource_name=artifact.title,
            details=f"Linked cleanup artifact '{artifact.title}' to asset '{asset.name}'",
        )

    return {"status": "linked"}


@router.delete("/{artifact_id}/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_cleanup_from_asset(
    artifact_id: str,
    asset_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Unlink a cleanup artifact from an asset."""
    result = await db.execute(
        select(CleanupArtifact).options(selectinload(CleanupArtifact.assets)).where(CleanupArtifact.id == artifact_id)
    )
    artifact = result.scalar_one_or_none()
    if not artifact:
        raise HTTPException(status_code=404, detail="Cleanup artifact not found")
    await _require_artifact_edit(artifact, current_user, db)

    result = await db.execute(select(Asset).where(Asset.id == asset_id))
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    if asset in artifact.assets:
        artifact.assets.remove(asset)
        await db.commit()

        await create_activity_log(
            db,
            engagement_id=artifact.engagement_id,
            user_id=current_user.id,
            action="unlinked_cleanup_artifact",
            resource_type="cleanup_artifact",
            resource_id=artifact.id,
            resource_name=artifact.title,
            details=f"Unlinked cleanup artifact '{artifact.title}' from asset '{asset.name}'",
        )

    return None

