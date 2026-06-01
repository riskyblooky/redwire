from fastapi import APIRouter, Depends, HTTPException, status, Form, Query, UploadFile, File as FastAPIFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from database import get_db
from models.evidence import Evidence
from models.user import User, UserRole
from schemas.evidence import EvidenceResponse
from auth.dependencies import get_current_user
from auth.rbac import check_engagement_permission
from models.permission import Permission
from utils.storage import storage_service
from utils.collaboration import create_activity_log

from models.finding import Finding
from models.testcase import TestCase
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
import io

router = APIRouter(prefix="/evidence", tags=["evidence"])

async def get_evidence_engagement_id(evidence: Evidence, db: AsyncSession) -> Optional[str]:
    """Resolve the engagement ID for an evidence item, checking direct, finding, and testcase links."""
    if evidence.engagement_id:
        return evidence.engagement_id
    if evidence.finding_id:
        result = await db.execute(select(Finding.engagement_id).where(Finding.id == evidence.finding_id))
        return result.scalar_one_or_none()
    if evidence.testcase_id:
        result = await db.execute(select(TestCase.engagement_id).where(TestCase.id == evidence.testcase_id))
        return result.scalar_one_or_none()
    return None

@router.get("/{evidence_id}", response_model=EvidenceResponse)
async def get_evidence(
    evidence_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get evidence metadata."""
    from models.finding import Finding
    from models.testcase import TestCase
    
    result = await db.execute(
        select(Evidence, User.username, Finding.title.label("finding_title"), TestCase.title.label("testcase_title"))
        .outerjoin(User, Evidence.created_by == User.id)
        .outerjoin(Finding, Evidence.finding_id == Finding.id)
        .outerjoin(TestCase, Evidence.testcase_id == TestCase.id)
        .where(Evidence.id == evidence_id)
    )
    row = result.first()
    
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence not found"
        )
    
    evidence, username, finding_title, testcase_title = row
    
    # Authorization Check using RBAC
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    
    if not is_admin:
        eng_id = await get_evidence_engagement_id(evidence, db)
        if eng_id:
            has_permission = await check_engagement_permission(current_user.id, eng_id, Permission.EVIDENCE_VIEW.value, db)
            if not has_permission:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions. You need the 'evidence_view' permission to view evidence."
                )
        else:
            # No engagement linked, restrict to admin
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to system file"
            )
    
    evidence.created_by_username = username
    evidence.finding_title = finding_title
    evidence.testcase_title = testcase_title
    
    return evidence

@router.patch("/{evidence_id}", response_model=EvidenceResponse)
async def update_evidence(
    evidence_id: str,
    update_data: dict, # Using dict for simplicity or create a specific schema
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update evidence metadata."""
    result = await db.execute(select(Evidence).where(Evidence.id == evidence_id))
    evidence = result.scalar_one_or_none()
    
    if not evidence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence not found"
        )
    
    # Check permissions using RBAC with ANY model
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    is_owner = evidence.created_by == current_user.id
    
    if not is_admin:
        eng_id = await get_evidence_engagement_id(evidence, db)
        if eng_id:
            if is_owner:
                # Owner needs base edit permission
                has_permission = await check_engagement_permission(current_user.id, eng_id, Permission.EVIDENCE_EDIT.value, db)
            else:
                # Non-owner needs edit_any permission
                has_permission = await check_engagement_permission(current_user.id, eng_id, Permission.EVIDENCE_EDIT_ANY.value, db)
            
            if not has_permission:
                required_perm = Permission.EVIDENCE_EDIT.value if is_owner else Permission.EVIDENCE_EDIT_ANY.value
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Insufficient permissions. You need the '{required_perm}' permission to modify this evidence."
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions to modify this evidence."
            )
    
    # Build specific change details before applying updates
    change_parts = []
    if "description" in update_data:
        change_parts.append("description")
    if "include_in_report" in update_data:
        old_include = getattr(evidence, "include_in_report", None)
        change_parts.append(f"include in report: {str(old_include).lower()} → {str(update_data['include_in_report']).lower()}")
    change_details = f"Updated evidence '{evidence.original_filename}'"
    if change_parts:
        change_details += f" — {', '.join(change_parts)}"

    if "description" in update_data:
        evidence.description = update_data["description"]
    if "include_in_report" in update_data:
        evidence.include_in_report = update_data["include_in_report"]
        
    evidence.updated_by = current_user.id
    
    await db.commit()
    
    # Reload with username
    result = await db.execute(
        select(Evidence, User.username)
        .outerjoin(User, Evidence.created_by == User.id)
        .where(Evidence.id == evidence.id)
    )
    row = result.first()
    if row:
        evidence, username = row
        evidence.created_by_username = username
    else:
        await db.refresh(evidence)

    # Log activity
    await create_activity_log(
        db,
        engagement_id=evidence.engagement_id or "global", # Fallback if engagement_id somehow null
        user_id=current_user.id,
        action="updated_evidence",
        resource_type="evidence",
        resource_id=evidence.id,
        resource_name=evidence.original_filename,
        details=change_details
    )
    
    await db.commit() # Commit the log
    
    return evidence

