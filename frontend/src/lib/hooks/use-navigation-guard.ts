'use client';

import { useEffect, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';

/**
 * Navigation guard hook for edit pages.
 *
 * Handles three scenarios when `isDirty` is true:
 *  1. Browser tab close / refresh  → native `beforeunload` prompt
 *  2. Browser back/forward button  → `popstate` intercept + confirm()
 *  3. In-app navigation (back btn) → `navigateWithGuard()` helper
 *
 * Usage:
 *   const { navigateWithGuard } = useNavigationGuard(isDirty, confirm);
 *
 *   // For in-app buttons:
 *   <Button onClick={() => navigateWithGuard('/some/path')}>Back</Button>
 */
export function useNavigationGuard(
    isDirty: boolean,
    confirm: (opts: {
        title: string;
        description: string;
        variant?: 'default' | 'destructive' | 'warning';
        confirmLabel?: string;
        extraAction?: { label: string; variant?: 'default' | 'destructive' | 'outline' };
    }) => Promise<boolean | string>,
) {
    const router = useRouter();
    const isDirtyRef = useRef(isDirty);
    isDirtyRef.current = isDirty;

    // 1. Browser tab close / refresh
    useEffect(() => {
        const handler = (e: BeforeUnloadEvent) => {
            if (!isDirtyRef.current) return;
            e.preventDefault();
        };
        window.addEventListener('beforeunload', handler);
        return () => window.removeEventListener('beforeunload', handler);
    }, []);

    // 2. Browser back/forward button (popstate)
    //    Push a sentinel history entry so the first back-press lands here
    //    instead of actually navigating away.
    useEffect(() => {
        // Push sentinel entry
        window.history.pushState({ navigationGuard: true }, '');

        const handlePopState = async () => {
            if (!isDirtyRef.current) {
                // Not dirty → let the navigation happen (go back for real)
                window.history.back();
                return;
            }

            // Re-push sentinel so subsequent back presses are also caught
            window.history.pushState({ navigationGuard: true }, '');

            const ok = await confirm({
                title: 'Unsaved Changes',
                description:
                    'You have unsaved changes. Are you sure you want to leave? Your changes will be lost.',
                variant: 'warning',
                confirmLabel: 'Leave',
            });

            if (ok) {
                // User confirmed → go back twice (pop sentinel + real back)
                isDirtyRef.current = false; // prevent re-trigger
                window.history.go(-2);
            }
            // User cancelled → sentinel already re-pushed, stay on page
        };

        window.addEventListener('popstate', handlePopState);
        return () => {
            window.removeEventListener('popstate', handlePopState);
        };
    }, [confirm]);

    // 3. In-app navigation helper
    const navigateWithGuard = useCallback(
        async (path: string) => {
            if (!isDirtyRef.current) {
                router.push(path);
                return;
            }
            const ok = await confirm({
                title: 'Unsaved Changes',
                description:
                    'You have unsaved changes. Are you sure you want to leave? Your changes will be lost.',
                variant: 'warning',
                confirmLabel: 'Leave',
            });
            if (ok) {
                isDirtyRef.current = false;
                router.push(path);
            }
        },
        [router, confirm],
    );

    return { navigateWithGuard };
}
