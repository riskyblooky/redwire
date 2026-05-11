/**
 * Search relevance scoring utility.
 * Scores how closely a value matches a search term:
 *   0 = exact match (best)
 *   1 = starts with the term
 *   2 = contains the term
 *   3 = no match
 */
export function getSearchRelevance(value: string, term: string): number {
    const v = value.toLowerCase();
    const t = term.toLowerCase();
    if (v === t) return 0;
    if (v.startsWith(t)) return 1;
    if (v.includes(t)) return 2;
    return 3;
}

/**
 * Get the best (lowest) relevance score across multiple field values.
 * This lets you score an item by checking its name, identifier, description, etc.
 */
export function getBestRelevance(fields: string[], term: string): number {
    let best = 3;
    for (const field of fields) {
        if (!field) continue;
        const score = getSearchRelevance(field, term);
        if (score < best) best = score;
        if (best === 0) return 0; // can't beat exact match
    }
    return best;
}

/**
 * Comparator that sorts by search relevance first, then falls back to a
 * secondary comparator (e.g. alphabetical, date, severity).
 *
 * Usage:
 *   items.sort(relevanceComparator(term, ['name', 'identifier'], existingComparator))
 */
export function relevanceComparator<T>(
    term: string,
    fieldAccessors: ((item: T) => string)[],
    fallback?: (a: T, b: T) => number
): (a: T, b: T) => number {
    if (!term) return fallback || (() => 0);

    return (a: T, b: T) => {
        const scoreA = Math.min(...fieldAccessors.map(fn => getSearchRelevance(fn(a) || '', term)));
        const scoreB = Math.min(...fieldAccessors.map(fn => getSearchRelevance(fn(b) || '', term)));
        if (scoreA !== scoreB) return scoreA - scoreB;
        return fallback ? fallback(a, b) : 0;
    };
}
