from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy import func
from typing import List, Optional
from datetime import datetime, timezone
import uuid
import os
import json
import logging
from database import get_db

from models.user import User
from models.finding import Finding, Severity, FindingStatus, Tag
from models.evidence import Evidence
from schemas.finding import FindingCreate, FindingUpdate, FindingResponse, TagResponse
from schemas.evidence import EvidenceResponse
from auth.dependencies import get_current_user
from auth.rbac import can_modify_resource, check_engagement_permission
from models.user import UserRole
from models.permission import Permission
from utils.storage import storage_service
from utils.collaboration import create_activity_log, build_change_summary
from utils.versioning import create_version_snapshot
from models.discussion import ResourceType
from models.version_history import VersionHistory


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/findings", tags=["findings"])

@router.get("", response_model=List[FindingResponse])
async def get_findings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    engagement_id: Optional[str] = Query(None),
    severity: Optional[Severity] = Query(None),
    status: Optional[FindingStatus] = Query(None),
    skip: int = 0,
    limit: int = 100
):
    """Get findings with optional filters."""
    from models.discussion import Thread
    
    # Join with threads to count unresolved threads
    query = select(
        Finding,
        User.username.label("creator_username"),
        User.profile_photo.label("creator_profile_photo"),
        func.count(Thread.id).filter(Thread.is_resolved == False).label("unresolved_count")
    ).outerjoin(
        Thread,
        (Thread.resource_type == "finding") & (Thread.resource_id == Finding.id)
    ).outerjoin(
        User,
        Finding.created_by == User.id
    ).options(
        selectinload(Finding.evidence),
        selectinload(Finding.assets),
    ).group_by(Finding.id, User.username, User.profile_photo)

    if engagement_id:
        query = query.where(Finding.engagement_id == engagement_id)
    
    # Restrict to assigned engagements for non-admins
    if current_user.role not in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]:
        from models.engagement import Engagement
        query = query.join(Engagement, Finding.engagement_id == Engagement.id).where(
            Engagement.assigned_users.any(User.id == current_user.id)
        )
    
    query = query.offset(skip).limit(limit).order_by(Finding.created_at.desc())
    
    result = await db.execute(query)
    rows = result.all()

    # Batch-load port_ids from FindingAsset join table for all findings
    finding_ids = [row[0].id for row in rows]
    port_ids_by_finding: dict[str, dict[str, list[str]]] = {}  # {finding_id: {asset_id: [port_ids]}}
    if finding_ids:
        from models.associations import FindingAsset
        fa_result = await db.execute(
            select(FindingAsset).where(FindingAsset.finding_id.in_(finding_ids))
        )
        for fa in fa_result.scalars().all():
            entry = port_ids_by_finding.setdefault(fa.finding_id, {})
            asset_entry = entry.setdefault(fa.asset_id, {"port_ids": None, "remediated": False, "remediated_at": None, "remediated_by": None})
            asset_entry["remediated"] = fa.remediated or False
            asset_entry["remediated_at"] = fa.remediated_at.isoformat() if fa.remediated_at else None
            asset_entry["remediated_by"] = fa.remediated_by
            if fa.port_ids:
                asset_entry["port_ids"] = fa.parsed_port_ids

    findings_with_counts = []
    for finding, creator_username, creator_profile_photo, unresolved_count in rows:
        finding_dict = FindingResponse.model_validate(finding).model_dump()
        finding_dict["unresolved_thread_count"] = unresolved_count or 0
        finding_dict["created_by_username"] = creator_username
        finding_dict["created_by_profile_photo"] = creator_profile_photo
        # Inject ATT&CK technique IDs
        finding_dict["attack_technique_ids"] = [at.technique_id for at in (finding.attack_techniques or [])]
        # Inject port_ids and remediation data into each asset
        asset_data_map = port_ids_by_finding.get(finding.id, {})
        for asset_dict in finding_dict.get("assets", []):
            data = asset_data_map.get(asset_dict["id"], {})
            asset_dict["port_ids"] = data.get("port_ids")
            asset_dict["remediated"] = data.get("remediated", False)
            asset_dict["remediated_at"] = data.get("remediated_at")
            asset_dict["remediated_by"] = data.get("remediated_by")
        findings_with_counts.append(FindingResponse(**finding_dict))
    
    return findings_with_counts


# ── Remediation Summary ───────────────────────────────────────────────

