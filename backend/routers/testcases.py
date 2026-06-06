from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List, Optional
import logging
from database import get_db
from models.user import User
from models.testcase import TestCase
from schemas.testcase import TestCaseCreate, TestCaseUpdate, TestCaseResponse
from auth.dependencies import get_current_user
from auth.rbac import check_engagement_permission
from models.user import UserRole
from models.permission import Permission
import uuid
from utils.collaboration import create_activity_log, build_change_summary
from utils.versioning import create_version_snapshot
from models.discussion import ResourceType
from models.version_history import VersionHistory

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/testcases", tags=["testcases"])

@router.get("", response_model=List[TestCaseResponse])
async def get_testcases(
    engagement_id: Optional[str] = Query(None),
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all test cases, optionally filtered by engagement"""
    from models.discussion import Thread
    from sqlalchemy import func
    
    # Join with threads to count unresolved threads
    query = select(
        TestCase,
        User.username.label("creator_username"),
        User.profile_photo.label("creator_profile_photo"),
        func.count(Thread.id).filter(Thread.is_resolved == False).label("unresolved_count")
    ).outerjoin(
        Thread,
        (Thread.resource_type == "testcase") & (Thread.resource_id == TestCase.id)
    ).outerjoin(
        User,
        TestCase.created_by == User.id
    ).group_by(TestCase.id, User.username, User.profile_photo)
    
    if engagement_id:
        query = query.where(TestCase.engagement_id == engagement_id)
    
    # Restrict to assigned engagements for non-admins
    if current_user.role not in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]:
        from models.engagement import Engagement
        query = query.join(Engagement, TestCase.engagement_id == Engagement.id).where(
            Engagement.assigned_users.any(User.id == current_user.id)
        )
    
    query = query.offset(skip).limit(limit).order_by(TestCase.created_at.desc())
    
    result = await db.execute(query)
    rows = result.all()

    # Batch-load port_ids from TestCaseAsset join table for all test cases
    testcase_ids = [row[0].id for row in rows]
    port_ids_by_testcase: dict[str, dict[str, list[str]]] = {}  # {testcase_id: {asset_id: [port_ids]}}
    if testcase_ids:
        from models.associations import TestCaseAsset
        tca_result = await db.execute(
            select(TestCaseAsset).where(TestCaseAsset.testcase_id.in_(testcase_ids))
        )
        for tca in tca_result.scalars().all():
            pids = tca.parsed_port_ids
            if pids:
                port_ids_by_testcase.setdefault(tca.testcase_id, {})[tca.asset_id] = pids

    testcases_with_counts = []
    for testcase, creator_username, creator_profile_photo, unresolved_count in rows:
        testcase_dict = TestCaseResponse.model_validate(testcase).model_dump()
        testcase_dict["unresolved_thread_count"] = unresolved_count or 0
        testcase_dict["created_by_username"] = creator_username
        testcase_dict["created_by_profile_photo"] = creator_profile_photo
        testcase_dict["attack_technique_ids"] = [
            at.technique_id for at in (testcase.attack_techniques or [])
        ]
        # Inject port_ids into each asset
        asset_port_map = port_ids_by_testcase.get(testcase.id, {})
        for asset_dict in testcase_dict.get("assets", []):
            asset_dict["port_ids"] = asset_port_map.get(asset_dict["id"])
        testcases_with_counts.append(TestCaseResponse(**testcase_dict))

    return testcases_with_counts

@router.get("/{testcase_id}", response_model=TestCaseResponse)
async def get_testcase(
    testcase_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific test case by ID"""
    result = await db.execute(
        select(TestCase, User.username, User.profile_photo)
        .outerjoin(User, TestCase.created_by == User.id)
        .where(TestCase.id == testcase_id)
        .options(selectinload(TestCase.findings), selectinload(TestCase.tags))
    )
    row = result.first()
    
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test case not found"
        )
    
    testcase, creator_username, creator_profile_photo = row
    
    # Authorization Check using RBAC
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    
    if not is_admin:
        has_permission = await check_engagement_permission(current_user.id, testcase.engagement_id, Permission.TESTCASE_VIEW.value, db)
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. You need the 'testcase_view' permission to view test cases."
            )
    
    testcase_dict = TestCaseResponse.model_validate(testcase).model_dump()
    testcase_dict["created_by_username"] = creator_username
    testcase_dict["created_by_profile_photo"] = creator_profile_photo
    testcase_dict["attack_technique_ids"] = [
        at.technique_id for at in (testcase.attack_techniques or [])
    ]

    # Attach port_ids and resolved port details from the join table to each linked asset
    from models.associations import TestCaseAsset
    from models.asset_port import AssetPort
    tc_assets_result = await db.execute(
        select(TestCaseAsset).where(TestCaseAsset.testcase_id == testcase_id)
    )
    tc_assets = tc_assets_result.scalars().all()
    port_ids_map = {}
    all_port_ids = set()
    for tca in tc_assets:
        pids = tca.parsed_port_ids
        if pids:
            port_ids_map[tca.asset_id] = pids
            all_port_ids.update(pids)

    # Fetch actual port objects for resolution
    port_objects_map = {}
    if all_port_ids:
        ports_result = await db.execute(select(AssetPort).where(AssetPort.id.in_(list(all_port_ids))))
        for port in ports_result.scalars().all():
            port_objects_map[port.id] = {
                "id": port.id,
                "port_number": port.port_number,
                "protocol": port.protocol.value if hasattr(port.protocol, 'value') else str(port.protocol),
                "service_name": port.service_name,
                "state": port.state.value if hasattr(port.state, 'value') else str(port.state),
            }

    for asset_dict in testcase_dict.get("assets", []):
        pids = port_ids_map.get(asset_dict["id"])
        asset_dict["port_ids"] = pids
        if pids:
            asset_dict["linked_ports"] = [port_objects_map[pid] for pid in pids if pid in port_objects_map]

    return TestCaseResponse(**testcase_dict)

