"""PDF report — attack-path graphs: per-finding paths and the full engagement graph."""
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, Spacer, Table, TableStyle
from utils.reports.content import TESTCASE_STATUS_LABELS, _v, testcase_status
from utils.reports.common import _chain_component, _resolve_chain_edges, _t


class AttackGraphMixin:
    """Attack-path graphs: per-finding paths and the full engagement graph."""

    # ── Attack graph (native reportlab.graphics; mirrors the web report) ──
    #
    # Same node/edge model as the interactive HTML report's graph:
    #   nodes: testcase | finding | asset | cleanup
    #   edges: subtest (parent→child TC) · discovered (TC→finding)
    #          · impacts (finding→asset) · cleanup (asset|finding→cleanup)
    # Rendered with a longest-path (Sugiyama-style) column layout, drawn once
    # per finding as an "attack path", and once for the whole engagement when
    # the graph is small enough to stay legible on a static page.

    _ENT_ASSET = '#2563EB'      # blue-600  (light-theme entity colors)
    _ENT_TESTCASE = '#059669'   # emerald-600
    _ENT_CLEANUP = '#4D7C0F'    # lime-700
    _ENT_VAULT = '#CA8A04'      # yellow-600 (vault items in a chain)

    def _resolved_chain(self):
        """(vault_nodes, resolved_edges, dupe_pairs) for this engagement's
        chain edges, resolved into the PDF graph's identity scheme (test cases
        and findings keep their raw entity id; vault items become 'vault-<id>').
        Cached; empty when there are no chain edges."""
        if not hasattr(self, '_rc_cache'):
            tc_map = {t.id: t.id for t in self.testcases}
            f_map = {f.id: f.id for f in self.findings}
            self._rc_cache = _resolve_chain_edges(
                self.chain_edges, tc_map, f_map, self.chain_vault_items)
        return self._rc_cache

    def _chain_subgraph_nodes(self, comp, resolved, vault_nodes):
        """Build (nodes, edges) for the chain connected-component `comp`."""
        dF, dT = self._display_ids()
        tcmap = {t.id: t for t in self.testcases}
        fmap = {f.id: f for f in self.findings}
        vmap = {v['id']: v for v in vault_nodes}
        nodes = []
        for nid in comp:
            if nid in tcmap:
                t = tcmap[nid]
                nodes.append({'id': t.id, 'type': 'testcase', 'label': t.title or 'Test case',
                              'did': dT.get(t.id, ''), 'status': self._graph_status(t)})
            elif nid in fmap:
                f = fmap[nid]
                nodes.append({'id': f.id, 'type': 'finding', 'label': f.title or 'Untitled',
                              'did': dF.get(f.id, ''), 'sev': _v(f.severity).upper()})
            elif nid in vmap:
                v = vmap[nid]
                nodes.append({'id': v['id'], 'type': 'vault', 'label': v['label'], 'did': ''})
        edges = [e for e in resolved if e['s'] in comp and e['t'] in comp]
        return nodes, edges

    @staticmethod
    def _graph_status(tc):
        st = testcase_status(tc)
        return None if st == 'none' else TESTCASE_STATUS_LABELS[st]

    def _display_ids(self):
        return ({f.id: f.ref for f in self.doc.findings},
                {t.id: t.ref for t in self.doc.testcases})

    def _node_color(self, n):
        t = n['type']
        if t == 'finding':
            return self._sev_hex(n.get('sev', 'INFO'))
        if t == 'testcase':
            return self._ENT_TESTCASE
        if t == 'asset':
            return self._ENT_ASSET
        if t == 'vault':
            return self._ENT_VAULT
        return self._ENT_CLEANUP

    def _edge_style(self, kind):
        """(hex, width, dash-or-None) — matches the web EDGE_STYLE mapping.

        'discovered' uses the web brand purple (not the PDF theme primary, which
        defaults to the same red as Critical severity and would read as a severity
        cue on an edge)."""
        return {
            'subtest':    ('#94A3B8', 1.0, None),
            'discovered': ('#7C3AED', 1.6, None),
            'impacts':    ('#60A5FA', 1.0, (3, 3)),
            'cleanup':    ('#B45309', 1.0, (2, 3)),
            # Operator-authored causal chain edge — indigo-400, matches the
            # app attack graph's CHAIN_EDGE_COLOR.
            'chain':      ('#818CF8', 2.0, None),
        }.get(kind, ('#94A3B8', 1.0, None))

    def _finding_subgraph(self, f):
        """(nodes, edges) for one finding.

        When the finding participates in operator-authored chain edges, the
        subgraph is the chain's connected component (test cases / findings /
        vault items reachable via ChainLink), drawn with the causal chain
        edges. Otherwise it falls back — unchanged — to the association-derived
        subgraph: the test cases that discovered it (with their parent chain),
        the finding, its assets, and its cleanup artifacts."""
        vault_nodes, resolved, _ = self._resolved_chain()
        if resolved:
            comp = _chain_component(f.id, resolved)
            if comp:
                return self._chain_subgraph_nodes(comp, resolved, vault_nodes)
        dF, dT = self._display_ids()
        tcmap = {t.id: t for t in self.testcases}
        nodes, edges, seen = [], [], set()
        for t in self.testcases:
            if any(x.id == f.id for x in (t.findings or [])):
                edges.append({'s': t.id, 't': f.id, 'kind': 'discovered'})
                cur = t
                while cur is not None:
                    if cur.id not in seen:
                        seen.add(cur.id)
                        nodes.append({'id': cur.id, 'type': 'testcase', 'label': cur.title or 'Test case',
                                      'did': dT.get(cur.id, ''), 'status': self._graph_status(cur)})
                    if cur.parent_id and cur.parent_id in tcmap:
                        edges.append({'s': cur.parent_id, 't': cur.id, 'kind': 'subtest'})
                        cur = tcmap[cur.parent_id]
                    else:
                        cur = None
        nodes.append({'id': f.id, 'type': 'finding', 'label': f.title or 'Untitled',
                      'did': dF.get(f.id, ''), 'sev': _v(f.severity).upper()})
        f_asset_names = {a.name for a in (f.assets or [])}
        seen_assets = set()
        for a in (f.assets or []):
            if a.name in seen_assets:
                continue
            seen_assets.add(a.name)
            nodes.append({'id': 'a-' + a.name, 'type': 'asset', 'label': a.name, 'did': ''})
            edges.append({'s': f.id, 't': 'a-' + a.name, 'kind': 'impacts'})
        for i, ca in enumerate(self.cleanup_artifacts):
            if any(x.id == f.id for x in (ca.findings or [])):
                cid = 'sC%d' % i
                nodes.append({'id': cid, 'type': 'cleanup', 'label': ca.title or 'Artifact', 'did': ''})
                linked_a = next((x.name for x in (ca.assets or [])), None)
                src = ('a-' + linked_a) if (linked_a and linked_a in f_asset_names) else f.id
                edges.append({'s': src, 't': cid, 'kind': 'cleanup'})
        return nodes, edges

    def _build_full_graph(self):
        """(nodes, edges) for the whole engagement — the web buildGraph()."""
        dF, dT = self._display_ids()
        nodes, edges, aid = [], [], {}
        for t in self.testcases:
            nodes.append({'id': t.id, 'type': 'testcase', 'label': t.title or 'Test case',
                          'did': dT.get(t.id, ''), 'status': self._graph_status(t)})
        for f in self.findings:
            nodes.append({'id': f.id, 'type': 'finding', 'label': f.title or 'Untitled',
                          'did': dF.get(f.id, ''), 'sev': _v(f.severity).upper()})
        asset_names = []
        for f in self.findings:
            for a in (f.assets or []):
                if a.name not in aid:
                    aid[a.name] = 'A%d' % len(asset_names)
                    asset_names.append(a.name)
        for name in asset_names:
            nodes.append({'id': aid[name], 'type': 'asset', 'label': name, 'did': ''})
        for i, ca in enumerate(self.cleanup_artifacts):
            cid = 'C%d' % i
            nodes.append({'id': cid, 'type': 'cleanup', 'label': ca.title or 'Artifact', 'did': ''})
            linked_a = next((x.name for x in (ca.assets or [])), None)
            linked_f = next((x.id for x in (ca.findings or [])), None)
            src = aid.get(linked_a) if (linked_a and linked_a in aid) else linked_f
            if src:
                edges.append({'s': src, 't': cid, 'kind': 'cleanup'})
        for t in self.testcases:
            if getattr(t, 'parent_id', None):
                edges.append({'s': t.parent_id, 't': t.id, 'kind': 'subtest'})
            for f in (t.findings or []):
                edges.append({'s': t.id, 't': f.id, 'kind': 'discovered'})
        for f in self.findings:
            for a in (f.assets or []):
                if a.name in aid:
                    edges.append({'s': f.id, 't': aid[a.name], 'kind': 'impacts'})
        # A filtered report (severity / status / …) keeps only the matching
        # findings, but test cases and cleanup artifacts still link to the
        # dropped ones: drop edges whose ends aren't drawn, or layering
        # raised KeyError and the PDF 500'd.
        drawn = {n['id'] for n in nodes}
        edges = [e for e in edges if e['s'] in drawn and e['t'] in drawn]
        # ── Chain overlay ──
        # Overlay operator-authored causal chain edges (and any vault items
        # they touch) onto the association-derived graph, mirroring the app's
        # attack graph. No chain edges → this is a no-op and the graph is
        # byte-identical to before.
        vault_nodes, resolved, dupes = self._resolved_chain()
        if resolved:
            existing_ids = {n['id'] for n in nodes}
            for v in vault_nodes:
                if v['id'] not in existing_ids:
                    nodes.append({'id': v['id'], 'type': 'vault', 'label': v['label'], 'did': ''})
                    existing_ids.add(v['id'])
            # Drop a factual 'discovered' edge duplicated by a same-direction
            # chain edge (same fact twice); a reverse-direction chain edge is a
            # distinct relationship and leaves 'discovered' intact.
            if dupes:
                edges = [e for e in edges
                         if not (e.get('kind') == 'discovered' and (e['s'], e['t']) in dupes)]
            for e in resolved:
                if e['s'] in existing_ids and e['t'] in existing_ids:
                    edges.append(e)
        return nodes, edges

    @staticmethod
    def _layer_nodes(nodes, edges):
        """Longest-path layering (the web renderGraph topo pass). Returns id→layer."""
        inD = {n['id']: 0 for n in nodes}
        outA = {n['id']: [] for n in nodes}
        for e in edges:
            if e['s'] not in outA or e['t'] not in inD:
                continue  # dangling edge: nothing to layer
            outA[e['s']].append(e['t'])
            inD[e['t']] += 1
        layer = {n['id']: 0 for n in nodes}
        ind = dict(inD)
        q = [nid for nid in inD if ind[nid] == 0]
        while q:
            nid = q.pop(0)
            for t in outA[nid]:
                if layer[nid] + 1 > layer[t]:
                    layer[t] = layer[nid] + 1
                ind[t] -= 1
                if ind[t] == 0:
                    q.append(t)
        return layer

    def _draw_node(self, group, n, NW, NH, compact):
        from reportlab.graphics.shapes import Rect, String, Circle
        col = self._node_color(n)
        x, y = n['x'], n['y']
        muted = _t(self.theme, 'muted_text_color')
        body = _t(self.theme, 'body_text_color')
        group.add(Rect(x, y, NW, NH, rx=4, ry=4, fillColor=colors.white,
                       strokeColor=colors.HexColor(col), strokeWidth=1.1))
        group.add(Rect(x, y, 3.2, NH, fillColor=colors.HexColor(col), strokeColor=None))
        group.add(Circle(x + 12, y + NH - 10, 3, fillColor=colors.HexColor(col), strokeColor=None))
        did = n.get('did', '')
        top = did
        if n['type'] == 'testcase' and n.get('status'):
            top = f'{did} · {n["status"]}' if did else n['status']
        if top:
            group.add(String(x + 20, y + NH - 12.5, top, fontSize=6.3, fontName='Helvetica-Bold',
                             fillColor=colors.HexColor(muted)))
        lim = 20 if compact else 24
        lbl = n['label'] if len(n['label']) <= lim else n['label'][:lim - 1] + '…'
        group.add(String(x + 8, y + 6, lbl, fontSize=7.4,
                         fillColor=colors.HexColor(body)))

    def _draw_edge(self, group, a, b, kind, NW, NH):
        from reportlab.graphics.shapes import Path
        hexc, w, dash = self._edge_style(kind)
        sx, sy = a['x'] + NW, a['y'] + NH / 2.0
        tx, ty = b['x'], b['y'] + NH / 2.0
        mx = (sx + tx) / 2.0
        p = Path(strokeColor=colors.HexColor(hexc), strokeWidth=w, fillColor=None)
        if dash:
            p.strokeDashArray = list(dash)
        p.moveTo(sx, sy)
        p.curveTo(mx, sy, mx, ty, tx, ty)
        group.add(p)

    def _graph_drawing(self, nodes, edges, avail_w, compact=True):
        from reportlab.graphics.shapes import Drawing, Group
        if not nodes:
            return None
        byId = {n['id']: n for n in nodes}
        edges = [e for e in edges if e['s'] in byId and e['t'] in byId]
        layer = self._layer_nodes(nodes, edges)
        NW = 118 if compact else 138
        NH = 30
        hgap, vgap = 32, 12
        cols = {}
        for n in nodes:
            cols.setdefault(layer[n['id']], []).append(n)
        max_layer = max(layer.values()) if layer else 0
        max_rows = max((len(v) for v in cols.values()), default=1)
        w_nat = (max_layer + 1) * NW + max_layer * hgap
        h_nat = max_rows * NH + (max_rows - 1) * vgap
        for L, ns in cols.items():
            col_h = len(ns) * NH + (len(ns) - 1) * vgap
            y0 = (h_nat - col_h) / 2.0
            for i, n in enumerate(ns):
                n['x'] = L * (NW + hgap)
                n['y'] = h_nat - y0 - NH - i * (NH + vgap)
        g = Group()
        for e in edges:
            self._draw_edge(g, byId[e['s']], byId[e['t']], e['kind'], NW, NH)
        for n in nodes:
            self._draw_node(g, n, NW, NH, compact)
        s = min(1.0, avail_w / w_nat) if w_nat > avail_w else 1.0
        if s != 1.0:
            g.transform = (s, 0, 0, s, 0, 0)
        d = Drawing(w_nat * s, h_nat * s)
        d.add(g)
        return d

    def _graph_legend(self):
        body = _t(self.theme, 'body_text_color')
        muted = _t(self.theme, 'muted_text_color')
        items = [(self._ENT_TESTCASE, 'Test case'), ('#64748B', 'Finding'),
                 (self._ENT_ASSET, 'Asset'), (self._ENT_CLEANUP, 'Cleanup')]
        cells = [Paragraph(f'<font color="{c}">■</font> {t}', ParagraphStyle(
                    name=f'_gl_{t}', parent=self.styles['Normal'], fontSize=8,
                    textColor=colors.HexColor(body), leading=10)) for c, t in items]
        edgep = Paragraph(
            'test&#8594;finding <b>discovered</b> · finding&#8943;asset <b>impacts</b> · &#8594;<b>cleanup</b>',
            ParagraphStyle(name='_gle', parent=self.styles['Normal'], fontSize=7.3,
                           textColor=colors.HexColor(muted), leading=10))
        t = Table([cells + [edgep]], colWidths=[0.9 * inch] * 4 + [2.9 * inch])
        t.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                               ('LEFTPADDING', (0, 0), (-1, -1), 0),
                               ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2)]))
        return t

    def _render_attack_graph_section(self, elements):
        """Full-engagement attack graph — only when small enough to read on paper.
        Larger engagements rely on the per-finding attack paths inside each card."""
        nodes, edges = self._build_full_graph()
        if len(nodes) < 3:
            return
        # Legibility gate: a static page can't pan/zoom, so a tall finding column
        # becomes an unreadable stripe. Skip past a threshold; per-finding paths cover it.
        layer = self._layer_nodes(nodes, edges)
        cols = {}
        for n in nodes:
            cols.setdefault(layer[n['id']], []).append(n['id'])
        # The width auto-scales to the page, so the tallest column (not the node
        # total) is what governs legibility on a static page. Past ~12 rows the
        # graph becomes a cramped stripe — skip it; the per-finding paths carry it.
        max_rows = max((len(v) for v in cols.values()), default=1)
        if max_rows > 12:
            return
        elements.append(PageBreak())
        elements.append(self._section_header_table('ATTACK GRAPH', None))
        elements.append(Spacer(1, 12))
        elements.append(self._graph_legend())
        elements.append(Spacer(1, 14))
        d = self._graph_drawing(nodes, edges, avail_w=6.5 * inch, compact=False)
        if d is not None:
            elements.append(d)
        elements.append(Spacer(1, 24))