@router.get("/remediation-summary")
async def get_remediation_summary(
    engagement_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get remediation summary for an engagement."""
    from models.engagement import Engagement
    from models.cleanup_artifact import CleanupArtifact
    import json

    # Fetch engagement
    eng_result = await db.execute(select(Engagement).where(Engagement.id == engagement_id))
    engagement = eng_result.scalar_one_or_none()
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")

    # Fetch findings for engagement with assets eager-loaded
    findings_result = await db.execute(
        select(Finding)
        .where(Finding.engagement_id == engagement_id)
        .options(selectinload(Finding.assets), selectinload(Finding.tags))
        .order_by(Finding.created_at.desc())
    )
    findings = findings_result.scalars().all()

    # Batch-load FindingAsset data for all findings
    finding_ids = [f.id for f in findings]
    fa_data: dict[str, list] = {}  # {finding_id: [{asset_id, remediated, ...}]}
    if finding_ids:
        fa_result = await db.execute(
            select(FindingAsset).where(FindingAsset.finding_id.in_(finding_ids))
        )
        for fa in fa_result.scalars().all():
            entry = {
                "asset_id": fa.asset_id,
                "remediated": fa.remediated or False,
                "remediated_at": fa.remediated_at.isoformat() if fa.remediated_at else None,
                "remediated_by": fa.remediated_by,
            }
            fa_data.setdefault(fa.finding_id, []).append(entry)

    # Load remediated_by usernames
    all_remediated_user_ids = set()
    for entries in fa_data.values():
        for e in entries:
            if e["remediated_by"]:
                all_remediated_user_ids.add(e["remediated_by"])
    username_map = {}
    if all_remediated_user_ids:
        user_result = await db.execute(
            select(User.id, User.username).where(User.id.in_(all_remediated_user_ids))
        )
        username_map = {uid: uname for uid, uname in user_result.all()}

    # Build per-finding data with remediation stats
    by_status = {}
    by_severity = {}
    total_assets_all = 0
    remediated_assets_all = 0
    findings_data = []

    # Batch-load unresolved thread counts for all findings
    from models.discussion import Thread
    unresolved_counts: dict[str, int] = {}
    if finding_ids:
        thread_result = await db.execute(
            select(Thread.resource_id, func.count(Thread.id))
            .where(
                Thread.resource_type == "finding_remediation",
                Thread.resource_id.in_(finding_ids),
                Thread.is_resolved == False,
            )
            .group_by(Thread.resource_id)
        )
        for rid, cnt in thread_result.all():
            unresolved_counts[rid] = cnt

    for f in findings:
        status_val = f.status.value if f.status else "OPEN"
        severity_val = f.severity.value if f.severity else "INFO"
        by_status[status_val] = by_status.get(status_val, 0) + 1
        by_severity[severity_val] = by_severity.get(severity_val, 0) + 1

        fa_entries = fa_data.get(f.id, [])
        total_assets = len(fa_entries)
        remediated_count = sum(1 for e in fa_entries if e["remediated"])
        total_assets_all += total_assets
        remediated_assets_all += remediated_count

        # Build asset details for this finding
        asset_map = {a.id: a for a in f.assets}
        asset_details = []
        for e in fa_entries:
            a = asset_map.get(e["asset_id"])
            asset_details.append({
                "id": e["asset_id"],
                "name": a.name if a else "Unknown",
                "identifier": a.identifier if a else "",
                "asset_type": a.asset_type if a else "",
                "remediated": e["remediated"],
                "remediated_at": e["remediated_at"],
                "remediated_by": e["remediated_by"],
                "remediated_by_username": username_map.get(e["remediated_by"]) if e["remediated_by"] else None,
            })

        findings_data.append({
            "id": f.id,
            "title": f.title,
            "severity": severity_val,
            "status": status_val,
            "cvss_score": f.cvss_score,
            "category": f.category,
            "created_at": f.created_at.isoformat(),
            "total_assets": total_assets,
            "remediated_assets": remediated_count,
            "remediation_pct": round((remediated_count / total_assets * 100), 1) if total_assets > 0 else 0,
            "assets": asset_details,
            "tags": [{"id": t.id, "name": t.name, "color": t.color} for t in (f.tags or [])],
            "unresolved_thread_count": unresolved_counts.get(f.id, 0),
        })

    # Fetch cleanup artifacts
    ca_result = await db.execute(
        select(CleanupArtifact)
        .where(CleanupArtifact.engagement_id == engagement_id)
        .options(selectinload(CleanupArtifact.assets))
        .order_by(CleanupArtifact.created_at.desc())
    )
    cleanup_artifacts = ca_result.scalars().all()

    return {
        "engagement": {"id": engagement.id, "name": engagement.name},
        "summary": {
            "total_findings": len(findings),
            "by_status": by_status,
            "by_severity": by_severity,
            "total_assets": total_assets_all,
            "remediated_assets": remediated_assets_all,
            "overall_remediation_pct": round((remediated_assets_all / total_assets_all * 100), 1) if total_assets_all > 0 else 0,
        },
        "findings": findings_data,
        "cleanup_artifacts": [
            {
                "id": ca.id,
                "title": ca.title,
                "artifact_type": ca.artifact_type,
                "status": ca.status.value if ca.status else "PENDING",
                "location": ca.location,
                "description": ca.description,
                "cleanup_notes": ca.cleanup_notes,
                "cleaned_at": ca.cleaned_at.isoformat() if ca.cleaned_at else None,
                "linked_assets": [
                    {"id": a.id, "name": a.name, "identifier": a.identifier, "asset_type": a.asset_type}
                    for a in (ca.assets or [])
                ],
            }
            for ca in cleanup_artifacts
        ],
    }

@router.get("/{finding_id}", response_model=FindingResponse)
async def get_finding(
    finding_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific finding by ID."""
    result = await db.execute(
        select(Finding, User.username, User.profile_photo)
        .outerjoin(User, Finding.created_by == User.id)
        .where(Finding.id == finding_id)
        .options(
            selectinload(Finding.evidence),
            selectinload(Finding.assets),
            selectinload(Finding.testcases)
        )
    )
    row = result.first()
    
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Finding not found"
        )
    
    finding, creator_username, creator_profile_photo = row

    
    if not finding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Finding not found"
        )
    
    # Authorization Check using RBAC
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    
    if not is_admin:
        has_permission = await check_engagement_permission(current_user.id, finding.engagement_id, Permission.FINDING_VIEW.value, db)
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. You need the 'finding_view' permission to view findings."
            )

    # Count unresolved discussion threads for this finding
    from models.discussion import Thread
    unresolved_count_result = await db.execute(
        select(func.count(Thread.id)).where(
            Thread.resource_type == "finding",
            Thread.resource_id == finding_id,
            Thread.is_resolved == False,
        )
    )
    unresolved_count = unresolved_count_result.scalar() or 0

    # Build response dict and inject port_ids from join table
    finding_dict = FindingResponse.model_validate(finding).model_dump()
    finding_dict["unresolved_thread_count"] = unresolved_count
    finding_dict["created_by_username"] = creator_username
    finding_dict["created_by_profile_photo"] = creator_profile_photo
    # Inject ATT&CK technique IDs
    finding_dict["attack_technique_ids"] = [at.technique_id for at in (finding.attack_techniques or [])]

    fa_result = await db.execute(
        select(FindingAsset).where(FindingAsset.finding_id == finding_id)
    )
    fa_rows = fa_result.scalars().all()
    asset_data_map = {}
    for fa in fa_rows:
        entry = {"port_ids": None, "remediated": fa.remediated or False, "remediated_at": fa.remediated_at.isoformat() if fa.remediated_at else None, "remediated_by": fa.remediated_by}
        if fa.port_ids:
            entry["port_ids"] = fa.parsed_port_ids
        asset_data_map[fa.asset_id] = entry
    for asset_dict in finding_dict.get("assets", []):
        data = asset_data_map.get(asset_dict["id"], {})
        asset_dict["port_ids"] = data.get("port_ids")
        asset_dict["remediated"] = data.get("remediated", False)
        asset_dict["remediated_at"] = data.get("remediated_at")
        asset_dict["remediated_by"] = data.get("remediated_by")

    return FindingResponse(**finding_dict)

