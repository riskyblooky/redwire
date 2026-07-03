from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
import uuid
import os
import logging

logger = logging.getLogger(__name__)

from database import get_db
from models.user import User, UserRole
from models.vault import VaultItem
from models.finding import Finding
from models.testcase import TestCase
from schemas.vault import (
    VaultItemCreate,
    VaultItemUpdate,
    VaultItemResponse,
    VaultItemRevealResponse,
)
from auth.dependencies import get_current_user
from auth.rbac import check_engagement_permission
from models.permission import Permission
from utils.collaboration import create_activity_log, build_change_summary, compute_changes_dict
from utils.hash_utils import identify_hash_type
from utils.vault_access_log import should_log_vault_access
# VaultItem.{username,password,note} are EncryptedText columns —
# encrypt-on-write / decrypt-on-read happens at the ORM type layer.
# Only the file-blob helpers (encrypt_bytes / decrypt_bytes) need an
# explicit wrap in this router; the secret-text columns no longer do.
from utils.vault_crypto import encrypt_bytes, decrypt_bytes
from utils.storage import storage_service
from sqlalchemy.orm import selectinload

router = APIRouter(prefix="/vault", tags=["vault"])


def _build_metadata_response(
    item: VaultItem,
    creator_username: Optional[str] = None,
    creator_profile_photo: Optional[str] = None,
) -> VaultItemResponse:
    """Build the metadata-only response shape from a VaultItem. The
    decrypted secret values are inspected to compute ``has_*`` flags
    and the hash-shape badge, but neither is returned in the
    response — only ``GET /vault/{item_id}/reveal`` carries the
    plaintext to callers (with an audit log row).

    GHSA-fp69-w2mg-4pqp follow-up. ``item.username`` / ``item.password``
    / ``item.note`` are already plaintext at this point because the
    EncryptedText column type decrypted on ORM read; the strict
    decrypt_field returns ``None`` on InvalidToken so a corrupted
    or wrong-keyed row surfaces as has_* = False (rather than
    silently round-tripping ciphertext).
    """
    has_username = bool(item.username)
    has_password = bool(item.password)
    has_note = bool(item.note)

    # Classify hash shape only when there's a password to classify. The
    # frontend uses this boolean to surface a "Crack this hash"
    # affordance without forcing a reveal call first.
    password_looks_like_hash = (
        bool(identify_hash_type(item.password)) if has_password else False
    )

    return VaultItemResponse(
        id=item.id,
        engagement_id=item.engagement_id,
        name=item.name,
        item_type=item.item_type,
        description=item.description,
        has_username=has_username,
        has_password=has_password,
        has_note=has_note,
        password_looks_like_hash=password_looks_like_hash,
        filename=item.filename,
        file_path=item.file_path,
        created_at=item.created_at,
        updated_at=item.updated_at,
        created_by=item.created_by,
        updated_by=item.updated_by,
        created_by_username=creator_username,
        created_by_profile_photo=creator_profile_photo,
        findings=[
            {"id": f.id, "title": f.title, "severity": f.severity.value if hasattr(f.severity, "value") else str(f.severity)}
            for f in (getattr(item, "findings", None) or [])
        ],
        testcases=[
            {"id": t.id, "title": t.title}
            for t in (getattr(item, "testcases", None) or [])
        ],
        assets=[
            {"id": a.id, "name": a.name, "asset_type": a.asset_type, "identifier": getattr(a, "identifier", None)}
            for a in (getattr(item, "assets", None) or [])
        ],
    )

