"""
collab_fields.py — which record fields can be co-edited live, and who may.

Live editing of a rich-text field on the finding / test case / asset edit
pages and the report builder's text sections goes through
``/ws/yjs/field/{resource_type}/{resource_id}/{field}``: one Y.js room per
(record, field), relayed like notes. Unlike notes the server never persists
the room on a timer; instead the editing client sends the field's Markdown
a moment after the author stops typing (and when the editor closes), and
``save_collab_field`` writes that one field. Each live-editing session (see
LIVE_SESSION_WINDOW) gets one version snapshot and one activity-log entry,
like notes. Only text is written here: status changes, review gates,
notifications and automation events stay on the page's Save (the REST PUT).
See docs/collaborative-edit-pages.md §4.2.

Access mirrors the REST endpoints: view needs the resource's VIEW permission
on its engagement (admin / read-only admin / team lead bypass); edit needs
the same permission the PUT would demand (owner EDIT vs EDIT_ANY for
findings, test cases and assets; REPORT_GENERATE for report sections), with
only admin / team lead bypassing. Read-only admins can watch, not write.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.rbac import check_engagement_permission
from models.permission import Permission
from models.user import User, UserRole

COLLAB_FIELDS = {
    "finding": {"description", "impact", "steps_to_reproduce", "technical_details", "mitigations", "references"},
    "testcase": {"description", "steps", "expected_result", "notes", "actual_result"},
    "asset": {"description", "notes"},
    "report_section": {"content"},
}

logger = logging.getLogger(__name__)

# One version snapshot + activity-log entry per field per window of live
# editing (matches notes' NOTE_UPDATE_LOG_DEBOUNCE).
LIVE_SESSION_WINDOW = timedelta(minutes=10)

_FIELD_LABELS = {
    "description": "Description", "impact": "Impact", "steps_to_reproduce": "Steps to Reproduce",
    "technical_details": "Technical Details", "mitigations": "Mitigations", "references": "References",
    "steps": "Steps", "expected_result": "Expected Result", "notes": "Notes",
    "actual_result": "Actual Result", "content": "Content",
}

_VIEW_BYPASS = (UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD)
_EDIT_BYPASS = (UserRole.ADMIN, UserRole.TEAM_LEAD)

# resource_type → (VIEW, EDIT (own), EDIT_ANY)
_RECORD_PERMS = {
    "finding": (Permission.FINDING_VIEW, Permission.FINDING_EDIT, Permission.FINDING_EDIT_ANY),
    "testcase": (Permission.TESTCASE_VIEW, Permission.TESTCASE_EDIT, Permission.TESTCASE_EDIT_ANY),
    "asset": (Permission.ASSET_VIEW, Permission.ASSET_EDIT, Permission.ASSET_EDIT_ANY),
}


@dataclass
class CollabTarget:
    engagement_id: str
    content: str
    can_edit: bool


def room_key(resource_type: str, resource_id: str, field: str) -> str:
    # Note rooms are keyed by the bare note id; the colons keep these apart.
    return f"{resource_type}:{resource_id}:{field}"


async def _load(resource_type: str, resource_id: str, field: str, db: AsyncSession):
    """(engagement_id, content, owner_id) for the field, or None."""
    if resource_type == "report_section":
        from models.report_layout import ReportLayout, ReportSection, SectionType
        row = (await db.execute(
            select(ReportSection, ReportLayout.engagement_id)
            .join(ReportLayout, ReportLayout.id == ReportSection.report_layout_id)
            .where(ReportSection.id == resource_id)
        )).first()
        if row is None or row[0].section_type != SectionType.TEXT:
            return None
        return row[1], row[0].content or "", None

    if resource_type == "finding":
        from models.finding import Finding as model
    elif resource_type == "testcase":
        from models.testcase import TestCase as model
    else:
        from models.asset import Asset as model
    obj = (await db.execute(select(model).where(model.id == resource_id))).scalar_one_or_none()
    if obj is None:
        return None
    return obj.engagement_id, getattr(obj, field) or "", obj.created_by


async def resolve_collab_target(
    resource_type: str, resource_id: str, field: str, user: User, db: AsyncSession,
) -> Optional[CollabTarget]:
    """The field's current text and the caller's edit right, or None when the
    field isn't collaborative, the record doesn't exist, or the caller can't
    view it (callers close the socket without saying which)."""
    if field not in COLLAB_FIELDS.get(resource_type, ()):
        return None
    loaded = await _load(resource_type, resource_id, field, db)
    if loaded is None:
        return None
    engagement_id, content, owner_id = loaded

    if resource_type == "report_section":
        view_perm, edit_perm = Permission.REPORT_VIEW, Permission.REPORT_GENERATE
    else:
        view_perm, own_perm, any_perm = _RECORD_PERMS[resource_type]
        edit_perm = own_perm if owner_id == user.id else any_perm

    if user.role not in _VIEW_BYPASS and not await check_engagement_permission(
        user.id, engagement_id, view_perm.value, db
    ):
        return None
    can_edit = user.role in _EDIT_BYPASS or await check_engagement_permission(
        user.id, engagement_id, edit_perm.value, db
    )
    return CollabTarget(engagement_id=engagement_id, content=content, can_edit=can_edit)


def _record_model(resource_type: str):
    if resource_type == "finding":
        from models.finding import Finding
        return Finding
    if resource_type == "testcase":
        from models.testcase import TestCase
        return TestCase
    from models.asset import Asset
    return Asset


async def save_collab_field(
    resource_type: str, resource_id: str, field: str, content: str, user_id: str,
) -> bool:
    """Persist one live-edited field (the caller has checked the user may
    edit it). Returns False if the record is gone. The first write of a
    live-editing session snapshots the pre-edit state and logs the edit; the
    rest of the session just writes."""
    if field not in COLLAB_FIELDS.get(resource_type, ()):
        return False
    from database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        if resource_type == "report_section":
            from models.report_layout import ReportSection
            sec = (await db.execute(
                select(ReportSection).where(ReportSection.id == resource_id)
            )).scalar_one_or_none()
            if sec is None:
                return False
            if (sec.content or "") != content:
                sec.content = content
                await db.commit()
            return True

        model = _record_model(resource_type)
        obj = (await db.execute(select(model).where(model.id == resource_id))).scalar_one_or_none()
        if obj is None:
            return False
        if (getattr(obj, field) or "") == content:
            return True

        from models.discussion import ActivityLog
        from utils.versioning import create_version_snapshot

        action = f"updated_{resource_type}"
        details = f"Edited {_FIELD_LABELS.get(field, field)} (live)"
        in_session = (await db.execute(
            select(ActivityLog.id).where(
                ActivityLog.resource_type == resource_type,
                ActivityLog.resource_id == resource_id,
                ActivityLog.action == action,
                ActivityLog.details == details,
                ActivityLog.created_at >= datetime.utcnow() - LIVE_SESSION_WINDOW,
            ).limit(1)
        )).scalar_one_or_none() is not None

        if not in_session:
            # Pre-edit state, so history and the activity feed's diff show
            # what the session changed.
            await create_version_snapshot(db, obj, resource_type, {field: content}, user_id)
        if resource_type == "finding":
            from utils.peer_review import withdraw_approvals_if_reviewed_changed
            await withdraw_approvals_if_reviewed_changed(db, resource_id, [field])
        setattr(obj, field, content)
        obj.updated_by = user_id
        engagement_id = obj.engagement_id
        name = getattr(obj, "title", None) or getattr(obj, "name", None)
        await db.commit()

        if not in_session:
            from utils.collaboration import create_activity_log
            await create_activity_log(
                db, engagement_id=engagement_id, user_id=user_id, action=action,
                resource_type=resource_type, resource_id=resource_id,
                resource_name=name, details=details,
            )
        await _announce_field_saved(resource_type, resource_id, field, user_id)
        return True


async def _announce_field_saved(resource_type: str, resource_id: str, field: str, user_id: str) -> None:
    """Tell the record's own presence channel (/ws/{type}/{id} — the view and
    edit pages, gated on the record's engagement at connect) that a field
    changed, so pages showing it but not in its live room refetch. The
    activity-log broadcast only fires once per live session, so it can't
    carry this. Best effort."""
    try:
        from utils.collaboration import manager
        await manager.broadcast_to_resource(resource_type, resource_id, {
            "type": "record_updated", "resource_type": resource_type,
            "resource_id": resource_id, "field": field, "user_id": user_id,
        })
    except Exception as e:  # noqa: BLE001
        logger.warning("collab field: record_updated broadcast failed: %s", e)


async def assert_no_other_live_editors(resource_type: str, resource_id: str, user_id: str) -> None:
    """409 if someone else has one of the record's text fields open live.

    A version restore rewrites the stored text, but an open live editor still
    holds the old text and would auto-save it back on the next keystroke."""
    from fastapi import HTTPException, status as http_status
    from utils.ws_bus import bus
    from utils.yjs_server import yjs_store

    others = 0
    for field in COLLAB_FIELDS.get(resource_type, ()):
        key = room_key(resource_type, resource_id, field)
        members = await bus.presence_list("yjs", key)
        if members is None:  # no registry — this worker's sockets only
            room = yjs_store.rooms.get(key)
            ids = list(room.client_user_ids.values()) if room else []
        else:
            ids = [m.get("id") for m in members]
        others += sum(1 for uid in ids if uid and uid != user_id)
    if others:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="Someone else is editing this live. Restore once they've left the edit page "
                   "— otherwise their open editor would save the old text back.",
        )
