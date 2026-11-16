import { useEffect, useRef } from 'react';

/**
 * Seed local form state from query data without clobbering edits.
 *
 * Edit pages copy a record into local state and save that state back. A
 * plain `useEffect(() => seed(data), [data])` re-runs on every refetch
 * (window focus, a mutation's invalidation, a websocket nudge, another
 * field's autosave), so whatever the user was typing is replaced by the
 * server copy.
 *
 * `seed(source)` runs when data first arrives, when `key` changes (a
 * different record), and on later refetches only while `isDirty` is false.
 * Leave `isDirty` out to seed once per key. Pages that navigate away after
 * saving need nothing else; pages that stay call `reseed()` after a save
 * so the next refetch is taken.
 */
export function useFormFromQuery<S>(
    source: S | null | undefined,
    seed: (source: S) => void,
    { key, isDirty }: { key?: string | null; isDirty?: boolean } = {},
): { reseed: () => void } {
    const seedRef = useRef(seed);
    seedRef.current = seed;
    const dirtyRef = useRef(isDirty);
    dirtyRef.current = isDirty;
    const seededKey = useRef<string | null | undefined>(undefined);
    const seeded = useRef(false);

    useEffect(() => {
        if (source === null || source === undefined) return;
        const k = key ?? null;
        const sameRecord = seeded.current && seededKey.current === k;
        // Same record: once-mode never reseeds; dirty-mode keeps the edits.
        if (sameRecord && (dirtyRef.current === undefined || dirtyRef.current)) return;
        seeded.current = true;
        seededKey.current = k;
        seedRef.current(source);
    }, [source, key]);

    return {
        reseed: () => {
            seeded.current = false;
        },
    };
}