@router.post("", response_model=TestCaseResponse, status_code=status.HTTP_201_CREATED)
async def create_testcase(
    testcase_data: TestCaseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new test case"""
    # Check permissions using RBAC
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    
    if not is_admin:
        has_permission = await check_engagement_permission(current_user.id, testcase_data.engagement_id, Permission.TESTCASE_CREATE.value, db)
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. You need the 'testcase_create' permission to create test cases."
            )
    # Validate parent_id if provided
    if testcase_data.parent_id:
        parent_result = await db.execute(select(TestCase).where(TestCase.id == testcase_data.parent_id))
        parent_tc = parent_result.scalar_one_or_none()
        if not parent_tc:
            raise HTTPException(status_code=400, detail="Parent test case not found")
        if parent_tc.engagement_id != testcase_data.engagement_id:
            raise HTTPException(status_code=400, detail="Parent test case must be in the same engagement")

    # Extract tag_ids and attack_technique_ids before creating the model
    tag_ids = testcase_data.tag_ids
    attack_technique_ids = testcase_data.attack_technique_ids
    testcase_dict = testcase_data.model_dump(exclude={"tag_ids", "attack_technique_ids"})

    db_testcase = TestCase(
        id=str(uuid.uuid4()),
        created_by=current_user.id,
        **testcase_dict
    )

    # Add tags if provided
    if tag_ids:
        from models.finding import Tag
        tag_result = await db.execute(select(Tag).where(Tag.id.in_(tag_ids)))
        db_testcase.tags = tag_result.scalars().all()

    # Add ATT&CK techniques if provided
    if attack_technique_ids:
        from models.associations import TestCaseAttackTechnique
        db_testcase.attack_techniques = [
            TestCaseAttackTechnique(technique_id=tid) for tid in attack_technique_ids
        ]

    db.add(db_testcase)
    await db.commit()
    await db.refresh(db_testcase)

    # Reload with tags for automation context
    reload_result = await db.execute(
        select(TestCase).where(TestCase.id == db_testcase.id).options(selectinload(TestCase.tags))
    )
    db_testcase = reload_result.scalar_one()

    # Log activity (self-contained, never raises)
    await create_activity_log(
        db,
        engagement_id=testcase_data.engagement_id,
        user_id=current_user.id,
        action="created_testcase",
        resource_type="testcase",
        resource_id=db_testcase.id,
        resource_name=db_testcase.title,
        details=f"Created test case: {db_testcase.title}",
        extra_context={
            "tags": [t.name.lower() for t in (db_testcase.tags or [])],
        },
    )

    return db_testcase

@router.put("/{testcase_id}", response_model=TestCaseResponse)
async def update_testcase(
    testcase_id: str,
    testcase_update: TestCaseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update an existing test case"""
    result = await db.execute(
        select(TestCase).where(TestCase.id == testcase_id)
        .options(selectinload(TestCase.tags))
    )
    db_testcase = result.scalar_one_or_none()
    
    if not db_testcase:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test case not found"
        )
    
    # Check permissions using RBAC with ANY model
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    is_owner = db_testcase.created_by == current_user.id
    
    if not is_admin:
        if is_owner:
            # Owner needs base edit permission
            has_permission = await check_engagement_permission(current_user.id, db_testcase.engagement_id, Permission.TESTCASE_EDIT.value, db)
        else:
            # Non-owner needs edit_any permission
            has_permission = await check_engagement_permission(current_user.id, db_testcase.engagement_id, Permission.TESTCASE_EDIT_ANY.value, db)
        
        if not has_permission:
            required_perm = Permission.TESTCASE_EDIT.value if is_owner else Permission.TESTCASE_EDIT_ANY.value
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. You need the '{required_perm}' permission to modify this test case."
            )
    
    # Update fields
    update_data = testcase_update.model_dump(exclude_unset=True, exclude={"tag_ids", "attack_technique_ids"})

    # Capture change summary before applying updates
    change_details = build_change_summary(db_testcase, update_data, label=f"Updated test case '{db_testcase.title}'")
    if testcase_update.tag_ids is not None:
        change_details += ", tags updated"
    if testcase_update.attack_technique_ids is not None:
        change_details += ", ATT&CK techniques updated"

    # Snapshot current state before applying changes
    await create_version_snapshot(db, db_testcase, "testcase", update_data, current_user.id)

    for field, value in update_data.items():
        setattr(db_testcase, field, value)

    # Update tags if provided
    if testcase_update.tag_ids is not None:
        from models.finding import Tag
        tag_result = await db.execute(select(Tag).where(Tag.id.in_(testcase_update.tag_ids)))
        db_testcase.tags = tag_result.scalars().all()

    # Update ATT&CK techniques if provided
    if testcase_update.attack_technique_ids is not None:
        from models.associations import TestCaseAttackTechnique
        db_testcase.attack_techniques = [
            TestCaseAttackTechnique(technique_id=tid) for tid in testcase_update.attack_technique_ids
        ]
    
    db_testcase.updated_by = current_user.id
    
    # Validate parent_id if being updated
    if 'parent_id' in update_data:
        new_parent_id = update_data['parent_id']
        if new_parent_id is not None:
            if new_parent_id == testcase_id:
                raise HTTPException(status_code=400, detail="A test case cannot be its own parent")
            parent_result = await db.execute(select(TestCase).where(TestCase.id == new_parent_id))
            parent_tc = parent_result.scalar_one_or_none()
            if not parent_tc:
                raise HTTPException(status_code=400, detail="Parent test case not found")
            if parent_tc.engagement_id != db_testcase.engagement_id:
                raise HTTPException(status_code=400, detail="Parent test case must be in the same engagement")
    
    await db.commit()
    await db.refresh(db_testcase)
    
    # Log activity (self-contained, never raises)
    await create_activity_log(
        db,
        engagement_id=db_testcase.engagement_id,
        user_id=current_user.id,
        action="updated_testcase",
        resource_type="testcase",
        resource_id=db_testcase.id,
        resource_name=db_testcase.title,
        details=change_details,
        extra_context={
            "tags": [t.name.lower() for t in (db_testcase.tags or [])],
        },
    )

    return db_testcase


