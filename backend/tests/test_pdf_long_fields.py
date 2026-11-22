"""A test case or cleanup field taller than a page must flow across pages
(and not be cut at 3000 characters) instead of aborting the PDF."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from models.report_layout import SectionType
from tests.test_report_content import _engagement, _section, _tc
from utils.report_generator import PDFReportGenerator

# ~140 short lines: far taller than one page, ~4k characters.
_LONG = "\n\n".join(f"step {i}: run the thing and capture output" for i in range(140))


@pytest.fixture(autouse=True)
def _uncompressed(monkeypatch):
    # Uncompressed content streams, so drawn text can be found in the bytes.
    from reportlab import rl_config
    monkeypatch.setattr(rl_config, "pageCompression", 0)


def _pdf_text(gen) -> str:
    out = gen.generate()
    data = out.getvalue() if hasattr(out, "getvalue") else out
    return data.decode("latin-1")


def _cleanup(**over):
    base = dict(id="ca1", title="Dropped implant", artifact_type="FILE", status="PENDING",
                location="/tmp/x", description="", cleanup_notes="", assets=[], findings=[],
                classification_level=None, classification_suffix=None)
    base.update(over)
    return SimpleNamespace(**base)


def test_long_testcase_field_flows_across_pages():
    gen = PDFReportGenerator(_engagement(), [_section(SectionType.TESTCASES, "Tests")], [],
                             [_tc("Long one", steps=_LONG)], [])
    text = _pdf_text(gen)
    assert "step 0:" in text and "step 139:" in text


def test_long_cleanup_field_flows_across_pages():
    gen = PDFReportGenerator(_engagement(), [_section(SectionType.CLEANUP_ARTIFACTS, "Cleanup")], [],
                             [], [_cleanup(cleanup_notes=_LONG)])
    text = _pdf_text(gen)
    assert "step 0:" in text and "step 139:" in text


@pytest.mark.parametrize("body", [
    " ".join(f"word{i}" for i in range(2500)),                          # one paragraph
    "```\n" + "\n".join(f"line {i} of output" for i in range(160)) + "\n```",  # one code block
])
def test_one_huge_block_in_a_testcase_still_builds(body):
    gen = PDFReportGenerator(_engagement(), [_section(SectionType.TESTCASES, "Tests")], [],
                             [_tc("Huge", notes=body)], [])
    assert _pdf_text(gen).startswith("%PDF")
