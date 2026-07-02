from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from sqlalchemy.orm import selectinload
from typing import List
from database import get_db
from models.user import User, UserRole
from models.client import Client
from models.engagement import Engagement
from models.configurable_type import ConfigurableType
from schemas.client import (
    ClientCreate, ClientUpdate, ClientResponse, ClientTreeNode,
    ClientReorderRequest,
    ClientStatsResponse, EngagementSummary,
)
from schemas.configurable_type import (
    ConfigurableTypeCreate, ConfigurableTypeUpdate, ConfigurableTypeResponse
)
from auth.dependencies import get_current_user
from auth.permissions import has_global_permission
from models.permission import Permission

router = APIRouter(prefix="/clients", tags=["clients"])


# GHSA-rq7c-4v9x-mjfp issue 3 (CWE-835): defence against parent-chain
# cycles in the client tree. Every DB-backed parent walk in this file
# (single-node update-time check, batch reorder pre-commit check, ancestor
# lookups) is bounded by this depth. Legitimate client trees never come
# close — RedWire deployments almost always have a two- or three-level
# hierarchy — so this cap is effectively "impossible for real data" but
# small enough that even a 1000-cycle write can't hang a worker for more
# than a handful of milliseconds.
_MAX_CLIENT_TREE_DEPTH = 1000


# ============ Helper: Check manage_clients permission ============

async def require_manage_clients(current_user: User, db: AsyncSession):
    """Check that the user has the manage_clients permission."""
    has_perm = await has_global_permission(current_user, Permission.MANAGE_CLIENTS, db)
    if not has_perm:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You need the 'manage_clients' permission to perform this action."
        )


# ============ Helper: Build tree from flat list ============

def build_tree(clients: List[Client], engagement_counts: dict) -> List[ClientTreeNode]:
    """Build a hierarchical tree from a flat list of clients."""
    node_map = {}
    roots = []

    for client in clients:
        node = ClientTreeNode(
            id=client.id,
            name=client.name,
            description=client.description,
            client_type_id=client.client_type_id,
            client_type=client.client_type,
            parent_id=client.parent_id,
            sort_order=client.sort_order,
            contact_name=client.contact_name,
            contact_email=client.contact_email,
            notes=client.notes,
            created_at=client.created_at,
            updated_at=client.updated_at,
            engagement_count=engagement_counts.get(client.id, 0),
            children=[]
        )
        node_map[client.id] = node

    for client in clients:
        node = node_map[client.id]
        if client.parent_id and client.parent_id in node_map:
            node_map[client.parent_id].children.append(node)
        else:
            roots.append(node)

    return roots


# ============ Client Type Endpoints (backed by configurable_types) ============

client_type_router = APIRouter(prefix="/client-types", tags=["client-types"])


