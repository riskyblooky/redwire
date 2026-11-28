import { describe, expect, it } from 'vitest';
import { occurrenceIndexAt, relocateAnchor } from '@/lib/anchor-relocate';

const slice = (text: string, r: { start: number; end: number } | null) => (r ? text.slice(r.start, r.end) : null);

describe('relocateAnchor', () => {
    it('returns null for an empty quote', () => {
        expect(relocateAnchor('anything', { quote: '' })).toBeNull();
        expect(relocateAnchor('', { quote: '' })).toBeNull();
    });

    it('returns null (orphaned) when the quote is gone', () => {
        expect(relocateAnchor('the host was patched', { quote: 'unpatched' })).toBeNull();
        expect(relocateAnchor('', { quote: 'x' })).toBeNull();
    });

    it('follows a unique quote that moved', () => {
        const text = 'New intro paragraph. The admin panel lacks CSRF tokens.';
        const r = relocateAnchor(text, { quote: 'lacks CSRF', prefix: 'panel ', suffix: ' tokens', occurrence: 3 });
        expect(r).toEqual({ start: text.indexOf('lacks CSRF'), end: text.indexOf('lacks CSRF') + 10 });
    });

    it('is case-sensitive', () => {
        expect(relocateAnchor('Root access', { quote: 'root' })).toBeNull();
    });

    it('picks the duplicate whose prefix matches', () => {
        const text = 'host A: SMB signing off. host B: SMB signing off.';
        const r = relocateAnchor(text, { quote: 'SMB signing off', prefix: 'host B: ' });
        expect(r?.start).toBe(text.lastIndexOf('SMB signing off'));
        expect(slice(text, r)).toBe('SMB signing off');
    });

    it('picks the duplicate whose suffix matches', () => {
        const text = 'weak password on web01; weak password on db01;';
        const r = relocateAnchor(text, { quote: 'weak password', suffix: ' on db01' });
        expect(r?.start).toBe(text.lastIndexOf('weak password'));
    });

    it('scores prefix + suffix together and prefers the closer context', () => {
        const text = 'xx foo yy | ax foo yb';
        // #1 shares "x " / " y" with the stored context (score 4); #2 matches
        // all of "ax " / " yb" (score 6).
        const r = relocateAnchor(text, { quote: 'foo', prefix: 'ax ', suffix: ' yb' });
        expect(r?.start).toBe(text.lastIndexOf('foo'));
    });

    it('scores partial context (a tail of the prefix still counts)', () => {
        const text = '1. edited foo; 2. other foo';
        // #1 is preceded by " edited " (8 chars of the stored prefix), #2 only by " ".
        const r = relocateAnchor(text, { quote: 'foo', prefix: 'was edited ' });
        expect(r?.start).toBe(text.indexOf('foo'));
    });

    it('falls back to the stored occurrence when there is no context', () => {
        const text = 'a TODO b TODO c TODO';
        expect(relocateAnchor(text, { quote: 'TODO', occurrence: 2 })?.start).toBe(text.lastIndexOf('TODO'));
        expect(relocateAnchor(text, { quote: 'TODO', occurrence: 1 })?.start).toBe(text.indexOf('TODO', 3));
        expect(relocateAnchor(text, { quote: 'TODO', prefix: null, suffix: null, occurrence: null })?.start).toBe(2);
    });

    it('falls back to the occurrence when the context matches nothing', () => {
        const text = 'a TODO b TODO';
        expect(relocateAnchor(text, { quote: 'TODO', prefix: 'zzz', suffix: 'qqq', occurrence: 1 })?.start).toBe(9);
    });

    it('falls back to the first match when the occurrence is out of range', () => {
        const text = 'x y x y';
        expect(relocateAnchor(text, { quote: 'x', occurrence: 5 })?.start).toBe(0);
        expect(relocateAnchor(text, { quote: 'x', occurrence: -1 })?.start).toBe(0);
    });

    it('does not count overlapping matches', () => {
        // "aa" in "aaaa" is found at 0 and 2, not 1.
        const text = 'aaaa';
        expect(relocateAnchor(text, { quote: 'aa', occurrence: 1 })).toEqual({ start: 2, end: 4 });
    });

    it('handles a quote at the very start and end of the text', () => {
        const text = 'end start end';
        expect(relocateAnchor(text, { quote: 'end', prefix: 'start ' })).toEqual({ start: 10, end: 13 });
        expect(relocateAnchor(text, { quote: 'end', suffix: ' start' })).toEqual({ start: 0, end: 3 });
    });

    // BUG: the doc comment says "on a tie ... fall back to the stored occurrence
    // index", but a tie with a positive context score keeps the FIRST match.
    // A repeated phrase with identical surroundings ("see foo. see foo.")
    // anchored on its second copy used to relocate onto the first one.
    it('on a context tie, uses the stored occurrence', () => {
        const text = 'see foo. see foo.';
        const r = relocateAnchor(text, { quote: 'foo', prefix: 'see ', suffix: '.', occurrence: 1 });
        expect(r).toEqual({ start: 13, end: 16 });
    });

    it('a better context match beats the stored occurrence', () => {
        const text = 'see foo. read foo!';
        const r = relocateAnchor(text, { quote: 'foo', prefix: 'read ', suffix: '!', occurrence: 0 });
        expect(r).toEqual({ start: 14, end: 17 });
    });
});

describe('occurrenceIndexAt', () => {
    it('counts occurrences that start before the index', () => {
        const text = 'ab ab ab';
        expect(occurrenceIndexAt(text, 'ab', 0)).toBe(0);
        expect(occurrenceIndexAt(text, 'ab', 1)).toBe(1);
        expect(occurrenceIndexAt(text, 'ab', 3)).toBe(1);   // the match AT 3 is not before it
        expect(occurrenceIndexAt(text, 'ab', 4)).toBe(2);
        expect(occurrenceIndexAt(text, 'ab', 100)).toBe(3);
    });

    it('is 0 for an empty or absent quote', () => {
        expect(occurrenceIndexAt('abc', '', 3)).toBe(0);
        expect(occurrenceIndexAt('abc', 'z', 3)).toBe(0);
    });

    it('agrees with relocateAnchor when there is no context', () => {
        const text = 'x-x-x-x';
        for (const start of [0, 2, 4, 6]) {
            const occurrence = occurrenceIndexAt(text, 'x', start);
            expect(relocateAnchor(text, { quote: 'x', occurrence })?.start).toBe(start);
        }
    });

    it('uses the same non-overlapping scan as relocation', () => {
        // Selecting the second "aa" of "aaaa" (index 2) is occurrence 1.
        expect(occurrenceIndexAt('aaaa', 'aa', 2)).toBe(1);
    });
});
