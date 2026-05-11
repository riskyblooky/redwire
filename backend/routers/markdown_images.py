"""Inline markdown image storage.

Two endpoints — upload and fetch — both auth-required and scoped by
engagement. The frontend's tiptap editor calls POST on paste/drop, then
embeds the image as a `/api/markdown-images/{id}` URL.

Permission model: an authenticated caller can upload to any engagement
they have view access to (admins always pass). Fetching the image bytes
re-checks engagement view permission, so a user removed from an
engagement loses access to its markdown images.
"""

import uuid
import os
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User, UserRole
from models.markdown_image import MarkdownImage
from models.engagement import Engagement
from models.permission import Permission
from auth.dependencies import get_current_user
from auth.rbac import check_engagement_permission
from utils.storage import storage_service

router = APIRouter(prefix="/markdown-images", tags=["markdown-images"])


_ALLOWED_TYPES = {
    "image/png", "image/jpeg", "image/gif", "image/webp",
    "image/svg+xml", "image/bmp",
}
_MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
_EXT_FALLBACK = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "image/bmp": ".bmp",
}


async def _check_engagement_view(user: User, engagement_id: str, db: AsyncSession) -> None:
    """Raise 403 unless user has view access to the engagement."""
    if user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]:
        return
    has = await check_engagement_permission(
        user.id, engagement_id, Permission.ENGAGEMENT_VIEW.value, db
    )
    if not has:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this engagement",
        )


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_markdown_image(
    file: UploadFile = File(...),
    engagement_id: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload an image embedded inline in a markdown editor."""
    # Verify engagement exists and caller has view access
    eng_result = await db.execute(select(Engagement).where(Engagement.id == engagement_id))
    if eng_result.scalar_one_or_none() is None:
        raise HTTPException(404, "Engagement not found")
    await _check_engagement_view(current_user, engagement_id, db)

    content_type = (file.content_type or "").lower()
    if content_type not in _ALLOWED_TYPES:
        raise HTTPException(400, f"Unsupported image type: {content_type or 'unknown'}")

    body = await file.read()
    if len(body) == 0:
        raise HTTPException(400, "Empty file")
    if len(body) > _MAX_SIZE_BYTES:
        raise HTTPException(413, f"Image exceeds {_MAX_SIZE_BYTES // (1024 * 1024)} MB limit")

    image_id = str(uuid.uuid4())
    ext = _EXT_FALLBACK.get(content_type, "")
    if not ext and file.filename and "." in file.filename:
        ext = "." + file.filename.rsplit(".", 1)[-1].lower()
    storage_key = f"markdown/{engagement_id}/{image_id}{ext}"

    await storage_service.upload_file(body, storage_key, content_type)

    row = MarkdownImage(
        id=image_id,
        storage_key=storage_key,
        engagement_id=engagement_id,
        created_by=current_user.id,
        content_type=content_type,
        size_bytes=len(body),
        original_filename=file.filename,
    )
    db.add(row)
    await db.commit()

    return {
        "id": image_id,
        "url": f"/api/markdown-images/{image_id}",
        "content_type": content_type,
        "size_bytes": len(body),
    }


@router.get("/{image_id}")
async def get_markdown_image(
    image_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Stream an inline markdown image. Re-checks engagement permission."""
    result = await db.execute(select(MarkdownImage).where(MarkdownImage.id == image_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Image not found")

    await _check_engagement_view(current_user, row.engagement_id, db)

    body = await storage_service.download_file(row.storage_key)
    return StreamingResponse(
        BytesIO(body),
        media_type=row.content_type,
        headers={
            "Cache-Control": "private, max-age=3600",
            "Content-Length": str(len(body)),
        },
    )
