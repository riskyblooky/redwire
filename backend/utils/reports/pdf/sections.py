"""PDF report — test case and cleanup artifact sections."""
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import KeepTogether, Paragraph, Spacer, Table, TableStyle
from utils.reports.common import _escape_xml, _t
from utils.reports.pdf.text import _bold_font


class SectionsMixin:
    """Test case and cleanup artifact sections."""

    # ── Table section renderers ───────────────────────────────────

    # Test-case status → (key, label, hex). Darker shades read well on white paper.
    _TC_STATUS = {
        'pass': ('✓ Pass', '#16A34A'),
        'fail': ('✗ Fail', '#DC2626'),
        'exec': ('Executed · no verdict', '#2563EB'),
        'none': ('Not executed', '#64748B'),
    }

    def _render_testcases_section(self, elements, section):
        """Hierarchical test plan: one detail block per test case (parent → child),
        with a pass/fail status chip and markdown-rendered steps / expected /
        actual / notes and the findings each test discovered — modeled on the
        cleanup-artifact detail renderer."""
        elements.append(self._section_header_table(section.title.upper(), section))
        elements.append(Spacer(1, 16))

        if not self.testcases:
            elements.append(Paragraph('No test cases recorded.', self.styles['BodyText2']))
            elements.append(Spacer(1, 12))
            return

        font   = _t(self.theme, 'font_family')
        font_b = _bold_font(font)
        dark   = _t(self.theme, 'secondary_color')
        muted  = _t(self.theme, 'muted_text_color')

        # summary line
        summ = self.doc.testcase_summary
        total = summ['total']
        elements.append(Paragraph(
            f'{total} test case{"s" if total != 1 else ""} · {summ["executed"]} executed · '
            f'{summ["passed"]} passed · {summ["failed"]} failed',
            ParagraphStyle(name='TCSummary', parent=self.styles['BodyText2'], fontSize=9.5,
                           textColor=colors.HexColor(muted), spaceAfter=14)))

        for item in self.doc.testcases:
            t, depth, num = item.src, item.depth, item.number
            det_rows = []

            def _label(label):
                return Paragraph(label, ParagraphStyle(
                    name=f'TCL_{t.id}_{label}', parent=self.styles['Label'],
                    fontSize=8, fontName=font_b, textColor=colors.HexColor(muted)))

            def _add(label, val):
                if not val:
                    return
                det_rows.append([_label(label), Paragraph(_escape_xml(str(val)[:800]), ParagraphStyle(
                    name=f'TCV_{t.id}_{label}', parent=self.styles['BodyText2'], fontSize=9))])

            def _add_md(label, val, max_chars=50000):
                if not val:
                    return
                cs = ParagraphStyle(name=f'TCM_{t.id}_{label}', parent=self.styles['BodyText2'],
                                    fontSize=9, spaceAfter=2)
                fls = self._md_flowables(
                    str(val), cs, item.mark, max_chars=max_chars,
                    max_image_width=4.5 * inch, max_image_height=3.0 * inch)
                if fls:
                    det_rows.append([_label(label), fls])

            if item.category:
                _add('CATEGORY', item.category)
            for fld in item.fields:
                _add_md(fld.label.upper(), fld.markdown)
            if item.assets:
                _add('ASSETS', ', '.join(item.assets))
            if item.findings:
                fnames = ', '.join(
                    f'{_escape_xml(f.title)} ({f.severity.title()})' for f in item.findings)
                det_rows.append([_label('DISCOVERED FINDINGS'), Paragraph(fnames, ParagraphStyle(
                    name=f'TCF_{t.id}', parent=self.styles['BodyText2'], fontSize=9))])

            sc_label, sc_hex = self._TC_STATUS[item.status]
            indent = 14 + depth * 16
            title_p = Paragraph(f'{num}&nbsp;&nbsp;{self._mark_prefix(item.mark)}{_escape_xml(item.title)}',
                ParagraphStyle(name=f'TCTitle_{t.id}', parent=self.styles['FindingTitle'], fontSize=10))
            status_p = Paragraph(f'<b>{sc_label}</b>', ParagraphStyle(
                name=f'TCStatus_{t.id}', parent=self.styles['Normal'], fontSize=9, fontName=font_b,
                textColor=colors.HexColor(sc_hex), alignment=2))
            header = Table([[title_p, status_p]], colWidths=[5.0 * inch, 1.5 * inch])
            header.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(dark)),
                ('LEFTPADDING', (0, 0), (0, 0), indent),
                ('RIGHTPADDING', (1, 0), (1, 0), 12),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LINEBEFORE', (0, 0), (0, 0), 4, colors.HexColor(sc_hex)),
            ]))

            tc_above, tc_below = self._table_mark_flowables([item.mark])
            block = [header]
            if det_rows:
                # splitInRow: a field taller than a page splits inside its row
                # (a row that can't split aborted the whole PDF with LayoutError).
                body_t = Table(det_rows, colWidths=[1.3 * inch, 5.2 * inch], splitInRow=1)
                body_t.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('TOPPADDING', (0, 0), (-1, -1), 6),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                    ('LEFTPADDING', (0, 0), (0, -1), indent),
                    ('LEFTPADDING', (1, 0), (1, -1), 8),
                    ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
                    ('LINEBELOW', (0, 0), (-1, -2), 0.25, colors.HexColor('#E2E8F0')),
                    ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
                ]))
                block.append(body_t)
            elements.append(KeepTogether(tc_above + block + tc_below))
            elements.append(Spacer(1, 10))
        elements.append(Spacer(1, 10))

    def _render_cleanup_artifacts_section(self, elements, section):
        elements.append(self._section_header_table(section.title.upper(), section))
        elements.append(Spacer(1, 16))

        if not self.cleanup_artifacts:
            elements.append(Paragraph('No cleanup artifacts recorded.', self.styles['BodyText2']))
            elements.append(Spacer(1, 12))
            return

        font   = _t(self.theme, 'font_family')
        font_b = _bold_font(font)
        dark   = _t(self.theme, 'secondary_color')

        header_style = ParagraphStyle(
            name='CAHeader', parent=self.styles['Normal'],
            fontSize=9, fontName=font_b, textColor=colors.white,
        )
        cell_style = ParagraphStyle(
            name='CACell', parent=self.styles['Normal'],
            fontSize=9, fontName=font, textColor=colors.HexColor(_t(self.theme, 'body_text_color')),
        )

        per_row = bool(self.marking and self.marking.per_row)
        zebra, alt_bg, grid = self._table_style_tokens()

        header_cells = [
            Paragraph('ARTIFACT', header_style),
            Paragraph('TYPE', header_style),
            Paragraph('STATUS', header_style),
            Paragraph('LOCATION', header_style),
        ]
        if per_row:
            header_cells = [self._row_mark_cell(header=True)] + header_cells
        rows = [header_cells]

        for ca in self.doc.cleanup:
            cells = [
                Paragraph(_escape_xml(ca.title[:60]), cell_style),
                Paragraph(_escape_xml(ca.artifact_type), cell_style),
                Paragraph(_escape_xml(ca.status), cell_style),
                Paragraph(_escape_xml((ca.location or 'N/A')[:50]), cell_style),
            ]
            if per_row:
                cells = [self._row_mark_cell(ca.mark)] + cells
            rows.append(cells)

        if per_row:
            col_widths = [0.55 * inch, 1.95 * inch, 1.2 * inch, 1.15 * inch, 1.65 * inch]
        else:
            col_widths = [2.3 * inch, 1.3 * inch, 1.2 * inch, 1.7 * inch]

        t = Table(rows, colWidths=col_widths, repeatRows=1)
        style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(dark)),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('LINEBELOW', (0, 0), (-1, -1), 0.25, grid),
        ]
        if zebra:
            style.append(('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, alt_bg]))
        t.setStyle(TableStyle(style))

        above, below = self._table_mark_flowables([ca.mark for ca in self.doc.cleanup])
        for fl in above:
            elements.append(fl)
        elements.append(t)
        for fl in below:
            elements.append(fl)

        # Detailed entries
        elements.append(Spacer(1, 24))
        for idx, ca in enumerate(self.doc.cleanup, 1):
            det_rows = []

            def _label(label):
                return Paragraph(label, ParagraphStyle(
                    name=f'CAL_{idx}_{label}', parent=self.styles['Label'],
                    fontSize=8, fontName=font_b,
                    textColor=colors.HexColor(_t(self.theme, 'muted_text_color')),
                ))

            def _add(label, val):
                """Plain row — short scalar values."""
                if not val:
                    return
                det_rows.append([
                    _label(label),
                    Paragraph(_escape_xml(str(val)[:600]), ParagraphStyle(
                        name=f'CAV_{idx}_{label}', parent=self.styles['BodyText2'],
                        fontSize=9,
                    )),
                ])

            def _add_md(label, val, max_chars=50000):
                """Markdown row — renders block-level markdown into the cell."""
                if not val:
                    return
                cell_style = ParagraphStyle(
                    name=f'CAV_{idx}_{label}', parent=self.styles['BodyText2'],
                    fontSize=9, spaceAfter=2,
                )
                flowables = self._md_flowables(
                    str(val), cell_style, ca.mark, max_chars=max_chars,
                    max_image_width=4.5 * inch, max_image_height=3.0 * inch,
                )
                if not flowables:
                    return
                det_rows.append([_label(label), flowables])

            _add('TYPE', ca.artifact_type)
            _add('STATUS', ca.status)
            if ca.location:
                _add('LOCATION', ca.location)
            for fld in ca.fields:
                _add_md(fld.label.upper(), fld.markdown)
            if ca.assets:
                _add('ASSETS', ', '.join(ca.assets))

            if det_rows:
                header = Table(
                    [[Paragraph(f'{idx}. {self._mark_prefix(ca.mark)}{_escape_xml(ca.title)}', ParagraphStyle(
                        name=f'CATitle_{idx}', parent=self.styles['FindingTitle'],
                        fontSize=10,
                    ))]],
                    colWidths=[6.5 * inch],
                )
                header.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(dark)),
                    ('LEFTPADDING', (0, 0), (-1, -1), 14),
                    ('TOPPADDING', (0, 0), (-1, -1), 8),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                    ('LINEBEFORE', (0, 0), (0, 0), 4, colors.HexColor(_t(self.theme, 'primary_color'))),
                ]))
                # splitInRow: a field taller than a page splits inside its row
                # (a row that can't split aborted the whole PDF with LayoutError).
                body_t = Table(det_rows, colWidths=[1.3 * inch, 5.2 * inch], splitInRow=1)
                body_t.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('TOPPADDING', (0, 0), (-1, -1), 6),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                    ('LEFTPADDING', (0, 0), (0, -1), 14),
                    ('LEFTPADDING', (1, 0), (1, -1), 8),
                    ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
                    ('LINEBELOW', (0, 0), (-1, -2), 0.25, colors.HexColor('#E2E8F0')),
                    ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
                ]))
                # Each cleanup entry is its own table → mark per the table guide.
                ca_above, ca_below = self._table_mark_flowables([ca.mark])
                elements.append(KeepTogether(ca_above + [header, body_t] + ca_below))
                elements.append(Spacer(1, 12))
