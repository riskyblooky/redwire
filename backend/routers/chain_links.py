from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, delete as sa_delete
from sqlalchemy.exc import IntegrityError
from typing import Optional

from database import get_db
from models.user import User, UserRole
from models.engagement import Engagement
from models.finding import Finding
from models.testcase import TestCase
from models.vault import VaultItem
from models.chain_link import ChainLink, CHAIN_NODE_TYPES, CHAIN_RELATION_DEFAULT
from models.associations import FindingTestCase, VaultItemFinding, VaultItemTestCase
from schemas.chain_link import (
    ChainNodeRef, ChainLinkCreate, ChainLinkNoteUpdate,
    ChainLinkOut, ChainNeighbor, ChainLinksForEntity,
)
from auth.dependencies import get_current_user
from auth.rbac import check_engagement_permission
from utils.collaboration import create_activity_log, manager

router = APIRouter(prefix="/engagements", tags=["chain-links"])

_TYPE_MODEL = {"testcase": TestCase, "finding": Finding, "vault_item": VaultItem}


# ── permission helpers (mirror attack_graph.py) ──
async def _require_view(current_user: User, engagement_id: str, db: AsyncSession):
    if current_user.role in (UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD):
        return
    if not await check_engagement_permission(current_user.id, engagement_id, "engagement_view", db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


async def _require_edit(current_user: User, engagement_id: str, db: AsyncSession):
    if current_user.role in (UserRole.ADMIN, UserRole.TEAM_LEAD):
        return
    if not await check_engagement_permission(current_user.id, engagement_id, "engagement_edit", db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


async def _load_node_maps(engagement_id: str, db: AsyncSession):
    """Build {id: ChainNodeRef} lookups for every chain-eligible entity in the
    engagement, so edges can be resolved to labels in one pass."""
    maps: dict[str, dict[str, ChainNodeRef]] = {"testcase": {}, "finding": {}, "vault_item": {}}

    tcs = (await db.execute(
        select(TestCase.id, TestCase.title, TestCase.category, TestCase.is_executed, TestCase.is_successful)
        .where(TestCase.engagement_id == engagement_id)
    )).all()
    for r in tcs:
        st = "Not Executed" if not r.is_executed else ("Pass" if r.is_successful else "Fail")
        maps["testcase"][r.id] = ChainNodeRef(type="testcase", id=r.id, label=r.title, sub=r.category, status=st)

    fs = (await db.execute(
        select(Finding.id, Finding.title, Finding.category, Finding.severity, Finding.status)
        .where(Finding.engagement_id == engagement_id)
    )).all()
    for r in fs:
        maps["finding"][r.id] = ChainNodeRef(
            type="finding", id=r.id, label=r.title, sub=r.category or "Uncategorized",
            severity=r.severity.value if r.severity else None,
            status=r.status.value if r.status else None,
        )

    vs = (await db.execute(
        select(VaultItem.id, VaultItem.name, VaultItem.item_type)
        .where(VaultItem.engagement_id == engagement_id)
    )).all()
    for r in vs:
        maps["vault_item"][r.id] = ChainNodeRef(type="vault_item", id=r.id, label=r.name, sub=r.item_type)

    return maps


def _resolve(maps, type_: str, id_: str) -> ChainNodeRef:
    node = maps.get(type_, {}).get(id_)
    if node is not None:
        return node
    # Dangling endpoint (entity deleted out from under the edge, or foreign).
    return ChainNodeRef(type=type_, id=id_, label=None)


def _ref_from_entity(type_: str, entity) -> ChainNodeRef:
    """Build a ChainNodeRef from an already-loaded ORM entity — avoids a
    whole-engagement _load_node_maps scan when the endpoints are in hand."""
    if type_ == "finding":
        return ChainNodeRef(
            type="finding", id=entity.id, label=entity.title,
            sub=entity.category or "Uncategorized",
            severity=entity.severity.value if entity.severity else None,
            status=entity.status.value if entity.status else None,
        )
    if type_ == "testcase":
        st = "Not Executed" if not entity.is_executed else ("Pass" if entity.is_successful else "Fail")
        return ChainNodeRef(type="testcase", id=entity.id, label=entity.title, sub=entity.category, status=st)
    return ChainNodeRef(type="vault_item", id=entity.id, label=entity.name, sub=entity.item_type)


async def _resolve_one(type_: str, id_: str, db: AsyncSession) -> ChainNodeRef:
    """Resolve a single (type, id) to a ChainNodeRef with one query; returns a
    dangling ref if the entity no longer exists."""
    model = _TYPE_MODEL.get(type_)
    if model is None:
        return ChainNodeRef(type=type_, id=id_, label=None)
    entity = (await db.execute(select(model).where(model.id == id_))).scalar_one_or_none()
    if entity is None:
        return ChainNodeRef(type=type_, id=id_, label=None)
    return _ref_from_entity(type_, entity)


async def _flat_linked_refs(entity_type: str, entity_id: str, db: AsyncSession):
    """The (type, id) pairs already associated with this entity via the flat
    link tables — the pool the chain can be 'promoted' from. Only the
    chain-eligible relationships (finding↔testcase, vault↔finding,
    vault↔testcase) are considered."""
    refs: list[tuple[str, str]] = []
    if entity_type == "finding":
        for r in (await db.execute(
            select(FindingTestCase.testcase_id).where(FindingTestCase.finding_id == entity_id)
        )).all():
            refs.append(("testcase", r.testcase_id))
        for r in (await db.execute(
            select(VaultItemFinding.vault_item_id).where(VaultItemFinding.finding_id == entity_id)
        )).all():
            refs.append(("vault_item", r.vault_item_id))
    elif entity_type == "testcase":
        for r in (await db.execute(
            select(FindingTestCase.finding_id).where(FindingTestCase.testcase_id == entity_id)
        )).all():
            refs.append(("finding", r.finding_id))
        for r in (await db.execute(
            select(VaultItemTestCase.vault_item_id).where(VaultItemTestCase.testcase_id == entity_id)
        )).all():
            refs.append(("vault_item", r.vault_item_id))
    elif entity_type == "vault_item":
        for r in (await db.execute(
            select(VaultItemFinding.finding_id).where(VaultItemFinding.vault_item_id == entity_id)
        )).all():
            refs.append(("finding", r.finding_id))
        for r in (await db.execute(
            select(VaultItemTestCase.testcase_id).where(VaultItemTestCase.vault_item_id == entity_id)
        )).all():
            refs.append(("testcase", r.testcase_id))
    return refs


async def _verify_engagement(engagement_id: str, db: AsyncSession):
    exists = (await db.execute(select(Engagement.id).where(Engagement.id == engagement_id))).scalar_one_or_none()
    if not exists:
        raise HTTPException(status_code=404, detail="Engagement not found")


# ═══════════════════════════════════════════════════════════
# Reads
# ═══════════════════════════════════════════════════════════

@router.get("/{engagement_id}/chain-links", response_model=list[ChainLinkOut])
async def list_chain_links(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """All chain edges for the engagement, resolved to node summaries."""
    await _require_view(current_user, engagement_id, db)
    await _verify_engagement(engagement_id, db)

    maps = await _load_node_maps(engagement_id, db)
    rows = (await db.execute(
        select(ChainLink).where(ChainLink.engagement_id == engagement_id)
    )).scalars().all()
    return [
        ChainLinkOut(
            id=row.id, relation=row.relation, note=row.note,
            source=_resolve(maps, row.source_type, row.source_id),
            target=_resolve(maps, row.target_type, row.target_id),
        )
        for row in rows
    ]


@router.get("/{engagement_id}/chain-links/for/{entity_type}/{entity_id}",
            response_model=ChainLinksForEntity)
async def chain_links_for_entity(
    engagement_id: str,
    entity_type: str,
    entity_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Chain edges touching one entity, split into upstream (causes) and
    downstream (effects)."""
    await _require_view(current_user, engagement_id, db)
    if entity_type not in CHAIN_NODE_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported entity_type")

    maps = await _load_node_maps(engagement_id, db)
    # The focused entity must belong to this engagement. Without this, a
    # foreign entity_id would fall through to _flat_linked_refs (which is
    # keyed only on the id, not the engagement) and leak the ids of another
    # engagement's linked items as candidates.
    if entity_id not in maps.get(entity_type, {}):
        raise HTTPException(status_code=404, detail="Entity not found in this engagement")

    rows = (await db.execute(
        select(ChainLink).where(
            ChainLink.engagement_id == engagement_id,
            or_(
                and_(ChainLink.source_type == entity_type, ChainLink.source_id == entity_id),
                and_(ChainLink.target_type == entity_type, ChainLink.target_id == entity_id),
            ),
        )
    )).scalars().all()

    upstream: list[ChainNeighbor] = []
    downstream: list[ChainNeighbor] = []
    for row in rows:
        is_source = row.source_type == entity_type and row.source_id == entity_id
        if is_source:
            # this entity → target: target is an effect (downstream)
            downstream.append(ChainNeighbor(
                link_id=row.id, relation=row.relation, note=row.note,
                node=_resolve(maps, row.target_type, row.target_id),
            ))
        else:
            # source → this entity: source is a cause (upstream)
            upstream.append(ChainNeighbor(
                link_id=row.id, relation=row.relation, note=row.note,
                node=_resolve(maps, row.source_type, row.source_id),
            ))

    # Promotable suggestions: flat-linked items not already chained to this
    # entity in either direction. "Linked" is broader than "caused", so these
    # are offered as one-click promotions rather than auto-created edges.
    chained_keys = {(n.node.type, n.node.id) for n in (upstream + downstream)}
    candidates: list[ChainNodeRef] = []
    seen: set[tuple[str, str]] = set()
    for (t, i) in await _flat_linked_refs(entity_type, entity_id, db):
        if (t, i) in chained_keys or (t, i) in seen:
            continue
        seen.add((t, i))
        candidates.append(_resolve(maps, t, i))

    return ChainLinksForEntity(upstream=upstream, downstream=downstream, candidates=candidates)


# ═══════════════════════════════════════════════════════════
# Writes
# ═══════════════════════════════════════════════════════════

async def _fetch_scoped(type_: str, id_: str, engagement_id: str, db: AsyncSession, label: str):
    model = _TYPE_MODEL.get(type_)
    if model is None:
        raise HTTPException(status_code=400, detail=f"Unsupported {label}_type")
    entity = (await db.execute(select(model).where(model.id == id_))).scalar_one_or_none()
    if entity is None:
        raise HTTPException(status_code=404, detail=f"{label.capitalize()} entity not found")
    if entity.engagement_id != engagement_id:
        raise HTTPException(status_code=400, detail=f"{label.capitalize()} entity belongs to a different engagement")
    return entity


def _node_name(entity) -> str:
    return getattr(entity, "title", None) or getattr(entity, "name", None) or "item"


@router.post("/{engagement_id}/chain-links", response_model=ChainLinkOut, status_code=201)
async def create_chain_link(
    engagement_id: str,
    body: ChainLinkCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a directed causal edge: source → target ("source led to target")."""
    await _require_edit(current_user, engagement_id, db)
    await _verify_engagement(engagement_id, db)

    if body.source_type not in CHAIN_NODE_TYPES or body.target_type not in CHAIN_NODE_TYPES:
        raise HTTPException(status_code=400, detail="type must be one of testcase, finding, vault_item")

    # No self-loop.
    if body.source_type == body.target_type and body.source_id == body.target_id:
        raise HTTPException(status_code=400, detail="An item cannot lead to itself")

    # Testcase → testcase is the organizational tree (testcases.parent_id),
    # not a causal chain edge. Route those through the tree instead.
    if body.source_type == "testcase" and body.target_type == "testcase":
        raise HTTPException(
            status_code=400,
            detail="Testcase-to-testcase links are the testcase tree, not a chain. Use the parent relationship.",
        )

    # Both endpoints must exist and belong to this engagement.
    src = await _fetch_scoped(body.source_type, body.source_id, engagement_id, db, "source")
    tgt = await _fetch_scoped(body.target_type, body.target_id, engagement_id, db, "target")

    # Reject an exact duplicate or the inverse (which would form a 2-cycle).
    dup = (await db.execute(
        select(ChainLink).where(
            ChainLink.engagement_id == engagement_id,
            or_(
                and_(
                    ChainLink.source_type == body.source_type, ChainLink.source_id == body.source_id,
                    ChainLink.target_type == body.target_type, ChainLink.target_id == body.target_id,
                ),
                and_(
                    ChainLink.source_type == body.target_type, ChainLink.source_id == body.target_id,
                    ChainLink.target_type == body.source_type, ChainLink.target_id == body.source_id,
                ),
            ),
        ).limit(1)
    )).scalar_one_or_none()
    if dup is not None:
        raise HTTPException(status_code=409, detail="These two items are already linked in a chain")

    link = ChainLink(
        engagement_id=engagement_id,
        source_type=body.source_type, source_id=body.source_id,
        target_type=body.target_type, target_id=body.target_id,
        relation=CHAIN_RELATION_DEFAULT,
        note=body.note,
        created_by=current_user.id,
    )
    db.add(link)
    try:
        await db.commit()
    except IntegrityError:
        # Lost a race against the uq_chain_link_edge constraint — a concurrent
        # request created the same edge between the app-level dup check above
        # and this commit.
        await db.rollback()
        raise HTTPException(status_code=409, detail="These two items are already linked in a chain")
    await db.refresh(link)

    await create_activity_log(
        db, engagement_id=engagement_id, user_id=current_user.id,
        action="linked_chain",
        resource_type=body.source_type, resource_id=body.source_id,
        resource_name=_node_name(src),
        details=f"Chained '{_node_name(src)}' → '{_node_name(tgt)}'",
    )
    try:
        await manager.broadcast_to_resource("engagement", engagement_id, {
            "type": "graph_attacker_changed", "username": current_user.username,
        })
    except Exception:
        pass

    # src/tgt are already loaded — resolve the response directly instead of
    # re-scanning the whole engagement via _load_node_maps.
    return ChainLinkOut(
        id=link.id, relation=link.relation, note=link.note,
        source=_ref_from_entity(body.source_type, src),
        target=_ref_from_entity(body.target_type, tgt),
    )


@router.patch("/{engagement_id}/chain-links/{link_id}", response_model=ChainLinkOut)
async def update_chain_link_note(
    engagement_id: str,
    link_id: str,
    body: ChainLinkNoteUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Edit the note on a chain edge."""
    await _require_edit(current_user, engagement_id, db)
    link = (await db.execute(
        select(ChainLink).where(ChainLink.id == link_id, ChainLink.engagement_id == engagement_id)
    )).scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=404, detail="Chain link not found")

    link.note = body.note
    link.updated_by = current_user.id
    await db.commit()
    await db.refresh(link)

    # Resolve just the two endpoints rather than scanning the whole engagement.
    return ChainLinkOut(
        id=link.id, relation=link.relation, note=link.note,
        source=await _resolve_one(link.source_type, link.source_id, db),
        target=await _resolve_one(link.target_type, link.target_id, db),
    )


@router.delete("/{engagement_id}/chain-links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chain_link(
    engagement_id: str,
    link_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a chain edge."""
    await _require_edit(current_user, engagement_id, db)
    link = (await db.execute(
        select(ChainLink).where(ChainLink.id == link_id, ChainLink.engagement_id == engagement_id)
    )).scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=404, detail="Chain link not found")

    await db.execute(sa_delete(ChainLink).where(ChainLink.id == link_id))
    await db.commit()
    try:
        await manager.broadcast_to_resource("engagement", engagement_id, {
            "type": "graph_attacker_changed", "username": current_user.username,
        })
    except Exception:
        pass
    return None
