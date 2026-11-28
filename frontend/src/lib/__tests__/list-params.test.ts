import { describe, expect, it } from 'vitest';
import { readListParams, writeListParams, hasNonDefault, toSkipLimit, type ParamSpec } from '@/lib/list-params';
import { serializeListQuery } from '@/lib/fetch-page';

const spec = {
    q: { kind: 'string' },
    sev: { kind: 'array' },
    sort: { kind: 'string', default: 'created_at' },
    dir: { kind: 'enum', values: ['asc', 'desc'], default: 'desc' },
    page: { kind: 'int', default: 1, min: 1 },
    size: { kind: 'int', default: 50, min: 1, max: 500 },
} satisfies ParamSpec;

const read = (qs: string, prefix = '') => readListParams(new URLSearchParams(qs), spec, prefix);

describe('readListParams', () => {
    it('gives the defaults for an empty query', () => {
        expect(read('')).toEqual({ q: '', sev: [], sort: 'created_at', dir: 'desc', page: 1, size: 50 });
    });

    it('reads repeated keys as an array and ignores empty values', () => {
        expect(read('sev=HIGH&sev=&sev=LOW').sev).toEqual(['HIGH', 'LOW']);
    });

    it('falls back to the default on a bad value', () => {
        expect(read('page=0&size=9999&dir=sideways').page).toBe(1);
        expect(read('page=abc').page).toBe(1);
        expect(read('size=9999').size).toBe(50);
        expect(read('dir=sideways').dir).toBe('desc');
        expect(read('page=1.5').page).toBe(1);
    });

    it('reads only its own prefix', () => {
        expect(read('f_q=sql&q=other&a_q=asset', 'f_').q).toBe('sql');
    });
});

describe('writeListParams', () => {
    it('leaves defaults out and keeps other keys', () => {
        const out = writeListParams(new URLSearchParams('tab=findings&a_q=keep'), spec,
            { q: 'sql', sev: ['HIGH', 'LOW'], sort: 'created_at', page: 1 }, 'f_');
        expect(out.toString()).toBe('tab=findings&a_q=keep&f_q=sql&f_sev=HIGH&f_sev=LOW');
    });

    it('removes a key reset to its default', () => {
        const out = writeListParams(new URLSearchParams('f_q=sql&f_page=3'), spec, { q: '', page: 1 }, 'f_');
        expect(out.toString()).toBe('');
    });

    it('only touches the keys in the patch', () => {
        const out = writeListParams(new URLSearchParams('f_q=sql&f_page=3'), spec, { page: 4 }, 'f_');
        expect(out.toString()).toBe('f_q=sql&f_page=4');
    });

    it('round-trips', () => {
        const state = { q: 'domain admin', sev: ['CRITICAL'], sort: 'severity', dir: 'asc', page: 2, size: 100 };
        expect(read(writeListParams(new URLSearchParams(), spec, state).toString())).toEqual(state);
    });
});

describe('helpers', () => {
    it('hasNonDefault', () => {
        expect(hasNonDefault(spec, read(''), ['q', 'sev'])).toBe(false);
        expect(hasNonDefault(spec, read('sev=LOW'), ['q', 'sev'])).toBe(true);
    });

    it('toSkipLimit is 1-based', () => {
        expect(toSkipLimit(1, 50)).toEqual({ skip: 0, limit: 50 });
        expect(toSkipLimit(3, 25)).toEqual({ skip: 50, limit: 25 });
        expect(toSkipLimit(0, 25)).toEqual({ skip: 0, limit: 25 });
    });

    it('serializeListQuery repeats array keys and drops empties', () => {
        expect(serializeListQuery({ severity: ['HIGH', 'LOW'], q: '', status: [], skip: 0, x: undefined }))
            .toBe('severity=HIGH&severity=LOW&skip=0');
    });
});
