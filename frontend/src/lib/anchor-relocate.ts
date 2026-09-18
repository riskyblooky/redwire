/**
 * Re-location algorithm for anchored peer-review comments.
 * See docs/anchored-comments-peer-review.md §7.3.
 *
 * Pure string logic (no ProseMirror dependency) so it can be reasoned about and
 * tested in isolation. Given the current plain text of a field and a stored
 * anchor, find the character range the anchor now refers to — or null if the
 * quoted text can no longer be found (the comment has orphaned).
 */

export interface StoredAnchor {
    quote: string;
    prefix?: string | null;
    suffix?: string | null;
    occurrence?: number | null;
}

export interface CharRange {
    start: number;
    end: number;
}

/** Length of the longest common suffix of a and b. */
function commonSuffixLen(a: string, b: string): number {
    let n = 0;
    let i = a.length - 1;
    let j = b.length - 1;
    while (i >= 0 && j >= 0 && a[i] === b[j]) {
        n++;
        i--;
        j--;
    }
    return n;
}

/** Length of the longest common prefix of a and b. */
function commonPrefixLen(a: string, b: string): number {
    let n = 0;
    const max = Math.min(a.length, b.length);
    while (n < max && a[n] === b[n]) n++;
    return n;
}

/** All start indices of `needle` in `hay` (non-overlapping left-to-right). */
function allIndicesOf(hay: string, needle: string): number[] {
    const out: number[] = [];
    if (!needle) return out;
    let i = hay.indexOf(needle);
    while (i !== -1) {
        out.push(i);
        i = hay.indexOf(needle, i + needle.length);
    }
    return out;
}

/**
 * Locate `anchor.quote` in `text`. When the quote occurs more than once,
 * disambiguate by how well the surrounding text matches the stored prefix/suffix
 * context; on a tie (or no context), fall back to the stored occurrence index,
 * then to the first match. Returns null when the quote is absent (orphaned).
 */
export function relocateAnchor(text: string, anchor: StoredAnchor): CharRange | null {
    const quote = anchor.quote || '';
    if (!quote) return null;

    const matches = allIndicesOf(text, quote);
    if (matches.length === 0) return null;
    if (matches.length === 1) {
        return { start: matches[0], end: matches[0] + quote.length };
    }

    const prefix = anchor.prefix || '';
    const suffix = anchor.suffix || '';

    let best: CharRange | null = null;
    let bestScore = -1;
    for (const start of matches) {
        const end = start + quote.length;
        let score = 0;
        if (prefix) {
            const before = text.slice(Math.max(0, start - prefix.length), start);
            score += commonSuffixLen(before, prefix);
        }
        if (suffix) {
            const after = text.slice(end, end + suffix.length);
            score += commonPrefixLen(after, suffix);
        }
        if (score > bestScore) {
            bestScore = score;
            best = { start, end };
        }
    }

    // No usable context signal → prefer the stored occurrence index.
    if (bestScore <= 0) {
        const occ = anchor.occurrence ?? 0;
        if (occ >= 0 && occ < matches.length) {
            return { start: matches[occ], end: matches[occ] + quote.length };
        }
        return { start: matches[0], end: matches[0] + quote.length };
    }
    return best;
}

/**
 * Count how many times `quote` occurs strictly before character index `before`
 * in `text` — used at creation time to record the anchor's occurrence index.
 */
export function occurrenceIndexAt(text: string, quote: string, before: number): number {
    if (!quote) return 0;
    let count = 0;
    let i = text.indexOf(quote);
    while (i !== -1 && i < before) {
        count++;
        i = text.indexOf(quote, i + quote.length);
    }
    return count;
}
