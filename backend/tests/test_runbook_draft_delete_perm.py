"""Deleting someone else's draft runbook takes the runbook_delete
permission (like a published one), not the ADMIN role name."""

from __future__ import annotations

import uuid

from tests.test_security_center import _grant


async def _draft(db, owner):
    from models.runbook import Runbook
    from models.template_status import TemplateStatus
    rb = Runbook(id=str(uuid.uuid4()), name=f"rb-{uuid.uuid4().hex[:6]}", runbook_type="Recon",
                 status=TemplateStatus.DRAFT, created_by=owner.id)
    db.add(rb)
    await db.flush()
    return rb


async def test_draft_delete_follows_runbook_delete(client, db_session, make_user, authenticate_as):
    owner = await make_user(role="operator")
    stranger = await make_user(role="operator")
    cleaner = await make_user(role="operator")
    await _grant(db_session, cleaner, "runbook_delete")

    rb = await _draft(db_session, owner)
    authenticate_as(stranger)
    assert (await client.delete(f"/runbooks/{rb.id}")).status_code == 403
    authenticate_as(cleaner)
    assert (await client.delete(f"/runbooks/{rb.id}")).status_code == 204

    mine = await _draft(db_session, owner)
    authenticate_as(owner)
    assert (await client.delete(f"/runbooks/{mine.id}")).status_code == 204


async def test_template_draft_delete_follows_manage_permission(client, db_session, make_user, authenticate_as):
    from models.testcase_template import TestCaseTemplate
    from models.template_status import TemplateStatus
    owner, stranger, curator = [await make_user(role="operator") for _ in range(3)]
    await _grant(db_session, curator, "manage_testcase_templates")
    t = TestCaseTemplate(id=str(uuid.uuid4()), title="tpl", category="Recon", description="d",
                         status=TemplateStatus.DRAFT, created_by=owner.id)
    db_session.add(t)
    await db_session.flush()
    authenticate_as(stranger)
    assert (await client.delete(f"/testcase-templates/{t.id}")).status_code == 403
    authenticate_as(curator)
    assert (await client.delete(f"/testcase-templates/{t.id}")).status_code == 204
