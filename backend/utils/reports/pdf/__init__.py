"""PDF report (ReportLab).

``generator.py`` holds ``PDFReportGenerator``: construction, the build loop
and the free-text section. Everything it draws comes from one mixin per part
of the report, so a change to one part stays in one file:

- ``cover.py``         cover page, header/footer, table of contents, section bars
- ``overview.py``      executive overview: severity table, donut, metric tiles
- ``findings.py``      finding cards and embedded evidence
- ``attack_graph.py``  per-finding attack paths and the full engagement graph
- ``sections.py``      test case and cleanup artifact sections
- ``marking.py``       portion-marking banners and heading/table marks
- ``styles.py``        paragraph styles derived from the theme
- ``text.py``          markdown → ReportLab markup and flowables
- ``page.py``          page sizes, logo decoding, doc template, numbered canvas
"""
from reportlab import rl_config

# Defence-in-depth: the PDF code never asks ReportLab to fetch a URL — every
# Image() flowable is built from a BytesIO we filled ourselves (MinIO download
# or markdown-image resolver). Locking trustedSchemes/trustedHosts down means
# that even if a future change lets unescaped user text reach Paragraph(), an
# `<img src="http://…">` / `file://…` in that text cannot make the report
# builder open a network connection or read a local file. Set before any
# submodule is imported, so no PDF code runs without it.
rl_config.trustedSchemes = []
rl_config.trustedHosts = []

from utils.reports.pdf.generator import PDFReportGenerator  # noqa: E402

__all__ = ["PDFReportGenerator"]