from models.asset import Asset
from models.associations import FindingAsset

@router.post("", response_model=FindingResponse, status_code=status.HTTP_201_CREATED)
async def create_finding(
    finding_data: FindingCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new finding for an engagement. Optionally link assets, tags, and a test case during creation."""
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    
    if not is_admin:
        has_permission = await check_engagement_permission(current_user.id, finding_data.engagement_id, Permission.FINDING_CREATE.value, db)
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. You need the 'finding_create' permission to create findings."
            )

    # Extract asset_ids, tag_ids, testcase_id, and attack_technique_ids
    asset_ids = finding_data.asset_ids
    asset_port_ids = finding_data.asset_port_ids or {}
    tag_ids = finding_data.tag_ids
    testcase_id = finding_data.testcase_id
    attack_technique_ids = finding_data.attack_technique_ids
    finding_dict = finding_data.model_dump(exclude={"asset_ids", "asset_port_ids", "tag_ids", "testcase_id", "attack_technique_ids"})
    
    new_finding = Finding(
        **finding_dict,
        created_by=current_user.id
    )
    
    # Add assets if provided — only assets in the SAME engagement; foreign
    # ids are silently dropped from the .in_() filter.
    if asset_ids:
        asset_result = await db.execute(
            select(Asset).where(
                Asset.id.in_(asset_ids),
                Asset.engagement_id == new_finding.engagement_id,
            )
        )
        new_finding.assets = asset_result.scalars().all()

    # Add tags if provided (Tag has no engagement_id — intentionally global)
    if tag_ids:
        tag_result = await db.execute(select(Tag).where(Tag.id.in_(tag_ids)))
        new_finding.tags = tag_result.scalars().all()

    # Link to test case if provided — must be in the same engagement
    if testcase_id:
        from models.testcase import TestCase as TC
        tc_result = await db.execute(
            select(TC).where(
                TC.id == testcase_id,
                TC.engagement_id == new_finding.engagement_id,
            )
        )
        tc = tc_result.scalar_one_or_none()
        if tc:
            new_finding.testcases = [tc]

    # Add ATT&CK techniques if provided
    if attack_technique_ids:
        from models.associations import FindingAttackTechnique
        new_finding.attack_techniques = [
            FindingAttackTechnique(technique_id=tid) for tid in attack_technique_ids
        ]

    db.add(new_finding)
    await db.commit()
    await db.refresh(new_finding)

    # Update port_ids on join table rows if provided
    if asset_port_ids:
        for aid, pids in asset_port_ids.items():
            if pids:
                await db.execute(
                    FindingAsset.__table__.update()
                    .where(FindingAsset.finding_id == new_finding.id, FindingAsset.asset_id == aid)
                    .values(port_ids=json.dumps(pids))
                )
        await db.commit()

    
    # Reload with evidence, assets and tags so we can pass tags to automation
    result = await db.execute(
        select(Finding)
        .where(Finding.id == new_finding.id)
        .options(selectinload(Finding.evidence), selectinload(Finding.assets), selectinload(Finding.tags))
    )
    new_finding = result.scalar_one()

    # Log activity
    await create_activity_log(
        db,
        engagement_id=finding_data.engagement_id,
        user_id=current_user.id,
        action="created_finding",
        resource_type="finding",
        resource_id=new_finding.id,
        resource_name=new_finding.title,
        details=f"Created finding: {new_finding.title}",
        extra_context={
            "severity": new_finding.severity.value.lower() if new_finding.severity else None,
            "status": new_finding.status.value.lower() if new_finding.status else None,
            "cvss_score": float(new_finding.cvss_score) if new_finding.cvss_score is not None else None,
            "tags": [t.name.lower() for t in (new_finding.tags or [])],
        },
    )

    # Notify engagement team about the new finding
    from utils.collaboration import notify_engagement_users
    await notify_engagement_users(
        db=db,
        engagement_id=finding_data.engagement_id,
        event_type="finding_created",
        title=f"New finding: {new_finding.title}",
        message=f"{current_user.full_name or current_user.username} created a {new_finding.severity.value} finding",
        link=f"/engagements/{finding_data.engagement_id}/findings/{new_finding.id}",
        actor_id=current_user.id,
    )
    await db.commit()

    return new_finding

@router.put("/{finding_id}", response_model=FindingResponse)
async def update_finding(
    finding_id: str,
    finding_data: FindingUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a finding."""
    result = await db.execute(
        select(Finding)
        .where(Finding.id == finding_id)
        .options(selectinload(Finding.evidence), selectinload(Finding.assets), selectinload(Finding.testcases))
    )
    finding = result.scalar_one_or_none()
    
    if not finding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Finding not found"
        )
    
    # Check permissions using RBAC with ANY model
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    is_owner = finding.created_by == current_user.id
    
    if not is_admin:
        if is_owner:
            # Owner needs base edit permission
            has_permission = await check_engagement_permission(current_user.id, finding.engagement_id, Permission.FINDING_EDIT.value, db)
        else:
            # Non-owner needs edit_any permission
            has_permission = await check_engagement_permission(current_user.id, finding.engagement_id, Permission.FINDING_EDIT_ANY.value, db)
        
        if not has_permission:
            required_perm = Permission.FINDING_EDIT.value if is_owner else Permission.FINDING_EDIT_ANY.value
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. You need the '{required_perm}' permission to modify this finding."
            )
    
    # Update fields
    update_data = finding_data.model_dump(exclude_unset=True, exclude={"asset_ids", "asset_port_ids", "tag_ids", "attack_technique_ids"})

    # Two-person rule: a finding's author cannot self-attest the terminal-state
    # transitions that downstream reports + dashboards treat as reviewed work.
    # Admins and team-leads still can, matching the existing global bypass; a
    # future configurable layer (see todo "Configurable chain-of-custody admin
    # tab") will replace the role check with an engagement-scoped permission.
    if (
        "status" in update_data
        and is_owner
        and not is_admin
        and update_data["status"] in (FindingStatus.VERIFIED, FindingStatus.REMEDIATED, FindingStatus.CLOSED)
    ):
        logger.warning(
            "Blocked self-attestation on finding %s by author %s: status→%s",
            finding.id, current_user.id, update_data["status"],
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Finding authors cannot set their own finding to VERIFIED/REMEDIATED/CLOSED. A separate reviewer must approve the status change.",
        )

    # Capture old status before applying updates (for notification)
    old_status = finding.status.value if finding.status else None

    # Capture change summary before applying updates
    change_details = build_change_summary(finding, update_data, label=f"Updated finding '{finding.title}'")
    if finding_data.asset_ids is not None:
        change_details += ", linked assets updated"
    if finding_data.tag_ids is not None:
        change_details += ", tags updated"
    if finding_data.attack_technique_ids is not None:
        change_details += ", ATT&CK techniques updated"

    # Snapshot current state before applying changes
    await create_version_snapshot(db, finding, "finding", update_data, current_user.id)

    for field, value in update_data.items():
        setattr(finding, field, value)
    
    finding.updated_by = current_user.id
    
    # Update assets if provided — only assets in the SAME engagement; foreign
    # ids are silently dropped from the .in_() filter.
    if finding_data.asset_ids is not None:
        asset_result = await db.execute(
            select(Asset).where(
                Asset.id.in_(finding_data.asset_ids),
                Asset.engagement_id == finding.engagement_id,
            )
        )
        finding.assets = asset_result.scalars().all()

    # Update tags if provided
    if finding_data.tag_ids is not None:
        tag_result = await db.execute(select(Tag).where(Tag.id.in_(finding_data.tag_ids)))
        finding.tags = tag_result.scalars().all()

    # Update ATT&CK techniques if provided
    if finding_data.attack_technique_ids is not None:
        from models.associations import FindingAttackTechnique
        # Replace entire set — delete old, add new
        finding.attack_techniques = [
            FindingAttackTechnique(technique_id=tid) for tid in finding_data.attack_technique_ids
        ]

    await db.commit()
    await db.refresh(finding)

    # Update port_ids on join table rows if provided
    if finding_data.asset_port_ids:
        for aid, pids in finding_data.asset_port_ids.items():
            await db.execute(
                FindingAsset.__table__.update()
                .where(FindingAsset.finding_id == finding.id, FindingAsset.asset_id == aid)
                .values(port_ids=json.dumps(pids) if pids else None)
            )
        await db.commit()
    
    # Reload with tags for automation context
    tags_result = await db.execute(
        select(Finding).where(Finding.id == finding.id).options(selectinload(Finding.tags))
    )
    finding_with_tags = tags_result.scalar_one()

    # Log activity
    await create_activity_log(
        db,
        engagement_id=finding.engagement_id,
        user_id=current_user.id,
        action="updated_finding",
        resource_type="finding",
        resource_id=finding.id,
        resource_name=finding.title,
        details=change_details,
        extra_context={
            "severity": finding.severity.value.lower() if finding.severity else None,
            "status": finding.status.value.lower() if finding.status else None,
            "cvss_score": float(finding.cvss_score) if finding.cvss_score is not None else None,
            "tags": [t.name.lower() for t in (finding_with_tags.tags or [])],
        },
    )

    # Notify finding creator if status changed
    new_status = finding.status.value if finding.status else None
    if "status" in update_data and old_status != new_status:
        from utils.collaboration import create_notification
        if finding.created_by and finding.created_by != current_user.id:
            await create_notification(
                db=db,
                user_id=finding.created_by,
                event_type="finding_status_changed",
                title=f"Finding status updated: {finding.title}",
                message=f"{current_user.full_name or current_user.username} changed status from {old_status} to {new_status}",
                link=f"/findings/{finding.id}?engagementId={finding.engagement_id}",
                actor_id=current_user.id,
                engagement_id=finding.engagement_id,
            )
            await db.commit()

    return finding


