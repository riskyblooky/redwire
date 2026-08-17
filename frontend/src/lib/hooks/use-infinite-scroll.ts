'use client';

import { useEffect, useRef, useState } from 'react';

/**
 * Client-side infinite scroll / windowing over an already-loaded array.
 *
 * Renders only the first `pageSize` items and reveals another `pageSize` each
 * time the returned `sentinelRef` element scrolls near the viewport — so a big
 * list (each row of which mounts its own tooltips/hooks) doesn't pay the full
 * render cost up front. Below `threshold` items it renders everything and skips
 * the machinery entirely.
 *
 * The window resets to the first page whenever the underlying list size changes
 * (e.g. a search/filter narrows or widens the set), so you land at the top of
 * the new result set. Sorting keeps the length, so it just re-slices the new
 * order in place.
 */
export function useInfiniteScroll<T>(
    items: T[],
    opts?: { pageSize?: number; threshold?: number; resetKey?: string },
) {
    const pageSize = opts?.pageSize ?? 20;
    const threshold = opts?.threshold ?? 20;
    const [count, setCount] = useState(pageSize);
    const sentinelRef = useRef<HTMLDivElement | null>(null);

    // Reset the window to the first page when the result set is redefined. By
    // default that's any length change (a flat list's filter/search). Pass an
    // explicit `resetKey` (e.g. search+sort) when the length also changes for
    // reasons that should NOT reset — like expanding a tree node.
    const resetDep = opts?.resetKey ?? items.length;
    useEffect(() => {
        setCount(pageSize);
    }, [resetDep, pageSize]);

    const windowed = items.length > threshold;
    const visible = windowed ? items.slice(0, count) : items;
    const hasMore = windowed && count < items.length;

    useEffect(() => {
        if (!hasMore) return;
        const el = sentinelRef.current;
        if (!el) return;
        const obs = new IntersectionObserver(
            (entries) => {
                if (entries[0].isIntersecting) setCount(c => c + pageSize);
            },
            { rootMargin: '600px' },
        );
        obs.observe(el);
        return () => obs.disconnect();
    }, [hasMore, pageSize, items.length]);

    return { visible, sentinelRef, hasMore, shownCount: visible.length, total: items.length };
}
