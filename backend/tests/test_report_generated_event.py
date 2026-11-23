"""report.generated fires once the report has rendered, not before: a
render that fails isn't announced."""

from __future__ import annotations

import pytest


@pytest.fixture
def captured(monkeypatch):
    from utils.event_bus import event_bus
    seen = []
    orig = event_bus.emit

    async def emit(name, payload=None, *a, **kw):
        if name == "report.generated":
            seen.append(payload)
        return await orig(name, payload, *a, **kw)
    monkeypatch.setattr(event_bus, "emit", emit)
    return seen


async def _setup(client, db_session, make_user, authenticate_as):
    import uuid
    from models.report_layout import ReportLayout, ReportSection, SectionType
    from tests.test_authz_boundaries import _make_engagement
    admin = await make_user(role="admin")
    eng = await _make_engagement(db_session, created_by=admin.id)
    layout = ReportLayout(id=str(uuid.uuid4()), engagement_id=eng.id, name="L")
    db_session.add(layout)
    await db_session.flush()
    db_session.add(ReportSection(report_layout_id=layout.id, section_type=SectionType.FINDINGS, title="F"))
    await db_session.flush()
    authenticate_as(admin)
    return eng, layout.id


async def test_announced_after_render(client, db_session, make_user, authenticate_as, captured):
    eng, layout_id = await _setup(client, db_session, make_user, authenticate_as)
    r = await client.post("/reports/generate", json={"engagement_id": eng.id, "layout_id": layout_id,
                                                     "report_format": "markdown"})
    assert r.status_code == 200, r.text
    assert [p["format"] for p in captured] == ["markdown"]


async def test_failed_render_is_not_announced(client, db_session, make_user, authenticate_as, captured, monkeypatch):
    import routers.reports as reports
    eng, layout_id = await _setup(client, db_session, make_user, authenticate_as)

    async def boom(generator):
        raise RuntimeError("render failed")
    monkeypatch.setattr(reports, "_render", boom)
    r = await client.post("/reports/generate", json={"engagement_id": eng.id, "layout_id": layout_id,
                                                     "report_format": "markdown"})
    assert r.status_code >= 400
    assert captured == []
