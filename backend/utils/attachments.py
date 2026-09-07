"""Helpers for auto-saving import/upload source files as engagement records.

Scanner and asset imports parse a file and then discard it; these helpers let
those endpoints also retain the original file — scan/asset source files as an
engagement Evidence attachment, and credential-bearing spray logs as an
encrypted Vault file — so the raw input is preserved for the record.

All helpers are best-effort: they never raise into the caller (a retention
failure must not fail the import that already succeeded) and return the new
record id or None.
"""
import os
import uuid
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def save_bytes_as_evidence(
    db: AsyncSession,
    *,
    engagement_id: str,
    content: bytes,
    original_filename: str,
    user_id: str,
    description: Optional[str] = None,
    include_in_report: bool = False,
) -> Optional[str]:
    """Persist raw bytes as an engagement Evidence attachment. Returns the
    evidence id, or None on failure (never raises)."""
    from models.evidence import Evidence
    from utils.storage import storage_service
    from utils.uploads import sanitize_original_filename, safe_content_type
    from utils.collaboration import create_activity_log
    try:
        ext = os.path.splitext(original_filename or "")[1]
        storage_filename = f"{uuid.uuid4()}{ext}"
        safe_mime = safe_content_type(original_filename)
        await storage_service.upload_file(content, storage_filename, content_type=safe_mime)
        ev = Evidence(
            engagement_id=engagement_id,
            filename=storage_filename,
            original_filename=sanitize_original_filename(original_filename, fallback="import"),
            file_path=storage_filename,
            file_size=len(content),
            mime_type=safe_mime,
            description=description,
            include_in_report=include_in_report,
            created_by=user_id,
        )
        db.add(ev)
        await db.commit()
        await db.refresh(ev)
        try:
            await create_activity_log(
                db, engagement_id=engagement_id, user_id=user_id,
                action="uploaded", resource_type="evidence", resource_id=ev.id,
                resource_name=ev.original_filename,
                details=f"Auto-saved import source file as attachment: {ev.original_filename}",
            )
        except Exception:
            pass
        return ev.id
    except Exception as e:
        logger.warning("Failed to auto-save import file as evidence: %s", e)
        try:
            await db.rollback()
        except Exception:
            pass
        return None


async def save_bytes_as_vault_file(
    db: AsyncSession,
    *,
    engagement_id: str,
    content: bytes,
    name: str,
    original_filename: str,
    user_id: str,
    description: Optional[str] = None,
) -> Optional[str]:
    """Persist raw bytes as a Fernet-encrypted Vault FILE item (for
    credential-bearing sources like spray logs). Returns the vault item id, or
    None on failure (never raises)."""
    from models.vault import VaultItem
    from utils.storage import storage_service
    from utils.vault_crypto import encrypt_bytes
    from utils.uploads import sanitize_original_filename
    from utils.collaboration import create_activity_log
    try:
        encrypted = encrypt_bytes(content)
        storage_key = f"vault/{uuid.uuid4()}.enc"
        await storage_service.upload_file(encrypted, storage_key, content_type="application/octet-stream")
        item = VaultItem(
            engagement_id=engagement_id,
            name=name,
            item_type="FILE",
            filename=sanitize_original_filename(original_filename, fallback="spray.log"),
            file_path=storage_key,
            description=description,
            encryption_version=1,
            created_by=user_id,
        )
        db.add(item)
        await db.commit()
        await db.refresh(item)
        try:
            await create_activity_log(
                db, engagement_id=engagement_id, user_id=user_id,
                action="uploaded_vault_file", resource_type="vault", resource_id=item.id,
                resource_name=item.name,
                details=f"Auto-saved spray log to vault (encrypted): {item.filename}",
            )
        except Exception:
            pass
        return item.id
    except Exception as e:
        logger.warning("Failed to auto-save spray log as vault file: %s", e)
        try:
            await db.rollback()
        except Exception:
            pass
        return None
