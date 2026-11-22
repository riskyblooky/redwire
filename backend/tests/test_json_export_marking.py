"""JSON/ZIP exports carry each item's effective classification and the
document banner, resolved as in the rendered formats."""

from __future__ import annotations

import io
import json
import uuid
import zipfile

from models.evidence import Evidence
from models.marking_profile import MarkingProfile, MarkingScheme
from models.report_layout import ReportLayout, ReportSection, SectionType
from tests.test_authz_boundaries import _make_engagement, _make_finding
from tests.test_report_content import _LEVELS


async def _export(client, db, eng, admin, fmt="json_layout_zip"):
    layout = ReportLayout(id=str(uuid.uuid4()), engagement_id=eng.id, name="L")
    db.add(layout)
    await db.flush()
    db.add(ReportSection(report_layout_id=layout.id, section_type=SectionType.TEXT, title="Intro",
                         content="hi", classification_level="U"))
    db.add(ReportSection(report_layout_id=layout.id, section_type=SectionType.FINDINGS, title="F"))
    await db.flush()
    r = await client.post("/reports/generate", json={
        "engagement_id": eng.id, "layout_id": layout.id, "report_format": fmt, "include_evidence": False})
    assert r.status_code == 200, r.text
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    return json.loads(zf.read("engagement_export.json"))


async def test_export_carries_effective_marks_and_banner(client, db_session, make_user, authenticate_as):
    admin = await make_user(role="admin")
    profile = MarkingProfile(id=str(uuid.uuid4()), name="IC", scheme=MarkingScheme.IC_DOD, levels=_LEVELS,
                             distribution_statement="Handle with care")
    db_session.add(profile)
    eng = await _make_engagement(db_session, marking_profile_id=profile.id,
                                 default_classification_level="C")
    secret = await _make_finding(db_session, eng, created_by=admin.id, title="S one",
                                 classification_level="S", classification_suffix="//REL")
    await _make_finding(db_session, eng, created_by=admin.id, title="Default one")
    db_session.add(Evidence(id=str(uuid.uuid4()), finding_id=secret.id, engagement_id=eng.id,
                            filename="k", original_filename="shot.png", file_path="k", file_size=1,
                            mime_type="image/png", created_by=admin.id))
    await db_session.flush()
    authenticate_as(admin)

    data = await _export(client, db_session, eng, admin)

    by_title = {f["title"]: f for f in data["findings"]}
    assert by_title["S one"]["classification"] == {"level": "S", "suffix": "//REL", "portion_mark": "(S//REL)"}
    assert by_title["Default one"]["classification"]["level"] == "C"        # engagement default
    assert by_title["S one"]["evidence"][0]["classification"]["level"] == "S"  # inherits finding
    assert data["layout"]["sections"][0]["classification"]["level"] == "U"
    assert data["marking"] == {"profile": "IC", "scheme": "IC_DOD", "banner": "SECRET",
                               "banner_level": "S", "distribution_statement": "Handle with care"}


async def test_export_without_a_profile_has_no_marking(client, db_session, make_user, authenticate_as):
    admin = await make_user(role="admin")
    eng = await _make_engagement(db_session)
    await _make_finding(db_session, eng, created_by=admin.id)
    authenticate_as(admin)

    data = await _export(client, db_session, eng, admin, fmt="json_zip")
    assert "marking" not in data
    assert data["findings"][0]["classification"] is None
