"""Interactive HTML report generator (single self-contained file)."""
import logging
import base64
import io
import re
from utils.reports.content import _title_case, build_report_document
from utils.reports.common import _DEFAULTS, _SEV_COLORS, _SEV_THEME_KEY, _escape_xml, _resolve_chain_edges, _t

_log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# HTML Report Generator — self-contained, styled, marking-aware
# ═══════════════════════════════════════════════════════════════════

def _markdown_without_raw_html(text: str) -> str:
    """Render markdown with raw HTML switched off: Python-Markdown's HTML
    block preprocessor and inline-HTML pattern are removed, so author
    content can't inject <script> / <img onerror=…> (any "<…>" is output
    as escaped text) while all markdown syntax still works. Escaping the
    source first instead (the previous approach) double-escaped code
    ("&lt;" shown literally) and turned "> quote" into "&gt; quote".
    Dangerous URL schemes in links are stripped by the caller."""
    import markdown as _markdown
    md = _markdown.Markdown(extensions=['extra', 'sane_lists', 'nl2br'])
    md.preprocessors.deregister('html_block')
    md.inlinePatterns.deregister('html')
    return md.convert(text)


class HTMLReportGenerator:
    """Produces a single self-contained HTML document (inline CSS, base64
    images) — an editable deliverable clients can open in a browser or import
    into Word. Honors the theme palette and the marking profile (banner +
    portion marks)."""

    def __init__(self, engagement, sections, findings, testcases,
                 cleanup_artifacts=None, theme=None, storage=None,
                 markdown_image_map=None, marking_profile=None,
                 finding_custom_fields=None, chain_edges=None,
                 chain_vault_items=None):
        self.engagement = engagement
        self.theme = theme
        self.storage = storage
        self.doc = build_report_document(
            engagement, sections, findings, testcases, cleanup_artifacts,
            theme=theme, marking_profile=marking_profile,
            finding_custom_fields=finding_custom_fields,
            default_title=_DEFAULTS['cover_title'])
        # Operator-authored attack-chain edges (ChainLink) + touched vault
        # items. Empty → payload's `chain` is [] and the interactive graph
        # renders exactly as before.
        self.chain_edges = chain_edges or []
        self.chain_vault_items = chain_vault_items or {}
        self.markdown_image_map = markdown_image_map or {}
        self.marking = self.doc.marking

    def _sev_color(self, sev):
        key = _SEV_THEME_KEY.get((sev or '').upper())
        return (_t(self.theme, key) if key else None) or _SEV_COLORS.get((sev or '').upper(), '#64748B')

    # ── images ────────────────────────────────────────────────────
    def _data_uri(self, storage_key, content_type=None):
        if not self.storage or not storage_key:
            return None
        try:
            buf = io.BytesIO()
            self.storage.s3.download_fileobj(self.storage.bucket_name, storage_key, buf)
            b64 = base64.b64encode(buf.getvalue()).decode('ascii')
            return f'data:{content_type or "image/png"};base64,{b64}'
        except Exception as exc:
            _log.warning(f'HTML: could not embed image {storage_key!r}: {exc}')
            return None

    def _rewrite_inline_images(self, html_text):
        """Replace /markdown-images/<id> srcs with embedded data URIs."""
        if not self.markdown_image_map:
            return html_text

        def _repl(m):
            src = m.group(1)
            mm = re.search(r'/markdown-images/([^/?#"\']+)', src) or re.search(r'([0-9a-fA-F-]{16,})', src)
            if not mm:
                return m.group(0)
            image_id = mm.group(1).rsplit('.', 1)[0]
            info = self.markdown_image_map.get(image_id)
            if not info:
                return m.group(0)
            uri = self._data_uri(info.get('storage_key'), info.get('content_type'))
            return f'src="{uri}"' if uri else m.group(0)

        return re.sub(r'src="([^"]+)"', _repl, html_text)

    def _md(self, text):
        if not text:
            return ''
        try:
            html = _markdown_without_raw_html(str(text))
        except Exception:
            html = '<p>' + _escape_xml(str(text)).replace('\n', '<br/>') + '</p>'
        # Neutralize dangerous URL schemes markdown may emit from links like
        # [x](javascript:…). Our own embedded images (data: URIs) are added by
        # _rewrite_inline_images *after* this strip, so they are unaffected.
        html = re.sub(r'(?i)(href|src)\s*=\s*"\s*(?:javascript|vbscript|data):[^"]*"', r'\1="#"', html)
        return self._rewrite_inline_images(html)

    # ── generate ──────────────────────────────────────────────────

    # ── interactive report: build data + inject into the app template ──
    def _build_report_data(self):
        doc = self.doc
        eng = self.engagement
        fid = {f.id: f.ref for f in doc.findings}
        tid = {t.id: t.ref for t in doc.testcases}

        findings = []
        for f in doc.findings:
            ev = []
            for e in f.evidence:
                # 'cap' is raw text: the template escapes it (escaping here as
                # well showed "&amp;" in captions).
                item = {'cap': e.description or e.filename, 'mark': e.mark.token}
                uri = self._data_uri(e.storage_key, e.mime) if e.is_image else None
                if uri:
                    ev.append({**item, 'img': uri})
                else:
                    # Non-image evidence (or an image that couldn't be read)
                    # is listed by name rather than silently dropped.
                    ev.append({**item, 'file': e.filename, 'mime': e.mime})
            src, si = f.src, f.score
            findings.append({
                'id': f.ref, 'sev': f.severity.lower(), 'status': f.status_group,
                # 'cvss' stays numeric for sorting (nominal for categorical
                # models); 'num' says whether it is a real score to display.
                'cvss': (round(float(src.cvss_score), 1) if src.cvss_score is not None else 0),
                'num': si['numeric'], 'model': si['label'], 'outcome': si['outcome'] or '',
                'vec': src.cvss_vector or '—',
                'cwe': f.category,
                'mark': f.mark.token, 'title': f.title,
                'assets': [a.name for a in f.assets],
                'desc': self._md(src.description), 'impact': self._md(src.impact), 'biz': '',
                'steps': self._md(src.steps_to_reproduce), 'tech': self._md(src.technical_details),
                'remed': self._md(src.mitigations),
                'refs_html': self._md(src.references) if src.references else '',
                'custom': [[label, value] for label, value in f.custom_fields],
                'ev': ev,
            })

        testcases = []
        for t in doc.testcases:
            src = t.src
            testcases.append({
                'id': t.ref, 'label': t.title, 'status': t.status_label, 'mark': t.mark.token,
                'parent': t.parent_ref,
                'finds': [x.ref for x in t.findings if x.ref],
                'desc': self._md(src.description), 'steps': self._md(src.steps),
                'expected': self._md(src.expected_result), 'actual': self._md(src.actual_result),
                'notes': self._md(src.notes),
            })

        asset_map = {}
        for f in doc.findings:
            for a in f.assets:
                d = asset_map.setdefault(a.name, {'n': a.name, 'type': a.asset_type, 'sevs': {}})
                sev = f.severity.lower()
                d['sevs'][sev] = d['sevs'].get(sev, 0) + 1
        assets = list(asset_map.values())

        cleanup = []
        for ca in doc.cleanup:
            src = ca.src
            cleanup.append({
                't': ca.title, 'type': ca.artifact_type, 'sys': ca.location, 'owner': '',
                'status': ca.status, 'mark': ca.mark.token,
                'finding': ca.finding_refs[0] if ca.finding_refs else None,
                'asset': ca.assets[0] if ca.assets else None,
                'note': _escape_xml((src.description or src.cleanup_notes or '')[:400]),
            })

        rating = doc.findings[0].severity if doc.findings else 'INFO'
        cvsses = [f.src.cvss_score for f in doc.findings if f.src.cvss_score]
        score = max(cvsses) if cvsses else {'CRITICAL': 9.5, 'HIGH': 7.5, 'MEDIUM': 5.0,
                                             'LOW': 3.0, 'INFO': 0.5}.get(rating, 0)
        top = doc.findings[0].title if doc.findings else ''
        n = len(doc.findings)
        risk = {
            'rating': rating, 'score': round(float(score), 1),
            'caption': (f'Overall risk posture · driven by {top}' if top else 'Overall risk posture'),
            'summary_html': self._md(getattr(eng, 'description', None)) if getattr(eng, 'description', None) else '',
            'subtitle': f'{n} finding{"s" if n != 1 else ""} confirmed across this engagement.',
        }

        marking = {}
        if doc.banner:
            marking = {'banner': doc.banner.text,
                       'caption': (getattr(doc.marking, 'distribution_statement', '') or '')}

        window = ''
        sd, ed = getattr(eng, 'start_date', None), getattr(eng, 'end_date', None)
        if sd and ed:
            window = f'{sd.strftime("%b %d").replace(" 0", " ")} – {ed.strftime("%b %d, %Y").replace(" 0", " ")}'
        ref = _t(self.theme, 'report_reference') or ''
        ver = _t(self.theme, 'report_version') or ''
        ref_full = (f'{ref} · {ver}' if ref and ver else (ref or ver))
        team = len(getattr(eng, 'assigned_users', None) or [])
        eng_type = _title_case(getattr(eng, 'engagement_type', None)) or (eng.name or 'Engagement')

        fields = [['Client', eng.client_name or '—', None], ['Engagement', eng_type, None]]
        if window:
            fields.append(['Window', window, None])
        if ref_full:
            fields.append(['Report ref', ref_full, None])
        fields.append(['Prepared by', 'RedWire', None])
        if team:
            fields.append(['Team', f'{team} operator{"s" if team != 1 else ""}', None])
        if marking.get('banner'):
            fields.append(['Classification', marking['banner'], '#FFC000'])
        fields.append(['Findings', f'{n} confirmed', None])
        models = sorted({f.score['label'] for f in doc.findings})
        if models:
            fields.append(['Scoring', ' · '.join(models), None])

        meta = {
            'title': doc.title,
            'client': eng.client_name or eng.name, 'engagement': eng_type,
            'ref': ref_full, 'summary': '', 'fields': fields,
        }

        # Attack-chain overlay: resolve operator-authored ChainLink edges into
        # the interactive graph's display-id space (F##/T#; vault → 'vault-<id>').
        # Vault items aren't otherwise in the report, so surface the ones a chain
        # touches. When there are no chain edges this yields chain=[] and no
        # chainVault key.
        cv_nodes, c_edges, _ = _resolve_chain_edges(
            self.chain_edges, tid, fid, self.chain_vault_items)
        chain = [{'s': e['s'], 't': e['t'], 'note': e.get('note') or ''} for e in c_edges]

        # Scope & Method page: the engagement's scope and objectives plus the
        # layout's TEXT sections, in layout order, each with its mark.
        narrative = {
            'scope_html': self._md(getattr(eng, 'scope', None)),
            'objectives_html': self._md(getattr(eng, 'objectives', None)),
            'sections': [
                {'title': s.title, 'mark': s.heading_mark.token, 'html': self._md(s.content)}
                for s in doc.sections if s.kind == 'TEXT' and (s.content or '').strip()
            ],
        }

        data = {'meta': meta, 'risk': risk, 'marking': marking, 'findings': findings,
                'testcases': testcases, 'assets': assets, 'cleanup': cleanup, 'chain': chain,
                'narrative': narrative}
        if cv_nodes:
            data['chainVault'] = [
                {'id': v['id'], 'label': v['label'], 'itype': v['itype']} for v in cv_nodes
            ]
        return data

    def generate(self) -> str:
        """Portable, offline, interactive HTML report — a self-contained app whose
        data is injected as ``window.__REPORT__`` (markdown pre-rendered, images
        embedded as data URIs). Replaces the old single-page HTML clone."""
        import json as _json
        import os as _os
        data = self._build_report_data()
        # backend/report_templates — this file is backend/utils/reports/html_report.py
        tmpl_path = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))),
                                  'report_templates', 'interactive', 'report.template.html')
        with open(tmpl_path, 'r', encoding='utf-8') as fh:
            tmpl = fh.read()
        # Every "<" is written as \u003c (the same string to JSON and JS), so
        # no field can end the <script> element ("</script") or put the HTML
        # parser into its double-escaped state ("<!--" then "<script"), where
        # the real closing tag no longer ends the element.
        payload = 'window.__REPORT__ = ' + _json.dumps(data, ensure_ascii=False).replace('<', '\\u003c') + ';'
        return tmpl.replace('/*__REPORT_DATA__*/', payload, 1)
