"""Storing an uploaded evidence file: the one pipeline behind the
engagement, finding and test-case upload endpoints (which used to carry
three drifting copies). Callers do their own permission checks and
activity log; this reads the upload under the size cap, stores it under a
server-chosen key with a server-derived MIME type, and inserts the row.
"""
import logging
import os
import uuid
from typing import Optional

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from models.evidence import Evidence
from utils import storage_tx
from utils.uploads import MAX_EVIDENCE_BYTES, read_upload_capped, safe_content_type, sanitize_original_filename

_log = logging.getLogger(__name__)


async def store_evidence(
    db: AsyncSession,
    file: UploadFile,
    *,
    engagement_id: str,
    uploader,
    description: Optional[str],
    include_in_report: bool,
    finding_id: Optional[str] = None,
    testcase_id: Optional[str] = None,
) -> Evidence:
    """Store ``file`` as evidence and commit the row. Returns it with the
    uploader's name filled in for the response."""
    content = await read_upload_capped(
        file, MAX_EVIDENCE_BYTES,
        detail=f"Evidence upload exceeds the {MAX_EVIDENCE_BYTES}-byte size limit.",
    )
    ext = os.path.splitext(file.filename)[1] if file.filename else ""
    storage_filename = f"{uuid.uuid4()}{ext}"
    # GHSA-h77m-pjqc-5cm3 follow-up: the MIME type comes from the filename,
    # not the client's Content-Type header. The same string goes to storage
    # and to Evidence.mime_type, which the frontend reads to decide whether
    # to preview inline.
    safe_mime = safe_content_type(file.filename)

    try:
        await storage_tx.upload(db, content, storage_filename, content_type=safe_mime)
    except Exception:
        # Logged, not echoed: the storage error can name internal hosts.
        _log.exception("Evidence upload to storage failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Couldn't store the file. Please retry.")

    evidence = Evidence(
        engagement_id=engagement_id,
        finding_id=finding_id,
        testcase_id=testcase_id,
        filename=storage_filename,
        original_filename=sanitize_original_filename(file.filename, fallback="unknown"),
        file_path=storage_filename,
        file_size=len(content),
        mime_type=safe_mime,
        description=description,
        include_in_report=include_in_report,
        created_by=uploader.id,
    )
    db.add(evidence)
    await db.commit()
    await db.refresh(evidence)
    evidence.created_by_username = uploader.username
    evidence.created_by_full_name = uploader.full_name
    return evidence
