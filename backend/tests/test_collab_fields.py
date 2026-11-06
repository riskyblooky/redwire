"""Collaborative edit-page fields (utils/collab_fields.py): allow-list,
REST-equivalent view/edit gates, and non-persisting Y.js rooms."""

from __future__ import annotations

import uuid

import pytest

from models.engagement import Engagement
from models.finding import Finding
from models.report_layout import ReportLayout, ReportSection, SectionType
from utils import collab_fields
from utils.collab_fields import resolve_collab_target


@pytest.fixture
def perms(monkeypatch):
    """Grant engagement permissions from a {(user_id, perm)} set."""
    granted: set = set()

    async def _check(user_id, engagement_id, perm, db):
        return (user_id, perm) in granted
    monkeypatch.setattr(collab_fields, "check_engagement_permission", _check)
    return granted


async def _setup(db, make_user):
    author = await make_user(role="operator", username=f"cf_au_{uuid.uuid4().hex[:6]}")
    eng = Engagement(id=str(uuid.uuid4()), name="Collab", client_name="ACME",
                     engagement_type="external_pentest", created_by=author.id)
    db.add(eng)
    await db.flush()
    finding = Finding(id=str(uuid.uuid4()), engagement_id=eng.id, title="F", description="desc text",
                      severity="LOW", created_by=author.id)
    layout = ReportLayout(id=str(uuid.uuid4()), engagement_id=eng.id, name="L")
    db.add_all([finding, layout])
    await db.flush()
    text = ReportSection(id=str(uuid.uuid4()), report_layout_id=layout.id, title="Exec",
                         section_type=SectionType.TEXT, content="summary")
    table = ReportSection(id=str(uuid.uuid4()), report_layout_id=layout.id, title="Findings",
                          section_type=SectionType.FINDINGS, content="")
    db.add_all([text, table])
    await db.flush()
    return author, finding, text, table


async def test_field_allow_list_and_missing_records(db_session, make_user, perms):
    admin = await make_user(role="admin", username=f"cf_ad_{uuid.uuid4().hex[:6]}")
    _, finding, _, table = await _setup(db_session, make_user)
    assert await resolve_collab_target("finding", finding.id, "title", admin, db_session) is None
    assert await resolve_collab_target("finding", finding.id, "cvss_vector", admin, db_session) is None
    assert await resolve_collab_target("note", finding.id, "content", admin, db_session) is None
    assert await resolve_collab_target("finding", str(uuid.uuid4()), "description", admin, db_session) is None
    # Only text sections are collaborative.
    assert await resolve_collab_target("report_section", table.id, "content", admin, db_session) is None

    t = await resolve_collab_target("finding", finding.id, "description", admin, db_session)
    assert t.content == "desc text" and t.can_edit is True


async def test_finding_owner_vs_edit_any(db_session, make_user, perms):
    author, finding, _, _ = await _setup(db_session, make_user)
    other = await make_user(role="operator", username=f"cf_ot_{uuid.uuid4().hex[:6]}")

    assert await resolve_collab_target("finding", finding.id, "impact", other, db_session) is None  # no view

    perms.update({(author.id, "finding_view"), (author.id, "finding_edit"),
                  (other.id, "finding_view"), (other.id, "finding_edit")})
    assert (await resolve_collab_target("finding", finding.id, "impact", author, db_session)).can_edit is True
    # A non-author needs EDIT_ANY, like the PUT.
    assert (await resolve_collab_target("finding", finding.id, "impact", other, db_session)).can_edit is False
    perms.add((other.id, "finding_edit_any"))
    assert (await resolve_collab_target("finding", finding.id, "impact", other, db_session)).can_edit is True


async def test_read_only_admin_watches_but_cannot_write(db_session, make_user, perms):
    roa = await make_user(role="read_only_admin", username=f"cf_ro_{uuid.uuid4().hex[:6]}")
    _, finding, text, _ = await _setup(db_session, make_user)
    for rt, rid, field in (("finding", finding.id, "description"), ("report_section", text.id, "content")):
        t = await resolve_collab_target(rt, rid, field, roa, db_session)
        assert t is not None and t.can_edit is False


async def test_report_section_uses_report_perms(db_session, make_user, perms):
    _, _, text, _ = await _setup(db_session, make_user)
    op = await make_user(role="operator", username=f"cf_rp_{uuid.uuid4().hex[:6]}")
    assert await resolve_collab_target("report_section", text.id, "content", op, db_session) is None
    perms.add((op.id, "report_view"))
    t = await resolve_collab_target("report_section", text.id, "content", op, db_session)
    assert t.content == "summary" and t.can_edit is False
    perms.add((op.id, "report_generate"))
    assert (await resolve_collab_target("report_section", text.id, "content", op, db_session)).can_edit is True


async def test_field_room_never_requests_save():
    from utils.yjs_server import yjs_store

    key = collab_fields.room_key("finding", uuid.uuid4().hex, "description")
    room = yjs_store.get_or_create_room(key, persist=False)
    try:
        room._schedule_save()
        assert room._save_task is None
    finally:
        yjs_store.remove_room(key)