@client_type_router.get("", response_model=List[ConfigurableTypeResponse])
async def get_client_types(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all client types."""
    result = await db.execute(
        select(ConfigurableType)
        .where(ConfigurableType.category == "client")
        .order_by(ConfigurableType.sort_order, ConfigurableType.name)
    )
    return result.scalars().all()


@client_type_router.post("", response_model=ConfigurableTypeResponse, status_code=status.HTTP_201_CREATED)
async def create_client_type(
    data: ConfigurableTypeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new client type."""
    await require_manage_clients(current_user, db)

    # Check uniqueness within category
    existing = await db.execute(
        select(ConfigurableType).where(
            ConfigurableType.category == "client",
            ConfigurableType.name == data.name
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Client type '{data.name}' already exists.")

    # Get next sort order
    max_order = await db.execute(
        select(func.max(ConfigurableType.sort_order)).where(ConfigurableType.category == "client")
    )
    next_order = (max_order.scalar() or 0) + 1

    new_type = ConfigurableType(
        category="client",
        name=data.name,
        description=data.description,
        color=data.color,
        sort_order=next_order,
    )
    db.add(new_type)
    await db.commit()
    await db.refresh(new_type)
    return new_type


@client_type_router.put("/{type_id}", response_model=ConfigurableTypeResponse)
async def update_client_type(
    type_id: str,
    data: ConfigurableTypeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a client type."""
    await require_manage_clients(current_user, db)

    result = await db.execute(
        select(ConfigurableType).where(ConfigurableType.id == type_id, ConfigurableType.category == "client")
    )
    ct = result.scalar_one_or_none()
    if not ct:
        raise HTTPException(status_code=404, detail="Client type not found.")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(ct, field, value)

    await db.commit()
    await db.refresh(ct)
    return ct


@client_type_router.delete("/{type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client_type(
    type_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a client type. Cannot delete system types."""
    await require_manage_clients(current_user, db)

    result = await db.execute(
        select(ConfigurableType).where(ConfigurableType.id == type_id, ConfigurableType.category == "client")
    )
    ct = result.scalar_one_or_none()
    if not ct:
        raise HTTPException(status_code=404, detail="Client type not found.")
    if ct.is_system:
        raise HTTPException(status_code=400, detail="Cannot delete a system client type.")

    # Check if any clients use this type
    count_result = await db.execute(
        select(func.count(Client.id)).where(Client.client_type_id == type_id)
    )
    count = count_result.scalar() or 0
    if count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete: {count} client(s) are using this type. Reassign them first."
        )

    await db.delete(ct)
    await db.commit()


# ============ Client Endpoints ============

@router.get("", response_model=List[ClientResponse])
async def get_clients(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all clients as a flat list."""
    # GHSA-fj3c-4c5j-cq87: confine non-admins to their granted clients.
    accessible_ids = None
    if current_user.role not in (UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD):
        accessible_ids = await get_accessible_client_ids(current_user.id, db)
        if not accessible_ids:
            return []

    # Subquery for engagement counts
    eng_count_sq = (
        select(Engagement.client_id, func.count(Engagement.id).label("eng_count"))
        .where(Engagement.client_id.isnot(None))
        .group_by(Engagement.client_id)
        .subquery()
    )

    query = (
        select(Client, func.coalesce(eng_count_sq.c.eng_count, 0).label("engagement_count"))
        .outerjoin(eng_count_sq, Client.id == eng_count_sq.c.client_id)
        .options(selectinload(Client.client_type))
        .order_by(Client.sort_order, Client.name)
    )
    if accessible_ids is not None:
        query = query.where(Client.id.in_(accessible_ids))
    result = await db.execute(query)
    rows = result.all()

    clients = []
    for client, eng_count in rows:
        client.engagement_count = eng_count
        clients.append(client)
    return clients


@router.get("/tree", response_model=List[ClientTreeNode])
async def get_client_tree(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the full hierarchical client tree."""
    # GHSA-fj3c-4c5j-cq87: confine non-admins to their granted clients.
    accessible_ids = None
    if current_user.role not in (UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD):
        accessible_ids = await get_accessible_client_ids(current_user.id, db)
        if not accessible_ids:
            return []

    # Get all clients
    query = (
        select(Client)
        .options(selectinload(Client.client_type))
        .order_by(Client.sort_order, Client.name)
    )
    if accessible_ids is not None:
        query = query.where(Client.id.in_(accessible_ids))
    result = await db.execute(query)
    all_clients = result.scalars().all()

    # Get engagement counts
    eng_counts = await db.execute(
        select(Engagement.client_id, func.count(Engagement.id))
        .where(Engagement.client_id.isnot(None))
        .group_by(Engagement.client_id)
    )
    engagement_counts = dict(eng_counts.all())

    return build_tree(all_clients, engagement_counts)


@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(
    client_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single client."""
    # GHSA-fj3c-4c5j-cq87: enforce per-user client visibility.
    await _ensure_client_visible(client_id, current_user, db)
    result = await db.execute(
        select(Client)
        .options(selectinload(Client.client_type))
        .where(Client.id == client_id)
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found.")

    # Get engagement count
    eng_count = await db.execute(
        select(func.count(Engagement.id)).where(Engagement.client_id == client_id)
    )
    client.engagement_count = eng_count.scalar() or 0
    return client


@router.post("", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
async def create_client(
    data: ClientCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new client."""
    await require_manage_clients(current_user, db)

    # If parent_id specified, verify it exists
    if data.parent_id:
        parent = await db.execute(select(Client).where(Client.id == data.parent_id))
        if not parent.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Parent client not found.")

    # Get next sort order for siblings
    sibling_query = select(func.max(Client.sort_order)).where(Client.parent_id == data.parent_id)
    max_order = await db.execute(sibling_query)
    next_order = (max_order.scalar() or 0) + 1

    new_client = Client(
        name=data.name,
        description=data.description,
        client_type_id=data.client_type_id,
        parent_id=data.parent_id,
        sort_order=next_order,
        contact_name=data.contact_name,
        contact_email=data.contact_email,
        notes=data.notes,
        created_by=current_user.id,
    )
    db.add(new_client)
    await db.commit()
    await db.refresh(new_client)

    # Reload with relationships
    result = await db.execute(
        select(Client).options(selectinload(Client.client_type)).where(Client.id == new_client.id)
    )
    return result.scalar_one()


@router.put("/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: str,
    data: ClientUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a client."""
    await require_manage_clients(current_user, db)

    result = await db.execute(
        select(Client).options(selectinload(Client.client_type)).where(Client.id == client_id)
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found.")

    update_data = data.model_dump(exclude_unset=True)

    # Prevent circular parent reference
    if "parent_id" in update_data:
        new_parent = update_data["parent_id"]
        if new_parent == client_id:
            raise HTTPException(status_code=400, detail="A client cannot be its own parent.")
        # Check if the new parent is a descendant of this client.
        # GHSA-rq7c-4v9x-mjfp issue 3: bound the walk. A legitimate tree
        # is never this deep — if we hit the cap it's either a cycle in
        # legacy bad data or an attempt to write one; refuse either way.
        if new_parent:
            current_check = new_parent
            for _ in range(_MAX_CLIENT_TREE_DEPTH):
                if current_check is None:
                    break
                p_result = await db.execute(select(Client.parent_id).where(Client.id == current_check))
                p_row = p_result.scalar_one_or_none()
                if p_row == client_id:
                    raise HTTPException(status_code=400, detail="Cannot set parent: would create circular reference.")
                current_check = p_row
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Ancestor walk exceeded depth cap — suspected cycle in existing client tree.",
                )

    for field, value in update_data.items():
        setattr(client, field, value)

    client.updated_by = current_user.id
    await db.commit()
    await db.refresh(client)

    # Reload with relationships
    result = await db.execute(
        select(Client).options(selectinload(Client.client_type)).where(Client.id == client_id)
    )
    return result.scalar_one()


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client(
    client_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a client. Blocked if engagements reference it."""
    await require_manage_clients(current_user, db)

    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found.")

    # Check if engagements reference this client
    eng_count = await db.execute(
        select(func.count(Engagement.id)).where(Engagement.client_id == client_id)
    )
    count = eng_count.scalar() or 0
    if count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete: {count} engagement(s) reference this client. Reassign them first."
        )

    # Check for child clients
    child_count = await db.execute(
        select(func.count(Client.id)).where(Client.parent_id == client_id)
    )
    c_count = child_count.scalar() or 0
    if c_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete: {c_count} child client(s) exist. Delete or reassign them first."
        )

    await db.delete(client)
    await db.commit()


async def _assert_no_reorder_cycle(
    items: list, db: AsyncSession
) -> None:
    """GHSA-rq7c-4v9x-mjfp issue 3: refuse a batch reorder that would
    introduce a parent-chain cycle in the client tree.

    The reorder handler writes ``(sort_order, parent_id)`` for many
    clients at once. Previously it committed the writes without any
    cycle check, so a payload like ``[{A→B}, {B→A}]`` created a
    self-referential loop that hung the next tree walk at 100% CPU.

    Approach: build the POST-COMMIT parent-map first (current DB state
    overlaid with the incoming batch), then walk each mutated id's
    chain to root bounded by ``_MAX_CLIENT_TREE_DEPTH``. Any revisit of
    a starting id, or hitting the depth cap, is a cycle → refuse the
    whole batch before any writes.
    """
    # Load the current parent for every client — cheap, one query.
    result = await db.execute(select(Client.id, Client.parent_id))
    parent_of: dict[str, str | None] = {row[0]: row[1] for row in result.all()}

    # Overlay the proposed batch. Reject unknown ids and self-parents up
    # front for a cleaner error than surfacing them via the walk.
    for item in items:
        if item.id not in parent_of:
            raise HTTPException(status_code=400, detail=f"Unknown client id: {item.id}")
        if item.parent_id == item.id:
            raise HTTPException(status_code=400, detail=f"Client {item.id} cannot be its own parent.")
        if item.parent_id is not None and item.parent_id not in parent_of:
            raise HTTPException(status_code=400, detail=f"Unknown parent_id: {item.parent_id}")
        parent_of[item.id] = item.parent_id

    # Walk each mutated id's ancestor chain. A cycle either revisits the
    # starting id or blows the depth cap.
    for item in items:
        seen: set[str] = {item.id}
        current = parent_of[item.id]
        for _ in range(_MAX_CLIENT_TREE_DEPTH):
            if current is None:
                break
            if current in seen:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Reorder would create a parent-chain cycle involving "
                        f"client {item.id}. Refusing the whole batch."
                    ),
                )
            seen.add(current)
            current = parent_of.get(current)
        else:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Client {item.id}'s ancestor chain exceeded "
                    f"{_MAX_CLIENT_TREE_DEPTH} — refusing as a suspected cycle."
                ),
            )


