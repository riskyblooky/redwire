from fastapi import APIRouter, Depends, HTTPException, status, Query, Form, File, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from typing import List, Optional
from datetime import datetime
import uuid
import os
import io

from database import get_db
from auth.dependencies import get_current_user
from auth.permissions import require_global_permission
from models.user import User, UserRole
from models.permission import Permission
from models.infra_item import InfraItem, InfraType, InfraStatus
from models.infra_vault_item import InfraVaultItem
from models.finding import Finding
from models.testcase import TestCase
from models.note import Note
from models.associations import InfraItemFinding, InfraItemTestCase, InfraItemNote, InfraVaultAccess
from schemas.infra import (
    InfraItemCreate, InfraItemUpdate, InfraItemResponse, InfraItemDetail,
    InfraLinkRequest, LinkedEntitySummary,
)
from schemas.infra_vault import (
    InfraVaultItemCreate, InfraVaultItemUpdate, InfraVaultItemResponse,
    InfraVaultAccessResponse,
)
from utils.vault_crypto import encrypt_vault_fields, decrypt_vault_item
from utils.storage import storage_service

router = APIRouter(prefix="/infra", tags=["infrastructure"])


# ── Helpers ──────────────────────────────────────────────────────

async def _check_vault_access(
    infra_item_id: str,
    current_user: User,
    db: AsyncSession,
    require_manage: bool = False,
):
    """Check that current_user can access the vault for this infra item.

    Admins/Team Leads always pass.  Otherwise, user needs:
      - INFRA_VAULT_VIEW (or INFRA_VAULT_MANAGE) global permission, AND
      - an entry in infra_vault_access for this item.

    If require_manage is True, INFRA_VAULT_MANAGE is required instead.
    """
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if is_admin:
        return

    perm = Permission.INFRA_VAULT_MANAGE if require_manage else Permission.INFRA_VAULT_VIEW
    await require_global_permission(perm, current_user, db)

    # Check per-item ACL
    result = await db.execute(
        select(InfraVaultAccess).where(
            InfraVaultAccess.infra_item_id == infra_item_id,
            InfraVaultAccess.user_id == current_user.id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this infrastructure item's vault. Ask an admin to grant access.",
        )


# ── Infra Items ──────────────────────────────────────────────────

@router.get("/items", response_model=dict)
async def list_infra_items(
    search: Optional[str] = Query(None),
    infra_type: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List infra items with optional filters."""
    await require_global_permission(Permission.INFRA_VIEW, current_user, db)

    query = select(InfraItem)
    count_query = select(func.count(InfraItem.id))

    if search:
        search_filter = or_(
            InfraItem.name.ilike(f"%{search}%"),
            InfraItem.ip_address.ilike(f"%{search}%"),
            InfraItem.hostname.ilike(f"%{search}%"),
            InfraItem.provider.ilike(f"%{search}%"),
            InfraItem.point_of_presence.ilike(f"%{search}%"),
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    if infra_type:
        query = query.where(InfraItem.infra_type == infra_type)
        count_query = count_query.where(InfraItem.infra_type == infra_type)

    if status_filter:
        query = query.where(InfraItem.status == status_filter)
        count_query = count_query.where(InfraItem.status == status_filter)

    total = (await db.execute(count_query)).scalar() or 0
    result = await db.execute(
        query.order_by(InfraItem.created_at.desc()).offset(offset).limit(limit)
    )
    items = result.scalars().all()

    return {
        "items": [InfraItemResponse.model_validate(item) for item in items],
        "total": total,
    }


@router.post("/items", response_model=InfraItemResponse, status_code=status.HTTP_201_CREATED)
async def create_infra_item(
    data: InfraItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new infra item."""
    await require_global_permission(Permission.INFRA_CREATE, current_user, db)

    item = InfraItem(
        **data.model_dump(),
        created_by=current_user.id,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.get("/items/{item_id}", response_model=InfraItemDetail)
async def get_infra_item(
    item_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single infra item with linked entities."""
    await require_global_permission(Permission.INFRA_VIEW, current_user, db)
    result = await db.execute(
        select(InfraItem)
        .options(
            selectinload(InfraItem.findings),
            selectinload(InfraItem.testcases),
            selectinload(InfraItem.notes_rel),
        )
        .where(InfraItem.id == item_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Infra item not found")

    detail = InfraItemDetail.model_validate(item)
    detail.linked_findings = [
        LinkedEntitySummary(id=f.id, title=f.title, type="finding")
        for f in item.findings
    ]
    detail.linked_testcases = [
        LinkedEntitySummary(id=tc.id, title=tc.title, type="testcase")
        for tc in item.testcases
    ]
    detail.linked_notes = [
        LinkedEntitySummary(id=n.id, title=n.title, type="note")
        for n in item.notes_rel
    ]
    detail.linked_count = len(detail.linked_findings) + len(detail.linked_testcases) + len(detail.linked_notes)
    return detail


@router.put("/items/{item_id}", response_model=InfraItemResponse)
async def update_infra_item(
    item_id: str,
    data: InfraItemUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update an infra item."""
    await require_global_permission(Permission.INFRA_EDIT, current_user, db)
    result = await db.execute(select(InfraItem).where(InfraItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Infra item not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    item.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_infra_item(
    item_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete an infra item."""
    await require_global_permission(Permission.INFRA_DELETE, current_user, db)
    result = await db.execute(select(InfraItem).where(InfraItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Infra item not found")
    await db.delete(item)
    await db.commit()


# ── Linking ──────────────────────────────────────────────────────

@router.post("/items/{item_id}/link", status_code=status.HTTP_201_CREATED)
async def link_infra_item(
    item_id: str,
    data: InfraLinkRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Link an infra item to a finding, testcase, or note."""
    await require_global_permission(Permission.INFRA_EDIT, current_user, db)

    # Verify item exists
    result = await db.execute(select(InfraItem).where(InfraItem.id == item_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Infra item not found")

    if data.entity_type == "finding":
        link = InfraItemFinding(infra_item_id=item_id, finding_id=data.entity_id)
    elif data.entity_type == "testcase":
        link = InfraItemTestCase(infra_item_id=item_id, testcase_id=data.entity_id)
    elif data.entity_type == "note":
        link = InfraItemNote(infra_item_id=item_id, note_id=data.entity_id)
    else:
        raise HTTPException(status_code=400, detail="Invalid entity_type")

    db.add(link)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Link already exists")

    return {"status": "linked"}


@router.delete("/items/{item_id}/link")
async def unlink_infra_item(
    item_id: str,
    data: InfraLinkRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Unlink an infra item from a finding, testcase, or note."""
    await require_global_permission(Permission.INFRA_EDIT, current_user, db)

    if data.entity_type == "finding":
        result = await db.execute(
            select(InfraItemFinding).where(
                InfraItemFinding.infra_item_id == item_id,
                InfraItemFinding.finding_id == data.entity_id,
            )
        )
    elif data.entity_type == "testcase":
        result = await db.execute(
            select(InfraItemTestCase).where(
                InfraItemTestCase.infra_item_id == item_id,
                InfraItemTestCase.testcase_id == data.entity_id,
            )
        )
    elif data.entity_type == "note":
        result = await db.execute(
            select(InfraItemNote).where(
                InfraItemNote.infra_item_id == item_id,
                InfraItemNote.note_id == data.entity_id,
            )
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid entity_type")

    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")

    await db.delete(link)
    await db.commit()
    return {"status": "unlinked"}


# ── By Entity ────────────────────────────────────────────────────

@router.get("/by-entity", response_model=List[InfraItemResponse])
async def get_infra_by_entity(
    entity_type: str = Query(...),
    entity_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get infra items linked to a specific entity."""
    await require_global_permission(Permission.INFRA_VIEW, current_user, db)

    if entity_type == "finding":
        query = (
            select(InfraItem)
            .join(InfraItemFinding, InfraItemFinding.infra_item_id == InfraItem.id)
            .where(InfraItemFinding.finding_id == entity_id)
        )
    elif entity_type == "testcase":
        query = (
            select(InfraItem)
            .join(InfraItemTestCase, InfraItemTestCase.infra_item_id == InfraItem.id)
            .where(InfraItemTestCase.testcase_id == entity_id)
        )
    elif entity_type == "note":
        query = (
            select(InfraItem)
            .join(InfraItemNote, InfraItemNote.infra_item_id == InfraItem.id)
            .where(InfraItemNote.note_id == entity_id)
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid entity_type")

    result = await db.execute(query.order_by(InfraItem.created_at.desc()))
    items = result.scalars().all()
    return [InfraItemResponse.model_validate(item) for item in items]


# ══════════════════════════════════════════════════════════════════
# Infra Vault — Per-item credential storage
# ══════════════════════════════════════════════════════════════════

@router.get("/items/{item_id}/vault", response_model=List[InfraVaultItemResponse])
async def list_infra_vault(
    item_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List vault items for an infrastructure item."""
    await _check_vault_access(item_id, current_user, db)

    result = await db.execute(
        select(InfraVaultItem)
        .where(InfraVaultItem.infra_item_id == item_id)
        .order_by(InfraVaultItem.created_at.desc())
    )
    items = result.scalars().all()

    responses = []
    for vi in items:
        decrypt_vault_item(vi)
        resp = InfraVaultItemResponse.model_validate(vi)
        if vi.created_by:
            user = await db.get(User, vi.created_by)
            if user:
                resp.created_by_username = user.username
        responses.append(resp)

    return responses


@router.post("/items/{item_id}/vault", response_model=InfraVaultItemResponse, status_code=status.HTTP_201_CREATED)
async def create_infra_vault_item(
    item_id: str,
    data: InfraVaultItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new vault item (credential, key, note) for an infra item."""
    await _check_vault_access(item_id, current_user, db, require_manage=True)

    infra = await db.get(InfraItem, item_id)
    if not infra:
        raise HTTPException(status_code=404, detail="Infra item not found")

    encrypted = encrypt_vault_fields(data.model_dump())
    db_item = InfraVaultItem(
        infra_item_id=item_id,
        **encrypted,
        created_by=current_user.id,
    )
    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)

    decrypt_vault_item(db_item)
    return db_item


# ── Fixed-path routes MUST come before {vault_id} routes ─────────

@router.post("/items/{item_id}/vault/upload", response_model=InfraVaultItemResponse, status_code=status.HTTP_201_CREATED)
async def upload_infra_vault_file(
    item_id: str,
    name: str = Form(...),
    description: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload a sensitive file to an infra item's vault."""
    await _check_vault_access(item_id, current_user, db, require_manage=True)

    infra = await db.get(InfraItem, item_id)
    if not infra:
        raise HTTPException(status_code=404, detail="Infra item not found")

    content = await file.read()
    file_ext = os.path.splitext(file.filename)[1] if file.filename else ""
    storage_key = f"infra-vault/{uuid.uuid4()}{file_ext}"
    await storage_service.upload_file(content, storage_key, content_type=file.content_type)

    db_item = InfraVaultItem(
        infra_item_id=item_id,
        name=name,
        item_type="FILE",
        filename=file.filename,
        file_path=storage_key,
        description=description,
        created_by=current_user.id,
    )
    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)
    return db_item


@router.get("/items/{item_id}/vault/access", response_model=List[InfraVaultAccessResponse])
async def list_vault_access(
    item_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List users who have access to this infra item's vault."""
    await _check_vault_access(item_id, current_user, db, require_manage=True)

    result = await db.execute(
        select(InfraVaultAccess).where(InfraVaultAccess.infra_item_id == item_id)
    )
    grants = result.scalars().all()

    responses = []
    for g in grants:
        user = await db.get(User, g.user_id)
        if user:
            responses.append(InfraVaultAccessResponse(
                user_id=g.user_id,
                username=user.username,
                display_name=user.display_name,
                profile_photo=user.profile_photo,
                granted_by=g.granted_by,
                granted_at=g.granted_at,
            ))
    return responses


@router.post("/items/{item_id}/vault/access", status_code=status.HTTP_201_CREATED)
async def grant_vault_access(
    item_id: str,
    user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Grant a user access to this infra item's vault."""
    await _check_vault_access(item_id, current_user, db, require_manage=True)

    target_user = await db.get(User, user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    existing = await db.execute(
        select(InfraVaultAccess).where(
            InfraVaultAccess.infra_item_id == item_id,
            InfraVaultAccess.user_id == user_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Access already granted")

    grant = InfraVaultAccess(
        infra_item_id=item_id,
        user_id=user_id,
        granted_by=current_user.id,
    )
    db.add(grant)
    await db.commit()
    return {"status": "granted", "user_id": user_id}


@router.get("/items/{item_id}/vault/check-access")
async def check_vault_access(
    item_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Check if the current user has vault access to this infra item."""
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if is_admin:
        return {"has_access": True, "can_manage": True}

    result = await db.execute(
        select(InfraVaultAccess).where(
            InfraVaultAccess.infra_item_id == item_id,
            InfraVaultAccess.user_id == current_user.id,
        )
    )
    has_access = result.scalar_one_or_none() is not None
    return {"has_access": has_access, "can_manage": has_access}


@router.delete("/items/{item_id}/vault/access/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_vault_access(
    item_id: str,
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Revoke a user's access to this infra item's vault."""
    await _check_vault_access(item_id, current_user, db, require_manage=True)

    result = await db.execute(
        select(InfraVaultAccess).where(
            InfraVaultAccess.infra_item_id == item_id,
            InfraVaultAccess.user_id == user_id,
        )
    )
    grant = result.scalar_one_or_none()
    if not grant:
        raise HTTPException(status_code=404, detail="Access grant not found")

    await db.delete(grant)
    await db.commit()


# ── Parameterized {vault_id} routes ──────────────────────────────

@router.put("/items/{item_id}/vault/{vault_id}", response_model=InfraVaultItemResponse)
async def update_infra_vault_item(
    item_id: str,
    vault_id: str,
    data: InfraVaultItemUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a vault item."""
    await _check_vault_access(item_id, current_user, db, require_manage=True)

    result = await db.execute(
        select(InfraVaultItem).where(
            InfraVaultItem.id == vault_id,
            InfraVaultItem.infra_item_id == item_id,
        )
    )
    vi = result.scalar_one_or_none()
    if not vi:
        raise HTTPException(status_code=404, detail="Vault item not found")

    updates = data.model_dump(exclude_unset=True)
    encrypted = encrypt_vault_fields(updates)
    for field, value in encrypted.items():
        setattr(vi, field, value)
    vi.updated_by = current_user.id
    vi.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(vi)

    decrypt_vault_item(vi)
    return vi


@router.delete("/items/{item_id}/vault/{vault_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_infra_vault_item(
    item_id: str,
    vault_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a vault item. Also removes file from MinIO if it's a file type."""
    await _check_vault_access(item_id, current_user, db, require_manage=True)

    result = await db.execute(
        select(InfraVaultItem).where(
            InfraVaultItem.id == vault_id,
            InfraVaultItem.infra_item_id == item_id,
        )
    )
    vi = result.scalar_one_or_none()
    if not vi:
        raise HTTPException(status_code=404, detail="Vault item not found")

    if vi.file_path:
        try:
            await storage_service.delete_file(vi.file_path)
        except Exception:
            pass

    await db.delete(vi)
    await db.commit()


@router.get("/items/{item_id}/vault/{vault_id}/download")
async def download_infra_vault_file(
    item_id: str,
    vault_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Download a file from the infra vault."""
    await _check_vault_access(item_id, current_user, db)

    result = await db.execute(
        select(InfraVaultItem).where(
            InfraVaultItem.id == vault_id,
            InfraVaultItem.infra_item_id == item_id,
        )
    )
    vi = result.scalar_one_or_none()
    if not vi or vi.item_type != "FILE" or not vi.file_path:
        raise HTTPException(status_code=404, detail="File not found")

    file_data = await storage_service.download_file(vi.file_path)
    return StreamingResponse(
        io.BytesIO(file_data),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{vi.filename or "file"}"'},
    )


