"""Unpublishing someone else's template / runbook puts it back in the review
queue (visible to managers), not a DRAFT only its creator can see."""

from __future__ import annotations

import uuid

import pytest

from models.finding_template import FindingTemplate
from models.runbook import Runbook
from models.template_status import TemplateStatus
from models.testcase_template import TestCaseTemplate


@pytest.mark.parametrize("prefix,make", [
    ("/templates", lambda by: FindingTemplate(id=str(uuid.uuid4()), title="T", description="d", created_by=by)),
    ("/testcase-templates", lambda by: TestCaseTemplate(id=str(uuid.uuid4()), title="T", category="c", description="d", created_by=by)),
    ("/runbooks", lambda by: Runbook(id=str(uuid.uuid4()), name="R", created_by=by)),
])
async def test_unpublish_keeps_it_visible_to_managers(prefix, make, client, db_session, make_user, authenticate_as):
    author = await make_user(role="operator")
    admin = await make_user(role="admin")
    for by in (author.id, None):           # another user's, and a seeded one
        row = make(by)
        row.status = TemplateStatus.PUBLISHED
        db_session.add(row)
        await db_session.flush()
        authenticate_as(admin)
        r = await client.post(f"{prefix}/{row.id}/unpublish")
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "SUBMITTED"
        assert (await client.get(f"{prefix}/{row.id}")).status_code == 200   # manager can still reach it

    own = make(admin.id)
    own.status = TemplateStatus.PUBLISHED
    db_session.add(own)
    await db_session.flush()
    assert (await client.post(f"{prefix}/{own.id}/unpublish")).json()["status"] == "DRAFT"
