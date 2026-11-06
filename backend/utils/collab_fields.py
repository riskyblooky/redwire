"""
collab_fields.py — which record fields can be co-edited live, and who may.

Live editing of a rich-text field on the finding / test case / asset edit
pages and the report builder's text sections goes through
``/ws/yjs/field/{resource_type}/{resource_id}/{field}``: one Y.js room per
(record, field), relayed like notes. Unlike notes the server never persists
the room — the text is saved by the page's normal Save (the REST PUT), which
keeps versioning, the activity log, review gates and automation events tied
to an explicit save. See docs/collaborative-edit-pages.md.

Access mirrors the REST endpoints: view needs the resource's VIEW permission
on its engagement (admin / read-only admin / team lead bypass); edit needs
the same permission the PUT would demand (owner EDIT vs EDIT_ANY for
findings, test cases and assets; REPORT_GENERATE for report sections), with
only admin / team lead bypassing. Read-only admins can watch, not write.
"""

from dataclasses import dataclass
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