# ── Per-Asset Remediation ─────────────────────────────────────────────

@router.patch("/{finding_id}/assets/{asset_id}/remediate")
async def toggle_asset_remediation(
    finding_id: str,
    asset_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Toggle remediation status for a specific asset on a finding."""
    from datetime import datetime
    result = await db.execute(
        select(FindingAsset).where(
            FindingAsset.finding_id == finding_id,
            FindingAsset.asset_id == asset_id
        )
    )
    fa = result.scalar_one_or_none()
    if not fa:
        raise HTTPException(status_code=404, detail="Finding-asset link not found")

    # Toggle
    new_val = not (fa.remediated or False)
    fa.remediated = new_val
    fa.remediated_at = datetime.utcnow() if new_val else None
    fa.remediated_by = current_user.id if new_val else None

    await db.commit()

    # Build the response before any fire-and-forget work
    response = {
        "finding_id": finding_id,
        "asset_id": asset_id,
        "remediated": fa.remediated,
        "remediated_at": fa.remediated_at.isoformat() if fa.remediated_at else None,
        "remediated_by": fa.remediated_by,
    }

    # Log activity (non-fatal, will not crash the request)
    finding = await db.execute(select(Finding).where(Finding.id == finding_id))
    finding_obj = finding.scalar_one_or_none()
    if finding_obj:
        from models.asset import Asset as AssetModel
        asset_result = await db.execute(select(AssetModel).where(AssetModel.id == asset_id))
        asset_obj = asset_result.scalar_one_or_none()
        asset_name = asset_obj.name if asset_obj else asset_id
        action_verb = "remediated" if new_val else "un-remediated"
        await create_activity_log(
            db,
            engagement_id=finding_obj.engagement_id,
            user_id=current_user.id,
            action=f"asset_{action_verb}",
            resource_type="finding",
            resource_id=finding_id,
            resource_name=finding_obj.title,
            details=f"Marked asset '{asset_name}' as {action_verb} for finding '{finding_obj.title}'",
        )

    return response



# ── Version History ────────────────────────────────────────────────────

@router.get("/{finding_id}/versions")
async def get_finding_versions(
    finding_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all versions for a finding (most recent first)."""
    # Verify finding exists
    result = await db.execute(select(Finding).where(Finding.id == finding_id))
    finding = result.scalar_one_or_none()
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_permission = await check_engagement_permission(
            current_user.id, finding.engagement_id, Permission.FINDING_VIEW.value, db
        )
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. You need the 'finding_view' permission to view findings.",
            )

    versions = await db.execute(
        select(VersionHistory, User.username)
        .outerjoin(User, VersionHistory.changed_by == User.id)
        .where(VersionHistory.entity_type == "finding")
        .where(VersionHistory.entity_id == finding_id)
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


@router.get("/{finding_id}/versions/{version_id}")
async def get_finding_version(
    finding_id: str,
    version_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the full snapshot of a specific version."""
    # Load the parent finding so we have an engagement_id to gate on.
    finding_result = await db.execute(select(Finding).where(Finding.id == finding_id))
    finding = finding_result.scalar_one_or_none()
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_permission = await check_engagement_permission(
            current_user.id, finding.engagement_id, Permission.FINDING_VIEW.value, db
        )
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. You need the 'finding_view' permission to view findings.",
            )

    result = await db.execute(
        select(VersionHistory, User.username)
        .outerjoin(User, VersionHistory.changed_by == User.id)
        .where(VersionHistory.id == version_id)
        .where(VersionHistory.entity_type == "finding")
        .where(VersionHistory.entity_id == finding_id)
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


@router.delete("/{finding_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_finding(
    finding_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a finding."""
    result = await db.execute(select(Finding).where(Finding.id == finding_id))
    finding = result.scalar_one_or_none()
    
    if not finding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Finding not found"
        )
    
    # Check permissions using RBAC with ANY model
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    is_owner = finding.created_by == current_user.id
   
    if not is_admin:
        if is_owner:
            # Owner needs base delete permission
            has_permission = await check_engagement_permission(current_user.id, finding.engagement_id, Permission.FINDING_DELETE.value, db)
        else:
            # Non-owner needs delete_any permission
            has_permission = await check_engagement_permission(current_user.id, finding.engagement_id, Permission.FINDING_DELETE_ANY.value, db)
        
        if not has_permission:
            required_perm = Permission.FINDING_DELETE.value if is_owner else Permission.FINDING_DELETE_ANY.value
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. You need the '{required_perm}' permission to delete this finding."
            )
    
    # Log activity before deletion
    await create_activity_log(
        db,
        engagement_id=finding.engagement_id,
        user_id=current_user.id,
        action="deleted_finding",
        resource_type="finding",
        resource_id=finding.id,
        resource_name=finding.title,
        details=f"Deleted finding: {finding.title}"
    )

    await db.delete(finding)
    await db.commit()
    
    return None