@router.get("", response_model=List[VaultItemResponse])
async def get_vault_items(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all vault items for an engagement."""
    # Authorization Check using RBAC
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    
    if not is_admin:
        has_permission = await check_engagement_permission(current_user.id, engagement_id, Permission.VAULT_VIEW.value, db)
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. You need the 'vault_view' permission to view vault items."
            )

    result = await db.execute(
        select(VaultItem, User.username.label("creator_username"), User.profile_photo.label("creator_profile_photo"))
        .outerjoin(User, VaultItem.created_by == User.id)
        .where(VaultItem.engagement_id == engagement_id)
        .options(
            selectinload(VaultItem.findings),
            selectinload(VaultItem.testcases),
            selectinload(VaultItem.assets),
        )
        .order_by(VaultItem.created_at.desc())
    )

    return [
        _build_metadata_response(item, creator_username, creator_profile_photo)
        for item, creator_username, creator_profile_photo in result.all()
    ]

@router.post("", response_model=VaultItemResponse, status_code=status.HTTP_201_CREATED)
async def create_vault_item(
    item_data: VaultItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new vault item."""
    # Authorization Check using RBAC
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.TEAM_LEAD]
    
    if not is_admin:
        has_permission = await check_engagement_permission(current_user.id, item_data.engagement_id, Permission.VAULT_CREATE.value, db)
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. You need the 'vault_create' permission to create vault items."
            )

    # EncryptedText handles the field-level Fernet wrap at bind time.
    db_item = VaultItem(
        **item_data.model_dump(),
        created_by=current_user.id
    )
    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)

    # Log activity
    await create_activity_log(
        db,
        engagement_id=db_item.engagement_id,
        user_id=current_user.id,
        action="created_vault_item",
        resource_type="vault",
        resource_id=db_item.id,
        resource_name=db_item.name,
        details=f"Created {db_item.item_type} vault item: {db_item.name}"
    )

    # GHSA-fp69-w2mg-4pqp: create returns metadata-only — the caller
    # just submitted the plaintext, they don't need it echoed back, and
    # uniform response shape across endpoints makes the surface clearer.
    return _build_metadata_response(db_item)

@router.post("/upload", response_model=VaultItemResponse)
async def upload_vault_file(
    engagement_id: str = Form(...),
    name: str = Form(...),
    description: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Upload a sensitive file to the vault."""
    # Authorization Check
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_permission = await check_engagement_permission(current_user.id, engagement_id, Permission.VAULT_CREATE.value, db)
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. You need the 'vault_create' permission to upload files to the vault."
            )

    # Upload file to MinIO. Encrypt the content with the vault Fernet key
    # so files in object storage are protected at rest the same way the
    # username/password/note fields are protected in Postgres (RDW-057).
    # Force application/octet-stream + .enc suffix so any future direct
    # bucket access doesn't misadvertise a content type for the
    # ciphertext blob.
    content = await file.read()
    encrypted_content = encrypt_bytes(content)
    storage_key = f"vault/{uuid.uuid4()}.enc"
    await storage_service.upload_file(
        encrypted_content,
        storage_key,
        content_type="application/octet-stream",
    )

    db_item = VaultItem(
        engagement_id=engagement_id,
        name=name,
        item_type="FILE",
        filename=file.filename,
        file_path=storage_key,
        description=description,
        # Explicit so future schemes can change the default safely —
        # this row's blob is at the current Fernet scheme.
        encryption_version=1,
        created_by=current_user.id
    )
    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)

    # Log activity
    await create_activity_log(
        db,
        engagement_id=db_item.engagement_id,
        user_id=current_user.id,
        action="uploaded_vault_file",
        resource_type="vault",
        resource_id=db_item.id,
        resource_name=db_item.name,
        details=f"Uploaded file to vault: {db_item.filename}"
    )

    return _build_metadata_response(db_item)

@router.patch("/{item_id}", response_model=VaultItemResponse)
async def update_vault_item(
    item_id: str,
    item_update: VaultItemUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a vault item."""
    try:
        result = await db.execute(
            select(VaultItem)
            .options(selectinload(VaultItem.findings), selectinload(VaultItem.testcases))
            .where(VaultItem.id == item_id)
        )
        item = result.scalar_one_or_none()
        
        if not item:
            raise HTTPException(status_code=404, detail="Vault item not found")

        # Authorization Check using RBAC with ANY model
        is_admin = current_user.role in [UserRole.ADMIN, UserRole.TEAM_LEAD]
        is_owner = item.created_by == current_user.id
        
        if not is_admin:
            if is_owner:
                has_permission = await check_engagement_permission(current_user.id, item.engagement_id, Permission.VAULT_EDIT.value, db)
            else:
                has_permission = await check_engagement_permission(current_user.id, item.engagement_id, Permission.VAULT_EDIT_ANY.value, db)
            
            if not has_permission:
                required_perm = Permission.VAULT_EDIT.value if is_owner else Permission.VAULT_EDIT_ANY.value
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Insufficient permissions. You need the '{required_perm}' permission to edit this vault item."
                )

        # Disallow changing type if it's a file
        if item.item_type == "File" and item_update.item_type and item_update.item_type != "File":
            raise HTTPException(status_code=400, detail="Cannot change type of a file vault item")

        # Update fields — encrypt sensitive values before persisting.
        # NOTE: do not decrypt `item` here. build_change_summary redacts
        # vault-encrypted fields, so the diff doesn't need plaintext; and an
        # in-place decrypt mutates the SQLAlchemy attrs, which would persist
        # un-edited credential fields back as plaintext on the next commit.
        update_data = item_update.model_dump(exclude_unset=True)
        change_details = build_change_summary(item, update_data, label=f"Updated vault item '{item.name}'")
        # Structured changes for automation matching (GHSA-88hm follow-up).
        # compute_changes_dict consults the same _REDACTED_FIELDS set as
        # build_change_summary, so password/username/note appear as
        # {"changed": True} rather than leaking plaintext into the
        # automation context.
        changes = compute_changes_dict(item, update_data)

        # EncryptedText encrypts each bound value at commit time.
        for key, value in update_data.items():
            setattr(item, key, value)
        
        item.updated_by = current_user.id
        await db.commit()

        # Log activity (non-fatal)
        try:
            await create_activity_log(
                db,
                engagement_id=item.engagement_id,
                user_id=current_user.id,
                action="updated_vault_item",
                resource_type="vault",
                resource_id=item.id,
                resource_name=item.name,
                details=change_details,
                extra_context={"changes": changes},
            )
        except Exception as log_err:
            logger.warning(f"Vault activity log failed: {log_err}")
            await db.rollback()

        # Re-fetch with relationships for response serialization
        result = await db.execute(
            select(VaultItem)
            .options(
                selectinload(VaultItem.findings),
                selectinload(VaultItem.testcases),
                selectinload(VaultItem.assets),
            )
            .where(VaultItem.id == item_id)
        )
        item = result.scalar_one_or_none()

        return _build_metadata_response(item) if item else None
    except HTTPException:
        raise
    except Exception as e:
        # GHSA-7x2f-ff7r-h388 #4 (CWE-209): the previous 500 response
        # body reflected the exception type + str(e) directly. For a
        # SQLAlchemy IntegrityError that string carries table names,
        # column names, and the row values that violated the
        # constraint — sensitive schema detail for a low-priv user to
        # see. Server log keeps the full traceback for operator
        # debugging; the client just gets a generic message.
        logger.error(f"update_vault_item FAILED: {type(e).__name__}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error updating vault item.")


