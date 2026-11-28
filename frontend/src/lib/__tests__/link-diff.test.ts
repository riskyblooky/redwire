import { describe, expect, it } from 'vitest';
import { diffLinkSelection } from '@/lib/link-diff';

describe('diffLinkSelection', () => {
    it('links newly selected ids and unlinks deselected ones', () => {
        const { toLink, toUnlink } = diffLinkSelection(new Set(['a', 'b', 'c']), new Set(['b', 'c', 'd', 'e']));
        expect(toLink).toEqual(['d', 'e']);
        expect(toUnlink).toEqual(['a']);
    });

    it('is a no-op when the selection equals what is linked', () => {
        expect(diffLinkSelection(new Set(['x', 'y']), new Set(['y', 'x']))).toEqual({ toLink: [], toUnlink: [] });
    });

    it('handles empty sets on either side', () => {
        expect(diffLinkSelection(new Set(), new Set())).toEqual({ toLink: [], toUnlink: [] });
        expect(diffLinkSelection(new Set(), new Set(['a', 'b']))).toEqual({ toLink: ['a', 'b'], toUnlink: [] });
        expect(diffLinkSelection(new Set(['a', 'b']), new Set())).toEqual({ toLink: [], toUnlink: ['a', 'b'] });
    });

    it('swaps a full selection without overlap', () => {
        expect(diffLinkSelection(new Set(['a']), new Set(['b']))).toEqual({ toLink: ['b'], toUnlink: ['a'] });
    });

    it('does not mutate its inputs', () => {
        const linked = new Set(['a', 'b']);
        const selected = new Set(['b', 'c']);
        diffLinkSelection(linked, selected);
        expect([...linked]).toEqual(['a', 'b']);
        expect([...selected]).toEqual(['b', 'c']);
    });

    it('never puts an id in both lists', () => {
        const { toLink, toUnlink } = diffLinkSelection(new Set(['1', '2', '3']), new Set(['3', '4']));
        expect(toLink.filter(id => toUnlink.includes(id))).toEqual([]);
        // Applying the diff to the linked set yields exactly the selection.
        const after = new Set(['1', '2', '3']);
        toUnlink.forEach(id => after.delete(id));
        toLink.forEach(id => after.add(id));
        expect([...after].sort()).toEqual(['3', '4']);
    });
});