# ── Version History ────────────────────────────────────────────────────

@router.get("/{testcase_id}/versions")
async def get_testcase_versions(
    testcase_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all versions for a test case (most recent first)."""
    result = await db.execute(select(TestCase).where(TestCase.id == testcase_id))
    tc = result.scalar_one_or_none()
    if not tc:
        raise HTTPException(status_code=404, detail="Test case not found")

    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_permission = await check_engagement_permission(
            current_user.id, tc.engagement_id, Permission.TESTCASE_VIEW.value, db
        )
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. You need the 'testcase_view' permission to view test cases.",
            )

    versions = await db.execute(
        select(VersionHistory, User.username)
        .outerjoin(User, VersionHistory.changed_by == User.id)
        .where(VersionHistory.entity_type == "testcase")
        .where(VersionHistory.entity_id == testcase_id)
        .order_by(VersionHistory.version.desc())
    )
    rows = versions.all()
    return [
        {
            "id": v.id,
            "version": v.version,
            "changed_fields": v.changed_fields,
            "changed_by": v.changed_by,
            "changed_by_username": username,
            "created_at": v.created_at.isoformat(),
        }
        for v, username in rows
    ]


@router.get("/{testcase_id}/versions/{version_id}")
async def get_testcase_version(
    testcase_id: str,
    version_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the full snapshot of a specific test case version."""
    # Load the parent test case so we have an engagement_id to gate on.
    tc_result = await db.execute(select(TestCase).where(TestCase.id == testcase_id))
    tc = tc_result.scalar_one_or_none()
    if not tc:
        raise HTTPException(status_code=404, detail="Test case not found")

    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_permission = await check_engagement_permission(
            current_user.id, tc.engagement_id, Permission.TESTCASE_VIEW.value, db
        )
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. You need the 'testcase_view' permission to view test cases.",
            )

    result = await db.execute(
        select(VersionHistory, User.username)
        .outerjoin(User, VersionHistory.changed_by == User.id)
        .where(VersionHistory.id == version_id)
        .where(VersionHistory.entity_type == "testcase")
        .where(VersionHistory.entity_id == testcase_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Version not found")

    v, username = row
    return {
        "id": v.id,
        "version": v.version,
        "snapshot": v.snapshot,
        "changed_fields": v.changed_fields,
        "changed_by": v.changed_by,
        "changed_by_username": username,
        "created_at": v.created_at.isoformat(),
    }


@router.delete("/{testcase_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_testcase(
    testcase_id: str,
    cascade: bool = Query(False, description="If true, also delete all child test cases recursively"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a test case. If cascade=true, also deletes all descendant test cases."""
    result = await db.execute(select(TestCase).where(TestCase.id == testcase_id))
    db_testcase = result.scalar_one_or_none()
    
    if not db_testcase:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test case not found"
        )
    
    # Check permissions using RBAC with ANY model
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    is_owner = db_testcase.created_by == current_user.id
    
    if not is_admin:
        if is_owner:
            # Owner needs base delete permission
            has_permission = await check_engagement_permission(current_user.id, db_testcase.engagement_id, Permission.TESTCASE_DELETE.value, db)
        else:
            # Non-owner needs delete_any permission
            has_permission = await check_engagement_permission(current_user.id, db_testcase.engagement_id, Permission.TESTCASE_DELETE_ANY.value, db)
        
        if not has_permission:
            required_perm = Permission.TESTCASE_DELETE.value if is_owner else Permission.TESTCASE_DELETE_ANY.value
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. You need the '{required_perm}' permission to delete this test case."
            )
    
    # Cascade: collect all descendant IDs and delete them too
    cascade_count = 0
    if cascade:
        # GHSA-3mpw-xmrg-5rx5: the BFS below must enforce the same own-vs-_ANY
        # gate per descendant that the direct-delete path enforces. Hoist the
        # _ANY lookup once — it is a static property of the (user, engagement)
        # pair within this request.
        has_delete_any = False
        if not is_admin:
            has_delete_any = await check_engagement_permission(
                current_user.id, db_testcase.engagement_id,
                Permission.TESTCASE_DELETE_ANY.value, db,
            )

        # BFS to find all descendants
        descendants = []
        queue = [testcase_id]
        while queue:
            parent_id = queue.pop(0)
            children_result = await db.execute(
                select(TestCase).where(TestCase.parent_id == parent_id)
            )
            children = children_result.scalars().all()
            for child in children:
                if not is_admin and child.created_by != current_user.id and not has_delete_any:
                    logger.warning(
                        "Blocked cascade delete by user %s: descendant %s authored by %s",
                        current_user.id, child.id, child.created_by,
                    )
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Cascade delete includes test cases owned by other users; you need the 'testcase_delete_any' permission.",
                    )
                descendants.append(child)
                queue.append(child.id)
        # Delete descendants in reverse (leaves first)
        for desc in reversed(descendants):
            await db.delete(desc)
        cascade_count = len(descendants)

    # Log activity before deletion
    details = f"Deleted test case: {db_testcase.title}"
    if cascade_count > 0:
        details += f" (and {cascade_count} child test case{'s' if cascade_count != 1 else ''})"
    await create_activity_log(
        db,
        engagement_id=db_testcase.engagement_id,
        user_id=current_user.id,
        action="deleted_testcase",
        resource_type="testcase",
        resource_id=db_testcase.id,
        resource_name=db_testcase.title,
        details=details
    )

    await db.delete(db_testcase)
    await db.commit()
    
    return None

@router.post("/{testcase_id}/findings/{finding_id}", status_code=status.HTTP_200_OK)
async def link_finding_to_testcase(
    testcase_id: str,
    finding_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Link a finding to a test case"""
    from models.finding import Finding
    from models.associations import FindingTestCase
    
    # Verify test case exists
    tc_result = await db.execute(select(TestCase).where(TestCase.id == testcase_id))
    testcase = tc_result.scalar_one_or_none()
    if not testcase:
        raise HTTPException(status_code=404, detail="Test case not found")
    
    # Verify finding exists
    f_result = await db.execute(select(Finding).where(Finding.id == finding_id))
    finding = f_result.scalar_one_or_none()
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    if finding.engagement_id != testcase.engagement_id:
        raise HTTPException(status_code=400, detail="Finding belongs to a different engagement")

    # Check if link already exists
    existing = await db.execute(
        select(FindingTestCase).where(
            FindingTestCase.finding_id == finding_id,
            FindingTestCase.testcase_id == testcase_id
        )
    )
    if existing.scalar_one_or_none():
        return {"message": "Already linked"}

    link = FindingTestCase(finding_id=finding_id, testcase_id=testcase_id)
    db.add(link)
    await db.commit()
    
    # Log activity
    await create_activity_log(
        db,
        engagement_id=testcase.engagement_id,
        user_id=current_user.id,
        action="linked_finding",
        resource_type="testcase",
        resource_id=testcase.id,
        resource_name=testcase.title,
        details=f"Linked finding '{finding.title}' to test case '{testcase.title}'"
    )
    
    return {"message": "Finding linked to test case"}

@router.delete("/{testcase_id}/findings/{finding_id}", status_code=status.HTTP_200_OK)
async def unlink_finding_from_testcase(
    testcase_id: str,
    finding_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Unlink a finding from a test case"""
    from models.associations import FindingTestCase
    from models.finding import Finding
    
    # Fetch test case and finding for log context
    tc_result = await db.execute(select(TestCase).where(TestCase.id == testcase_id))
    testcase = tc_result.scalar_one_or_none()
    f_result = await db.execute(select(Finding).where(Finding.id == finding_id))
    finding = f_result.scalar_one_or_none()
    
    result = await db.execute(
        select(FindingTestCase).where(
            FindingTestCase.finding_id == finding_id,
            FindingTestCase.testcase_id == testcase_id
        )
    )
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    
    await db.delete(link)
    await db.commit()
    
    # Log activity
    if testcase and finding:
        await create_activity_log(
            db,
            engagement_id=testcase.engagement_id,
            user_id=current_user.id,
            action="unlinked_finding",
            resource_type="testcase",
            resource_id=testcase.id,
            resource_name=testcase.title,
            details=f"Unlinked finding '{finding.title}' from test case '{testcase.title}'"
        )
    
    return {"message": "Finding unlinked from test case"}

@router.post("/{testcase_id}/assets/{asset_id}", status_code=status.HTTP_200_OK)
async def link_asset_to_testcase(
    testcase_id: str,
    asset_id: str,
    port_ids: str = Query(None, description="JSON array of port IDs to associate"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Link an asset to a test case, optionally specifying ports"""
    from models.asset import Asset
    from models.associations import TestCaseAsset

    # Verify test case exists
    tc_result = await db.execute(select(TestCase).where(TestCase.id == testcase_id))
    testcase = tc_result.scalar_one_or_none()
    if not testcase:
        raise HTTPException(status_code=404, detail="Test case not found")

    # Verify asset exists
    a_result = await db.execute(select(Asset).where(Asset.id == asset_id))
    asset = a_result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    if asset.engagement_id != testcase.engagement_id:
        raise HTTPException(status_code=400, detail="Asset belongs to a different engagement")

    # Check if link already exists
    existing = await db.execute(
        select(TestCaseAsset).where(
            TestCaseAsset.testcase_id == testcase_id,
            TestCaseAsset.asset_id == asset_id
        )
    )
    existing_link = existing.scalar_one_or_none()
    if existing_link:
        # Update port_ids on existing link
        existing_link.port_ids = port_ids
        await db.commit()
        return {"message": "Asset link updated"}

    link = TestCaseAsset(testcase_id=testcase_id, asset_id=asset_id, port_ids=port_ids)
    db.add(link)
    await db.commit()

    # Log activity
    await create_activity_log(
        db,
        engagement_id=testcase.engagement_id,
        user_id=current_user.id,
        action="linked_asset",
        resource_type="testcase",
        resource_id=testcase.id,
        resource_name=testcase.title,
        details=f"Linked asset '{asset.name}' to test case '{testcase.title}'"
    )

    return {"message": "Asset linked to test case"}

@router.delete("/{testcase_id}/assets/{asset_id}", status_code=status.HTTP_200_OK)
async def unlink_asset_from_testcase(
    testcase_id: str,
    asset_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Unlink an asset from a test case"""
    from models.asset import Asset
    from models.associations import TestCaseAsset

    # Fetch test case and asset for log context
    tc_result = await db.execute(select(TestCase).where(TestCase.id == testcase_id))
    testcase = tc_result.scalar_one_or_none()
    a_result = await db.execute(select(Asset).where(Asset.id == asset_id))
    asset = a_result.scalar_one_or_none()

    result = await db.execute(
        select(TestCaseAsset).where(
            TestCaseAsset.testcase_id == testcase_id,
            TestCaseAsset.asset_id == asset_id
        )
    )
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")

    await db.delete(link)
    await db.commit()

    # Log activity
    if testcase and asset:
        await create_activity_log(
            db,
            engagement_id=testcase.engagement_id,
            user_id=current_user.id,
            action="unlinked_asset",
            resource_type="testcase",
            resource_id=testcase.id,
            resource_name=testcase.title,
            details=f"Unlinked asset '{asset.name}' from test case '{testcase.title}'"
        )

    return {"message": "Asset unlinked from test case"}

@router.post("/{testcase_id}/evidence")
async def upload_testcase_evidence(
    testcase_id: str,
    file: UploadFile = File(...),
    description: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Upload an evidence file for a test case."""
    from models.evidence import Evidence
    from schemas.evidence import EvidenceResponse
    from utils.storage import storage_service
    import os

    result = await db.execute(select(TestCase).where(TestCase.id == testcase_id))
    testcase = result.scalar_one_or_none()

    if not testcase:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test case not found"
        )

    # Check permissions
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    is_creator = testcase.created_by == current_user.id

    if not (is_admin or is_creator):
        has_permission = await check_engagement_permission(current_user.id, testcase.engagement_id, Permission.EVIDENCE_CREATE.value, db)
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. You need the 'evidence_create' permission to add evidence to this test case."
            )

    # Read file content
    content = await file.read()
    file_size = len(content)

    # Generate unique filename
    ext = os.path.splitext(file.filename)[1] if file.filename else ""
    storage_filename = f"{uuid.uuid4()}{ext}"

    # Upload to storage
    try:
        await storage_service.upload_file(
            content,
            storage_filename,
            content_type=file.content_type
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload file to storage: {str(e)}"
        )

    # Create evidence record
    new_evidence = Evidence(
        testcase_id=testcase_id,
        engagement_id=testcase.engagement_id,
        filename=storage_filename,
        original_filename=file.filename or "unknown",
        file_path=storage_filename,
        file_size=file_size,
        mime_type=file.content_type,
        description=description,
        created_by=current_user.id
    )

    db.add(new_evidence)
    await db.commit()
    await db.refresh(new_evidence)

    # Log activity
    await create_activity_log(
        db,
        engagement_id=testcase.engagement_id,
        user_id=current_user.id,
        action="uploaded_evidence",
        resource_type="testcase",
        resource_id=testcase.id,
        resource_name=testcase.title,
        details=f"Uploaded evidence '{file.filename}' to test case '{testcase.title}'"
    )

    new_evidence.created_by_username = current_user.username
    return new_evidence


# ── Cross-Link: TestCase ↔ VaultItem / CleanupArtifact ───────────────────────

async def _require_testcase(testcase_id: str, db: AsyncSession, current_user: User) -> TestCase:
    """Load a test case and verify the user has edit permission."""
    result = await db.execute(select(TestCase).where(TestCase.id == testcase_id))
    tc = result.scalar_one_or_none()
    if not tc:
        raise HTTPException(status_code=404, detail="Test case not found")
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_perm = await check_engagement_permission(
            current_user.id, tc.engagement_id, Permission.TESTCASE_EDIT.value, db
        )
        if not has_perm:
            raise HTTPException(status_code=403, detail="Insufficient permissions.")
    return tc


@router.post("/{testcase_id}/vault-items/{vault_item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def link_testcase_to_vault_item(testcase_id: str, vault_item_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Link a test case to a vault item."""
    from models.associations import VaultItemTestCase
    from models.vault import VaultItem
    tc = await _require_testcase(testcase_id, db, current_user)
    existing = await db.execute(select(VaultItemTestCase).where(VaultItemTestCase.testcase_id == testcase_id, VaultItemTestCase.vault_item_id == vault_item_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Already linked")
    item = (await db.execute(select(VaultItem).where(VaultItem.id == vault_item_id))).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Vault item not found")
    if item.engagement_id != tc.engagement_id:
        raise HTTPException(status_code=400, detail="Vault item belongs to a different engagement")
    db.add(VaultItemTestCase(vault_item_id=vault_item_id, testcase_id=testcase_id))
    await db.commit()


@router.delete("/{testcase_id}/vault-items/{vault_item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_testcase_from_vault_item(testcase_id: str, vault_item_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Remove the link between a test case and a vault item."""
    from models.associations import VaultItemTestCase
    await _require_testcase(testcase_id, db, current_user)
    result = await db.execute(select(VaultItemTestCase).where(VaultItemTestCase.testcase_id == testcase_id, VaultItemTestCase.vault_item_id == vault_item_id))
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    await db.delete(link)
    await db.commit()


@router.post("/{testcase_id}/cleanup-artifacts/{cleanup_artifact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def link_testcase_to_cleanup_artifact(testcase_id: str, cleanup_artifact_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Link a test case to a cleanup artifact."""
    from models.associations import CleanupArtifactTestCase
    from models.cleanup_artifact import CleanupArtifact as CA
    tc = await _require_testcase(testcase_id, db, current_user)
    existing = await db.execute(select(CleanupArtifactTestCase).where(CleanupArtifactTestCase.testcase_id == testcase_id, CleanupArtifactTestCase.cleanup_artifact_id == cleanup_artifact_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Already linked")
    ca = (await db.execute(select(CA).where(CA.id == cleanup_artifact_id))).scalar_one_or_none()
    if not ca:
        raise HTTPException(status_code=404, detail="Cleanup artifact not found")
    if ca.engagement_id != tc.engagement_id:
        raise HTTPException(status_code=400, detail="Cleanup artifact belongs to a different engagement")
    db.add(CleanupArtifactTestCase(cleanup_artifact_id=cleanup_artifact_id, testcase_id=testcase_id))
    await db.commit()


@router.delete("/{testcase_id}/cleanup-artifacts/{cleanup_artifact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_testcase_from_cleanup_artifact(testcase_id: str, cleanup_artifact_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Remove the link between a test case and a cleanup artifact."""
    from models.associations import CleanupArtifactTestCase
    await _require_testcase(testcase_id, db, current_user)
    result = await db.execute(select(CleanupArtifactTestCase).where(CleanupArtifactTestCase.testcase_id == testcase_id, CleanupArtifactTestCase.cleanup_artifact_id == cleanup_artifact_id))
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    await db.delete(link)
    await db.commit()
