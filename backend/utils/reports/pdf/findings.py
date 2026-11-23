"""PDF report — finding cards, the findings section and embedded evidence images."""
import logging
import io
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Image, KeepTogether, Paragraph, Spacer, Table, TableStyle
from typing import Optional
from utils.marking import MarkedImage
from utils.reports.common import _SEV_BG_COLORS, _escape_xml, _t
from utils.reports.pdf.text import _bold_font

_log = logging.getLogger(__name__)


class FindingsMixin:
    """Finding cards, the findings section and embedded evidence images."""

    # ── Finding card ──────────────────────────────────────────────

    def _finding_card(self, item) -> tuple:
        """Flowables for a single finding, as ``(head, body)``.

        ``head`` = the header + meta tables (kept together by the caller);
        ``body`` = the field flowables, rendered full-width so long content
        (e.g. an oversized code block) paginates instead of crashing.
        """
        finding   = item.src
        idx       = int(item.ref[1:])
        sev_str   = item.severity
        sev_hex   = self._sev_hex(sev_str)
        sev_bg    = _SEV_BG_COLORS.get(sev_str, '#F8FAFC')
        font      = _t(self.theme, 'font_family')
        font_b    = _bold_font(font)
        body_c    = _t(self.theme, 'body_text_color')
        muted_c   = _t(self.theme, 'muted_text_color')
        dark      = _t(self.theme, 'secondary_color')

        show_bar = _t(self.theme, 'show_finding_severity_bar')
        show_bar = True if show_bar is None else bool(show_bar)

        elements = []

        def _label_para(label):
            return Paragraph(label, ParagraphStyle(
                name=f'L_{label}_{idx}', parent=self.styles['Label'],
                fontName=font_b, fontSize=8,
                textColor=colors.HexColor(muted_c),
            ))

        # -- Header row: number + title (severity now lives in the meta row)
        title_text = Paragraph(
            f'<font color="{sev_hex}">{item.ref}</font>  '
            f'{self._mark_prefix(item.mark)}{_escape_xml(item.title)}',
            ParagraphStyle(
                name=f'FT_{idx}', parent=self.styles['FindingTitle'],
                textColor=colors.white, fontSize=11, fontName=font_b, leading=15,
            )
        )
        header_t = Table([[title_text]], colWidths=[6.5 * inch])
        header_t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(dark)),
            ('LEFTPADDING', (0, 0), (-1, -1), 14),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 9),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(header_t)

        # -- Meta row: criticality + score (labelled by its scoring model).
        meta_val_style = ParagraphStyle(
            name=f'MV_{idx}', parent=self.styles['BodyText2'],
            fontSize=10, fontName=font_b, textColor=colors.HexColor(body_c), spaceAfter=0,
        )
        score_info = item.score
        cvss_text = score_info['text']
        meta_t = Table(
            [
                [_label_para('CRITICALITY'), _label_para(_escape_xml(score_info['label'].upper()))],
                [Paragraph(f'<font color="{sev_hex}">{sev_str}</font>', meta_val_style),
                 Paragraph(_escape_xml(cvss_text) if cvss_text else '—', meta_val_style)],
            ],
            colWidths=[2.4 * inch, 4.1 * inch],
        )
        meta_t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(sev_bg)),
            ('LEFTPADDING', (0, 0), (-1, -1), 14),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LINEAFTER', (0, 0), (0, -1), 0.25, colors.HexColor('#E2E8F0')),
            ('LINEBELOW', (0, 0), (-1, -1), 0.25, colors.HexColor('#E2E8F0')),
        ]))
        elements.append(meta_t)

        # -- Body: each field is a full-width, page-splittable block. Rendering
        # the body as top-level flowables (rather than nested table cells) lets
        # long content — e.g. a fenced code block taller than a page — paginate
        # instead of crashing ReportLab (a table row / KeepTogether can't be
        # split across a page boundary).
        body = []

        def _field_label(label):
            return Paragraph(label, ParagraphStyle(
                name=f'FL_{label}_{idx}', parent=self.styles['Label'],
                fontName=font_b, fontSize=8, leading=10,
                textColor=colors.HexColor(muted_c),
                spaceBefore=10, spaceAfter=3,
            ))

        def _add_row(label, value):
            """Plain (non-markdown) field — used for short scalar values."""
            if not value:
                return
            body.append(_field_label(label))
            body.append(Paragraph(_escape_xml(str(value)[:800]), ParagraphStyle(
                name=f'V_{label}_{idx}', parent=self.styles['BodyText2'],
                fontSize=9, textColor=colors.HexColor(body_c),
            )))

        def _add_md_row(label, value, max_chars=50000):
            """Markdown field — block-level markdown as top-level flowables."""
            if not value:
                return
            cell_body_style = ParagraphStyle(
                name=f'V_{label}_{idx}', parent=self.styles['BodyText2'],
                fontSize=9, textColor=colors.HexColor(body_c),
                spaceAfter=2,
            )
            # Inline images inherit the finding's effective mark.
            flowables = self._md_flowables(
                str(value), cell_body_style, item.mark, max_chars=max_chars,
                max_image_width=4.5 * inch, max_image_height=3.0 * inch,
            )
            if not flowables:
                return
            body.append(_field_label(label))
            body.extend(flowables)

        _add_row('AFFECTED ASSETS', ', '.join(a.name for a in item.assets) or 'N/A')
        # (The score is in the meta row alongside criticality.)

        for fld in item.fields:
            _add_md_row(fld.label.upper(), fld.markdown)

        # Admin-defined custom fields flagged show_in_report.
        for _cf_label, _cf_value in item.custom_fields:
            _add_row(_cf_label.upper(), _cf_value)

        # Attack path — the per-finding subgraph (test cases → finding → assets →
        # cleanup), mirroring the interactive report. Rendered only when there is
        # something beyond the finding node itself to show.
        if _t(self.theme, 'show_attack_graph') is not False:
            try:
                sg_nodes, sg_edges = self._finding_subgraph(finding)
                if len(sg_nodes) >= 2:
                    d = self._graph_drawing(sg_nodes, sg_edges, avail_w=6.4 * inch, compact=True)
                    if d is not None:
                        body.append(_field_label('ATTACK PATH'))
                        body.append(d)
            except Exception as _ge:
                _log.warning("attack-path graph render failed for finding %s: %s", finding.id, _ge)

        # `elements` holds the header + meta tables (small, page-safe) — the
        # "head" that should stay together; `body` holds the splittable field
        # flowables. Returned separately so the caller keeps the head together
        # while letting the body flow across pages.
        return elements, body

    def _render_findings_section(self, elements, section):
        elements.append(self._section_header_table(section.title.upper(), section))
        elements.append(Spacer(1, 16))

        if not self.findings:
            elements.append(Paragraph('No findings recorded for this engagement.', self.styles['BodyText2']))
            elements.append(Spacer(1, 12))
            return

        # ── Severity overview ──────────────────────────────────────
        elements.append(Paragraph(f"{self._heading_mark_prefix()}Severity Distribution", self.styles['SubSectionTitle']))
        # The aggregate chart carries the engagement-default mark.
        sev_above, sev_below = self._table_mark_flowables([self.doc.default_mark])
        for fl in sev_above:
            elements.append(fl)
        elements.append(self._severity_summary_table(self.doc.severity_counts))
        for fl in sev_below:
            elements.append(fl)
        elements.append(Spacer(1, 24))

        # ── Finding details ────────────────────────────────────────
        elements.append(Paragraph(f"{self._heading_mark_prefix()}Detailed Findings", self.styles['SubSectionTitle']))
        elements.append(Spacer(1, 8))

        for item in self.doc.findings:
            head, body = self._finding_card(item)
            above, below = self._table_mark_flowables([item.mark])
            elements.extend(above)
            # Keep the header + meta together so a finding never starts with just
            # its title stranded at a page bottom; the body flows/splits freely.
            elements.append(KeepTogether(head))
            elements.extend(body)
            elements.extend(below)
            elements.append(Spacer(1, 8))
            self._render_evidence(elements, item)
            elements.append(Spacer(1, 12))

    # ── Evidence helpers ──────────────────────────────────────────

    def _fetch_file_bytes(self, filename: str) -> Optional[bytes]:
        """Synchronously download a file from MinIO via the underlying boto3 client."""
        if self.storage is None:
            return None
        try:
            buf = io.BytesIO()
            self.storage.s3.download_fileobj(self.storage.bucket_name, filename, buf)
            return buf.getvalue()
        except Exception as exc:
            _log.warning(f'Could not fetch evidence file {filename!r}: {exc}')
            return None

    _IMAGE_MIMES = {'image/png', 'image/jpeg', 'image/gif', 'image/webp', 'image/bmp'}

    def _render_evidence(self, elements, item):
        """Embed images and list non-image attachments beneath a finding card."""
        evidence_list = item.evidence
        if not evidence_list:
            return

        font    = _t(self.theme, 'font_family')
        font_b  = _bold_font(font)
        muted   = _t(self.theme, 'muted_text_color')
        page_w  = 6.5 * inch
        max_img_h = 4.0 * inch

        # Section label
        ev_hdr = Table(
            [[Paragraph('EVIDENCE & ATTACHMENTS', ParagraphStyle(
                name='EvidenceHdrLabel', parent=self.styles['Normal'],
                fontSize=8, fontName=font_b,
                textColor=colors.HexColor(muted), letterSpacing=1,
            ))]],
            colWidths=[page_w],
        )
        ev_hdr.setStyle(TableStyle([
            ('TOPPADDING',    (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING',   (0, 0), (-1, -1), 0),
            ('LINEABOVE',     (0, 0), (-1, 0), 0.5, colors.HexColor('#E2E8F0')),
        ]))
        elements.append(ev_hdr)

        # Image mark placement policy (per the marking profile).
        anchors = self.marking.image_anchors if self.marking else []
        overlay_anchors = [a for a in anchors if a != 'CAPTION']
        show_filenames = _t(self.theme, 'show_evidence_filenames')

        for ev in evidence_list:
            mime = ev.mime

            # Effective mark for this evidence item (inherits the finding).
            ev_mark_raw = ev.mark.token
            ev_mark_esc = _escape_xml(ev_mark_raw)

            # Build caption (filename optional; mark-prefixed when CAPTION anchor).
            caption_parts = []
            if ev.description:
                caption_parts.append(ev.description)
            if show_filenames:
                caption_parts.append(f'[{ev.filename}]')
            caption_text = _escape_xml('  '.join(caption_parts))
            if ev_mark_esc and 'CAPTION' in anchors:
                caption_text = f'{ev_mark_esc}  {caption_text}'.strip()

            if mime in self._IMAGE_MIMES and self.storage:
                file_bytes = self._fetch_file_bytes(ev.storage_key)
                if file_bytes:
                    try:
                        img_stream = io.BytesIO(file_bytes)
                        # Default: marks sit OUTSIDE the image (strips above/below)
                        # so they never overlap content. stamp_images additionally
                        # burns the mark onto the bitmap (detached-screenshot safety).
                        do_stamp = bool(self.marking and self.marking.stamp_images and ev_mark_raw)
                        stamp_anchors = overlay_anchors or (['TOP_LEFT'] if do_stamp else [])
                        if do_stamp and stamp_anchors:
                            img = MarkedImage(img_stream, mark_text=ev_mark_raw,
                                              anchors=stamp_anchors, mark_fg=ev.mark.color)
                        else:
                            img = Image(img_stream)
                        iw, ih = img.imageWidth, img.imageHeight
                        if iw and ih:
                            scale = min(page_w / iw, max_img_h / ih, 1.0)
                            img.drawWidth  = iw * scale
                            img.drawHeight = ih * scale
                        img.hAlign = 'CENTER'
                        above_lines, below_lines = self._anchor_mark_lines(ev_mark_raw, overlay_anchors, ev.mark.color)
                        block = above_lines + [img] + below_lines
                        if caption_text:
                            block.append(Paragraph(caption_text, ParagraphStyle(
                                name=f'ImgCap_{ev.id}', parent=self.styles['Caption'],
                                alignment=1, spaceAfter=6,
                            )))
                        elements.append(KeepTogether(block))
                        elements.append(Spacer(1, 4))
                        continue
                    except Exception as exc:
                        _log.warning(f'Could not embed image {ev.storage_key!r}: {exc}')

            # Non-image or failed image → text attachment reference. Always carry
            # the mark (an attachment has no figure to stamp).
            attach_caption = f'{ev_mark_esc}  {caption_text}' if (ev_mark_esc and 'CAPTION' not in anchors) else caption_text
            elements.append(Paragraph(
                f'\U0001f4ce  {attach_caption}',
                ParagraphStyle(
                    name=f'AttachRef_{ev.id}', parent=self.styles['BodyText2'],
                    fontSize=9, textColor=colors.HexColor(muted), spaceAfter=4,
                    alignment=1,
                ),
            ))
