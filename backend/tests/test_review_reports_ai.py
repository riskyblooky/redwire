"""Regressions for the 2026-11 review's medium items in reports, AI
settings, search and dashboard widgets."""

from __future__ import annotations

import pytest


async def test_ai_compaction_settings_round_trip(client, make_user, authenticate_as):
    authenticate_as(await make_user(role="admin"))
    put = await client.put("/ai/settings", json={
        "ai_max_context_tokens": "32000", "ai_compact_keep_recent_turns": "6", "ai_compact_threshold_pct": "60"})
    assert put.status_code == 200, put.text

    got = (await client.get("/ai/settings")).json()
    assert (got["ai_max_context_tokens"], got["ai_compact_keep_recent_turns"], got["ai_compact_threshold_pct"]) \
        == ("32000", "6", "60")


@pytest.mark.parametrize("font", ["Helvetica", "Times-Roman", "Courier"])
def test_pdf_builds_in_each_theme_font(font):
    """Bold faces were built as font + "-Bold", which doesn't exist for Times."""
    from types import SimpleNamespace
    from tests.test_report_content import _SECTIONS, _engagement, _finding, _tc
    from utils.reports import PDFReportGenerator

    theme = SimpleNamespace(font_family=font)
    pdf = PDFReportGenerator(_engagement(), _SECTIONS, [_finding("F", description="**bold** text")],
                             [_tc("T", description="# Heading\n\nbody")], [], theme=theme).generate()
    data = pdf.getvalue() if hasattr(pdf, "getvalue") else pdf
    assert data[:4] == b"%PDF"


def test_theme_font_is_one_of_the_offered_families():
    from pydantic import ValidationError
    from schemas.report_theme import ReportThemeUpdate
    assert ReportThemeUpdate(font_family="Times-Roman").font_family == "Times-Roman"
    with pytest.raises(ValidationError):
        ReportThemeUpdate(font_family="Comic Sans")


async def test_zip_export_keeps_same_named_evidence_apart(client, db_session, make_user, authenticate_as, monkeypatch):
    """The evidence loop reused the engagement's safe_name (so the ZIP was
    named after the last file), and two files with one name overwrote."""
    import io, json, uuid, zipfile
    from models.evidence import Evidence
    from models.report_layout import ReportLayout, ReportSection, SectionType
    from tests.test_authz_boundaries import _make_engagement, _make_finding
    from utils.storage import storage_service

    async def _download(name):
        return f"bytes of {name}".encode()
    monkeypatch.setattr(storage_service, "download_file", _download)

    admin = await make_user(role="admin")
    eng = await _make_engagement(db_session, name="Op Zip")
    finding = await _make_finding(db_session, eng, created_by=admin.id)
    for key in ("k1", "k2"):
        db_session.add(Evidence(id=str(uuid.uuid4()), finding_id=finding.id, engagement_id=eng.id,
                                filename=key, original_filename="shot.png", file_path=key, file_size=1,
                                mime_type="image/png", created_by=admin.id))
    layout = ReportLayout(id=str(uuid.uuid4()), engagement_id=eng.id, name="L")
    db_session.add(layout)
    await db_session.flush()
    db_session.add(ReportSection(report_layout_id=layout.id, section_type=SectionType.FINDINGS, title="F"))
    await db_session.flush()
    authenticate_as(admin)

    r = await client.post("/reports/generate", json={"engagement_id": eng.id, "layout_id": layout.id,
                                                     "report_format": "json_zip"})

    assert r.status_code == 200, r.text
    assert "Export_Op_Zip.zip" in r.headers["content-disposition"]
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    shots = sorted(n for n in zf.namelist() if n.endswith("shot.png"))
    assert len(shots) == 2 and len(set(shots)) == 2
    assert sorted(zf.read(n) for n in shots) == [b"bytes of k1", b"bytes of k2"]
    [data_name] = [n for n in zf.namelist() if n.endswith(".json")]
    paths = {e["attachment_path"] for f in json.loads(zf.read(data_name))["findings"] for e in f["evidence"]}
    assert paths == set(shots)
