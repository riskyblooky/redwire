from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete as sa_delete
import json
from datetime import datetime
from database import get_db
from models.user import User
from models.engagement import Engagement
from models.finding import Finding
from models.asset import Asset
from models.testcase import TestCase
from models.cleanup_artifact import CleanupArtifact
from models.associations import (
    FindingAsset, FindingTestCase, TestCaseAsset,
    CleanupArtifactFinding, CleanupArtifactTestCase, CleanupArtifactAsset,
    InfraItemFinding, InfraItemTestCase,
)
from models.attack_graph_layout import AttackGraphLayout
from models.attacker_node import AttackerNode, AttackerNodeEdge
from models.infra_item import InfraItem
from auth.dependencies import get_current_user
from auth.rbac import check_engagement_permission
from models.user import UserRole
from utils.collaboration import manager

router = APIRouter(prefix="/engagements", tags=["attack-graph"])


@router.get("/{engagement_id}/attack-graph")
async def get_attack_graph(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Build attack graph nodes and edges from engagement data and associations."""

    # Permission check
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_permission = await check_engagement_permission(
            current_user.id, engagement_id, "engagement_view", db
        )
        if not has_permission:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Verify engagement exists
    eng = await db.execute(select(Engagement).where(Engagement.id == engagement_id))
    if not eng.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Engagement not found")

    nodes = []
    edges = []

    # ── Assets ──
    result = await db.execute(
        select(Asset.id, Asset.name, Asset.identifier, Asset.asset_type, Asset.in_scope, Asset.is_pwned)
        .where(Asset.engagement_id == engagement_id)
    )
    for row in result.all():
        nodes.append({
            "id": f"asset-{row.id}",
            "type": "asset",
            "data": {
                "label": row.name,
                "subtitle": row.identifier,
                "assetType": row.asset_type,
                "inScope": row.in_scope,
                "isPwned": row.is_pwned,
                "entityId": row.id,
            },
        })

    # ── Test Cases ──
    result = await db.execute(
        select(TestCase.id, TestCase.title, TestCase.category, TestCase.is_executed, TestCase.is_successful)
        .where(TestCase.engagement_id == engagement_id)
    )
    for row in result.all():
        tc_status = "Not Executed"
        if row.is_executed:
            tc_status = "Pass" if row.is_successful else "Fail"
        nodes.append({
            "id": f"testcase-{row.id}",
            "type": "testcase",
            "data": {
                "label": row.title,
                "subtitle": row.category,
                "status": tc_status,
                "entityId": row.id,
            },
        })

    # ── Findings ──
    result = await db.execute(
        select(Finding.id, Finding.title, Finding.category, Finding.severity, Finding.status)
        .where(Finding.engagement_id == engagement_id)
    )
    for row in result.all():
        nodes.append({
            "id": f"finding-{row.id}",
            "type": "finding",
            "data": {
                "label": row.title,
                "subtitle": row.category or "Uncategorized",
                "severity": row.severity.value if row.severity else "info",
                "status": row.status.value if row.status else "open",
                "entityId": row.id,
            },
        })

    # ── Cleanup Items ──
    result = await db.execute(
        select(CleanupArtifact.id, CleanupArtifact.title, CleanupArtifact.artifact_type, CleanupArtifact.status)
        .where(CleanupArtifact.engagement_id == engagement_id)
    )
    for row in result.all():
        nodes.append({
            "id": f"cleanup-{row.id}",
            "type": "cleanup",
            "data": {
                "label": row.title,
                "subtitle": row.artifact_type or "",
                "status": row.status.value if row.status else "pending",
                "entityId": row.id,
            },
        })

    # ── Edges from association tables ──
    # Finding ↔ Asset
    result = await db.execute(
        select(FindingAsset.finding_id, FindingAsset.asset_id)
        .join(Finding, FindingAsset.finding_id == Finding.id)
        .where(Finding.engagement_id == engagement_id)
    )
    for row in result.all():
        edges.append({
            "id": f"e-finding-{row.finding_id}-asset-{row.asset_id}",
            "source": f"asset-{row.asset_id}",
            "target": f"finding-{row.finding_id}",
            "label": "affected",
        })

    # Finding ↔ Test Case
    result = await db.execute(
        select(FindingTestCase.finding_id, FindingTestCase.testcase_id)
        .join(Finding, FindingTestCase.finding_id == Finding.id)
        .where(Finding.engagement_id == engagement_id)
    )
    for row in result.all():
        edges.append({
            "id": f"e-finding-{row.finding_id}-tc-{row.testcase_id}",
            "source": f"testcase-{row.testcase_id}",
            "target": f"finding-{row.finding_id}",
            "label": "discovered",
        })

    # Test Case ↔ Asset
    result = await db.execute(
        select(TestCaseAsset.testcase_id, TestCaseAsset.asset_id)
        .join(TestCase, TestCaseAsset.testcase_id == TestCase.id)
        .where(TestCase.engagement_id == engagement_id)
    )
    for row in result.all():
        edges.append({
            "id": f"e-tc-{row.testcase_id}-asset-{row.asset_id}",
            "source": f"testcase-{row.testcase_id}",
            "target": f"asset-{row.asset_id}",
            "label": "targets",
        })

    # Cleanup ↔ Finding
    result = await db.execute(
        select(CleanupArtifactFinding.cleanup_artifact_id, CleanupArtifactFinding.finding_id)
        .join(CleanupArtifact, CleanupArtifactFinding.cleanup_artifact_id == CleanupArtifact.id)
        .where(CleanupArtifact.engagement_id == engagement_id)
    )
    for row in result.all():
        edges.append({
            "id": f"e-cleanup-{row.cleanup_artifact_id}-finding-{row.finding_id}",
            "source": f"finding-{row.finding_id}",
            "target": f"cleanup-{row.cleanup_artifact_id}",
            "label": "cleanup",
        })

    # Cleanup ↔ Test Case
    result = await db.execute(
        select(CleanupArtifactTestCase.cleanup_artifact_id, CleanupArtifactTestCase.testcase_id)
        .join(CleanupArtifact, CleanupArtifactTestCase.cleanup_artifact_id == CleanupArtifact.id)
        .where(CleanupArtifact.engagement_id == engagement_id)
    )
    for row in result.all():
        edges.append({
            "id": f"e-cleanup-{row.cleanup_artifact_id}-tc-{row.testcase_id}",
            "source": f"testcase-{row.testcase_id}",
            "target": f"cleanup-{row.cleanup_artifact_id}",
            "label": "cleanup",
        })

    # Cleanup ↔ Asset
    result = await db.execute(
        select(CleanupArtifactAsset.cleanup_artifact_id, CleanupArtifactAsset.asset_id)
        .join(CleanupArtifact, CleanupArtifactAsset.cleanup_artifact_id == CleanupArtifact.id)
        .where(CleanupArtifact.engagement_id == engagement_id)
    )
    for row in result.all():
        edges.append({
            "id": f"e-cleanup-{row.cleanup_artifact_id}-asset-{row.asset_id}",
            "source": f"asset-{row.asset_id}",
            "target": f"cleanup-{row.cleanup_artifact_id}",
            "label": "cleanup",
        })

    # ── Infra Items (auto-surfaced by link) ──
    # InfraItem is not engagement-scoped (it's a shared pool of attacker
    # infrastructure — C2s, redirectors, jumpboxes — typically reused
    # across engagements). To keep the graph engagement-scoped we surface
    # only the infra items that are linked to a finding or testcase
    # belonging to this engagement. New items appear automatically the
    # first time a tester links them to an in-engagement record.
    infra_finding_rows = (await db.execute(
        select(InfraItemFinding.infra_item_id, InfraItemFinding.finding_id)
        .join(Finding, InfraItemFinding.finding_id == Finding.id)
        .where(Finding.engagement_id == engagement_id)
    )).all()
    infra_testcase_rows = (await db.execute(
        select(InfraItemTestCase.infra_item_id, InfraItemTestCase.testcase_id)
        .join(TestCase, InfraItemTestCase.testcase_id == TestCase.id)
        .where(TestCase.engagement_id == engagement_id)
    )).all()

    in_play_infra_ids = {row.infra_item_id for row in infra_finding_rows} | {
        row.infra_item_id for row in infra_testcase_rows
    }
    if in_play_infra_ids:
        result = await db.execute(
            select(
                InfraItem.id, InfraItem.name, InfraItem.infra_type,
                InfraItem.status, InfraItem.hostname, InfraItem.ip_address,
            ).where(InfraItem.id.in_(in_play_infra_ids))
        )
        for row in result.all():
            nodes.append({
                "id": f"infra-{row.id}",
                "type": "infra",
                "data": {
                    "label": row.name,
                    "subtitle": row.hostname or row.ip_address or row.infra_type,
                    "infraType": row.infra_type,
                    "status": row.status,
                    "entityId": row.id,
                },
            })

        for row in infra_finding_rows:
            edges.append({
                "id": f"e-infra-{row.infra_item_id}-finding-{row.finding_id}",
                "source": f"infra-{row.infra_item_id}",
                "target": f"finding-{row.finding_id}",
                "label": "enabled",
            })
        for row in infra_testcase_rows:
            edges.append({
                "id": f"e-infra-{row.infra_item_id}-tc-{row.testcase_id}",
                "source": f"infra-{row.infra_item_id}",
                "target": f"testcase-{row.testcase_id}",
                "label": "enabled",
            })

    # ── Attacker Nodes ──
    result = await db.execute(
        select(AttackerNode).where(AttackerNode.engagement_id == engagement_id)
    )
    attacker_nodes = result.scalars().all()
    for an in attacker_nodes:
        nodes.append({
            "id": f"attacker-{an.id}",
            "type": "attacker",
            "data": {
                "label": an.name,
                "subtitle": an.point_of_presence,
                "description": an.description or "",
                "entityId": an.id,
            },
        })

    # Attacker Edges
    for an in attacker_nodes:
        result = await db.execute(
            select(AttackerNodeEdge).where(AttackerNodeEdge.attacker_node_id == an.id)
        )
        for edge_row in result.scalars().all():
            edges.append({
                "id": edge_row.id,
                "source": f"attacker-{an.id}",
                "target": edge_row.target_node_id,
                "label": "attacks",
            })

    # ── Check for active pinned layout ──
    layout_row = await db.execute(
        select(AttackGraphLayout)
        .where(AttackGraphLayout.engagement_id == engagement_id, AttackGraphLayout.is_active == True)
        .order_by(AttackGraphLayout.pinned_at.desc())
        .limit(1)
    )
    saved_layout = layout_row.scalar_one_or_none()
    pinned_positions = None
    pinned_by = None
    pinned_at = None
    if saved_layout:
        pinned_positions = json.loads(saved_layout.positions)
        pinned_by = saved_layout.pinned_by
        pinned_at = saved_layout.pinned_at.isoformat() if saved_layout.pinned_at else None

    return {
        "nodes": nodes,
        "edges": edges,
        "pinned_positions": pinned_positions,
        "pinned_by": pinned_by,
        "pinned_at": pinned_at,
    }


# ═══════════════════════════════════════════════════════════
# Named Layouts CRUD
# ═══════════════════════════════════════════════════════════

@router.get("/{engagement_id}/attack-graph/layouts")
async def list_attack_graph_layouts(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all saved named layouts for this engagement."""
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_permission = await check_engagement_permission(
            current_user.id, engagement_id, "engagement_view", db
        )
        if not has_permission:
            raise HTTPException(status_code=403, detail="Access denied")

    result = await db.execute(
        select(AttackGraphLayout, User.username)
        .join(User, AttackGraphLayout.pinned_by == User.id)
        .where(AttackGraphLayout.engagement_id == engagement_id)
        .order_by(AttackGraphLayout.pinned_at.desc())
    )
    rows = result.all()
    return [
        {
            "id": row.AttackGraphLayout.id,
            "name": row.AttackGraphLayout.name,
            "is_active": row.AttackGraphLayout.is_active,
            "pinned_by": row.AttackGraphLayout.pinned_by,
            "pinned_by_username": row.username,
            "pinned_at": row.AttackGraphLayout.pinned_at.isoformat() if row.AttackGraphLayout.pinned_at else None,
        }
        for row in rows
    ]


@router.post("/{engagement_id}/attack-graph/layouts")
async def create_attack_graph_layout(
    engagement_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Save current positions as a new named layout."""
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_permission = await check_engagement_permission(
            current_user.id, engagement_id, "engagement_edit", db
        )
        if not has_permission:
            raise HTTPException(status_code=403, detail="Access denied")

    positions = body.get("positions")
    name = body.get("name", "Unnamed Layout")
    make_active = body.get("make_active", True)

    if not positions or not isinstance(positions, dict):
        raise HTTPException(status_code=400, detail="positions is required and must be a dict")

    from sqlalchemy import update as sa_update

    # If this layout will be active, deactivate all others first
    if make_active:
        await db.execute(
            sa_update(AttackGraphLayout)
            .where(AttackGraphLayout.engagement_id == engagement_id)
            .values(is_active=False)
        )

    layout = AttackGraphLayout(
        engagement_id=engagement_id,
        name=name,
        positions=json.dumps(positions),
        is_active=make_active,
        pinned_by=current_user.id,
        pinned_at=datetime.utcnow(),
    )
    db.add(layout)
    await db.commit()
    await db.refresh(layout)

    try:
        await manager.broadcast_to_resource("engagement", engagement_id, {
            "type": "graph_layout_saved",
            "layout_id": layout.id,
            "layout_name": layout.name,
            "is_active": layout.is_active,
            "username": current_user.username,
        })
    except Exception:
        pass

    return {
        "id": layout.id,
        "name": layout.name,
        "is_active": layout.is_active,
        "pinned_at": layout.pinned_at.isoformat() if layout.pinned_at else None,
    }


@router.put("/{engagement_id}/attack-graph/layouts/{layout_id}")
async def update_attack_graph_layout(
    engagement_id: str,
    layout_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update positions and/or name of a saved layout."""
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_permission = await check_engagement_permission(
            current_user.id, engagement_id, "engagement_edit", db
        )
        if not has_permission:
            raise HTTPException(status_code=403, detail="Access denied")

    result = await db.execute(
        select(AttackGraphLayout).where(
            AttackGraphLayout.id == layout_id,
            AttackGraphLayout.engagement_id == engagement_id,
        )
    )
    layout = result.scalar_one_or_none()
    if not layout:
        raise HTTPException(status_code=404, detail="Layout not found")

    if "name" in body:
        layout.name = body["name"]
    if "positions" in body:
        layout.positions = json.dumps(body["positions"])
        layout.pinned_by = current_user.id
        layout.pinned_at = datetime.utcnow()

    await db.commit()

    try:
        await manager.broadcast_to_resource("engagement", engagement_id, {
            "type": "graph_layout_saved",
            "layout_id": layout.id,
            "layout_name": layout.name,
            "username": current_user.username,
        })
    except Exception:
        pass

    return {"status": "ok"}


@router.put("/{engagement_id}/attack-graph/layouts/{layout_id}/activate")
async def activate_attack_graph_layout(
    engagement_id: str,
    layout_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Set a layout as the active one for all users."""
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_permission = await check_engagement_permission(
            current_user.id, engagement_id, "engagement_edit", db
        )
        if not has_permission:
            raise HTTPException(status_code=403, detail="Access denied")

    # Verify layout belongs to this engagement
    result = await db.execute(
        select(AttackGraphLayout).where(
            AttackGraphLayout.id == layout_id,
            AttackGraphLayout.engagement_id == engagement_id,
        )
    )
    layout = result.scalar_one_or_none()
    if not layout:
        raise HTTPException(status_code=404, detail="Layout not found")

    # Deactivate all layouts for this engagement
    from sqlalchemy import update as sa_update
    await db.execute(
        sa_update(AttackGraphLayout)
        .where(AttackGraphLayout.engagement_id == engagement_id)
        .values(is_active=False)
    )
    # Activate the chosen one
    layout.is_active = True
    await db.commit()

    try:
        await manager.broadcast_to_resource("engagement", engagement_id, {
            "type": "graph_layout_activated",
            "layout_id": layout.id,
            "layout_name": layout.name,
            "username": current_user.username,
        })
    except Exception:
        pass

    return {"status": "ok", "layout_name": layout.name}


@router.delete("/{engagement_id}/attack-graph/layouts/{layout_id}")
async def delete_attack_graph_layout_named(
    engagement_id: str,
    layout_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a named layout."""
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_permission = await check_engagement_permission(
            current_user.id, engagement_id, "engagement_edit", db
        )
        if not has_permission:
            raise HTTPException(status_code=403, detail="Access denied")

    result = await db.execute(
        select(AttackGraphLayout).where(
            AttackGraphLayout.id == layout_id,
            AttackGraphLayout.engagement_id == engagement_id,
        )
    )
    layout = result.scalar_one_or_none()
    if not layout:
        raise HTTPException(status_code=404, detail="Layout not found")

    if layout.name == "Default":
        raise HTTPException(status_code=409, detail="The Default layout cannot be deleted")

    was_active = layout.is_active
    await db.execute(
        sa_delete(AttackGraphLayout).where(AttackGraphLayout.id == layout_id)
    )
    await db.commit()

    try:
        await manager.broadcast_to_resource("engagement", engagement_id, {
            "type": "graph_layout_deleted",
            "layout_id": layout_id,
            "was_active": was_active,
            "username": current_user.username,
        })
    except Exception:
        pass

    return {"status": "ok"}


# ═══════════════════════════════════════════════════════════
# Legacy / backward-compat layout endpoints
# ═══════════════════════════════════════════════════════════

@router.put("/{engagement_id}/attack-graph/layout")
async def save_attack_graph_layout(
    engagement_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Pin the current attack graph layout (legacy: upsert a Default active layout)."""
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_permission = await check_engagement_permission(
            current_user.id, engagement_id, "engagement_edit", db
        )
        if not has_permission:
            raise HTTPException(status_code=403, detail="Access denied")

    positions = body.get("positions")
    if not positions or not isinstance(positions, dict):
        raise HTTPException(status_code=400, detail="positions is required and must be a dict")

    # Deactivate all others
    from sqlalchemy import update as sa_update
    await db.execute(
        sa_update(AttackGraphLayout)
        .where(AttackGraphLayout.engagement_id == engagement_id)
        .values(is_active=False)
    )

    # Upsert the Default active layout
    result = await db.execute(
        select(AttackGraphLayout).where(
            AttackGraphLayout.engagement_id == engagement_id,
            AttackGraphLayout.name == "Default",
        ).limit(1)
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.positions = json.dumps(positions)
        existing.pinned_by = current_user.id
        existing.pinned_at = datetime.utcnow()
        existing.is_active = True
    else:
        layout = AttackGraphLayout(
            engagement_id=engagement_id,
            name="Default",
            positions=json.dumps(positions),
            is_active=True,
            pinned_by=current_user.id,
        )
        db.add(layout)

    await db.commit()

    try:
        await manager.broadcast_to_resource("engagement", engagement_id, {
            "type": "graph_layout_pinned",
            "pinned_by": current_user.id,
            "username": current_user.username,
        })
    except Exception:
        pass

    return {"status": "ok"}


@router.delete("/{engagement_id}/attack-graph/layout")
async def delete_attack_graph_layout(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove active layout flag (legacy reset)."""
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_permission = await check_engagement_permission(
            current_user.id, engagement_id, "engagement_edit", db
        )
        if not has_permission:
            raise HTTPException(status_code=403, detail="Access denied")

    # Just deactivate all – don't delete, so named layouts are preserved
    from sqlalchemy import update as sa_update
    await db.execute(
        sa_update(AttackGraphLayout)
        .where(AttackGraphLayout.engagement_id == engagement_id)
        .values(is_active=False)
    )
    await db.commit()

    try:
        await manager.broadcast_to_resource("engagement", engagement_id, {
            "type": "graph_layout_unpinned",
            "unpinned_by": current_user.id,
            "username": current_user.username,
        })
    except Exception:
        pass

    return {"status": "ok"}


# ═══════════════════════════════════════════════════════════
# Attacker Node CRUD
# ═══════════════════════════════════════════════════════════

@router.post("/{engagement_id}/attack-graph/attacker")
async def create_attacker_node(
    engagement_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create an attacker node."""
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_permission = await check_engagement_permission(
            current_user.id, engagement_id, "engagement_edit", db
        )
        if not has_permission:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    node = AttackerNode(
        engagement_id=engagement_id,
        name=body.get("name", "Threat Actor"),
        point_of_presence=body.get("point_of_presence", "External"),
        description=body.get("description"),
    )
    db.add(node)
    await db.commit()
    await db.refresh(node)

    try:
        await manager.broadcast_to_resource("engagement", engagement_id, {
            "type": "graph_attacker_changed",
            "username": current_user.username,
        })
    except Exception:
        pass

    return {"id": node.id, "name": node.name, "point_of_presence": node.point_of_presence}


@router.put("/{engagement_id}/attack-graph/attacker/{attacker_id}")
async def update_attacker_node(
    engagement_id: str,
    attacker_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update an attacker node."""
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_permission = await check_engagement_permission(
            current_user.id, engagement_id, "engagement_edit", db
        )
        if not has_permission:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(AttackerNode).where(AttackerNode.id == attacker_id, AttackerNode.engagement_id == engagement_id)
    )
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Attacker node not found")

    if "name" in body:
        node.name = body["name"]
    if "point_of_presence" in body:
        node.point_of_presence = body["point_of_presence"]
    if "description" in body:
        node.description = body["description"]

    await db.commit()

    try:
        await manager.broadcast_to_resource("engagement", engagement_id, {
            "type": "graph_attacker_changed",
            "username": current_user.username,
        })
    except Exception:
        pass

    return {"status": "ok"}


@router.delete("/{engagement_id}/attack-graph/attacker/{attacker_id}")
async def delete_attacker_node(
    engagement_id: str,
    attacker_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete an attacker node (cascades to edges)."""
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_permission = await check_engagement_permission(
            current_user.id, engagement_id, "engagement_edit", db
        )
        if not has_permission:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    await db.execute(
        sa_delete(AttackerNode).where(AttackerNode.id == attacker_id, AttackerNode.engagement_id == engagement_id)
    )
    await db.commit()

    try:
        await manager.broadcast_to_resource("engagement", engagement_id, {
            "type": "graph_attacker_changed",
            "username": current_user.username,
        })
    except Exception:
        pass

    return {"status": "ok"}


@router.post("/{engagement_id}/attack-graph/attacker/{attacker_id}/edge")
async def create_attacker_edge(
    engagement_id: str,
    attacker_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create an edge from attacker to a target node."""
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_permission = await check_engagement_permission(
            current_user.id, engagement_id, "engagement_edit", db
        )
        if not has_permission:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    target_node_id = body.get("target_node_id")
    target_node_type = body.get("target_node_type", "testcase")
    if not target_node_id:
        raise HTTPException(status_code=400, detail="target_node_id is required")

    # The frontend posts the React Flow graph id ("testcase-<uuid>", etc.)
    # which is also what `AttackerNodeEdge.target_node_id` stores (per its
    # schema comment). Strip the "<type>-" prefix when we need the bare
    # entity id for an FK lookup, but keep the prefixed form for storage
    # so existing rows continue to render correctly.
    _prefix = f"{target_node_type}-"
    target_entity_id = (
        target_node_id[len(_prefix):]
        if target_node_id.startswith(_prefix)
        else target_node_id
    )

    # Verify the target node belongs to this engagement (mirrors vault.py's
    # cross-engagement guard). Without this an attacker could draw graph
    # edges from a same-engagement attacker node to a foreign testcase /
    # finding / asset, pulling the target's serialized fields back through
    # graph reads.
    from models.testcase import TestCase as _TC
    from models.finding import Finding as _Finding
    from models.asset import Asset as _Asset
    from models.infra_item import InfraItem as _Infra
    _target_models = {"testcase": _TC, "finding": _Finding, "asset": _Asset, "infra": _Infra}
    _model = _target_models.get(target_node_type)
    if _model is None:
        raise HTTPException(status_code=400, detail="Unsupported target_node_type")
    _target = (await db.execute(
        select(_model).where(_model.id == target_entity_id)
    )).scalar_one_or_none()
    if not _target:
        raise HTTPException(status_code=404, detail=f"{target_node_type.capitalize()} not found")
    if target_node_type == "infra":
        # InfraItem is a shared pool with no engagement_id. Mirror the
        # auto-surface rule from get_attack_graph: the infra item is
        # "in play" for this engagement iff at least one of its links
        # points at a finding or testcase scoped to this engagement.
        # Without this check an attacker could draw an edge from a
        # same-engagement attacker node to any infra item in the
        # platform — pulling its hostname/IP/notes through graph reads.
        linked_here = (await db.execute(
            select(InfraItemFinding.infra_item_id)
            .join(Finding, InfraItemFinding.finding_id == Finding.id)
            .where(
                InfraItemFinding.infra_item_id == target_entity_id,
                Finding.engagement_id == engagement_id,
            ).limit(1)
        )).scalar_one_or_none()
        if linked_here is None:
            linked_here = (await db.execute(
                select(InfraItemTestCase.infra_item_id)
                .join(TestCase, InfraItemTestCase.testcase_id == TestCase.id)
                .where(
                    InfraItemTestCase.infra_item_id == target_entity_id,
                    TestCase.engagement_id == engagement_id,
                ).limit(1)
            )).scalar_one_or_none()
        if linked_here is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Infra item is not linked to any finding or testcase in "
                    "this engagement. Link it to one first, then draw the edge."
                ),
            )
    elif getattr(_target, "engagement_id", None) != engagement_id:
        raise HTTPException(
            status_code=400,
            detail=f"{target_node_type.capitalize()} belongs to a different engagement",
        )

    # Check for duplicate edge
    existing = await db.execute(
        select(AttackerNodeEdge).where(
            AttackerNodeEdge.attacker_node_id == attacker_id,
            AttackerNodeEdge.target_node_id == target_node_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Connection already exists")

    edge = AttackerNodeEdge(
        attacker_node_id=attacker_id,
        target_node_id=target_node_id,
        target_node_type=target_node_type,
    )
    db.add(edge)
    await db.commit()
    await db.refresh(edge)

    try:
        await manager.broadcast_to_resource("engagement", engagement_id, {
            "type": "graph_attacker_changed",
            "username": current_user.username,
        })
    except Exception:
        pass

    return {"id": edge.id}


@router.delete("/{engagement_id}/attack-graph/attacker/{attacker_id}/edge/{edge_id}")
async def delete_attacker_edge(
    engagement_id: str,
    attacker_id: str,
    edge_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove an edge from attacker node."""
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_permission = await check_engagement_permission(
            current_user.id, engagement_id, "engagement_edit", db
        )
        if not has_permission:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    await db.execute(
        sa_delete(AttackerNodeEdge).where(
            AttackerNodeEdge.id == edge_id,
            AttackerNodeEdge.attacker_node_id == attacker_id,
        )
    )
    await db.commit()

    try:
        await manager.broadcast_to_resource("engagement", engagement_id, {
            "type": "graph_attacker_changed",
            "username": current_user.username,
        })
    except Exception:
        pass

    return {"status": "ok"}
