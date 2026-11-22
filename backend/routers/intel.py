from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File as FastAPIFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from typing import List, Optional
from datetime import datetime

from database import get_db
from auth.dependencies import get_current_user
from auth.permissions import require_global_permission
from models.user import User, UserRole
from models.permission import Permission
from models.intel_item import IntelItem, IntelItemType, IntelSeverity
from models.intel_attachment import IntelAttachment
from models.intel_feed import IntelFeed
from models.finding import Finding
from models.testcase import TestCase
from models.note import Note
from models.associations import IntelItemFinding, IntelItemTestCase, IntelItemNote
from schemas.intel import (
    IntelItemCreate, IntelItemUpdate, IntelItemResponse, IntelItemDetail,
    IntelFeedCreate, IntelFeedResponse,
    IntelLinkRequest, LinkedEntitySummary, IntelAttachmentResponse,
)
from utils.storage import storage_service
from utils.uploads import (
    MAX_INTEL_ATTACHMENT_BYTES,
    read_upload_capped,
    sanitize_original_filename,
)
from utils.ssrf import validate_outbound_url, validate_outbound_url_sync, OutboundURLError

import logging
from utils import storage_tx
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/intel", tags=["intelligence"])


# ── Intel Items CRUD ─────────────────────────────────────────────

@router.get("/items")
async def list_intel_items(
    search: Optional[str] = None,
    item_type: Optional[str] = None,
    severity: Optional[str] = None,
    sort_by: str = Query("created_at", regex="^(title|created_at|published_at|item_type|severity|source)$"),
    sort_dir: str = Query("desc", regex="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List intel items with server-side search, filtering, sorting, and pagination."""
    await require_global_permission(Permission.INTEL_VIEW, current_user, db)
    # Base filter
    base_query = select(IntelItem)
    if search:
        base_query = base_query.where(
            or_(
                IntelItem.title.ilike(f"%{search}%"),
                IntelItem.cve_id.ilike(f"%{search}%"),
                IntelItem.content.ilike(f"%{search}%"),
            )
        )
    if item_type:
        base_query = base_query.where(IntelItem.item_type == item_type)
    if severity:
        base_query = base_query.where(IntelItem.severity == severity)

    # Total count (before limit/offset)
    count_q = select(func.count()).select_from(base_query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Sorting
    sort_column = getattr(IntelItem, sort_by, IntelItem.created_at)
    order = sort_column.asc() if sort_dir == "asc" else sort_column.desc()
    query = base_query.order_by(order, IntelItem.id).offset(offset).limit(limit)

    result = await db.execute(query)
    items = result.scalars().all()

    # Linked counts: one grouped query per link table for the whole page
    # (was three COUNT queries per item).
    ids = [item.id for item in items]
    linked: dict[str, int] = {}
    if ids:
        for model in (IntelItemFinding, IntelItemTestCase, IntelItemNote):
            rows = await db.execute(
                select(model.intel_item_id, func.count()).where(model.intel_item_id.in_(ids))
                .group_by(model.intel_item_id)
            )
            for item_id, n in rows.all():
                linked[item_id] = linked.get(item_id, 0) + n
    responses = []
    for item in items:
        resp = IntelItemResponse.model_validate(item)
        resp.linked_count = linked.get(item.id, 0)
        responses.append(resp)

    return {"items": responses, "total": total, "limit": limit, "offset": offset}


@router.post("/items", response_model=IntelItemResponse, status_code=status.HTTP_201_CREATED)
async def create_intel_item(
    data: IntelItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a manual intel item."""
    await require_global_permission(Permission.INTEL_CREATE, current_user, db)
    item_data = data.model_dump()
    # Strip timezone from published_at
    if item_data.get("published_at") and hasattr(item_data["published_at"], "tzinfo") and item_data["published_at"].tzinfo:
        item_data["published_at"] = item_data["published_at"].replace(tzinfo=None)

    item = IntelItem(**item_data, created_by=current_user.id)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def _can_view_linked(current_user: User, eng_id: str, perm: Permission, db: AsyncSession) -> bool:
    """Intel items are global but what they link to isn't: a linked finding /
    test case / note is only shown (or unlinkable) for callers who can view
    it in its engagement."""
    from auth.rbac import check_engagement_permission
    if current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]:
        return True
    return await check_engagement_permission(current_user.id, eng_id, perm.value, db)


@router.get("/items/{item_id}", response_model=IntelItemDetail)
async def get_intel_item(
    item_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single intel item with linked entities."""
    await require_global_permission(Permission.INTEL_VIEW, current_user, db)
    result = await db.execute(
        select(IntelItem)
        .options(
            selectinload(IntelItem.findings),
            selectinload(IntelItem.testcases),
            selectinload(IntelItem.notes),
            selectinload(IntelItem.attachments),
        )
        .where(IntelItem.id == item_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Intel item not found")

    seen: dict = {}

    async def visible(entities, perm: Permission):
        out = []
        for e in entities:
            key = (e.engagement_id, perm)
            if key not in seen:
                seen[key] = await _can_view_linked(current_user, e.engagement_id, perm, db)
            if seen[key]:
                out.append(e)
        return out

    detail = IntelItemDetail.model_validate(item)
    detail.linked_findings = [
        LinkedEntitySummary(id=f.id, title=f.title, type="finding")
        for f in await visible(item.findings, Permission.FINDING_VIEW)
    ]
    detail.linked_testcases = [
        LinkedEntitySummary(id=tc.id, title=tc.title, type="testcase")
        for tc in await visible(item.testcases, Permission.TESTCASE_VIEW)
    ]
    detail.linked_notes = [
        LinkedEntitySummary(id=n.id, title=n.title, type="note")
        for n in await visible(item.notes, Permission.NOTE_VIEW)
    ]
    detail.linked_count = len(detail.linked_findings) + len(detail.linked_testcases) + len(detail.linked_notes)
    detail.attachments = [
        IntelAttachmentResponse.model_validate(att) for att in item.attachments
    ]
    return detail


@router.put("/items/{item_id}", response_model=IntelItemResponse)
async def update_intel_item(
    item_id: str,
    data: IntelItemUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update an intel item."""
    await require_global_permission(Permission.INTEL_EDIT, current_user, db)
    result = await db.execute(select(IntelItem).where(IntelItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Intel item not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(item, field, value)

    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_intel_item(
    item_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete an intel item."""
    await require_global_permission(Permission.INTEL_DELETE, current_user, db)
    result = await db.execute(select(IntelItem).where(IntelItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Intel item not found")
    await db.delete(item)
    await db.commit()


# ── Linking ──────────────────────────────────────────────────────

def _require_linked_view(current_user: User, db: AsyncSession):
    async def _require_view(eng_id: str, perm: Permission, label: str):
        if not await _can_view_linked(current_user, eng_id, perm, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions on this {label}'s engagement.",
            )
    return _require_view


@router.post("/items/{item_id}/link", status_code=status.HTTP_201_CREATED)
async def link_intel_item(
    item_id: str,
    data: IntelLinkRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Link an intel item to a finding, testcase, or note."""
    await require_global_permission(Permission.INTEL_EDIT, current_user, db)
    # Verify item exists
    result = await db.execute(select(IntelItem).where(IntelItem.id == item_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Intel item not found")

    # IntelItem is global (no engagement_id), so per-link the caller must have
    # at least view permission on the target entity's engagement.
    _require_view = _require_linked_view(current_user, db)

    if data.entity_type == "finding":
        finding = (await db.execute(select(Finding).where(Finding.id == data.entity_id))).scalar_one_or_none()
        if not finding:
            raise HTTPException(status_code=404, detail="Finding not found")
        await _require_view(finding.engagement_id, Permission.FINDING_VIEW, "finding")
        existing = await db.execute(
            select(IntelItemFinding).where(
                IntelItemFinding.intel_item_id == item_id,
                IntelItemFinding.finding_id == data.entity_id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Already linked")
        db.add(IntelItemFinding(intel_item_id=item_id, finding_id=data.entity_id))
    elif data.entity_type == "testcase":
        tc = (await db.execute(select(TestCase).where(TestCase.id == data.entity_id))).scalar_one_or_none()
        if not tc:
            raise HTTPException(status_code=404, detail="Test case not found")
        await _require_view(tc.engagement_id, Permission.TESTCASE_VIEW, "test case")
        existing = await db.execute(
            select(IntelItemTestCase).where(
                IntelItemTestCase.intel_item_id == item_id,
                IntelItemTestCase.testcase_id == data.entity_id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Already linked")
        db.add(IntelItemTestCase(intel_item_id=item_id, testcase_id=data.entity_id))
    elif data.entity_type == "note":
        note = (await db.execute(select(Note).where(Note.id == data.entity_id))).scalar_one_or_none()
        if not note:
            raise HTTPException(status_code=404, detail="Note not found")
        await _require_view(note.engagement_id, Permission.NOTE_VIEW, "note")
        existing = await db.execute(
            select(IntelItemNote).where(
                IntelItemNote.intel_item_id == item_id,
                IntelItemNote.note_id == data.entity_id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Already linked")
        db.add(IntelItemNote(intel_item_id=item_id, note_id=data.entity_id))
    else:
        raise HTTPException(status_code=400, detail="entity_type must be 'finding', 'testcase', or 'note'")

    await db.commit()
    return {"status": "linked"}


@router.delete("/items/{item_id}/link")
async def unlink_intel_item(
    item_id: str,
    data: IntelLinkRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Unlink an intel item from a finding, testcase, or note."""
    await require_global_permission(Permission.INTEL_EDIT, current_user, db)
    # Same engagement check as linking — otherwise anyone with intel_edit
    # could strip links off findings in engagements they can't see.
    model, perm, label = {
        "finding": (Finding, Permission.FINDING_VIEW, "finding"),
        "testcase": (TestCase, Permission.TESTCASE_VIEW, "test case"),
        "note": (Note, Permission.NOTE_VIEW, "note"),
    }.get(data.entity_type, (None, None, None))
    if model is not None:
        entity = await db.get(model, data.entity_id)
        if entity is not None:
            await _require_linked_view(current_user, db)(entity.engagement_id, perm, label)
    if data.entity_type == "finding":
        result = await db.execute(
            select(IntelItemFinding).where(
                IntelItemFinding.intel_item_id == item_id,
                IntelItemFinding.finding_id == data.entity_id,
            )
        )
        link = result.scalar_one_or_none()
    elif data.entity_type == "testcase":
        result = await db.execute(
            select(IntelItemTestCase).where(
                IntelItemTestCase.intel_item_id == item_id,
                IntelItemTestCase.testcase_id == data.entity_id,
            )
        )
        link = result.scalar_one_or_none()
    elif data.entity_type == "note":
        result = await db.execute(
            select(IntelItemNote).where(
                IntelItemNote.intel_item_id == item_id,
                IntelItemNote.note_id == data.entity_id,
            )
        )
        link = result.scalar_one_or_none()
    else:
        raise HTTPException(status_code=400, detail="entity_type must be 'finding', 'testcase', or 'note'")

    if not link:
        raise HTTPException(status_code=404, detail="Link not found")

    await db.delete(link)
    await db.commit()
    return {"status": "unlinked"}


@router.get("/by-entity", response_model=List[IntelItemResponse])
async def get_intel_by_entity(
    entity_type: str = Query(..., regex="^(finding|testcase|note)$"),
    entity_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all intel items linked to a specific finding, testcase, or note."""
    await require_global_permission(Permission.INTEL_VIEW, current_user, db)
    if entity_type == "finding":
        query = (
            select(IntelItem)
            .join(IntelItemFinding, IntelItemFinding.intel_item_id == IntelItem.id)
            .where(IntelItemFinding.finding_id == entity_id)
        )
    elif entity_type == "testcase":
        query = (
            select(IntelItem)
            .join(IntelItemTestCase, IntelItemTestCase.intel_item_id == IntelItem.id)
            .where(IntelItemTestCase.testcase_id == entity_id)
        )
    else:
        query = (
            select(IntelItem)
            .join(IntelItemNote, IntelItemNote.intel_item_id == IntelItem.id)
            .where(IntelItemNote.note_id == entity_id)
        )

    result = await db.execute(query.order_by(IntelItem.created_at.desc()))
    items = result.scalars().all()
    return [IntelItemResponse.model_validate(item) for item in items]



# ── Attachments ──────────────────────────────────────────────────

@router.post("/items/{item_id}/attachments", response_model=List[IntelAttachmentResponse], status_code=status.HTTP_201_CREATED)
async def upload_intel_attachments(
    item_id: str,
    files: List[UploadFile] = FastAPIFile(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload one or more file attachments to an intel item."""
    await require_global_permission(Permission.INTEL_EDIT, current_user, db)

    # Verify item exists
    result = await db.execute(select(IntelItem).where(IntelItem.id == item_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Intel item not found")

    import uuid as _uuid
    created = []
    for file in files:
        content = await read_upload_capped(
            file, MAX_INTEL_ATTACHMENT_BYTES,
            detail=f"Intel attachment exceeds the {MAX_INTEL_ATTACHMENT_BYTES}-byte size limit.",
        )
        storage_key = f"intel/{item_id}/{_uuid.uuid4()}_{file.filename}"
        content_type = file.content_type or "application/octet-stream"

        await storage_tx.upload(db, content, storage_key, content_type)

        attachment = IntelAttachment(
            intel_item_id=item_id,
            filename=storage_key,
            original_filename=sanitize_original_filename(file.filename),
            file_size=len(content),
            mime_type=content_type,
            created_by=current_user.id,
        )
        db.add(attachment)
        created.append(attachment)

    await db.commit()
    for att in created:
        await db.refresh(att)

    return created


@router.get("/items/{item_id}/attachments/{attachment_id}/download")
async def download_intel_attachment(
    item_id: str,
    attachment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a presigned download URL for an intel attachment."""
    await require_global_permission(Permission.INTEL_VIEW, current_user, db)

    result = await db.execute(
        select(IntelAttachment).where(
            IntelAttachment.id == attachment_id,
            IntelAttachment.intel_item_id == item_id,
        )
    )
    attachment = result.scalar_one_or_none()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")

    url = storage_service.get_presigned_url(attachment.filename)
    return {"url": url, "filename": attachment.original_filename}


@router.delete("/items/{item_id}/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_intel_attachment(
    item_id: str,
    attachment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete an intel attachment."""
    await require_global_permission(Permission.INTEL_EDIT, current_user, db)

    result = await db.execute(
        select(IntelAttachment).where(
            IntelAttachment.id == attachment_id,
            IntelAttachment.intel_item_id == item_id,
        )
    )
    attachment = result.scalar_one_or_none()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")

    storage_tx.delete_after_commit(db, attachment.filename)  # once the row is gone
    await db.delete(attachment)
    await db.commit()


# ── Intel Feeds ──────────────────────────────────────────────────

@router.get("/feeds", response_model=List[IntelFeedResponse])
async def list_feeds(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all configured feeds."""
    await require_global_permission(Permission.INTEL_VIEW, current_user, db)
    result = await db.execute(select(IntelFeed).order_by(IntelFeed.name))
    return result.scalars().all()


@router.post("/feeds", response_model=IntelFeedResponse, status_code=status.HTTP_201_CREATED)
async def create_feed(
    data: IntelFeedCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a new RSS/Atom feed."""
    await require_global_permission(Permission.INTEL_MANAGE_FEEDS, current_user, db)

    feed = IntelFeed(**data.model_dump(), created_by=current_user.id)
    db.add(feed)
    await db.commit()
    await db.refresh(feed)
    return feed


@router.put("/feeds/{feed_id}", response_model=IntelFeedResponse)
async def update_feed(
    feed_id: str,
    data: IntelFeedCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a feed."""
    await require_global_permission(Permission.INTEL_MANAGE_FEEDS, current_user, db)

    result = await db.execute(select(IntelFeed).where(IntelFeed.id == feed_id))
    feed = result.scalar_one_or_none()
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")

    for field, value in data.model_dump().items():
        setattr(feed, field, value)
    await db.commit()
    await db.refresh(feed)
    return feed


@router.delete("/feeds/{feed_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_feed(
    feed_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a feed and its items."""
    await require_global_permission(Permission.INTEL_MANAGE_FEEDS, current_user, db)

    result = await db.execute(select(IntelFeed).where(IntelFeed.id == feed_id))
    feed = result.scalar_one_or_none()
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")
    await db.delete(feed)
    await db.commit()


# ── Feed Refresh (RSS fetching) ──────────────────────────────────

@router.post("/feeds/refresh")
async def refresh_feeds(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fetch all enabled feeds and import new items."""
    await require_global_permission(Permission.INTEL_MANAGE_FEEDS, current_user, db)
    from utils.intel_refresh import refresh_enabled_feeds
    total_new, processed = await refresh_enabled_feeds(db)
    return {"status": "ok", "new_items": total_new, "feeds_processed": processed}