@router.post("/{finding_id}/evidence", response_model=EvidenceResponse)
async def upload_evidence(
    finding_id: str,
    file: UploadFile = File(...),
    description: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Upload an evidence file for a finding."""
    # Check if finding exists
    result = await db.execute(select(Finding).where(Finding.id == finding_id))
    finding = result.scalar_one_or_none()
    
    if not finding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Finding not found"
        )
    
    # Check permissions
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    is_creator = finding.created_by == current_user.id
    
    if not (is_admin or is_creator):
        has_permission = await check_engagement_permission(current_user.id, finding.engagement_id, Permission.EVIDENCE_CREATE.value, db)
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. You need the 'evidence_create' permission to add evidence to this finding."
            )
    
    # Read file content
    content = await file.read()
    file_size = len(content)
    
    # Generate unique filename for storage
    ext = os.path.splitext(file.filename)[1] if file.filename else ""
    storage_filename = f"{uuid.uuid4()}{ext}"
    
    # Upload to MinIO
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
    
    # Create evidence record in database
    new_evidence = Evidence(
        finding_id=finding_id,
        engagement_id=finding.engagement_id,
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
        engagement_id=finding.engagement_id,
        user_id=current_user.id,
        action="uploaded",
        resource_type="evidence",
        resource_id=new_evidence.id,
        resource_name=new_evidence.original_filename,
        details=f"Uploaded evidence for finding: {finding.title}"
    )

    return new_evidence

@router.get("/{finding_id}/evidence/{evidence_id}/url")
async def get_evidence_url(
    finding_id: str,
    evidence_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate a presigned URL for an evidence file."""
    # Authorization Check
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        # Resolve engagement_id via finding
        eng_res = await db.execute(select(Finding.engagement_id).where(Finding.id == finding_id))
        eng_id = eng_res.scalar_one_or_none()
        
        if not eng_id:
             raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Associated engagement not found"
            )
            
        has_permission = await check_engagement_permission(current_user.id, eng_id, Permission.EVIDENCE_VIEW.value, db)
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. You need the 'evidence_view' permission to access this file."
            )

    result = await db.execute(
        select(Evidence)
        .where(Evidence.id == evidence_id, Evidence.finding_id == finding_id)
    )
    evidence = result.scalar_one_or_none()
    
    if not evidence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence not found"
        )
    
    url = storage_service.get_presigned_url(evidence.filename)
    return {"url": url}


