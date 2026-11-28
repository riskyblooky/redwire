import { describe, expect, it } from 'vitest';
import {
    adoptSavedSectionIds, toSectionPayload, toTemplateSectionPayload, type LocalSection,
} from '@/lib/report-sections';

const sec = (over: Partial<LocalSection> = {}): LocalSection => ({
    localId: 'local_x', section_type: 'text', title: 'T', content: '<p>c</p>', ...over,
});

describe('toSectionPayload', () => {
    it('numbers sort_order by list position and keeps existing ids', () => {
        const payload = toSectionPayload([
            sec({ localId: 'l1', id: 'srv-1', title: 'Exec summary' }),
            sec({ localId: 'l2', section_type: 'findings', title: 'Findings', content: '' }),
            sec({ localId: 'l3', id: 'srv-3', section_type: 'cleanup_artifacts', title: 'Cleanup' }),
        ]);
        expect(payload.map(p => p.sort_order)).toEqual([0, 1, 2]);
        expect(payload.map(p => p.id)).toEqual(['srv-1', undefined, 'srv-3']);
        expect(payload.map(p => p.section_type)).toEqual(['text', 'findings', 'cleanup_artifacts']);
        expect(payload[1]).toMatchObject({ title: 'Findings', content: '' });
    });

    it('never sends the client-only localId', () => {
        const [p] = toSectionPayload([sec({ id: 'a' })]);
        expect(p).not.toHaveProperty('localId');
    });

    it('normalises empty markings to null and page break to a boolean', () => {
        const [a, b, c] = toSectionPayload([
            sec(),
            sec({ classification_level: '', classification_suffix: '', page_break_before: undefined }),
            sec({ classification_level: 'SECRET', classification_suffix: 'NOFORN', page_break_before: true }),
        ]);
        expect(a).toMatchObject({ classification_level: null, classification_suffix: null, page_break_before: false });
        expect(b).toMatchObject({ classification_level: null, classification_suffix: null, page_break_before: false });
        expect(c).toMatchObject({ classification_level: 'SECRET', classification_suffix: 'NOFORN', page_break_before: true });
    });

    it('maps an empty layout to an empty list', () => {
        expect(toSectionPayload([])).toEqual([]);
    });
});

describe('toTemplateSectionPayload', () => {
    it('sends only type, title, content and order', () => {
        const out = toTemplateSectionPayload([
            sec({ id: 'srv-1', classification_level: 'SECRET', page_break_before: true }),
            sec({ section_type: 'testcases', title: 'TCs', content: '' }),
        ]);
        expect(out).toEqual([
            { section_type: 'text', title: 'T', content: '<p>c</p>', sort_order: 0 },
            { section_type: 'testcases', title: 'TCs', content: '', sort_order: 1 },
        ]);
    });
});

describe('adoptSavedSectionIds', () => {
    it('assigns server ids by sort_order, whatever order the response lists them in', () => {
        const local = [sec({ localId: 'l1', id: 'old-1' }), sec({ localId: 'l2' }), sec({ localId: 'l3' })];
        const saved = [
            { id: 'new-3', sort_order: 2 },
            { id: 'old-1', sort_order: 0 },
            { id: 'new-2', sort_order: 1 },
        ];
        const out = adoptSavedSectionIds(local, saved);
        expect(out.map(s => [s.localId, s.id])).toEqual([['l1', 'old-1'], ['l2', 'new-2'], ['l3', 'new-3']]);
    });

    it('keeps the local id where the response has no section at that position', () => {
        const out = adoptSavedSectionIds([sec({ id: 'a' }), sec({ id: 'b' })], [{ id: 'z', sort_order: 0 }]);
        expect(out.map(s => s.id)).toEqual(['z', 'b']);
        expect(adoptSavedSectionIds([sec({ id: 'keep' })], []).map(s => s.id)).toEqual(['keep']);
    });

    it('does not mutate the sections or the response', () => {
        const local = [sec({ localId: 'l1' })];
        const saved = [{ id: 'b', sort_order: 1 }, { id: 'a', sort_order: 0 }];
        const out = adoptSavedSectionIds(local, saved);
        expect(local[0].id).toBeUndefined();
        expect(out[0]).not.toBe(local[0]);
        expect(saved.map(s => s.id)).toEqual(['b', 'a']);
    });

    it('round-trips with toSectionPayload: what was sent is what is adopted', () => {
        const local = [sec({ localId: 'l1' }), sec({ localId: 'l2', id: 'kept' })];
        const sent = toSectionPayload(local);
        const response = sent.map((p, i) => ({ id: p.id ?? `gen-${i}`, sort_order: p.sort_order }));
        expect(adoptSavedSectionIds(local, response).map(s => s.id)).toEqual(['gen-0', 'kept']);
    });
});
