from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime

from database import get_db
from models.user import User, UserRole
from models.note import Note
from models.finding import Finding
from models.testcase import TestCase
from models.asset import Asset
from models.vault import VaultItem
from models.cleanup_artifact import CleanupArtifact
from models.associations import NoteAsset, NoteTestCase, NoteFinding, NoteVaultItem, NoteCleanupArtifact
from auth.dependencies import get_current_user
from auth.rbac import check_engagement_permission
from models.permission import Permission
from utils.collaboration import create_activity_log, manager

router = APIRouter(tags=["notes"])


# ─── Schemas ───────────────────────────────────────────────────────────

class NoteCreate(BaseModel):
    title: str = Field(..., max_length=500)
    # GHSA-82jh-8f6p-vgx9: cap body length at the schema layer. The note
    # body flows into notify_mentions which runs a regex with O(n)
    # materialized output; without a cap, a single oversized note could
    # drive multi-GB allocations on a worker. 32 KiB is generous.
    content: Optional[str] = Field("", max_length=32768)
    parent_id: Optional[str] = None

class NoteUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=500)
    content: Optional[str] = Field(None, max_length=32768)
    parent_id: Optional[str] = None

class LinkedResourceRef(BaseModel):
    id: str
    title: str

    class Config:
        from_attributes = True

class LinkedVaultRef(BaseModel):
    id: str
    name: str
    item_type: str

    class Config:
        from_attributes = True

class LinkedCleanupRef(BaseModel):
    id: str
    title: str
    artifact_type: str

    class Config:
        from_attributes = True

class NoteResponse(BaseModel):
    id: str
    engagement_id: str
    parent_id: Optional[str] = None
    title: str
    content: Optional[str] = ""
    created_by: str
    created_by_username: Optional[str] = None
    created_by_profile_photo: Optional[str] = None
    updated_by: Optional[str] = None
    updated_by_username: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    linked_findings: list[LinkedResourceRef] = []
    linked_testcases: list[LinkedResourceRef] = []
    linked_assets: list[LinkedResourceRef] = []
    linked_vault_items: list[LinkedVaultRef] = []
    linked_cleanup_artifacts: list[LinkedCleanupRef] = []

    class Config:
        from_attributes = True


# ─── Helpers ───────────────────────────────────────────────────────────

def _build_note_response(note, creator_username=None, creator_profile_photo=None, editor_username=None):
    """Build NoteResponse from a Note ORM object with eagerly loaded linked resources."""
    return NoteResponse(
        id=note.id,
        engagement_id=note.engagement_id,
        parent_id=note.parent_id,
        title=note.title,
        content=note.content,
        created_by=note.created_by,
        created_by_username=creator_username,
        created_by_profile_photo=creator_profile_photo,
        updated_by=note.updated_by,
        updated_by_username=editor_username,
        created_at=note.created_at,
        updated_at=note.updated_at,
        linked_findings=[LinkedResourceRef(id=f.id, title=f.title) for f in (note.findings or [])],
        linked_testcases=[LinkedResourceRef(id=t.id, title=t.title) for t in (note.testcases or [])],
        linked_assets=[LinkedResourceRef(id=a.id, title=a.name) for a in (note.assets or [])],
        linked_vault_items=[LinkedVaultRef(id=v.id, name=v.name, item_type=v.item_type) for v in (note.vault_items or [])],
        linked_cleanup_artifacts=[LinkedCleanupRef(id=c.id, title=c.title, artifact_type=c.artifact_type) for c in (note.cleanup_artifacts or [])],
    )


# ─── Endpoints ─────────────────────────────────────────────────────────

@router.get("/engagements/{engagement_id}/notes", response_model=List[NoteResponse])
async def get_notes(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all notes for an engagement."""
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]

    if not is_admin:
        has_permission = await check_engagement_permission(
            current_user.id, engagement_id, Permission.NOTE_VIEW.value, db
        )
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. You need the 'note_view' permission."
            )

    from models.user import User as UserModel
    CreatorUser = UserModel.__table__.alias("creator_user")
    EditorUser = UserModel.__table__.alias("editor_user")

    result = await db.execute(
        select(
            Note,
            CreatorUser.c.username.label("creator_username"),
            CreatorUser.c.profile_photo.label("creator_profile_photo"),
            EditorUser.c.username.label("editor_username"),
        )
        .outerjoin(CreatorUser, Note.created_by == CreatorUser.c.id)
        .outerjoin(EditorUser, Note.updated_by == EditorUser.c.id)
        .where(Note.engagement_id == engagement_id)
        .order_by(Note.updated_at.desc())
    )

    notes = []
    for note, creator_username, creator_profile_photo, editor_username in result.all():
        notes.append(_build_note_response(note, creator_username, creator_profile_photo, editor_username))

    return notes


@router.get("/notes/{note_id}", response_model=NoteResponse)
async def get_note(
    note_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a single note."""
    result = await db.execute(select(Note).where(Note.id == note_id))
    note = result.scalar_one_or_none()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_permission = await check_engagement_permission(
            current_user.id, note.engagement_id, Permission.NOTE_VIEW.value, db
        )
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions."
            )

    # Get usernames and profile photo
    from models.user import User as UserModel
    creator_result = await db.execute(select(UserModel.username, UserModel.profile_photo).where(UserModel.id == note.created_by))
    creator_row = creator_result.first()
    creator_username = creator_row[0] if creator_row else None
    creator_profile_photo = creator_row[1] if creator_row else None

    editor_username = None
    if note.updated_by:
        editor_result = await db.execute(select(UserModel.username).where(UserModel.id == note.updated_by))
        editor_username = editor_result.scalar_one_or_none()

    return _build_note_response(note, creator_username, creator_profile_photo, editor_username)


