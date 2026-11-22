"""Seeded finding / test case templates are published, so every user sees them."""

from __future__ import annotations

import contextlib

from sqlalchemy import select

import seed_defaults
from models.finding_template import FindingTemplate
from models.template_status import TemplateStatus
from models.testcase_template import TestCaseTemplate
from seed_templates import finding_templates
from seed_testcase_templates import testcase_templates


async def test_seeders_publish_what_they_add(db_session, make_user, monkeypatch):
    await make_user(role="admin")
    for model, data in ((FindingTemplate, finding_templates), (TestCaseTemplate, testcase_templates)):
        for row in (await db_session.execute(select(model).where(model.title.in_([t["title"] for t in data])))).scalars():
            await db_session.delete(row)
    await db_session.flush()

    @contextlib.asynccontextmanager
    async def _session():
        yield db_session
    monkeypatch.setattr(seed_defaults, "AsyncSessionLocal", _session)
    # As if these defaults were new in this release: none seeded yet.
    from models.auth_settings import AuthSetting
    for kind in ("finding_templates", "testcase_templates"):
        row = await db_session.get(AuthSetting, f"seeded_defaults:{kind}")
        if row is None:
            db_session.add(AuthSetting(key=f"seeded_defaults:{kind}", value="[]", is_encrypted=False))
        else:
            row.value = "[]"
    await db_session.flush()

    assert await seed_defaults.seed_finding_templates() == len(finding_templates)
    assert await seed_defaults.seed_testcase_templates() == len(testcase_templates)
    for model, data in ((FindingTemplate, finding_templates), (TestCaseTemplate, testcase_templates)):
        rows = (await db_session.execute(select(model).where(model.title.in_([t["title"] for t in data])))).scalars().all()
        assert len(rows) == len(data)
        assert {r.status for r in rows} == {TemplateStatus.PUBLISHED}
        assert all(r.published_at for r in rows)