@router.delete("/{evidence_id}")
async def delete_evidence(
    evidence_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete evidence."""
    result = await db.execute(select(Evidence).where(Evidence.id == evidence_id))
    evidence = result.scalar_one_or_none()
    
    if not evidence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence not found"
        )
    
    # Check permissions using RBAC with ANY model
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    is_owner = evidence.created_by == current_user.id
    
    if not is_admin:
        eng_id = await get_evidence_engagement_id(evidence, db)
        if eng_id:
            if is_owner:
                # Owner needs base delete permission
                has_permission = await check_engagement_permission(current_user.id, eng_id, Permission.EVIDENCE_DELETE.value, db)
            else:
                # Non-owner needs delete_any permission
                has_permission = await check_engagement_permission(current_user.id, eng_id, Permission.EVIDENCE_DELETE_ANY.value, db)
            
            if not has_permission:
                required_perm = Permission.EVIDENCE_DELETE.value if is_owner else Permission.EVIDENCE_DELETE_ANY.value
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Insufficient permissions. You need the '{required_perm}' permission to delete this evidence."
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions to delete this evidence."
            )
    
    # Capture details before deletion
    engagement_id = evidence.engagement_id or "global"
    evidence_id = evidence.id
    filename = evidence.filename
    original_filename = evidence.original_filename

    # Delete from storage
    try:
        await storage_service.delete_file(filename)
    except Exception as e:
        # Log error but continue to delete DB record? Or alert user?
        print(f"Failed to delete file from storage: {e}")
        
    # Delete from database
    await db.delete(evidence)
    await db.commit()
    
    # Log activity
    await create_activity_log(
        db,
        engagement_id=engagement_id,
        user_id=current_user.id,
        action="deleted_evidence",
        resource_type="evidence",
        resource_id=evidence_id,
        resource_name=original_filename,
        details=f"Deleted evidence {original_filename}"
    )
    
    await db.commit() # Commit the log
    
    return {"message": "Evidence deleted successfully"}

@router.put("/{evidence_id}/replace-file", response_model=EvidenceResponse)
async def replace_evidence_file(
    evidence_id: str,
    file: UploadFile = FastAPIFile(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Replace the file content of an existing evidence item (e.g. after image editing)."""
    result = await db.execute(select(Evidence).where(Evidence.id == evidence_id))
    evidence = result.scalar_one_or_none()

    if not evidence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence not found"
        )

    # Check permissions using RBAC (same as update_evidence)
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    is_owner = evidence.created_by == current_user.id

    if not is_admin:
        eng_id = await get_evidence_engagement_id(evidence, db)
        if eng_id:
            if is_owner:
                has_permission = await check_engagement_permission(current_user.id, eng_id, Permission.EVIDENCE_EDIT.value, db)
            else:
                has_permission = await check_engagement_permission(current_user.id, eng_id, Permission.EVIDENCE_EDIT_ANY.value, db)

            if not has_permission:
                required_perm = Permission.EVIDENCE_EDIT.value if is_owner else Permission.EVIDENCE_EDIT_ANY.value
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Insufficient permissions. You need the '{required_perm}' permission to modify this evidence."
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions to modify this evidence."
            )

    # Read file content and overwrite in storage using the same key
    file_content = await file.read()
    content_type = file.content_type or evidence.mime_type or "application/octet-stream"

    await storage_service.upload_file(file_content, evidence.filename, content_type)

    # Update metadata in DB
    evidence.file_size = len(file_content)
    evidence.mime_type = content_type
    evidence.updated_by = current_user.id

    await db.commit()

    # Reload with username
    result = await db.execute(
        select(Evidence, User.username)
        .outerjoin(User, Evidence.created_by == User.id)
        .where(Evidence.id == evidence.id)
    )
    row = result.first()
    if row:
        evidence, username = row
        evidence.created_by_username = username
    else:
        await db.refresh(evidence)

    # Log activity
    await create_activity_log(
        db,
        engagement_id=evidence.engagement_id or "global",
        user_id=current_user.id,
        action="edited_evidence_image",
        resource_type="evidence",
        resource_id=evidence.id,
        resource_name=evidence.original_filename,
        details=f"Replaced file content for {evidence.original_filename} (image edit)"
    )

    return evidence