@router.get("/{item_id}", response_model=VaultItemResponse)
async def get_vault_item(
    item_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single vault item (metadata only). Plaintext is never
    returned by this endpoint — call ``GET /vault/{item_id}/reveal``
    to fetch decrypted credentials with audit logging."""
    result = await db.execute(
        select(VaultItem, User.username.label("creator_username"), User.profile_photo.label("creator_profile_photo"))
        .outerjoin(User, VaultItem.created_by == User.id)
        .where(VaultItem.id == item_id)
        .options(
            selectinload(VaultItem.findings),
            selectinload(VaultItem.testcases),
            selectinload(VaultItem.assets),
        )
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Vault item not found")
    item, creator_username, creator_profile_photo = row

    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_permission = await check_engagement_permission(
            current_user.id, item.engagement_id, Permission.VAULT_VIEW.value, db
        )
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. You need the 'vault_view' permission to view vault items.",
            )

    return _build_metadata_response(item, creator_username, creator_profile_photo)


@router.get("/{item_id}/reveal", response_model=VaultItemRevealResponse)
async def reveal_vault_item(
    item_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reveal the decrypted plaintext (username / password / note) for
    a single vault item.

    GHSA-fp69-w2mg-4pqp follow-up: this is the only endpoint that
    carries the decrypted fields on the wire. Every call writes an
    ``accessed_vault_secret`` activity-log row so an investigator can
    later see *which* specific credentials a departed operator
    pulled. Same per-recipient logging is deduped per (user, item)
    over a 5-minute window via Redis so a chatty UI session doesn't
    drown the audit signal.
    """
    result = await db.execute(
        select(VaultItem, User.username.label("creator_username"), User.profile_photo.label("creator_profile_photo"))
        .outerjoin(User, VaultItem.created_by == User.id)
        .where(VaultItem.id == item_id)
        .options(
            selectinload(VaultItem.findings),
            selectinload(VaultItem.testcases),
            selectinload(VaultItem.assets),
        )
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Vault item not found")
    item, creator_username, creator_profile_photo = row

    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_permission = await check_engagement_permission(
            current_user.id, item.engagement_id, Permission.VAULT_VIEW.value, db
        )
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. You need the 'vault_view' permission to reveal vault credentials.",
            )

    # The EncryptedText column type already returned plaintext from
    # the ORM read; metadata + reveal both consume the same values.
    metadata = _build_metadata_response(item, creator_username, creator_profile_photo)
    response = VaultItemRevealResponse(
        **metadata.model_dump(),
        username=item.username,
        password=item.password,
        note=item.note,
    )

    if should_log_vault_access(current_user.id, item.id):
        await create_activity_log(
            db,
            engagement_id=item.engagement_id,
            user_id=current_user.id,
            action="accessed_vault_secret",
            resource_type="vault",
            resource_id=item.id,
            resource_name=item.name,
            details=f"Revealed vault item: {item.name}",
        )

    return response

@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vault_item(
    item_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a vault item."""
    result = await db.execute(select(VaultItem).where(VaultItem.id == item_id))
    item = result.scalar_one_or_none()
    
    if not item:
        raise HTTPException(status_code=404, detail="Vault item not found")

    # Authorization Check using RBAC with ANY model
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.TEAM_LEAD]
    is_owner = item.created_by == current_user.id
    
    if not is_admin:
        if is_owner:
            # Owner needs base delete permission
            has_permission = await check_engagement_permission(current_user.id, item.engagement_id, Permission.VAULT_DELETE.value, db)
        else:
            # Non-owner needs delete_any permission
            has_permission = await check_engagement_permission(current_user.id, item.engagement_id, Permission.VAULT_DELETE_ANY.value, db)
        
        if not has_permission:
            required_perm = Permission.VAULT_DELETE.value if is_owner else Permission.VAULT_DELETE_ANY.value
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. You need the '{required_perm}' permission to delete this vault item."
            )

    # Delete file from MinIO if exists
    if item.file_path:
        try:
            await storage_service.delete_file(item.file_path)
        except Exception:
            logger.warning(f"Failed to delete vault file from storage: {item.file_path}")

    # Log activity before deletion
    await create_activity_log(
        db,
        engagement_id=item.engagement_id,
        user_id=current_user.id,
        action="deleted_vault_item",
        resource_type="vault",
        resource_id=item.id,
        resource_name=item.name,
        details=f"Deleted vault item: {item.name}"
    )

    await db.delete(item)
    await db.commit()
    
    return None

@router.get("/download/{item_id}")
async def download_vault_file(
    item_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Securely download a vault file as an attachment."""
    result = await db.execute(select(VaultItem).where(VaultItem.id == item_id))
    item = result.scalar_one_or_none()
    
    if not item or item.item_type != "FILE":
        raise HTTPException(status_code=404, detail="File not found in vault")

    # Authorization Check
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_permission = await check_engagement_permission(current_user.id, item.engagement_id, Permission.VAULT_VIEW.value, db)
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. You need the 'vault_view' permission to access this file."
            )

    if not item.file_path:
        raise HTTPException(status_code=404, detail="File content missing on server")

    # Log access. Same 5-minute dedup window as the /reveal endpoint —
    # an operator who clicks download three times in a row (file lost,
    # browser blocked, retry) shouldn't produce three audit rows. The
    # first download per (user, item) per window writes; subsequent
    # downloads inside the window skip the log. GHSA-fp69-w2mg-4pqp
    # follow-up.
    if should_log_vault_access(current_user.id, item.id):
        await create_activity_log(
            db,
            engagement_id=item.engagement_id,
            user_id=current_user.id,
            action="downloaded_vault_file",
            resource_type="vault",
            resource_id=item.id,
            resource_name=item.name,
            details=f"Downloaded vault file: {item.filename}"
        )

    # Stream from MinIO. decrypt_bytes falls back to the raw payload
    # if the stored blob isn't Fernet-shaped — covers legacy plaintext
    # files uploaded before RDW-057 shipped.
    try:
        file_bytes = await storage_service.download_file(item.file_path)
    except Exception:
        raise HTTPException(status_code=404, detail="File content missing in storage")

    file_bytes = decrypt_bytes(file_bytes)

    # GHSA-7x2f-ff7r-h388 #2 (CWE-116): the previous format string
    # interpolated `item.filename` verbatim into the header. A
    # filename containing `"` or `\r` could break out of the quoted
    # value and inject sibling headers (CRLF injection at the response
    # level) or produce a malformed header that some clients render as
    # HTML in an error banner. Use RFC 6266's dual-emission shape
    # (`filename=` ASCII-fallback + `filename*=UTF-8''<pct-encoded>`)
    # so clients get a safe rendering regardless of the original name.
    from urllib.parse import quote as _pq
    _raw = (item.filename or "download").replace("\r", "").replace("\n", "")
    _ascii_fallback = "".join(c if 32 <= ord(c) < 127 and c not in '"\\' else "_" for c in _raw)
    _utf8_encoded = _pq(_raw, safe="")
    disposition = f'attachment; filename="{_ascii_fallback}"; filename*=UTF-8\'\'{_utf8_encoded}'
    return Response(
        content=file_bytes,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": disposition,
            "X-Content-Type-Options": "nosniff"
        }
    )


