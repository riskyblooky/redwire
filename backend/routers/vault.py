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
from schemas.vault import VaultItemCreate, VaultItemUpdate, VaultItemResponse
from auth.dependencies import get_current_user
from auth.rbac import check_engagement_permission
from models.permission import Permission
from utils.collaboration import create_activity_log, build_change_summary
from utils.vault_crypto import (
    encrypt_vault_fields,
    decrypt_vault_item,
    encrypt_field,
    encrypt_bytes,
    decrypt_bytes,
)
from utils.storage import storage_service
from sqlalchemy.orm import selectinload

router = APIRouter(prefix="/vault", tags=["vault"])

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
        .order_by(VaultItem.created_at.desc())
    )
    
    items = []
    for item, creator_username, creator_profile_photo in result.all():
        decrypt_vault_item(item)
        item_dict = VaultItemResponse.model_validate(item).model_dump()
        item_dict["created_by_username"] = creator_username
        item_dict["created_by_profile_photo"] = creator_profile_photo
        items.append(VaultItemResponse(**item_dict))
    
    return items

@router.post("", response_model=VaultItemResponse, status_code=status.HTTP_201_CREATED)
async def create_vault_item(
    item_data: VaultItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new vault item."""
    # Authorization Check using RBAC
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    
    if not is_admin:
        has_permission = await check_engagement_permission(current_user.id, item_data.engagement_id, Permission.VAULT_CREATE.value, db)
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. You need the 'vault_create' permission to create vault items."
            )

    encrypted_data = encrypt_vault_fields(item_data.model_dump())
    db_item = VaultItem(
        **encrypted_data,
        created_by=current_user.id
    )
    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)
    decrypt_vault_item(db_item)

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

    return db_item

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
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
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

    return db_item

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
        is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
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

        encrypted_data = encrypt_vault_fields(update_data)
        for key, value in encrypted_data.items():
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
                details=change_details
            )
        except Exception as log_err:
            logger.warning(f"Vault activity log failed: {log_err}")
            await db.rollback()

        # Re-fetch with relationships for response serialization
        result = await db.execute(
            select(VaultItem)
            .options(selectinload(VaultItem.findings), selectinload(VaultItem.testcases))
            .where(VaultItem.id == item_id)
        )
        item = result.scalar_one_or_none()
        if item:
            decrypt_vault_item(item)

        return item
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"update_vault_item FAILED: {type(e).__name__}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {type(e).__name__}: {str(e)}")

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
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
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

    # Log access
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

    return Response(
        content=file_bytes,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{item.filename}"',
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
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
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
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
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
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
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
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
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
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
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
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
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
