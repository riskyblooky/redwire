"""A test case template used by a runbook can't be deleted out from under it."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from models.runbook import Runbook, RunbookItem
from models.template_status import TemplateStatus
from models.testcase_template import TestCaseTemplate


def _u() -> str:
    return str(uuid.uuid4())


async def _template(db, admin):
    t = TestCaseTemplate(id=_u(), title=f"tpl-{_u()[:8]}", category="web", description="d",
                         created_by=admin.id, status=TemplateStatus.PUBLISHED)
    db.add(t)
    await db.flush()
    return t


async def test_delete_in_use_template_is_refused(client, db_session, make_user, authenticate_as):
    admin = await make_user(role="admin")
    authenticate_as(admin)
    tpl = await _template(db_session, admin)
    rb = Runbook(id=_u(), name="Initial access", runbook_type="Recon", created_by=admin.id)
    db_session.add(rb)
    await db_session.flush()
    db_session.add(RunbookItem(id=_u(), runbook_id=rb.id, template_id=tpl.id, sort_order=0))
    await db_session.flush()

    r = await client.delete(f"/testcase-templates/{tpl.id}")
    assert r.status_code == 409, r.text
    assert "Initial access" in r.json()["detail"]
    items = (await db_session.execute(select(func.count()).select_from(RunbookItem)
                                      .where(RunbookItem.runbook_id == rb.id))).scalar_one()
    assert items == 1


async def test_delete_unused_template_still_works(client, db_session, make_user, authenticate_as):
    admin = await make_user(role="admin")
    authenticate_as(admin)
    tpl = await _template(db_session, admin)
    r = await client.delete(f"/testcase-templates/{tpl.id}")
    assert r.status_code == 204, r.text
