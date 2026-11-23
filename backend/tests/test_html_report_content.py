"""Interactive HTML report: every page shows this engagement's data. No
sample content from the template design survives, text sections and
non-image evidence are included, and the page declares its charset."""

from __future__ import annotations

import json
import re

from models.report_layout import SectionType
from tests.test_report_content import _engagement, _evidence, _finding, _profile, _section, _tc
from utils.reports import HTMLReportGenerator


def _build(**kw):
    eng = _engagement(default="C")
    eng.scope, eng.objectives, eng.description = "Scope **text**", "Get DA", ""
    secs = [_section(SectionType.TEXT, "Methodology"), _section(SectionType.FINDINGS, "Findings"),
            _section(SectionType.TEXT, "Empty")]
    secs[0].content, secs[2].content = "We used **PTES**.", "  "
    f = _finding("SQLi", "CRITICAL", evidence=[_evidence(original_filename="dump.pcap",
                                                         description="traffic & creds")])
    gen = HTMLReportGenerator(eng, secs, [f], [_tc("T1")], [], None, marking_profile=_profile())
    return gen


def _payload(html: str) -> dict:
    m = re.search(r"window\.__REPORT__ = (.*?);\n", html, re.S)
    return json.loads(m.group(1).replace("<\\/", "</"))


def test_text_sections_scope_and_objectives_are_in_the_payload():
    data = _payload(_build().generate())
    n = data["narrative"]
    assert "<strong>text</strong>" in n["scope_html"] and "Get DA" in n["objectives_html"]
    assert [(s["title"], s["mark"]) for s in n["sections"]] == [("Methodology", "(U)")]
    assert "<strong>PTES</strong>" in n["sections"][0]["html"]


def test_non_image_evidence_is_listed_with_a_raw_caption():
    [ev] = _payload(_build().generate())["findings"][0]["ev"]
    assert ev["file"] == "dump.pcap" and "img" not in ev
    assert ev["cap"] == "traffic & creds"          # escaped once, by the template
    assert ev["mark"] == "(C)"


def test_no_template_sample_content_ships():
    html = _build().generate()
    for sample in ("Meridian", "meridianfinancial", "RW-2026-0431", "Okafor", "TLP:AMBER+STRICT",
                   "How one login became customer data", "1 of 7 fixed", "Kickoff &amp; recon"):
        assert sample not in html, sample
    assert html.startswith('<meta charset="utf-8">')