@router.post("/engagements/{engagement_id}/notes", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
async def create_note(
    engagement_id: str,
    note_data: NoteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new note."""
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]

    if not is_admin:
        has_permission = await check_engagement_permission(
            current_user.id, engagement_id, Permission.NOTE_CREATE.value, db
        )
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. You need the 'note_create' permission."
            )

    # Validate parent belongs to same engagement if specified
    if note_data.parent_id:
        parent_result = await db.execute(select(Note).where(Note.id == note_data.parent_id))
        parent_note = parent_result.scalar_one_or_none()
        if not parent_note or parent_note.engagement_id != engagement_id:
            raise HTTPException(status_code=400, detail="Parent note not found in this engagement")

    db_note = Note(
        engagement_id=engagement_id,
        title=note_data.title,
        content=note_data.content or "",
        created_by=current_user.id,
        parent_id=note_data.parent_id,
    )
    db.add(db_note)
    await db.commit()
    await db.refresh(db_note)

    # Log activity (self-contained, never raises)
    await create_activity_log(
        db,
        engagement_id=engagement_id,
        user_id=current_user.id,
        action="created_note",
        resource_type="note",
        resource_id=db_note.id,
        resource_name=db_note.title,
        details=f"Created note: {db_note.title}"
    )

    try:
        await manager.broadcast_to_resource("engagement", engagement_id, {
            "type": "note_created",
            "note_id": db_note.id,
            "title": db_note.title,
            "user_id": current_user.id,
        })
    except Exception:
        pass

    try:
        from utils.collaboration import notify_mentions
        await notify_mentions(
            db=db,
            content=db_note.content or "",
            actor_id=current_user.id,
            title=f"You were mentioned in a note",
            message=f"{current_user.full_name or current_user.username} mentioned you in note '{db_note.title}'",
            link=f"/engagements/{engagement_id}?tab=notes&noteId={db_note.id}",
            engagement_id=engagement_id,
        )
        await db.commit()
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass

    return _build_note_response(
        db_note,
        creator_username=current_user.username,
        creator_profile_photo=current_user.profile_photo,
        editor_username=None,
    )


@router.patch("/notes/{note_id}", response_model=NoteResponse)
async def update_note(
    note_id: str,
    note_data: NoteUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a note's title and/or content."""
    result = await db.execute(select(Note).where(Note.id == note_id))
    note = result.scalar_one_or_none()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        is_owner = note.created_by == current_user.id
        if is_owner:
            has_permission = await check_engagement_permission(
                current_user.id, note.engagement_id, Permission.NOTE_EDIT.value, db
            )
        else:
            has_permission = await check_engagement_permission(
                current_user.id, note.engagement_id, Permission.NOTE_EDIT_ANY.value, db
            )
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions."
            )

    if note_data.title is not None:
        note.title = note_data.title
    if note_data.content is not None:
        note.content = note_data.content
    if note_data.parent_id is not None:
        if note_data.parent_id == "":
            note.parent_id = None
        else:
            # Validate parent belongs to same engagement and isn't a circular reference
            if note_data.parent_id != note.id:
                parent_result = await db.execute(select(Note).where(Note.id == note_data.parent_id))
                parent_note = parent_result.scalar_one_or_none()
                if parent_note and parent_note.engagement_id == note.engagement_id:
                    note.parent_id = note_data.parent_id

    note.updated_by = current_user.id
    note.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(note)

    # Build specific change details
    change_parts = []
    if note_data.title is not None:
        change_parts.append(f"title: '{note.title}'")
    if note_data.content is not None:
        change_parts.append("content")
    change_details = f"Updated note '{note.title}'"
    if change_parts:
        change_details += f" — {', '.join(change_parts)}"

    # Log activity
    await create_activity_log(
        db,
        engagement_id=note.engagement_id,
        user_id=current_user.id,
        action="updated_note",
        resource_type="note",
        resource_id=note.id,
        resource_name=note.title,
        details=change_details
    )

    # Broadcast WebSocket event
    try:
        await manager.broadcast_to_resource("engagement", note.engagement_id, {
            "type": "note_updated",
            "note_id": note.id,
            "title": note.title,
            "user_id": current_user.id,
        })
    except Exception:
        pass

    # Notify mentioned users if content was updated
    if note_data.content is not None:
        from utils.collaboration import notify_mentions
        await notify_mentions(
            db=db,
            content=note.content or "",
            actor_id=current_user.id,
            title=f"You were mentioned in a note",
            message=f"{current_user.full_name or current_user.username} mentioned you in note '{note.title}'",
            link=f"/engagements/{note.engagement_id}?tab=notes&noteId={note.id}",
            engagement_id=note.engagement_id,
        )
        await db.commit()

    # Get usernames and profile photo
    from models.user import User as UserModel
    creator_result = await db.execute(select(UserModel.username, UserModel.profile_photo).where(UserModel.id == note.created_by))
    creator_row = creator_result.first()
    creator_username = creator_row[0] if creator_row else None
    creator_profile_photo = creator_row[1] if creator_row else None

    editor_result = await db.execute(select(UserModel.username).where(UserModel.id == note.updated_by))
    editor_username = editor_result.scalar_one_or_none()

    return _build_note_response(note, creator_username, creator_profile_photo, editor_username)


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    note_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a note."""
    result = await db.execute(select(Note).where(Note.id == note_id))
    note = result.scalar_one_or_none()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        is_owner = note.created_by == current_user.id
        if is_owner:
            has_permission = await check_engagement_permission(
                current_user.id, note.engagement_id, Permission.NOTE_DELETE.value, db
            )
        else:
            has_permission = await check_engagement_permission(
                current_user.id, note.engagement_id, Permission.NOTE_DELETE_ANY.value, db
            )
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions."
            )

    engagement_id = note.engagement_id
    note_title = note.title
    note_id_val = note.id

    await db.delete(note)
    await db.commit()

    # Log activity
    await create_activity_log(
        db,
        engagement_id=engagement_id,
        user_id=current_user.id,
        action="deleted_note",
        resource_type="note",
        resource_id=note_id_val,
        resource_name=note_title,
        details=f"Deleted note: {note_title}"
    )

    # Broadcast WebSocket event
    try:
        await manager.broadcast_to_resource("engagement", engagement_id, {
            "type": "note_deleted",
            "note_id": note_id_val,
            "user_id": current_user.id,
        })
    except Exception:
        pass


# ─── Note Link/Unlink endpoints ──────────────────────────────────────


async def _get_note_with_perm_check(note_id: str, db: AsyncSession, current_user: User):
    """Load a note and verify the user has edit permission."""
    result = await db.execute(select(Note).where(Note.id == note_id))
    note = result.scalar_one_or_none()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_permission = await check_engagement_permission(
            current_user.id, note.engagement_id, Permission.NOTE_EDIT.value, db
        )
        if not has_permission:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions.")

    return note


# ── Findings ──

@router.post("/notes/{note_id}/findings/{finding_id}", status_code=status.HTTP_204_NO_CONTENT)
async def link_note_to_finding(note_id: str, finding_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Link a note to a finding. Returns 409 if already linked."""
    note = await _get_note_with_perm_check(note_id, db, current_user)
    existing = await db.execute(select(NoteFinding).where(NoteFinding.note_id == note_id, NoteFinding.finding_id == finding_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Already linked")
    finding = (await db.execute(select(Finding).where(Finding.id == finding_id))).scalar_one_or_none()
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    if finding.engagement_id != note.engagement_id:
        raise HTTPException(status_code=400, detail="Finding belongs to a different engagement")
    db.add(NoteFinding(note_id=note_id, finding_id=finding_id))
    await db.commit()


@router.delete("/notes/{note_id}/findings/{finding_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_note_from_finding(note_id: str, finding_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Remove the link between a note and a finding."""
    await _get_note_with_perm_check(note_id, db, current_user)
    result = await db.execute(select(NoteFinding).where(NoteFinding.note_id == note_id, NoteFinding.finding_id == finding_id))
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    await db.delete(link)
    await db.commit()


# ── Test Cases ──

@router.post("/notes/{note_id}/testcases/{testcase_id}", status_code=status.HTTP_204_NO_CONTENT)
async def link_note_to_testcase(note_id: str, testcase_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Link a note to a test case. Returns 409 if already linked."""
    note = await _get_note_with_perm_check(note_id, db, current_user)
    existing = await db.execute(select(NoteTestCase).where(NoteTestCase.note_id == note_id, NoteTestCase.testcase_id == testcase_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Already linked")
    tc = (await db.execute(select(TestCase).where(TestCase.id == testcase_id))).scalar_one_or_none()
    if not tc:
        raise HTTPException(status_code=404, detail="Test case not found")
    if tc.engagement_id != note.engagement_id:
        raise HTTPException(status_code=400, detail="Test case belongs to a different engagement")
    db.add(NoteTestCase(note_id=note_id, testcase_id=testcase_id))
    await db.commit()


@router.delete("/notes/{note_id}/testcases/{testcase_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_note_from_testcase(note_id: str, testcase_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Remove the link between a note and a test case."""
    await _get_note_with_perm_check(note_id, db, current_user)
    result = await db.execute(select(NoteTestCase).where(NoteTestCase.note_id == note_id, NoteTestCase.testcase_id == testcase_id))
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    await db.delete(link)
    await db.commit()


# ── Assets ──

@router.post("/notes/{note_id}/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def link_note_to_asset(note_id: str, asset_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Link a note to an asset. Returns 409 if already linked."""
    note = await _get_note_with_perm_check(note_id, db, current_user)
    existing = await db.execute(select(NoteAsset).where(NoteAsset.note_id == note_id, NoteAsset.asset_id == asset_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Already linked")
    asset = (await db.execute(select(Asset).where(Asset.id == asset_id))).scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    if asset.engagement_id != note.engagement_id:
        raise HTTPException(status_code=400, detail="Asset belongs to a different engagement")
    db.add(NoteAsset(note_id=note_id, asset_id=asset_id))
    await db.commit()


@router.delete("/notes/{note_id}/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_note_from_asset(note_id: str, asset_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Remove the link between a note and an asset."""
    await _get_note_with_perm_check(note_id, db, current_user)
    result = await db.execute(select(NoteAsset).where(NoteAsset.note_id == note_id, NoteAsset.asset_id == asset_id))
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    await db.delete(link)
    await db.commit()


# ── Vault Items ──

@router.post("/notes/{note_id}/vault-items/{vault_item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def link_note_to_vault_item(note_id: str, vault_item_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Link a note to a vault item. Returns 409 if already linked."""
    note = await _get_note_with_perm_check(note_id, db, current_user)
    existing = await db.execute(select(NoteVaultItem).where(NoteVaultItem.note_id == note_id, NoteVaultItem.vault_item_id == vault_item_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Already linked")
    item = (await db.execute(select(VaultItem).where(VaultItem.id == vault_item_id))).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Vault item not found")
    if item.engagement_id != note.engagement_id:
        raise HTTPException(status_code=400, detail="Vault item belongs to a different engagement")
    db.add(NoteVaultItem(note_id=note_id, vault_item_id=vault_item_id))
    await db.commit()


@router.delete("/notes/{note_id}/vault-items/{vault_item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_note_from_vault_item(note_id: str, vault_item_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Remove the link between a note and a vault item."""
    await _get_note_with_perm_check(note_id, db, current_user)
    result = await db.execute(select(NoteVaultItem).where(NoteVaultItem.note_id == note_id, NoteVaultItem.vault_item_id == vault_item_id))
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    await db.delete(link)
    await db.commit()


# ── Cleanup Artifacts ──

@router.post("/notes/{note_id}/cleanup-artifacts/{cleanup_artifact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def link_note_to_cleanup_artifact(note_id: str, cleanup_artifact_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Link a note to a cleanup artifact. Returns 409 if already linked."""
    note = await _get_note_with_perm_check(note_id, db, current_user)
    existing = await db.execute(select(NoteCleanupArtifact).where(NoteCleanupArtifact.note_id == note_id, NoteCleanupArtifact.cleanup_artifact_id == cleanup_artifact_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Already linked")
    ca = (await db.execute(select(CleanupArtifact).where(CleanupArtifact.id == cleanup_artifact_id))).scalar_one_or_none()
    if not ca:
        raise HTTPException(status_code=404, detail="Cleanup artifact not found")
    if ca.engagement_id != note.engagement_id:
        raise HTTPException(status_code=400, detail="Cleanup artifact belongs to a different engagement")
    db.add(NoteCleanupArtifact(note_id=note_id, cleanup_artifact_id=cleanup_artifact_id))
    await db.commit()


@router.delete("/notes/{note_id}/cleanup-artifacts/{cleanup_artifact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_note_from_cleanup_artifact(note_id: str, cleanup_artifact_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Remove the link between a note and a cleanup artifact."""
    await _get_note_with_perm_check(note_id, db, current_user)
    result = await db.execute(select(NoteCleanupArtifact).where(NoteCleanupArtifact.note_id == note_id, NoteCleanupArtifact.cleanup_artifact_id == cleanup_artifact_id))
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    await db.delete(link)
    await db.commit()