@router.post("/{item_id}/findings/{finding_id}", status_code=status.HTTP_201_CREATED)
async def link_vault_to_finding(
    item_id: str,
    finding_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Link a vault item to a finding."""
    result = await db.execute(select(VaultItem).options(selectinload(VaultItem.findings)).where(VaultItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Vault item not found")

    # RBAC check
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_permission = await check_engagement_permission(current_user.id, item.engagement_id, Permission.VAULT_EDIT.value, db)
        if not has_permission:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions. You need 'vault_edit' permission.")

    result = await db.execute(select(Finding).where(Finding.id == finding_id))
    finding = result.scalar_one_or_none()
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    # Ensure same engagement
    if finding.engagement_id != item.engagement_id:
        raise HTTPException(status_code=400, detail="Finding belongs to a different engagement")

    if finding not in item.findings:
        item.findings.append(finding)
        await db.commit()

        # Log activity
        await create_activity_log(
            db,
            engagement_id=item.engagement_id,
            user_id=current_user.id,
            action="linked_vault_item",
            resource_type="vault",
            resource_id=item.id,
            resource_name=item.name,
            details=f"Linked vault item '{item.name}' to finding '{finding.title}'"
        )

    return {"status": "linked"}


@router.delete("/{item_id}/findings/{finding_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_vault_from_finding(
    item_id: str,
    finding_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Unlink a vault item from a finding."""
    result = await db.execute(select(VaultItem).options(selectinload(VaultItem.findings)).where(VaultItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Vault item not found")

    # RBAC check
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_permission = await check_engagement_permission(current_user.id, item.engagement_id, Permission.VAULT_EDIT.value, db)
        if not has_permission:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions. You need 'vault_edit' permission.")

    result = await db.execute(select(Finding).where(Finding.id == finding_id))
    finding = result.scalar_one_or_none()
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    if finding in item.findings:
        item.findings.remove(finding)
        await db.commit()

        # Log activity
        await create_activity_log(
            db,
            engagement_id=item.engagement_id,
            user_id=current_user.id,
            action="unlinked_vault_item",
            resource_type="vault",
            resource_id=item.id,
            resource_name=item.name,
            details=f"Unlinked vault item '{item.name}' from finding '{finding.title}'"
        )

    return None


@router.post("/{item_id}/testcases/{testcase_id}", status_code=status.HTTP_201_CREATED)
async def link_vault_to_testcase(
    item_id: str,
    testcase_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Link a vault item to a test case."""
    result = await db.execute(select(VaultItem).options(selectinload(VaultItem.testcases)).where(VaultItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Vault item not found")

    # RBAC check
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_permission = await check_engagement_permission(current_user.id, item.engagement_id, Permission.VAULT_EDIT.value, db)
        if not has_permission:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions. You need 'vault_edit' permission.")

    result = await db.execute(select(TestCase).where(TestCase.id == testcase_id))
    testcase = result.scalar_one_or_none()
    if not testcase:
        raise HTTPException(status_code=404, detail="Test case not found")

    # Ensure same engagement
    if testcase.engagement_id != item.engagement_id:
        raise HTTPException(status_code=400, detail="Test case belongs to a different engagement")

    if testcase not in item.testcases:
        item.testcases.append(testcase)
        await db.commit()

        # Log activity
        await create_activity_log(
            db,
            engagement_id=item.engagement_id,
            user_id=current_user.id,
            action="linked_vault_item",
            resource_type="vault",
            resource_id=item.id,
            resource_name=item.name,
            details=f"Linked vault item '{item.name}' to test case '{testcase.title}'"
        )

    return {"status": "linked"}


@router.delete("/{item_id}/testcases/{testcase_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_vault_from_testcase(
    item_id: str,
    testcase_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Unlink a vault item from a test case."""
    result = await db.execute(select(VaultItem).options(selectinload(VaultItem.testcases)).where(VaultItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Vault item not found")

    # RBAC check
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_permission = await check_engagement_permission(current_user.id, item.engagement_id, Permission.VAULT_EDIT.value, db)
        if not has_permission:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions. You need 'vault_edit' permission.")

    result = await db.execute(select(TestCase).where(TestCase.id == testcase_id))
    testcase = result.scalar_one_or_none()
    if not testcase:
        raise HTTPException(status_code=404, detail="Test case not found")

    if testcase in item.testcases:
        item.testcases.remove(testcase)
        await db.commit()

        # Log activity
        await create_activity_log(
            db,
            engagement_id=item.engagement_id,
            user_id=current_user.id,
            action="unlinked_vault_item",
            resource_type="vault",
            resource_id=item.id,
            resource_name=item.name,
            details=f"Unlinked vault item '{item.name}' from test case '{testcase.title}'"
        )

    return None


@router.post("/{item_id}/assets/{asset_id}", status_code=status.HTTP_201_CREATED)
async def link_vault_to_asset(
    item_id: str,
    asset_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Link a vault item to an asset."""
    from models.asset import Asset
    result = await db.execute(select(VaultItem).options(selectinload(VaultItem.assets)).where(VaultItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Vault item not found")

    # RBAC check
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_permission = await check_engagement_permission(current_user.id, item.engagement_id, Permission.VAULT_EDIT.value, db)
        if not has_permission:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions. You need 'vault_edit' permission.")

    result = await db.execute(select(Asset).where(Asset.id == asset_id))
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    # Ensure same engagement
    if asset.engagement_id != item.engagement_id:
        raise HTTPException(status_code=400, detail="Asset belongs to a different engagement")

    if asset not in item.assets:
        item.assets.append(asset)
        await db.commit()

        await create_activity_log(
            db,
            engagement_id=item.engagement_id,
            user_id=current_user.id,
            action="linked_vault_item",
            resource_type="vault",
            resource_id=item.id,
            resource_name=item.name,
            details=f"Linked vault item '{item.name}' to asset '{asset.name}'"
        )

    return {"status": "linked"}


@router.delete("/{item_id}/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_vault_from_asset(
    item_id: str,
    asset_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Unlink a vault item from an asset."""
    from models.asset import Asset
    result = await db.execute(select(VaultItem).options(selectinload(VaultItem.assets)).where(VaultItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Vault item not found")

    # RBAC check
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_permission = await check_engagement_permission(current_user.id, item.engagement_id, Permission.VAULT_EDIT.value, db)
        if not has_permission:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions. You need 'vault_edit' permission.")

    result = await db.execute(select(Asset).where(Asset.id == asset_id))
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    if asset in item.assets:
        item.assets.remove(asset)
        await db.commit()

        await create_activity_log(
            db,
            engagement_id=item.engagement_id,
            user_id=current_user.id,
            action="unlinked_vault_item",
            resource_type="vault",
            resource_id=item.id,
            resource_name=item.name,
            details=f"Unlinked vault item '{item.name}' from asset '{asset.name}'"
        )

    return None
