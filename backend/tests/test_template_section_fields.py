"""Report layout template sections accept only their own columns: the
classification / page-break fields (engagement layouts only) are a 422,
not silently dropped."""

from __future__ import annotations


async def test_template_section_rejects_layout_only_fields(client, make_user, authenticate_as):
    authenticate_as(await make_user(role="admin"))
    base = {"name": "T", "sections": [{"section_type": "text", "title": "Intro", "content": "x"}]}
    ok = await client.post("/report-layout-templates", json=base)
    assert ok.status_code in (200, 201), ok.text
    assert "page_break_before" not in ok.json()["sections"][0]

    bad = {"name": "T2", "sections": [{"section_type": "text", "title": "Intro", "page_break_before": True}]}
    r = await client.post("/report-layout-templates", json=bad)
    assert r.status_code == 422, (r.status_code, r.text)
