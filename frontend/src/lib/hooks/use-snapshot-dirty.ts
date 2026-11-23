import { useEffect, useState } from 'react';

function sameValue(a: unknown, b: unknown): boolean {
    if (Object.is(a, b)) return true;
    if (typeof a !== 'object' || typeof b !== 'object' || a === null || b === null) return false;
    if (Array.isArray(a) !== Array.isArray(b)) return false;
    if (Array.isArray(a)) {
        const bb = b as unknown[];
        return a.length === bb.length && a.every((v, i) => sameValue(v, bb[i]));
    }
    const ka = Object.keys(a as object);
    const kb = Object.keys(b as object);
    return ka.length === kb.length
        && ka.every(k => sameValue((a as Record<string, unknown>)[k], (b as Record<string, unknown>)[k]));
}

/**
 * Dirty flag for editors whose state is spread over many setters.
 *
 * Pass what Save would send (plain data) and whether the form has been
 * seeded (always true for a new record). The first snapshot taken once
 * `ready` is true is the baseline; the form is dirty while the current
 * snapshot differs from it, so undoing an edit makes it clean again.
 */
export function useSnapshotDirty(snapshot: unknown, ready: boolean): boolean {
    const [baseline, setBaseline] = useState<{ value: unknown } | null>(null);
    useEffect(() => {
        if (ready && baseline === null) setBaseline({ value: snapshot });
    }, [ready, baseline, snapshot]);
    return baseline !== null && !sameValue(baseline.value, snapshot);
}