@router.get("/{evidence_id}/url")
async def get_evidence_presigned_url(
    evidence_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate a presigned URL for an evidence file (generic)."""
    result = await db.execute(select(Evidence).where(Evidence.id == evidence_id))
    evidence = result.scalar_one_or_none()
    
    if not evidence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence not found"
        )
    
    # Check permissions
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        eng_id = await get_evidence_engagement_id(evidence, db)
        if eng_id:
            has_permission = await check_engagement_permission(current_user.id, eng_id, Permission.EVIDENCE_VIEW.value, db)
            if not has_permission:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions. You need the 'evidence_view' permission to access this file."
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to system file"
            )
            
    url = storage_service.get_presigned_url(evidence.filename)
    return {"url": url}

# Query-param authentication for the download endpoint. The frontend
# attaches the JWT to ?token=... because <img src> and window.open
# can't carry an Authorization header — and that puts the credential
# into URL sinks (browser history, proxy logs, Referer).
#
# To make those sinks low-value, the dependency now ONLY accepts a
# purpose-scoped, short-lived JWT minted by POST /evidence/{id}/
# download-token: type == "evidence_dl", an "eid" claim that pins it
# to a specific evidence row, and a 60-second lifetime. A captured
# download URL therefore can't be replayed against any other endpoint
# or against a different evidence row. GHSA-gjcp-hxgm-2vx7.
async def get_current_user_from_token(
    evidence_id: str,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db)
) -> User:
    from auth.jwt import decode_token, is_token_blacklisted

    # Check blacklist/revocation first
    if is_token_blacklisted(token):
        raise HTTPException(status_code=401, detail="Token has been revoked")

    payload = decode_token(token)
    if not payload or payload.get("type") != "evidence_dl":
        raise HTTPException(status_code=401, detail="Invalid token")

    if payload.get("eid") != evidence_id:
        raise HTTPException(status_code=401, detail="Token not issued for this evidence")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return user

@router.post("/{evidence_id}/download-token")
async def create_evidence_download_token(
    evidence_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mint a short-lived (60s) download-only JWT for this evidence id.

    Header-authenticated so the long-lived session token never leaves the
    Authorization header. The returned JWT has type=evidence_dl and is
    scoped to this evidence_id via the eid claim — get_current_user_from_token
    on /download rejects anything else. GHSA-gjcp-hxgm-2vx7.
    """
    from datetime import timedelta
    from auth.jwt import create_access_token

    result = await db.execute(select(Evidence).where(Evidence.id == evidence_id))
    evidence = result.scalar_one_or_none()
    if not evidence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence not found",
        )

    # Mirror the same authorization the download route enforces — issuing
    # a token to a caller who can't use the underlying file would be a
    # capability leak.
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        eng_id = await get_evidence_engagement_id(evidence, db)
        if eng_id and not await check_engagement_permission(
            current_user.id, eng_id, Permission.EVIDENCE_VIEW.value, db,
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Insufficient permissions. You need the 'evidence_view' "
                    "permission to download files from this engagement."
                ),
            )

    dl_token = create_access_token(
        data={
            "sub": current_user.id,
            "type": "evidence_dl",
            "eid": evidence_id,
        },
        expires_delta=timedelta(seconds=60),
    )
    return {"token": dl_token}


@router.get("/{evidence_id}/download")
async def download_evidence(
    evidence_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    """Download evidence file directly via backend proxy."""
    from fastapi.responses import StreamingResponse
    
    result = await db.execute(select(Evidence).where(Evidence.id == evidence_id))
    evidence = result.scalar_one_or_none()
    
    if not evidence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence not found"
        )
    
    # Security: Verify user has access to this engagement
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    
    if not is_admin:
        eng_id = await get_evidence_engagement_id(evidence, db)
        if eng_id:
            # Security: Verify user has access to this engagement via permissions
            has_permission = await check_engagement_permission(current_user.id, eng_id, Permission.EVIDENCE_VIEW.value, db)
            if not has_permission:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions. You need the 'evidence_view' permission to download files from this engagement."
                )
        else:
            # If no engagement linked, default to admin-only or handle as needed
            # For now, let's assume secure by default
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to system file"
            )
    
    try:
        file_stream = await storage_service.get_file_stream(evidence.filename)
        
        return StreamingResponse(
            file_stream, 
            media_type=evidence.mime_type or "application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{evidence.original_filename.replace(chr(34), "").replace(chr(13), "").replace(chr(10), "")}"'}
        )
    except Exception as e:
        # Check for MinIO/S3 missing file error
        error_str = str(e)
        if "NoSuchKey" in error_str or "404" in error_str:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found in storage. It may have been deleted or moved."
            )
            
        print(f"Download error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to download file"
        )


# ─── EXIF helpers ────────────────────────────────────────────────────

