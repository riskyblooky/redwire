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
    from utils.report_generator import PDFReportGenerator

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