@router.get("/tags/list", response_model=List[TagResponse])
async def get_tags(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all available tags."""
    result = await db.execute(select(Tag).order_by(Tag.name))
    return result.scalars().all()


# ── Cross-Link Endpoints ────────────────────────────────────────────────────

async def _require_finding(finding_id: str, db: AsyncSession, current_user: User) -> "Finding":
    """Load a finding and verify the user has edit permission."""
    result = await db.execute(select(Finding).where(Finding.id == finding_id))
    finding = result.scalar_one_or_none()
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_perm = await check_engagement_permission(
            current_user.id, finding.engagement_id, Permission.FINDING_EDIT.value, db
        )
        if not has_perm:
            raise HTTPException(status_code=403, detail="Insufficient permissions.")
    return finding


# ── Finding ↔ TestCase ──

@router.post("/{finding_id}/testcases/{testcase_id}", status_code=status.HTTP_204_NO_CONTENT)
async def link_finding_to_testcase(finding_id: str, testcase_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Link a finding to a test case."""
    from models.associations import FindingTestCase
    from models.testcase import TestCase as TC
    finding = await _require_finding(finding_id, db, current_user)
    existing = await db.execute(select(FindingTestCase).where(FindingTestCase.finding_id == finding_id, FindingTestCase.testcase_id == testcase_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Already linked")
    tc = (await db.execute(select(TC).where(TC.id == testcase_id))).scalar_one_or_none()
    if not tc:
        raise HTTPException(status_code=404, detail="Test case not found")
    if tc.engagement_id != finding.engagement_id:
        raise HTTPException(status_code=400, detail="Test case belongs to a different engagement")
    db.add(FindingTestCase(finding_id=finding_id, testcase_id=testcase_id))
    await db.commit()


@router.delete("/{finding_id}/testcases/{testcase_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_finding_from_testcase(finding_id: str, testcase_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Remove the link between a finding and a test case."""
    from models.associations import FindingTestCase
    await _require_finding(finding_id, db, current_user)
    result = await db.execute(select(FindingTestCase).where(FindingTestCase.finding_id == finding_id, FindingTestCase.testcase_id == testcase_id))
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    await db.delete(link)
    await db.commit()


# ── Finding ↔ VaultItem ──

@router.post("/{finding_id}/vault-items/{vault_item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def link_finding_to_vault_item(finding_id: str, vault_item_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Link a finding to a vault item."""
    from models.associations import VaultItemFinding
    from models.vault import VaultItem
    finding = await _require_finding(finding_id, db, current_user)
    existing = await db.execute(select(VaultItemFinding).where(VaultItemFinding.finding_id == finding_id, VaultItemFinding.vault_item_id == vault_item_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Already linked")
    item = (await db.execute(select(VaultItem).where(VaultItem.id == vault_item_id))).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Vault item not found")
    if item.engagement_id != finding.engagement_id:
        raise HTTPException(status_code=400, detail="Vault item belongs to a different engagement")
    db.add(VaultItemFinding(vault_item_id=vault_item_id, finding_id=finding_id))
    await db.commit()


@router.delete("/{finding_id}/vault-items/{vault_item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_finding_from_vault_item(finding_id: str, vault_item_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Remove the link between a finding and a vault item."""
    from models.associations import VaultItemFinding
    await _require_finding(finding_id, db, current_user)
    result = await db.execute(select(VaultItemFinding).where(VaultItemFinding.finding_id == finding_id, VaultItemFinding.vault_item_id == vault_item_id))
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    await db.delete(link)
    await db.commit()


# ── Finding ↔ CleanupArtifact ──

@router.post("/{finding_id}/cleanup-artifacts/{cleanup_artifact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def link_finding_to_cleanup_artifact(finding_id: str, cleanup_artifact_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Link a finding to a cleanup artifact."""
    from models.associations import CleanupArtifactFinding
    from models.cleanup_artifact import CleanupArtifact as CA
    finding = await _require_finding(finding_id, db, current_user)
    existing = await db.execute(select(CleanupArtifactFinding).where(CleanupArtifactFinding.finding_id == finding_id, CleanupArtifactFinding.cleanup_artifact_id == cleanup_artifact_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Already linked")
    ca = (await db.execute(select(CA).where(CA.id == cleanup_artifact_id))).scalar_one_or_none()
    if not ca:
        raise HTTPException(status_code=404, detail="Cleanup artifact not found")
    if ca.engagement_id != finding.engagement_id:
        raise HTTPException(status_code=400, detail="Cleanup artifact belongs to a different engagement")
    db.add(CleanupArtifactFinding(cleanup_artifact_id=cleanup_artifact_id, finding_id=finding_id))
    await db.commit()


@router.delete("/{finding_id}/cleanup-artifacts/{cleanup_artifact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_finding_from_cleanup_artifact(finding_id: str, cleanup_artifact_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Remove the link between a finding and a cleanup artifact."""
    from models.associations import CleanupArtifactFinding
    await _require_finding(finding_id, db, current_user)
    result = await db.execute(select(CleanupArtifactFinding).where(CleanupArtifactFinding.finding_id == finding_id, CleanupArtifactFinding.cleanup_artifact_id == cleanup_artifact_id))
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    await db.delete(link)
    await db.commit()

