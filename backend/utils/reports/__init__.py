"""Report generation, one module per output format.

- ``content.py``          what a report says (``build_report_document``): order,
                          ids, fields, statuses and portion marks, shared by
                          every format
- ``common.py``           theme lookups, severity colours, attack-chain helpers
- ``pdf/``                PDF (ReportLab), split by report part — see its __init__
- ``markdown_report.py``  Markdown
- ``html_report.py``      interactive single-file HTML
                          (template: ``backend/report_templates/interactive``)

JSON/ZIP exports are not rendered documents; they are built in
``routers/reports.py`` (``_do_generate_report``).
"""
from utils.reports.pdf import PDFReportGenerator
from utils.reports.markdown_report import MarkdownReportGenerator
from utils.reports.html_report import HTMLReportGenerator

__all__ = ["PDFReportGenerator", "MarkdownReportGenerator", "HTMLReportGenerator"]