@router.post("/reorder", status_code=status.HTTP_200_OK)
async def reorder_clients(
    data: ClientReorderRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Batch reorder clients (drag-and-drop)."""
    await require_manage_clients(current_user, db)

    # GHSA-rq7c-4v9x-mjfp: refuse cycles up front so a payload like
    # [{A→B}, {B→A}] can't land in the DB.
    await _assert_no_reorder_cycle(list(data.items), db)

    for item in data.items:
        await db.execute(
            update(Client)
            .where(Client.id == item.id)
            .values(sort_order=item.sort_order, parent_id=item.parent_id)
        )

    await db.commit()
    return {"status": "ok"}


# ============ Client User Access Endpoints ============


async def require_manage_client_access(current_user: User, db: AsyncSession):
    """Check that the user has the manage_client_access permission."""
    has_perm = await has_global_permission(current_user, Permission.MANAGE_CLIENT_ACCESS, db)
    if not has_perm:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You need the 'manage_client_access' permission to perform this action."
        )


async def get_descendant_client_ids(db: AsyncSession, client_ids: set[str]) -> set[str]:
    """Given a set of client IDs, return them plus ALL descendant IDs (recursive)."""
    all_ids = set(client_ids)
    frontier = set(client_ids)
    while frontier:
        result = await db.execute(
            select(Client.id).where(Client.parent_id.in_(frontier))
        )
        children = set(result.scalars().all())
        new_children = children - all_ids
        if not new_children:
            break
        all_ids |= new_children
        frontier = new_children
    return all_ids


async def get_accessible_client_ids(user_id: str, db: AsyncSession) -> set[str]:
    """Get all client IDs a user has read access to (direct grants + descendants)."""
    from models.associations import ClientUserAccess
    result = await db.execute(
        select(ClientUserAccess.client_id).where(ClientUserAccess.user_id == user_id)
    )
    direct_ids = set(result.scalars().all())
    if not direct_ids:
        return set()
    return await get_descendant_client_ids(db, direct_ids)


@router.get("/{client_id}/access")
async def get_client_access(
    client_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List users with direct access to this client."""
    await require_manage_client_access(current_user, db)

    from models.associations import ClientUserAccess
    result = await db.execute(
        select(ClientUserAccess, User)
        .join(User, ClientUserAccess.user_id == User.id)
        .where(ClientUserAccess.client_id == client_id)
    )
    rows = result.all()
    return [
        {
            "user_id": access.user_id,
            "username": user.username,
            "full_name": user.full_name,
            "email": user.email,
            "profile_photo": user.profile_photo,
            "granted_at": access.granted_at.isoformat() if access.granted_at else None,
        }
        for access, user in rows
    ]


@router.post("/{client_id}/access", status_code=status.HTTP_201_CREATED)
async def grant_client_access(
    client_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Grant a user read access to a client."""
    await require_manage_client_access(current_user, db)

    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    # Verify client exists
    client = await db.execute(select(Client).where(Client.id == client_id))
    if not client.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Client not found")

    # Verify user exists
    user = await db.execute(select(User).where(User.id == user_id))
    if not user.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="User not found")

    # Check if already granted
    from models.associations import ClientUserAccess
    existing = await db.execute(
        select(ClientUserAccess).where(
            ClientUserAccess.client_id == client_id,
            ClientUserAccess.user_id == user_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="User already has access to this client")

    db.add(ClientUserAccess(
        client_id=client_id,
        user_id=user_id,
        granted_by=current_user.id,
    ))
    await db.commit()
    return {"status": "granted"}


@router.delete("/{client_id}/access/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_client_access(
    client_id: str,
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Revoke a user's read access to a client."""
    await require_manage_client_access(current_user, db)

    from models.associations import ClientUserAccess
    from sqlalchemy import delete as sql_delete
    result = await db.execute(
        sql_delete(ClientUserAccess).where(
            ClientUserAccess.client_id == client_id,
            ClientUserAccess.user_id == user_id,
        )
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Access grant not found")

    await db.commit()


# ============ Stats / Trends / Engagement list ============

# Findings in these statuses are considered "closed" for MTTR + counts.
# We don't have a dedicated closed_at column, so we use Finding.updated_at as the
# proxy timestamp for when the closure happened. Subsequent edits to a closed
# finding will skew this slightly upward — acceptable for v1.
CLOSED_FINDING_STATUSES = ("REMEDIATED", "CLOSED")


async def _ensure_client_visible(client_id: str, current_user: User, db: AsyncSession) -> None:
    """404 if the client doesn't exist or the user has no read access to it."""
    exists = await db.execute(select(Client.id).where(Client.id == client_id))
    if exists.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Client not found")
    if current_user.role in (UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD):
        return
    accessible = await get_accessible_client_ids(current_user.id, db)
    if client_id not in accessible:
        raise HTTPException(status_code=404, detail="Client not found")


async def _resolve_client_scope(client_id: str, include_descendants: bool, db: AsyncSession) -> set[str]:
    """Return the set of client IDs to include in a stats query."""
    if not include_descendants:
        return {client_id}
    return await get_descendant_client_ids(db, {client_id})


async def _build_engagement_summaries(client_ids: set[str], db: AsyncSession) -> List[EngagementSummary]:
    """Aggregate per-engagement metrics for the given clients in two queries."""
    from models.finding import Finding, Severity, FindingStatus

    if not client_ids:
        return []

    eng_result = await db.execute(
        select(Engagement)
        .where(Engagement.client_id.in_(client_ids))
        .order_by(Engagement.start_date.asc().nullslast(), Engagement.created_at.asc())
    )
    engagements = eng_result.scalars().all()
    if not engagements:
        return []

    eng_ids = [e.id for e in engagements]

    # One query: (engagement_id, severity, status, count) — covers severity, status, totals
    rows = await db.execute(
        select(
            Finding.engagement_id,
            Finding.severity,
            Finding.status,
            func.count(Finding.id),
        )
        .where(Finding.engagement_id.in_(eng_ids))
        .group_by(Finding.engagement_id, Finding.severity, Finding.status)
    )

    by_eng: Dict[str, Dict] = {
        eid: {
            "by_severity": {s.value: 0 for s in Severity},
            "by_status": {s.value: 0 for s in FindingStatus},
            "open": 0,
            "closed": 0,
            "total": 0,
        }
        for eid in eng_ids
    }
    for eng_id, sev, st, cnt in rows.all():
        bucket = by_eng[eng_id]
        sev_v = sev.value if hasattr(sev, "value") else str(sev)
        st_v = st.value if hasattr(st, "value") else str(st)
        bucket["by_severity"][sev_v] = bucket["by_severity"].get(sev_v, 0) + cnt
        bucket["by_status"][st_v] = bucket["by_status"].get(st_v, 0) + cnt
        bucket["total"] += cnt
        if st_v in CLOSED_FINDING_STATUSES:
            bucket["closed"] += cnt
        else:
            bucket["open"] += cnt

    # Second query: average MTTR (in days) per engagement, only for closed findings
    mttr_rows = await db.execute(
        select(
            Finding.engagement_id,
            func.avg(
                func.extract("epoch", Finding.updated_at - Finding.created_at) / 86400.0
            ),
        )
        .where(
            Finding.engagement_id.in_(eng_ids),
            Finding.status.in_(CLOSED_FINDING_STATUSES),
        )
        .group_by(Finding.engagement_id)
    )
    mttr_by_eng = {eid: (float(avg) if avg is not None else None) for eid, avg in mttr_rows.all()}

    summaries: List[EngagementSummary] = []
    for e in engagements:
        b = by_eng[e.id]
        summaries.append(EngagementSummary(
            id=e.id,
            name=e.name,
            status=e.status.value if hasattr(e.status, "value") else str(e.status),
            engagement_type=e.engagement_type,
            client_id=e.client_id,
            client_name=e.client_name,
            start_date=e.start_date,
            end_date=e.end_date,
            finding_count=b["total"],
            findings_by_severity=b["by_severity"],
            findings_by_status=b["by_status"],
            open_findings=b["open"],
            closed_findings=b["closed"],
            mttr_days=mttr_by_eng.get(e.id),
        ))
    return summaries


@router.get("/{client_id}/stats", response_model=ClientStatsResponse)
async def get_client_stats(
    client_id: str,
    include_descendants: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Aggregate KPIs for a client. Defaults to rolling up descendants — pass
    include_descendants=false to scope to the single client only."""
    await _ensure_client_visible(client_id, current_user, db)

    scope = await _resolve_client_scope(client_id, include_descendants, db)
    summaries = await _build_engagement_summaries(scope, db)

    if not summaries:
        return ClientStatsResponse(client_id=client_id, include_descendants=include_descendants)

    eng_status_counts: Dict[str, int] = {}
    sev_totals: Dict[str, int] = {}
    status_totals: Dict[str, int] = {}
    open_total = 0
    closed_total = 0
    finding_total = 0

    for s in summaries:
        eng_status_counts[s.status] = eng_status_counts.get(s.status, 0) + 1
        for k, v in s.findings_by_severity.items():
            sev_totals[k] = sev_totals.get(k, 0) + v
        for k, v in s.findings_by_status.items():
            status_totals[k] = status_totals.get(k, 0) + v
        open_total += s.open_findings
        closed_total += s.closed_findings
        finding_total += s.finding_count

    # Aggregate MTTR weighted by closed-finding count per engagement
    weighted_total = 0.0
    weight = 0
    for s in summaries:
        if s.mttr_days is not None and s.closed_findings > 0:
            weighted_total += s.mttr_days * s.closed_findings
            weight += s.closed_findings
    overall_mttr = (weighted_total / weight) if weight else None

    start_dates = [s.start_date for s in summaries if s.start_date]
    return ClientStatsResponse(
        client_id=client_id,
        include_descendants=include_descendants,
        engagement_count=len(summaries),
        engagements_by_status=eng_status_counts,
        finding_count=finding_total,
        findings_by_severity=sev_totals,
        findings_by_status=status_totals,
        open_findings=open_total,
        closed_findings=closed_total,
        mttr_days=overall_mttr,
        first_engagement_at=min(start_dates) if start_dates else None,
        last_engagement_at=max(start_dates) if start_dates else None,
    )


@router.get("/{client_id}/engagements", response_model=List[EngagementSummary])
async def get_client_engagements(
    client_id: str,
    include_descendants: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Per-engagement summaries for a client. Defaults to rolling up descendants
    so a parent client shows the union across the whole subtree."""
    # GHSA-fj3c-4c5j-cq87: previous check failed open on empty grant set
    # (set() is falsy → short-circuit skipped the 404).
    await _ensure_client_visible(client_id, current_user, db)

    scope = await _resolve_client_scope(client_id, include_descendants, db)
    return await _build_engagement_summaries(scope, db)

