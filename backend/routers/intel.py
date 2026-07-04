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
from utils.uploads import sanitize_original_filename
from utils.ssrf import validate_outbound_url, validate_outbound_url_sync, OutboundURLError

import logging
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
    query = base_query.order_by(order).offset(offset).limit(limit)

    result = await db.execute(query)
    items = result.scalars().all()

    # Compute linked counts
    responses = []
    for item in items:
        count_result = await db.execute(
            select(func.count()).select_from(IntelItemFinding).where(IntelItemFinding.intel_item_id == item.id)
        )
        finding_count = count_result.scalar() or 0
        count_result = await db.execute(
            select(func.count()).select_from(IntelItemTestCase).where(IntelItemTestCase.intel_item_id == item.id)
        )
        tc_count = count_result.scalar() or 0
        count_result = await db.execute(
            select(func.count()).select_from(IntelItemNote).where(IntelItemNote.intel_item_id == item.id)
        )
        note_count = count_result.scalar() or 0

        resp = IntelItemResponse.model_validate(item)
        resp.linked_count = finding_count + tc_count + note_count
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

    detail = IntelItemDetail.model_validate(item)
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
        for n in item.notes
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

@router.post("/items/{item_id}/link", status_code=status.HTTP_201_CREATED)
async def link_intel_item(
    item_id: str,
    data: IntelLinkRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Link an intel item to a finding, testcase, or note."""
    from auth.rbac import check_engagement_permission
    await require_global_permission(Permission.INTEL_EDIT, current_user, db)
    # Verify item exists
    result = await db.execute(select(IntelItem).where(IntelItem.id == item_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Intel item not found")

    # IntelItem is global (no engagement_id), so per-link the caller must have
    # at least view permission on the target entity's engagement. Admins bypass.
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.TEAM_LEAD]

    async def _require_view(eng_id: str, perm: Permission, label: str):
        if is_admin:
            return
        if not await check_engagement_permission(current_user.id, eng_id, perm.value, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions on this {label}'s engagement.",
            )

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
        content = await file.read()
        storage_key = f"intel/{item_id}/{_uuid.uuid4()}_{file.filename}"
        content_type = file.content_type or "application/octet-stream"

        await storage_service.upload_file(content, storage_key, content_type)

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

    try:
        await storage_service.delete_file(attachment.filename)
    except Exception as e:
        print(f"Failed to delete file from storage: {e}")

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
    import httpx
    import defusedxml.ElementTree as ET
    import json
    import uuid

    result = await db.execute(select(IntelFeed).where(IntelFeed.enabled == True))
    feeds = result.scalars().all()

    total_new = 0

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
        for feed in feeds:
            try:
                # SSRF guard (GHSA-f33c-g6w5-6xm6): re-validate at fetch time and
                # don't follow redirects, so a stored feed URL can't reach
                # internal services or 302 to them.
                try:
                    await validate_outbound_url(feed.url)
                except OutboundURLError as exc:
                    logger.warning("Skipping intel feed %r: %s", feed.url, exc)
                    continue
                resp = await client.get(feed.url, headers={"User-Agent": "RedWire/1.0"})
                if resp.status_code != 200:
                    continue

                entries = []

                if feed.feed_type == "JSON":
                    data = resp.json()
                    # Handle CISA KEV format
                    vulns = data.get("vulnerabilities", data if isinstance(data, list) else [])
                    for v in vulns[:30]:  # Limit
                        entries.append({
                            "title": v.get("vulnerabilityName") or v.get("cveID", "Unknown"),
                            "content": v.get("shortDescription", ""),
                            "source_url": f"https://nvd.nist.gov/vuln/detail/{v.get('cveID', '')}",
                            "cve_id": v.get("cveID"),
                            "item_type": "CVE",
                            "severity": "HIGH" if v.get("knownRansomwareCampaignUse") == "Known" else None,
                            "published_at": _parse_date(v.get("dateAdded")),
                        })
                else:
                    # RSS / Atom
                    try:
                        root = ET.fromstring(resp.text)
                    except ET.ParseError:
                        continue

                    # Try RSS 2.0 format
                    items_el = root.findall(".//item")
                    if not items_el:
                        # Try Atom format
                        ns = {"atom": "http://www.w3.org/2005/Atom"}
                        items_el = root.findall(".//atom:entry", ns)

                    for el in items_el[:30]:
                        title = _get_text(el, "title") or _get_text(el, "{http://www.w3.org/2005/Atom}title") or "Untitled"
                        link = _get_text(el, "link") or ""
                        if not link:
                            link_el = el.find("{http://www.w3.org/2005/Atom}link")
                            if link_el is not None:
                                link = link_el.get("href", "")
                        desc = _get_text(el, "description") or _get_text(el, "{http://www.w3.org/2005/Atom}summary") or ""
                        pub_date = _get_text(el, "pubDate") or _get_text(el, "{http://www.w3.org/2005/Atom}updated") or ""

                        # Detect CVE in title
                        cve_id = None
                        import re
                        cve_match = re.search(r"CVE-\d{4}-\d+", title)
                        if cve_match:
                            cve_id = cve_match.group(0)

                        item_type = "CVE" if cve_id else "ARTICLE"
                        if any(kw in title.lower() for kw in ["advisory", "alert", "bulletin"]):
                            item_type = "ADVISORY"
                        elif any(kw in title.lower() for kw in ["exploit", "poc", "proof of concept"]):
                            item_type = "EXPLOIT"

                        entries.append({
                            "title": title[:500],
                            "content": _strip_html(desc)[:2000] if desc else None,
                            "source_url": link,
                            "cve_id": cve_id,
                            "item_type": item_type,
                            "published_at": _parse_rss_date(pub_date),
                        })

                # Insert new entries (skip duplicates by source_url)
                for entry in entries:
                    if entry.get("source_url"):
                        existing = await db.execute(
                            select(IntelItem).where(
                                IntelItem.source_url == entry["source_url"],
                                IntelItem.feed_id == feed.id,
                            )
                        )
                        if existing.scalar_one_or_none():
                            continue

                    item = IntelItem(
                        id=str(uuid.uuid4()),
                        title=entry["title"],
                        content=entry.get("content"),
                        source=feed.name,
                        source_url=entry.get("source_url"),
                        item_type=entry.get("item_type", "OTHER"),
                        severity=entry.get("severity"),
                        cve_id=entry.get("cve_id"),
                        published_at=entry.get("published_at"),
                        feed_id=feed.id,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                    )
                    db.add(item)
                    total_new += 1

                feed.last_fetched_at = datetime.utcnow()
            except Exception as e:
                print(f"Error fetching feed {feed.name}: {e}")
                continue

    await db.commit()
    return {"status": "ok", "new_items": total_new, "feeds_processed": len(feeds)}


# ── Helpers ──────────────────────────────────────────────────────

def _get_text(element, tag):
    """Get text content from an XML element."""
    el = element.find(tag)
    if el is not None and el.text:
        return el.text.strip()
    return None


def _strip_html(text):
    """Remove HTML tags from text."""
    import re
    return re.sub(r'<[^>]+>', '', text)


def _parse_date(date_str):
    """Parse a date string loosely."""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def _parse_rss_date(date_str):
    """Parse RSS date formats."""
    if not date_str:
        return None
    from email.utils import parsedate_to_datetime
    try:
        return parsedate_to_datetime(date_str).replace(tzinfo=None)
    except Exception:
        return _parse_date(date_str)