def _extract_exif_dict(image_bytes: bytes) -> dict:
    """Extract EXIF data from image bytes, returning a JSON-safe dict."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        exif_data = img._getexif()  # type: ignore
        if not exif_data:
            return {}
        result = {}
        for tag_id, value in exif_data.items():
            tag_name = TAGS.get(tag_id, str(tag_id))
            # Skip binary/thumbnail data
            if isinstance(value, bytes):
                continue
            # Handle IFDRational and other non-serializable types
            try:
                if hasattr(value, 'numerator'):
                    value = float(value)
                elif isinstance(value, tuple):
                    value = [float(v) if hasattr(v, 'numerator') else v for v in value]
                # Verify it's JSON-serializable
                import json
                json.dumps(value)
                result[tag_name] = value
            except (TypeError, ValueError, OverflowError):
                result[tag_name] = str(value)
        return result
    except Exception:
        return {}


@router.get("/{evidence_id}/exif")
async def get_evidence_exif(
    evidence_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Extract and return EXIF metadata from an image evidence file."""
    result = await db.execute(select(Evidence).where(Evidence.id == evidence_id))
    evidence = result.scalar_one_or_none()

    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")

    # Check permissions
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        eng_id = await get_evidence_engagement_id(evidence, db)
        if eng_id:
            has_perm = await check_engagement_permission(current_user.id, eng_id, Permission.EVIDENCE_VIEW.value, db)
            if not has_perm:
                raise HTTPException(status_code=403, detail="Insufficient permissions")
        else:
            raise HTTPException(status_code=403, detail="Access denied")

    # Only process images
    if not evidence.mime_type or not evidence.mime_type.startswith('image/'):
        return {"exif": {}, "has_exif": False}

    try:
        file_stream = await storage_service.get_file_stream(evidence.filename)
        image_bytes = b""
        async for chunk in file_stream:
            image_bytes += chunk
    except Exception:
        # If stream is sync (bytes-like), try reading directly
        try:
            file_stream = await storage_service.get_file_stream(evidence.filename)
            if hasattr(file_stream, 'read'):
                image_bytes = file_stream.read()
            else:
                image_bytes = b"".join(file_stream)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")

    exif = _extract_exif_dict(image_bytes)
    return {"exif": exif, "has_exif": len(exif) > 0}


@router.post("/{evidence_id}/strip-exif")
async def strip_evidence_exif(
    evidence_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Strip all EXIF data from an image except DateTimeOriginal and DateTimeDigitized."""
    result = await db.execute(select(Evidence).where(Evidence.id == evidence_id))
    evidence = result.scalar_one_or_none()

    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")

    # Check edit permissions
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    is_owner = evidence.created_by == current_user.id
    if not is_admin:
        eng_id = await get_evidence_engagement_id(evidence, db)
        if eng_id:
            perm = Permission.EVIDENCE_EDIT.value if is_owner else Permission.EVIDENCE_EDIT_ANY.value
            has_perm = await check_engagement_permission(current_user.id, eng_id, perm, db)
            if not has_perm:
                raise HTTPException(status_code=403, detail=f"Insufficient permissions ({perm})")
        else:
            raise HTTPException(status_code=403, detail="Access denied")

    if not evidence.mime_type or not evidence.mime_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="Not an image file")

    # Download file from storage
    try:
        file_stream = await storage_service.get_file_stream(evidence.filename)
        image_bytes = b""
        async for chunk in file_stream:
            image_bytes += chunk
    except Exception:
        try:
            file_stream = await storage_service.get_file_stream(evidence.filename)
            if hasattr(file_stream, 'read'):
                image_bytes = file_stream.read()
            else:
                image_bytes = b"".join(file_stream)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")

    # Extract EXIF before stripping
    old_exif = _extract_exif_dict(image_bytes)
    date_taken = old_exif.get('DateTimeOriginal') or old_exif.get('DateTimeDigitized') or old_exif.get('DateTime')

    # Open image, strip EXIF by saving without exif
    img = Image.open(io.BytesIO(image_bytes))
    output = io.BytesIO()
    # Determine format
    fmt = img.format or 'JPEG'
    # Save without EXIF
    img.save(output, format=fmt)
    clean_bytes = output.getvalue()

    # Re-upload the clean image
    content_type = evidence.mime_type or "application/octet-stream"
    await storage_service.upload_file(clean_bytes, evidence.filename, content_type)

    # Update file size in DB
    evidence.file_size = len(clean_bytes)
    evidence.updated_by = current_user.id
    await db.commit()

    # Log activity
    await create_activity_log(
        db,
        engagement_id=evidence.engagement_id or "global",
        user_id=current_user.id,
        action="stripped_exif",
        resource_type="evidence",
        resource_id=evidence.id,
        resource_name=evidence.original_filename,
        details=f"Stripped EXIF metadata from {evidence.original_filename}"
    )
    await db.commit()

    stripped_count = len(old_exif)
    return {
        "message": f"Stripped {stripped_count} EXIF tags",
        "date_taken": date_taken,
        "new_file_size": len(clean_bytes),
    }
