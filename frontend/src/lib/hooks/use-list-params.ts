'use client';

import { useCallback, useMemo } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { readListParams, writeListParams, type ParamSpec, type ParamState } from '@/lib/list-params';

/**
 * A list's view state, read from and written to the URL (see
 * ``lib/list-params``). ``set(patch)`` replaces the history entry rather than
 * pushing one, so typing in a search box doesn't fill the back stack, and
 * resets ``page`` to 1 unless the patch sets it (a new filter starts at the
 * first page).
 */
export function useListParams<S extends ParamSpec>(spec: S, prefix = '') {
    const searchParams = useSearchParams();
    const router = useRouter();
    const pathname = usePathname();
    const query = searchParams.toString();

    // The spec is a module constant at every call site, so the query string
    // is the only real input.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    const state = useMemo(() => readListParams(new URLSearchParams(query), spec, prefix), [query, prefix]);

    const set = useCallback((patch: Partial<ParamState<S>>) => {
        const full: Partial<ParamState<S>> = { ...patch };
        if ('page' in spec && !('page' in patch)) (full as Record<string, unknown>).page = 1;
        // Read the live URL, not the render's copy: two quick updates (a
        // filter click right after typing) must not drop the first.
        const current = new URLSearchParams(typeof window !== 'undefined' ? window.location.search : query);
        const next = writeListParams(current, spec, full, prefix).toString();
        if (next === current.toString()) return;
        router.replace(next ? `${pathname}?${next}` : pathname, { scroll: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [pathname, prefix, router, query]);

    return [state, set] as const;
}
