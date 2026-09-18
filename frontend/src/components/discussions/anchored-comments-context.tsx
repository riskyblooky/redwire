'use client';

/**
 * Coordinates the page-level comment rail with the per-field annotation editors
 * for anchored peer-review comments (docs/anchored-comments-peer-review.md).
 *
 * Each annotatable field registers an "opener" keyed by its field name. The rail
 * calls `openField(field, threadId)` to switch that field into annotation mode
 * and focus a specific thread. The provider is optional — `useAnchoredComments`
 * returns inert defaults when there's no provider, so an annotatable field works
 * standalone (just without the page rail driving it).
 */
import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react';

type Opener = (threadId?: string) => void;

interface AnchoredCommentsValue {
    /** A field registers how to open itself into annotation mode. Returns an unregister fn. */
    registerOpener: (field: string, open: Opener) => () => void;
    /** Ask a field to open into annotation mode (optionally focusing a thread). */
    openField: (field: string, threadId?: string) => void;
    /** The thread the rail/highlight most recently focused. */
    focusedThreadId: string | null;
    setFocusedThreadId: (id: string | null) => void;
}

const noop = () => {};
const AnchoredCommentsContext = createContext<AnchoredCommentsValue>({
    registerOpener: () => noop,
    openField: noop,
    focusedThreadId: null,
    setFocusedThreadId: noop,
});

export function AnchoredCommentsProvider({ children }: { children: ReactNode }) {
    const openers = useRef<Map<string, Opener>>(new Map());
    const [focusedThreadId, setFocusedThreadId] = useState<string | null>(null);

    const registerOpener = useCallback((field: string, open: Opener) => {
        openers.current.set(field, open);
        return () => {
            if (openers.current.get(field) === open) openers.current.delete(field);
        };
    }, []);

    const openField = useCallback((field: string, threadId?: string) => {
        setFocusedThreadId(threadId ?? null);
        openers.current.get(field)?.(threadId);
    }, []);

    const value = useMemo<AnchoredCommentsValue>(
        () => ({ registerOpener, openField, focusedThreadId, setFocusedThreadId }),
        [registerOpener, openField, focusedThreadId],
    );

    return <AnchoredCommentsContext.Provider value={value}>{children}</AnchoredCommentsContext.Provider>;
}

export function useAnchoredComments() {
    return useContext(AnchoredCommentsContext);
}
