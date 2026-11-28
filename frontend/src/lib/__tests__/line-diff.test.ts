import { describe, expect, it } from 'vitest';
import { computeLineDiff } from '@/lib/line-diff';

type Op = ReturnType<typeof computeLineDiff>[number];

const oldSide = (d: Op[]) => d.filter(o => o.type !== 'add').map(o => o.text).join('\n');
const newSide = (d: Op[]) => d.filter(o => o.type !== 'remove').map(o => o.text).join('\n');
const same = (d: Op[]) => d.filter(o => o.type === 'same').length;

describe('computeLineDiff', () => {
    it('marks every line same for identical text', () => {
        expect(computeLineDiff('a\nb\nc', 'a\nb\nc')).toEqual([
            { type: 'same', text: 'a' },
            { type: 'same', text: 'b' },
            { type: 'same', text: 'c' },
        ]);
    });

    it('shows a changed line as remove then add, in place', () => {
        expect(computeLineDiff('a\nb\nc', 'a\nx\nc')).toEqual([
            { type: 'same', text: 'a' },
            { type: 'remove', text: 'b' },
            { type: 'add', text: 'x' },
            { type: 'same', text: 'c' },
        ]);
    });

    it('detects pure insertions and deletions', () => {
        expect(computeLineDiff('a\nc', 'a\nb\nc')).toEqual([
            { type: 'same', text: 'a' },
            { type: 'add', text: 'b' },
            { type: 'same', text: 'c' },
        ]);
        expect(computeLineDiff('a\nb\nc', 'a\nc')).toEqual([
            { type: 'same', text: 'a' },
            { type: 'remove', text: 'b' },
            { type: 'same', text: 'c' },
        ]);
    });

    it('keeps the longest common subsequence (minimal edit)', () => {
        // LCS of these is a,b,d,f (length 4).
        const d = computeLineDiff('a\nb\nc\nd\ne\nf', 'a\nb\nd\nx\nf');
        expect(same(d)).toBe(4);
        expect(d.filter(o => o.type === 'remove').map(o => o.text)).toEqual(['c', 'e']);
        expect(d.filter(o => o.type === 'add').map(o => o.text)).toEqual(['x']);
    });

    it('reconstructs both sides exactly', () => {
        const cases: [string, string][] = [
            ['one\ntwo\nthree', 'zero\none\nthree\nfour'],
            ['x\nx\nx', 'x\ny\nx'],
            ['', 'only new'],
            ['only old', ''],
            ['a\n\nb', 'a\nb\n'],
        ];
        for (const [o, n] of cases) {
            const d = computeLineDiff(o, n);
            expect(oldSide(d)).toBe(o);
            expect(newSide(d)).toBe(n);
        }
    });

    it('treats null-ish input as empty text', () => {
        // Callers pass String(value || ''); the helper also guards itself.
        const d = computeLineDiff(undefined as unknown as string, 'a');
        expect(newSide(d)).toBe('a');
        expect(computeLineDiff('', '')).toEqual([{ type: 'same', text: '' }]);
    });

    it('empty → text shows the empty old line as removed', () => {
        // ''.split('\n') is [''], so an empty old value is one blank line.
        expect(computeLineDiff('', 'new')).toEqual([
            { type: 'remove', text: '' },
            { type: 'add', text: 'new' },
        ]);
    });

    it('uses the LCS up to 500 total lines and a full replace above it', () => {
        const lines = (n: number) => Array.from({ length: n }, (_, i) => `l${i}`).join('\n');
        // 250 + 250 = 500 lines: still diffed, identical text is all same.
        const at = computeLineDiff(lines(250), lines(250));
        expect(at).toHaveLength(250);
        expect(at.every(o => o.type === 'same')).toBe(true);
        // 250 + 251 = 501 lines: every old line removed, every new line added.
        const over = computeLineDiff(lines(250), lines(251));
        expect(over).toHaveLength(501);
        expect(over.slice(0, 250).every(o => o.type === 'remove')).toBe(true);
        expect(over.slice(250).every(o => o.type === 'add')).toBe(true);
        expect(oldSide(over)).toBe(lines(250));
        expect(newSide(over)).toBe(lines(251));
    });
});
